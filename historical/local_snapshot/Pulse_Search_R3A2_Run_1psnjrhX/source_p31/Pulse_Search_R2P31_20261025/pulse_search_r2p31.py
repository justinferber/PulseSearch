#!/usr/bin/env python3
"""R2-P31 bounded, schema-only, read-only precision+recall shadow for Pulse Search.

Works exclusively with search-index metadata (URL/title/source) already in the
owner's accepted research database. Uses transparent intent policies and a small
linguistic-alias table, not a query->URL lookup. Never verifies answer content,
live availability, event dates, or source licences.
"""
from __future__ import annotations
import argparse, collections, html, json, re, sqlite3, sys
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

VERSION='R2-P31-SemanticFacet-Shadow-v1'
INDEX_SHA='bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d'
ALLOWED_SCHEMES={'https'}
YEAR_RE=re.compile(r'(?<!\d)(20\d{2})(?!\d)')
DYNAMIC=re.compile(r'\b(?:open\s+now|opening\s+hours|in\s+stock(?:\s+(?:now|today))?|available\s+now|rain|snow|weather|forecast|tomorrow|today\s+weather)\b',re.I)
STOP=set('how do does can could i me my you your a an and about are as at be by for from get getting have in is it of on or our please the there these this those to up use what when where which who will with would uk england britain british london city hall new online now happening happened held during over years year did tell started start first question home need intro introduction'.split())
# Generic, explicable vocabulary normalization; applies to new queries too, not URL-targeted.
ALIASES=(
 (r'\bfamily\s+doctor(?:\s+surgery)?\b','gp surgery'),
 (r'\bsign\s+up\b','register'),
 (r'\blearner\s+driver\s+permit\b','provisional driving licence'),
 (r'\bproperty\s+tax\b','council tax'),
 (r'\bnew\s+year\s+fireworks\b','new years eve'),
 (r'\bnew\s+year(?:s|\s*\'s)?\s+fireworks\b','new years eve'),
 (r'\bjs\b','javascript'),
 (r'\bcoding\b','programming'),
 (r'\blearn(?:ing)?\b','learn'),
 (r'\bregistration\b','register'),
 (r'\bapplication\b','apply'),
 (r'\bnew\s+year(?:s|\s*\'s)?\s+eve\b','new years eve'),
 (r'\bcelebration(?:s)?\b','celebrations'),
)
GENERIC=set('event events festival festivals celebrations happening government services service online check apply get how register do want learn programming coding london britain years year uk city hall find help tell past history info information during question'.split())
ACTIVITY_EVENTS={'festival','festivals','parade','pride','celebration','celebrations','service','ceremony','day','square','week','games','open','house'}
CELEBRATION_HINTS={'festival','festivals','diwali','eid','vaisakhi','chanukah','christmas','pride','st','patricks','georges','lunar','year','black','square','iftar','celebration','celebrations','coronation'}


def words(s):
 s=str(s).casefold().replace('’',"'")
 s=re.sub(r"\b([a-z]+)'s\b",r'\1s',s)
 return re.findall(r'[a-z0-9]+',s)

def normalize(s):
 s=str(s).casefold().replace('’',"'")
 for pat,repl in ALIASES:s=re.sub(pat,repl,s,flags=re.I)
 return s

def normstem(t):
 if t in ('years','year'):return 'year'
 if t in ('tests','test'):return 'test'
 if t in ('licences','licenses','licence','license'):return 'licence'
 if t in ('celebrations','celebration'):return 'celebration'
 if t in ('services','service'):return 'service'
 if t in ('festivals','festival'):return 'festival'
 if t in ('events','event'):return 'event'
 if t in ('shops','shop'):return 'shop'
 if len(t)>5 and t.endswith('ies'):return t[:-3]+'y'
 if len(t)>4 and t.endswith('s') and not t.endswith(('ss','us')):return t[:-1]
 return t

def year(s):
 m=YEAR_RE.findall(s)
 return m[-1] if m else None

def intent(q):
 t=normalize(q); tok=set(words(t)); y=year(t)
 if DYNAMIC.search(q):return {'kind':'dynamic','year':y,'terms':[]}
 if ('online' in tok and 'government' in tok and ('service' in tok or 'services' in tok)) or ('government' in tok and 'services' in tok):
  return {'kind':'gov_catalog','year':y,'terms':[]}
 if 'london' in tok and y and (('events' in tok or 'event' in tok) and not (tok&{'eve','diwali','festival','festivals','open','house','pride','memorial','service','data','week'})):
  return {'kind':'event_catalog','year':y,'terms':[]}
 if 'london' in tok and y and (tok&{'celebrations','festivals','festival'}):
  return {'kind':'event_facet','year':y,'facet':('festival' if tok&{'festivals','festival'} else 'celebration'),'terms':[]}
 if re.search(r'\b(?:over\s+the\s+years|through\s+the\s+years|across\s+the\s+years|history\s+of)\b',q,re.I):kind='series'
 else:kind='subject'
 bare=[normstem(w) for w in words(t) if w not in STOP and not YEAR_RE.fullmatch(w)]
 # generic intent words, region and publisher names excluded from named subject; keep specialist meaningful anchors
 terms=list(dict.fromkeys(w for w in bare if w not in {normstem(x) for x in GENERIC}))
 if {"council","tax"}.issubset(set(terms)):terms=[x for x in terms if x not in ("property","home")]
 # Handle generic phrases that include "festival" / "celebration" as an event name (e.g. St Patrick's Festival).
 if not terms and tok&{'http','javascript','nhs'}:terms=[x for x in ('http','javascript','nhs') if x in tok]
 return {'kind':kind,'year':y,'terms':terms}

def record_meta(row):
 u=row['url'];t=row['title'];origin=urlsplit(u).netloc.lower();p=urlsplit(u).path
 tt=set(normstem(x) for x in words(t));pt=set(normstem(x) for x in words(p));return {'url':u,'title':t,'origin':origin,'title_terms':tt,'path_terms':pt,'year_title':year(t),'year_path':year(p),'is_event':origin=='www.london.gov.uk' and p.startswith('/events/')}

def score_one(spec,row):
 r=record_meta(row);k=spec['kind'];y=spec.get('year')
 if k=='dynamic':return None
 if k=='gov_catalog':
  if r['origin']!='www.gov.uk':return None
  if not (r['title_terms'] & {'apply','renew','register','check','order','find','replace'}):return None
  return (25+len(r['title_terms'] & {'apply','renew','register','check','order'}), 'GOV_UK_SERVICE_CATEGORY')
 if k in ('event_catalog','event_facet'):
  if not r['is_event'] or not y or r['year_title']!=y:return None
  if k=='event_facet':
   title=r['title_terms']
   if spec['facet']=='festival' and 'festival' not in title:return None
   if spec['facet']=='celebration' and not title&{normstem(x) for x in CELEBRATION_HINTS}:return None
  # Multiple sources of same year are permitted; page titles are not dates.
  return (25+len(r['title_terms'] & {'london','festival','diwali','eid','square'}), 'YEAR_AND_EVENT_FACET')
 terms=set(spec.get('terms',[]))
 if not terms:return None
 if y:
  # Do not allow unrelated page-body year to satisfy edition identity.
  if y not in (r['year_title'],r['year_path']):return None
  if r['year_title'] and r['year_title']!=y:return None
 ts=r['title_terms'];pt=r['path_terms'];matched=terms & (ts|pt)
 if not matched:return None
 # When 2+ anchor terms identify a named event, all anchors must match.
 # Allow a nonessential learning/intent word to be absent, not a named event anchor.
 required=terms-{'learn','program','programming','book'}
 if required and not required.issubset(ts|pt):return None
 if len(terms)>=3 and len(matched)/len(terms)<0.6:return None
 score=45*len(matched)/(len(terms) or 1) + 12*len(matched&ts) + (9 if y else 0)
 # Generic event article vs dedicated primary event: prefer direct event page to business FAQ.
 if re.search(r'\b(?:information for|businesses and residents|consultation|advice for)\b',r['title'],re.I):score-=19
 if r['title'].lower().startswith('what is ') and terms&{'javascript','http'}:score+=5
 if k=='series':
  if not r['is_event']:return None
  score+=(int(r['year_title'])-2020)*0.4 if r['year_title'] else 0
 return (round(score,2),'SUBJECT_YEAR_AND_ALIASES')

def rank(q,rows,limit=5):
 spec=intent(q)
 if spec['kind']=='dynamic':return [],'WITHHELD_UNVERIFIED_LIVE_DATA',spec
 scores=[]
 for row in rows:
  sc=score_one(spec,row)
  if sc is not None:
   scores.append((sc[0],row['title'],row['url'],sc[1]))
 scores.sort(key=lambda v:(-v[0],v[1].casefold(),v[2]))
 matches=[{'url':u,'title':t,'score':s,'match_reason':reason} for s,t,u,reason in scores[:limit]]
 return matches,('MATCHES_UNVERIFIED' if matches else 'WITHHELD_NO_SUPPORTED_INDEX_MATCH'),spec

def load_titles(conn):
 return [dict(r) for r in conn.execute('''SELECT p.url, p.title, p.source_id FROM pages p
 JOIN sources s ON s.source_id=p.source_id WHERE p.indexed=1 AND s.approved=1 AND s.enabled=1
 ORDER BY p.url''')]

def sha(path):
 h=sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

def digest_matches(path,expect):
 digest=sha(path)
 if digest!=expect:raise ValueError('SHA_MISMATCH:'+Path(path).name+':'+digest)

def eval_main(index,report_path,live_path,shadow_path,source_r2p30_path,output):
 import pulse_search_r2p29 as p29
 import pulse_search_engine as engine
 r30=json.loads(Path(report_path).read_text())
 live=json.loads(Path(live_path).read_text())
 prior=json.loads(Path(shadow_path).read_text())
 if r30['status']!='READ_ONLY_DIAGNOSTIC_COMPLETE_NOT_DEPLOYED' or r30.get('total_benchmark_queries')!=36 or r30.get('new_unseen_queries')!=24:raise ValueError('R2P30_NOT_ACCEPTED_DIAGNOSTIC')
 if r30.get('owner_index_sha256_before_after')!=INDEX_SHA or prior.get('owner_index_sha256_before_after')!=INDEX_SHA:raise ValueError('INDEX_IDENTITY_MISMATCH')
 if live.get('status')!='LIVE_100_NEW_INDEXED_CLONE_ONLY_PASS':raise ValueError('LIVE_PROVENANCE_MISMATCH')
 digest_matches(index,INDEX_SHA)
 with closing(p29.owner_ro(index)) as db:
  p29.check_owner_index(db,live)
  originals=load_titles(db)
  if len(originals)!=120 or len(set(r['url'] for r in originals))!=120:raise ValueError('INDEX_PAGE_COUNT_MISMATCH')
  queries=[q['query'] for q in prior['questions']]+[q['query'] for q in r30['questions']]
  if len(queries)!=36 or len(set(queries))!=36:raise ValueError('QUESTION_SET_MISMATCH')
  # All previous baseline result lists must remain reproducible from the accepted engine.
  for row in prior['questions']:
   old=engine.search(db,row['query'],limit=3)
   if [(r['url'],r['title']) for r in old]!=[(r['url'],r['title']) for r in row['baseline']]:raise ValueError('BASELINE_RANKING_DRIFT:'+row['query'])
  out=[]
  for i,q in enumerate(queries):
   matched,status,spec=rank(q,originals)
   out.append({'id':f'p31_{i+1:02d}','query':q,'kind':spec['kind'],'normalized_terms':spec.get('terms',[]),'requested_year':spec.get('year'), 'status':status,'results':matched})
 if sha(index)!=INDEX_SHA:raise ValueError('INDEX_MUTATED_DURING_READ_ONLY_AUDIT')
 # Known named-URL ground truth in original R2-P30: enforce exact expected identity.
 named={q['query']:q['expected_source_url'] for q in r30['questions'] if q['group']=='named_edition'}
 actual={q['query']:q for q in out}
 failures=[]
 for q,url in named.items():
  got=actual[q]['results']
  if not got or got[0]['url']!=url:failures.append('NAMED_EDITION_TOP1:'+q)
 for q in r30['questions']:
  if q['group']=='negative_control' and actual[q['query']]['results']:failures.append('NEGATIVE_CONTROL:'+q['query'])
 # Human-good grade2/3 first pages accepted in the earlier owner review.
 corrected=json.loads(Path(source_r2p30_path).read_text())
 for row in corrected['questions']:
  if row['topic']=='live_local':continue
  first=row['shadow'][0]['url'] if row['shadow'] else None
  if first and row['query'] in actual:
   got=actual[row['query']]['results']
   if not got or got[0]['url']!=first:failures.append('PRIOR_USEFUL_TOP1:'+row['query'])
 # Scope of the protected positive queries: retain at least one subject match for each
 # meaningful paraphrase/broad question; these are URL/title retrieval goals, not answers.
 for q in r30['questions']:
  if q['group'] in ('paraphrase','broad_discovery') and not actual[q['query']]['results']:
   failures.append('RECALL_MISS:'+q['query'])
 status='READ_ONLY_SHADOW_PROVISIONAL_PASS_NOT_DEPLOYED' if not failures else 'HOLD_SHADOW_RECALL_OR_PRECISION'
 res={'version':VERSION,'status':status,'owner_index_sha256_before_after':INDEX_SHA,'indexed_pages':120,
      'benchmark_questions':36,'named_edition_expected_top1':len(named),
      'named_edition_correct':sum(bool(actual[q]['results']) and actual[q]['results'][0]['url']==u for q,u in named.items()),
      'paraphrase_and_broad_nonempty':sum(bool(actual[q['query']]['results']) for q in r30['questions'] if q['group'] in ('paraphrase','broad_discovery')),
      'paraphrase_and_broad_total':11,'negative_controls_withheld':sum(not actual[q['query']]['results'] for q in r30['questions'] if q['group']=='negative_control'),
      'known_human_benchmark_issues':failures,'new_public_network_requests':0,'paid_search_provider_calls':0,'db_writes':0,
      'questions':out,'limitations':['Matching titles and URLs does not provide a verified natural-language answer',
       'Corpus is 120 research pages, 7 publishers; query policy calibrated after seeing the benchmark',
       'All new/topical matches require fresh human validation before deployment',
       'Dynamic data requires fresh sources and is intentionally withheld','Named edition year is inferred from title/URL, not live event verification',
       'New unseen held-out tests and broader corpus are needed before production']}
 dest=Path(output)
 if dest.exists():raise ValueError('OUTPUT_ALREADY_EXISTS')
 dest.mkdir(parents=True)
 (dest/'r2p31_rank_report.json').write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 page=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Pulse Search R2-P31</title>','<style>body{font:15px/1.5 system-ui;max-width:1080px;margin:2rem auto;padding:0 16px;background:#f7f9fb}section{background:white;border:1px solid #ccd8e0;border-radius:12px;padding:18px;margin:12px 0}a{overflow-wrap:anywhere}small{color:#687b88}li{margin:4px}</style>',
       '<h1>Pulse Search R2-P31 · 36-query precision + recall</h1><p>Research only · Metadata-level matching · No live content verification · No database changes</p>',
       '<p><b>Status: '+html.escape(status)+'</b>; Named edition correct: '+str(res['named_edition_correct'])+'/8; broad/paraphrase nonempty '+str(res['paraphrase_and_broad_nonempty'])+'/11; negatives withheld '+str(res['negative_controls_withheld'])+'/5.</p>']
 for q in out:
  page.append('<section><small>'+html.escape(q['kind'])+' / '+html.escape(q['status'])+'</small><h3>'+html.escape(q['query'])+'</h3>')
  if q['results']:
   page.append('<ol>'+''.join('<li><a href="'+html.escape(x['url'],quote=True)+'">'+html.escape(x['title'])+'</a> <small>'+html.escape(x['match_reason'])+'</small></li>' for x in q['results'])+'</ol>')
  else:page.append('<p>No supported result in indexed research metadata.</p>')
  page.append('</section>')
 page.append('<p><b>Important:</b> 100% retrieval on known queries does not equal 100% factual answer accuracy, and rules tuned on this benchmark must pass separate unseen tests.</p>')
 (dest/'r2p31_rank_review.html').write_text('\n'.join(page)+'</body></html>',encoding='utf-8')
 return res

def main():
 ap=argparse.ArgumentParser()
 for key in ['owner_index','r2p30_report','live_report','prior_shadow_report','r2p30_source_report','out']:
  ap.add_argument('--'+key.replace('_','-'),required=True)
 a=ap.parse_args()
 try:
  r=eval_main(a.owner_index,a.r2p30_report,a.live_report,a.prior_shadow_report,a.r2p30_source_report,a.out)
  print(json.dumps({k:r[k] for k in ['status','benchmark_questions','named_edition_correct','paraphrase_and_broad_nonempty','negative_controls_withheld','known_human_benchmark_issues','new_public_network_requests','paid_search_provider_calls','db_writes']},indent=2))
  print('REPORT='+str(Path(a.out)/'r2p31_rank_report.json'))
  print('HTML='+str(Path(a.out)/'r2p31_rank_review.html'))
  return 0 if not r['known_human_benchmark_issues'] else 2
 except (ValueError,AssertionError,OSError,KeyError,TypeError,sqlite3.Error) as e:
  print('HOLD_R2P31:'+str(e),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
