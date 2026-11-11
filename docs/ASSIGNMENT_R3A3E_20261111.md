# FB2 — R3-A3E: blind independent grading, anomaly adjudication and standalone search quality repairs

**11 November 2026 | Standalone Pulse Search only | Research/lab scope | No production promotion**

Upstream: [R3-A3C draft PR #4](https://github.com/justinferber/PulseSearch/pull/4) and [R3-A3D child draft PR #6](https://github.com/justinferber/PulseSearch/pull/6). Branch `fb2/r3-a3e-independent-grading-and-relevance-repair-20261111` starts at recovered/replayed R3-A3D head `1c9a846ad894ce801821cbc70651c1e5a88b1739`. Preserve both PRs as drafts until independent review.

## What has been independently verified from committed replay data

- Accepted owner corpus: 120 indexed pages / 120 FTS / 7 approved sources; SHA-256 `bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d`.
- BGE model and WSL pinned stage: 12/12 model files verified; model manifest `3955a9a2ca390314555ddb6a11b2ed16210657b689cab1b8e708653d3c63c437`; offline runtime recovered.
- Genuine repeated 54-query, 2-engine replay: hybrid 19/54 vs BGE 27/54 automated `PASS_RETRIEVAL`; 8 recoveries, 0 new regressions, all 54 verdicts in each engine identical to historical report. **This is reproducibility, not externally accepted relevance.**
- **Correction to top-URL agreement:** 44/54 is a denominator artifact, *not ten different top URLs*. Exactly ten queries have no BGE results; **all 44/44 nonempty BGE top-1 URLs equal the historical BGE top-1 URLs**. Correct future reports and comparison logic to use `top1_agreement = 44/44 comparable`, plus `no_result=10`, not tie-ordering speculation.
- **Confirmed exclusion defect:** `exclude_diwali` returns the forbidden Diwali on the Square 2025 record at **BGE rank 8** (and in the hybrid baseline at rank 1). Prior 5-link export hid the BGE leak. Full top-10 exclusion compliance fails. Do not mark this query PASS.
- **Edition recall:** multi-edition London Open House queries (`event_series_2`, `event_series_3`, `x09`) omit required years even though the corpus exposes 2023/2024 records in `catalog_history` / `x14`. Investigate year/series query decomposition, rank/filter evidence and corpus IDs; do not claim editions absent.
- Lab API `11/11` status checks, but **3/5 exact-answer relevance** on 8-page synthetic loopback corpus. Doctor query returned zero, voting query returned GP registration top. Fix quality only in NEW code/fixtures, not in immutable October snapshots.
- POSIX original tests: 21/25 modules clean, 419 executed, 362 within passing modules. Remaining 4 are historical fixture/report hash assertions (P21, R2-P32/P33/P34); retain HOLD until original files are recovered, never edit expected digests to force PASS.
- Independently signed grades remain **0**, source-verified factual answers **0**, production **HOLD**.

## Owner-facing blinded grading pack — already created

Owner's file: `PulseSearch_R3A3D_Blind_Independent_Grading_54_20261111.xlsx` (supplied in ChatGPT).
Separate unblinding file: `PulseSearch_R3A3D_Engine_Mapping_Keep_Sealed_20261111.csv` (keep out of reviewer access and Git).

The pack is assembled from the committed R3-A3D JSON, October owner workbook, and full actual returned ranks. It includes 54 exact questions, 423 returned candidate rows (72 baseline + 351 BGE), 32 masked engine-query no-result receipts, 25 priority cases and 74 unique candidate documents. No fabricated grades, signature or source checks. Historical BGE top-1 URLs crosschecked 44/44 against October workbook.

For future regenerations, use the exact `docs/evidence/r3a3d_frozen54_replay.json` provenance and verify ranking arrays, not any preliminary five-link exports. Mask engine identities per probe and keep the mapping separately. **Do not commit the sealed engine map, personally identifying reviewer information or unlicensed publisher body text to Git.**

## Next executable action, in order

1. **Preserve replay evidence.** Freeze hashes of R3-A3D replay JSON, frozen_54.csv, source/index/model pins and full 54x2 query outputs. Maintain the untouched 26 Oct comparison and R3-A3D results as immutable baselines.
2. **Prepare blinded grading export.** Confirm 54 unique question IDs, 108 blinded engine-query combinations, 423 real ranked candidate rows, 32 explicit empty-response combinations; guarantee no rank >10 and no omitted candidate. Create a deterministic integrity checker for the scoring export, separate from the sealed A/B identity mapping. Never expose automated verdicts/expected URLs to graders. Reviewer manually enters 0–3 for rank relevance; independently records constraint breach, edition correctness, captured primary-source evidence, reviewer ID and UTC timestamp. Negative queries receive a separate abstention judgement; unverified factual-answer queries remain uncategorically unverified until source checked.
3. **Owner / independent review.** Provide the filled-in query-and-candidate workbook for the human reviewer. Leave all grades blank until a person actually signs them. Do not auto-fill or call an LLM label a human judgement. Independently double-grade the 25 priority cases when a second reviewer is available; record discrepancies for reconciliation. Owners can make an explicit first-pass human grading; avoid conflating it with external independent signoff.
4. **Metric consolidation.** Only with genuine signed, fully graded evidence, compute paired P@1, P@5, MRR@5 and noise@5 with exact denominators, constraints/exclusion violation rate, year/edition coverage and negative-query abstention. Do not calculate recall without a complete relevance set; report signed-subset measurements separately until all cases done. Keep factual-answer abstention separate from search-result relevance.
5. **Defect fixtures / tests.** In a new dev tree, reproduce `exclude_diwali` illegal BGE rank-8 hit, incomplete `event_series_2`, `event_series_3`, `x09`, plus `exclude_games`/`x12` festival noise. Add integration tests asserting exclusion at *every returned rank*, required editions, year, geographical scope and duplicate handling. Never silently switch from top10 to top5 to pass. Keep original case text, corpus and metrics frozen.
6. **Investigate live API relevance.** On the synthetic lab corpus, explain `doctor` no-result and `register to vote` GP top1, add expected-canonical-result and query-intent assertions, then implement guarded experimental improvements. Report baseline vs new candidate metrics, zero regressions on safety/exclusions, no promotion without owner decision.
7. **Recover remaining pin-mismatched fixtures** via original Oct artifacts, full SHA checks and exact provenance. Do not manufacture accepted P21 or R2-P32/33/34 reports.
8. **Plan independent capability expansion** only after grading: genuine robots-respecting public discovery, crawl freshness/recrawl, source admission and quality, larger independent index, multilingual search, local hybrid+semantic ranking, protected standalone API. Pilot on owner-approved sources and bounded sample; no unauthorised public crawling and no paid-search dependency.

## Deliverables in Git

- `docs/R3A3E_GRADING_ACCEPTANCE.md`: independent reviewer protocol, denominator rules, signoff audit.
- `docs/R3A3E_DEFECT_FINDINGS.md`: full rank-8 Diwali evidence; year/edition and lab API findings.
- `docs/R3A3E_EXPANSION_PLAN.md`: isolated search-engine roadmap, dependencies and safe staged gates.
- `tools/verify_blind_grading_input.py`: stdlib validator for 54×2, top10 rank identity, no signoffs invented, source provenance.
- `tests/test_r3a3e_constraints.py`: fail-before-fix tests in a new development tree, not rewritten historic snapshots.
- `docs/evidence/r3a3e_quality_delta.json`: actual numeric results only after verified grades/real candidate tests. Otherwise explicit `HOLD_UNGRADED`.
- Draft PR targeted at R3-A3D branch; do not merge into main.

**Acceptance:** `REPLAY_REPRODUCED=PASS`; `BLIND_PACK_VALID=PASS/HOLD`; `SIGNED_HUMAN_GRADING=<actual>`; `FULL_K_EXCLUSION_COMPLIANCE=FAIL_UNTIL_FIXED`; `OPEN_HOUSE_EDITION_COVERAGE=FAIL_UNTIL_FIXED`; `ORIGINAL_REGRESSION=PARTIAL`; `PRODUCTION=HOLD`. Continue automatically through safe research/test/code work without repeatedly stopping; stop before destructive owner actions, external crawling, releases, or substituting evidence.
