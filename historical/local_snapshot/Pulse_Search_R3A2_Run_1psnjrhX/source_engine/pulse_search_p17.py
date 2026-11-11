#!/usr/bin/env python3
"""R2-P17: rights-preserving, source-scoped merging of two owner-accepted independent indexes.

Research only: read two owner databases, clone P16 index, import P12 pages where origin/source
policy does not conflict, and compare query coverage without crawling, paid providers or writes
to either original database. Never promote rights to commercial/public use.
"""
from __future__ import annotations
from contextlib import closing
import argparse
import hashlib
import html
import json
from pathlib import Path
import sqlite3
import re
import sys

import pulse_search_engine as eng
import pulse_search_p16 as p16
import pulse_search_p11 as shadow
import pulse_search_real_questions as r9

VERSION = '0.17.0-r2p17-source-safe-research-index'
REVIEW_SHA = '98eea7d517d308060fa9457fcfcb07496d551d26b9092ce446fd72c56495f0cf'
CITY = 'https://www.london.gov.uk/events/'
CITY_PAGES = frozenset({CITY+'london-new-years-eve-2026',CITY+'london-games-festival-2026',
                        CITY+'diwali-square-2026',CITY+'city-hall-open-house-2026'})
EXTRA_QUERIES = ['London Games Festival 2026','Diwali on the Square 2026',
                 'City Hall Open House 2026',"London New Year's Eve 2027"]
MAX_IMPORTED = 100

class Hold(ValueError):pass


def ro(path):
    p=Path(path).resolve(strict=True)
    if not p.is_file() or p.is_symlink() or p.stat().st_size>2_000_000_000:
        raise Hold('invalid_input_database')
    conn=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=5)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    return conn


def source_rows(c):
    rows=[dict(x) for x in c.execute('SELECT * FROM sources ORDER BY source_id')]
    for s in rows:
        if s['approved']!=1 or s['enabled']!=1 or s['display_mode']!='metadata_only' or len(s['rights_basis'])<20:
            raise Hold('source_approval_or_rights_invalid')
        try:paths=json.loads(s['paths'])
        except (ValueError,TypeError):raise Hold('invalid_source_paths')
        if not paths or not all(isinstance(p,str) and p.startswith('/') and '..' not in p for p in paths):
            raise Hold('invalid_source_paths')
    return rows


def page_rows(c):
    return [dict(x) for x in c.execute('''SELECT url,source_id,title,body,content_sha256,fetched_at,indexed,duplicate_of
                                         FROM pages WHERE indexed=1 ORDER BY url''')]


def validate_page(page,src):
    if not eng.scope(page['url'],src) or eng.normal_url(page['url'])!=page['url']:
        raise Hold('indexed_page_outside_source_approved_paths')
    if page['duplicate_of'] is not None or page['indexed'] != 1:
        raise Hold('unexpected_page_state')
    if (not page['title'] or not page['body'] or len(page['title'])>300 or len(page['body'])>120000
        or not re.fullmatch('[0-9a-f]{64}',page['content_sha256'])):
        # Test fixtures also use genuine content hashes to represent live content.
        raise Hold('invalid_indexed_page_content_or_hash')


def verify_input(p16db,p12db,p12report,review):
    meta=json.loads(Path(p12report).read_text(encoding='utf-8'))
    ratings=json.loads(Path(review).read_text(encoding='utf-8'))
    if (meta.get('results_sha256')!=REVIEW_SHA or r9.digest({k:v for k,v in meta.items() if k!='results_sha256'})!=REVIEW_SHA
       or ratings.get('results_sha256')!=REVIEW_SHA or ratings.get('version')!='r2p12-human-review'):
        raise Hold('r2p12_human_review_fingerprint_mismatch')
    if len(meta.get('questions',[]))!=15 or len(ratings.get('questions',[]))!=15:
        raise Hold('missing_fifteen_r2p12_questions')
    if [x.get('id') for x in meta['questions']] != [x.get('id') for x in ratings['questions']]:
        raise Hold('review_question_binding_mismatch')
    for q,r in zip(meta['questions'],ratings['questions']):
        if len(q['results'])!=len(r['judgements']):raise Hold('review_result_count_mismatch')
        for a,b in zip(q['results'],r['judgements']):
            if a['url']!=b['url'] or a['position']!=b['position'] or type(b['grade']) is not int or b['grade'] not in (0,1,2,3):
                raise Hold('review_result_binding_mismatch')
    with closing(ro(p16db)) as base,closing(ro(p12db)) as old:
        if base.execute('PRAGMA quick_check').fetchone()[0]!='ok' or old.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise Hold('source_db_integrity_failure')
        bsrc=source_rows(base);psrc=source_rows(old)
        if len(bsrc)!=1 or bsrc[0]['origin']!='https://www.london.gov.uk' or json.loads(bsrc[0]['paths'])!=['/events/']:
            raise Hold('unexpected_r2p16_source_scope')
        count=base.execute("SELECT COUNT(*) FROM sitemap_candidates WHERE source_id='london_events_p14'").fetchone()[0]
        urls={x['url'] for x in page_rows(base)}
        if count!=112 or urls!=CITY_PAGES:raise Hold('r2p16_owner_four_page_fingerprint_mismatch')
        if r9.digest([dict(x) for x in old.execute('SELECT url,source_id,title,content_sha256,indexed FROM pages ORDER BY url')])!=meta.get('index_fingerprint'):
            raise Hold('r2p12_live_index_fingerprint_mismatch')
        if len(psrc)<3:raise Hold('r2p12_source_count_invalid')
        so={s['source_id']:s for s in psrc}
        oldpages=page_rows(old)
        if not (5<=len(oldpages)<=MAX_IMPORTED):raise Hold('r2p12_page_count_outside_bound')
        for x in oldpages:validate_page(x,so[x['source_id']])
        for x in page_rows(base):validate_page(x,bsrc[0])
    return meta,ratings


def build_evidence(db,meta,ratings):
    report=[]
    qs=[(q['id'],q['q']) for q in meta['questions']]+[(f'additional_{i}',x) for i,x in enumerate(EXTRA_QUERIES,1)]
    rlookup={r['id']:{j['url']:(j['grade'],j['answer']) for j in r['judgements']} for r in ratings['questions']}
    for qid,query in qs:
        payload=shadow.search_payload(db,query,limit=5)
        matches=[x for x in payload['results'] if p16.year_compatible(query,x)]
        known=rlookup.get(qid,{})
        hits=[]
        for hit in matches:
            grade_answer=known.get(hit['url'])
            hits.append({k:hit[k] for k in ('url','title','source_id','fetched_at','position')}
                        |{'previous_human_grade':grade_answer[0] if grade_answer else None,
                          'previous_human_answer':grade_answer[1] if grade_answer else None,
                          'verification':'PREVIOUSLY_HUMAN_GRADED' if grade_answer else 'HUMAN_REVIEW_REQUIRED'})
        report.append({'id':qid,'query':query,'coverage_status':'INDEXED_MATCHES_UNVERIFIED' if hits else 'NO_INDEXED_MATCH',
                       'results':hits,'top1_known_direct_answer':bool(hits and hits[0]['previous_human_answer']=='yes'),
                       'new_top1_needs_review':bool(hits and hits[0]['previous_human_grade'] is None),
                       'year_conflicts_suppressed':len(payload['results'])-len(matches)})
    return report


def render(report):
    rows=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Pulse Search R2-P17 research</title>',
          '<style>body{max-width:1100px;margin:2rem auto;padding:1rem;font:16px system-ui;line-height:1.5}section{border:1px solid #bbb;border-radius:10px;padding:1rem;margin:1.2rem 0}small{color:#555}li{overflow-wrap:anywhere}</style>',
          '<h1>Pulse Search — Cross-source research results</h1>',
          '<p><strong>Internal metadata research only.</strong> No live browsing, paid APIs, public search release, or commercial snippet rights. A hit is not automatically a verified answer.</p>',
          '<p>Sources: '+str(report['combined_index']['sources'])+'; indexed pages: '+str(report['combined_index']['indexed_pages'])+'. Conflicting original-source scope skipped: '+str(len(report['skipped_origin_policy_conflicts']))+'.</p>']
    for q in report['questions']:
        rows.append('<section><h2>'+html.escape(q['query'])+'</h2><small>'+q['coverage_status']+'</small>')
        if q['results']:
            rows.append('<ol>')
            for r in q['results']:
                rows.append('<li><a href="'+html.escape(r['url'],quote=True)+'" rel="noopener noreferrer">'+html.escape(r['title'])+'</a> <small>source '+html.escape(r['source_id'])+'; '+html.escape(r['verification'])+'</small></li>')
            rows.append('</ol>')
        else:rows.append('<p>No indexed match; not proof of absence from the open web.</p>')
        rows.append('</section>')
    return '\n'.join(rows+['</html>'])+'\n'


def execute(p16db,p12db,p12report,review,out_dir):
    o=Path(out_dir).resolve()
    if o.exists():raise Hold('output_directory_already_exists')
    paths=[Path(x).resolve(strict=True) for x in (p16db,p12db)]
    if len(set(paths))!=2 or o in paths:raise Hold('input_db_path_collision')
    sources_hash={str(x):p16.sha256(x) for x in paths}
    meta,ratings=verify_input(p16db,p12db,p12report,review)
    o.mkdir(parents=True)
    clone=o/'combined_research_index.sqlite'
    p16.copy_db_readonly(p16db,clone)
    included=[];skipped=[];dups=[]
    with closing(ro(p12db)) as old:
        p12_sources=source_rows(old)
        pages=page_rows(old)
        with eng.dbopen(clone) as target:
            existing=source_rows(target)
            by_origin={s['origin']:s for s in existing};by_id={s['source_id']:s for s in existing}
            imported_sources={}
            for s in p12_sources:
                if s['origin'] in by_origin:
                    skipped.append({'origin':s['origin'],'source_id':s['source_id'],
                                    'reason':'ORIGIN_PRESENT_WITH_DIFFERENT_APPROVED_PATH_SCOPE_NOT_AUTOMATICALLY_EXPANDED'})
                    continue
                if s['source_id'] in by_id:
                    raise Hold('source_id_collision_between_different_origins')
                target.execute('INSERT INTO sources(source_id,origin,paths,approved,display_mode,rights_basis,enabled) VALUES(?,?,?,?,?,?,?)',
                               tuple(s[k] for k in ('source_id','origin','paths','approved','display_mode','rights_basis','enabled')))
                imported_sources[s['source_id']]=s
            for p in pages:
                if p['source_id'] not in imported_sources:continue
                validate_page(p,imported_sources[p['source_id']])
                if target.execute('SELECT 1 FROM pages WHERE url=?',(p['url'],)).fetchone():
                    raise Hold('duplicate_url_requires_manual_source_policy_reconciliation')
                if target.execute('SELECT 1 FROM pages WHERE content_sha256=? AND indexed=1',(p['content_sha256'],)).fetchone():
                    dups.append(p['url']);continue
                rowid=target.execute('INSERT INTO pages(url,source_id,title,body,content_sha256,fetched_at,duplicate_of,indexed) VALUES(?,?,?,?,?,?,NULL,1)',
                                     tuple(p[k] for k in ('url','source_id','title','body','content_sha256','fetched_at'))).lastrowid
                target.execute('INSERT INTO page_fts(rowid,title,body) VALUES(?,?,?)',(rowid,p['title'],p['body']))
                included.append({'url':p['url'],'source_id':p['source_id'],'title':p['title'],'original_fetched_at':p['fetched_at']})
    with closing(ro(clone)) as combined:
        if combined.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise Hold('combined_db_integrity_failure')
        n=combined.execute('SELECT COUNT(*) FROM pages WHERE indexed=1').fetchone()[0]
        f=combined.execute('SELECT COUNT(*) FROM page_fts').fetchone()[0]
        src=combined.execute('SELECT COUNT(DISTINCT source_id) FROM pages WHERE indexed=1').fetchone()[0]
        cand=combined.execute('SELECT COUNT(*) FROM sitemap_candidates').fetchone()[0]
        if n!=f or n!=4+len(included) or cand!=112 or src<2:raise Hold('combined_index_invariant_failure')
    if len([x for x in skipped if x['origin']=='https://www.london.gov.uk'])!=1:
        raise Hold('missing_expected_city_hall_policy_conflict')
    questions=build_evidence(clone,meta,ratings)
    for p,h in sources_hash.items():
        if p16.sha256(p)!=h:raise Hold('accepted_owner_source_changed_during_merge')
    result={'version':VERSION,'status':'CROSS_SOURCE_INTERNAL_RESEARCH_INDEX_NOT_PRODUCTION',
            'combined_index':{'indexed_pages':n,'sources':src,'fts_rows':f,'sitemap_leads_retained':cand},
            'source_db_sha256_unchanged':sources_hash,'new_pages_imported':included,
            'skipped_origin_policy_conflicts':skipped,'skipped_duplicate_content':dups,
            'questions':questions,'query_count':len(questions),
            'known_direct_answer_top1':sum(q['top1_known_direct_answer'] for q in questions),
            'new_top1_require_human_review':sum(q['new_top1_needs_review'] for q in questions),
            'no_indexed_match_questions':sum(not q['results'] for q in questions),
            'network_requests':0,'paid_search_provider_calls':0,'owner_database_writes':0,
            'limitations':['Metadata-only internal research; public/subscriber display rights not granted',
                 'Four preselected City Hall pages and small human-reviewed R2-P12 corpus',
                 'Conflicting City Hall /media-centre scope not automatically combined',
                 'Previously graded links may move rank; new rank positions need fresh human grading']}
    (o/'combined_report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (o/'search_review.html').write_text(render(result),encoding='utf-8')
    return result


def main(argv=None):
    p=argparse.ArgumentParser()
    for x in ('p16-db','p12-db','p12-report','review','out'):p.add_argument('--'+x,required=True)
    args=p.parse_args(argv)
    try:
        report=execute(args.p16_db,args.p12_db,args.p12_report,args.review,args.out)
        print(json.dumps({'status':report['status'],'indexed_pages':report['combined_index']['indexed_pages'],
            'indexed_sources':report['combined_index']['sources'],'imported_pages':len(report['new_pages_imported']),
            'conflicting_origin_scopes_skipped':len(report['skipped_origin_policy_conflicts']),
            'questions':report['query_count'],'previously_graded_direct_top1':report['known_direct_answer_top1'],
            'ungraded_top1_for_review':report['new_top1_require_human_review'],
            'no_match_queries':report['no_indexed_match_questions'],
            'paid_search_provider_calls':0,'network_requests':0,'report':str(Path(args.out)/'combined_report.json'),
            'review_html':str(Path(args.out)/'search_review.html')},indent=2))
        return 0
    except (Hold,eng.Hold,OSError,KeyError,ValueError,sqlite3.Error,TypeError) as exc:
        print('HOLD: '+str(exc),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
