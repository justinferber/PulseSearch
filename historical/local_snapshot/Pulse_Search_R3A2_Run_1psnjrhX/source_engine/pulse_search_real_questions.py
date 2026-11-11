#!/usr/bin/env python3
"""Independent Pulse Search real-question benchmark (not a new engine).

Fresh separate pilot index; reviewed source seeds only; no paid provider API.
All relevance judgments are collected from a person, never inferred from URL/title.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import html
import json
from pathlib import Path
import secrets
import sqlite3
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pulse_search_engine as e

VERSION='r2p9-independent-real-questions'
ROOT=Path(__file__).resolve().parent
SOURCES=ROOT/'examples'/'reviewed_sources.json'
SEEDS=ROOT/'examples'/'approved_seeds.json'
QUESTIONS=ROOT/'examples'/'real_world_questions.json'
MAX_SEEDS=8
MAX_RESULTS=3


def canonical_json(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')

def digest(value):return hashlib.sha256(canonical_json(value)).hexdigest()

def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def validate_plan(sources=None,seeds=None,questions=None):
    sources=read_json(SOURCES) if sources is None else sources
    seeds=read_json(SEEDS) if seeds is None else seeds
    questions=read_json(QUESTIONS) if questions is None else questions
    if not isinstance(sources,list) or len(sources)>8 or len(sources)<3:raise e.Hold('invalid_source_set')
    parsed=e.validate_sources(sources)
    scopes=[{'source_id':r[0],'origin':r[1],'paths':r[2]} for r in parsed]
    if not isinstance(seeds,list) or not 1<=len(seeds)<=MAX_SEEDS or len(set(seeds))!=len(seeds):
        raise e.Hold('invalid_seed_budget')
    if len(questions)!=9 or any(not isinstance(x,dict) for x in questions):raise e.Hold('invalid_question_set')
    ids=[x.get('id') for x in questions]
    if len(set(ids))!=len(ids):raise e.Hold('duplicate_question_id')
    for s in sources:
        if s.get('display_mode')!='metadata_only' or s.get('collection_approved') is not True:
            raise e.Hold('source_rights_or_review_missing')
    for u in seeds:
        if sum(e.scope(u,s) for s in scopes)!=1:raise e.Hold('seed_outside_exact_reviewed_scope:'+str(u)[:110])
    known={s['source_id'] for s in sources}
    for q in questions:
        if not isinstance(q.get('q'),str) or not q['q'].strip() or not isinstance(q.get('answer_intent'),str):
            raise e.Hold('invalid_question')
        if any(x not in known for x in q.get('target_sources',[])):
            raise e.Hold('unknown_target_source')
    return sources,seeds,questions


def page_fingerprint(db):
    with e.dbopen(db) as c:
        return digest([dict(r) for r in c.execute('''SELECT url,source_id,title,content_sha256,indexed FROM pages ORDER BY url''')])


def quality(db):
    with e.dbopen(db) as c:
        try:
            integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
            indexed=c.execute('SELECT COUNT(*) FROM pages WHERE indexed=1').fetchone()[0]
            fts=c.execute('SELECT COUNT(*) FROM page_fts').fetchone()[0]
            sources=c.execute('SELECT COUNT(DISTINCT source_id) FROM pages WHERE indexed=1').fetchone()[0]
            c.execute("INSERT INTO page_fts(page_fts) VALUES ('integrity-check')")
            if integrity!='ok' or indexed!=fts:raise e.Hold('index_health_failure')
            return {'integrity':integrity,'pages':indexed,'fts_pages':fts,'covered_sources':sources}
        except sqlite3.DatabaseError as exc:raise e.Hold('index_integrity_error') from exc

@contextmanager
def private_api(db):
    token=secrets.token_urlsafe(36)
    server=ThreadingHTTPServer(('127.0.0.1',0),e.make_handler(db,token))
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try: yield f'http://127.0.0.1:{server.server_address[1]}',token
    finally:server.shutdown();thread.join(timeout=5);server.server_close()

def http_search(base,token,query):
    url=base+'/v1/search?'+urlencode({'q':query,'limit':MAX_RESULTS})
    req=Request(url,headers={'Authorization':'Bearer '+token})
    with urlopen(req,timeout=10) as response:
        if response.status!=200:raise e.Hold('authenticated_api_not_200')
        payload=json.load(response)
    if payload.get('query')!=query or not isinstance(payload.get('results'),list):raise e.Hold('api_bad_response')
    return payload['results']

def run_benchmark(db,output,live=False):
    if not live:raise e.Hold('explicit_live_approval_required')
    sources,seeds,questions=validate_plan()
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    db=Path(db)
    if db.exists():raise e.Hold('refuse_overwrite_database')
    if db.parent.resolve()!=output.resolve():raise e.Hold('database_must_be_in_new_output_dir')
    e.initdb(db)
    report=e.crawl(db,str(SOURCES),seeds,max_pages=MAX_SEEDS,max_depth=0,min_delay=2.0,sitemaps=False)
    integrity=quality(db)
    with private_api(db) as (base,token):
        req=Request(base+'/v1/search?'+urlencode({'q':questions[0]['q']}))
        try:
            urlopen(req,timeout=10)
            raise e.Hold('unauthenticated_api_was_allowed')
        except HTTPError as err:
            if err.code!=401:raise e.Hold('unexpected_auth_response')
            err.close()
        rows=[]
        for q in questions:
            hits=http_search(base,token,q['q'])
            rows.append({**q,'results':[{'url':h['url'],'title':h['title'],'source_id':h['source_id'],
                                         'fetched_at':h['fetched_at'],'position':idx+1} for idx,h in enumerate(hits)]})
    body={'version':VERSION,'questions':rows,'fingerprint':page_fingerprint(db),
          'test_scope':'own independently crawled index; results are NOT independently graded'}
    body['results_sha256']=digest({k:v for k,v in body.items() if k!='results_sha256'})
    (output/'query_results.json').write_text(json.dumps(body,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (output/'crawl_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (output/'review.html').write_text(review_html(body),encoding='utf-8')
    enough=integrity['pages']>=3 and integrity['covered_sources']>=3
    summary={'version':VERSION,'status':'LIVE_FETCH_FINISHED_AWAITING_HUMAN_REVIEW' if enough else 'INSUFFICIENT_LIVE_COVERAGE',
             'crawl':report,'index_health':integrity,'questions':len(questions),
             'questions_with_results':sum(bool(r['results']) for r in rows),
             'no_result_questions':[r['q'] for r in rows if not r['results']],
             'paid_search_api_requests':0,'unauthenticated_api_blocked':True,
             'manual_grading':'PENDING','output':str(output)}
    (output/'session_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return summary


def review_html(body):
    escaped=[]
    for row in body['questions']:
        qid=html.escape(row['id'],quote=True)
        title=html.escape(row['q'])
        criteria=html.escape(row['answer_intent'])
        lines=[f'<section class="question" data-id="{qid}"><div class="query"><span class="category">{html.escape(row["category"])}</span><h2>Search: {title}</h2><p>What a useful result must provide: {criteria}</p></div>']
        if not row['results']:
            lines.append('<p class="empty">No results returned. This is a COVERAGE GAP, not a ranking success. Do not invent ratings.</p>')
        for hit in row['results']:
            url=html.escape(hit['url'],quote=True);h_title=html.escape(hit['title'])
            position=int(hit['position'])
            lines.append(f'<article class="hit" data-position="{position}" data-url="{url}"><p class="repeat">Search: {title}</p><h3>#{position} <a href="{url}" target="_blank" rel="noopener noreferrer">{h_title}</a></h3><p class="url">{url}</p><label>How useful is this page for answering this exact question?<select class="grade"><option value="">Not reviewed</option><option value="0">0 — Does not answer</option><option value="1">1 — Loosely related</option><option value="2">2 — Useful</option><option value="3">3 — Directly answers</option></select></label><label>Did you find the answer on the page?<select class="answered"><option value="">Not checked</option><option value="yes">Yes</option><option value="no">No</option></select></label></article>')
        lines.append('</section>');escaped.append('\n'.join(lines))
    css='''body{font:16px system-ui,sans-serif;line-height:1.5;color:#202b3a;background:#f4f6fa;max-width:980px;margin:0 auto;padding:24px}header,.question{background:white;padding:24px;margin:18px 0;border-radius:14px;border:1px solid #d9e1ed}h1{margin:0}.query{position:sticky;top:0;background:#e8f2ff;border-radius:10px;padding:10px 16px;z-index:2}.query h2{margin:.2em 0}.query p{margin:.3em 0}.category{color:#2357a5;text-transform:uppercase;font-size:12px;font-weight:bold}.hit{border-top:1px solid #ddd;padding:14px 0}.hit h3{margin:4px 0}.url{overflow-wrap:anywhere;color:#53677e;font-size:13px}.repeat{font-size:14px;color:#496e9b;font-weight:bold}select{display:block;padding:8px;width:min(100%,470px);margin:5px 0 14px}a{color:#064e9e}.empty{color:#a33;font-weight:bold}.actions{position:sticky;bottom:0;background:#16385c;padding:14px;border-radius:12px;color:white;display:flex;gap:12px;align-items:center;flex-wrap:wrap}button{padding:10px 20px;border:0;border-radius:7px;background:#dcecff;color:#16385c;font-weight:bold;cursor:pointer}'''
    script='''const sha=__SHA__;const finger=__FINGER__;function save(){const questions=[];let unfinished=0;document.querySelectorAll('.question').forEach(section=>{const judgements=[];section.querySelectorAll('.hit').forEach(hit=>{const g=hit.querySelector('.grade').value;const a=hit.querySelector('.answered').value;if(g===''||a===''){unfinished++;}judgements.push({url:hit.dataset.url,position:Number(hit.dataset.position),grade:g===''?null:Number(g),answered:a===''?null:(a==='yes')});});questions.push({id:section.dataset.id,judgements});});const obj={version:'r2p9-human-review',results_sha256:sha,index_fingerprint:finger,questions};const blob=new Blob([JSON.stringify(obj,null,2)+'\\n'],{type:'application/json'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='Pulse_Search_R2P9_Reviewed.json';link.click();URL.revokeObjectURL(link.href);document.getElementById('status').textContent=unfinished?`Saved draft: ${unfinished} incomplete judgments`:'Saved complete review';}'''.replace('__SHA__',json.dumps(body['results_sha256'])).replace('__FINGER__',json.dumps(body['fingerprint']))
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pulse Search R2-P9 Real Questions Review</title><style>'+css+'</style></head><body><header><h1>Pulse Search — Real Question Review</h1><p>Read the query and required answer above each result. Open the page, judge its usefulness, and record whether the actual answer is present. Grades do not measure whether a link merely opens.</p><p>All results are from our own independently crawled index, not an external search engine.</p></header>'+''.join(escaped)+'<div class="actions"><button onclick="save()">Save review JSON</button><span id="status">Save after reviewing all returned results.</span></div><script>'+script+'</script></body></html>'


def score(candidate,review,db=None):
    orig=read_json(candidate); human=read_json(review)
    if orig.get('results_sha256')!=digest({k:v for k,v in orig.items() if k!='results_sha256'}):
        raise e.Hold('result_collection_content_hash_mismatch')
    if db is not None and page_fingerprint(db)!=orig.get('fingerprint'):
        raise e.Hold('underlying_search_index_changed_since_collection')
    if human.get('results_sha256')!=orig.get('results_sha256') or human.get('index_fingerprint')!=orig.get('fingerprint'):
        raise e.Hold('review_does_not_match_frozen_results')
    expected_ids=[x['id'] for x in orig['questions']]
    observed=human.get('questions')
    if not isinstance(observed,list) or [x.get('id') for x in observed]!=expected_ids:
        raise e.Hold('review_question_set_changed')
    import math
    records=[]
    for q,r in zip(orig['questions'],observed):
        judges=r.get('judgements',[])
        hits=q['results']
        if len(judges)!=len(hits):raise e.Hold('review_result_count_changed')
        out=[]
        for h,j in zip(hits,judges):
            if j.get('url')!=h['url'] or j.get('position')!=h['position']:
                raise e.Hold('review_result_order_changed')
            grade=j.get('grade');answered=j.get('answered')
            if type(grade)!=int or grade not in (0,1,2,3) or type(answered)!=bool:
                raise e.Hold('judgements_incomplete_or_invalid')
            out.append({'grade':grade,'answered':answered,'url':h['url']})
        grades=[x['grade'] for x in out]
        dcg=sum((2**g-1)/math.log2(i+2) for i,g in enumerate(grades))
        ideal=sum((2**g-1)/math.log2(i+2) for i,g in enumerate(sorted(grades,reverse=True)))
        records.append({'query':q['q'],'category':q['category'],'returned':len(out),
                        'p_at_3':sum(x>=2 for x in grades)/len(grades) if grades else None,
                        'answer_found_at_3':any(x['answered'] for x in out),
                        'top1_answered':out[0]['answered'] if out else False,
                        'irrelevant_at_3':sum(x==0 for x in grades),
                        'ndcg_at_3':round(dcg/ideal,4) if ideal else None,
                        'no_results':not bool(out)})
    measurable=[x['ndcg_at_3'] for x in records if x['ndcg_at_3'] is not None]
    return {'version':VERSION,'status':'MEASURED_FROM_HUMAN_REVIEW','queries':len(records),
            'queries_with_answer_in_top3':sum(x['answer_found_at_3'] for x in records),
            'top1_answer_rate':sum(x['top1_answered'] for x in records)/len(records),
            'no_result_queries':sum(x['no_results'] for x in records),
            'irrelevant_results_top3':sum(x['irrelevant_at_3'] for x in records),
            'mean_ndcg_at_3':round(sum(measurable)/len(measurable),4) if measurable else None,
            'caution':'Small reviewed source corpus; rankings and coverage cannot be generalised',
            'per_question':records}


def main(argv=None):
    ap=argparse.ArgumentParser(description='Pulse Search real user questions search benchmark')
    sp=ap.add_subparsers(dest='action',required=True)
    sp.add_parser('validate')
    live=sp.add_parser('live');live.add_argument('--output',required=True);live.add_argument('--acknowledge-real-world-bounded-crawl',action='store_true')
    sc=sp.add_parser('score');sc.add_argument('--candidates',required=True);sc.add_argument('--review',required=True);sc.add_argument('--db',required=True);sc.add_argument('--output',required=True)
    args=ap.parse_args(argv)
    try:
        if args.action=='validate':
            sources,seeds,queries=validate_plan();result={'status':'VALID_PLAN','sources':len(sources),'seeds':len(seeds),'queries':len(queries)}
        elif args.action=='live':
            if not args.acknowledge_real_world_bounded_crawl:raise e.Hold('owner_live_approval_required')
            folder=Path(args.output).resolve()
            if folder.exists():raise e.Hold('output_folder_exists')
            folder.parent.mkdir(parents=True,exist_ok=True)
            result=run_benchmark(folder/'index.sqlite',folder,live=True)
            if result['status']=='INSUFFICIENT_LIVE_COVERAGE':
                print(json.dumps(result,indent=2,ensure_ascii=False))
                print('HOLD: fewer than three indexed pages or approved sources; review crawl_report.json')
                return 2
        else:
            result=score(args.candidates,args.review,db=args.db)
            Path(args.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2,ensure_ascii=False))
    except (e.Hold,ValueError,TypeError,KeyError,sqlite3.Error,OSError) as error:
        print('HOLD: '+str(error));return 2
    return 0

if __name__=='__main__':raise SystemExit(main())
