"""R3-A2 real offline dense-vs-hybrid comparison, no live access or factual answers.
Hard date/geography/exclusion gates are inherited from pinned R2-P35 code.
No query->URL or per-benchmark routing; semantic inference is actual BGE vectors.
"""
import math
from hybrid_core import HybridIndex, parse, important, tokens

def dot(a,b):return sum(float(x)*float(y) for x,y in zip(a,b))

class DenseConstrainedIndex:
 def __init__(self,rows,encoder):
  self.base=HybridIndex(rows)
  self.encoder=encoder
  self.doc_vectors=encoder.encode([r['title'] for r in self.base.rows])
  if len(self.doc_vectors)!=len(rows) or any(len(x)!=384 for x in self.doc_vectors):
   raise ValueError('HOLD_DENSE_MODEL_OUTPUT_INVALID')
 def search(self,q,limit=10):
  it=parse(q)
  if it.kind=='empty':return {'query':q,'status':'WITHHELD_EMPTY_QUERY','results':[]}
  if it.kind=='dynamic':return {'query':q,'status':'WITHHELD_REQUIRES_LIVE_SOURCE','results':[]}
  if it.conflict:return {'query':q,'status':'WITHHELD_CONFLICTING_GEOGRAPHY','results':[]}
  if it.contradiction:return {'query':q,'status':'WITHHELD_CONTRADICTORY_EXCLUSION','results':[]}
  qvec=self.encoder.encode([q])[0]
  scored=[]
  for i,r in enumerate(self.base.rows):
   if not self.base._accept(r,it):continue
   if it.kind=='gov_catalog' and r['origin']!='www.gov.uk':continue
   if it.kind=='series':
    # Series must share the distinct subject, not simply generic event words.
    if len(set(it.terms)&set(r['title_tokens']+r['path_tokens']))<max(1,len(set(it.terms))):continue
   bm=self.base._bm25(it.terms,i)
   dense=dot(qvec,self.doc_vectors[i])
   if not math.isfinite(dense):raise ValueError('HOLD_NONFINITE_DENSE_SIMILARITY')
   # Do not infer statistical confidence from similarity. This low cutoff is
   # purely a candidate admission heuristic pending independent human labels.
   if it.kind=='subject' and dense<0.45 and bm<0.1:continue
   if it.kind in ('catalog','series') and r['origin']!='www.london.gov.uk':continue
   if it.kind=='gov_catalog' and r['origin']!='www.gov.uk':continue
   # Lexical and contextual scores retained as separately visible signals.
   score=5.0*dense + 0.8*bm
   scored.append((score,dense,bm,r))
  scored.sort(key=lambda x:(-x[0],-x[1],x[3]['title'].casefold(),x[3]['url']))
  found=[]
  for score,dense,bm,r in scored[:limit]:
   found.append({'title':r['title'],'url':r['url'],'score':round(score,5),
    'semantic_cosine':round(dense,5),'bm25_signal':round(bm,5),
    'confidence':'NOT_CALIBRATED_METADATA_RELEVANCE_ONLY'})
  status='WITHHELD_NO_GROUNDED_INDEX_RESULT' if not found else ('SOURCE_LINK_ONLY_FACT_UNVERIFIED' if it.requires_facts else 'RETRIEVAL_CANDIDATES_UNVERIFIED')
  return {'query':q,'status':status,'results':found}
