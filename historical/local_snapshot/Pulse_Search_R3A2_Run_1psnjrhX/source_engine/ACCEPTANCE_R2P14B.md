# R2-P14B acceptance

LOCAL: original 169 and 5 new tests = 174/174 passed in isolated fixture environment.
LIVE: pending owner WSL retest. Required for success:
1. Original engine SHA-256 and all manifest members pass.
2. Declared index and bounded child sitemap documents processed, with safe reasons for any rejection.
3. Exact `https://www.london.gov.uk/events/london-new-years-eve-2026` URL independently discovered in a sitemap, rather than seeded to web search.
4. If permitted, single exact target page fetched and indexed in new local SQLite DB, retrievable through own full-text query.
5. 0 paid external provider API requests and 0 accepted database modifications.

A valid diagnostic HOLD is acceptable: it means more evidence is required; it is not a technical acceptance PASS.
