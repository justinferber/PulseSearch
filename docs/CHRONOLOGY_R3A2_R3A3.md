# Chronology — R3-A1 → R3-A2 → R3-A3

All timestamps are the local (Windows) directory and file times of the surviving artefacts from **26 October 2026**, read-only. They establish ordering, not authorship.

| Time | Artefact | Meaning | Authority |
| --- | --- | --- | --- |
| 00:45:09 | `Pulse_Search_R3A1_20261026/` | R3-A1 package: 30-case adversarial challenge, fixed success checks, owner R2-P35 hybrid report | accepted baseline (9/9 hashes) |
| 00:45:23 | `Pulse_Search_R3A1_Run_XmiTzc5D/` | R3-A1 run output (122 files) | supporting |
| 01:20:50 | `Pulse_Search_R3A2_20261026/` | R3-A2 package: pinned BGE trial, acquisition + offline evaluation | superseded by R1/R2 (19/19 hashes) |
| 01:27:21 | `Pulse_Search_R3A2R1_20261026/` | R3-A2R1: preflight import-path correction (`r3a_cases`, `hybrid_core` on explicit `PYTHONPATH`) | superseded by R2 (20/20 hashes) |
| 01:38:xx | `Pulse_Search_R3A2R2_20261026/` | R3-A2R2: interpreter selection widened to CPython 3.10–3.13, venv+pip probed before any download | **authoritative package** (22/22 hashes) |
| 01:48:57 | `Pulse_Search_R3A2_Run_F9zS4WJf/` | Run directory with pinned sources only — **no `shadow/` comparison output** | **non-authoritative** (partial/earlier run) |
| 01:53:46 | `Pulse_Search_R3A2_SQLite_Test_Compatibility_20261026/test_p17.py` | Test-only P17 SQLite compatibility overlay used to make the frozen test suite run | test scaffolding, not product code |
| 01:55:42 | `Pulse_Search_R3A2_Run_1psnjrhX/` | **Authoritative R3-A2 run**: `shadow/r3a2_bge_comparison_report.json` (79 KB), review HTML, independent review CSV | **the comparison of record** |
| 14:24:33 | `Pulse_Search_R3A3_Owner_Review_20261026.xlsx` | R3-A3 owner review workbook: 4 sheets, 54-case ledger, 25 priority cases, gate table | **preliminary**, human grades blank |
| 11 Nov 2026 | this repository | Independent reconciliation of the above; no new run | review record |

## Reading of the sequence

1. **R3-A1** established the trustworthy-measurement baseline (30 adversarial cases, honest failure classification, no factual claims).
2. **R3-A2** attempted the real local BGE branch and stopped twice, correctly and visibly: first on a missing import path (R1), then on an over-restrictive interpreter guard (R2). Neither stop was worked around; the guard was corrected and the allowed range documented against publisher wheel availability.
3. The successful run produced one comparison report covering 54 probes. `Pulse_Search_R3A2_Run_F9zS4WJf` is an earlier, incomplete run and must not be quoted as a second independent result.
4. **R3-A3** is one workbook, not a second evaluation: it re-reads the same 54 probes at title/URL level and adds a triage grade. It adds **no new evidence** about page content, ranking traces, latency or factual truth.

## Consequences for any future claim

- Only one BGE comparison exists. Any statement of the form "BGE was measured twice" would be false.
- Every R3-A3 grade inherits the R3-A2 candidate list, which was truncated to five links in the export. Grades 1 and 2 in particular may reflect truncation rather than ranking failure.
- The 11 blank grades are the fact probes. They are blank because a title cannot verify a fee, time, price, ticket state, accessibility or cancellation — not because grading was skipped.
