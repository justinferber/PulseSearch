# R3-A3F — existing crawler audit (read-only)

**Date:** 11 November 2026. **Scope:** what Pulse Search already had before R3-A3F, what was reused, and what had to be added. No third-party request was made to produce this audit; the owner's index was opened read-only and hashed.

## Where the previous crawler lives

The accepted October engine is archived byte-for-byte in `historical/local_snapshot/Pulse_Search_R3A2_Run_1psnjrhX/source_engine/` (pinned by `historical/SOURCE_IMPORT_MANIFEST_20261111.json`, 135 files). The relevant implementation is `pulse_search_engine.py`; the crawler is not a separate service — it is a set of functions around `Fetcher`, `crawl()` and the scheduler.

## What exists today

| Capability | Implementation found | Reused in R3-A3F? |
| --- | --- | --- |
| Safe fetch | `Fetcher.get()` with `PinnedHTTPS`/`PinnedHTTP`: DNS resolved once, connection pinned to the checked IP, TLS server name preserved | Concept reused; rewritten because the old fetcher checks only the first address and does not re-validate after a redirect |
| SSRF guard | `addresses()` rejects loopback/private/link-local unless `allow_local` | Same policy, applied per redirect hop |
| Depth limit | `MAX_DEPTH = 2`; `enqueue()` refuses `depth > MAX_DEPTH` | Raised to 3 with the same refuse-not-clamp semantics |
| Frontier | SQLite `frontier(url, source_id, depth, state, parent_url, last_seen, last_error)` | Extended: minimum-depth promotion, retry scheduling, per-host state, edges, rejections |
| Robots | `robots_allowed()` + `RobotFileParser`; engine tests already assert fail-closed on 503 and denial on `Disallow` | Rewritten as an RFC-9309-style longest-match parser with explicit agent groups and a 24h cache |
| Scope | `scope()` limits to one origin plus approved paths | Same, per source registry row |
| Sitemap | `sitemap_links()` parses `urlset`, refuses DOCTYPE/ENTITY, caps URLs | Deliberately **not** used for admission: R3-A3F records sitemap URLs as candidates only |
| Off-domain links | `record_external_candidates()` stores origin + referrer, never crawls | Same principle, separate table |
| Recrawl | `conditional_headers()` / 304 handling / `purge_page()` on 404/410/robots change | Same semantics, plus `next_recrawl_at` scheduling |
| Scheduling | `pulse_search_scheduler.py` (`scheduled_urls`, `run_cycle`, `run_bounded_loop`) | Not reused: R3-A3F needs a per-host queue, not a fixed URL allowlist per cycle |
| Quality audit | `pulse_search_quality.py` verifies DB integrity | Not reused; staging index has its own checks |

`crawl()` in the old engine is a single-origin loop with `max_pages` and `max_depth`; it never exceeds two hops, has no per-host scheduler, no category model and no separate index. Its robots and 304 behaviour is well tested (the archived matrix still passes on it).

## Recovered approved source families

`tools/r3a3f_source_audit.py` opens the accepted index read-only (`mode=ro`), verifies SHA-256 `bb8e5202…7368c35d` and lists the hosts that are actually represented:

| Host | Pages in accepted index | Status |
| --- | --- | --- |
| `www.london.gov.uk` | 107 | **Not yet admitted for crawling** — needs owner signoff + terms review |
| `www.gov.uk` | 4 | Not yet admitted |
| `www.nhs.uk` | 4 | Not yet admitted |
| `developer.mozilla.org` | 2 | Not yet admitted (technical reference) |
| `docs.python.org` | 1 | Not yet admitted (technical reference) |
| `www.rfc-editor.org` | 1 | Not yet admitted (standards reference) |
| `www.sqlite.org` | 1 | Not yet admitted (technical reference) |

Full machine-readable proposal: `docs/evidence/r3a3f_source_registry_proposal.json` (`status: PROPOSAL_ONLY_NOT_ADMITTED`). Presence in the index is **not** permission to crawl; each host needs an explicit admission row with a rights basis, and `bytebytego.com` / `nginx.org` remain references, not sources.

## Gaps this stage had to close

1. **No depth-3 traversal.** Old maximum was 2 and depth was clamped silently at enqueue.
2. **No persistent frontier across processes.** `crawl()` consumed rows inside one run; a crash lost in-flight work and depth provenance was not maintained across restarts.
3. **No per-host politeness scheduler.** Only a global `min_delay` between requests; no `Retry-After` handling, no host backoff, no daily budget ledger.
4. **No category understanding.** The engine has no classifier and no coverage reporting.
5. **No separate staging index.** Crawled pages went to the same research DB shape as accepted content, so newly discovered pages were not isolated from accepted evidence.
6. **No run dashboard or signed JSON run report.**
7. **Redirect handling** validated the first hop only; a redirect to a loopback/private address was not re-checked.
8. **No near-duplicate detection** beyond an exact hash of title+body.

All eight are addressed in `pulse_search_crawler_r3a3f/`; the accepted engine, its snapshot, the pinned index and the 54-case benchmark were not modified.
