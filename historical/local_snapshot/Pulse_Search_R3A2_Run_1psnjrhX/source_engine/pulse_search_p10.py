#!/usr/bin/env python3
"""R2-P10 offline relevance/abstention experiment (NO network, NO index writes).

Keeps the R2-P9 engine & original review intact. Filters broad-OR candidates by
meaningful query-term coverage, then compares against unchanged baseline.

No production engine/ranker changes are made by this experiment.
"""
from __future__ import annotations
import argparse, collections, hashlib, html, json, math, re, sqlite3
from pathlib import Path
from urllib.parse import quote
import pulse_search_engine as engine
import pulse_search_real_questions as rq

STOP = frozenset('a an and are as at be by can could did do does for from had has have how i in into is it me my of on or our the their them these this those to was were what when where which who why will with would you your near now happening go'.split())

class GateError(Exception): pass

def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def tokenize(q):
    tokens = re.findall(r'[^\W_]+', q.casefold(), flags=re.UNICODE)
    return list(dict.fromkeys(t for t in tokens if len(t)>=2 and t not in STOP))[:12]

def review_metrics(review):
    qs=review.get('questions',[])
    if len(qs)!=9 or [q.get('id') for q in qs]!=[f'q{i:02d}' for i in range(1,10)]:
        raise GateError('unexpected_question_list')
    grades=collections.Counter(); conflicts=[]; rows=[]
    for q in qs:
        hits=q.get('judgements',[])
        if len(hits)!=3: raise GateError('expected_three_results_per_question')
        if [h.get('position') for h in hits]!=[1,2,3]:raise GateError('position_mismatch')
        g=[]
        for h in hits:
            gr=h.get('grade'); a=h.get('answered')
            if type(gr)!=int or gr not in (0,1,2,3) or type(a)!=bool:raise GateError('missing_or_bad_grade')
            grades[gr]+=1;g.append(gr)
            if gr<=1 and a:conflicts.append({'id':q['id'],'position':h['position'],'url':h['url'],'grade':gr})
        rows.append({'id':q['id'],'grades':g,'top1_useful':g[0]>=2,'any_top3_useful':any(x>=2 for x in g), 'irrelevant_count':g.count(0)})
    return {'queries':len(qs),'graded_results':sum(grades.values()),'grade_counts':{str(g):grades[g] for g in range(4)},
            'useful_top1':sum(row['top1_useful'] for row in rows),
            'useful_top3':sum(row['any_top3_useful'] for row in rows),
            'irrelevant_results':grades[0], 'answer_flag_conflicts':len(conflicts),
            'conflicts':conflicts,'answer_rate_status':'UNRELIABLE_REQUIRES_HUMAN_RECHECK' if conflicts else 'GRADE_CONSISTENT',
            'per_question':rows}

def read_only_db(path):
    # sqlite URI mode=ro avoids writing the owners' index; also reject sqlite writes.
    path=Path(path).resolve(strict=True)
    c=sqlite3.connect('file:'+quote(str(path),safe='/')+'?mode=ro',uri=True,timeout=10)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    return c

def ranked_experiment(conn,query, limit=3):
    terms=tokenize(query)
    if not terms:return []
    match=' OR '.join('"'+t+'"' for t in terms)
    rows=conn.execute('''SELECT p.url,p.title,p.body,p.source_id,p.fetched_at,
      bm25(page_fts,6.0,1.0) AS original_rank
      FROM page_fts JOIN pages p ON p.id=page_fts.rowid
      JOIN sources s ON s.source_id=p.source_id
      WHERE page_fts MATCH ? AND p.indexed=1 AND s.approved=1 AND s.enabled=1
      ORDER BY original_rank ASC, p.url ASC LIMIT 200''',(match,)).fetchall()
    required = max(1, min(3, math.ceil(len(terms)*0.4)))
    if len(terms)>=2: required=max(2,required)
    scored=[]
    for r in rows:
        title_tokens=set(re.findall(r'[^\W_]+',r['title'].casefold(),flags=re.UNICODE))
        body_tokens=set(re.findall(r'[^\W_]+',r['body'].casefold(),flags=re.UNICODE))
        title_hits=sum(t in title_tokens for t in terms)
        body_hits=sum(t in body_tokens for t in terms)
        covered=sum(t in title_tokens or t in body_tokens for t in terms)
        if covered<required:continue
        # conservative, transparent heuristic: exact title tokens > body tokens > FTS score
        ranking=(title_hits*4+covered*2+min(body_hits,12), covered,title_hits,-float(r['original_rank']))
        scored.append((ranking,{'url':r['url'],'title':r['title'],'source_id':r['source_id'],
                                'fetched_at':r['fetched_at'],'term_coverage':f'{covered}/{len(terms)}',
                                'title_terms':title_hits,'original_bm25':round(float(r['original_rank']),6)}))
    scored.sort(key=lambda s:(-s[0][0],-s[0][1],-s[0][2],-s[0][3],s[1]['url']))
    return [r for _,r in scored[:limit]]

def validate_bindings(candidates, review, conn):
    if candidates.get('results_sha256')!=rq.digest({k:v for k,v in candidates.items() if k!='results_sha256'}):
        raise GateError('candidate_collection_hash_mismatch')
    if review.get('results_sha256')!=candidates['results_sha256'] or review.get('index_fingerprint')!=candidates.get('fingerprint'):
        raise GateError('review_binding_mismatch')
    if rq.digest([dict(r) for r in conn.execute('SELECT url,source_id,title,content_sha256,indexed FROM pages ORDER BY url')])!=candidates['fingerprint']:
        raise GateError('owner_index_fingerprint_mismatch')
    a=candidates['questions'];b=review['questions']
    if [q['id'] for q in a]!=[q['id'] for q in b]:raise GateError('questions_not_identical')
    for qa,qb in zip(a,b):
        if [(x['url'],x['position']) for x in qa['results']]!=[(x['url'],x['position']) for x in qb['judgements']]:
            raise GateError('review_candidate_rows_mismatch')

def measure_known(q,old_judgements,candidate_hits):
    prior={h['url']:h['grade'] for h in old_judgements}
    rated=[prior.get(x['url']) for x in candidate_hits]
    if any(g is None for g in rated):return {'status':'REVIEW_REQUIRED','previously_ungraded':sum(g is None for g in rated)}
    return {'status':'ALL_PREVIOUSLY_GRADED','grades':rated,
            'top1_useful':bool(rated and rated[0]>=2),
            'irrelevant_top3':sum(g==0 for g in rated),
            'useful_top3':sum(g>=2 for g in rated)}

def report_html(report):
    body=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Pulse Search R2-P10 offline experiment</title>',
          '<style>body{font:16px system-ui;max-width:1050px;margin:30px auto;line-height:1.5;color:#222;padding:0 18px}section{border:1px solid #ccc;border-radius:12px;padding:18px;margin:20px 0}code{background:#eee;padding:3px}article{padding:8px 0;border-top:1px solid #ddd}small{color:#555}h2{position:sticky;top:0;background:white;padding:10px 0}a{word-wrap:break-word}</style>',
          '<h1>Pulse Search — offline relevance and no-answer experiment</h1>',
          '<p>Read-only ranking experiment. Original search engine and index are unchanged. Experimental results are NOT automatically judged as good.</p>',
          '<p><strong>Human answer flags require rechecking:</strong> previous review marked unrelated pages as answered. Use relevance grades separately.</p>']
    for q in report['questions']:
        body.append('<section><h2>Search: '+html.escape(q['query'])+'</h2>')
        body.append('<p>Baseline returned '+str(len(q['baseline']))+'; experimental ranking returned '+str(len(q['experimental']))+'.</p>')
        for kind,title in [('baseline','Original broad-OR results'),('experimental','Experimental stricter results')]:
            body.append('<h3>'+title+'</h3>')
            if not q[kind]:body.append('<p><em>No matching indexed pages — coverage gap / abstain</em></p>')
            for i,hit in enumerate(q[kind],1):
                url=html.escape(hit['url'],quote=True)
                grade=hit.get('previous_grade')
                body.append('<article><b>#'+str(i)+' '+html.escape(hit['title'])+'</b> <small>Earlier human grade: '+(str(grade) if grade is not None else 'not judged')+'</small><p><a href="'+url+'" rel="noopener noreferrer">'+url+'</a></p></article>')
        body.append('</section>')
    body.append('</html>')
    return '\n'.join(body)

def analyse(args):
    candidate=load_json(args.candidates);review=load_json(args.review)
    with read_only_db(args.db) as conn:
        validate_bindings(candidate,review,conn)
        reviews=review_metrics(review)
        rows=[]
        for qc,jc in zip(candidate['questions'],review['questions']):
            lookup={x['url']:x['grade'] for x in jc['judgements']}
            old=[{'url':x['url'],'title':x['title'],'previous_grade':lookup.get(x['url'])} for x in qc['results']]
            new=[{**x,'previous_grade':lookup.get(x['url'])} for x in ranked_experiment(conn,qc['q'])]
            rows.append({'id':qc['id'],'query':qc['q'],'baseline':old,'experimental':new,
                         'experiment_known_grade_metrics':measure_known(qc,jc['judgements'],new)})
    result={'status':'EXPERIMENT_COMPLETED_NOT_PRODUCTION_APPROVED',
            'strict_binding':'PASS','source':'independent owner R2-P9 index','original_human_review':reviews,
            'questions':rows,'experimental_zero_result_queries':[x['id'] for x in rows if not x['experimental']],
            'original_api_unchanged':True,'external_api_requests':0,
            'caution':'Small preseeded index; candidate URLs outside original top-3 are unjudged and need separate human review.'}
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    (out/'experiment_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'review.html').write_text(report_html(result),encoding='utf-8')
    print(json.dumps({'status':result['status'],'human_grade_top1_useful':reviews['useful_top1'],
            'answered_flag_conflicts':reviews['answer_flag_conflicts'],
            'experiment_zero_result_questions':result['experimental_zero_result_queries'],
            'report':str(out/'experiment_report.json'),'html':str(out/'review.html')},indent=2))

def preliminary(args):
    result=review_metrics(load_json(args.review))
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({'status':'PROVISIONAL_ONLY_NO_OWNER_DB_BINDING',**result},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PROVISIONAL_ONLY_NO_OWNER_DB_BINDING','queries':result['queries'],
                      'useful_top1':result['useful_top1'],'irrelevant_results':result['irrelevant_results'],
                      'answer_flag_conflicts':result['answer_flag_conflicts']}))

def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
    for cmd in ('preliminary','experiment'):
        a=s.add_parser(cmd);a.add_argument('--review',required=True);a.add_argument('--output',required=True)
        if cmd=='experiment':a.add_argument('--db',required=True);a.add_argument('--candidates',required=True)
    args=p.parse_args()
    try:
        if args.command=='preliminary':preliminary(args)
        else:analyse(args)
    except (GateError,engine.Hold,OSError,ValueError,KeyError,sqlite3.Error) as err:
        print('HOLD: '+str(err));raise SystemExit(2)

if __name__=='__main__':main()
