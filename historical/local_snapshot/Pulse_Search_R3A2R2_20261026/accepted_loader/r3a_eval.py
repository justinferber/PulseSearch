#!/usr/bin/env python3
"""R3 A1 reproducible link relevance and abstention evaluation. No writes to index.
Uses owner-approved/locally indexed page metadata for URL-level expectations.
An optional manually provisioned, SHA-pinned embedding model is off by default.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, html, json, os, sys, sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
from r3a_cases import CASES

OWNER_SHA='bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d'
R35_REPORT_SHA='ca056b51a7af76d095d9b4b76f0b3b082cdf92209a45e02aa190ee083f2d5fc1'

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

def check_output(kind,expect,returned):
 paths=[urlsplit(r['url']).path for r in returned]
 if kind=='fact_unverified':return ('ABSTAIN_FACT_UNVERIFIED','Factual claim not independently verified; no answer generated')
 if kind=='no_result':return ('PASS_SAFETY' if not returned else 'FAIL_FALSE_POSITIVE','No supported link expected')
 if kind=='top':return ('PASS_RETRIEVAL' if paths and paths[0].endswith(expect) else 'FAIL_WRONG_TOP1','Expected exact page at top')
 if kind=='all':
  needed=expect.split('|')
  missing=[x for x in needed if not any(p.endswith(x) for p in paths)]
  return ('PASS_RETRIEVAL' if not missing else 'FAIL_MISSING_EDITION','Required distinct editions: '+(', '.join(missing) if missing else 'all found'))
 if kind=='exclude_nonempty':
  if not paths:return ('FAIL_EMPTY_DISCOVERY','Other known indexed alternatives must be returned')
  if any(p.endswith(expect) for p in paths):return ('FAIL_EXCLUSION_LEAK','Excluded source appeared in results')
  return ('PASS_RETRIEVAL','Non-excluded alternative returned')
 if kind=='year_many':return ('PASS_RETRIEVAL' if len(paths)>=2 and all(expect in r['title'] and '/events/' in r['url'] for r in returned) else 'FAIL_YEAR_DISCOVERY','At least two matching event editions required')
 if kind=='series_many':return ('PASS_RETRIEVAL' if len(paths)>=2 and all(expect in r['title'].casefold() for r in returned) else 'FAIL_SERIES_RECALL','At least two exact series editions required')
 raise ValueError('UNKNOWN_KIND_'+kind)

def evaluate(index, report, out, model_dir=None):
 from hybrid_core import HybridIndex
 if sha(index)!=OWNER_SHA:raise ValueError('HOLD_OWNER_INDEX_SHA_DRIFT')
 if sha(report)!=R35_REPORT_SHA:raise ValueError('HOLD_ACCEPTED_R2P35_REPORT_SHA_DRIFT')
 audit=json.loads(Path(report).read_text(encoding='utf-8'))
 if audit.get('status')!='READ_ONLY_HYBRID_DIAGNOSTIC_COMPLETE_NOT_DEPLOYED' or len(audit['probes'])!=129:raise ValueError('HOLD_PRIOR_AUDIT_INVALID')
 out=Path(out)
 if out.exists():raise ValueError('HOLD_OUTPUT_EXISTS')
 with closing(sqlite3.connect(Path(index).resolve().as_uri()+'?mode=ro',uri=True)) as db:
  db.row_factory=sqlite3.Row
  db.execute('PRAGMA query_only=ON')
  if db.execute('PRAGMA query_only').fetchone()[0]!=1:raise ValueError('HOLD_NOT_READONLY')
  n=db.execute('SELECT COUNT(*) FROM pages WHERE indexed=1').fetchone()[0]
  f=db.execute('SELECT COUNT(*) FROM page_fts').fetchone()[0]
  s=db.execute('SELECT COUNT(DISTINCT p.source_id) FROM pages p JOIN sources s USING(source_id) WHERE p.indexed=1 AND s.approved=1 AND s.enabled=1').fetchone()[0]
  if (n,f,s)!=(120,120,7):raise ValueError('HOLD_CORPUS_DRIFT')
  data=[dict(x) for x in db.execute('''SELECT p.url,p.title,p.body,p.fetched_at,p.source_id,s.display_mode FROM pages p JOIN sources s USING(source_id) WHERE p.indexed=1 AND s.approved=1 AND s.enabled=1 ORDER BY p.url''')]
  if len(data)!=120:raise ValueError('HOLD_APPROVED_COUNT_DRIFT')
  if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('HOLD_DATABASE_QUICK_CHECK')
 if sha(index)!=OWNER_SHA:raise ValueError('HOLD_OWNER_INDEX_CHANGED')
 ranker=HybridIndex(data)
 model_status='NOT_CONFIGURED_NO_MODEL_EXECUTED'
 if model_dir:
  from r3a_local_model import PinnedSentenceEncoder
  model=PinnedSentenceEncoder(model_dir)
  model_status={'status':'OWNER_PROVIDED_LOCAL_MODEL_ACTIVE', 'model_sha256_manifest':model.manifest_sha256,'approved_files':model.verified_file_count}
  ranker=HybridIndex(data,semantic_model=model)
 rows=[]
 for cid,question,kind,exp in CASES:
  result=ranker.search(question,limit=10)
  returned=result['results']
  verdict,note=check_output(kind,exp,returned)
  if kind=='fact_unverified' and result['status'] not in ('SOURCE_LINK_ONLY_FACT_UNVERIFIED','WITHHELD_NO_GROUNDED_INDEX_RESULT','WITHHELD_REQUIRES_LIVE_SOURCE'):
   verdict='FAIL_FACT_GATE_STATUS'
  if kind=='fact_unverified' and returned and result['status']=='RETRIEVAL_CANDIDATES_UNVERIFIED':verdict='FAIL_FACT_GATE_STATUS'
  rows.append({'id':cid,'question':question,'expected_kind':kind,'verdict':verdict,'diagnostic':note,'candidate_count':len(returned),
    'result_status':result['status'],'top_links':[{'title':r['title'],'url':r['url']} for r in returned[:5]],
    'publisher_body_exported':False,'verified_factual_answer':False})
  if sha(index)!=OWNER_SHA:raise ValueError('HOLD_OWNER_INDEX_CHANGED_DURING_RUN')
 counter=dict(collections.Counter(x['verdict'] for x in rows))
 fail=sum(1 for x in rows if x['verdict'].startswith('FAIL_'))
 fact=sum(x['expected_kind']=='fact_unverified' for x in rows)
 report_data={'version':'PulseSearch-R3A1-Trustworthy-Evaluation-v1','status':'READ_ONLY_ARCHITECTURE_GATE_DIAGNOSTIC_NOT_DEPLOYED',
  'owner_index_sha256':OWNER_SHA, 'accepted_r2p35_report_sha256':R35_REPORT_SHA,
  'corpus':{'pages':n,'fts':f,'approved_sources':s},'model':model_status,
  'case_count':len(rows),'retrieval_or_safety_case_count':len(rows)-fact,'fact_cases_unverified':fact,
  'verified_factual_answers':0,'failures':fail,'distribution':counter,'judgement_provenance':'ENGINEER_AUTHORED_NOT_INDEPENDENT_HUMAN_LABELS',
  'ranker_production_integration':'HOLD', 'source_rights':'METADATA_LINK_ONLY_NO_PUBLISHER_PROSE_EXPORTED',
  'statistical_confidence_calibrated':False,'network_requests':0,'paid_search_calls':0,'owner_index_writes':0,
  'cases':rows,
  'known_limitations':['No licensed dense weights supplied by default','No factual answer is independently verified',
      'Engineer-authored expectations cannot certify production accuracy',
      '120 pages from seven approved sources are insufficient for global web coverage',
      'Some excluded-result and multi-year cases previously earned invalid success credit']}
 out.mkdir(parents=True)
 (out/'r3a1_quality_report.json').write_text(json.dumps(report_data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 # All HTML consists of authored queries, link metadata and test labels only.
 body=[]
 for x in rows:
  links='; '.join('<a href="'+html.escape(y['url'],quote=True)+'" target="_blank" rel="noopener noreferrer">'+html.escape(y['title'])+'</a>' for y in x['top_links']) or '<i>no result</i>'
  body.append('<tr><td>'+html.escape(x['id'])+'</td><td>'+html.escape(x['question'])+'</td><td>'+html.escape(x['verdict'])+'</td><td>'+links+'</td></tr>')
 page='''<!doctype html><html lang="en"><meta charset="utf-8"><title>Pulse Search R3-A1 quality gate</title>
<style>body{font:15px/1.55 system-ui;max-width:1200px;margin:40px auto;padding:0 16px;color:#183145}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #cdd8df;vertical-align:top;text-align:left;padding:10px}a{overflow-wrap:anywhere}.warn{padding:14px;background:#fff1e3;border-radius:8px}</style>
<h1>Pulse Search — R3-A1: adversarial quality gate</h1><p class="warn">Research only, not deployed. Engineer-authored URL relevance checks are NOT independent human labels; all factual answers remain unverified. No model = no trained contextual semantics.</p>'''
 page+='<pre>'+html.escape(json.dumps({'model':model_status,'distribution':counter,'failures':fail},indent=2))+'</pre><table><tr><th>Case</th><th>Question</th><th>Verdict</th><th>Top source links</th></tr>'+''.join(body)+'</table></html>'
 (out/'r3a1_quality_review.html').write_text(page,encoding='utf-8')
 with open(out/'r3a1_human_review_template.csv','w',newline='',encoding='utf-8') as fcsv:
  w=csv.writer(fcsv);w.writerow(['case_id','question','first_url','relevance_0_to_3','answer_supported_yes_no_unknown','independent_reviewer','notes'])
  for x in rows:w.writerow([x['id'],x['question'],x['top_links'][0]['url'] if x['top_links'] else '', '', '', '', ''])
 return report_data,out

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--index',required=True);ap.add_argument('--report',required=True);ap.add_argument('--out',required=True)
 ap.add_argument('--owner-approved-model-dir',default=None)
 a=ap.parse_args()
 try:
  r,out=evaluate(a.index,a.report,a.out,a.owner_approved_model_dir)
  print(json.dumps({k:r[k] for k in ('status','case_count','retrieval_or_safety_case_count','fact_cases_unverified','failures','distribution','model','verified_factual_answers','owner_index_writes','ranker_production_integration')},indent=2))
  for f in ('r3a1_quality_report.json','r3a1_quality_review.html','r3a1_human_review_template.csv'): print('REPORT='+str(out/f))
 except Exception as e:
  print('HOLD_R3_A1:'+type(e).__name__+':'+str(e),file=sys.stderr)
  return 2
 return 0
if __name__=='__main__':raise SystemExit(main())
