# R3A3G M11 — safeguards and ordinary-question relevance

Date: 2026-11-11
Status: engineering review candidate; **not** production or release approval.
Branches: Pulse Search `fb2/r3-a3g-broad-search-query-intents-20261111` (draft PR #11);
UNA review branch `review/pulse-search-wiki-adapter-20261111`.

## Scope

M11 closes the four findings in the M10 independent review and uses the ten existing
standalone-API questions as the regression set. It does not add a synthetic benchmark,
a public Wiki page, a production write or an uncontrolled crawl.

## 1. Crash-safe Wiki retries

`WikiPublisher` now binds an idempotency key to a SHA-256 hash of the exact submitted
payload. A retry with the same key and payload returns the recorded result; the same key
with a different payload is rejected as a conflict. The local receipt file is validated,
merged under an exclusive lock and remains backward-compatible with older receipts.

`UnaWikiBackend` now stores the receipt in `pulse_search_wiki_receipts` in the same
transaction as the revision insert or block deactivation. The block row is locked before
the receipt and revision state are read. The receipt table is created before the
transaction; no DDL is issued while the transaction is open. A crash before commit loses
both the write and the receipt; a crash after commit leaves both. A concurrent publisher
waits on the block lock and then observes the receipt.

Checks:

- `run_tests.php` — 12/12, including restart retry and different-payload conflict.
- `una_staging_test.php` — 13 checks, including a payload-bound receipt in the real UNA
  staging database and an idempotent publisher restart that adds no revision.
- `una_safety_test.php` — 9/9 staging and approval guards.

## 2. Authorised revocation reactivation

`StagingIndex.add_document()` no longer treats `allow_reactivation=True` as sufficient.
Re-admission must include `reactivation_approval` with `approved_by`, `approval_ref` and
`approved_at`; the approval is merged into the stored provenance. A request without a
recorded approval returns `reactivation_approval_required` and leaves the revocation in
place.

Covered by `test_index_preserves_m8_metadata_and_revocation`.

## 3. Navigation is not an answer

Search cards already distinguish content support from curator metadata. M11 adds a
response-level `NAVIGATION_ONLY` mode when every result is metadata-assisted. PUKE now
returns `Answer.status = NAVIGATION_ONLY`, with `indexed_navigation` citations and an
explicit statement that no fact was extracted; it never opens with
`From the indexed page ...`. `/v1/answer` maps that status to `NAVIGATION_ONLY`.

Covered by the metadata test in `test_r3a3g_m8.py` and the real-source answer regression
in `test_r3a3g_m11.py`.

## 4. Ordinary API relevance

The ten existing poor/frozen API questions are now regressions over the admitted
real-source snapshot. Changes:

- museum questions exclude non-museum pages, so Berlin museum hours no longer return
  Christmas markets and London museum access no longer returns theatre pages;
- city-scoped transport/events exclude pages for another city;
- German refund questions keep German consumer guidance and drop GOV.UK consumer pages
  (and the reverse for UK questions);
- NHS 111 returns the NHS 111 official entry point;
- when support is enforced, pages with no support for the question are withheld, removing
  the unrelated passport secondary cards.

Current ten-question API evidence
(`docs/evidence/r3a3g_m11_api_demo.json`):

```json
{
  "questions": 10,
  "with_indexed_result": 2,
  "with_metadata_navigation": 4,
  "with_official_navigation": 3,
  "no_evidence": 1
}
```

The categories overlap where a response contains both a content card and metadata
navigation. The remaining no-evidence case is the deliberately unknown “Moon Parade”
question; it stays honest rather than inventing a route. Four metadata-navigation cases
return specific official pages but are not quoted as facts.

## Verification

- Python full suite: **285 tests, OK** (includes 7 M11 real-source regressions).
- API test repeated **8/8 OK** after draining POST bodies before early 401/403/429
  responses; this removes the Windows `WinError 10053` reset caused by unread request
  bytes on a closing keep-alive socket.
- UNA: 12 adapter, 13 staging, 9 safety checks — all passed.
- `git diff --check` clean.

## Residual limits

- `berlin-museums` source capture still ends in a 301 redirect loop; the source snapshot
  remains 10/11 and no source was silently substituted.
- No SearXNG endpoint is configured; provider status remains `NOT_CONFIGURED`.
- M11 is a loopback/API and staging-database review candidate. No production deployment,
  public Wiki publication or uncontrolled crawl was performed.
- The metadata-navigation cases are useful navigation, not verified live facts; dates,
  prices, access and availability still require the source page.
