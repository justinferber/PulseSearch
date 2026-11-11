#!/usr/bin/env python3
"""Research-only source evidence signatures and abstention quality controls.
No publisher body text is written into the report. Word occurrences do not prove facts.
"""
import hashlib,re
PATTERNS={
 'clock_like':r'(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)|\b(?:[1-9]|1[0-2])\s?(?:am|pm)\b',
 'currency_like':r'(?:£|GBP\s?)\s?\d[\d,.]*',
 'date_like':r'\b(?:\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d\d|20\d\d-\d\d-\d\d)\b',
 'cancel_like':r'\b(?:cancelled|canceled|postponed|not going ahead)\b',
 'availability_like':r'\b(?:sold out|tickets available|tickets remaining|booking closed)\b',
 'accessibility_like':r'\b(?:wheelchair|step.free|accessible entrance)\b'
}
def evidence_signals(body,display_mode):
 body=body or ''
 return {'body_sha256':hashlib.sha256(body.encode('utf-8')).hexdigest(),
  'body_chars':len(body),
  'signals':{kind:len(list(re.finditer(pattern,body,re.I))) for kind,pattern in PATTERNS.items()},
  'publisher_body_exported':False,
  'factual_claim_verified':False,
  'status':'SOURCE_TEXT_PATTERNS_ONLY_NOT_FACT_VERIFIED',
  'display_mode':display_mode}

class ReliabilityCalibrator:
 """Independent relevance judgments required; below threshold, no probabilities."""
 def __init__(self,grade_pairs=(),min_judgments=50):
  self.pairs=tuple(grade_pairs)
  self.min_judgments=min_judgments
  if self.pairs and any(not (isinstance(q,(int,float)) and 0<=q<=1 and isinstance(label,bool)) for q,label in self.pairs):raise ValueError('INVALID_JUDGMENTS')
  self.status='CALIBRATED_ON_RELEVANCE_JUDGMENTS' if len(self.pairs)>=min_judgments else 'INSUFFICIENT_INDEPENDENT_LABELS_NO_PROBABILITIES'
 def estimate(self,score):
  if self.status!='CALIBRATED_ON_RELEVANCE_JUDGMENTS':return None
  nearest=sorted(self.pairs,key=lambda p:abs(p[0]-score))[:max(15,len(self.pairs)//5)]
  return {'empirical_relevance_rate':round(sum(int(label) for _,label in nearest)/len(nearest),3),
    'neighbors':len(nearest), 'not_factual_answer_probability':True}
