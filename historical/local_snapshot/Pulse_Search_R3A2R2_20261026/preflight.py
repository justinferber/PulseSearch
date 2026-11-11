import argparse,hashlib,json
from pathlib import Path
from r3a2_eval import verify_owner_report, DB_SHA, sha
p=argparse.ArgumentParser();p.add_argument('--index',required=True);p.add_argument('--owner-report',required=True)
a=p.parse_args()
if sha(a.index)!=DB_SHA:raise SystemExit('HOLD_OWNER_INDEX_SHA_MISMATCH')
print('OWNER_R3A1_REPORT_SHA256='+verify_owner_report(a.owner_report))
print('READ_ONLY_OWNER_BASELINE_PRESERVED')
