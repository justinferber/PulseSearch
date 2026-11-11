#!/usr/bin/env python3
"""Pulse Search R2-P35 hybrid *research* pipeline.

Approved indexed pages only. No live network, no writes, no free-form fact answers.
Semantic tier: corpus-derived LSA when numpy is installed, otherwise explicit
subword TF-IDF fallback (NOT a contextual language-model embedding).
This module never imports test expectations or maps user queries to URLs.
"""
from __future__ import annotations
import collections, hashlib, math, re, unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit
from semantic_context import CorpusContext

STOP=set('historical previous earlier past editions edition years year except apply an a the and or to by with from about what which where who when how why can could do does did is are was were be been will would i we my our me you your of in on at for as it this that those these any some please tell show find getting get into via through over during between have has had into they their any give help information info instructions guide explaining introduction beginning started start work services service application available events event city hall'.split())
WEAK=set('online guide help information details instruction instructions how get getting would like near around happening happened planned scheduled held about tell explain explanation uk united kingdom england british Britain london'.casefold().split())
YEAR=re.compile(r'(?<!\d)(20\d\d)(?!\d)')
DYNAMIC=re.compile(r'\b(?:weather|rain(?:ing)?|snow(?:ing)?|forecast|tomorrow|open\s+now|opening\s+hours|in\s+stock|stock\s+(?:now|today)|available\s+right\s+now|currently\s+available)\b',re.I)
TIME_FACT=re.compile(r'\b(?:what\s+time|starting\s+time|opening\s+time|exact\s+time|at\s+what\s+time|how\s+much|price|cost|fee|ticket(?:s)?|sold\s+out|cancelled|canceled|free\s+entry|free\s+to\s+attend|wheelchair|step.free|accessible|attendance|how\s+many\s+people|what\s+steps|source.confirmed\s+event\s+date|require\s+paid)\b',re.I)
SERIES=re.compile(r'\b(?:past|historical|previous|earlier)\b.*\b(?:years|editions|events|festivals)\b|\b(?:history|editions|over\s+the\s+years|through\s+the\s+years|previous\s+years)\b',re.I)
CATALOG=re.compile(r'\b(?:events?|festivals?|celebrations?)\b',re.I)
EXCLUDE=re.compile(r'\b(?:excluding|except(?:\s+for)?|without|apart\s+from|but\s+not|not\s+including)\b\s+([^?,;]+)',re.I)
PLACES={'london','manchester','edinburgh','berlin','paris','liverpool','bristol','newbury','oxford','sydney','york','birmingham','glasgow'}
# Transparent broad semantic lexicon; NOT per-query URL targets. Could eventually
# be replaced by a private, licensed on-device sentence-embedding model.
FAMILIES=(
 ('doctor','gp','physician','practitioner'),
 ('enrol','enroll','register','registration','sign-up','signup'),
 ('vote','voting','voter','electoral'),
 ('test','testing','screening','screen'),
 ('blood','bloods'),
 ('driving','driver','drivers'),
 ('licence','license','permit'),
 ('provisional','learner','temporary'),
 ('javascript','js','ecmascript'),
 ('programming','coding','code','script'),
 ('renew','renewal','replace','replacement'),
 ('passport','passports'),
 ('government','gov'),
 ('celebration','celebrations','festival','festivals'),
 ('years','year','editions','edition'),
 ('admission','entry'),
)
LEX={v:k for family in FAMILIES for k,v in [(family[0],x) for x in family]}
# Prevent the coarse 'celebration/festival' alias from falsely claiming all
# celebrations are festivals in specific-festival filters.
DOMAIN_FACETS={'festival','festivals','celebration','celebrations'}

def tokens(text):
 s=unicodedata.normalize('NFKC',str(text)).casefold().replace('’',"'")
 s=re.sub(r"\b([a-z]+)'s\b",r'\1s',s)
 return re.findall(r'[a-z0-9]+',s)

def root(t):
 if t in LEX:return LEX[t]
 if len(t)>5 and t.endswith('ies'):return t[:-3]+'y'
 if len(t)>6 and t.endswith('ing') and t[:-3] not in ('str','pr'):return t[:-3]
 if len(t)>5 and t.endswith('ed'):return t[:-2]
 if len(t)>4 and t.endswith('s') and not t.endswith(('ss','us')):return t[:-1]
 return t

def important(text):
 return [root(t) for t in tokens(text) if t not in STOP and t not in WEAK and not YEAR.fullmatch(t)]

def chargrams(text):
 # normalized character-3,4,5 grams; skips whitespace punctuation in token
 # boundaries. Lexical morphology support, NOT validated sentence semantics.
 out=collections.Counter()
 for token in tokens(text):
  if len(token)<4:continue
  s='^'+token+'$'
  for n in (3,4,5):out.update(s[i:i+n] for i in range(len(s)-n+1))
 return out

def cosine(a,b):
 common=sum(v*b.get(k,0) for k,v in a.items())
 norm=math.sqrt(sum(v*v for v in a.values())*sum(v*v for v in b.values()))
 return common/norm if norm else 0.0

@dataclass
class Intent:
 text:str
 kind:str
 terms:list[str]
 year:str|None
 places:set[str]
 excluded:list[str]
 facet:str|None
 requires_facts:bool
 conflict:bool
 contradiction:bool=False

def parse(q):
 if not isinstance(q,str) or not q.strip():return Intent(str(q),'empty',[],None,set(),[],None,False,False)
 t=tokens(q); year=(YEAR.findall(q) or [None])[-1]
 places={p for p in PLACES if p in t}
 conflict=len(places)>1 and 'london' in places and ('only' in t or 'but' in t or 'in' in t)
 exclusions=[m.group(1).strip() for m in EXCLUDE.finditer(q)]
 main_clause=EXCLUDE.split(q,maxsplit=1)[0] if exclusions else q
 contradictory=bool(exclusions and (set(important(main_clause)) & {x for part in exclusions for x in important(part)})) and not CATALOG.search(main_clause)
 exclusion_tokens={x for phrase in exclusions for x in important(phrase)}
 ts=[x for x in important(q) if x not in exclusion_tokens]
 # Venue entity is a constraint needing source verification, not the event name.
 venue = re.search(r'\b(?:at|in)\s+([a-z\s]+?\s+square)\b', q, re.I)
 if venue and len([x for x in ts if x not in important(venue.group(1))])>=1:
  ts=[x for x in ts if x not in important(venue.group(1))]
 fact=bool(TIME_FACT.search(q)); dyn=bool(DYNAMIC.search(q))
 if dyn:kind='dynamic'
 elif SERIES.search(q):kind='series'
 elif CATALOG.search(q) and ('london' in places or bool(year)) and (re.search(r'\b(?:which|show|find|list|what|during|in|around)\b',q,re.I)) and (len([x for x in ts if x not in ('celebration','festival','year')])<=1):kind='catalog'
 elif 'government' in ts and (re.search(r'\b(?:online|service|application|applications)\b',q,re.I)):kind='gov_catalog'
 else:kind='subject'
 facet='festival' if re.search(r'\bfestivals?\b',q,re.I) else ('celebration' if re.search(r'\bcelebrations?\b',q,re.I) else None)
 # Query geography/year are constraints, not generic content terms.
 ts=[x for x in ts if x not in PLACES and x not in ('year','celebration','festival') or (kind=='subject' and x in ('celebration','festival'))]
 ts=list(dict.fromkeys(ts))
 return Intent(q,kind,ts,year,places,exclusions,facet,fact,conflict,contradictory)

class HybridIndex:
 def __init__(self,rows, *, semantic_model=None):
  self.rows=[]
  self.model=semantic_model
  for r in rows:
   url=r['url'];title=r['title'];path=urlsplit(url).path
   body=str(r.get('body') or '')
   # index body-only memory. Research outputs NEVER serialize publisher prose.
   tt=important(title);pp=important(path.replace('-',' '));bb=important(body[:28000]);
   self.rows.append({'url':url,'title':title,'path':path,'origin':urlsplit(url).netloc.lower(),
        'year':(YEAR.findall(title) or [None])[-1],'title_tokens':tt,'path_tokens':pp,
        'body_tokens':bb,'ngrams':chargrams(title+' '+path),'body':body,
        'display_mode':r.get('display_mode','metadata_only'), 'fetched_at':r.get('fetched_at')})
  self.n=len(self.rows)
  self.df=collections.Counter()
  for r in self.rows:self.df.update(set(r['title_tokens']+r['path_tokens']+r['body_tokens']))
  self.avgdl=max(1,sum(len(r['title_tokens'])*3+len(r['path_tokens'])+len(r['body_tokens']) for r in self.rows)/max(self.n,1))
  self.semantic_context=CorpusContext(self.rows,self.df)
  self.doc_tf=[]
  for r in self.rows:
   tf=collections.Counter(r['title_tokens']*4+r['path_tokens']*2+r['body_tokens']);self.doc_tf.append(tf)
  self.capabilities={'lexical':'BM25F-inspired term scoring, title/path boosted',
       'similarity':'offline corpus-derived co-occurrence vectors + subword cosine (NOT pretrained contextual embeddings)',
       'dense_model':'DISABLED_UNLESS_LOCAL_PINNED_BACKEND_PROVIDED',
       'factual_answers':'NONE_VERIFIED_METADATA_ONLY',
       'calibration':'HEURISTIC_ABSTENTION_NOT_STATISTICALLY_CALIBRATED'}
  if self.model is not None:
   # Pluggable local-only model must be caller-provided; never network download.
   self.doc_embeddings=self.model.encode([r['title'] for r in self.rows])
   self.capabilities['dense_model']='LOCAL_INJECTED_MODEL_ACTIVE'

 def _bm25(self,terms,idx):
  tf=self.doc_tf[idx];d=self.rows[idx];length=max(1,sum(tf.values()))
  score=0.
  for t in set(terms):
   f=tf.get(t,0)
   if not f:continue
   idf=math.log(1+(self.n-self.df[t]+.5)/(self.df[t]+.5))
   part=f*(1.2+1)/(f+1.2*(.25+.75*length/self.avgdl))
   score+=idf*part
  return score

 def _exclusion(self,r,intent):
  for phrase in intent.excluded:
   excluded=important(phrase)
   if not excluded:continue
   if set(excluded).issubset(set(r['title_tokens']+r['path_tokens'])):return True
   # Exact excluded event name without a generic `festival` after query phrases
   critical=[x for x in excluded if x not in ('festival','celebration','year')]
   if len(critical)>=1 and all(x in r['title_tokens'] for x in critical):return True
  return False

 def _accept(self,r,intent):
  if intent.year and r['year']!=intent.year:return False
  if intent.places:
   if r['origin']=='www.london.gov.uk' and any(x!='london' for x in intent.places):return False
   if 'london' in intent.places and r['origin']!='www.london.gov.uk' and intent.kind in ('catalog','series'):return False
   if not 'london' in intent.places and r['origin']=='www.london.gov.uk':return False
  if self._exclusion(r,intent):return False
  if intent.kind in ('catalog','series'):
   if r['origin']!='www.london.gov.uk' or not r['path'].startswith('/events/'):return False
   if intent.facet=='festival' and not any(x in tokens(r['title']) for x in ('festival','festivals')):return False
  if intent.kind=='gov_catalog' and r['origin']!='www.gov.uk':return False
  return True

 def search(self,q,limit=5):
  it=parse(q)
  if it.kind=='empty':return {'query':q,'status':'WITHHELD_EMPTY_QUERY','intent':it,'results':[]}
  if it.kind=='dynamic':return {'query':q,'status':'WITHHELD_REQUIRES_LIVE_SOURCE','intent':it,'results':[]}
  if it.conflict:return {'query':q,'status':'WITHHELD_CONFLICTING_GEOGRAPHY','intent':it,'results':[]}
  if it.contradiction:return {'query':q,'status':'WITHHELD_CONTRADICTORY_EXCLUSION','intent':it,'results':[]}
  candidate=[];qgrams=chargrams(q)
  q_context=self.semantic_context.query_embedding(it.terms)
  for i,r in enumerate(self.rows):
   if not self._accept(r,it):continue
   b=self._bm25(it.terms,i);sim=cosine(qgrams,r['ngrams']);
   contextual=self.semantic_context.similarity(q_context,i)
   dense=0.
   if self.model is not None:
    dense=float(self.model.cosine(self.model.encode([q])[0],self.doc_embeddings[i]))
   title_matches=len(set(it.terms)&set(r['title_tokens']+r['path_tokens']))
   # Subject questions require subject evidence, not a page matching `London`.
   if it.kind=='subject':
    if it.excluded and set(it.terms).intersection({x for ex in it.excluded for x in important(ex)}) :continue
    if it.terms and title_matches/max(1,len(it.terms))<0.45:continue
    if not title_matches and sim < .40:continue
    if b < .01 and sim < .38:continue
   elif it.kind=='series':
    if title_matches<max(1,len(set(it.terms))):continue
   elif it.kind=='gov_catalog':
    if not any(x in r['title_tokens'] for x in ('apply','renew','register','vote','check','replace')):continue
   # Suppress generic short-name matches: 'New Year's Eve London 2026' should
   # beat other 2026 pages with common words.
   balance=(title_matches/max(1,len(it.terms)))
   score=2.0*b+5.0*sim+12*balance+2.5*contextual+5*dense
   if it.kind=='series' and r['year']:score+=min(2,max(0,int(r['year'])-2020)*.2)
   if 'businesses and residents' in r['title'].lower():score-=3
   if it.kind=='catalog':score+=5
   if it.kind=='gov_catalog':score+=5
   candidate.append((score,-title_matches,r['title'].casefold(),r))
  candidate.sort(key=lambda x:(-x[0],x[1],x[2],x[3]['url']))
  results=[]
  for score,_,_,r in candidate[:limit]:
   # Abstention confidence is a *rule-based label*, NEVER an empirical
   # probability or a claim that page contains the factual answer.
   anchor=len(set(it.terms)&set(r['title_tokens']+r['path_tokens']))
   evidence_count=len(set(it.terms)&set(r['body_tokens']))
   confidence='HIGH_RETRIEVAL_SIGNAL' if anchor>=2 else 'LIMITED_RETRIEVAL_SIGNAL'
   results.append({'title':r['title'],'url':r['url'],'score':round(score,3),
     'confidence_label':confidence,'body_anchor_hits':evidence_count,
     'evidence_body_sha256':hashlib.sha256(r['body'].encode('utf-8')).hexdigest(),
     'display_mode':r['display_mode'],'fetched_at':r['fetched_at']})
  status=('WITHHELD_NO_GROUNDED_INDEX_RESULT' if not results else 'SOURCE_LINK_ONLY_FACT_UNVERIFIED' if it.requires_facts else 'RETRIEVAL_CANDIDATES_UNVERIFIED')
  return {'query':q,'status':status,'intent':it,'results':results}
