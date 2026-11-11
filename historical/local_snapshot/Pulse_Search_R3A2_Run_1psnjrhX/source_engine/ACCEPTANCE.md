# R2-P14 Acceptance Record

- Build timestamp: 23 October 2026.
- Source foundation: `Pulse_Search_R2P12_Coverage_Pilot_20261023.zip` previously provided and available in the current conversation container.
- Components: original independent crawler, scheduler, shadow API, relevance tools unmodified; new `pulse_search_p14.py`, 27 regression/security fixtures.
- Baseline inherited tests: 142.
- R2-P14 new tests: 27.
- Total tests: **169/169 passed locally**, no public internet accessed by these tests.
- Offline fixtures: robots declared sitemaps, fallback behavior, nested XML sitemap index, bounded gzip, external origin rejection, robots restrictions, invalid XML/DTD refusal, per-document request budget, late-listed relevant URLs, staged-only discovery, separately approved exact-page indexing.
- Owner WSL acceptance: **NOT YET RUN**.
- Live `www.london.gov.uk` discovery: **NOT YET RUN by independent Python crawler in WSL**.
- Paid external search requests: **0 in this R2-P14 build and tests**.
- No previously accepted SQLite indices modified.
