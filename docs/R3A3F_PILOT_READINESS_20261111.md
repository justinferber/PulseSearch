# R3-A3F — final pilot-readiness report (closeout)

**Date:** 11 November 2026. **Status:** engineering ready for a capped pilot · **F3 = HOLD** ·
**`REAL_SOURCES_ADMITTED=0`** · **`THIRD_PARTY_CRAWLER_REQUESTS=0`** · **Production HOLD**.
PR #10 remains a draft; no scheduler, no deployment, no live crawl.

This report closes the three review findings and states, per source, exactly what permission is
still missing before the first external GET.

## 1. Closeout corrections

| Finding | Correction | Regression |
| --- | --- | --- |
| `robots.txt` redirects bypassed admission/pacing/budget | `Fetcher.fetch` now receives `_robots_redirect_gate` for the robots request: same origin as the admitted source, pacing wait + record **before** the hop, run request ceiling, and the daily attempt ledger via the fetcher's attempt gate. Every hop is written to `redirect_log`; a refusal fails closed (robots → deny-all, no content request). The loader also records the robots request *before* sending it, so the first hop sees a real previous request and waits. | `tests/test_r3a3f_closeout.py`: off-origin robots redirect blocked with zero target hits; same-origin redirect followed with two ≥3s gaps and three counted attempts; attempt cap stops before the redirect destination. |
| Committed SQLite WAL/SHM artefacts | Removed from Git tracking (`git rm --cached`), `.gitignore` extended with `*.sqlite-wal`, `*.sqlite-shm`, `*.sqlite-journal`, `data/*/`. Reproducible evidence stays in the JSON reports; databases are run artefacts. | `git ls-files` contains no database/WAL/SHM file. |
| Administrative routes could be searchable | `urls.is_administrative_path` covers `admin`, `administrator`, `adminpanel`, `wp-admin`, `wp-login.php`, `phpmyadmin`, `cpanel`, `backend`, `login`, `logout`, `signin`, `signup`, `register`, `account/login|register`, `user/login|register`; `is_indexable_shape` refuses them as `administrative_path` and `StagingIndex.add_document` refuses them again as defence in depth. | Admin links are never queued or fetched; a direct staging insert is refused and not searchable. |

## 2. Readiness by source

| Gate | City Hall | London Parade | Lord Mayor's Show |
| --- | --- | --- | --- |
| Robots reviewed (dated) | ✅ 200, allows `/events`, no Crawl-delay | ✅ 200, `Crawl-delay: 10`, search signalled yes / AI-train no | ⚠️ 404 — no robots.txt |
| Terms reviewed | ⚠️ re-use basis not recorded | ✅ Existing Destination Events approval confirmed by owner; exact data-use scope to document | ❌ terms forbid deep links and reserve all rights |
| Proposed path scope | `/events` only | none admitted; 5 review paths | none admitted; `RIGHTS_HOLD` |
| Owner authorisation | ❌ not recorded | ⚠️ owner attestation received; specific crawler/indexer scope not recorded | ❌ not recorded |
| Technical gates (offline) | ✅ | ✅ | ✅ |
| Ready for a first GET | **No** — needs rights basis + written admission | **No** — existing approval's precise crawl/indexing scope and explicit pilot admission to be recorded | **No** — needs licence or link-only arrangement |

Technical gates are shared and already demonstrated offline: depth 3, zero probes, one in-flight,
persisted 300 attempts / 20 accepted / 30 minutes per day, per-hop redirect authority, robots and
admin exclusions, pinned novelty, per-source dashboard and JSON export.

## 3. Priority — London Parade (Destination Events Ltd)

**Why first if permission arrives:** the highest event value of the three, a public 2027 edition,
a 10s Crawl-delay that is already respected, and no competing rights claim beyond the organiser's.
**Owner correction (11 Nov):** The project owner confirms that Destination Events has already granted approval and Mine Media is the official London Parade partner. Do not ask for redundant new organiser permission. Record the existing approval's actual data-use scope, source reference and signed owner admission before activating the crawler. The site carries an “All Rights Reserved” notice; do not presume unrestricted snippet rights without checking the existing arrangement.

### 3.1 The exact permissions to obtain (written, signatory, dated)

1. **Crawl permission** for `https://londonparade.com` (state the canonical host and how `www`
   redirects), for the user agent `PulseSearchFB2/0.1 (+contact)`.
2. **Path scope**: `/about/`, `/parade-location-timing/`, `/londonparade-participants/`,
   `/news-archive`, `/festivals/concerts/`, and the public 2027 edition and news pages linked from
   them; depth ≤3; explicitly **excluding** `/shop/`, `/takepart/`, `/account/`, `/contact/`,
   application forms, participant personal data and third-party ticketing hosts.
3. **Metadata indexing**: store and display title, canonical URL, publication/edition date,
   category and a short excerpt of **≤320 characters**; no full-text or page-body storage, no image
   or media copying.
4. **Link retention and display**: permission to keep the URL and snippet in a search index and to
   show a link back to the source, with attribution; confirm whether the index may be public or
   must stay internal to Mine Media/Pulse.
5. **Recrawl and freshness**: permission to recrawl at ≥24h (and ≤168h for 404 rechecks), using
   conditional requests; confirmation that the published `Crawl-delay: 10` applies to this agent.
6. **Removal and takedown**: a named contact and a target response time for removing a URL, snippet
   or whole source; confirmation that permission can be withdrawn prospectively.
7. **Edition accuracy**: agreement that the index may state “2027 edition, 1 January 2027” only as
   announced by the organiser, must label 2026 and earlier as past editions, and must not infer a
   future date from a previous year.
8. **Duration and scope of the permission**: start date, review date, whether it covers future
   editions, and whether it extends to an eventual public search product.

### 3.2 Authorised structured-data feed — the preferred alternative

Ask Destination Events whether they can supply, or authorise, a machine-readable feed of public
event metadata: edition/year, date and start time, route/landmark sections, programme and
performance listings, participant/band names intended for publication, ticket links and public
contacts. Useful formats: JSON or CSV over HTTPS, a documented API, or a publisher sitemap with
structured data.

Questions that determine whether it replaces crawling:

- Which fields are public and licensed for search display, and which are internal?
- Update cadence and whether an incremental “changed since” parameter exists.
- Authentication (key/OAuth/IP allowlist) and rate limits.
- Attribution, snippet length and link-back requirements.
- Whether the feed covers historical editions and cancellations.
- Licence term, revocation, takedown and whether it permits a public search index.

If a feed is granted it becomes a **separate input connector** with its own provenance, permission
record and tests. It is not a crawler depth shortcut, and its fields must be marked as
organiser-supplied rather than independently discovered.

## 4. Remaining permissions by source

**City Hall** — record the terms/re-use basis for fetching `/events` and indexing a title plus a
≤320-character snippet; confirm `/events` is the listing and whether it paginates; name the contact
and takedown recipient; write the owner admission with `owner_authorisation`. The 107-page baseline
is expected overlap and must not be reported as novelty.

**London Parade** — the owner has confirmed existing Destination Events approval and Mine Media's official partnership. Capture the scope of this existing authorisation against items 1–8 above (plus canonical host and 2027 paths), or identify a licensed organiser feed covered by it. Do not treat the owner as lacking organiser approval. Until a documented crawl/index scope and a separate pilot go/no-go are recorded, `approved=false`, `index_allowed=false`.

**Lord Mayor's Show** — the published terms permit linking only to the home page and forbid deep
links, framing and links from non-owned sites, and no robots.txt exists. Either obtain explicit
permission for automated discovery, snippet indexing and deep links, or adopt a link-only/licensed
metadata arrangement; confirm whether `procession.` and `api.` subdomains are in scope. Otherwise the
record stays `RIGHTS_HOLD`.

## 5. Verification (this closeout)

- **123 tests pass**, including the new closeout regressions.
- Six-origin demo **28/28**; three-source demo **30/30** — 40 documents (13 City Hall / 14 Parade /
  13 Show), depth 3, depth-4 fetches 0, zero requests while unadmitted, off-origin redirect refused,
  no admin/terms/shop/application requests, editions separated, duplicates rejected.
- Archived matrix **25/25 modules, 419 tests**; pinned index `bb8e5202…7368c35d` and frozen 54 replay
  `bf0bee88…` byte-identical.
- Console and JSON export retain all three candidates, per-source figures and novelty.

## 6. What is still not ready

Live robots, latency and rate-limit behaviour are untested; signed human grading is pending; there is
no scheduler and no production deployment. The first live GET requires the written permissions above,
a recorded `owner_authorisation`, and a separate explicit authorisation to start.

## 7. Owner correction — Destination Events approval confirmed (11 November 2026)

The project owner personally confirms **existing Destination Events approval for London Parade** and that **Mine Media is the official event partner**. That is an owner attestation of an existing approval, not a newly requested licence. The project should NOT repeatedly require the owner to seek approval from Destination Events as if it did not exist. The current conversation does not itself specify whether the previous approval explicitly covers automated website crawling, storing and publicly displaying excerpts, or the permitted paths/retention terms; these items must be recorded from the existing agreement or confirmed through a clear owner scope statement. This is an evidence-recording step, not a demand for redundant consent. See `docs/FB2_R3A3F_LONDON_PARADE_EXISTING_APPROVAL_20261111.md` and the updated three-source admission register. No flags were switched and no live crawler was started.
