# R3-A3G M6: Real information quality

Date: 2026-11-11  
Status: **local evidence only**; production and public Wiki publication remain on HOLD.

## M6 outcomes

Pulse Search now ranks official destinations with a generic **location + facet**
model rather than adding named-query branches:

- city aliases cover Berlin, London, Paris, Hamburg, Munich, Cologne, Frankfurt,
  Stuttgart, Manchester, Birmingham and Glasgow;
- a destination that names another city is excluded from a city-specific query;
- venue, ticket, transport, access, museum and refund facets change ordering;
- generic festival directories no longer stand in for a missing local service;
- a query for an unsupported city can return `NO_EVIDENCE` rather than a
  wrong-city Berlin/London page;
- broader destinations include Berlin museums, Hamburg city/tourism and Munich
  city portals, plus London and Manchester Pride organisers.

Examples from the live local index:

| Query | Top destination |
| --- | --- |
| Berlin museum accessibility | Berlin.de museums |
| Hamburg Christmas markets | Hamburg tourism |
| Munich concert tickets | Eventim Germany |
| Manchester Pride | Manchester Pride |
| London Pride | Pride in London |
| Berlin live music venues | Verti Music Hall |
| Berlin concert venue accessibility | Huxley's Neue Welt |
| London theatre tickets | Roundhouse |

## Independent graded relevance

`config/m6_relevance.json` contains 12 queries with **destination-level grades
0–3**. It is deliberately separate from the search implementation. A URL not in
the judgement set gets zero credit; domain identity alone earns nothing.

`tools/r3a3g_m6_relevance_eval.py` computes:

- nDCG@5 using graded relevance;
- precision@3 for grades >= 2;
- helpful top-1 rate;
- judged coverage of the returned top five.

Current result:

| Metric | Result |
| --- | ---: |
| Queries | 12 |
| Mean nDCG@5 | **0.956** |
| Mean precision@3 | **0.722** |
| Helpful top-1 | **1.0** (12/12) |
| Judged top-five results | 36 |

Evidence: `docs/evidence/r3a3g_m6_relevance_eval.json`.

This is an **internal first-pass** judgement set, not an external reviewer or a
claim of factual correctness. It is a stronger check than the old domain-match
benchmark because the ranking is scored on whether a destination can serve the
request and on where it appears.

## Wiki staging safety

The Pulse UNITY adapter now has a fail-closed `StagingGuard`:

- writes require both an explicit write switch and a guard;
- the guard reads `SELECT DATABASE()` from UNA;
- only names containing `staging`, `pre_verify` or `test` are accepted;
- `una`, `production` and `prod` are rejected;
- an empty authorisation identity is rejected.

Real validation against the mounted UNA application and isolated
`una_pre_verify` database:

- `tests/una_safety_test.php`: **6/6** guard checks passed;
- `tests/una_staging_test.php`: **10/10** checks passed, including real ACL,
  revision write/read-back, denied write, retraction and cleanup;
- original staging block activation, text and revision history restored.

Page creation remains deliberately blocked because UNA’s `addPage()` needs
operator-UI language-catalogue and page-builder side effects. The guard does not
authorise production and does not create a public publication path.

## System boundaries

- **Pulse Search** discovers/ranks information and exposes the standalone API.
- **PUKE** asks through `/v1/search` and `/v1/answer`; it does not import Search.
- **Pulse UNITY Wiki** prepares sourced drafts through its own publisher; the
  UNA adapter is a separate repository and is not part of the Search API.

## Reproduction

```sh
python tools/r3a3g_m6_relevance_eval.py
python tools/r3a3g_usefulness_benchmark.py
python tools/r3a3g_api_demo.py
python tools/puke_client_demo.py
python -m unittest discover -s tests
```

UNA/PHP checks run inside `una-php-1`:

```sh
php tests/una_safety_test.php
php tests/una_staging_test.php
```

## Limits

- Captured pages remain a small, permissioned snapshot; this is not open-web recall.
- The official directory is reviewed navigation, not live data or a crawl licence.
- The graded judgements are an internal first pass and should be repeated by an
  independent reviewer before any production claim.
- No production write, public Wiki publication, deployment or new crawl occurred.
