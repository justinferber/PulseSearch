# Pulse Search — FB2 R3-A3 evidence reconciliation

Private, sanitised engineering record for the **Pulse Search** research programme only. Independent of Pulse UNITY Events, PulseChat and ARIES.

**Status: HOLD.** No production activation, no R3-A4 progression, no model deployment, no crawler/index/API changes.

- Assignment: FB2 R3-A3 Git recovery and independent grading (11 November 2026)
- Branch: `fb2/r3-a3-evidence-reconciliation-20261111`
- Evidence base: owner-side artefacts dated 26 October 2026 (`Pulse_Search_R3A1_20261026` … `Pulse_Search_R3A3_Owner_Review_20261026`)

## What is in this repository

| Path | Purpose |
| --- | --- |
| `docs/STATUS_20261111.md` | Sanitised status record: what is verified, what is not, and the gate table |
| `docs/CHRONOLOGY_R3A2_R3A3.md` | Reconstruction of the R3-A1 → R3-A2 → R3-A3 sequence with timestamps |
| `docs/GRADING_R3A3.md` | Independent reading of the R3-A3 grading workbook, including discrepancies |
| `docs/EVIDENCE_INVENTORY.md` | Which artefacts are authoritative, and manifest verification results |
| `docs/HOLDS_AND_GATES.md` | Every outstanding HOLD condition with the owner action required |
| `docs/evidence_inventory.json` | Machine-readable inventory: path, bytes, SHA-256, mtime, publish flag |
| `docs/grading_ledger_r3a3.csv` | The 54-case ledger exported from the workbook (no human grades were added) |
| `docs/grading_summary.json` | Aggregate counts derived from the R3-A2 report and the ledger |
| `manifests/*.sha256` | The four original package manifests, byte-for-byte |
| `tools/verify_evidence.py` | Re-computes every hash and re-derives the summary locally |

## Deliberately not published

No model weights, no SQLite owner index, no virtual environment, no wheelhouse, no secrets or tokens, no `.env` file, and no publisher page-body text. All graded rows are metadata only (URL and title).

## Verify locally

```bash
python tools/verify_evidence.py --root /path/to/ChatGPTCode
```

Expected result on the intact evidence set: `FILES_OK=338 FILES_FAIL=0`, `MANIFEST entries ok=70 mismatch=0 missing=0`, and `probe_total=54 baseline_pass_retrieval=19 bge_pass_retrieval=27`.

A green verification means the local files still match the October record. It does **not** mean the search results are correct, independently graded, or approved for production.
