# R3-A3G M8: Real information discovery and retrieval

Date: 2026-11-11  
Status: development evidence only. Production deployment, uncontrolled crawling,
unapproved source admission and public Wiki publication remain on HOLD.

## M8-A: source discovery and capture

`config/m8_sources.json` adds eleven specific public pages for the M7 gaps. The
controlled capture in `tools/r3a3g_m8_capture.py` uses the existing fetcher:
private-IP/DNS guard, robots check, bounded redirects, pacing and an explicit
rights class. It records title and meta description only.

Ten of eleven sources returned HTTP 200. The Berlin museums URL repeatedly
redirected (`301`) through the reviewed fetcher and is retained as a failed
receipt, not silently indexed. The capture is in
`docs/evidence/r3a3g_m8_source_snapshot.json`.

`pulse_search_broad_r3a3g/discovery.py` adds optional SearXNG discovery. It is
only allowed on a loopback-configured instance, returns metadata labelled
`UNVERIFIED_PROVIDER_LEAD`, and never fetches or admits those URLs. With no
provider configured it returns `NOT_CONFIGURED` honestly.

## M8-B: indexed metadata and ranking

The staging schema now preserves source authority, document type, language,
jurisdiction, specificity and provenance. Search ranking uses jurisdiction,
specificity and the existing authority/freshness signals. The API returns
`source_receipts` and `result_types` separately from
`unverified_leads`.

## M8-C: real examples

`tools/r3a3g_m8_demo.py` builds a local index from the M8 snapshot plus the
earlier receipts and runs 14 different questions.

Examples with specific indexed pages:

- Hamburg HVV ticket information → `hvv.de/en/deutschlandticket-en`
- London museum wheelchair access → `tate.org.uk/visit/accessibility`
- German concert refunds → Verbraucherzentrale advice
- UK passport renewal → GOV.UK passport application
- UK consumer refunds → GOV.UK consumer rights
- Berlin Christmas transport → visitBerlin Christmas markets

Examples that remain official navigation rather than indexed copy:

- Paris Pride/events → Paris city page
- London theatre refunds → GOV.UK guidance
- NHS 111 → currently a general reference handoff, not a specific answer

No-evidence example: the Moon Parade query returns no result instead of filling
the page with unrelated event/transport links.

## M8-D: standalone API

`tools/r3a3g_m8_api_demo.py` sends ten questions through the authenticated
loopback API. Five returned indexed pages, four returned official navigation,
and one returned no evidence. The API includes:

- `results` / `result_cards`
- `source_receipts`
- `result_types`
- `unverified_leads` (currently `NOT_CONFIGURED`)
- draft-only Wiki candidate support

Evidence: `docs/evidence/r3a3g_m8_api_demo.json`.

## M8-E: UNA boundary

The separate adapter commit adds:

- optional pinned database host/port identity (`StagingGuard`)
- a real transaction around revision insert + indexing refresh
- existing base-version conflict detection, idempotent publisher retries and
  scoped rollback/restoration
- non-destructive test cleanup that preserves another editor's revisions

Current checks:

- `una_safety_test.php`: **9/9**
- `una_staging_test.php`: **10/10**
- no production write, public publish, or page creation

The staging test still uses the existing `wiki-home` block 342. A dedicated
disposable page/block and the HTTP/session/CSRF operator path remain blocked by
UNA's page-builder side effects; this is a remaining requirement, not claimed
complete.

## M8-F: evaluation

`config/m8_questions.json` is a new 22-question English/German set, disjoint
from the M6 and M7 query sets. Labels were produced by the internal FB2 reviewer
after source capture; they are not an external blind review.

| Metric | M8 result |
| --- | ---: |
| Queries | 22 |
| Mean nDCG@5 | **0.620** |
| Precision@3 among returned links | **0.409** |
| Fixed-denominator Precision@3 | **0.197** |
| Helpful top-1 | **0.591** (13/22) |
| Judged top-five results | 17 |

Evidence: `docs/evidence/r3a3g_m8_eval.json`.

The lower result is expected and material: specific-page coverage is still thin,
the M8 source snapshot is only ten usable pages, and several questions still fall
back to city or government navigation. The result must not be presented as
open-web quality.

## Risks and remaining limitations

- No SearXNG endpoint is configured, so temporary web leads were demonstrated as
  a boundary but not exercised against a live provider.
- The Berlin museums capture is a redirect failure.
- The M8 judgements are internal and the set was written alongside this
  implementation, so it is not a blind holdout.
- Source pages provide metadata/short snippets only; no live dates, prices or
  availability are asserted.
- Page creation, operator HTTP/CSRF controls and public Wiki publication remain
  disabled.
- PR #11 and crawler PR #10 remain draft.
