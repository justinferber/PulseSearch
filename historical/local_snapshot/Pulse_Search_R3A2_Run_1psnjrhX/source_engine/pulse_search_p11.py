#!/usr/bin/env python3
"""Pulse Search R2-P11: independent read-only shadow search API and coverage gate.

Compares experimental R2-P10 ranker against human-graded R2-P9 results. Does
not change the original search API; no live crawl, provider calls or indexing.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

import pulse_search_p10 as p10
import pulse_search_real_questions as r9

VERSION = '0.11.0-r2p11-shadow-search'
MAX_QUERY = 256

class ApiInputError(Exception):
    pass


def validate_query(params):
    if set(params) - {'q', 'limit'}:
        raise ApiInputError('unexpected_parameters')
    q = params.get('q', [''])[0]
    if len(params.get('q', [])) != 1 or not isinstance(q, str) or not q.strip() or len(q) > MAX_QUERY:
        raise ApiInputError('invalid_query')
    limits = params.get('limit', ['3'])
    if len(limits) != 1 or not limits[0].isdigit() or not 1 <= int(limits[0]) <= 10:
        raise ApiInputError('invalid_limit')
    return q.strip(), int(limits[0])


def search_payload(db, q, limit=3):
    with closing(p10.read_only_db(db)) as conn:
        results = p10.ranked_experiment(conn,q,limit=limit)
        source_count = conn.execute('SELECT COUNT(DISTINCT source_id) FROM pages WHERE indexed=1').fetchone()[0]
        indexed_pages = conn.execute('SELECT COUNT(*) FROM pages WHERE indexed=1').fetchone()[0]
    return {
        'version': VERSION, 'query': q, 'results': [dict(position=i+1, **result) for i,result in enumerate(results)],
        'coverage_status': 'MATCHES_FOUND_NOT_VERIFIED_ANSWERS' if results else 'NO_INDEXED_MATCH',
        'coverage_scope': {'indexed_pages': indexed_pages, 'sources': source_count},
        'production_approved': False, 'answer_verified': False,
        'disclaimer': 'Results are from Pulse Search own index. A result does not establish a verified answer; no match does not mean the answer is unavailable on the internet.',
        'paid_provider_requests':0,
    }


def make_handler(db, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return
        def reply(self, code, body):
            raw = json.dumps(body,ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            path = urlsplit(self.path)
            if path.path == '/healthz' and not path.query:
                return self.reply(200,{'version':VERSION,'status':'ready','scope':'loopback-readonly-shadow'})
            if path.path != '/v1/experimental/search':
                return self.reply(404,{'error':'not_found'})
            auth = self.headers.get('Authorization','')
            if not hmac.compare_digest(auth,'Bearer '+token):
                return self.reply(401,{'error':'unauthorized'})
            try:
                params=parse_qs(path.query,keep_blank_values=True,strict_parsing=True,max_num_fields=3)
                q,limit=validate_query(params)
            except (ApiInputError,ValueError):
                return self.reply(400,{'error':'invalid_parameters'})
            try:
                payload=search_payload(db,q,limit)
            except Exception:
                return self.reply(503,{'error':'index_unavailable'})
            return self.reply(200,payload)
    return Handler


def compare_real_review(db,candidates,review):
    # The same full cryptographic bindings from R2-P10 are mandatory.
    with closing(p10.read_only_db(db)) as conn:
        p10.validate_bindings(candidates,review,conn)
    questions=[];retained=0;original_useful=0;unjudged=0
    for raw,ratings in zip(candidates['questions'],review['questions']):
        old = ratings['judgements'][0]
        payload=search_payload(db,raw['q'])
        hits=payload['results'];lookup={v['url']:v['grade'] for v in ratings['judgements']}
        new_grade=lookup.get(hits[0]['url']) if hits else None
        if old['grade']>=2:
            original_useful+=1
            if new_grade is not None and new_grade>=2: retained+=1
        if hits and new_grade is None:unjudged+=1
        questions.append({'id':raw['id'],'query':raw['q'],'previous_top_grade':old['grade'],
            'new_top_grade':new_grade, 'experimental_result_count':len(hits),'status':payload['coverage_status'],
            'new_top_url':hits[0]['url'] if hits else None,
            'interpretation':'PARTIAL_MATCH_NEEDS_BETTER_COVERAGE' if raw['id']=='q01' and new_grade==1
                 else 'NO_INDEXED_MATCH_NOT_A_GLOBAL_NEGATIVE' if not hits else 'HUMAN_REVIEW_REQUIRED' if new_grade is None
                 else 'HUMAN_GRADED_USEFUL' if new_grade>=2 else 'HUMAN_GRADED_NOT_USEFUL'})
    return {
       'version': VERSION,'status':'SHADOW_API_REGRESSION_MEASURED_NOT_PRODUCTION_APPROVED',
       'questions':questions,
       'regression':{'previously_useful_top1':original_useful,'retained_useful_top1':retained,
         'retained_all_previous_useful':retained==original_useful,'unjudged_new_top1':unjudged,
         'q09_no_indexed_match':not questions[-1]['new_top_url'],
         'q01_still_partial':questions[0]['new_top_grade']==1},
       'paid_provider_calls':0,
       'limitations':['9 preseeded questions','Source-restricted, very small index','Ranking not yet applied to production Search API','No-match does not imply absence from the live web']
    }


def api_smoke(db):
    token=secrets.token_urlsafe(32)
    srv=ThreadingHTTPServer(('127.0.0.1',0),make_handler(db,token))
    thread=threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base=f'http://127.0.0.1:{srv.server_address[1]}'
    try:
        def req(q, auth):
            headers={'Authorization':'Bearer '+token} if auth else {}
            return urlopen(Request(base+'/v1/experimental/search?'+urlencode({'q':q}), headers=headers), timeout=5)
        try:
            with req('What is HTTP?', False):
                raise AssertionError('auth unexpectedly allowed')
        except HTTPError as exc:
            if exc.code != 401: raise
            exc.close()
        with req('What is HTTP?',True) as response:
            data=json.load(response)
            if response.status!=200 or data['query'] != 'What is HTTP?':raise AssertionError('bad_http_response')
        with req('Which restaurants near me are open now?',True) as response:
            missing=json.load(response)
        return {'http_authorised':200,'http_unauthorised':401,'no_match_status':missing['coverage_status'],
            'no_match_results':len(missing['results']), 'paid_provider_calls':0}
    finally:
        srv.shutdown();thread.join(timeout=3);srv.server_close()


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--db',required=True)
    ap.add_argument('--candidates',required=True)
    ap.add_argument('--review',required=True)
    ap.add_argument('--output',required=True)
    args=ap.parse_args(argv)
    db=Path(args.db).resolve(strict=True)
    before=hashlib.sha256(db.read_bytes()).hexdigest()
    results=compare_real_review(db,p10.load_json(args.candidates),p10.load_json(args.review))
    results['http_smoke']=api_smoke(db)
    if hashlib.sha256(db.read_bytes()).hexdigest()!=before:
        raise SystemExit('HOLD: owner index changed during read-only test')
    out=Path(args.output)
    if out.exists():raise SystemExit('HOLD: output already exists')
    out.mkdir(parents=True)
    (out/'shadow_api_report.json').write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':results['status'],'regression':results['regression'],
         'http_smoke':results['http_smoke'],'report':str(out/'shadow_api_report.json')},indent=2))
    g=results['regression']
    if g['retained_all_previous_useful'] and g['unjudged_new_top1']==0 and g['q09_no_indexed_match'] and g['q01_still_partial']:
       print('SUCCESS: R2-P11 read-only shadow Search API regression PASS; coverage remains limited')
    else: raise SystemExit('HOLD: shadow ranking or coverage acceptance regression')

if __name__=='__main__':
    main()
