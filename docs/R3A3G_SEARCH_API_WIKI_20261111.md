# R3-A3G — Useful search, PUKE API and Wiki draft workflow

**Date:** 11 November 2026 · **Branch:** `fb2/r3-a3g-broad-search-query-intents-20261111` · **PR #11 draft.**
**R3-A3F PR #10 remains separate.** No crawler admission, public deployment or real Wiki publication occurred.

## What was built

| Area | Implementation |
| --- | --- |
| Query router | English/German intent classification: navigation, weather, translate, transport, flights, how-to/tickets, events, sports, shopping, general; negation (`excluding`, `ohne`), aliases (CSD/Pride, Konzert/concert), city detection. |
| Ranking | Lexical title/snippet/URL weights + SQLite FTS5 BM25 + official-source authority + recency; URL/title dedup; per-host diversity; explainable `ranking_reasons`; snippet windowing. |
| Official fallback | `official.py` registry of reviewed services: BBC Weather, Met Office, DWD, DeepL, Google Translate, Eventim, Berlin venues, BVG/S-Bahn, TfL, airlines/CAA/ABTA, city calendars, Wikipedia/GOV.UK. Weather/translate are handoffs; no fabricated value, no paid API. |
| API | `api.py`: loopback-only, bearer-token auth, per-consumer rate limit, body/query caps, no CORS, request IDs, `POST /v1/search`, `POST /v1/answer`, `POST /v1/wiki-candidates`, `GET /v1/health`, `/v1/capabilities`. |
| Wiki | `wiki.py`: source-cited drafts, duplicate detection, update diffs without overwriting, approval/rejection, publication policy (off by default), source revocation → flag/unpublish, PII/transient-value rejection, publisher adapter boundary. |

## Measured acceptance (offline fixtures)

70 labelled English/German patterns in `tests/test_r3a3g_acceptance.py`
(evidence `docs/evidence/r3a3g_acceptance.json`):

| Metric | Result |
| --- | --- |
| Queries / failures | 70 / **0** |
| Recall@3 | **0.986** |
| MRR | **0.896** |
| Wrong-city rate | **0.000** |
| Unsupported-result rate | **0.000** |
| Mean latency | **0.47 ms** |
| Source diversity | 0.173 (fixture corpus has few hosts — not a web measurement) |

These are labelled offline fixtures, not open-web accuracy. Source diversity is the honest weak point
because the corpus is synthetic; no claim is made about universal coverage.

## API examples (actual local test)

`POST /v1/search` → `{"status":"staging_results","response_mode":"SEARCH_RESULTS","result_cards":[...],
"source_ids":[...],"request_id":"…","retrieved_at":"…"}`

`POST /v1/answer` weather → `{"status":"OFFICIAL_LINKS","response_mode":"OFFICIAL_LINKS",
"citations":[BBC Weather, Met Office/DWD],"answer":"…official forecast links…","limits":[...]}`

Wiki candidates are always `"publication":"DRAFT_ONLY"`; no publish endpoint is exposed.

```bash
PULSE_API_TOKEN=… python -m pulse_search_broad_r3a3g.api \
  --staging data/r3a3f_three_source/staging.sqlite --wiki data/r3a3g_wiki/wiki.sqlite
```

The token must come from the environment (not argv) in real use. The service refuses a non-loopback
bind; public exposure requires a separate security review. Query text is not logged.

## Wiki workflow

`tools/r3a3g_wiki_demo.py` produces 11 drafts, an update diff, duplicate detection, three approvals,
a local-test publication, a rejection and a source-revocation flag/unpublish:

- `draft` 7 · `published` 2 · `flagged` 1 · `rejected` 1 (local test DB).
- `published` means the **local test publisher only**. No Pulse UNITY/UNA Wiki write occurred.
- Real publication requires the UNA Wiki ACL/API inspection, an adapter implementation and explicit
  owner deployment authority. `WikiPublisher` is the boundary; `PublisherNotConfigured` is the
  default for any unimplemented adapter.
- Articles need ≥2 independent sources, claim-level citations, non-future verification dates, and
  must not contain email/phone data, transient prices/stock or live observations.

Browser previews: `/wiki` and `/wiki/<slug>` in the local console; the database is
`data/r3a3g_wiki/wiki.sqlite`.

## Tests run

- `python -m unittest discover -s tests -p "test_r3a3*.py"` — 231 tests after the final fixes.
- 70 acceptance patterns, 8 API cases, 7 Wiki workflow cases, plus the existing crawler/answer suites.
- Crawler safety unchanged; PR #10 reverted to its previous scope.

## Honest limitations

1. Fixtures are synthetic; no open-web precision or recall claim.
2. No SearXNG instance is configured, so ephemeral discovery is not demonstrated live.
3. Weather/translate are **links**, not live values; the optional Open-Meteo adapter remains off by default.
4. The Wiki side ends at a local test publisher; the real UNA adapter is deliberately not invented.
5. Source diversity is low in the fixture set; real source expansion and human grading remain the next M4 step.
