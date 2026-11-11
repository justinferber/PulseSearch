#!/usr/bin/env python3
"""R2-P32 experimental intent reformulation and exclusion-aware wrapper.

This is a research candidate, not an accepted or deployed search engine.
No URL lookups, domain overrides, current facts, live signals, or network access.
"""
from __future__ import annotations
import re
from urllib.parse import urlsplit
import pulse_search_r2p31 as p31

# Generic language differences; source-aware ranking itself is delegated unchanged.
REWRITES=(
 (r'\btesting\b','tests'),
 (r'\brenewal\b','renew'),
 (r'\bregistering\b','register'),
 (r'\bvoter\b','vote'),
 (r'\blearner\s+driver\s+licen[cs]e\b','provisional driving licence'),
 (r'\bexplain(?:ing)?\b',''),
 (r'\bguide\b',''),
 (r'\bspecification\b',''),
 (r'\bexplanation\b',''),
 (r'\binstructions\b',''),
 (r'\bsubmit\b',''),
 (r'\b(historical\s+editions|previous\s+editions|past\s+editions)\b','over the years'),
 (r'\bwhat\s+was\b',''),
 (r'\bwas\b',''),
 (r'\brun\s+by\b',''),
 (r'\bneed\s+to\s+do\s+to\b',''),
)
EXCLUDE=re.compile(r'\b(?:excluding|except(?:\s+for)?|but\s+not|not\s+including)\b\s*(.+)$',re.I)
ONLY_IN=re.compile(r'\bonly\s+in\s+([\w-]+(?:\s+[\w-]+)?)\b',re.I)
FACT_CHECK=re.compile(r'\b(?:confirmed\s+free\s+entry|have\s+free\s+entry|were\s+cancelled|are\s+cancelled|have\s+sold\s+out|ticket\s+availability)\b',re.I)


def clean(q):
 q=str(q)
 # Catalog intent tokens must survive; source publisher GOV.UK is a trusted URL hint in a query.
 q=re.sub(r'\bgov\.uk\b','government',q,flags=re.I)
 for src,repl in REWRITES:q=re.sub(src,repl,q,flags=re.I)
 q=re.sub(r'\bpast\s+(.{1,80}?)\s+editions\b',r'history of \1',q,flags=re.I)
 q=re.sub(r'\s+',' ',q).strip()
 return q

def rank(q,rows,limit=5):
 if not isinstance(q,str) or not q.strip():return [],'WITHHELD_INVALID_QUERY',{'kind':'invalid','year':None,'terms':[]}
 # No publisher page can justify live claims just because it has an event title.
 if FACT_CHECK.search(q):return [],'WITHHELD_UNVERIFIED_FACT_QUALIFIER',{'kind':'factual','year':p31.year(q),'terms':[]}
 x=ONLY_IN.search(q)
 if x and re.search(r'\blondon\b',q,re.I) and x.group(1).casefold().split()[0]!='london':
  return [],'WITHHELD_CONTRADICTORY_GEOGRAPHY',{'kind':'geo_conflict','year':p31.year(q),'terms':[]}
 exclusion=EXCLUDE.search(q)
 expr=exclusion.group(1) if exclusion else ''
 source=q[:exclusion.start()] if exclusion else q
 matched,status,spec=p31.rank(clean(source),rows,limit=max(limit,30) if exclusion else limit)
 if exclusion:
  discard=set(p31.normstem(w) for w in p31.words(p31.normalize(expr)))
  discard-={'the','a','an','on','in','at','of','and','festival','festivals','event','events','only','please','show','me'}
  if discard:
   matched=[v for v in matched if not discard.issubset(p31.record_meta(v)['title_terms']|p31.record_meta(v)['path_terms'])]
  matched=matched[:limit]
  status='MATCHES_UNVERIFIED' if matched else 'WITHHELD_NO_SUPPORTED_INDEX_MATCH'
 return matched,status,spec
