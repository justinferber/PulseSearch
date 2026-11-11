#!/usr/bin/env python3
"""R2-P32: independent adversarial search retrieval + content-signal research audit.

Not a factual-answer grader. Does NOT serve or export copyrighted body prose.
Does NOT write the index, contact websites, or install candidate rankers.
"""
from __future__ import annotations
import argparse, collections, hashlib, html, json, re, sqlite3, sys
from pathlib import Path
from contextlib import closing
from urllib.parse import urlsplit

VERSION='R2-P32-Evidence-And-Adversarial-v1'
OWNER_SHA='bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d'
PRIOR_SHA='3d86e678fb1208d63b3021f04680304f25354c39b5c7f3248b25c2933104e625'
# Expectations are a frozen audit fixture, NEVER loaded or referenced by the ranker.
# 'url': precise known indexed source identity; 'withhold': unsupported with this corpus;
# 'exclude': the named excluded result should not be presented; 'facet': year/source/subject.
PROBES=[
 ('direct','Where do I register with an NHS GP?', 'url','/nhs-services/gps/how-to-register-with-a-gp-surgery/'),
 ('direct','NHS guide to blood testing', 'url','/tests-and-treatments/blood-tests/'),
 ('direct','How can I find my council tax band?', 'url','/council-tax-bands'),
 ('direct','British adult passport renewal application', 'url','/renew-adult-passport/renew'),
 ('direct','A guide explaining JavaScript', 'url','/What_is_JavaScript'),
 ('direct','HTTP specification and explanation', 'url','/Web/HTTP'),
 ('direct','Application for a provisional driving licence', 'url','/apply-first-provisional-driving-licence'),
 ('direct','Instructions for registering to vote', 'url','/register-to-vote'),
 ('direct','Lunar New Year London 2026', 'url','/events/lunar-new-year-festival-spring-2026'),
 ('direct','Vaisakhi 2024 in London', 'url','/events/vaisakhi-2024'),
 ('direct','UK Black Pride in the year 2024', 'url','/events/uk-black-pride-2024'),
 ('direct','Armed Forces Day London 2025', 'url','/events/armed-forces-day-2025'),
 ('direct','What was St George\'s Day London 2025?', 'url','/events/st-georges-day-2025'),
 ('direct','Eid on the Square 2025 celebration', 'url','/events/eid-square-2025'),
 ('direct','London Data Week 2026 information', 'url','/events/london-data-week-2026'),
 ('direct','What is London Open House 2024?', 'url','/events/london-open-house-2024'),
 ('direct','Pride in London 2024 event', 'url','/events/pride-london-2024'),
 ('direct','What was the Christmas carol service 2025 run by the Mayor?', 'url','/events/mayors-christmas-carol-service-2025'),
 ('direct','Where can I submit my voter registration?', 'url','/register-to-vote'),
 ('direct','What do I need to do to get a learner driver licence?', 'url','/apply-first-provisional-driving-licence'),
 ('catalog','Find events in London during 2027', 'year_event','2027'),
 ('catalog','Show London events planned for 2026', 'year_event','2026'),
 ('catalog','Find London festivals in 2025', 'year_festival','2025'),
 ('catalog','What festivals were on in London in 2027?', 'year_festival','2027'),
 ('catalog','Celebrations in London during 2024', 'year_celebration','2024'),
 ('catalog','What services does GOV.UK offer online?', 'gov_catalog','gov.uk'),
 ('catalog','Historical editions of London Open House', 'series','open house'),
 ('catalog','Tell me about past Eid on the Square editions', 'series','eid'),
 ('negative','Diwali on the Square 2038', 'withhold',''),
 ('negative','Armed Forces Day 2044', 'withhold',''),
 ('negative','London events in the year 2039', 'withhold',''),
 ('negative','Will it snow in Bristol tomorrow?', 'withhold',''),
 ('negative','Which new laptop can I buy in stock now?', 'withhold',''),
 ('negative','Shops selling shoes in Manchester open now', 'withhold',''),
 ('negative','Which New York festivals happen in 2027?', 'withhold',''),
 ('negative','Is the New Year\'s Eve festival in Sydney in 2026?', 'withhold',''),
 ('negative','Apply for a mortgage on Mars', 'withhold',''),
 ('negative','Events happening in Liverpool during 2027', 'withhold',''),
 ('negative','Diwali on the Square 2026 but in New York', 'withhold',''),
 ('negative','London festivals in 2026 excluding St Patrick\'s Festival', 'exclude','/events/st-patricks-festival-2026'),
 ('negative','London events 2027 excluding Eid', 'exclude','/events/eid'),
 ('negative','London events 2027 only in Edinburgh', 'withhold',''),
 ('negative','London events 2027 except memorial services', 'exclude','/events/77-memorial-service-2027'),
 ('negative','Which 2027 London events have free entry confirmed?', 'fact_unknown','free entry'),
 ('negative','Which 2026 London festivals were cancelled?', 'fact_unknown','cancelled'),
 ('negative','London events in 2027 that have sold out', 'fact_unknown','sold out'),
 ('negative','London festivals for 2026 but not St Patrick\'s', 'exclude','/events/st-patricks-festival-2026'),
 ('factual','What is the entry price for Black on the Square 2027?', 'fact_unknown','entry price'),
 ('factual','What time does Eid on the Square 2027 start?', 'fact_unknown','start time'),
 ('factual','Did London Games Festival 2026 sell tickets?', 'fact_unknown','ticket sales'),
 ('factual','Was London Data Week 2025 cancelled?', 'fact_unknown','cancellation'),
 ('factual','How many people attended London Open House 2024?', 'fact_unknown','attendance'),
 ('factual','What is the fee for a UK adult passport renewal?', 'fact_unknown','fees'),
 ('factual','What steps are needed to register with a GP?', 'fact_unknown','registration steps'),
 ('factual','Which London events in 2027 have wheelchair access?', 'fact_unknown','accessibility'),
]

# Sealed post-development holdout: these cases are NOT used to tune R2-P32 candidate.
# Failures are reported unchanged for the next iteration rather than fixed here.
HELDOUT=[
 ('direct','Apply for a provisional drivers permit', 'url','/apply-first-provisional-driving-licence'),
 ('direct','Renew or replace a passport in England', 'url','/renew-adult-passport/renew'),
 ('direct','What do I need to register with a GP near my home?', 'url','/how-to-register-with-a-gp-surgery/'),
 ('direct','Eid celebration at Trafalgar Square 2026', 'url','/events/eid-square-2026'),
 ('direct','UK Black Pride scheduled for 2025', 'url','/events/uk-black-pride-2025'),
 ('direct','Guide for replacing a lost UK adult passport', 'url','/renew-adult-passport/renew'),
 ('negative','London events in 2027 but not Eid', 'exclude','/events/eid'),
 ('negative',"Which London events in 2027 aren't free?", 'fact_unknown','free entry'),
 ('negative','What Manchester events will happen in 2027?', 'withhold',''),
 ('negative','Eid on the Square 2027 except Eid', 'withhold',''),
 ('negative','Diwali on the Square 2026 in Berlin', 'withhold',''),
 ('catalog','Government service applications on GOV.UK', 'gov_catalog','gov.uk'),
 ('catalog','Which festivals were held in London in 2025?', 'year_festival','2025'),
 ('factual','Do tickets remain available for London New Year’s Eve 2026?', 'fact_unknown','tickets'),
 ('factual','Are there step-free routes at London Open House 2026?', 'fact_unknown','accessibility'),
 ('factual','What is the source-confirmed event date for Eid 2027?', 'fact_unknown','event date'),
]

def shaf(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()

def open_ro(path):
 # SQLite URI mode=ro; no writes or schema initialization permitted.
 c=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
 c.row_factory=sqlite3.Row
 c.execute('PRAGMA query_only=ON')
 return c

def validate_owner(conn,prior):
 counts={}
 counts['pages']=conn.execute('SELECT COUNT(*) FROM pages WHERE indexed=1').fetchone()[0]
 counts['fts']=conn.execute('SELECT COUNT(*) FROM page_fts').fetchone()[0]
 counts['sources']=conn.execute('SELECT COUNT(DISTINCT p.source_id) FROM pages p JOIN sources s USING(source_id) WHERE p.indexed=1 AND s.approved=1 AND s.enabled=1').fetchone()[0]
 if counts != {'pages':120,'fts':120,'sources':7}:raise ValueError('OWNER_CORPUS_OR_SCHEMA_DRIFT:'+str(counts))
 if prior.get('status')!='READ_ONLY_SHADOW_PROVISIONAL_PASS_NOT_DEPLOYED' or len(prior.get('questions',[]))!=36 or prior.get('owner_index_sha256_before_after')!=OWNER_SHA:raise ValueError('R2P31_PRIOR_REPORT_NOT_ACCEPTED')
 return counts

def classify(probe,res):
 group,q,kind,expected=probe
 urls=[r['url'] for r in res]
 if kind=='url':good=bool(res) and urlsplit(res[0]['url']).path.endswith(expected)
 elif kind=='withhold':good=not res
 elif kind=='exclude':good=all(urlsplit(u).path!=expected for u in urls)
 elif kind=='year_event':good=len(res)>=2 and all(expected in x['title'] and '/events/' in x['url'] for x in res)
 elif kind=='year_festival':good=bool(res) and all(expected in x['title'] and 'festival' in x['title'].casefold() for x in res)
 elif kind=='year_celebration':good=bool(res) and all(expected in x['title'] and '/events/' in x['url'] for x in res)
 elif kind=='gov_catalog':good=len(res)>=2 and all(urlsplit(x['url']).netloc=='www.gov.uk' for x in res)
 elif kind=='series':good=len(res)>=2 and all(expected in x['title'].casefold() for x in res)
 elif kind=='fact_unknown':return 'UNVERIFIED_FACT_NEEDS_SOURCE_EVIDENCE'
 else:raise ValueError('BAD_PROBE:'+kind)
 return 'EXPECTED_RETRIEVAL_BEHAVIOUR' if good else 'POTENTIAL_RETRIEVAL_ERROR'

def page_signals(conn,rows,spec):
 ret=[]
 for result in rows[:3]:
  page=conn.execute('''SELECT p.body,p.fetched_at,p.title,p.source_id,s.display_mode FROM pages p JOIN sources s USING(source_id) WHERE p.url=? AND p.indexed=1 AND s.approved=1 AND s.enabled=1''',(result['url'],)).fetchone()
  if page is None:raise ValueError('MATCH_NOT_IN_APPROVED_INDEX:'+result['url'])
  # Do not copy or publish publisher body text from metadata-only sources.
  body=(page['body'] or '').casefold()
  anchors=spec.get('terms',[])
  # Keyword match is merely a signal of matching text, never a factual correctness proof.
  hits=sum(bool(re.search(r'(?<!\w)'+re.escape(t)+r'(?!\w)',body)) for t in anchors)
  ret.append({'url':result['url'],'title':page['title'],'fetched_at':page['fetched_at'],'source_id':page['source_id'],
              'display_mode':page['display_mode'],'indexed_body_chars':len(page['body'] or ''),
              'indexed_body_anchor_hits':hits,'indexed_body_anchor_total':len(anchors),
              'evidence_status':'INDEXED_TEXT_SIGNALS_ONLY_NOT_FACT_VERIFIED',
              'publisher_body_exported':False})
 return ret

def evaluate(db_path,prior_path,out_dir,p31,candidate=None):
 if shaf(db_path)!=OWNER_SHA:raise ValueError('OWNER_INDEX_SHA_MISMATCH')
 if shaf(prior_path)!=PRIOR_SHA:raise ValueError('R2P31_REPORT_SHA_MISMATCH')
 prior=json.loads(Path(prior_path).read_text(encoding='utf-8'))
 output=Path(out_dir)
 if output.exists():raise ValueError('OUTPUT_ALREADY_EXISTS')
 with closing(open_ro(db_path)) as db:
  counts=validate_owner(db,prior)
  indexed=p31.load_titles(db)
  if len(indexed)!=120:raise ValueError('OWNER_APPROVED_COUNT_MISMATCH')
  # Verify that the exact R2-P31 36 baseline results still reproduce.
  for previous in prior['questions']:
   actual,status,spec=p31.rank(previous['query'],indexed)
   if [x['url'] for x in actual] != [x['url'] for x in previous['results']] or status!=previous['status']:
    raise ValueError('PRIOR_RANKING_CHANGED:'+previous['id'])
  probes=[]
  for i,probe in enumerate(PROBES+HELDOUT,1):
   group,q,kind,expect=probe
   baseline_results,baseline_status,_=p31.rank(q,indexed)
   results,status,spec=(candidate.rank(q,indexed) if candidate else p31.rank(q,indexed))
   judgement=classify(probe,results)
   signals=page_signals(db,results,spec)
   probes.append({'id':f'p32_{i:02d}','group':group,'question':q,'expectation_kind':kind,'expectation':expect,
                  'probe_partition':'development' if i<=len(PROBES) else 'post_development_holdout',
                  'retrieval_audit':judgement,'ranker_status':status,'intent_kind':spec['kind'],
                  'returned_results':results,'baseline_results':baseline_results,'baseline_status':baseline_status,
                  'evidence_signals':signals,'fact_verified':False})
  # For the 36 original owner queries, report content-signal check on first result.
  old=[]
  for p in prior['questions']:
   res,status,spec=(candidate.rank(p['query'],indexed) if candidate else p31.rank(p['query'],indexed))
   old.append({'id':p['id'],'question':p['query'],'retrieved_results':len(res),'first':res[0]['url'] if res else None,
               'prior_first':p['results'][0]['url'] if p['results'] else None,
               'evidence_signals':page_signals(db,res,spec)[:1], 'fact_verified':False})
  try:
   integrity=db.execute('PRAGMA quick_check').fetchone()[0]
  except sqlite3.DatabaseError as e:raise ValueError('READ_ONLY_INTEGRITY_CHECK_FAILED') from e
  if integrity!='ok':raise ValueError('OWNER_INDEX_INTEGRITY_FAILED:'+integrity)
 if shaf(db_path)!=OWNER_SHA:raise ValueError('OWNER_INDEX_CHANGED_DURING_AUDIT')
 counts_by_status=dict(collections.Counter(p['retrieval_audit'] for p in probes))
 baseline_by_status=dict(collections.Counter(classify((p['group'],p['question'],p['expectation_kind'],p['expectation']),p['baseline_results']) for p in probes))
 heldout_counts=dict(collections.Counter(p['retrieval_audit'] for p in probes if p['probe_partition']=='post_development_holdout'))
 development_counts=dict(collections.Counter(p['retrieval_audit'] for p in probes if p['probe_partition']=='development'))
 old_changes=[{'question':v['question'],'before':v['prior_first'],'candidate':v['first']} for v in old if v['first']!=v['prior_first']]
 dynamic_regressions=[x['question'] for x in old if x['prior_first'] is None and x['first'] is not None]
 if dynamic_regressions:raise ValueError('PRIOR_WITHHELD_NOW_RESULTS:'+str(dynamic_regressions))
 failures=[{'id':p['id'],'query':p['question'],'expected':p['expectation'],'actual':[r['title'] for r in p['returned_results']]} for p in probes if p['retrieval_audit']=='POTENTIAL_RETRIEVAL_ERROR']
 report={'version':VERSION,'status':'READ_ONLY_ADVERSARIAL_DIAGNOSTIC_COMPLETE_NOT_DEPLOYED',
         'owner_index_sha256_before_after':OWNER_SHA,'prior_owner_report_sha256':PRIOR_SHA,
         'verified_index':counts,'old_queries_reproduced':36,'new_probe_count':len(probes),
         'diagnostic_counts':counts_by_status,'development_diagnostic_counts':development_counts,
         'heldout_diagnostic_counts':heldout_counts,'heldout_questions':len(HELDOUT),
         'baseline_diagnostic_counts':baseline_by_status,
         'prior_36_candidate_first_changes':old_changes,'potential_retrieval_errors':failures,
         'factual_answers_verified':0,'no_content_export':True,'no_network_calls':True,'no_paid_search_apis':True,
         'original_db_writes':0,'production_integration':'HOLD_PENDING_INDEPENDENT_EVIDENCE_AND_RECALL_REPAIR',
         'probes':probes,'old_evidence':old,
         'limits':['Matching URL/title and indexed body keywords is not source-grounded natural-language answer verification.',
                  'Evidence signals come from locally held web text which may include repeated navigation and stale material.',
                  'No publisher body prose is exported; metadata_only source rights remain intact.',
                  'Expectations in frozen diagnostics are not a proxy for human relevance grades.',
                  'Some questions require live/structured data not present in a research corpus.',
                  'All probes run on one 120-page corpus; not web-scale generalisation.']}
 output.mkdir(parents=True)
 (output/'r2p32_adversarial_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 styles='body{font:15px/1.5 system-ui;max-width:1250px;margin:30px auto;padding:0 18px;color:#16283d}table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid #ddd;padding:8px;vertical-align:top;text-align:left}small{color:#53657a}.err{font-weight:bold;color:#9b2515}.ok{color:#087345}code{font-size:12px;overflow-wrap:anywhere}'
 parts=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Pulse Search R2-P32 Evidence + Adversarial</title><style>'+styles+'</style>',
        '<h1>Pulse Search R2-P32 · Evidence and adversarial test</h1>',
        '<p><b>READ-ONLY DIAGNOSTIC — NOT PRODUCTION.</b> Indexed 120 pages, 7 sources; 36 original questions reproduced; '+str(len(probes))+' new questions. No new website calls and no publisher body reproduction.</p>',
        '<p><b>Potential retrieval errors: '+str(len(failures))+'</b> · Factual answers independently verified: 0 · Exact word-only matching is not proof of factual correctness.</p>',
        '<table><thead><tr><th># / group</th><th>Unseen challenge</th><th>Judgement</th><th>Top indexed page</th><th>Indexed-text signal</th></tr></thead><tbody>']
 for p in probes:
  r=p['returned_results'];signals=p['evidence_signals'];sig=signals[0] if signals else None
  status=p['retrieval_audit'];css='err' if status=='POTENTIAL_RETRIEVAL_ERROR' else 'ok' if status=='EXPECTED_RETRIEVAL_BEHAVIOUR' else ''
  title=html.escape(r[0]['title']) if r else 'No returned page'
  href='<a href="'+html.escape(r[0]['url'],quote=True)+'" target="_blank" rel="noopener noreferrer">'+title+'</a>' if r else title
  support=(f"{sig['indexed_body_anchor_hits']}/{sig['indexed_body_anchor_total']} anchor terms in indexed text" if sig else 'No page to inspect')
  parts.append('<tr><td><small>'+html.escape(p['id'])+' · '+html.escape(p['group'])+'</small></td><td>'+html.escape(p['question'])+'</td><td class="'+css+'">'+html.escape(status)+'</td><td>'+href+'</td><td><small>'+html.escape(support)+'</small></td></tr>')
 parts.append('</tbody></table><p><b>Interpretation:</b> a red result is a potential retrieval defect; “fact needs evidence” is an intentionally ungraded factual claim. This file never supplies unverified answers and must not be used to deploy a ranker. All publisher body text remains in the existing local SQLite index, not in this report.</p></html>')
 (output/'r2p32_adversarial_review.html').write_text('\n'.join(parts),encoding='utf-8')
 return report

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--owner-index',required=True)
 ap.add_argument('--prior-report',required=True)
 ap.add_argument('--out',required=True)
 args=ap.parse_args()
 try:
  import pulse_search_r2p31 as p31
  report=evaluate(args.owner_index,args.prior_report,args.out,p31)
  print(json.dumps({k:report[k] for k in ['status','old_queries_reproduced','new_probe_count','baseline_diagnostic_counts','development_diagnostic_counts','heldout_diagnostic_counts','factual_answers_verified','no_network_calls','original_db_writes','production_integration']},indent=2))
  print('REPORT='+str(Path(args.out)/'r2p32_adversarial_report.json'))
  print('HTML='+str(Path(args.out)/'r2p32_adversarial_review.html'))
  return 0
 except (ValueError,KeyError,TypeError,AssertionError,OSError,sqlite3.DatabaseError) as e:
  print('HOLD_R2P32_INTEGRITY:'+str(e),file=sys.stderr)
  return 2
if __name__=='__main__':raise SystemExit(main())
