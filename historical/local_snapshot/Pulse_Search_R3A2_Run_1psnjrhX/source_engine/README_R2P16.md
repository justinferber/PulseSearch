# Pulse Search R2-P16 — Candidate-to-Page Promotion (Research Pilot)

Pulse Search is an independent standalone search engine. This additive milestone **reuses** the accepted 112 City Hall sitemap URL candidates, does not use any paid search provider and does not touch the previously accepted original database.

## What this advances

R2-P15 proved we can re-evaluate sitemap URL *leads* across multiple queries. R2-P16 tests a new step: promote **three independently selected, already-discovered URLs** into actual indexed page records via the existing HTTPS/robots-aware native crawler, then run six different search queries against a cloned, multi-page index. The three planned URLs are official City Hall event pages for London Games Festival 2026, Diwali in the Square 2026 and City Hall Open House 2026. All URLs must be confirmed present in the user's original staged URL catalogue before any page fetch.

### Boundaries

- Source: the existing reviewed `london_events_p14`, origin `https://www.london.gov.uk`, path `/events/` only, `metadata_only` internal research.
- Source DB: the already accepted R2-P14B research index with 112 staged candidates and the one previously indexed City Hall New Year's Eve page.
- Writes: **only a new SQLite copy** inside a new, uniquely named audit folder. Source DB SHA256 is verified unchanged.
- Without the live approval flag, zero network requests. With explicit approval, fetch at most **three named site pages**, using the current engine with maximum link depth 0 and 2-second minimum per-origin delay. The crawler may separately fetch robots.txt and follow bounded same-origin redirects, so HTTP request count may exceed three; no other pages are intentionally seeded.
- No new sitemap reads, source approvals, external search engines or paid search provider requests.
- The research query comparison includes conservative year-mismatch suppression. This is a **research-only presentation filter**, not a change to the accepted API.
- Indexing is not proof that a page answers the question or that publication/subscriber rights have been granted. Existing rights limitations continue to apply.

## Run from Ubuntu WSL

Extract `Pulse_Search_R2P16_Complete_20261023.zip` into `C:\Users\justi\Desktop\pulseunity\ChatGPTCode`, then:

```bash
D="$(wslpath -u 'C:\Users\justi\Desktop\pulseunity\ChatGPTCode')"
bash "$D/Pulse_Search_R2P16_OnePass_20261023.sh"
```

Owner clone-only dry run (no internet):

```bash
PULSE_SEARCH_RUN_OWNER_AUDIT=1 bash "$D/Pulse_Search_R2P16_OnePass_20261023.sh"
```

Optional explicitly authorised **bounded live fetch** (3 named pages, not the whole catalog):

```bash
PULSE_SEARCH_RUN_LIVE=1 PULSE_SEARCH_APPROVE_THREE_EVENT_PAGES=YES \
  bash "$D/Pulse_Search_R2P16_OnePass_20261023.sh"
```

The default accepted source DB is `$D/Pulse_Search_R2P14B_Run_qR4X82/research_index.sqlite`. Set `PULSE_SEARCH_R2P14B_RUN_DIR` only if the accepted source DB lives elsewhere.

The report files `promotion_report.json` and `search_review.html` are in the printed new output directory. They list the exact page-fetch outcomes and distinguish indexed-page matches from human-verified answers. A 404, noindex or robots-denied response is a legitimate reason to retain HOLD/partial status rather than inventing a successful result.
