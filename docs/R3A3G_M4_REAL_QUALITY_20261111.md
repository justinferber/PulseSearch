# R3-A3G M4 — corrected real-source grading and Wiki integrity

**Date:** 11 November 2026 · **Branch:** `fb2/r3-a3g-broad-search-query-intents-20261111` · **PR #11 draft.**
No production promotion, crawler admission or public Wiki publication occurred.

## Evaluator correction

The previous `HUMAN_GRADED` label was wrong: PASS was assigned from domain and term overlap.
The evaluator now reports automatic domain metrics separately from a signed manual grade.
Recall@3 counts only a matching domain at rank 1–3; MRR uses the matching rank. The legacy
receipt is preserved as `docs/evidence/r3a3g_real_source_eval_legacy.json` and its ranks are
recomputed under the strict rule.

| Measure | Legacy reported | Legacy recomputed | M4 |
| --- | ---: | ---: | ---: |
| Auto domain matches | — | — | 8/15 |
| Recall@3 | 0.733 | 0.667 | **0.533** |
| MRR | 0.650 | 0.650 | **0.467** |
| Human PASS / PARTIAL / FAIL | 11 / 0 / 4 (mislabel) | — | **4 / 3 / 8** |
| Top-1 helpful | — | — | **4/15** |
| Correct answer | — | — | **5/15** |
| Wrong city / duplicate links | — | — | **0 / 0** |

The lower M4 recall is honest: stricter capture controls lost several previously captured pages,
and automatic domain matching is not an answer-quality claim. Individual top results and the
reviewer's reason are in `docs/evidence/r3a3g_real_source_eval.json`.

## Evidence verification

`config/wiki_evidence.json` now contains explicit `facts`, each bound to admitted evidence.
A Wiki claim must name a `fact_id` and its text must equal that admitted fact exactly
(after lower-case token normalisation). Shared words, a matching city or a domain no longer
pass. Negative tests cover refundability, a false date, an unknown fact, a swapped source,
a revoked source and overlapping city text. Claims without `fact_id` fail closed.

## Publisher acknowledgement

`_validate_receipt` runs inside the failure boundary. An explicit `ok=false` is recorded as
`safe rejection`; malformed or mismatched receipts are `needs_reconciliation` and cannot be
retried blindly. The previous published body stays intact. A post-ack local database failure
reconciles without a second external write.

## Real-source capture controls

`tools/r3a3g_capture_real_sources.py` now requires explicit owner approval and an
`evaluation_metadata_only` rights class for every source. Requests pass through the reviewed
`Fetcher` (DNS/private-IP guard, pinned connection, bounded redirects), per-hop same-registrable-
domain checks, robots.txt fail-closed, a per-source attempt ceiling and 3-second host pacing.
Only title and meta description are retained.

19 sources were attempted. Usable 200 responses included CSD Berlin, BVG, TfL, Glastonbury,
visitBerlin Christmas markets, visitBerlin, and BBC's Glastonbury 2027 report. Real failures
included DNS failures (arena, Huxley), connection reset (Eventim), 403 (London Parade), 404
(London fireworks), 410 (old Berlin concert/Christmas URLs) and redirect loops (Berlin events,
Glastonbury 2027). Missing sources are coverage gaps, not evidence to fabricate.

## PUKE privacy and chain

Client and API now share strict public-only schemas. Unknown nested fields are rejected,
sensitive key names are denied, and email/phone material is rejected at both boundaries.
The demo records search → answer claim evidence → Wiki draft (`DRAFT_ONLY`) and proves nested
member context is blocked. No provider is called.

## UNA adapter review branch

The adapter was checked for secrets and pushed to the **private** correct repository:

- repository: `justinferber/pulse-unity-marketplace` (private)
- branch: `review/pulse-search-wiki-adapter-20261111`
- commit: `a9bf576`
- path: `adapters/pulse_search_wiki/`
- PHP 8.3: syntax clean, 12/12 in-memory checks pass.

This is not a staging-UNA receipt. No isolated UNA database/editor account was available, so
draft/update/conflict/revocation have not been exercised through the real `bx_wiki` form/CSRF
path. Writes remain disabled by default; no public Wiki write is claimed.
