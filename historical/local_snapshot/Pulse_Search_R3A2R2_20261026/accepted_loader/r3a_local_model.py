"""Explicit opt-in offline sentence encoder. No downloads. All files pinned.
The model is NOT provisioned or approved in the R3-A1 research ZIP.
"""
from pathlib import Path
import hashlib, os, re

class ModelHold(RuntimeError): pass

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

class PinnedSentenceEncoder:
 def __init__(self,folder):
  root=Path(folder).resolve(strict=True)
  if not root.is_dir():raise ModelHold('HOLD_MODEL_ROOT_NOT_DIRECTORY')
  manifest=root/'PULSE_APPROVED_MODEL.sha256'
  approval=root/'PULSE_LICENSE_REVIEW_ACCEPTED.txt'
  if not manifest.is_file() or not approval.is_file():raise ModelHold('HOLD_OWNER_MODEL_MANIFEST_OR_LICENCE_APPROVAL_MISSING')
  note=approval.read_text(encoding='utf-8')
  if 'APPROVED' not in note or not note.strip():raise ModelHold('HOLD_LICENCE_APPROVAL_EMPTY')
  expected={}
  for line in manifest.read_text(encoding='utf-8').splitlines():
   if not line or line.lstrip().startswith('#'):continue
   m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
   if not m:raise ModelHold('HOLD_BAD_MODEL_HASH_MANIFEST')
   digest,name=m.groups()
   raw=root/name
   if raw.is_symlink() or any(part.is_symlink() for part in raw.parents if part!=root):raise ModelHold('HOLD_MODEL_FILE_ESCAPE_OR_SYMLINK')
   p=raw.resolve(strict=True)
   if p==root or root not in p.parents or not p.is_file():raise ModelHold('HOLD_MODEL_FILE_ESCAPE_OR_SYMLINK')
   rel=p.relative_to(root).as_posix()
   if rel in expected:raise ModelHold('HOLD_DUPLICATE_MODEL_MANIFEST_ENTRY')
   expected[rel]=digest
   if sha(p)!=digest:raise ModelHold('HOLD_MODEL_FILE_DIGEST_MISMATCH')
  if not expected:raise ModelHold('HOLD_EMPTY_MODEL_MANIFEST')
  actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name not in ('PULSE_APPROVED_MODEL.sha256','PULSE_LICENSE_REVIEW_ACCEPTED.txt')}
  if any(p.is_symlink() for p in root.rglob('*')):raise ModelHold('HOLD_MODEL_SYMLINK')
  if actual!=set(expected):raise ModelHold('HOLD_UNPINNED_MODEL_FILE_OR_INCOMPLETE_MANIFEST')
  self.manifest_sha256=sha(manifest); self.verified_file_count=len(expected)
  os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['HF_DATASETS_OFFLINE']='1'
  try:from sentence_transformers import SentenceTransformer
  except ImportError as exc:raise ModelHold('HOLD_SENTENCE_TRANSFORMERS_MISSING_OFFLINE_NO_INSTALL') from exc
  self.model=SentenceTransformer(str(root),local_files_only=True,trust_remote_code=False)
  self.cache={}
 def encode(self,texts):
  missing=[str(x) for x in texts if str(x) not in self.cache]
  if missing:
   res=self.model.encode(missing,normalize_embeddings=True,show_progress_bar=False)
   for k,v in zip(missing,res):self.cache[k]=[float(a) for a in v]
  return [self.cache[str(x)] for x in texts]
 def cosine(self,a,b):
  return sum(float(x)*float(y) for x,y in zip(a,b))
