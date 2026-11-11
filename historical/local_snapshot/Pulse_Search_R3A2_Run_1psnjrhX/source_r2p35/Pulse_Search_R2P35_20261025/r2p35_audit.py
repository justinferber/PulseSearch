#!/usr/bin/env python3
"""R2-P35 owner read-only hybrid architecture benchmark and provenance audit.
The ranker NEVER imports this file, the gold labels, or expected URLs.
No text snippets from metadata-only sources are exported.
"""
from __future__ import annotations
import argparse,collections,hashlib,html,json,sys,sqlite3
from dataclasses import asdict
from pathlib import Path
from contextlib import closing
from urllib.parse import urlsplit
from hybrid_core import HybridIndex
from evidence_gate import evidence_signals,ReliabilityCalibrator

OWNER_SHA='bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d'
PREVIOUS_SHA='c15eaba6344394dffc387ecc0599a05c6f924f770ab0de87010d1e27ad02e4ce'
# Authored after R2-P35 architecture code was locked; do not tune this release
# against these. All query-result comparisons are retrieval checks, not facts.
NEW_HOLDOUT=(
 ('Where can a new NHS patient sign up to see a doctor?', 'url','/how-to-register-with-a-gp-surgery/'),
 ('How do I arrange laboratory blood screening?', 'url','/blood-tests/'),
 ('What should a UK learner motorist apply for?', 'url','/apply-first-provisional-driving-licence'),
 ('Where to make an electoral registration?', 'url','/register-to-vote'),
 ('What are the 2024 and 2025 London Open House editions?', 'series','open house'),
 ('All festivals in London during 2027 except St Patrick’s', 'exclude','/events/st-patricks-day'),
 ('London summer events in 2025', 'year_event','2025'),
 ('St George’s Day 2026 London', 'url','/events/st-georges-day-2026'),
 ('Eid on the Square 2027 excluding Eid', 'withhold',''),
 ('Paris concerts in 2027', 'withhold',''),
 ('Should I buy a laptop in stock at a London store now?', 'withhold',''),
 ('Will there be thunderstorms over Newbury tomorrow?', 'withhold',''),
 ('London festivals 2027 located in Berlin', 'withhold',''),
 ('Diwali on the Square 2040', 'withhold',''),
 ('How much is an adult passport renewal in 2026?', 'fact_unknown','fee'),
 ('Which Eid on the Square 2027 entrance is accessible?', 'fact_unknown','accessibility'),
 ('Was Armed Forces Day 2027 postponed?', 'fact_unknown','cancellation'),
 ('What is the exact start time for Black on the Square 2027?', 'fact_unknown','time'),
 ('Are tickets for London New Year’s Eve 2026 still available?', 'fact_unknown','tickets'),
 ('How many people attended Pride in London 2024?', 'fact_unknown','attendance'),
)

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def read_db(p):
 db=sqlite3.connect(Path(p).resolve().as_uri()+'?mode=ro',uri=True)
 db.row_factory=sqlite3.Row
 db.execute('PRAGMA query_only=ON')
 return db

def check(probe,rows):
 q,kind,expected=probe
 urls=[r['url'] for r in rows]
 if kind=='fact_unknown':return 'FACT_UNVERIFIED'
 if kind=='url':ok=bool(rows) and urlsplit(rows[0]['url']).path.endswith(expected)
 elif kind=='withhold':ok=not rows
 elif kind=='exclude':ok=all(urlsplit(u).path!=expected for u in urls)
 elif kind=='year_event':ok=len(rows)>=2 and all(expected in r['title'] and '/events/' in r['url'] for r in rows)
 elif kind=='year_festival':ok=bool(rows) and all(expected in r['title'] and 'festival' in r['title'].casefold() for r in rows)
 elif kind=='year_celebration':ok=bool(rows) and all(expected in r['title'] and '/events/' in r['url'] for r in rows)
 elif kind=='gov_catalog':ok=len(rows)>=2 and all(urlsplit(r['url']).netloc=='www.gov.uk' for r in rows)
 elif kind=='series':ok=len(rows)>=2 and all(expected in r['title'].casefold() for r in rows)
 else:raise ValueError('UNSUPPORTED_EXPECTATION:'+kind)
 return 'EXPECTED_RETRIEVAL' if ok else 'RETRIEVAL_MISS'

def run(index,prior_report,out):
 out=Path(out)
 if out.exists():raise ValueError('HOLD_OUTPUT_EXISTS')
 if sha(index)!=OWNER_SHA:raise ValueError('HOLD_OWNER_INDEX_SHA_MISMATCH')
 if sha(prior_report)!=PREVIOUS_SHA:raise ValueError('HOLD_PRIOR_REPORT_SHA')
 prior=json.loads(Path(prior_report).read_text(encoding='utf-8'))
 if len(prior['probes'])!=109 or prior['status']!='READ_ONLY_GENERALISATION_DIAGNOSTIC_COMPLETE_NOT_DEPLOYED':raise ValueError('HOLD_PRIOR_REPORT_DRIFT')
 with closing(read_db(index)) as db:
  if db.execute('PRAGMA query_only').fetchone()[0]!=1:raise ValueError('HOLD_QUERY_ONLY_NOT_SET')
  count=db.execute('SELECT COUNT(*) FROM pages WHERE indexed=1').fetchone()[0]
  fts=db.execute('SELECT COUNT(*) FROM page_fts').fetchone()[0]
  sources=db.execute('SELECT COUNT(DISTINCT p.source_id) FROM pages p JOIN sources s USING(source_id) WHERE p.indexed=1 AND s.approved=1 AND s.enabled=1').fetchone()[0]
  if (count,fts,sources)!=(120,120,7):raise ValueError('HOLD_CORPUS_DRIFT')
  rs=db.execute('''SELECT p.url,p.title,p.body,p.fetched_at,s.display_mode,p.source_id FROM pages p JOIN sources s USING(source_id) WHERE p.indexed=1 AND s.approved=1 AND s.enabled=1 ORDER BY p.url''')
  corpus=[dict(r) for r in rs]
  if len(corpus)!=120:raise ValueError('HOLD_APPROVED_ROWS_NOT_120')
  h=HybridIndex(corpus)
  body_lookup={r['url']:r for r in corpus}
  probes=[]
  for p in prior['probes']:
   probe=(p['query'],p['expected_kind'],p['expected_value'])
   result=h.search(probe[0]); verdict=check(probe,result['results'])
   probes.append({'partition':p['partition'],'query':probe[0], 'expected_kind':probe[1],
    'previous_p34':p['p34_label'],'new_r2p35':verdict,
    'status':result['status'],'kind':result['intent'].kind,
    'returned':[{'url':v['url'],'title':v['title'],'score':v['score'],'confidence_label':v['confidence_label']} for v in result['results']],
    'requires_facts':result['intent'].requires_facts,'unverified_factual_answer':True})
  for q,k,v in NEW_HOLDOUT:
   result=h.search(q);verdict=check((q,k,v),result['results'])
   probes.append({'partition':'fresh_20_sealed','query':q,'expected_kind':k,
    'previous_p34':None,'new_r2p35':verdict,'status':result['status'],'kind':result['intent'].kind,
    'returned':[{'url':x['url'],'title':x['title'],'score':x['score'],'confidence_label':x['confidence_label']} for x in result['results']],
    'requires_facts':result['intent'].requires_facts,'unverified_factual_answer':True})
  # Evidence extracted only as hash, counts and provenance; never as body prose.
  fact_signals=[]
  for p in probes:
   if p['expected_kind']!='fact_unknown':continue
   top=p['returned'][0]['url'] if p['returned'] else None
   ev=evidence_signals(body_lookup[top].get('body'),body_lookup[top].get('display_mode')) if top else None
   fact_signals.append({'partition':p['partition'],'query':p['query'],'top_source':top,
     'source_signals':ev,'answer_status':'UNVERIFIED_NO_CLAIM'})
  if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('HOLD_DB_INTEGRITY')
 if sha(index)!=OWNER_SHA:raise ValueError('HOLD_DB_CHANGED')
 dist={}
 for name in ('previous_71','previous_18','fresh_20_untouched','fresh_20_sealed'):
  rows=[p for p in probes if p['partition']==name]
  dist[name]=dict(collections.Counter(p['new_r2p35'] for p in rows))
 report={'version':'R2-P35-HybridFoundation-v1','status':'READ_ONLY_HYBRID_DIAGNOSTIC_COMPLETE_NOT_DEPLOYED',
  'index_sha256_before_after':OWNER_SHA,'corpus':{'pages':120,'fts':120,'approved_sources':7},
  'hybrid_capabilities':h.capabilities,'calibration_status':ReliabilityCalibrator().status,
  'previous_r2p34_retrieval_misses':len(prior['remaining_retrieval_misses']),
  'distributions':dist,'factual_answers_verified':0,'fact_probe_signals':fact_signals,
  'no_network_calls':True,'paid_api_calls':0,'database_writes':0,
  'production_integration':'HOLD_SEMANTIC_MODEL_CALIBRATION_EVIDENCE_RIGHTS_AND_UNSEEN_RECALL',
  'probes':probes,'limitations':['Not a statistical probability calibration','Subword cosine is not contextual semantics; approved local model absent',
  'URL-level expected checks are NOT factual answer grades','Source display policy metadata-only; no publisher body exported',
  'Limited 120 pages / 7 origins; any missing answer may require new licensed sources',
  'R2-P35 is a new research architecture, not deployed to existing search API']}
 out.mkdir(parents=True)
 (out/'r2p35_hybrid_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 html_rows=[]
 for p in probes:
  top=p['returned'][0] if p['returned'] else None
  a=('<a href="'+html.escape(top['url'],quote=True)+'">'+html.escape(top['title'])+'</a>') if top else 'No indexed page'
  html_rows.append('<tr><td>'+html.escape(p['partition'])+'</td><td>'+html.escape(p['query'])+'</td><td>'+html.escape(p['new_r2p35'])+'</td><td>'+a+'</td><td>'+html.escape(p['status'])+'</td></tr>')
 report_html='''<!doctype html><html lang="en"><meta charset="utf-8"><title>Pulse Search R2-P35 Hybrid Foundation</title>
<style>body{font:15px/1.5 system-ui;max-width:1200px;margin:auto;padding:25px;color:#17283d}table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid #ddd;padding:9px;text-align:left}a{overflow-wrap:anywhere} .warn{padding:15px;background:#fff4e3}</style>
<h1>Pulse Search — R2-P35 Hybrid Foundation</h1><p class="warn">Research only, NOT deployed. Character n-gram similarity is not a contextual semantic model. Factual answers verified: <b>0</b>. Source body text not exported.</p>'''
 report_html+='<h2>Retrieval diagnostic by partition</h2><pre>'+html.escape(json.dumps(dist,indent=2))+'</pre><h2>All 129 questions</h2><table><tr><th>Partition</th><th>Question</th><th>Automated judgement</th><th>First result</th><th>Safety status</th></tr>'+'\n'.join(html_rows)+'</table></html>'
 (out/'r2p35_hybrid_review.html').write_text(report_html,encoding='utf-8')
 return report

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--index',required=True);ap.add_argument('--prior-report',required=True);ap.add_argument('--out',required=True)
 a=ap.parse_args()
 try:
  report=run(a.index,a.prior_report,a.out)
  print(json.dumps({k:report[k] for k in ('status','corpus','distributions','hybrid_capabilities','calibration_status','factual_answers_verified','database_writes','no_network_calls','production_integration')},indent=2))
  print('REPORT='+str(Path(a.out)/'r2p35_hybrid_report.json'))
  print('HTML='+str(Path(a.out)/'r2p35_hybrid_review.html'))
  return 0
 except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as e:
  print('HOLD_R2P35:'+str(e),file=sys.stderr)
  return 2
if __name__=='__main__':raise SystemExit(main())
