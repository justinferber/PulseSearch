# Evidence inventory — what is authoritative and what was verified

Independent verification performed 11 November 2026 on the local Windows copy. Every hash below was recomputed; nothing was taken from a report's own claim.

## 1. Package-level verification

| Package | Manifest entries | Verified | Mismatch | Missing | Verdict |
| --- | --- | --- | --- | --- | --- |
| `Pulse_Search_R3A1_20261026` | 9 | 9 | 0 | 0 | intact |
| `Pulse_Search_R3A2_20261026` | 19 | 19 | 0 | 0 | intact, superseded |
| `Pulse_Search_R3A2R1_20261026` | 20 | 20 | 0 | 0 | intact, superseded |
| `Pulse_Search_R3A2R2_20261026` | 22 | 22 | 0 | 0 | intact, **authoritative** |
| **Total** | **70** | **70** | **0** | **0** | |

## 2. Authoritative artefacts

| Artefact | Bytes | Role |
| --- | --- | --- |
| `Pulse_Search_R3A2R2_20261026/` | ~2.9 MB dir | Authoritative R3-A2 package: pinned acquisition, interpreter policy, offline evaluation |
| `Pulse_Search_R3A2_Run_1psnjrhX/shadow/r3a2_bge_comparison_report.json` | 79,158 | **Primary comparison of record** (54 probes, per-partition distributions, deltas) |
| `Pulse_Search_R3A2_Run_1psnjrhX/shadow/r3a2_independent_review.csv` | 7,327 | 54-row review template — human grade columns intentionally empty |
| `Pulse_Search_R3A2_Run_1psnjrhX/shadow/r3a2_bge_comparison_review.html` | 14,943 | Human-readable view of the same comparison |
| `Pulse_Search_R3A3_Owner_Review_20261026.xlsx` | 19,133 | R3-A3 preliminary grading workbook (4 sheets) |
| `Pulse_Search_R3A1_20261026/owner_R2P35_report.json` | — | Baseline owner report; pins index SHA and honest failure counts |
| `Pulse_Search_R3A1_20261026/R3_MAJOR_ROUTE.md` | — | The release-gate contract (A1/A2/B/C) that constrains any promotion |

## 3. Explicitly non-authoritative

| Artefact | Why not authoritative |
| --- | --- |
| `Pulse_Search_R3A2_Run_F9zS4WJf/` | Earlier run (01:48:57) with no `shadow/` comparison output. Contains pinned sources only. Must never be quoted as a second independent result. |
| `Pulse_Search_R3A2_SQLite_Test_Compatibility_20261026/test_p17.py` | Test-only compatibility overlay so the frozen suite runs under the available SQLite; not product behaviour. |
| `Pulse_Search_R3A1_Run_XmiTzc5D/` | R3-A1 run scratch; superseded by the accepted owner report. |
| Older `Pulse_Search_R2P*` directories | Pre-R3 history; useful context, not part of the R3-A2/A3 claim. |

## 4. Machine-readable inventory

`docs/evidence_inventory.json` records, for 338 files across the eight R3 artefacts: relative path, byte size, SHA-256, last-write time, and whether the file is publishable. Files with extensions `.sqlite`, `.sqlite3`, `.db`, `.safetensors`, `.bin`, `.pt`, `.whl`, `.gz`, `.pyc` are flagged `publish: false` and are not in this repository.

## 5. What the hashes prove, and what they do not

**Prove:** the files on disk today are byte-identical to the October record, so the R3-A2/R3-A3 outputs being discussed are the outputs that were produced, unaltered.

**Do not prove:** that the evaluation was correct, that the model weights matched the publisher SHA (weights are absent from this workspace), that the owner index still matches `bb8e5202…`, or that any factual claim is true. Model-identity claims rest on the report's own `model_manifest_sha256` (`3955a9a2…`) and its 12 verified files, which cannot be re-checked here without the weights.

## 6. Missing input

`PulseSearch_FB2_Local_Evidence_and_Git_Handover_20261111.zip`, its read-only evidence inventory script (`PulseSearch_FB2_ReadOnly_Evidence_Inventory_20261111.sh`) and the accompanying Git handover document were **not present** in the working directory (searched to depth 10). This inventory is therefore a substitute built from the surviving artefacts, not the handed-over procedure.
