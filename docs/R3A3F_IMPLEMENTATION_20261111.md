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
| Fetched (four phases) | 144 |
| Accepted | 70 (69 searchable documents; 1 updated) |
| Acceptance yield | 48.6% (synthetic — **not** a real-world yield) |
| Categories covered | **18/18** |
| Depth histogram of fetched URLs | 0: 8, 1: 40, 2: 28, 3: 6 |
| Deepest fetch | 3 |
| Depth-4 sentinel hits | **0** |
| Robots requests | logged `outcome="robots"` and paced on the same host schedule as content |
| Robots-denied fetches | 0 (denied URLs never reached the network) |
| Sites with broken robots (503) | 1 request total: `/robots.txt` only; content never fetched |
| Duplicate rejections | 24 exact, 1 near |
| Rate-limit responses handled | 10 across the four phases (`Retry-After` honoured, host paused) |
| 404 rechecks scheduled / recovered | 5 scheduled, 1 recovered to 200 and indexed |
| Discovery provenance | 8 seeds, 72 genuine link discoveries, 2 reviewed probes (no fabricated parent) |
| Useful discoveries | 14 intent-bearing documents; 10.6 per 100 fetches |
| Mean / p95 latency | 7.3 ms / 23 ms (loopback) |
| Off-domain hosts proposed | recorded, none crawled |

Gate checks: **23/23 PASS** — the original 15 (depth ≤3, robots denial, robots 5xx fail-closed, noindex exclusion, duplicate rejection, cultural events discoverable, 18/18 coverage, ≥100-page network, restart recovery, conditional recrawl, source revocation, rate-limit backoff, no unapproved hosts, owner index untouched, frozen 54 replay unchanged) plus fail-closed admission by default, probe provenance without a fabricated parent, 404 recheck recovery, per-source fairness under budget, measured useful discoveries, separate genuine-link versus guessed-probe counts, and the out-of-season Christmas listing recovered after a 404.

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

## Tests

* `tests/test_r3a3f_units.py`, `test_r3a3f_safety.py`, `test_r3a3f_crawl.py`, `test_r3a3f_discovery.py`, `test_r3a3f_prepilot.py` — **83 tests, all passing**; `test_r3a3f_prepilot.py` is one class per review correction.
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
