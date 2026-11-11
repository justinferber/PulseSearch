#!/usr/bin/env python3
"""R3-A2 one-time owner-approved online acquisition, local-only research environment.

No crawler/index/API changes. Weight SHA is from the publisher's public model file.
Other model files and resolved binary wheels are hashed and locked before execution.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, subprocess, sys, urllib.request, urllib.error, urllib.parse, platform
from html.parser import HTMLParser
from pathlib import Path

MODEL_ID='BAAI/bge-small-en-v1.5'
EXPECTED_REV_PREFIX='5c38ec7'  # Official signed last commit, 22 Feb 2024
WEIGHTS_SHA='3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad'
WEIGHTS_SIZE=133466304
FILES=('1_Pooling/config.json','README.md','config.json','config_sentence_transformers.json',
       'model.safetensors','modules.json','sentence_bert_config.json','special_tokens_map.json',
       'tokenizer.json','tokenizer_config.json','vocab.txt')
REQUIREMENTS=('sentence-transformers==5.1.2','transformers==4.57.1',
              'huggingface-hub==0.35.3','torch==2.6.0+cpu')
# Official PyTorch CPU 2.6.0 provides linux_x86_64 wheels for cp310, cp311, cp312 and cp313.
# Do not accept cp314 or switch the approved PyTorch version silently.
SUPPORTED_PYTHON={(3,10),(3,11),(3,12),(3,13)}

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def get(url,output=None, attempts=3):
 last=None
 for attempt in range(attempts):
  try:
   req=urllib.request.Request(url, headers={'User-Agent':'PulseSearch-R3A2-offline-research/1.0'})
   with urllib.request.urlopen(req,timeout=90) as response:
    if output is None:return response.read()
    with open(output,'wb') as out:
     shutil.copyfileobj(response,out,1<<20)
    return None
  except (urllib.error.URLError, TimeoutError, OSError) as err:
   last=err
   if output and Path(output).exists():Path(output).unlink()
 raise RuntimeError('HOLD_DOWNLOAD_FAILED: '+str(last))

def cmd(args):
 print('RUN:', ' '.join(map(str,args)),flush=True)
 subprocess.run(args,check=True,env={**os.environ,'PIP_DISABLE_PIP_VERSION_CHECK':'1','PIP_NO_INPUT':'1'})

class Anchors(HTMLParser):
 def __init__(self):super().__init__();self.urls=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a':
   href=dict(attrs).get('href','')
   if href:self.urls.append(href)

def verify_upstream_wheel(name,vers,filename,digest):
 """Verify local wheel against official PyPI JSON or PyTorch CPU simple-index hash.
 Fail closed if no matching *publisher-listed* hash can be located.
 """
 if name=='torch':
  raw=get('https://download.pytorch.org/whl/cpu/torch/').decode('utf-8')
  anchors=Anchors();anchors.feed(raw)
  hashes=[]
  for href in anchors.urls:
   parsed=urllib.parse.urlsplit(href)
   fname=urllib.parse.unquote(parsed.path.rsplit('/',1)[-1])
   if fname!=filename:continue
   params=urllib.parse.parse_qs(parsed.fragment)
   hashes+=params.get('sha256',[])
  if digest not in hashes:raise RuntimeError('HOLD_PYTORCH_PUBLISHED_WHEEL_SHA_MISMATCH_'+filename)
  return 'https://download.pytorch.org/whl/cpu/torch/'
 data=json.loads(get('https://pypi.org/pypi/'+urllib.parse.quote(name)+'/'+urllib.parse.quote(vers)+'/json'))
 for row in data.get('urls',[]):
  if row.get('filename')==filename and row.get('digests',{}).get('sha256')==digest:
   return 'https://pypi.org/pypi/'+name+'/'+vers+'/json'
 raise RuntimeError('HOLD_PYPI_PUBLISHED_WHEEL_SHA_MISMATCH_'+filename)

def provision(root:Path):
 if sys.platform!='linux' or platform.machine()!='x86_64':raise RuntimeError('HOLD_UNSUPPORTED_NON_X86_64_LINUX_WHEEL_PLATFORM')
 if tuple(sys.version_info[:2]) not in SUPPORTED_PYTHON:
  raise RuntimeError('HOLD_PYTHON_310_TO_313_REQUIRED_FOR_PINNED_CPU_WHEEL')
 root=root.expanduser().resolve()
 if root.exists() or Path(str(root)+'.provisioning').exists():
  raise RuntimeError('HOLD_EXISTING_RESEARCH_ROOT_OR_STAGING: no overwrite allowed')
 stage=Path(str(root)+'.provisioning')
 stage.mkdir(parents=True)
 try:
  print('=== VERIFY EXACT OFFICIAL REPOSITORY REVISION & MODEL LICENSE ===',flush=True)
  meta=json.loads(get('https://huggingface.co/api/models/'+MODEL_ID))
  revision=meta.get('sha','')
  if not re.fullmatch(r'[a-f0-9]{40}',revision) or not revision.startswith(EXPECTED_REV_PREFIX):
   raise RuntimeError('HOLD_MODEL_REPO_REVISION_DRIFT_REVIEW_REQUIRED: '+revision)
  if str(meta.get('cardData',{}).get('license','')).lower()!='mit':
   raise RuntimeError('HOLD_MODEL_LICENSE_DECLARATION_NOT_MIT')
  names={row.get('rfilename') for row in meta.get('siblings',[])}
  if set(FILES)-names:raise RuntimeError('HOLD_MODEL_EXPECTED_FILES_MISSING')
  model=stage/'model';model.mkdir()
  hashes=[]
  for rel in FILES:
   if rel.startswith('/') or '..' in Path(rel).parts:raise RuntimeError('HOLD_MODEL_BAD_PATH')
   output=model/rel;output.parent.mkdir(parents=True,exist_ok=True)
   url=f'https://huggingface.co/{MODEL_ID}/resolve/{revision}/{rel}'
   print('DOWNLOAD_MODEL_FILE:',rel,flush=True)
   get(url,output)
   digest=sha(output)
   if rel=='model.safetensors' and (digest!=WEIGHTS_SHA or output.stat().st_size!=WEIGHTS_SIZE):
    raise RuntimeError('HOLD_PUBLISHER_WEIGHT_SHA256_OR_SIZE_MISMATCH')
   hashes.append((rel,digest))
  provenance={'source_url':'https://huggingface.co/'+MODEL_ID,'model_id':MODEL_ID,'git_revision_sha40':revision,
   'model_weight_sha256':WEIGHTS_SHA,'model_weight_size_bytes':WEIGHTS_SIZE,
   'declared_model_license':'MIT','approved_scope':'isolated, offline, research-only; no production',
   'downloaded_directly_by_owner':'yes','external_model_code_execution':'disabled',
   'source_note':'Owner approval in ChatGPT on 2026-10-26; official Hub model card and weight SHA.'}
  prov=model/'PULSE_MODEL_PROVENANCE.json'
  prov.write_text(json.dumps(provenance,indent=2,sort_keys=True)+'\n',encoding='utf-8')
  hashes.append((prov.name,sha(prov)))
  (model/'PULSE_LICENSE_REVIEW_ACCEPTED.txt').write_text(
   'APPROVED — one-time owner-authorised R3-A2 local research evaluation only.\n'
   'Model: BAAI/bge-small-en-v1.5\nLicence declared by official publisher: MIT.\n'
   'Usage: no republishing, no commercial/API deployment, no remote model execution.\n'
   'Copyright attribution and MIT conditions must be retained for any later distribution.\n'
   'Third-party Python dependency licences require separate inventory review before distribution.\n',encoding='utf-8')
  (model/'PULSE_APPROVED_MODEL.sha256').write_text(
   ''.join(f'{digest}  {rel}\n' for rel,digest in sorted(hashes)),encoding='utf-8')
  print('MODEL_FILES_SHA_VERIFIED:',len(hashes),flush=True)
  # Download in a single resolver pass, locking every platform-specific wheel before local installation.
  wheelhouse=stage/'wheelhouse';wheelhouse.mkdir()
  print('=== RESOLVE CPU-ONLY TORCH + REQUIRED PYTHON WHEELS ===',flush=True)
  pip=[sys.executable,'-m','pip']
  cmd(pip+['download','--only-binary=:all:','--index-url','https://pypi.org/simple',
    '--extra-index-url','https://download.pytorch.org/whl/cpu', '--dest',str(wheelhouse),*REQUIREMENTS])
  wheels=sorted(wheelhouse.glob('*.whl'))
  if not wheels or set(wheelhouse.iterdir())!=set(wheels):raise RuntimeError('HOLD_NONWHEEL_DOWNLOAD_OR_EMPTY_WHEELHOUSE')
  from pip._vendor.packaging.utils import parse_wheel_filename
  lock=[];seen=set()
  for path in wheels:
   name,vers,build,tags=parse_wheel_filename(path.name)
   name=str(name).lower().replace('_','-')
   if name in seen:raise RuntimeError('HOLD_DUPLICATE_RESOLVED_PACKAGE_'+name)
   seen.add(name)
   digest=sha(path)
   upstream=verify_upstream_wheel(name,str(vers),path.name,digest)
   lock.append((name,str(vers),path.name,digest,upstream))
  if ('torch','2.6.0+cpu') not in {(r[0],r[1]) for r in lock}:raise RuntimeError('HOLD_CPU_TORCH_NOT_SELECTED')
  for spec in REQUIREMENTS:
   name,version=spec.split('==',1)
   if (name,version) not in {(r[0],r[1]) for r in lock}:raise RuntimeError('HOLD_TOP_LEVEL_VERSION_DRIFT_'+name)
  (stage/'wheels.sha256').write_text(''.join(f'{h}  wheelhouse/{f}\n' for _,_,f,h,_ in lock),encoding='utf-8')
  (stage/'requirements-locked.txt').write_text(''.join(f'{n}=={v} --hash=sha256:{h}\n' for n,v,_,h,_ in lock),encoding='utf-8')
  (stage/'packages-audit.json').write_text(json.dumps({'requested_exact_versions':REQUIREMENTS,
   'wheel_sha256s':[{'package':n,'version':v,'wheel':f,'sha256':h,'verified_upstream':u} for n,v,f,h,u in lock],
   'binary_download_then_upstream_SHA_verified_and_locked_before_install':True,'wheel_index_sources':['pypi.org','download.pytorch.org/whl/cpu'],
   'third_party_package_licences':'Inventory required before redistribution or deployment'},indent=2)+'\n')
  print('=== INSTALL EXCLUSIVELY FROM LOCALLY HASH-LOCKED WHEELS ===',flush=True)
  import venv
  venv.create(stage/'venv',with_pip=True,clear=False,symlinks=True)
  pipenv=stage/'venv/bin/python'
  cmd([str(pipenv),'-m','pip','install','--no-index','--find-links',str(wheelhouse),
      '--require-hashes','--no-deps','-r',str(stage/'requirements-locked.txt')])
  cmd([str(pipenv),'-m','pip','check'])
  smoke=stage/'venv/bin/python'
  cmd([str(smoke),'-c',"import torch,transformers,sentence_transformers;print('RUNTIME_READY',torch.__version__, transformers.__version__,sentence_transformers.__version__)"])
  # Model verification and first inference performed strictly offline.
  script='''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[2])
from r3a_local_model import PinnedSentenceEncoder
encoder=PinnedSentenceEncoder(sys.argv[1]); v=encoder.encode(['London Open House 2025','Register with a GP surgery'])
assert len(v)==2 and all(len(a)==384 for a in v)
print('LOCAL_MODEL_OFFLINE_INFERENCE_READY',len(v),len(v[0]))'''
  # accepted R3-A1 loader is supplied by R3-A2 source folder (not downloaded)
  scriptsrc=Path(__file__).parent
  cmd([str(smoke),'-c',script,str(model),str(scriptsrc/'accepted_loader')])
  # Keep fixed .provisioning directory: moving a venv breaks absolute script paths.
  ready=stage/'PROVISION_SUCCESS.json'
  ready.write_text(json.dumps({'model_revision':revision,'weight_sha256':WEIGHTS_SHA,
    'model_manifest_sha256':sha(model/'PULSE_APPROVED_MODEL.sha256'),
    'wheels_manifest_sha256':sha(stage/'wheels.sha256'),
    'wheel_count':len(wheels),'ready':True},indent=2)+'\n')
  print('PROVISION_SUCCESS_ROOT='+str(stage))
  print('PULSE_R3A2_RUNTIME='+str(stage))
 except BaseException:
  print('HOLD_R3A2_PROVISION_FAILED; staged directory retained for review: '+str(stage),file=sys.stderr)
  raise

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--root',required=True)
 args=ap.parse_args();provision(Path(args.root))
