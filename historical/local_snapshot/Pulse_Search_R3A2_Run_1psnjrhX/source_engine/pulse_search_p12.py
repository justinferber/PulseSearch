#!/usr/bin/env python3
"""Pulse Search R2-P12: standalone, reviewed-seed search coverage benchmark.

Internal/metadata-only pilot, no paid search or third-party search provider, no
writes to any prior Pulse Search DB and no claims about answer correctness.
"""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import sqlite3
import sys

import pulse_search_engine as e
import pulse_search_p10 as p10
import pulse_search_p11 as p11
import pulse_search_real_questions as r9

ROOT=Path(__file__).resolve().parent
SOURCE_FILE=ROOT/'examples/pilot_sources.json'
SEED_FILE=ROOT/'examples/pilot_seeds.json'
QUESTION_FILE=ROOT/'examples/questions.json'
VERSION='r2p12-standalone-coverage-pilot'
MAX_PAGES=11
MAX_RESULTS=3

class PilotHold(Exception): pass

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def hash_bytes(data):return hashlib.sha256(data).hexdigest()

def dump(value):return json.dumps(value,indent=2,ensure_ascii=False)+'\n'

def validate_plan(sources=None,seeds=None,questions=None):
    sources=read_json(SOURCE_FILE) if sources is None else sources
    seeds=read_json(SEED_FILE) if seeds is None else seeds
    questions=read_json(QUESTION_FILE) if questions is None else questions
    if not isinstance(sources,list) or len(sources)!=7:raise PilotHold('must_have_seven_reviewed_sources')
    rows=e.validate_sources(sources)
    source_map={r[0]:{'origin':r[1],'paths':r[2],'source_id':r[0]} for r in rows}
    expected_hosts={'www.london.gov.uk','www.gov.uk','www.nhs.uk','developer.mozilla.org',
                    'www.sqlite.org','docs.python.org','www.rfc-editor.org'}
    from urllib.parse import urlsplit
    if {urlsplit(s['origin']).hostname for s in source_map.values()}!=expected_hosts:
        raise PilotHold('new_origin_requires_explicit_new_review')
    if not isinstance(seeds,list) or len(seeds)!=MAX_PAGES or len(set(seeds))!=len(seeds):
        raise PilotHold('seed_list_must_be_exactly_eleven_unique_pages')
    for seed in seeds:
        if sum(e.scope(seed,s) for s in source_map.values()) != 1:raise PilotHold('unreviewed_seed:'+str(seed)[:120])
        if len(seed)>500:raise PilotHold('seed_too_long')
    if not isinstance(questions,list) or len(questions)!=15:raise PilotHold('question_count')
    ids=[x.get('id') for x in questions]
    if ids!=[f'q{i:02}' for i in range(1,16)]:raise PilotHold('question_id_or_order_changed')
    if len(set(x['q'] for x in questions))!=15:raise PilotHold('duplicate_questions')
    if any(not isinstance(q['q'],str) or not 10 <= len(q['q']) <= 200
           or q.get('cohort') not in ('known','heldout','negative','coverage_gap')
           or not q.get('expected_answer') for q in questions):raise PilotHold('bad_question_fields')
    if [q['id'] for q in questions if q['cohort']=='heldout']!=['q10','q11','q12','q13']:
        raise PilotHold('heldout_question_ids_changed')
    if [q['id'] for q in questions if q['cohort']=='negative']!=['q09','q14','q15']:
        raise PilotHold('negative_question_ids_changed')
    if any(s.get('display_mode')!='metadata_only' or s.get('collection_approved') is not True for s in sources):
        raise PilotHold('metadata_only_research_required')
    return sources,seeds,questions

def review_template(report):
    # This HTML intentionally does not turn link accessibility into answer correctness.
    css='''body{font:15px system-ui,-apple-system,sans-serif;line-height:1.5;max-width:980px;margin:auto;padding:25px;color:#1c2736;background:#fafbfc}header,section{background:white;border:1px solid #dce2e8;border-radius:12px;padding:20px;margin:12px 0 22px}h2{position:sticky;top:0;background:white;padding:12px 0;border-bottom:1px solid #e3e3e3;font-size:22px}article{margin:16px 0;border-bottom:1px solid #ddd;padding-bottom:15px}a{overflow-wrap:anywhere}label{display:block;margin:8px 0 4px}select{padding:9px;width:min(450px,100%)}.hint{color:#54647a}.summary{border-left:4px solid #286eb0;padding-left:12px}.query{background:#f1f6fb;padding:10px 12px}.actions{position:sticky;bottom:10px;background:#103859;color:white;padding:15px;border-radius:10px}button{background:#e2f1fc;color:#13395e;border:0;padding:11px 18px;border-radius:8px;cursor:pointer}.none{font-weight:bold;color:#a13a29}'''
    h=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pulse Search R2-P12: real questions</title><style>'+css+'</style>',
       '<header><h1>Pulse Search — 15 real-world questions</h1><p>This is a research index of explicitly reviewed pages, not the full internet. Grade <strong>answer usefulness</strong>, not whether the link opens. If the page does not answer the query, choose “No” even if its URL is valid. Ratings are not prefilled.</p><p class="hint">All results were returned by Pulse Search from its own index. No paid search provider supplied results.</p></header>']
    esc=lambda x:html.escape(str(x),quote=True)
    for q in report['questions']:
        h.append(f'<section class="question" data-id="{esc(q["id"])}"><h2>Search query: {esc(q["q"])}</h2><p class="summary"><strong>What the user needs:</strong> {esc(q["expected_answer"])}</p>')
        hits=q['results']
        if not hits:h.append('<p class="none">NO INDEXED MATCH — not evidence that the answer is absent from the internet.</p>')
        for hit in hits:
            url=esc(hit['url']);title=esc(hit['title'])
            h.append(f'<article class="hit" data-url="{url}" data-position="{hit["position"]}"><p class="query">Question: {esc(q["q"])}</p><strong>#{hit["position"]} {title}</strong><p><a href="{url}" rel="noopener noreferrer" target="_blank">{url}</a></p><p class="hint">Source {esc(hit["source_id"])}</p><label>Relevance to this query</label><select class="grade"><option value="">Choose a grade</option><option value="0">0 — Not relevant</option><option value="1">1 — Related topic, not an answer</option><option value="2">2 — Useful, but incomplete</option><option value="3">3 — Directly answers the question</option></select><label>Does this page actually answer the question?</label><select class="answer"><option value="">Select one</option><option value="no">No</option><option value="partly">Partially</option><option value="yes">Yes</option></select></article>')
        h.append('</section>')
    script='''const bind=__BIND__;function save(){let missing=0;const questions=[];document.querySelectorAll('.question').forEach(sec=>{const judgements=[];sec.querySelectorAll('.hit').forEach(node=>{const g=node.querySelector('.grade').value;const a=node.querySelector('.answer').value;if(g===''||a==='')missing++;judgements.push({url:node.dataset.url,position:Number(node.dataset.position),grade:g===''?null:Number(g),answer:a||null});});questions.push({id:sec.dataset.id,judgements});});const obj={version:'r2p12-human-review',results_sha256:bind,questions};const blob=new Blob([JSON.stringify(obj,null,2)+'\\n'],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='Pulse_Search_R2P12_Reviewed.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);document.getElementById('save-status').textContent=missing?`Draft exported (${missing} unjudged results). Complete the remaining ratings before scoring.`:'All ratings exported. Keep the search index unchanged for scoring.';}'''.replace('__BIND__',json.dumps(report['results_sha256']))
    h.append('<div class="actions"><button onclick="save()">Save reviewed results JSON</button> <span id="save-status">Please rate each returned page against its query.</span></div><script>'+script+'</script></html>')
    return '\n'.join(h)

def quality(db):
    with closing(p10.read_only_db(db)) as c:
        integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
        pages=c.execute('SELECT COUNT(*) FROM pages WHERE indexed=1').fetchone()[0]
        fts=c.execute('SELECT COUNT(*) FROM page_fts').fetchone()[0]
        sites=c.execute('SELECT COUNT(DISTINCT source_id) FROM pages WHERE indexed=1').fetchone()[0]
        if integrity!='ok' or fts!=pages:raise PilotHold('index_integrity_failed')
    return {'integrity':integrity,'indexed_pages':pages,'fts_pages':fts,'sources_with_pages':sites}

def build_report(db,questions):
    data=[]
    for q in questions:
        p=p11.search_payload(db,q['q'],limit=MAX_RESULTS)
        hits=[{k:hit[k] for k in ('position','url','title','source_id','fetched_at')} for hit in p['results']]
        data.append({**q,'results':hits,'coverage_status':p['coverage_status']})
    core={'version':VERSION,'index_fingerprint':r9.page_fingerprint(db),
          'generated_utc':datetime.now(timezone.utc).isoformat(), 'questions':data,
          'limitations':['Preselected known pages, not a random web sample',
               'Human review pending; a returned URL does not prove an answer',
               'No indexed match does not imply live internet information is absent',
               'No commercial subscriber use authorised by this test']}
    core['results_sha256']=r9.digest({k:v for k,v in core.items() if k!='results_sha256'})
    return core

def run(output_dir):
    sources,seeds,questions=validate_plan()
    out=Path(output_dir).resolve()
    if out.exists():raise PilotHold('refuse_existing_output_directory')
    out.parent.mkdir(parents=True,exist_ok=True)
    out.mkdir(mode=0o700)
    db=out/'index.sqlite'
    try:
        e.initdb(db)
        crawl=e.crawl(db,str(SOURCE_FILE),seeds,max_pages=MAX_PAGES,max_depth=0,min_delay=2.0,sitemaps=False)
        index_health=quality(db)
        report=build_report(db,questions)
        (out/'crawl_report.json').write_text(dump(crawl),encoding='utf-8')
        (out/'quality_report.json').write_text(dump(index_health),encoding='utf-8')
        (out/'query_results.json').write_text(dump(report),encoding='utf-8')
        (out/'review.html').write_text(review_template(report),encoding='utf-8')
        summary={'status':'LIVE_RESEARCH_INDEX_BUILT_REVIEW_PENDING',
                 'indexed_pages':index_health['indexed_pages'],
                 'sources_with_pages':index_health['sources_with_pages'],
                 'question_count':len(questions),
                 'no_match_questions':[q['id'] for q in report['questions'] if not q['results']],
                 'crawler':crawl,'paid_external_search_api_calls':0,'output':str(out)}
        (out/'summary.json').write_text(dump(summary),encoding='utf-8')
        return summary
    except Exception:
        # Failed artefacts deliberately retained for diagnosis, never silently counted as PASS.
        raise

def score(candidate_path,review_path,db_path):
    original=read_json(candidate_path); human=read_json(review_path)
    if original.get('results_sha256')!=r9.digest({k:v for k,v in original.items() if k!='results_sha256'}):
        raise PilotHold('candidate_hash_invalid')
    if r9.page_fingerprint(db_path)!=original['index_fingerprint']:
        raise PilotHold('index_changed_since_review')
    if human.get('version')!='r2p12-human-review' or human.get('results_sha256')!=original['results_sha256']:
        raise PilotHold('review_binding_mismatch')
    qs=original['questions']; hs=human.get('questions',[])
    if [x['id'] for x in qs]!=[x.get('id') for x in hs]:raise PilotHold('review_question_order_mismatch')
    completed=[]
    for q,h in zip(qs,hs):
        if len(q['results'])!=len(h.get('judgements',[])):raise PilotHold('review_hit_count_mismatch')
        grades=[]
        for a,b in zip(q['results'],h['judgements']):
            if a['url']!=b.get('url') or a['position']!=b.get('position'):raise PilotHold('review_result_tampered')
            g=b.get('grade'); ans=b.get('answer')
            if type(g)!=int or g not in range(4) or ans not in ('yes','partly','no'):
                raise PilotHold('incomplete_review')
            if (g<=1 and ans=='yes') or (g==0 and ans=='partly'):
                raise PilotHold('contradictory_grade_and_answer')
            grades.append((g,ans))
        completed.append({'id':q['id'],'query':q['q'],'cohort':q['cohort'],'results':len(grades),
                 'top1_useful':bool(grades and grades[0][0]>=2),
                 'top1_directly_answers':bool(grades and grades[0][1]=='yes'),
                 'useful_in_top3':any(g>=2 for g,ans in grades),
                 'irrelevant_top3':sum(g==0 for g,ans in grades),
                 'no_indexed_match':not bool(grades)})
    if not completed:raise PilotHold('empty_questions')
    return {'status':'HUMAN_GRADED_LIMITED_CORPUS','measured_questions':len(completed),
         'top1_direct_answers':sum(q['top1_directly_answers'] for q in completed),
         'top1_useful':sum(q['top1_useful'] for q in completed),
         'no_indexed_match':sum(q['no_indexed_match'] for q in completed),
         'irrelevant_results_top3':sum(q['irrelevant_top3'] for q in completed),
         'per_question':completed,
         'caution':'Only eleven preselected source pages; do not generalise to open-web search quality'}

def main(argv=None):
    p=argparse.ArgumentParser()
    commands=p.add_subparsers(dest='command',required=True)
    commands.add_parser('validate')
    live=commands.add_parser('live');live.add_argument('--output',required=True);live.add_argument('--acknowledge',action='store_true')
    s=commands.add_parser('score');s.add_argument('--candidate',required=True);s.add_argument('--review',required=True);s.add_argument('--db',required=True);s.add_argument('--output',required=True)
    args=p.parse_args(argv)
    try:
        if args.command=='validate':
            sources,seeds,questions=validate_plan()
            result={'status':'REVIEWED_PLAN_VALID','sources':len(sources),'seeds':len(seeds),'queries':len(questions),'paid_search_calls':0}
        elif args.command=='live':
            if not args.acknowledge:raise PilotHold('explicit_live_approval_required')
            result=run(args.output)
            if result['indexed_pages']<5 or result['sources_with_pages']<3:
                print(dump(result));print('HOLD: minimum research coverage not achieved; see crawl_report.json');return 2
        else:
            result=score(args.candidate,args.review,args.db)
            dest=Path(args.output)
            if dest.exists():raise PilotHold('refuse_output_overwrite')
            dest.write_text(dump(result),encoding='utf-8')
        print(dump(result))
        return 0
    except (PilotHold,e.Hold,OSError,sqlite3.Error,ValueError,KeyError,TypeError) as exc:
        print('HOLD: '+str(exc),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
