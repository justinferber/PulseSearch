#!/usr/bin/env python3
"""Verify the Pulse Search R3-A2 / R3-A3 evidence set against docs/evidence_inventory.json.

Read-only. Recomputes SHA-256 for every inventoried file, re-checks the four package
manifests, and re-derives the grading summary from the R3-A2 report and the R3-A3 workbook.

Usage:
    python tools/verify_evidence.py --root /path/to/ChatGPTCode
    python tools/verify_evidence.py --root . --skip-grading
Exit code 0 = everything matched. 1 = at least one failure. 2 = input missing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
REPORT = 'Pulse_Search_R3A2_Run_1psnjrhX/shadow/r3a2_bge_comparison_report.json'
WORKBOOK = 'Pulse_Search_R3A3_Owner_Review_20261026.xlsx'
MANIFESTS = [
    'Pulse_Search_R3A1_20261026/MANIFEST.sha256',
    'Pulse_Search_R3A2_20261026/MANIFEST.sha256',
    'Pulse_Search_R3A2R1_20261026/MANIFEST.sha256',
    'Pulse_Search_R3A2R2_20261026/MANIFEST.sha256',
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for block in iter(lambda: fh.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def verify_inventory(root: Path, inventory: dict) -> tuple[int, int, list[str]]:
    ok = bad = 0
    failures: list[str] = []
    for rel, rec in sorted(inventory['files'].items()):
        path = root / rel
        if not path.exists():
            bad += 1
            failures.append(f'MISSING {rel}')
            continue
        if path.stat().st_size != rec['bytes']:
            bad += 1
            failures.append(f'SIZE {rel}')
            continue
        if sha256(path) != rec['sha256']:
            bad += 1
            failures.append(f'HASH {rel}')
            continue
        ok += 1
    return ok, bad, failures


def verify_manifests(root: Path) -> tuple[int, int, int, list[str]]:
    ok = bad = missing = 0
    failures: list[str] = []
    for rel in MANIFESTS:
        mf = root / rel
        if not mf.exists():
            missing += 1
            failures.append(f'MISSING MANIFEST {rel}')
            continue
        base = mf.parent
        for line in mf.read_text(encoding='utf-8', errors='replace').splitlines():
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            want, target = parts[0], parts[-1].lstrip('*')
            path = base / target
            if not path.exists():
                missing += 1
                failures.append(f'MISSING {rel}::{target}')
            elif sha256(path) != want:
                bad += 1
                failures.append(f'MISMATCH {rel}::{target}')
            else:
                ok += 1
    return ok, bad, missing, failures


def read_sheet_rows(workbook: Path, sheet: str) -> list[dict]:
    with zipfile.ZipFile(workbook) as z:
        root = __import__('xml.etree.ElementTree', fromlist=['ET']).fromstring(z.read(sheet))
    rows = []
    for row in root.iter(NS + 'row'):
        cells = {}
        for cell in row.findall(NS + 'c'):
            col = re.match(r'([A-Z]+)', cell.get('r')).group(1)
            value = cell.find(NS + 'v')
            inline = cell.find(NS + 'is')
            if value is not None:
                cells[col] = value.text or ''
            elif inline is not None:
                cells[col] = ''.join(t.text or '' for t in inline.iter(NS + 't'))
        rows.append(cells)
    return rows


def derive_grading(root: Path) -> dict:
    report = json.loads((root / REPORT).read_text(encoding='utf-8'))
    ledger = []
    for cells in read_sheet_rows(root / WORKBOOK, 'xl/worksheets/sheet3.xml'):
        probe = cells.get('A', '')
        if not cells.get('B') or probe == 'ID' or probe.startswith('COMPLETE'):
            continue
        ledger.append(cells.get('F', ''))
    distribution = report['distribution']
    return {
        'probe_total': len(ledger),
        'baseline_pass_retrieval': sum(p['baseline'].get('PASS_RETRIEVAL', 0) for p in distribution.values()),
        'bge_pass_retrieval': sum(p['bge_dense'].get('PASS_RETRIEVAL', 0) for p in distribution.values()),
        'baseline_pass_safety': sum(p['baseline'].get('PASS_SAFETY', 0) for p in distribution.values()),
        'bge_pass_safety': sum(p['bge_dense'].get('PASS_SAFETY', 0) for p in distribution.values()),
        'recoveries': len(report['deltas']['newly_recovered']),
        'regressions': len(report['deltas']['new_regressions']),
        'grades': {g or 'BLANK': ledger.count(g) for g in sorted(set(ledger))},
        'factual_answers_verified': report['factual_answers_verified'],
        'model_manifest_sha256': report['model_manifest_sha256'],
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True, help='directory containing the Pulse_Search_* artefacts')
    parser.add_argument('--skip-grading', action='store_true')
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    inventory_path = Path(__file__).resolve().parent.parent / 'docs' / 'evidence_inventory.json'
    if not inventory_path.exists():
        print(f'FAIL inventory missing: {inventory_path}')
        return 2

    inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
    ok, bad, inv_fail = verify_inventory(root, inventory)
    print(f'FILES_OK={ok} FILES_FAIL={bad}')

    m_ok, m_bad, m_missing, m_fail = verify_manifests(root)
    print(f'MANIFEST entries ok={m_ok} mismatch={m_bad} missing={m_missing}')

    failures = inv_fail + m_fail

    if not args.skip_grading:
        if not (root / REPORT).exists() or not (root / WORKBOOK).exists():
            print('FAIL grading inputs missing')
            failures.append('grading inputs missing')
        else:
            derived = derive_grading(root)
            expected = {
                'probe_total': 54,
                'baseline_pass_retrieval': 19,
                'bge_pass_retrieval': 27,
                'baseline_pass_safety': 10,
                'bge_pass_safety': 10,
                'recoveries': 8,
                'regressions': 0,
                'factual_answers_verified': 0,
            }
            for key, want in expected.items():
                got = derived[key]
                status = 'OK' if got == want else 'MISMATCH'
                print(f'{key}={got} expected={want} {status}')
                if got != want:
                    failures.append(f'{key} {got} != {want}')
            print('grades=' + json.dumps(derived['grades']))
            print('model_manifest_sha256=' + derived['model_manifest_sha256'])

    if failures:
        for item in failures[:40]:
            print('FAIL ' + item)
        print(f'RESULT=FAIL failures={len(failures)}')
        return 1
    print('RESULT=PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
