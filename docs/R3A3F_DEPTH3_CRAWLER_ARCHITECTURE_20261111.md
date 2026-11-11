# R3-A3F — Standalone Pulse Search: depth-three, category-balanced crawler architecture

**Owner design request: 11 November 2026.** Status: **DESIGN / TEST BUILD APPROVED**, live third-party crawling **NOT STARTED**. This is **not** the Pulse UNITY Events Knowledge Engine, its publisher or its database. The UNA Events category taxonomy is read-only inspiration/coverage metadata for Pulse Search.

## Purpose and numeric target

Crawl links from previously accepted source domains, up to **three hyperlink hops from an approved starting seed**, to grow **approximately 1,000 NEW, relevant, deduplicated, source-policy-compliant, searchable pages per day** in an isolated Pulse Search staging index. A raw fetch is not an accepted page. Never manufacture the count or lower relevance and source-rights gates to reach 1,000. A smaller accepted count is an honest outcome. Report gross URLs discovered, fetched, eligible, unique, relevant, indexed and searchable separately; use a rolling 7-day view and source/category coverage. Optimize *useful new pages*, not HTTP request volume.

Definition of depth: seed page = 0; following a link = depth 1; second link = depth 2; third link = depth 3; do not *fetch* depth 4 from that seed. Track minimum depth on deduplication. Sitemap URLs are **discovery candidates** and must be classified under an explicit policy: either admitted as fresh depth-0 seeds by a reviewed seed-admission decision, or queued under the source-specific depth budget. Do not let a sitemap silently bypass the max-three-hops rule.

### High-level flow

1. **Source registry and seed intake.** Reconcile the existing 7 approved October source families with source registry and rights evidence. Take only exact admitted URLs/hostnames as active seeds; log source admission, site terms, robots decisions, purpose, contact and allowed paths. Recover previous accepted source corpus first, never blindly treat `bytebytego.com` or `nginx.org` as an event-content seed.
2. **Persistent URL frontier.** Durable queue with `url, canonical_url, source_id, parent_url, seed_id, min_depth, discovered_at, priority, last_fetch, next_retry, category_signals, attempts, robots_decision`. Deduplicate by canonical URL and content hash. Persist across crash/restart without resetting depth or replaying HTTP requests uncontrollably.
3. **Per-host politeness scheduler.** One in-flight request/host initially; configurable 3-second minimum gap between requests to a host, stricter if published rules/provider agreement requires; tokens/backoff and fair shares by domain and category. Never make 1,000/day a reason to overload a host.
4. **Robots and rights gate.** RFC 9309 `robots.txt` with product-specific user-agent, allow/disallow precedence, redirects, cache expiry and 5xx/unreachable fail-closed. Independently check site terms, licenses, source permission, `noindex`, private/paywalled/authenticated routes and `X-Robots-Tag`. Robots permission alone does not grant content reuse rights. Preserve provenance and takedown/revocation handling.
5. **Safe fetcher.** HTTPS preference, DNS/IP safety at every redirect and connection (SSRF protection; prohibit loopback, private, link-local, cloud metadata, non-HTTP protocols, embedded credentials), bounded redirects, timeouts, response size, MIME, decompression, charset and cancellation. Honor `429` and `503` / `Retry-After`, disable host on repeated failures, never bypass CAPTCHAs or access controls. Log final response URL, status and headers safely.
6. **Page understanding.** Parse HTML title/headings/text for allowed extraction scope, canonical links, language, dates, location clues, structured data (`schema.org/Event` where present), category signals, 0–3 depth provenance and link edges. Filter boilerplate, navigation, pagination/date-infinite calendars, parameter traps and duplicate/near-duplicate documents. Default to metadata/short original summaries and source links if full-text indexing/storage rights are not established.
7. **Classifier and relevance gate.** **All 18 primary UNA Events categories**, as a mirrored snapshot, are seeds for *coverage*, not a separate Events Engine workflow. Output one primary category plus optional additional labels/facets and confidence/evidence. Content may be general search information related to the category, not necessarily a named event edition. Do not conflate a search result, an event candidate and approved public event publication.
8. **Staging index and query system.** Put newly accepted pages in a **new, separately versioned, reversible index/database**, not the immutable October SQLite (SHA-256 `bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d`) nor the blinded 54x2 replay. Build FTS, URL and category indexes; test candidate BGE/hybrid ranking over this broader corpus separately and compare user-gradeable **unseen** questions.
9. **Freshness loop.** Cache `ETag` and `Last-Modified`; use `If-None-Match`/`If-Modified-Since`, accept `304 Not Modified`, monitor changed/removed URLs, recrawl priority by source freshness, and remove/restrict documents when source rights or robots rules change. The fixed three-hop maximum applies to discovery, not to revisiting admitted URLs for updates.
10. **Owner dashboard and audit.** Local-only owner UI showing run-level funnel, category breadth, source mix, top rejection reasons, crawl failures, safety decisions, duplicates, changed docs, average latency, robots stops, rights status, freshness and index size. Export signed machine-readable run JSON, preserve decisions and code/fixtures in Git; no third-party body exports without permission.

## Taxonomy — 18 primary categories, no filtering by protected/community topic

Source-of-truth prior agreed category snapshot (26 Oct 2026), to be rechecked against the live admin list before any synchronization:

Conference; Festival; Fundraiser; Lecture; Market; Meal; Social Mixer; Tour; Volunteering; Workshop; Other; Horticulture & Flower Shows; Music & Performance; Sport & Fitness; Parades & Processions; Pride & Community; Exhibitions & Trade Shows; Arts & Culture.

Use `config/r3a3f_event_category_coverage_design.json` as a **planning taxonomy**, not a write-sync or production setting. `Outdoor Events` is a cross-category facet, **not** a 19th primary category. Additional cross-cutting facets can cover Family Events, Christmas & Winter, free/accessible events. Seed priority should rebalance under-covered categories, not enforce an arbitrary per-category numerical quota. Pride, Diwali, CSD Berlin and Stadtfest Berlin must remain discoverable; only explicit per-search negation may exclude a specific result for that single request.

### Source strategy

Start from the genuinely approved prior sites. The current 120-page corpus spans seven source families and includes technical/public-service references as well as event pages. Make an audit with exact domains, approved paths, type and terms. Prior web references `https://bytebytego.com/courses/system-design-interview/design-a-web-crawler` (architecture concepts) and `https://nginx.org` (reverse proxy/server docs) are **reference material, not an automatic source allowlist**. Build a proposed vetted category-specific source expansion for owner approval; off-domain links are *discovered leads*, never automatically crawled as an approved new host. A broad 18-category inventory cannot reasonably rely on the initial seven sites alone.

Preserve publisher rights and search linking policy. Prefer official public calendars, venue/organizer sites, museums, public institutions, sports associations, community/charity organisations and specialist directories where source admission permits crawling. Do not bias rankings or crawling against cultural, religious or LGBTQ+ events. Use category-independent freshness/relevance and audit diversity of source coverage.

## Crawl budget / operating interpretation

- **Target accepted new pages:** `target_unique_relevant_indexed_per_day = 1000`; aim, not guarantee.
- **Initial gross fetch ceiling:** `max_fetches_per_day = 5000`, including recrawls (adjust only after observed qualification yield and host rights). A 20% new-relevant yield could produce 1,000, but the yield is a *hypothesis*, not measured fact.
- **Per-host defaults:** `max_inflight_per_host = 1`, `min_interval_s = 3`, stricter as required, adaptive `429/503 Retry-After` and timeout backoff.
- **Safety:** no cross-domain fetch without explicit host admission, no dynamic executable spider following everything, no headless browsing by default, no auth/page bypass, no unsanctioned JS execution.
- **Fairness:** prioritize under-covered approved categories and authoritative source diversity; guarantee neither results nor quotas, never suppress legitimate events by topic.
- **Quality:** relevant/unique/rights-compliant must beat volume. 1,000 new rows/day must be independently confirmed by acceptance predicates; don't pad with empty pages, near-duplicates, stale expired listings or unapproved bodies.
- **Storage and scaling:** use SQLite for isolated PoC if sufficient; persistent host frontier plus Postgres/queue or other higher-scale alternative only after benchmark and resource observation. Keep ingestion and API separate. NGINX (optional) can front the API/admin UI; it is **not** the crawler.

## Strict stage gates

**F0: original evidence and source policy audit.** Read-only extraction of accepted source host/path metadata and the existing crawler `pulse_search_engine.crawl` behaviour. Document rights/robots and current 18-category taxonomy; capture stable hashes. No live third-party fetch.

**F1: isolated simulator and durable crawler.** Build deterministic local 3-hop site graph fixtures with at least 100+ URLs: cycles, deep paths, redirect aliases, duplicate content, pagination traps, HTML malformed, per-host rules, robots denial, unreachable robots, HTTP 429/503, source switch, SSRF attempts, noindex, source revocation, content edits. Acceptance: zero depth-4 fetches, zero unapproved-host requests, robots and rights hold, rate/politeness, dedup, crash/restart, category tagging. Keep `historical/local_snapshot/` byte-identical and all archived 419 tests passing.

**F2: isolated relevance/index dry-run.** Generate a separate staging corpus and search API surface with explicit category filters; 54 original frozen probes continue running solely against the accepted index; add a **new** independent, unseen query set for the expanded corpus and its provenance. Report source/category diversity, precision on human-graded subset, false-relevance and negation tests, no automatic editorial publish.

**F3: tiny live pilot — requires explicit owner-approved host list and crawl budget.** Propose initial **up to 100 pages/day** across permitted sites, with budget caps and rate restrictions, then progressively scale if evidence holds. **Do not start this stage automatically from design approval.** Obtain owner signoff and legal/terms review for each source and record it in source registry. Ramp to 250 → 500 → target 1,000 **relevant indexed** pages/day only after crawl/rights/relevance guards have passed and hosts have tolerated crawling.

**F4: sustained operation with monitoring.** No production service promotion until site/operator protection, accuracy, privacy, takedown, integrity and owner's signoff are verified. Maintain a manually stoppable scheduler with audit receipts, daily independent health report and recovery.

## Required safety and integrity acceptance

- Max 3 *link hops* from reviewed seed; no arbitrary off-domain browsing and no sitemap shortcut; provenance for every URL.
- Source rights, robots, user-agent contact, backoff, DNS/redirect SSRF restrictions, response-size ceilings and cancellation tested end-to-end.
- No unauthorised publisher body storage/export, sensitive personal-data harvesting, rate-limit evasion or source-rights override.
- Accurate category assignment without banning Diwali/Pride/CSD/Stadtfest; ambiguous category labelled as uncertain, not invented.
- No human grade automation. Original October/Nov replay, blinded reviewer workbook and review JSON preserved unaltered. Independent review can continue in parallel.
- Every new code change and test source committed on standalone PulseSearch R3-A3F branch in a **draft** child PR, with immutable evidence, no merge/main/production without owner approval.

## Research references

- ByteByteGo: https://bytebytego.com/courses/system-design-interview/design-a-web-crawler (URL frontier, downloader, parser, seen-URL/content checks, link discovery, host politeness)
- RFC 9309: https://www.rfc-editor.org/rfc/rfc9309.html (Robots Exclusion Protocol; 5xx/unreachable handling; 24h ordinary cache recommendation)
- Google Search Central: https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap (sitemap discovery/canonical guidance)
- MDN: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Conditional_requests (`ETag`/`Last-Modified`, 304)
- NGINX: https://nginx.org/en/docs/ (HTTP server, reverse proxy and API/admin-edge use, not a crawling library)
