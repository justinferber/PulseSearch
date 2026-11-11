# Pulse Search R2-P14B — Paged sitemap child discovery

A narrow maintenance release over accepted R2-P14; independently owned, general-purpose Pulse Search. No external search APIs, and no coupling to any other Pulse UNITY system.

## Owner live evidence triggering this fix
- R2-P14 local acceptance: 169 tests PASS.
- London City Hall robots sitemap fetched successfully; `/sitemap.xml` parsed as `sitemapindex` containing 5 child references.
- Only the root index was attempted, with 0 candidates and 0 child sitemap fetches; exact event page not discovered, live exit 2 HOLD.

## Root cause hypothesis and correction
R2-P14 `_valid_sitemap_doc` rejected **all** child sitemap URLs containing `?`. Site generators can legitimately publish child sitemap URLs containing `?page=...` or `?type=...&page=...`. We cannot independently verify the exact five child URLs from the owner's report, so their real shape remains to be established in the next owner run.

R2-P14B permits query parameters **only for sitemap documents** if all values conform to: `page` integer 0..100000 with canonical spelling, optional `type` 1..40 alphanumeric, hyphen or underscore characters. At most one of each, no other keys, and no duplicates; HTTPS, public IP via pinned DNS, same-origin, robots and fixed request/crawl budget remain in force. Page candidate URLs use the existing independent source scope restrictions. Unknown params and external hosts remain excluded without fetching.

Live report now records child links seen, child links admitted, rejection reason counts and sanitized diagnostic samples. It does not print query values that might contain credentials. Still uses no paid provider.

## Scope and limits
- Fresh temporary research index only; existing SQLite databases and production API not modified.
- One approved domain (`www.london.gov.uk`), 6 sitemap documents max, 25 total upper-bound sitemap request count (actual fetches reported), 400 staged URLs maximum, robots delay >=2 seconds, and at most one exact target page fetch if independently discovered in bounded sitemaps.
- The test is internal technical metadata research, not a claim of commercial content rights.
- If target not discovered, HOLD and report diagnostics; no fallback to a paid search API, no bypass of access controls.

## Run
Save/extract the complete ZIP to `C:\Users\justi\Desktop\pulseunity\ChatGPTCode`.

Local: `bash "$D/Pulse_Search_R2P14B_OnePass_20261023.sh"`

Live with explicit approval: `PULSE_SEARCH_RUN_LIVE=1 PULSE_SEARCH_APPROVE_LONDON_DISCOVERY=YES bash "$D/Pulse_Search_R2P14B_OnePass_20261023.sh"`

Run only if comfortable with another bounded visit to the same publisher. If a HOLD occurs, paste the diagnostic summary rather than retrying repeatedly.
