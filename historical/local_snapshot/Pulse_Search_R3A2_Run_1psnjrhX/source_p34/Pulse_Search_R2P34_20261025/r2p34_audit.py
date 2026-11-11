#!/usr/bin/env python3
"""R2-P34: owner-index read-only four-way retrieval + fresh held-out probes.

Requires exact accepted SHA pins and reproduces R2-P33's owner findings first.
No network, publisher-body export, ranking integration or factual-answer claims.
"""
from __future__ import annotations
import argparse, collections, html, json, sqlite3, sys
from contextlib import closing
from pathlib import Path
import r2p33_audit as a33
import r2p32_evidence as ev
import r2p33_candidate as p33
import r2p34_candidate as p34
import pulse_search_r2p31 as p31

VERSION='R2-P34-FourWay-Generalisation-v1'
OWNER_SHA=a33.OWNER_SHA
# New questions authored *after* freeze of the P34 candidate; no further tuning.
# Fact probes are intentionally ungraded, even when an appropriate page is found.
NEW_SEALED_HOLDOUT=[
 ('direct','How can I register as an NHS patient with a doctor?', 'url', '/nhs-services/gps/how-to-register-with-a-gp-surgery/'),
 ('direct','NHS blood screening test instructions', 'url','/tests-and-treatments/blood-tests/'),
 ('direct','Getting a temporary drivers permit in the UK', 'url','/apply-first-provisional-driving-licence'),
 ('direct','Help me enrol for voting in England', 'url','/register-to-vote'),
 ('direct','JavaScript learning introduction', 'url','/What_is_JavaScript'),
 ('direct','City Hall Open House 2026', 'url','/events/city-hall-open-house-2026'),
 ('direct','Black on the Square festival 2027', 'url','/events/black-square-2027'),
 ('catalog','London celebrations planned for 2027','year_celebration','2027'),
 ('catalog','Events happening around London in the year 2025','year_event','2025'),
 ('catalog','Which official online services can I access through GOV.UK?','gov_catalog','gov.uk'),
 ('catalog','Previous years of St George’s Day London events','series','st george'),
 ('negative','London events 2027 excluding St Patrick’s Festival','exclude','/events/st-patricks-day'),
 ('negative','London festival events 2026 without London Games Festival','exclude','/events/london-games-festival-2026'),
 ('negative','Events in Berlin during 2027','withhold',''),
 ('negative','What is the weather in Manchester tomorrow?','withhold',''),
 ('negative','Diwali on the Square 2039','withhold',''),
 ('factual','What was the exact start time of Eid on the Square 2027?','fact_unknown','start'),
 ('factual','How much is passport renewal today?','fact_unknown','fee'),
 ('factual','Was St Patrick’s Festival 2027 cancelled?','fact_unknown','cancellation'),
 ('factual','Which 2027 London events require paid tickets?','fact_unknown','ticket'),
]


def _dist(rows, key):
 return dict(collections.Counter(r[key] for r in rows))


def evaluate(owner, prior_p32, prior_p31, output):
 out=Path(output)
 if out.exists():raise ValueError('HOLD_OUTPUT_ALREADY_EXISTS')
 if ev.shaf(owner)!=OWNER_SHA:raise ValueError('HOLD_OWNER_SHA')
 if ev.shaf(prior_p32)!=a33.PREVIOUS_AUDIT_SHA:raise ValueError('HOLD_P32_SHA')
 if ev.shaf(prior_p31)!=ev.PRIOR_SHA:raise ValueError('HOLD_P31_SHA')
 prior33=a33.evaluate(owner,prior_p32,prior_p31,out/'prior_p33_verified')
 dist=prior33['distributions']
 expected={'p31':(23,5),'p32':(6,4),'p33':(0,4)}
 for label,errs in expected.items():
  old=dist[label]['previous_71'].get('POTENTIAL_RETRIEVAL_ERROR',0)
  new=dist[label]['new_18_untouched'].get('POTENTIAL_RETRIEVAL_ERROR',0)
  if (old,new)!=errs:raise ValueError('HOLD_P33_REPRODUCTION_DRIFT:'+label+':'+str((old,new)))
 if prior33['original_36_guard_violations'] or prior33['previous_71_candidate_regressions']:
  raise ValueError('HOLD_P33_NOT_ACCEPTED')
 old71=list(ev.PROBES)+list(ev.HELDOUT)
 old18=list(a33.NEW_HOLDOUT)
 new20=list(NEW_SEALED_HOLDOUT)
 if len(old71)!=71 or len(old18)!=18 or len(new20)!=20:raise ValueError('HOLD_PROBE_SET_DRIFT')
 with closing(ev.open_ro(owner)) as db:
  p31_prior=json.loads(Path(prior_p31).read_text(encoding='utf-8'))
  ev.validate_owner(db,p31_prior)
  rows=p31.load_titles(db)
  # Guard every original approved first-result URL and every withheld query.
  guard=[]; changed=[]
  for item in p31_prior['questions']:
   results,status,spec=p34.rank(item['query'],rows)
   old=item['results'][0]['url'] if item['results'] else None
   new=results[0]['url'] if results else None
   if old != new:
    changed.append({'question':item['query'],'before':old,'after':new})
    if not (item['kind']=='series' and item['query']=='What happened during London Open House over the years?' and new and results[0]['title'].startswith('London Open House')):
     guard.append(item['query'])
  results=[]
  for partition,probes in [('previous_71',old71),('previous_18',old18),('fresh_20_untouched',new20)]:
   for i,probe in enumerate(probes,1):
    q=probe[1]
    old,_,_=p33.rank(q,rows)
    match,status,spec=p34.rank(q,rows)
    signals=ev.page_signals(db,match[:1],spec)
    results.append({'id':f'{partition}_{i:02d}','partition':partition,'group':probe[0],
      'query':q,'expected_kind':probe[2],'expected_value':probe[3],
      'p33_label':ev.classify(probe,old),'p34_label':ev.classify(probe,match),
      'p33_top_title':old[0]['title'] if old else None,
      'p34_status':status,'p34_results':[{'title':x['title'],'url':x['url']} for x in match],
      'body_signals':signals,'factual_answer_verified':False})
  if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('HOLD_INTEGRITY')
 if ev.shaf(owner)!=OWNER_SHA:raise ValueError('HOLD_OWNER_DB_CHANGED')
 def failures(partition,which):
  return [r for r in results if r['partition']==partition and r[which]=='POTENTIAL_RETRIEVAL_ERROR']
 old_fail=failures('previous_71','p34_label');hold_fail=failures('previous_18','p34_label')
 recovered=[r for r in results if r['partition']=='previous_18' and r['p33_label']=='POTENTIAL_RETRIEVAL_ERROR' and r['p34_label']=='EXPECTED_RETRIEVAL_BEHAVIOUR']
 false_negative=[r for r in results if r['partition']!='fresh_20_untouched' and r['p33_label']=='EXPECTED_RETRIEVAL_BEHAVIOUR' and r['p34_label']!='EXPECTED_RETRIEVAL_BEHAVIOUR']
 issues=[]
 if old_fail:issues.append('PREVIOUS_71_ERRORS:'+str(len(old_fail)))
 if hold_fail:issues.append('PREVIOUS_18_ERRORS:'+str(len(hold_fail)))
 if false_negative:issues.append('RETRIEVAL_REGRESSION:'+str(len(false_negative)))
 if guard:issues.append('ORIGINAL_36_GUARD_VIOLATIONS:'+str(len(guard)))
 report={
  'version':VERSION,'status':'READ_ONLY_GENERALISATION_DIAGNOSTIC_COMPLETE_NOT_DEPLOYED' if not issues else 'HOLD_OLD_BENCHMARK_REGRESSION',
  'index_sha_before_after':OWNER_SHA,'indexed_pages':120,'sources':7,
  'original_36_guard_violations':guard,'original_36_first_changes':changed,
  'prior_p33_reproduction':dist,
  'comparative_counts':{part:{name:_dist([r for r in results if r['partition']==part], name) for name in ['p33_label','p34_label']} for part in ['previous_71','previous_18','fresh_20_untouched']},
  'previous_holdout_errors_recovered':[{'id':r['id'],'query':r['query']} for r in recovered],
  'remaining_retrieval_misses':[{'id':r['id'],'query':r['query'],'partition':r['partition']} for r in results if r['p34_label']=='POTENTIAL_RETRIEVAL_ERROR'],
  'factual_answers_verified':0,'no_network_calls':True,'paid_search_api_calls':0,'database_writes':0,
  'production_integration':'HOLD_PENDING_GENERALISATION_AND_INDEPENDENT_FACT_EVIDENCE',
  'issues':issues,'probes':results,
  'limitations':['Retrieval expected URL is a proxy, not an answer','Fresh-20 authored after candidate freeze but not independently human graded',
                 'Body term presence is not proof of accurate time, place, tickets, law or health guidance',
                 'No publisher body exported','Only 120 pages/7 approved origins']}
 out.mkdir(parents=True,exist_ok=True)
 (out/'r2p34_generalisation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 page=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Pulse Search R2-P34</title>',
 '<style>body{font:15px/1.5 system-ui;margin:2rem auto;padding:0 1rem;max-width:1150px;color:#183044}table{width:100%;border-collapse:collapse}td,th{padding:8px;text-align:left;vertical-align:top;border-bottom:1px solid #b5c4ce}a{overflow-wrap:anywhere}.bad{color:#9d2d24;font-weight:bold}.muted{color:#617283}</style>',
 '<h1>Pulse Search R2-P34 · owner-index generalisation</h1>',
 '<p>Read-only owner 120-page research index. Previously tested 71 + previous holdout 18 + new sealed 20. No public network, no paid API and no indexed database changes. <b>Zero factual answers verified.</b></p>',
 '<p><strong>'+html.escape(report['status'])+'</strong></p><table><tr><th>Partition</th><th>P33 retrieval misses</th><th>P34 retrieval misses</th><th>Unverified factual probes</th></tr>']
 for part in ['previous_71','previous_18','fresh_20_untouched']:
  r=report['comparative_counts'][part]
  err=lambda p:r[p].get('POTENTIAL_RETRIEVAL_ERROR',0)
  page.append('<tr><td>'+html.escape(part)+'</td><td>'+str(err('p33_label'))+'</td><td>'+str(err('p34_label'))+'</td><td>'+str(r['p34_label'].get('UNVERIFIED_FACT_NEEDS_SOURCE_EVIDENCE',0))+'</td></tr>')
 page.append('</table><h2>Question-by-question comparison</h2><table><tr><th>ID / Query</th><th>P33</th><th>P34</th><th>P34 first indexed page</th></tr>')
 for r in results:
  def fmt(x):return 'retrieval error' if x=='POTENTIAL_RETRIEVAL_ERROR' else 'unverified fact' if x=='UNVERIFIED_FACT_NEEDS_SOURCE_EVIDENCE' else 'expected indexed page'
  bad=' class="bad"' if r['p34_label']=='POTENTIAL_RETRIEVAL_ERROR' else ''
  url=r['p34_results'][0]['url'] if r['p34_results'] else None
  title=r['p34_results'][0]['title'] if r['p34_results'] else None
  link='<a href="'+html.escape(url,quote=True)+'">'+html.escape(title)+'</a>' if url else '<span class="muted">No page</span>'
  page.append('<tr><td>'+html.escape(r['id'])+'<p>'+html.escape(r['query'])+'</p></td><td>'+fmt(r['p33_label'])+'</td><td'+bad+'>'+fmt(r['p34_label'])+'</td><td>'+link+'</td></tr>')
 page.append('</table><p>Research only: page relevance is not a sourced factual answer, publication rights, live booking status, or event date verification.</p>')
 (out/'r2p34_generalisation_review.html').write_text('\n'.join(page),encoding='utf-8')
 return report


def main():
 parser=argparse.ArgumentParser()
 for arg in ['owner_index','p32_report','p31_report','out']:
  parser.add_argument('--'+arg.replace('_','-'),required=True)
 args=parser.parse_args()
 try:
  r=evaluate(args.owner_index,args.p32_report,args.p31_report,args.out)
  print(json.dumps({k:r[k] for k in ('status','comparative_counts','previous_holdout_errors_recovered','remaining_retrieval_misses','original_36_guard_violations','factual_answers_verified','no_network_calls','database_writes','production_integration')},indent=2))
  print('REPORT='+str(Path(args.out)/'r2p34_generalisation_report.json'))
  print('HTML='+str(Path(args.out)/'r2p34_generalisation_review.html'))
  return 0 if not r['issues'] else 2
 except (ValueError,KeyError,TypeError,sqlite3.Error,OSError) as e:
  print('HOLD_R2P34:'+str(e),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
