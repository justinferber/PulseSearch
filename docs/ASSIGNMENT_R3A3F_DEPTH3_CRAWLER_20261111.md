# FB2 ASSIGNMENT — R3-A3F: 3-hop discovery crawler for 18-category standalone Pulse Search

**Approved work:** Build and test a persistent, robots-respecting, topic-aware crawler in an isolated developer branch. **Desired eventual throughput:** approximately 1,000 NEW relevant, unique, rights-compliant indexed pages per day, not raw downloads. **No production activation or third-party crawl launch under this assignment alone.** A bounded live pilot requires an approved source register and documented host budgets.

**Read first:** `docs/R3A3F_DEPTH3_CRAWLER_ARCHITECTURE_20261111.md` and `config/r3a3f_event_category_coverage_design.json`.

**Parent:** R3-A3E PR #8 head `02a9efde4e2ad870fa76787d311f7345ae8d2796`, unmerged. **Branch:** `fb2/r3-a3f-depth3-category-crawler-20261111`. Do not alter R3-A3D original replay, graded workbook, sealed A/B mapping, pinned index, BGE weights, original October source snapshots, production API or UNA/Events database.

## Owner intent to preserve literally

- Revisit ALL historically admitted Pulse Search source sites and follow relevant discovered links at **most 3 hops** from each reviewed seed (0 seed, 1/2/3 links).
- Discovery should be persistent, continuously revisiting changed relevant pages while never exceeding the max depth for *new link expansion*.
- Expand search information relevant to **all 18 UNA Events primary categories**, but maintain **standalone Pulse Search separation**: categories are read-only search coverage inspiration. No Events Engine research/qualification/publication API, no automatic UNA event creation and no preferential event advertising status.
- Coverage is world-wide and inclusive; Diwali, Pride/CSD, Stadtfest, community, religious and cultural events must never be globally blocked. Search-local user negation filters do not affect crawling or indexing.
- Use ByteByteGo's URL frontier/download/parser/dedup/link workflow as an architectural reference; NGINX is a potential API reverse proxy, not a crawler.
- User's independent 54-question review continues in parallel, unaffected by any new corpus.

## Steps — do not stop after a paper design

### F0 — audit and forensic source inventory (read-only)
1. Use the existing Git snapshots and `pulse_search_engine.crawl` source, not a rewrite from scratch; create `docs/R3A3F_EXISTING_CRAWLER_AUDIT.md` listing current crawl depth handling, DNS/redirect/robots safety, source allowlist, URL frontier persistence, resume, dedup, metadata storage, index update and bottlenecks.
2. Read the current owner 120-page SQLite in immutable/read-only mode only, verify SHA-256 `bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d`; generate source registry *proposal* with exact prior approved hosts, paths, rights basis and origin evidence. Do not infer source permission just from URL presence or HTTPS.
3. Reconcile 18-category planning snapshot against the actual current UNA taxonomy **read-only only** if access exists; do not invent database primary IDs. The JSON has *proposed display order*, not live IDs.
4. Record the frozen 54 questions and current original archived 25/25 modules 419 tests, plus R3-A3E candidate delta, as separate baselines.

### F1 — implement a durable, 3-hop crawler in new source
5. Build a local independent package under `pulse_search_crawler_r3a3f/` (choose code structure as appropriate) with persisted SQLite-backed seed/source registry, frontier, URL graph, per-host schedule, robots/rights gate, safe fetch, HTML/link parser, relevance/classification, dedup, staging index and JSON run journal.
6. Exact depth admission: initial source-approved seed=0; URL discovered from a depth-d page is d+1; never fetch d>3 or silently count sitemap URLs as depth 0; canonical URL dedup keeps minimum depth. Outbound external-host links become unapproved source *candidates only*. Absolute/relative/canonical/redirect link handling and per-host rules included.
7. Robots RFC 9309 interpretation; Terms/rights metadata; `noindex`; named user-agent and contact; DNS/IP/redirect SSRF checks, auth/paywall/captcha exclusion, response bounds, rate/budget, graceful shutdown and resumable queue. Default one in-flight request/host and >=3 s delay (stricter per host policy), back off `429/503` and `Retry-After`. Fail closed on unreachable robots or unadmitted host, even when a site is publicly accessible.
8. Content relevance should be independent of event publisher pipeline. One primary category among 18 + optional multi-label facets + evidence/confidence; pages can provide *information about a category*, not just named events. Maintain category-balanced frontier priorities and report source/category representation, with special attention to underrepresented Meal, Volunteering, Social Mixer and Fundraiser if missing.
9. Only index permitted metadata/short snippets/source links where reuse rights unclear. Separate rights to fetch from rights to store/index/display; revocation and reclassification must propagate to staging. Strip tracking URLs, exclude infinite calendar pagination/query traps; content-hash and canonical dedup. Recrawl efficiently with ETag/Last-Modified; run logs persist depth, parent, root, source policy and content status.
10. Implement hard safety/quality counters: discovered, admitted, robots-denied, rights-denied, depth-skipped, off-domain-proposed, fetched, non-html, noindex, duplicate, low-relevance, newly indexed, changed/revalidated, error/by reason, category coverage, mean/p95 latency; no source-rights policy ever hidden by an overall success count.

### F2 — test and demonstrate fully offline, no third-party crawling
11. Deterministic local loopback graph >=100 synthetic pages crossing all 18 categories with positive tests for Diwali, Pride, Stadtfest Berlin and CSD Berlin, category changes, year+edition, duplicate templates, cyclic links, 4th-hop trap, separate hosts, robots 5xx/403, 429 and 503, noindex, 301/302/307/308 chains, malicious SSRF links, malformed HTML, sitemap admissions, re-fetch unchanged/updated and restart/recovery. Assert 0 forbidden hosts/depth4 fetches, no data leakage, stable dedup and source revocation.
12. Build a **new staging index only**, with a distinct path and versioned schema and a visible browser-based local crawler-run dashboard/report if feasible; demonstrate category searching and citations/source links without touching immutable index. Report accepted/rejected page distribution and real classification mistakes.
13. Model the daily target by simulated budgets/traffic. Do NOT claim 1,000/day achieved from lab simulation; calculate how many gross fetches would be needed at observed *real* yield when authorised pilot happens. Design safe ramp: 100/day pilot → 250 → 500 → target 1,000 relevant/day if compliant.
14. Re-run historical regression and frozen original replay against **original** accepted index, not the new corpus, report byte hash before/after. Include independent unseen test queries for new staging index, with human review pending.
15. Commit source, tests, source registry *proposals*, read-only evidence and comprehensive reports to current R3-A3F branch. Open a **draft** child PR targeting R3-A3E branch; leave all ancestors draft, no merge or deployment.

### F3 — NOT automatically approved by F0–F2
Once owner separately approves exact real domains/paths/rights/budgets, run a capped host-polite third-party pilot (initial up to 100/day) and produce receipts. No broad internet crawl, no automatic linking to unauthorised domains, no sustained schedule or 1,000/day launch absent an explicit activation decision.

## Acceptance matrix

`ORIGINAL_INDEX_UNTOUCHED=PASS`; `MODEL_UNTOUCHED=PASS`; `OLD_419_TESTS=PASS`; `FROZEN_54_BASELINE_UNCHANGED=PASS`; `LINK_MAX_DEPTH_3=PASS`; `ROBOT_AND_RIGHTS_POLICIES=PASS`; `HOST_POLITENESS_AND_SSRF=PASS`; `OUTBOUND_HOST_ADMISSION=PASS`; `PERSISTENT_RESTART=PASS`; `RELEVANCE_AND_DEDUP=PASS`; `18_CATEGORY_COVERAGE_TESTED=PASS`; `LIVE_1000_PER_DAY=NOT_CLAIMED`; `SIGNED_HUMAN_GRADING=0_OR_ACTUAL`; `PRODUCTION=HOLD`.

**The key business outcome:** when permissioned crawling starts, Pulse Search should grow a **meaningful** multilingual/global-ready search corpus with reliable freshness/source provenance, not merely store 1,000 arbitrary URL rows. This is standalone search infrastructure, not the Events publishing engine.
