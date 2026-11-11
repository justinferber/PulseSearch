# Pulse Search — R3-A3C source recovery, frozen replay and independent grading

**Date:** 2026-11-11. **Project:** standalone Pulse Search, not Pulse UNITY Events, UNA, PulseChat or ARIES. **Status:** authorised research and validation only. No production promotion.

## Why

Pulse Search previously proved genuine independent sitemap discovery, locally owned SQLite/FTS indexing and query retrieval. A single frozen October R3-A2 comparison found 19/54 hybrid and 27/54 gated BGE engine-labelled retrieval passes, eight reported recoveries and zero reported regressions. The R3-A3 54-case workbook contains title/URL-level preliminary grades, not accepted independent judgements. Existing Git commit `608cfd679b564f69af81d0f80229c2375f37ef7e` preserves **reports/manifests**, not the complete crawler, indexer, API, historical source and original tests.

## FB2 executable work, in order

1. **Reconcile Git / avoid fake history.** Check out `fb2/r3-a3c-frozen54-replay-and-history-20261111`; keep `main` untouched. Confirm source commit, worktree cleanliness and file hashes. Continue work in R3-A3B Issue #2 where available; this assignment is the replay and history consolidation workstream. Do not claim that historical archives represent original dated Git commits.
2. **Recover the real engine.** Search owner local `C:\Users\justi\Desktop\pulseunity\ChatGPTCode`, prior ZIPs, live source trees and existing (non-PulseSearch) Git histories for original crawl/discovery, robots/sitemaps, canonicalise/deduplicate, SQLite FTS/owner index, API, benchmark fixtures, runner scripts and tests. Build a provenance ledger for each milestone (R2-P14B, R2-P18, R2-P27C, R2-P35, R3-A1, R3-A2, R3-A3), recording source path, SHA-256, original date, source Git SHA if genuinely known, test result and imported location. Absence must be explicit.
3. **Backfill safely.** Import verified, licence-compatible SOURCE CODE, frozen fixtures, read-only non-sensitive reports, tests and docs to the dedicated private Git repository in stages. Preserve code changes and chronology through honest import commits with original source SHA/timestamps cited as metadata, not fabricated author dates or original Git ancestry. Never import SQLite owners' full DB, weights, large binaries, venv, secrets, auth tokens, publisher bodies, .env or credentials. Store exact hashes and expected local paths in manifests.
4. **Freeze the questions.** `data/frozen_54.csv` contains exactly the 54 historical question IDs and wording, copied from the prior owner workbook/ledger. No query should be edited, removed or replaced to improve a score. Preserve 6,476-phrase background baseline separately: do NOT confuse it with the 54 benchmark queries.
5. **Run the historical questions again on the genuine engine.** First verify the accepted owner index SHA-256 `bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d` and model manifest `3955a9a2ca390314555ddb6a11b2ed16210657b689cab1b8e708653d3c63c437`; verify binaries/source provenance, interpreter/CPU compatibility and nonmutating access. Read the actual restored CLI/API contract rather than guessing arguments. If WSL remains broken, use a proven isolated native environment; do not restart WSL, Docker or production. No unreviewed downloads/substitutions. If runtime unavailable, publish REPLAY_NOT_RUN with precise blocker.
6. **Compare two modes against exactly the same frozen corpus:** accepted hybrid lex/FTS baseline and gated local BGE retrieval. For *each* 54 probe and each engine record: UTC run timestamp, source Git SHA, locked config, read-only index SHA before/after, source/model hashes, query ID/text, entire top 10 (including zero-result receipt), score, document canonical ID/title/URL/edition, exclusion and filter decisions, timeout/error, latency and CPU/RAM measurement when available. Do not truncate to `links[:5]`. Never count a model rerun as independent human grading.
7. **Adjudicate anomalies.** Address `exclude_diwali` (engine leak vs displayed top-5 discrepancy), `event_series_2`, `event_series_3`, `x09`, `catalog_history`, `x14` (Open House series and edition recall), `exclude_games`/`x12` (festival relevance vs exclusion) and `x21` (fact status). Separate corpus absence from ranking/eligibility/filter errors, with full trace evidence.
8. **Independent grading.** Export a BLINDED A/B candidate CSV and separate private engine mapping. A reviewer without authorship of the algorithm grades all retrieved items 0–3 for query relevance, separately judges constraints/negative queries/source evidence and records reviewer identity. Do not manufacture human labels or pretend a model-authored grade is a human sign-off. The user has a prepared `PulseSearch_R3A3_Independent_Grading_and_Replay_20261111.xlsx` containing all 54 frozen questions; FB2 should use that schema as a guide and preserve human judgements separately from engine output. Source evidence must carry page identity and capture date; do not publish copyrighted page bodies.
9. **Run the grader (pure Python, no model required):**
   ```powershell
   python tools/grade_independent.py --frozen data/frozen_54.csv
   # Once real, blinded full-rank results and genuinely signed grade files exist:
   python tools/grade_independent.py --frozen data/frozen_54.csv --results path/to/blind_A_B_results.csv --grades path/to/signed_grades.csv --output path/to/new_report.json
   ```
   Until signed grades and explicit empty-response receipts exist, negative abstention and full-set search accuracy remain HOLD. Never infer recall@5 without known relevant-document ground truth.
10. **Independent discovery proof (separate from frozen replay).** Once the recovered original crawler can be run safely, perform a small, rights-respecting, controlled live read-only discovery of new URLs and API result retrieval, with robots/source checks, bounded requests, no paid API, no owner-index mutation and transparent provenance. A successful local lookup of 120 previously indexed pages does not prove *fresh* web discovery. Do not treat event-only performance as general search certification.
11. **Publish evidence and handover.** Commit cleaned code and checks to this branch, report exact source hashes, pass/fail deltas for all 54, signed labels if genuinely obtained, API discover/index/query proofs, time/memory measurements and remaining blockers. Open draft PR against `main`, link Issue #2 and the replay Issue, and request independent review. Never merge or unpause production autonomously.

## Required acceptance matrix

| Milestone | PASS evidence | Failure / HOLD |
| --- | --- | --- |
| Code history | Original executable crawler/indexer/API/tests with verified provenance and honest import commits | Only manifests/reports or unknown snapshots |
| Working API | Local test request returns real indexed results and trace with stable canonical identity | No runtime smoke |
| Replay | All 54 exact queries × both rankers, full top-10 or signed empty receipts, frozen hashes | Partial run, modified corpus, missing candidates |
| Search quality | Blind, independently signed top-k judgments and separate constraint/negative/source review | Historic automated PASS labels only |
| Independent discovery | Distinct newly discovered URLs and reproducible robots-respecting crawl proof | Lookup only / commercial API results |
| Performance | CPU/RAM/latency p50/p95/p99 from documented environment | Historic scores only |
| Factual reliability | Authenticated publisher evidence, capture date, abstention where uncertain | 0 verified factual answers |
| Production | Owner's explicit separate authorisation | ALWAYS HOLD here |

## Development after the gate

Continue as a **standalone, general-purpose search engine** with own discovery/crawler, indexing, source freshness and provenance, hybrid lexical-semantic retrieval, public-facing API with protections, multilingual/UK/Germany coverage research, and source-supported answers only after a separate factual gate. Preserve the original 6,476 search-phrase baseline and pursue zero paid-search-API dependency. Integrations to other products are future optional clients, never the engine's architectural dependency.

**Stop rule:** If full inference cannot run safely, continue source history recovery, static tests and blind-review preparation, but do not claim the engine is currently operational. No WSL shutdown or Docker disruption.
