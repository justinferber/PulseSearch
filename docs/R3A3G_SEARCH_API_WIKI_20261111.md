# R3-A3G — Secure search, PUKE API and Wiki publication boundary

**Date:** 11 November 2026 · **Branch:** `fb2/r3-a3g-broad-search-query-intents-20261111` · **PR #11 draft.**
**PR #10 remains separate.** No crawler admission, production activation or live UNA Wiki publication occurred.

## 1. P0 Wiki and API fixes

| Review finding | Fix |
| --- | --- |
| Publishing failed open | `WikiService` now constructs a fail-closed `WikiPublisher()` by default. `LocalPublisher` is injected only by tests and local demos. A missing adapter cannot publish. |
| Pending revision could replace the published body | Published and pending states are separate. `publish` builds an immutable `WikiRevision` from the pending snapshot; an update does not overwrite the published body until the receipt is acknowledged. |
| Caller-supplied URLs counted as evidence | New `evidence.py` + `config/wiki_evidence.json` admit evidence by source id, topic, rights and publisher/domain independence. Caller URLs are rejected. Claim checks require supporting admitted evidence. |
| Unscoped API tokens | API v1.1 uses per-consumer scopes: `health:read`, `search:read`, `answer:read`, `wiki:propose`. Missing scope returns 403. |
| Concurrency and rollback | Wiki transactions and the API rate limiter are thread-safe. Writes use idempotency keys and attempt records; failures roll back local state and leave the prior revision intact. |
| Unattributed answer sentences | `/v1/answer` returns sentence-level `claim_evidence`; unsupported sentences are labelled rather than presented as sourced. |

The legacy `build_server` string-token path deliberately grants read-only scopes
(`health:read`, `search:read`, `answer:read`). Tests and demos pass explicit
`Consumer` objects with `wiki:propose` only where needed.

## 2. Real-source coverage and human grading

`config/real_sources.json` contains 15 manually chosen Berlin/London sources for
concerts, fireworks, Pride/CSD, festivals, transport and general questions.
`tools/r3a3g_capture_real_sources.py` captures one page per source and records
the HTTP result; this is **not** crawler admission and does not mutate the
accepted owner index.

Latest capture/evaluation (`docs/evidence/r3a3g_real_source_snapshot.json`,
`docs/evidence/r3a3g_real_source_eval.json`):

| Measure | Result |
| --- | --- |
| Queries | 15 |
| Human-graded pass / fail | **11 / 4** |
| Recall@3 | **0.733** |
| MRR | **0.650** |
| Wrong-city results | **0** |
| Duplicate result sets | **0** |
| Missing expected sources | **6** |
| Official-handoff-only answers | **2** |
| Captured pages / domains | 8 / 8 |

Remaining failures are honest gaps, not hidden by the evaluator:

- **Berlin concert official seller** — no captured arena/Eventim/Huxley page; the
  query returns Berlin guides and S-Bahn instead. Official links are available,
  but they are navigation, not admitted results.
- **Berlin Christmas market public transport** — BVG/S-Bahn official links are
  available, but the admitted result is the visitBerlin Christmas guide only;
  no admitted page combines Christmas-market intent with transport.
- **Concert accessibility and bag rules** — venue pages were unreachable, so the
  result set contains unrelated Berlin pages.
- **Eventim Berlin concerts** — Eventim capture timed out.

Capture gaps include `410` for the old Berlin concert/Christmas URLs, `404` for
the London fireworks URL, and connection/timeout failures for the arena,
Eventim and Huxley hosts. These are reported as capture gaps, not as proof that
a source is permanently invalid.

## 3. Retrieval changes from the failures

- Added transport recognition for `S-Bahn`, `sbahn`, `Fahrplan` and journey
  planner phrasing. Reviewed BVG/S-Bahn/TfL links are now exposed as an explicit
  `related_official_links` handoff.
- Official cards are **not** prepended to admitted results. That earlier change
  displaced a genuinely relevant indexed page in the evergreen retrieval test.
  The correct behaviour is: admitted pages first; official navigation separate.
- Ranking remains lexical + FTS5 BM25 + authority + recency, with URL/title
  dedup, host diversity and explainable reasons. The human failures above remain
  the next ranking work, not something the evaluator declares solved.

## 4. PUKE client and API

`pulse_search_broad_r3a3g/client.py` is a standalone client of the versioned API.
It handles bearer auth, request ids, timeouts, response validation, reliable
links, claim evidence, no-evidence states and client-side blocking of nested
member context.

`tools/puke_client_demo.py` runs 6 arbitrary questions:
`OFFICIAL_LINKS`, `NO_EVIDENCE`, `ANSWERED`, `NO_EVIDENCE`, `NO_EVIDENCE`,
`NO_EVIDENCE`; the Wiki candidate is `update_draft` and `DRAFT_ONLY`. Each case
also records `search_status` and up to three reliable links, so a no-answer
response is still actionable.

`tools/r3a3g_api_demo.py` passes **9/9** fixtures: unauthenticated 401,
health/capabilities/search/event/weather/no-evidence/wiki 200, and a
scope-denied Wiki request 403. Evidence: `docs/evidence/r3a3g_api_demo.json`.

## 5. Real UNA Wiki adapter

The real implementation is the installed UNA `bx_wiki` module, not the
marketplace review clone:

- `inc/classes/BxDolWiki.php` — ACL `isAllowed()`, `actionAddPage()`,
  `actionAdd()`, `actionEdit()`, revisions and translations.
- `inc/classes/BxDolWikiQuery.php` — page/block lookup and revision reads.
- `modules/boonex/wiki/install/sql/install.sql` — exact page, block and
  revision schema.

The write paths are login/CSRF-bound form actions; there is no public JSON API.
The adapter now lives in the separate Pulse UNITY repository at
`PULSE_UNITY_UNA_RC1_REVIEW_20261107/adapters/pulse_search_wiki/`.

It provides:

- payload checksum, independent-source and editorial-approval validation;
- live ACL checks through `BxDolWiki::isAllowed()`;
- optimistic concurrency (`base_version`) and idempotent retries;
- explicit retraction with reviewer and reason;
- writes **disabled by default** (`WikiWriteDisabled`), and page creation blocked
  until exercised through the UNA operator UI on a staging instance.

Verified under PHP 8.3 in Docker: syntax clean and **12/12** in-memory checks for
draft creation, update, idempotent retry, stale revision, checksum mismatch, ACL
denial, missing approval, revocation and audit. No live Wiki write occurred.
Remaining blocker: the review clone does not contain the module, no UNA staging
database/editor account was supplied, and this host has no native PHP CLI.

## 6. Verification

- `python -m unittest discover -s tests -p "test_r3a3*.py"` — **247 tests, OK**.
- Real-source evaluation — 15 queries, 11 pass, 4 fail, metrics above.
- API fixtures — **9/9**.
- PUKE client — **5 tests OK**, 6-case demo.
- Wiki P0 suite — included in the 247.
- UNA adapter — PHP 8.3 syntax + **12/12** in-memory checks.
- Browser console: `/`, `/search`, `/wiki`, `/api/wiki`, `/api/ask` served from
  `data/r3a3g_wiki/wiki.sqlite` (local test data only).

## Honest limitations

1. Real-source coverage is 8 captured pages across 8 domains, not an open-web
   benchmark; 4 of 15 human queries still fail.
2. Eventim, the arena venues and the old Berlin event URLs could not be captured.
3. No search-provider discovery is configured, so ephemeral discovery is not
   demonstrated live.
4. The UNA adapter has not run against a real staging database or editor account;
   only the in-memory state machine and PHP syntax are verified.
5. The local Wiki database and dashboard are demonstrations. No public or live
   Wiki content was created.
