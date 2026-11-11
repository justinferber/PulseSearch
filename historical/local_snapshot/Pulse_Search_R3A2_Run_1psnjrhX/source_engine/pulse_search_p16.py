#!/usr/bin/env python3
"""R2-P16 — Independent candidate-to-page promotion in a disposable database copy.

All URLs must already be in a previously accepted, source-scoped sitemap catalog.
Only an operator-controlled live flag permits network page fetching. No paid search.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import html
import json
import re
from urllib.parse import urlsplit, unquote
from pathlib import Path
import sqlite3

import pulse_search_engine as engine
import pulse_search_p15 as p15
import pulse_search_p11 as shadow

VERSION = '0.16.0-r2p16-reviewed-multipage-index'
MAX_URLS = 3
QUESTIONS = [
    "What events are happening in London for New Year's Eve 2026?",
    'London Games Festival 2026',
    'Diwali in London 2026',
    'City Hall Open House London 2026',
    'How do I renew my UK adult passport online?',
    "London New Year's Eve 2027",
]

class Hold(ValueError):
    pass


def sha256(path):
    h = hashlib.sha256()
    with open(path,'rb') as fp:
        for part in iter(lambda:fp.read(1<<20),b''):h.update(part)
    return h.hexdigest()


def validate_plan(db, source_id, source_config, url_manifest):
    """Strict source/candidate binding; absolutely no live network access."""
    approved, src = p15.read_candidates(db,source_id)
    known = {x['url'] for x in approved}
    config=json.loads(Path(source_config).read_text(encoding='utf-8'))
    if not isinstance(config,list) or len(config)!=1:
        raise Hold('exactly_one_source_required')
    engine.validate_sources(config)
    sc=config[0]
    if sc['source_id']!=src['source_id'] or engine.origin(sc['origin'])!=src['origin']:
        raise Hold('source_identity_mismatch')
    if sc['allowed_paths']!=src['approved_scope_paths'] or sc['display_mode']!=src['display_mode'] or sc['rights_basis']!=src['rights_basis']:
        raise Hold('source_policy_mismatch')
    if sc['display_mode']!='metadata_only':
        raise Hold('only_internal_metadata_research')
    manifest=json.loads(Path(url_manifest).read_text(encoding='utf-8'))
    if set(manifest) != {'source_id','urls','purpose'} or manifest['source_id']!=source_id:
        raise Hold('invalid_promotion_manifest')
    urls=manifest['urls']
    if not isinstance(urls,list) or not 1<=len(urls)<=MAX_URLS or len(set(urls))!=len(urls):
        raise Hold('invalid_url_count')
    for url in urls:
        if not isinstance(url,str) or url not in known:
            raise Hold('url_not_in_accepted_sitemap_catalog')
        if engine.normal_url(url)!=url or not engine.scope(url,{'origin':src['origin'],'paths':json.dumps(src['approved_scope_paths'])}):
            raise Hold('url_outside_scope')
        if engine.urlsplit(url).query:
            raise Hold('unreviewed_query_url')
    if not isinstance(manifest['purpose'],str) or not manifest['purpose'].startswith('Internal research'):
        raise Hold('non_research_purpose')
    return {'source':src,'staged_candidates':len(known),'approved_new_urls':urls,
            'plan_status':'SOURCE_BOUND_CANDIDATES_NOT_YET_FETCHED',
            'rights_mode':'internal_metadata_research_only','paid_search_provider_calls':0}


def copy_db_readonly(source,destination):
    src=Path(source).resolve(strict=True)
    dest=Path(destination)
    if dest.exists() or src==dest.resolve():raise Hold('output_exists_or_same_as_source')
    dest.parent.mkdir(parents=True,exist_ok=True)
    before=sha256(src)
    try:
        with closing(sqlite3.connect(src.as_uri()+'?mode=ro',uri=True,timeout=6)) as a:
            a.execute('PRAGMA query_only=ON')
            with closing(sqlite3.connect(str(dest),timeout=6)) as b:
                a.backup(b)
        if sha256(src)!=before:raise Hold('accepted_owner_database_changed_during_copy')
        # Independent equivalent copy; no need to compare sqlite file byte layout.
        with closing(sqlite3.connect(dest)) as c:
            r=c.execute('PRAGMA quick_check').fetchone()[0]
            if r!='ok':raise Hold('invalid_copy')
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return before


def indexed_snapshot(db):
    with closing(p15.sqlite3.connect(Path(db).resolve().as_uri()+'?mode=ro',uri=True)) as c:
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA query_only=ON')
        return [dict(r) for r in c.execute('''SELECT url,title,source_id,fetched_at FROM pages
                                             WHERE indexed=1 ORDER BY url''')]


def year_compatible(query,hit):
    """Exclude a page explicitly identifying a different year from an exact-year query.

    A yearless page is not automatically an answer; it remains unverified.
    """
    requested=set(re.findall(r'(?<![0-9])20[0-4][0-9](?![0-9])',query))
    if not requested:return True
    identified=set(re.findall(r'(?<![0-9])20[0-4][0-9](?![0-9])',
         hit['title']+' '+unquote(urlsplit(hit['url']).path)))
    return not identified or bool(requested & identified)


def search_snapshots(db):
    # Provenance-grounded experiment. A hit is NOT a human-verified answer.
    out=[]
    for q in QUESTIONS:
        payload=shadow.search_payload(db,q,limit=5)
        hits=[x for x in payload['results'] if year_compatible(q,x)]
        out.append({'query':q,'results':hits,
            'coverage_status':'MATCHES_FOUND_NOT_VERIFIED_ANSWERS' if hits else 'NO_INDEXED_MATCH',
            'wrong_year_matches_suppressed':len(payload['results'])-len(hits)})
    return out


def execute(db,source_id,source_config,url_manifest,out_dir,*,allow_live=False):
    dest=Path(out_dir).resolve()
    if dest.exists():raise Hold('report_dir_already_exists')
    plan=validate_plan(db,source_id,source_config,url_manifest)
    dest.mkdir(parents=True)
    try:
        clone=dest/'independent_research_clone.sqlite'
        original_hash=copy_db_readonly(db,clone)
        before=indexed_snapshot(clone)
        result={'version':VERSION,'status':'PREPARED_NOT_LIVE','plan':plan,
                'original_db_sha256_before_after':original_hash,'owner_db_write_count':0,
                'baseline_indexed_pages':len(before),'baseline_indexed_urls':[x['url'] for x in before],
                'clone_database':str(clone),'network_requests':0,'paid_search_provider_calls':0}
        if allow_live:
            # Three previously discovered, exact reviewed URLs only; no sitemap request,
            # no link-depth follow, no automatic source expansion.
            crawl=engine.crawl(str(clone),str(source_config),plan['approved_new_urls'],
                               max_pages=len(plan['approved_new_urls']),max_depth=0,
                               min_delay=2.0,sitemaps=False)
            result['crawl']=crawl
            result['network_requests']=crawl['fetch_requests']
        after=indexed_snapshot(clone)
        baseline_urls={x['url'] for x in before}
        result['indexed_pages_after']=len(after)
        result['new_indexed_pages']=[{'url':x['url'],'title':x['title']} for x in after if x['url'] not in baseline_urls]
        result['promoted_urls_indexed']=[x['url'] for x in after if x['url'] in plan['approved_new_urls']]
        result['search_evidence']=search_snapshots(clone)
        if sha256(db)!=original_hash:raise Hold('accepted_owner_database_changed')
        result['status']=('MULTIPAGE_COPY_INDEXED_INTERNAL_NOT_PRODUCTION' if result['new_indexed_pages']
                          else 'LIVE_NO_NEW_INDEXED_PAGES_HOLD' if allow_live else 'READ_ONLY_PREPARED_FOR_OPTIONAL_LIVE')
        (dest/'promotion_report.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        (dest/'search_review.html').write_text(html_report(result),encoding='utf-8')
        return result
    except BaseException:
        # Failed runs retain their independent audit folder; never touch owner DB.
        raise


def html_report(report):
    lines=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Pulse Search R2-P16 research index</title>',
           '<style>body{max-width:1080px;margin:2rem auto;padding:1rem;font:16px system-ui;line-height:1.6}section{padding:1rem;margin:1rem 0;border:1px solid #bbb;border-radius:12px}small{color:#555}li{overflow-wrap:anywhere}</style>',
           '<h1>Pulse Search — Independent Multi-page Research Index</h1>',
           '<p>Research only: indexed result is not a human-verified answer. No commercial snippet rights or production release approved.</p>',
           '<p>Report status: '+html.escape(report['status'])+' | Total indexed pages: '+str(report['indexed_pages_after'])+'</p>']
    for x in report['search_evidence']:
        lines.append('<section><h2>'+html.escape(x['query'])+'</h2><small>'+html.escape(x['coverage_status'])+'</small>')
        if x['results']:
            lines.append('<ol>')
            for h in x['results']:
                lines.append('<li><strong>'+html.escape(h['title'])+'</strong> &mdash; <a href="'+html.escape(h['url'],quote=True)+'" rel="noopener noreferrer">'+html.escape(h['url'])+'</a> <small>index match, ungraded</small></li>')
            lines.append('</ol>')
        else:lines.append('<p>No indexed match. Not evidence that no page exists on the internet.</p>')
        lines.append('</section>')
    return '\n'.join(lines)+'</html>\n'


def main(argv=None):
    p=argparse.ArgumentParser(description='R2-P16 separate-db metadata-only candidate promotion')
    p.add_argument('--db',required=True);p.add_argument('--sources',required=True)
    p.add_argument('--manifest',required=True);p.add_argument('--source-id',default='london_events_p14')
    p.add_argument('--out',required=True);p.add_argument('--live',action='store_true')
    args=p.parse_args(argv)
    try:
        r=execute(args.db,args.source_id,args.sources,args.manifest,args.out,allow_live=args.live)
        print(json.dumps({'status':r['status'],'staged_candidates':r['plan']['staged_candidates'],
             'baseline_indexed_pages':r['baseline_indexed_pages'],'indexed_pages_after':r['indexed_pages_after'],
             'new_indexed_pages':len(r['new_indexed_pages']),'new_page_titles':r['new_indexed_pages'],
             'network_requests':r['network_requests'],'paid_search_provider_calls':0,
             'report':str(Path(args.out)/'promotion_report.json'),
             'review_html':str(Path(args.out)/'search_review.html')},indent=2))
        return 0 if not args.live or r['new_indexed_pages'] else 2
    except (Hold,p15.Hold,engine.Hold,sqlite3.Error,OSError,ValueError) as exc:
        print('HOLD: '+str(exc),file=__import__('sys').stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
