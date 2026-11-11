#!/usr/bin/env python3
"""Compare research hybrid vs real BGE on owner 120 pages; offline & no factual claims.
No source page text is exported. Owner index only read by SQLite read-only URI.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, html, json, os, sys, sqlite3
from pathlib import Path
from contextlib import closing
from r3a2_extra_cases import CASES as EXTRA
from r3a_cases import CASES as ORIGINAL
from r3a_eval import check_output
from hybrid_core import HybridIndex
from semantic_ranker import DenseConstrainedIndex
from r3a_local_model import PinnedSentenceEncoder

DB_SHA='bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d'

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

def verify_owner_report(path):
 x=json.loads(Path(path).read_text('utf-8'))
 if x.get('status')!='READ_ONLY_ARCHITECTURE_GATE_DIAGNOSTIC_NOT_DEPLOYED' or x.get('case_count')!=30 or x.get('failures')!=8 or x.get('verified_factual_answers')!=0 or x.get('owner_index_writes')!=0:
  raise ValueError('HOLD_EXPECTED_R3A1_OWNER_REPORT_NOT_CONFIRMED')
 if x.get('owner_index_sha256')!=DB_SHA:raise ValueError('HOLD_OWNER_REPORT_INDEX_MISMATCH')
 return sha(path)

def eval_one(query,kind,expected,ranker):
 result=ranker.search(query,limit=10)
 returned=result['results']
 verdict,note=check_output(kind,expected,returned)
 if kind=='fact_unverified':
  if result['status'] not in ('SOURCE_LINK_ONLY_FACT_UNVERIFIED','WITHHELD_NO_GROUNDED_INDEX_RESULT','WITHHELD_REQUIRES_LIVE_SOURCE'):
   verdict='FAIL_FACT_STATUS'
 # A model cannot certify facts; a source link is not an answer.
 return {'verdict':verdict,'status':result['status'],'count':len(returned),'links':[
  {'url':r['url'],'title':r['title']} for r in returned[:5]]}

def main(a):
 os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_DATASETS_OFFLINE='1',
                   HF_HUB_DISABLE_TELEMETRY='1',HF_HUB_DISABLE_XET='1',PIP_NO_INDEX='1')
 if sha(a.index)!=DB_SHA:raise ValueError('HOLD_OWNER_INDEX_SHA_MISMATCH')
 report_digest=verify_owner_report(a.owner_r3a1_report)
 if Path(a.out).exists():raise ValueError('HOLD_OUTPUT_ALREADY_EXISTS')
 with closing(sqlite3.connect(Path(a.index).resolve().as_uri()+'?mode=ro',uri=True)) as db:
  db.row_factory=sqlite3.Row
  db.execute('PRAGMA query_only=ON')
  if db.execute('PRAGMA query_only').fetchone()[0]!=1:raise ValueError('HOLD_READONLY_NOT_ENABLED')
  counts=(db.execute('select count(*) from pages where indexed=1').fetchone()[0],
          db.execute('select count(*) from page_fts').fetchone()[0],
          db.execute('select count(distinct p.source_id) from pages p join sources s using(source_id) where p.indexed=1 and s.approved=1 and s.enabled=1').fetchone()[0])
  if counts!=(120,120,7):raise ValueError('HOLD_UNAPPROVED_INDEX_STATE')
  rows=[dict(r) for r in db.execute('''select p.url,p.title,p.body,p.fetched_at,p.source_id,s.display_mode
       from pages p join sources s using(source_id) where p.indexed=1 and s.approved=1 and s.enabled=1 order by p.url''')]
 if sha(a.index)!=DB_SHA:raise ValueError('HOLD_OWNER_INDEX_MUTATED')
 baseline=HybridIndex(rows)
 encoder=PinnedSentenceEncoder(a.model_dir)
 dense=DenseConstrainedIndex(rows,encoder)
 probes=[]
 for tag,seq in [('r3a1_original_30',ORIGINAL),('new_24_frozen',EXTRA)]:
  for id,q,kind,expected in seq:
   old=eval_one(q,kind,expected,baseline)
   new=eval_one(q,kind,expected,dense)
   probes.append({'partition':tag,'id':id,'query':q,'kind':kind,
    'baseline':old,'bge_dense':new,'publisher_body_exported':False,'factual_answer_verified':False})
 bypart={}
 for name in ('r3a1_original_30','new_24_frozen'):
  sub=[x for x in probes if x['partition']==name]
  bypart[name]={}
  for rank in ('baseline','bge_dense'):
   bypart[name][rank]=dict(collections.Counter(x[rank]['verdict'] for x in sub))
 valid_new=[x for x in probes if x['kind'] not in ('fact_unverified',)]
 deltas={
  'newly_recovered':[x['id'] for x in valid_new if x['baseline']['verdict'].startswith('FAIL') and not x['bge_dense']['verdict'].startswith('FAIL')],
  'new_regressions':[x['id'] for x in valid_new if not x['baseline']['verdict'].startswith('FAIL') and x['bge_dense']['verdict'].startswith('FAIL')],
 }
 if sha(a.index)!=DB_SHA:raise ValueError('HOLD_INDEX_CHANGED_DURING_EVAL')
 output={'status':'READ_ONLY_TRUE_BGE_COMPARISON_NOT_DEPLOYED','model_id':'BAAI/bge-small-en-v1.5',
  'model_manifest_sha256':encoder.manifest_sha256,'model_verified_files':encoder.verified_file_count,
  'model_kind':'REAL_LOCAL_PINNED_BGE_384D_SENTENCE_EMBEDDINGS',
  'scoring':'hybrid_BM25F_vs_deterministically_constraint_gated_BGE',
  'owner_index_sha256_before_after':DB_SHA,'owner_r3a1_report_sha256':report_digest,
  'question_total':len(probes),'distribution':bypart,'deltas':deltas,
  'human_labels_independent':False,'relevance_confidence_calibrated':False,
  'factual_answers_verified':0,'no_publisher_body_export':True,'network_requests':0,
  'owner_index_writes':0,'production_integration':'HOLD_INDEPENDENT_GRADING_AND_FACT_EVIDENCE',
  'limitations':['Dense scores are not calibrated probabilities','Engineer-authored case set is not an independent human evaluation',
   'Semantic retrieval cannot waive geography, year, exclusions or source rights',
   'No factual answer or up-to-date availability has been validated',
   'No production deployment and no browser/API call'],
  'probes':probes}
 out=Path(a.out);out.mkdir(parents=True)
 (out/'r3a2_bge_comparison_report.json').write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n','utf-8')
 rowshtml=[]
 for x in probes:
  link=x['bge_dense']['links'][0] if x['bge_dense']['links'] else None
  l=('<a href="'+html.escape(link['url'],quote=True)+'">'+html.escape(link['title'])+'</a>') if link else '<i>No indexed result</i>'
  rowshtml.append('<tr><td>'+html.escape(x['id'])+'</td><td>'+html.escape(x['query'])+'</td><td>'+html.escape(x['baseline']['verdict'])+'</td><td>'+html.escape(x['bge_dense']['verdict'])+'</td><td>'+l+'</td></tr>')
 page='''<!doctype html><meta charset="utf-8"><title>Pulse Search R3-A2 true BGE research</title><style>body{font:15px/1.5 system-ui;max-width:1200px;margin:25px auto;padding:0 16px}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:9px;vertical-align:top;text-align:left}a{overflow-wrap:anywhere}</style>'''
 page+='<h1>Pulse Search R3-A2 — actual offline model comparison</h1><p>Research only. Real SHA-pinned BGE sentence embeddings, not deployed; no factual claims or publisher body exported. Independent relevance and confidence calibration remain unapproved.</p>'
 page+='<pre>'+html.escape(json.dumps({'distribution':bypart,'deltas':deltas},indent=2))+'</pre>'
 page+='<table><tr><th>ID</th><th>Question</th><th>Previous hybrid</th><th>Gated BGE</th><th>First candidate</th></tr>'+''.join(rowshtml)+'</table>'
 (out/'r3a2_bge_comparison_review.html').write_text(page,encoding='utf-8')
 with (out/'r3a2_independent_review.csv').open('w',newline='',encoding='utf-8') as f:
  writer=csv.writer(f);writer.writerow(['probe_id','question','model_top_url','baseline_top_url','human_grade_0_to_3','correct_answer_supported_yes_no_unknown','reviewer_name','comments'])
  for x in probes:
   writer.writerow([x['id'],x['query'],x['bge_dense']['links'][0]['url'] if x['bge_dense']['links'] else '',
       x['baseline']['links'][0]['url'] if x['baseline']['links'] else '', '', '', '', ''])
 print(json.dumps({k:output[k] for k in ('status','model_kind','question_total','distribution','deltas','factual_answers_verified','owner_index_writes','production_integration')},indent=2))
 for f in ('r3a2_bge_comparison_report.json','r3a2_bge_comparison_review.html','r3a2_independent_review.csv'):
  print('REPORT='+str(out/f))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--index',required=True);p.add_argument('--owner-r3a1-report',required=True)
 p.add_argument('--model-dir',required=True);p.add_argument('--out',required=True)
 a=p.parse_args()
 try:main(a)
 except Exception as e:
  print('HOLD_R3A2_EVAL:'+type(e).__name__+':'+str(e),file=sys.stderr);raise SystemExit(2)
