#!/usr/bin/env python3
"""Small, fully offline corpus-derived distributional semantic similarity.

Co-occurrence context vectors: context means nearby words IN the accepted index,
not facts, world knowledge, contextual language-model embeddings or LLM output.
This assists retrieval where there is some indexed semantic bridge; it cannot
infer unseen synonyms or verify event facts. No IO/network or model downloads.
"""
from __future__ import annotations
from collections import Counter,defaultdict
import math

def cos(a,b):
 if not a or not b:return 0.0
 inter=sum(v*b.get(k,0) for k,v in a.items())
 norm=math.sqrt(sum(v*v for v in a.values())*sum(v*v for v in b.values()))
 return inter/norm if norm else 0.0

class CorpusContext:
 def __init__(self,records,df):
  self.df=df;self.n=len(records)
  self.word_context=defaultdict(Counter)
  for r in records:
   # Document-structure cap prevents boilerplate-heavy origins overwhelming
   # every other source. Only previously approved indexed texts are consumed.
   doc=(r['title_tokens']*3+r['path_tokens']+r['body_tokens'][:700])
   for i,t in enumerate(doc):
    if self.df[t]>max(4, self.n*.7):continue
    for j in range(max(0,i-4),min(len(doc),i+5)):
     if i==j:continue
     neighbor=doc[j]
     if neighbor==t or self.df[neighbor]>max(4,self.n*.65):continue
     # Only a few adjacent context words contribute, not all document words.
     self.word_context[t][neighbor]+=1/abs(j-i)
  # Downweight ubiquitous source boilerplate and keep only informative
  # context features. This is unsupervised statistical similarity.
  for t,c in self.word_context.items():
   for k in list(c):
    c[k]*=math.log(1+(self.n-self.df[k]+.5)/(self.df[k]+.5))
  self.doc_vectors=[self.compose(r['title_tokens']*2+r['path_tokens']) for r in records]

 def compose(self,terms):
  out=Counter();n=0
  for t in terms:
   v=self.word_context.get(t)
   if not v:continue
   for k,x in v.items():out[k]+=x
   n+=1
  if n:out=Counter({k:v/n for k,v in out.items()})
  return out

 def query_embedding(self,terms):return self.compose(terms)
 def similarity(self,qvec,idx):return cos(qvec,self.doc_vectors[idx])
