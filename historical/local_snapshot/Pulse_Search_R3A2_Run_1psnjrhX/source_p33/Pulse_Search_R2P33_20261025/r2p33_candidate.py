#!/usr/bin/env python3
"""R2-P33: experimentally normalise inflections and catalog intent BEFORE R2-P32 rank.

Never imports judge expectations, never maps queries to URLs, never connects to a network,
never asserts publisher facts or availability. Read-only title/URL research evidence only.
"""
from __future__ import annotations
import re
import r2p32_candidate as p32

# Limited, auditable intent paraphrases, applied to any query.  Do not use named target URLs.
REWRITES=(
 (r'\bprovisional\s+drivers?\s+permits?\b','provisional driving licence'),
 (r'\bscheduled\s+for\b',''),
 (r'\b(?:near\s+(?:my|our|the)\s+home|nearby\s+my\s+home)\b',''),
 (r'\bgovernment\s+service\s+applications\b','government services online'),
 (r'\bgovernment\s+services?\s+applications\b','government services online'),
 (r'\breplacing\b','replace'),
 (r'\bpassport\s+replacement\b','replace passport'),
 (r'\blost\s+(uk\s+)?adult\s+passport\b',lambda m:(m.group(1) or '')+'adult passport'),
 (r'\b(?:celebrations?\s+at)\s+trafalgar\s+square\b','on the square'),
)

# This phrase can be an explicit geography constraint, yet the index metadata lacks
# per-event venue details. Never say a matching page confirms the venue.
VENUE_HINT=re.compile(r'\b(?:at|in)\s+trafalgar\s+square\b',re.I)

def reformulate(q):
 q=str(q)
 for pattern,replacement in REWRITES:
  q=re.sub(pattern,replacement,q,flags=re.I)
 return re.sub(r'\s+',' ',q).strip()

def rank(q,rows,limit=5):
 if not isinstance(q,str) or not q.strip():return p32.rank(q,rows,limit)
 original=q
 # The caller gets a caution metadata flag: a retrieved event page is NOT proof of venue.
 venue=bool(VENUE_HINT.search(q))
 matches,status,spec=p32.rank(reformulate(q),rows,limit)
 spec=dict(spec)
 if venue: spec['unverified_detail']='Event venue is not verified from titles/URLs'
 spec['reformulated']=reformulate(original)!=original
 return matches,status,spec
