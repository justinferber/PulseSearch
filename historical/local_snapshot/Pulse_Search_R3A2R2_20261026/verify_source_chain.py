"""Ensure audit helper copies are byte-identical to accepted R3-A1/R2-P35 sources."""
import zipfile,hashlib,sys
from pathlib import Path
root=Path(__file__).parent
with zipfile.ZipFile(root/'accepted_R3A1.zip') as a:
 for name in ('r3a_cases.py','r3a_eval.py','r3a_local_model.py'):
  original=a.read('Pulse_Search_R3A1_20261026/'+name)
  if original!=(root/'accepted_loader'/name).read_bytes():raise SystemExit('HOLD_A1_HELPER_DRIFT_'+name)
 with zipfile.ZipFile(__import__('io').BytesIO(a.read('Pulse_Search_R3A1_20261026/accepted_R2P35.zip'))) as p:
  for name in ('hybrid_core.py','semantic_context.py','offline_encoder.py'):
   if p.read('Pulse_Search_R2P35_20261025/'+name)!=(root/'accepted_hybrid'/name).read_bytes():
    raise SystemExit('HOLD_P35_HELPER_DRIFT_'+name)
print('VERIFIED_ACCEPTED_SOURCE_HELPERS_BIT_FOR_BIT')
