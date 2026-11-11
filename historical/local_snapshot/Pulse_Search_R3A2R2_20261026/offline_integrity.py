"""Recheck pinned wheel and model manifests; no network, no new installs."""
import argparse,hashlib,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent / "accepted_loader"))
from r3a_local_model import PinnedSentenceEncoder
from provision import WEIGHTS_SHA,WEIGHTS_SIZE

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

p=argparse.ArgumentParser();p.add_argument('--stage',required=True)
a=p.parse_args();root=Path(a.stage).resolve(strict=True)
info=json.loads((root/'PROVISION_SUCCESS.json').read_text('utf-8'))
assert info['ready'] is True
assert sha(root/'model/PULSE_APPROVED_MODEL.sha256')==info['model_manifest_sha256']
assert sha(root/'wheels.sha256')==info['wheels_manifest_sha256']
assert sha(root/'model/model.safetensors')==WEIGHTS_SHA
assert (root/'model/model.safetensors').stat().st_size==WEIGHTS_SIZE
assert (root/'model/PULSE_MODEL_PROVENANCE.json').is_file()
prov=json.loads((root/'model/PULSE_MODEL_PROVENANCE.json').read_text('utf-8'))
assert prov['git_revision_sha40']==info['model_revision']
assert prov['declared_model_license']=='MIT'
model=PinnedSentenceEncoder(root/'model')
a,b=model.encode(['Register with a GP surgery','What is JavaScript?'])
assert len(a)==len(b)==384
print('PINNED_OFFLINE_BGE_INFERENCE_PASS:',model.manifest_sha256, 'dim=384')
