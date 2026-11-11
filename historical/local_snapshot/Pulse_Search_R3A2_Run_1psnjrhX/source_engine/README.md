# Pulse Search R2-P14 — Independent Sitemap Discovery

**Search IP remains independent.** No paid search provider, Brave request, external search API, or linkage to another Pulse UNITY project.

R2-P14 is a *new opt-in module* layered on the previously accepted standalone crawler (`pulse_search_engine.py`), scheduler, SQLite FTS5 index and HTTP API. It does not alter the accepted crawl/search implementation, its API or the user's prior databases.

## What has actually changed

- Read `Sitemap:` declarations from an approved origin's `robots.txt`, fall back to `/sitemap.xml` only if no same-origin declaration is present.
- Accept `<sitemapindex>` and `<urlset>` with namespaced XML, including bounded nested indexes and gzip content.
- Stay within one explicitly reviewed source and scope; robots rules are checked for every sitemap and proposed page URL.
- Apply strict limits: 8 sitemap documents maximum, 2 levels beneath the root, 1.5MB compressed / 3MB decompressed, 5,000 entries examined per document, maximum 800 staged candidates; fetches enforce origin-pinned public IPs, TLS, redirects and HTTP timeouts using our existing crawler.
- Score candidate URLs against a question *without treating the score as verification*, prioritising relevant candidates across the processed sitemap rather than the first lines.
- Stage URL metadata into a **fresh research SQLite DB**, without fetching their webpages.
- Optionally, after the exact target URL was discovered in a sitemap, explicitly fetch and index that **one** first-party page into the *research DB only*, with a separate robots check. Never crawl the rest of the candidates automatically.
- Report the difference between `TARGET_DISCOVERED_IN_SITEMAP`, `TARGET_NOT_FOUND_IN_BOUNDED_SAMPLE`, `TARGET_DISCOVERED_AND_INDEXED_INTERNAL`, or restricted access/fetch failures.

## Risks and scope

The London City Hall example is internal technical metadata research; approvals in the example source configuration **do not constitute publisher consent for commercial use**. Never redistribute its text, imagery, or any resulting dataset to subscribers without legal and licence review. Indexing one research page may store text locally for FTS; the API only reveals metadata by default.

For a live trial, explicit permission is limited to the single origin `https://www.london.gov.uk`, robots discovery, up to six sitemap documents, and **one exact target** `https://www.london.gov.uk/events/london-new-years-eve-2026` if independently discovered. Sitemaps are hints, not an exhaustive listing. A 404, 403, 429, robots denial, oversized sitemap, no hit or network block is recorded, not disguised as a PASS for discovery.

The previous one-off Brave benchmarking is **closed**. This version calls no paid APIs.

## Owner run on WSL

Extract `Pulse_Search_R2P14_Complete_20261023.zip` into `C:\Users\justi\Desktop\pulseunity\ChatGPTCode` so that the inner engine ZIP and shell launcher sit beside each other.

```bash
D="$(wslpath -u 'C:\Users\justi\Desktop\pulseunity\ChatGPTCode')"
bash "$D/Pulse_Search_R2P14_OnePass_20261023.sh"
echo "TEST_EXIT_CODE=$?"
```

Only after that succeeds, opt into one bounded public-source trial:

```bash
PULSE_SEARCH_RUN_LIVE=1 \
PULSE_SEARCH_APPROVE_LONDON_DISCOVERY=YES \
bash "$D/Pulse_Search_R2P14_OnePass_20261023.sh"
echo "LIVE_EXIT_CODE=$?"
```

The second command attempts the sitemap discovery. If the target is found and accessible under robots controls, it attempts **one exact page** and searches the isolated research index. No accepted databases are loaded, cloned or altered.

Results appear in a new `Pulse_Search_R2P14_Run_XXXXXX` directory under `ChatGPTCode`. The script outputs its location. The report is `discovery_report.json`.

## Acceptance boundaries

- **Offline software PASS**: SHA-pinned package + manifest and 169 local tests.
- **Live discovery PASS**: full live report shows `target_discovered=true` and sitemap URL provenance, no paid search requests. A partial report with the target missing is useful data but NOT a target-discovery success.
- **Live independent index PASS**: additionally `target_indexed=true`, one published page is stored in the isolated index and is searchable. Rights permission for subscriber publication remains separate.
- **Live service readiness**: NOT asserted. This is one tiny bounded live sample, not a web-scale unattended crawler.

## Next step after successful live pilot

R2-P15 should focus on a repeatable multi-source discovery workflow, independently reviewed source enrolment, index freshness and a proper benchmark of ordinary queries. Keep any future paid comparison exceptional and separately approved.
