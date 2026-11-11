#!/usr/bin/env python3
"""Optional real semantic encoder: approved local-only weights, never downloads.

R2-P35 owner run intentionally does NOT invoke this without separate approval,
local model/rights audit, explicit SHA manifest, and dependency availability.
"""
from __future__ import annotations
from pathlib import Path
import hashlib

class OfflineEncoderUnavailable(RuntimeError):pass

class PinnedLocalEncoder:
 def __init__(self,folder):
  root=Path(folder).resolve(strict=True)
  if not root.is_dir():raise OfflineEncoderUnavailable('MODEL_ROOT_NOT_DIRECTORY')
  mf=root/'PULSE_APPROVED_MODEL.sha256'
  if not mf.is_file():raise OfflineEncoderUnavailable('HOLD_NO_OWNER_APPROVED_MODEL_MANIFEST')
  entries=[]
  for line in mf.read_text(encoding='utf-8').splitlines():
   if not line.strip() or line.startswith('#'):continue
   digest,sep,name=line.partition('  ')
   if not sep or len(digest)!=64 or any(x not in '0123456789abcdef' for x in digest):raise OfflineEncoderUnavailable('INVALID_MODEL_SHA_MANIFEST')
   p=(root/name).resolve(strict=True)
   if root not in p.parents or not p.is_file():raise OfflineEncoderUnavailable('MODEL_FILE_OUTSIDE_ROOT')
   h=hashlib.sha256(p.read_bytes()).hexdigest()
   if h!=digest:raise OfflineEncoderUnavailable('MODEL_FILE_SHA_MISMATCH')
   entries.append(name)
  if not entries:raise OfflineEncoderUnavailable('EMPTY_MODEL_MANIFEST')
  if not (root/'PULSE_LICENSE_REVIEW_ACCEPTED.txt').is_file():raise OfflineEncoderUnavailable('MODEL_LICENCE_NOT_REVIEWED')
  try:from sentence_transformers import SentenceTransformer
  except ImportError as e:raise OfflineEncoderUnavailable('SENTENCE_TRANSFORMERS_NOT_INSTALLED_NO_AUTO_INSTALL') from e
  # Explicitly disabled remote code and remote model downloads.
  self.model=SentenceTransformer(str(root),local_files_only=True,trust_remote_code=False)
 def encode(self, texts):
  return self.model.encode(texts,normalize_embeddings=True,show_progress_bar=False)
 def cosine(self,a,b):
  return float(sum(float(x)*float(y) for x,y in zip(a,b)))
