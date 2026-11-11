# R3-A3E — proposed next standalone Pulse Search milestone

**11 November 2026 | Proposal only | No production activation, no crawling, no merge**

## Where the engine actually stands

| Capability | State |
| --- | --- |
| Accepted corpus | 120 pages / 120 FTS / 7 approved sources, hash-verified |
| Ranking | Hybrid lexical + pinned local BGE; reproducible offline |
| Constraint handling | Exclusion, year-set and series purity repaired in a candidate layer (`0` leaks, `0` regressions) |
| Coverage | Single-city event metadata; no global retrieval claim |
| Evidence integrity | 25/25 archived modules, 419 tests, byte-pinned fixtures verify |
| Human grading | **0 signed judgements** — the binding limit on every quality claim |

The constraint layer is a repair harness, not a product. It exists to prove the
defects were in the parse/filter layer rather than the corpus, and to give the
owner a measurable candidate to accept or reject.

## Milestone proposal: **S1 — Graded Event Search Core**

The next milestone should be gated on measurement, not on more feature surface.
Four staged gates, each with an explicit exit condition:

### S1.0 Grading closure (blocking)

Transfer the blinded workbook to this host, validate it with the committed
verifier and its fingerprints, run independent review, and consolidate signed
metrics. **Exit:** `SIGNED_HUMAN_GRADING > 0` with every candidate row signed and
the 25 priority cases double-graded, or an explicit owner decision to accept a
single-reviewer first pass as non-independent evidence.

Until this closes, no ranking claim above "reproducible" should be published.

### S1.1 Constraint layer acceptance decision

Present the measured delta (hybrid 19→29, BGE 27→33, zero regressions, zero
exclusion leaks at any rank) to the owner. **Exit:** either the layer is adopted
as the query front-end for the standalone API, or rejected with reasons recorded.
Either way the accepted October snapshots stay untouched; adoption means a new
versioned module, not an edit.

### S1.2 Multi-year and series as a first-class capability

The current repair decomposes years by re-querying. A real capability needs
series identity in the index: a series key, edition year as a typed field, and
retrieval that returns editions as a set rather than re-running the query per
year. **Exit:** typed series/edition fields populated for the approved corpus, and
edition coverage measured without query decomposition.

### S1.3 Bounded, robots-respecting discovery pilot

Only after S1.0 closes. A capped pilot against owner-approved sources with
explicit robots handling, per-host rate limits, recrawl validators, source
admission review and rights metadata. **Exit:** a documented crawl budget, zero
policy violations, and a larger independent index that still reproduces the
graded baseline.

## Deliberately out of scope for S1

- Global web coverage or a general-purpose search claim.
- Multilingual retrieval (no accepted evaluation set exists).
- Any paid-search dependency.
- Production promotion, public crawling, or merge to `main`.
- Rebuilding the corpus to make the frozen questions pass.

## Risk if the order is inverted

Shipping the constraint layer before grading would trade a reproducible,
honestly-labelled engine for a better-looking one with no signed evidence behind
it. The measured defects are fixed; the *quality* question is still open, and the
next milestone should close that before adding reach.
