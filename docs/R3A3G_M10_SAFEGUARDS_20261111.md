# R3A3G M10 — close the remaining safeguards

M10 is a narrow follow-up to the M9 review. It corrects the four remaining
safeguards and keeps the M9 evidence/navigation boundary.

## Changes

### UNA staging identity

The staging test now uses `BxDolDb::lastId()` immediately after its own insert,
rather than selecting `MAX(id)`. Concurrent activity cannot make it identify or
delete another editor's block.

### Transaction and restart safety

`UnaWikiBackend::write()` and `retract()` lock the block row with
`SELECT ... FOR UPDATE`, then re-read the latest revision inside the transaction
and hold the lock until commit. Editor profile IDs are persisted.

`WikiPublisher` accepts an optional receipt path. Receipts are written under a
file lock and reloaded by a new publisher instance, so idempotent retries survive
a process restart. The adapter test exercises that restart path.

### Revoked pages stay revoked

`StagingIndex::add_document()` now refuses to clear `revoked` implicitly. A
previously revoked URL returns
`revoked_requires_explicit_admission`; reactivation requires the explicit
`allow_reactivation=True` decision. The M8 test covers both outcomes.

### Evidence classification and retrieval

Cards now expose:

- `support_basis: "content"` or `"metadata_assisted"`
- `evidence_class: "source_excerpt"` or `"curator_metadata_navigation"`
- `verified_fact: false`
- a source kind that distinguishes indexed excerpts from metadata navigation

Metadata-assisted cards are navigation, not fact evidence. The API receipts and
result types carry the distinction to PUKE. Longer result sets drop incidental
secondary cards below the relative score floor.

Redirects to another subdomain now trigger that host's robots check before the
redirect request is allowed, with the same attempt and pacing gate.

## Evidence

- M8 source capture: **10/11 HTTP 200**; Berlin museums remains a documented
  redirect failure.
- M8 demo: **13/14** useful specific or official results; one no-evidence result.
- Standalone authenticated API/PUKE client: **10 questions**
  - **4 with source excerpts**
  - **4 with metadata navigation** (one question has both an excerpt and
    metadata-only candidates)
  - **2 official navigation**
  - **1 no evidence**
- Frozen M8 evaluation after M10:
  - nDCG@5 **0.608**
  - returned-link Precision@3 **0.394**
  - fixed-denominator Precision@3 **0.212**
  - helpful top-1 **0.591** (13/22)
  - judged top-five **15**
- Python suite: **278 tests OK** on the clean retry. The first full run hit the
  known Windows `WinError 10053` socket abort in
  `test_scope_denies_wiki_write_for_search_only_token`; the retry passed. Both
  logs are retained.
- UNA guard: **9/9**
- UNA adapter tests: **12/12**
- UNA staging: **10/10**

## Remaining limits

- UNA page creation still requires operator UI approval; HTTP/session/CSRF is
  not validated.
- No SearXNG endpoint is configured; provider leads remain unverified.
- The API still returns an unrelated Christmas page for “Berlin museum opening
  hours”; it is not presented as a verified fact.
- The M8 evaluation is internal and not an independent open-web benchmark.
- No production deployment, uncontrolled crawl, crawler admission, public Wiki
  publication or paid integration occurred.
