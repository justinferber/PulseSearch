# HOLD conditions and required owner actions

Nothing in this repository authorises production activation or R3-A4. Each item below is a gate; none is satisfied by a passing hash.

| # | HOLD | Why it blocks | Evidence | Owner action |
| --- | --- | --- | --- | --- |
| H1 | **Handover package missing** | The assignment's mandated read-only inventory script and Git handover document were never available, so the prescribed procedure could not be executed or audited | Absent from `ChatGPTCode` to depth 10 | Re-supply `PulseSearch_FB2_Local_Evidence_and_Git_Handover_20261111.zip`, or confirm the surviving artefacts are the intended authority |
| H2 | **Source-page verification pending** | No page bodies or capture dates were exported, so no claim about actual content, price, time, accessibility or cancellation can be supported | `r3a2_bge_comparison_report.json`: `no_publisher_body_export: true`; workbook "Source verified" = NO ×54 | Approve a read-only, rights-cleared verification pass that records URL + hash + captured date privately |
| H3 | **Full candidate and filter trace pending** | Exports show at most 5 links (sometimes total 10), so edition/series and exclusion verdicts cannot be adjudicated — including the `exclude_diwali` conflict | `r3a2_eval.py` exports `links[:5]`; workbook flags `CONFLICT_WITH_ENGINE_VERDICT` | Produce an untruncated candidate + filter trace for the 25 priority cases, then re-grade |
| H4 | **Independent human labels** | 0 of 54 rows are signed; a model-authored title grade is a triage aid, not an independent judgement | Workbook: `Independent human grade` and `Source verified` blank/NO for all rows | Recruit at least one reviewer with no authorship role; grade blind, then compute precision@1 and recall@5 |
| H5 | **Factual answer mode** | 0 factual answers verified; retrieval of a relevant title is not evidence for a current fact | Report: `factual_answers_verified: 0`; 11 blank fact grades | Keep fact mode disabled until a separate evidence-backed gate (route C/B) is designed and reviewed |
| H6 | **No performance evidence** | No latency, CPU or memory figures exist, so no capacity or cost claim is supportable | Workbook: "Latency + CPU/memory benchmarking = PENDING" | Benchmark the pinned model on the owner host; record hardware and percentile timings |
| H7 | **Single comparison only** | One run exists; `F9zS4WJf` has no comparison output and must not be counted twice | Run directories and their `shadow/` contents | If a second measurement is wanted, run the frozen suite again unchanged and keep both reports |
| H8 | **WSL execution unavailable** | Ubuntu returned `Wsl/Service/0x8007274c` then `E_UNEXPECTED`; a global `wsl --shutdown` was refused because ten Docker containers were live | Shell transcripts of the failed launches | Repair WSL at a time that suits running containers, or authorise a dedicated environment for a re-run |
| H9 | **No re-execution in this review** | Model weights and the isolated venv are absent by design, so October outputs were re-verified by hash and internal consistency only, never recomputed | `docs/EVIDENCE_INVENTORY.md` §5 | Accept hash-level verification, or authorise a controlled re-run |
| H10 | **Production promotion** | R3-A2 explicitly holds production integration; the A/B/C release gates in `R3_MAJOR_ROUTE.md` are unmet | `production_integration: HOLD_INDEPENDENT_GRADING_AND_FACT_EVIDENCE` | No action; do not promote. R3-A4 must not begin until H1–H4 are closed |

## Deliberately not done

No model download, no Python provisioning, no database open for write, no crawler/API/Stripe/UNA change, no key handling, no publisher body text extracted, no weights or databases committed.

## Exit condition for this assignment

The assignment's deliverables — repository, branch, issue, sanitised status record, evidence inventory, chronology, grading results and this HOLD list — are complete. R3-A4 remains blocked by H1–H4 regardless of how the remaining items are resolved.
