# Pulse Search — independent grading rubric (R3-A3C)

**Status: research-only; no accepted independent grades yet.** Reviewers receive anonymised Engine A/B results and the 54 original questions. Keep the engine mapping sealed until all labels are committed. FB2 executes the search; independent reviewers judge the results. A model-authored label is never a human signature.

## Candidate grade, per ranked result
- **0 — FAIL:** wrong or irrelevant, materially misleading, disallowed by explicit exclusion/edition/geography constraints.
- **1 — WEAK:** tangential subject match, noise, or not an answer to the frozen query.
- **2 — PARTIAL:** useful relevant result but missing constraints, edition coverage or corroborating material.
- **3 — STRONG:** direct query match, constraints satisfied and adequate source grounding. For factual claims, grade 3 is **not** factual certification without independently captured primary-source content and date.

Grade relevance separately from **constraint compliance**, **source verification**, **freshness** and **negative-query abstention**. A correct top-1 does not excuse irrelevant positions 2–5. A result outside a requested edition/year or explicitly excluded named entity is a constraint violation even if it has a relevant title.

## Metrics / evidence contracts
- **P@1:** grade>=2 at rank 1, on independently judged queries only.
- **P@5:** relevant (grade>=2) ranks 1–5 / 5, independently judged.
- **MRR@5:** reciprocal rank of first relevant document, or zero when none; complete judged top-k needed.
- **Noise@5:** grade 0 or 1 results / 5; report relevance and noise separately.
- **Recall@5:** only if a *complete judged corpus relevance denominator* exists; otherwise `NOT_GRADABLE`.
- **Negative abstention:** requires genuine explicit empty-response receipts for the 10 frozen `no_result` probes and corpus-eligibility check. No returned file or missing log is **not** a pass.
- **Factual answer:** requires captured authoritative source, observed/capture date and source-supported claim. Historical verified count is **0**.
- **Performance:** report CPU, peak memory, latency distributions and environment for real executions only.

A candidate-grade CSV for the supplied stdlib tool `tools/grade_independent.py` must have:

```csv
probe_id,engine,rank,relevance,reviewer_id,source_verified,exclusion_violation,edition_correct
```

Only true reviewer-authored rows may contain `reviewer_id`. No grader should auto-populate them. An A/B replay CSV must include:

```csv
probe_id,engine,rank,title,url,source_id,filter_status
```

Do not invent empty rows to represent zero-result queries: capture explicit signed per-query zero-result receipts in a distinct run manifest. The grader intentionally returns HOLD for negative abstention until the receipt validator exists. Do not expose hidden engine mapping to reviewers.

## Blocking anomalies to adjudicate

1. `exclude_diwali`: reported leak vs five displayed non-Diwali links; requires **all candidate ranks and pre-/post-filter trace**.
2. `event_series_2`, `event_series_3`, `x09`, `catalog_history`, `x14`: determine whether 2023/2024 editions are missing from corpus vs filtered, mismatched, lower-ranked or hidden by five-link export.
3. `exclude_games`, `x12`: separate a genuine exclusion from festival-category noise.
4. `x21`: factual-status code ambiguity; never assert an answer absent independently captured evidence.

## Acceptance

Report counts and denominator for every metric; calculate separate A/B results only after comparable replay. Distinguish `AUTOMATED_ENGINE_VERDICT`, `MODEL_PRELIMINARY`, `HUMAN_REVIEW_SIGNED`, and `FACT_SOURCE_VERIFIED`. No source-body reproduction, secrets, owner index writes or production promotion.

The owner-facing workbook `PulseSearch_R3A3_Independent_Grading_and_Replay_20261111.xlsx` follows this rubric, but the real replay and signatures are still outstanding.