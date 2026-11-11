# R3-A3F — depth-3 crawler implementation and offline results

**Date:** 11 November 2026. **Branch:** `fb2/r3-a3f-depth3-category-crawler-20261111`. **Status:** offline implementation complete and tested; **no third-party site has been contacted**; production **HOLD**.

## Package

`pulse_search_crawler_r3a3f/` (stdlib only, Python 3.12/3.13):

| Module | Responsibility |
| --- | --- |
| `config.py` | Budgets, 3-hop maximum, 3s host spacing, loopback opt-in that refuses live speeds |
| `urls.py` | Canonicalisation (tracking params, fragments, dot segments), trap detection (infinite pagination, repeated segments, session ids, assets), scope |
| `netguard.py` | Per-hop DNS resolution and public-address enforcement; metadata hostnames always blocked |
| `safe_fetch.py` | Pinned-IP HTTP(S), redirect chain re-validated hop by hop, response caps, gzip, `Retry-After` |
| `robots.py` | RFC 9309-style parser (longest match wins, allow wins ties), agent groups, 24h cache, fail-closed 5xx/401/403, paced loader |
| `pacing.py` | One host schedule shared by robots, content and redirects: uncapped waits, full `Retry-After`, injectable clock for tests |
| `extract.py` | Title, main text, links (nofollow aware), canonical, `noindex`, JSON-LD, dates |
| `classify.py` | One primary category + secondary labels + evidence, 18 fixed categories, explicit `uncertain` |
| `quality.py` | Normalisation, SHA-256 content hash, 5-gram shingles, Jaccard, thin-content gate |
| `store.py` | Durable sources/seeds/frontier/host-state/edges/rejections/sitemap-candidates/run journal |
| `staging.py` | Separate staging index (docs, shingles, FTS5, rejections, revocation) |
| `crawler.py` | The loop: depth admission, politeness, robots, quality, dedup, link discovery, report |
| `sitesim.py` | 103-route synthetic six-origin network |
| `dashboard.py` | Read-only local console + JSON download |
| `cli.py` | `sources`, `run`, `report`, `dashboard` |

## Traversal and admission

* Seed admitted by review = depth 0; a link found on a depth-*d* page is depth *d*+1; `depth > 3` is refused at enqueue with reason `depth_beyond_max` and again at claim.
* Canonical URL is the frontier key; rediscovery at a shallower depth lowers `min_depth` but never replays a fetched URL backwards. Tracking parameters and fragments are removed before the key is formed.
* Off-domain links are recorded as candidates only — no host is crawled because it was linked to.
* Sitemap URLs from `robots.txt` are stored with policy `candidate_only_requires_review`; they are never surfaced as depth-0 seeds.
* Rejected-but-parseable pages still expand in-scope links (a thin hub can be a useful discovery node); `noindex`, robots denial, canonical aliases and duplicates are dead ends.
* Recrawl uses `ETag`/`If-None-Match` and `Last-Modified`/`If-Modified-Since`; a `304` revalidates without reindexing, `403/404/410/451` revoke the staged document.

## Quality, rights and categories

A fetch becomes a document only if: robots permits it, the source row has `index_allowed`, the response is HTML, no `noindex`, text ≥ 250 chars and ≥ 20 words, category signal is not a weak *specific* label, and the content is neither an exact nor a ≥0.90 Jaccard near-duplicate. Pages that match none of the 18 facets are indexed as **Other** with `uncertain` recorded — a general search engine does not drop material merely because it has no Events category, and no label is invented. Body text is not stored: metadata and a ≤320-character snippet only, unless a source row explicitly carries a licensing basis.

Coverage is a mirror of the owner-confirmed 18 categories, read-only. Diwali, Pride Berlin, CSD Berlin and Stadtfest Berlin classify and stay indexed; query-local negation in R3-A3E never influences crawling or indexing.

## Offline results (evidence: `docs/evidence/r3a3f_offline_run.json`)

Run against six loopback origins, 103 routes, 18 categories:

| Measure | Value |
| --- | --- |
| Fetched (four phases) | 147 |
| Accepted | 70 (69 searchable documents; 1 updated) |
| Acceptance yield | 47.6% (synthetic — **not** a real-world yield) |
| Categories covered | **18/18** |
| Depth histogram of fetched URLs | 0: 8, 1: 40, 2: 31, 3: 6 |
| Deepest fetch | 3 |
| Depth-4 sentinel hits | **0** |
| Robots requests | logged `outcome="robots"` and paced on the same host schedule as content |
| Robots-denied fetches | 0 (denied URLs never reached the network) |
| Sites with broken robots (503) | 1 request total: `/robots.txt` only; content never fetched |
| Duplicate rejections | 25 exact, 1 near |
| Rate-limit responses handled | 10 across the four phases (`Retry-After` honoured, host paused) |
| 404 rechecks scheduled / recovered | 5 scheduled, 1 recovered to 200 and indexed |
| Discovery provenance | 8 seeds, 75 genuine link discoveries, 2 reviewed probes (no fabricated parent) |
| Useful discoveries | 14 intent-bearing documents; 10.4 per 100 fetches |
| Redirects | 4 hops followed inside the approved origin; 2 blocked (1 off-origin, 1 robots-denied) |
| Novelty vs pinned index | 69 staged, 69 novel, 0 overlap (loopback fixture), 120 historical pages |
| Mean / p95 latency | 8.3 ms / 24 ms (loopback) |
| Off-domain hosts proposed | recorded, none crawled |

Gate checks: **28/28 PASS** — the original 15 (depth ≤3, robots denial, robots 5xx fail-closed, noindex exclusion, duplicate rejection, cultural events discoverable, 18/18 coverage, ≥100-page network, restart recovery, conditional recrawl, source revocation, rate-limit backoff, no unapproved hosts, owner index untouched, frozen 54 replay unchanged) plus fail-closed admission by default, probe provenance without a fabricated parent, 404 recheck recovery, per-source fairness under budget, measured useful discoveries, separate genuine-link versus guessed-probe counts, the out-of-season Christmas listing recovered after a 404, off-origin redirect refusal, robots-denied redirect refusal, per-hop redirect logging, explicit CLI source admission, and read-only novelty measurement.

### The 1,000/day question

At the observed *laboratory* yield, 1,000 accepted pages would need ≈1,758 gross fetches/day, inside the 5,000 ceiling. That is arithmetic on a synthetic corpus, **not** a forecast: real yield will be lower and unknown until a pilot. Per-host spacing of 3 seconds caps one host at 28,800 requests/day, so the binding constraint is host count and rights, not throughput. Resource estimate for the ceiling: ~750 MB/day of traffic at 150 KB average, ~2 MB/day of metadata and snippets, and one modest CPU core; SQLite is sufficient for the pilot and would be revisited only after measured load.

## Dashboard

```
python -m pulse_search_crawler_r3a3f.dashboard \
  --db data/r3a3f_offline/crawl.sqlite \
  --staging data/r3a3f_offline/staging.sqlite --port 8787
```

Open http://127.0.0.1:8787/ — funnel, 18/18 coverage bars, target progress, schedule/depth, source and rights table, rejections, freshness, latency, robots/errors, staged-document table, and a staging search box (try `Diwali`, `CSD Berlin`, `Stadtfest`). `/api/report.json` and **Download JSON report** (`/download`) provide the machine-readable run for independent assessment. The console is read-only: it cannot start a crawl or write to the index.

## Discovery focus (added after the first offline run)

Breadth-first discovery spent the 3-hop budget on navigation and missed seasonal content. `topics.py` adds seven discovery intents (Christmas/Advent markets, Pride/CSD, open-air music, parades/carnivals, street/summer festivals, Diwali, New Year) with local-language terms, anchor-text scoring, listing-section probes inside approved paths, hub detection and seasonality. Intent only changes **fetch order and labels**; it never blocks a topic, host or category. Full detail: `docs/R3A3F_DISCOVERY_PROFILES_20261111.md`.

## Pre-pilot corrections (review of `e364304a`)

Five findings were fixed without rebuilding the crawler; the suite was extended, not replaced.

| Finding | Fix | Where |
| --- | --- | --- |
| Admission and indexing were effectively open | `add_source` defaults to `approved=False`, `index_allowed=False`, empty `probe_policy`; an admitted source cannot be silently de-approved or re-scoped on re-import; `add_seed` requires admission; `add_document` requires `index_allowed=True` | `store.py`, `staging.py`, `crawler.py` |
| Guessed listing pages looked like real links | Probes are a reviewed per-source `probe_policy` with `probe_budget_per_run`; stored as `guessed_path_probe`, `parent_url=NULL`, `approval_ref=source:<id>:probe_policy`; genuine links keep their parent and `approval_ref=link:<parent>` | `store.py`, `crawler.py` |
| Pacing could end early and skipped robots | `HostPacer` is the only path to the network: robots, content and redirects wait on one schedule; waits are never capped; `Retry-After` blocks the host for the full duration; robots fetch gets its own `fetch_log` row | `pacing.py`, `crawler.py`, `robots.py` |
| 404 was permanent | 404 → `state='recheck'` with a long TTL (168h for probes, 24h otherwise), reactivated at run start and bounded by `max_rechecks`; 410/451/403 stay permanent with distinct counters | `store.py`, `crawler.py` |
| Fairness and yield were asserted | `claim_next(avoid_host=…)`, a per-source share of the run budget with `host_deferred` as an explicit stop reason, per-source shares in the report, and `useful_discoveries` / `useful_per_100_fetches` | `store.py`, `crawler.py`, `dashboard.py` |

Evidence now distinguishes **admitted seeds**, **genuine link discoveries**, **reviewed probes**, **successful pages** and **rejected pages**, and reports each source's share of the run's fetches. Improvement ideas for later: `docs/R3A3F_PREPILOT_NOTES_20261111.md`; the pilot proposal is `docs/R3A3F_PILOT_SOURCE_PROPOSAL_20261111.md` (`PROPOSAL_ONLY_NOT_ADMITTED`).

## Pre-pilot security corrections (review of `a7f6d37`)

| Finding | Fix | Where |
| --- | --- | --- |
| CLI import defaulted missing approval/indexing fields to `True` | `load_sources` requires every admission field, rejects non-boolean flags, approval without a reviewed rights basis, indexing without approval, seeds for unknown or unadmitted sources and seeds outside the approved scope; `run` preflight refuses with no admitted source or an admitted source without a reviewed basis, before any request | `cli.py` |
| Redirect hops bypassed admission, scope, robots, budget and pacing | `Fetcher.fetch(redirect_gate=…)` calls the gate before every destination request; the gate refuses off-origin targets (even public or separately admitted hosts), out-of-scope paths, robots-denied paths and an exhausted request ceiling, and waits and records the host slot; every hop lands in `redirect_log` and in `report.redirects` | `safe_fetch.py`, `crawler.py`, `store.py` |
| Pilot scope was too broad | proposal narrowed to `https://www.london.gov.uk` + `/events` only, `/whats-on` removed pending verification, zero probes in Phase 1, every source unapproved, manual robots/terms review required, and read-only novelty against the 107 pages already in the pinned index | `docs/R3A3F_PILOT_SOURCE_PROPOSAL_20261111.md`, `docs/evidence/r3a3f_pilot_source_proposal.json`, `novelty.py` |

The run report and console now include a redirect section (followed and blocked hops by decision) and a novelty line (novel documents versus already-indexed ones), so a pilot cannot present re-crawled pages as new.

## Tests

* `tests/test_r3a3f_units.py`, `test_r3a3f_safety.py`, `test_r3a3f_crawl.py`, `test_r3a3f_discovery.py`, `test_r3a3f_prepilot.py`, `test_r3a3f_redirects.py`, `test_r3a3f_admission.py` — **97 tests, all passing**; `test_r3a3f_prepilot.py` is one class per admission/pacing/recheck/fairness correction, `test_r3a3f_redirects.py` covers per-hop authorisation adversarially, and `test_r3a3f_admission.py` proves the CLI cannot imply approval.
* Archived POSIX matrix — **25/25 modules, 419 tests passing** (`docs/evidence/r3a3f_regression_posix.txt`), with `historical/local_snapshot` byte-clean.
* Owner index SHA-256 `bb8e5202…7368c35d` unchanged before and after; frozen 54 replay `bf0bee88…` unchanged.

## Outstanding risks

1. **No live evidence.** Every number above is loopback; robots, latency, `Retry-After` and rights behaviour against real publishers are untested until an approved pilot.
2. **Robots parser scope.** Longest-match and agent grouping are covered by tests, but the full RFC 9309 conformance suite is not.
3. **No JS rendering and no PDF/Office extraction** — pages requiring either are invisible.
4. **Near-duplicate cost** grows with the corpus; the shingle join is fine at pilot scale, not at millions of documents.
5. **Rights model is metadata-level.** `index_allowed`/`store_body` are assertions from the source registry, not a licence.
6. **Uncertain/Other acceptance** widens recall; a pilot must measure its precision before scaling.
7. **Single-machine scheduler.** No distributed locking; two crawler processes on one database would duplicate work.

## Three-candidate expansion (second owner directive, 11 November 2026)

The owner selected three candidates and the crawler was prepared without admitting any of them.
`registry.py` and `docs/evidence/r3a3f_three_source_admission.json` hold the register with four
auditable states (`candidate`, `robots_reviewed`, `rights_hold`, `owner_approved`); every record is
`approved=false`, `index_allowed=false`, `owner_authorisation=null`.

Five pending operational gates were implemented:

1. **Pre-network URL admission.** `Crawler._precheck` verifies origin, exact path scope and
   `index_allowed` *before* robots.txt or content is requested, and writes every decision to
   `url_admission_log`. An out-of-scope or unindexable URL produces zero requests.
2. **Persisted pilot limits.** `pilot_budget` stores `http_attempts`, `accepted_documents` and
   `run_seconds` per UTC day. Every attempt — robots, content hop, redirect hop, retry — passes the
   fetcher's attempt gate. A restart reads the same row: it cannot reset the allowance.
3. **Run-duration and acceptance caps.** The loop stops at `run_minutes_cap_reached`,
   `accepted_documents_cap_reached` or `http_attempts_cap_reached`; the caps are reported in
   `report.pilot_budget`.
4. **Novelty SHA-256 pin.** `novelty.overlap` verifies the index hash before reading it, exposes
   `index_sha256`/`pin_match`, and raises `NoveltyPinMismatch` for any other file.
5. **Distinct owner authorisation.** A real host cannot be admitted by `approved=true` alone; the
   store, CLI import and run preflight require a documented `owner_authorisation` reference that is
   not a copy of the rights status. Synthetic fixtures keep an explicit exemption.

Offline fixtures (`sitesim.build_three_source_network`) mirror the audited shapes of the three
candidates, and `tools/r3a3f_three_source_demo.py` runs two phases: the unadmitted register (import
and run refused, zero requests) and the synthetic simulation (41 documents, 13/15/13 per source).

Evidence: **118 tests**, six-origin demo **28/28**, three-source demo **30/30** (depth 3, depth-4 0,
off-origin redirect refused, no `/whats-on`, `/shop/`, `/takepart/`, `/terms-of-use/` or `/book/`
request, 2027 and 2026 editions separate, duplicate syndication rejected, novelty pin matched, owner
index byte-identical), archived matrix **25/25 modules, 419 tests**.

## Closeout corrections (final review, 11 November 2026)

1. **robots.txt redirects are now gated.** The robots fetch passes `_robots_redirect_gate`: the
   destination must be on the admitted source's origin, the host pacing slot is waited for and
   recorded *before* the hop, and the run ceiling plus the persisted daily attempt ledger apply.
   The robots request itself is recorded before it is sent, so the first hop cannot be issued with
   no pacing gap. Every hop lands in `redirect_log`; a refusal fails closed and no content request
   follows.
2. **Run artefacts are no longer tracked.** The committed WAL/SHM files were removed with
   `git rm --cached`; `.gitignore` now covers `*.sqlite-wal`, `*.sqlite-shm`, `*.sqlite-journal`
   and `data/*/`. Reproducible evidence remains in `docs/evidence/*.json`.
3. **Administrative routes are excluded from search.** `urls.is_administrative_path` refuses admin,
   authentication, account and registration paths at admission, and `StagingIndex.add_document`
   refuses them again, so they can never become searchable even if inserted directly.

Closeout evidence: **123 tests**, six-origin demo 28/28, three-source demo 30/30 (40 documents,
13/14/13 per source), archived matrix 25/25 modules and 419 tests, pinned index and frozen replay
unchanged. See `docs/R3A3F_PILOT_READINESS_20261111.md` for the per-source readiness report and the
London Parade permission checklist.

## London Parade scope record (owner correction, 11 November 2026)

The owner confirmed that Destination Events' approval already exists and that Mine Media is the
official London Parade partner, so no new organiser approval is requested. Instead the existing
authorisation's technical scope is recorded: `docs/evidence/r3a3f_london_parade_scope.json` and
`docs/R3A3F_LONDON_PARADE_DATA_USE_SCOPE_20261111.md`, with an owner-facing activation checklist in
`docs/R3A3F_LONDON_PARADE_PILOT_ACTIVATION_CHECKLIST_20261111.md`. The source stays
`approved=false`, `index_allowed=false`, `owner_authorisation=null`, `state=robots_reviewed`.

Prepared scope: five reviewed paths, two reviewed seeds, depth 3, zero probes, 20 accepted documents
and 300 network attempts and 30 minutes per UTC day, metadata plus a ≤320-character excerpt, no body
storage, and the published **10-second Crawl-delay preserved as a per-source floor**
(`crawl_delay_floor_s`), independent of a future robots change. Exclusions are unchanged: shop,
application form, account, contact form, administrative/login routes, Ticketmaster and every other
host.

The narrowly outstanding review item is also closed: a same-origin `robots.txt` redirect to an
administrative path is now refused as `administrative_path`, alongside the off-origin, pacing and
budget checks. Evidence: 129 tests, six-origin demo 28/28, three-source demo 30/30, archived matrix
25/25 modules and 419 tests, pinned index and frozen replay unchanged.
