# FB2 — R3-A3B executable engineering assignment

Canonical GitHub engineering thread: https://github.com/justinferber/PulseSearch/issues/2

Parent evidence reconciliation: https://github.com/justinferber/PulseSearch/issues/1

Target branch: `fb2/r3-a3b-trace-and-source-verification-20261111`

---

# FB2 — R3-A3B full-candidate trace and source-evidence recovery (research only)

**Authority:** Execute read-only research and publish sanitised evidence. **NO R3-A4, production promotion, ranker activation, crawler/API changes, owner SQLite writes, dependency/model downloads, or WSL/Docker restart.** Independently confirmed source-of-record: commit `608cfd679b564f69af81d0f80229c2375f37ef7e`. Work only in branch `fb2/r3-a3b-trace-and-source-verification-20261111`; no direct push to `main`.

**Current baseline:** One real R3-A2 comparison (`Pulse_Search_R3A2_Run_1psnjrhX`); 54 frozen probes; automated baseline/BGE 19/27 `PASS_RETRIEVAL`; 10/10 negative-safety passes; 8 claimed recoveries; 0 reported regressions. R3-A3 spreadsheet grades 54 at title/URL level; 0 independent human approvals and 0 verified factual answers. These are reports, not accepted retrieval-quality or factual-accuracy results. Issue #1 documents reconciliation.

## Start (Windows-native, no WSL requirement)
1. Locate `C:\Users\justi\Desktop\pulseunity\ChatGPTCode` and existing `PulseSearch_FB2_R3A3_20261111` checkout. Verify Git remote `https://github.com/justinferber/PulseSearch.git`, clean tree and exact baseline SHA. Fetch then check out the **already created** branch `fb2/r3-a3b-trace-and-source-verification-20261111`.
2. Run `python tools/verify_evidence.py --root "C:\Users\justi\Desktop\pulseunity\ChatGPTCode"` using available Windows Python 3.13; report exact exit code and counts. Do not reinstall Python or BGE. Preserve the initial R3-A3 metadata grading baseline.
3. Inspect the local source of `r3a2_eval.py` and adjacent ranking/SQL/filter code at the verified 26 Oct hashes; map candidate generation → eligibility → exclusion → ranking → verdict → `links[:5]` export. Publish source path, SHA-256, line references, a decision-flow diagram, and testable hypotheses. **Do not assume the omitted ranks 6–10 explain a verdict.**

## Forensic priority
- `exclude_diwali`: establish exactly whether the `FAIL_EXCLUSION_LEAK` comes from candidate ranks 6–10, pre-/post-filter logic, semantic normalization or an evaluator mismatch. Compare the actual exclusion criterion against *all* candidates, not merely the five displayed. Do not assert PASS without the full trace.
- `event_series_2`, `event_series_3`, `x09`, `catalog_history`, `x14`: identify whether missing 2023/2024/2025 Open House editions are absent from corpus, misidentified, excluded, de-ranked, or truncated at export.
- `exclude_games`, `x12`: separate exclusion correctness from 'festival' relevance and noise.
- `x21`: explain `FAIL_FACT_STATUS` vs `ABSTAIN_FACT_UNVERIFIED` without making unsupported factual assertions.

## Candidate evidence rules
1. Search **existing local reports/logs only** for the untruncated candidate lists, raw scores, source IDs and rejection reasons. If found, create a deterministic **read-only** extractor (not new rankings) and produce baseline/BGE per-probe rows for all **54** cases, including ranks 1–10 where originally generated. Record missing fields as `NOT_CAPTURED`. Keep raw sensitive material out of Git.
2. If no full candidate trace exists, return `TRACE_NOT_RECONSTRUCTIBLE_FROM_FROZEN_EXPORT` with source-level proof. A re-run is **not automatically authorised**; document a minimal isolated, frozen, read-only plan (exact model rev/hashes, index hash, commands, expected outputs) for separate approval. Never download new model dependencies just to make this gate pass.
3. For the **25 priority cases**, verify authoritative evidence available from captured, rights-cleared sources, recording URL, publisher identity, observed/capture date, content hash where lawfully available, edition precision, and limitation. Live pages in Nov 2026 are not presumed to be identical to Oct 2026 snapshots. Do not copy publisher page bodies into Git. Use limited factual notes and references; if source content is absent, record `SOURCE_UNVERIFIED`.
4. Produce a **blind independent reviewer pack** for all 54 probes (25 highlighted): anonymised engine A/B, complete top-k list when available, document year/edition, exclusion relevance and 0/1/2/3 relevance fields. No automated or self-generated labels may be called human sign-off. Have separate flags for source-supported facts, negative-query abstention and incomplete candidates.
5. Set out metrics that can genuinely be calculated from evidence: P@1, P@5, MRR@5, noise@5, constraint and exclusion violations. Calculate recall only if judged ground-truth/corpus coverage exists; distinguish engine labels from independently verified grades. Do not infer 54 independent judgements.

## Required Git outputs (sanitised)
- `docs/R3A3B_SOURCE_TRACE.md` — line-anchored logic, hypotheses, evidence and adjudication status;
- `docs/R3A3B_SOURCE_VERIFICATION.md` — timestamped primary-source checks and limitations;
- `docs/R3A3B_DECISION_AND_HOLDS.md` — per-gate PASS/PARTIAL/HOLD, no production promotion;
- `docs/r3a3b_candidate_trace.csv` — if available, immutable engine-specific candidate rows, otherwise explicit evidence gap;
- `docs/r3a3b_blind_reviewer_pack.csv` — 54 probes, no invented sign-offs;
- `docs/r3a3b_checksums.sha256` plus executable read-only checks/tests, sample commands and logs.

Commit on `fb2/r3-a3b-trace-and-source-verification-20261111` with meaningful SHA, open a **draft PR** against main and link it here. Do not merge. If one gate blocks, continue unrelated safe work. Report which findings are reproduced from files vs inferred vs newly obtained. End with precise next executable engineering action, but **do not start R3-A4**.

**Acceptance:** deliver a trace-supported resolution or explicit unresolvable status for the exclusion/series anomalies, primary-source provenance for assessable priority cases, a true blind-review packet and protected Git evidence. Final independent grading and production remain on HOLD until review.
