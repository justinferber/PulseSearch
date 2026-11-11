#!/usr/bin/env python3
"""Pulse Search R2-P33: pinned read-only three-way owner evaluation.

R2-P31 is baseline. R2-P32 owner audit *never invoked its experimental candidate*.
This script measures P31, P32, P33 on actual approved 120-page SQLite title/URL
metadata and body evidence *signals*; exports no publisher body prose.
"""
from __future__ import annotations
import argparse, collections, html, json, sys, re, sqlite3
from pathlib import Path
from urllib.parse import urlsplit
from contextlib import closing
import r2p32_evidence as p32audit
import r2p32_candidate as p32
import r2p33_candidate as p33
import pulse_search_r2p31 as p31

VERSION='R2-P33-ThreeWayShadow-v1'
OWNER_SHA=p32audit.OWNER_SHA
PREVIOUS_AUDIT_SHA='2414d557213283c47df297d30e242111cf27b5690de0b2c3290c456e0043414f'

# Genuine next-set probes authored after P33 implementation and frozen as a diagnostic.
# These are never loaded by the ranker and must NOT be silently tuned away.
NEW_HOLDOUT=(
 ('direct','2025 UK Black Pride event','url','/events/uk-black-pride-2025'),
 ('direct','NHS information about booking a blood test','url','/tests-and-treatments/blood-tests/'),
 ('direct','Where to replace my UK adult passport?','url','/renew-adult-passport/renew'),
 ('direct','How does a GP surgery registration work?','url','/how-to-register-with-a-gp-surgery/'),
 ('catalog','List London events for 2027','year_event','2027'),
 ('catalog','What were the London Open House editions?','series','open house'),
 ('catalog','What can I apply for through government online services?','gov_catalog','gov.uk'),
 ('negative','London events 2027 apart from Eid','exclude','/events/eid'),
 ('negative','Events in Paris in 2027','withhold',''),
 ('negative','New York Pride festival in 2025','withhold',''),
 ('negative','Diwali on the Square 2035','withhold',''),
 ('negative','London events 2027 only in Manchester','withhold',''),
 ('negative','Will it rain in Oxford tomorrow?','withhold',''),
 ('negative','Is a new laptop available in stock right now?','withhold',''),
 ('factual','Is St George\'s Day London 2025 free to attend?','fact_unknown','admission'),
 ('factual','Does the Eid on the Square 2027 webpage confirm its opening time?','fact_unknown','start time'),
 ('factual','Were all tickets sold for London New Year\'s Eve 2026?','fact_unknown','tickets'),
 ('factual','How much is a UK provisional driving licence this month?','fact_unknown','fee'),
)

def sha(path):return p32audit.shaf(path)

def probe_results(p,ranker,rows):
 result,status,spec=ranker.rank(p[1],rows)
 return {'status':status,'results':result,'judgement':p32audit.classify(p,result),'spec':spec}

def evaluate(owner,prior_audit,prior31,out_dir):
 if sha(owner)!=OWNER_SHA:raise ValueError('HOLD_OWNER_INDEX_SHA_MISMATCH')
 if sha(prior_audit)!=PREVIOUS_AUDIT_SHA:raise ValueError('HOLD_PREVIOUS_AUDIT_SHA_MISMATCH')
 prior=json.loads(Path(prior_audit).read_text(encoding='utf-8'))
 if prior.get('status')!='READ_ONLY_ADVERSARIAL_DIAGNOSTIC_COMPLETE_NOT_DEPLOYED' or len(prior.get('probes',[]))!=71:raise ValueError('HOLD_R2P32_AUDIT_NOT_ACCEPTED')
 if prior.get('owner_index_sha256_before_after')!=OWNER_SHA:raise ValueError('HOLD_INDEX_PROVENANCE_MISMATCH')
 if sha(prior31)!=p32audit.PRIOR_SHA:raise ValueError('HOLD_R2P31_SHA_MISMATCH')
 prior31_data=json.loads(Path(prior31).read_text())
 out=Path(out_dir)
 if out.exists():raise ValueError('HOLD_OUTPUT_ALREADY_EXISTS')
 frozen=p32audit.PROBES+p32audit.HELDOUT
 if len(frozen)!=71 or len(NEW_HOLDOUT)!=18:raise ValueError('HOLD_PROBES_COUNT_DRIFT')
 with closing(p32audit.open_ro(owner)) as db:
  counts=p32audit.validate_owner(db,prior31_data)
  rows=p31.load_titles(db)
  if len(rows)!=120:raise ValueError('HOLD_ROW_COUNT_DRIFT')
  for record in prior31_data['questions']:
   actual=p31.rank(record['query'],rows)
   if [r['url'] for r in actual[0]] != [r['url'] for r in record['results']] or actual[1]!=record['status']:
    raise ValueError('HOLD_P31_BASELINE_DRIFT:'+record['id'])
  source={q['id']:q for q in prior['probes']}
  all_rows=[]
  for i,p in enumerate(frozen+list(NEW_HOLDOUT),1):
   outputs={k:probe_results(p,v,rows) for k,v in [('p31',p31),('p32',p32),('p33',p33)]}
   if i<=71:
    original=source.get(f'p32_{i:02d}')
    if not original or original['question']!=p[1] or original['expectation_kind']!=p[2]:raise ValueError('HOLD_AUDIT_PROBE_IDENTITY_DRIFT')
    # Reproduce entire P32 baseline: earlier owner audit ran P31 ranker unchanged.
    oldurls=[x['url'] for x in original['returned_results']]
    if oldurls != [x['url'] for x in outputs['p31']['results']]:raise ValueError('HOLD_P32_OWNER_BASELINE_DRIFT:'+p[1])
   # Reuse prior source-rights-safe content signals; never export scraped publisher prose.
   signals=p32audit.page_signals(db,outputs['p33']['results'][:1],outputs['p33']['spec'])
   all_rows.append({'id':f'p33_{i:02d}','partition':'previous_71' if i<=71 else 'new_18_untouched',
    'question':p[1],'group':p[0],'expectation_kind':p[2], 'expectation':p[3],
    'p31':{'audit':outputs['p31']['judgement'],'titles':[r['title'] for r in outputs['p31']['results']]},
    'p32':{'audit':outputs['p32']['judgement'],'titles':[r['title'] for r in outputs['p32']['results']]},
    'p33':{'audit':outputs['p33']['judgement'],'titles':[r['title'] for r in outputs['p33']['results']],
           'urls':[r['url'] for r in outputs['p33']['results']], 'ranker_status':outputs['p33']['status'],
           'unverified_detail':outputs['p33']['spec'].get('unverified_detail')},
    'body_anchor_signals':signals,'factual_answer_verified':False})
  # Previously reviewed 36 questions must NOT return results for previously withheld items,
  # or lose first result identity for source-approved positives; performance is only URL matching.
  previous_gates=[]
  changes=[]
  for item in prior31_data['questions']:
   q=item['query'];old=item['results'];now,stat,_=p33.rank(q,rows)
   oldurl=old[0]['url'] if old else None
   newurl=now[0]['url'] if now else None
   if (oldurl is None and newurl is not None) or (oldurl is not None and newurl!=oldurl and not (item['kind']=='series' and q=='What happened during London Open House over the years?' and now and now[0]['title'].startswith('London Open House'))):previous_gates.append(q)
   if oldurl!=newurl:changes.append({'query':q,'before':oldurl,'after':newurl})
  integrity=db.execute('PRAGMA quick_check').fetchone()[0]
  if integrity!='ok':raise ValueError('HOLD_DB_INTEGRITY_NOT_OK')
 if sha(owner)!=OWNER_SHA:raise ValueError('HOLD_OWNER_DB_CHANGED')
 def dist(rows,key):return dict(collections.Counter(x[key]['audit'] for x in rows))
 old71=all_rows[:71];new18=all_rows[71:]
 stats={k:{'previous_71':dist(old71,k),'new_18_untouched':dist(new18,k)} for k in ('p31','p32','p33')}
 recovered=[r['id'] for r in old71 if r['p31']['audit']=='POTENTIAL_RETRIEVAL_ERROR' and r['p33']['audit']=='EXPECTED_RETRIEVAL_BEHAVIOUR']
 regress=[r['id'] for r in old71 if r['p31']['audit']=='EXPECTED_RETRIEVAL_BEHAVIOUR' and r['p33']['audit']!='EXPECTED_RETRIEVAL_BEHAVIOUR']
 issues=[]
 if previous_gates:issues.append('PREVIOUS_36_REGRESSION:'+str(len(previous_gates)))
 if regress:issues.append('BASELINE_71_RETRIEVAL_REGRESSION:'+str(len(regress)))
 # No forced certification of known probes or untouched holdout: disclose any misses.
 report={'version':VERSION,'status':'READ_ONLY_THREE_WAY_DIAGNOSTIC_COMPLETE_NOT_DEPLOYED' if not issues else 'HOLD_PREVIOUS_BENCHMARK_REGRESSION',
         'owner_index_sha256_before_after':OWNER_SHA,'index':counts, 'original_36_first_result_changes':changes,
         'original_36_guard_violations':previous_gates,'previous_71_recovered':recovered,
         'previous_71_candidate_regressions':regress,'distributions':stats,
         'candidate_remaining_retrieval_errors':[{'id':r['id'],'query':r['question'],'partition':r['partition']} for r in all_rows if r['p33']['audit']=='POTENTIAL_RETRIEVAL_ERROR'],
         'factual_answers_verified':0,'no_network_calls':True,'paid_api_calls':0,'db_writes':0,
         'production_integration':'HOLD_NEEDS_INDEPENDENT_HUMAN_EVIDENCE_AND_FRESH_GENERALISATION',
         'issues':issues,'probes':all_rows,
         'limits':['R2-P32 owner report was the R2-P31 baseline, not a test of the R2-P32 candidate',
                   'Source title/URL matching does not verify factual answers',
                   'Some expectations label suitable pages, not verified venue/date/availability claims',
                   'Rules were tuned on the earlier 71 probes; report fresh 18 without tuning',
                   'Publisher body prose is not exported or licensed by this audit']}
 out.mkdir(parents=True)
 (out/'r2p33_comparison_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 parts=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Pulse Search R2-P33</title>',
   '<style>body{font:15px/1.5 system-ui;max-width:1260px;margin:28px auto;padding:0 16px;color:#182839}table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #ccd4dc;text-align:left;vertical-align:top;padding:9px}.bad{color:#ac3b20;font-weight:bold}.ok{color:#177d49}small{color:#697b8c}</style>',
   '<h1>R2-P33 — Real-index P31 vs P32 vs P33</h1>',
   '<p><b>'+html.escape(report['status'])+'</b> · 120 indexed pages, 7 approved sources · 71 previous probes plus 18 genuinely new probes · no network/writes · no factual answers verified</p>',
   '<p>The previously reported 23 R2-P32 errors were produced by <b>R2-P31 baseline</b>. P32 and P33 are separately evaluated here.</p>',
   '<table><tr><th>Set</th><th>P31 baseline errors</th><th>P32 candidate errors</th><th>P33 candidate errors</th><th>Unverified facts</th></tr>']
 for name,rows0 in [('Previous 71',old71),('New untouched 18',new18)]:
  cnt=lambda name:sum(x[name]['audit']=='POTENTIAL_RETRIEVAL_ERROR' for x in rows0)
  unv=sum(x['p33']['audit']=='UNVERIFIED_FACT_NEEDS_SOURCE_EVIDENCE' for x in rows0)
  parts.append(f'<tr><td>{name}</td><td>{cnt("p31")}</td><td>{cnt("p32")}</td><td>{cnt("p33")}</td><td>{unv}</td></tr>')
 parts.append('</table><h2>Query-by-query findings</h2><table><tr><th>ID / question</th><th>P31</th><th>P32</th><th>P33</th><th>P33 top indexed page</th></tr>')
 for r in all_rows:
  def lab(a):return 'Matched expected retrieval' if a=='EXPECTED_RETRIEVAL_BEHAVIOUR' else 'Unverified fact' if a=='UNVERIFIED_FACT_NEEDS_SOURCE_EVIDENCE' else 'Potential error'
  result=r['p33']['urls'];title=r['p33']['titles']
  linked='<a href="'+html.escape(result[0],quote=True)+'">'+html.escape(title[0])+'</a>' if result else 'No indexed page'
  cells=''.join('<td class="'+('bad' if r[k]['audit']=='POTENTIAL_RETRIEVAL_ERROR' else 'ok')+'">'+html.escape(lab(r[k]['audit']))+'</td>' for k in ['p31','p32','p33'])
  parts.append('<tr><td><small>'+r['id']+' '+html.escape(r['partition'])+'</small><p>'+html.escape(r['question'])+'</p></td>'+cells+'<td>'+linked+'</td></tr>')
 parts.append('</table><p><strong>Research only.</strong> Even all expected URLs does not imply exact answers, source rights, authoritative event times or current availability. No source prose exported.</p></html>')
 (out/'r2p33_comparison_review.html').write_text('\n'.join(parts),encoding='utf-8')
 return report

def main():
 ap=argparse.ArgumentParser()
 for name in ('owner_index','p32_report','p31_report','out'):ap.add_argument('--'+name.replace('_','-'),required=True)
 a=ap.parse_args()
 try:
  r=evaluate(a.owner_index,a.p32_report,a.p31_report,a.out)
  print(json.dumps({k:r[k] for k in ('status','index','distributions','previous_71_recovered','candidate_remaining_retrieval_errors','original_36_guard_violations','factual_answers_verified','no_network_calls','db_writes','production_integration')},indent=2))
  print('REPORT='+str(Path(a.out)/'r2p33_comparison_report.json'))
  print('HTML='+str(Path(a.out)/'r2p33_comparison_review.html'))
  return 0 if not r['issues'] else 2
 except (ValueError,KeyError,TypeError,AssertionError,sqlite3.DatabaseError,OSError) as e:
  print('HOLD_R2P33:'+str(e),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
