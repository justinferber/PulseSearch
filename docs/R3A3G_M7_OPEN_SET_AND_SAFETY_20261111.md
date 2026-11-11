# R3-A3G M7: Open-set relevance and safer staging

Date: 2026-11-11  
Status: **development evidence only**; production and public Wiki publication remain on HOLD.

## What changed

This pass responds to the independent review of M6 rather than adding another
small directory benchmark.

### Search relevance and padding

- Museum-access questions now return the museum directory, not a concert venue.
- Venue-access questions return the named venue or the venue set, not Pride,
  Christmas or generic city calendars.
- Named venues are matched by current name **and** retained aliases.
- Ticket queries without a city no longer fan out to every venue in the
  directory.
- Event-ticket queries use the organiser/authorised seller rather than unrelated
  venues in the same city.
- Event results must contain a query event term; excluded Christmas terms remain
  eligible for explicit “without Christmas” queries.
- General refunds return GOV.UK first; CAA aviation advice only leads for flight
  queries.
- Generic search matches for accessibility questions no longer substitute a
  transport page (for example TfL for a museum-access question).

### Berlin venue rename

The directory now uses the current names, with old names searchable:

| Current destination | URL | Retained alias |
| --- | --- | --- |
| Uber Arena Berlin | `https://www.uber-arena.de/` | Mercedes-Benz Arena |
| Uber Eats Music Hall Berlin | `https://www.uber-eats-music-hall.de/` | Verti Music Hall |

Both URLs returned HTTP 200 in the live check; the old Mercedes-Benz host did
not resolve.

### Wiki staging safety

The `StagingGuard` now rejects production/live/public markers even when combined
with a test suffix, so `production_test` cannot pass. It also requires a named
operator email and a `STAGING-...` approval reference. The real staging test now
removes only its own revision/note and restores the block only if no later editor
revision exists.

## M7 open-set benchmark

`config/m7_unseen_questions.json` contains **28 English and German questions**
that are disjoint from the 12 M6 tuning queries. The questions were written
after the M6 work and were not used to add named-query branches. Destination
grades are 0–3 and are about the page a person needs, not the reputation of the
site.

| Metric | Result |
| --- | ---: |
| Queries | 28 |
| Mean nDCG@5 | **0.748** |
| Mean precision@3 | **0.566** |
| Helpful top-1 | **0.643** (18/28) |
| Judged top-five results | 38 |

Evidence: `docs/evidence/r3a3g_m7_unseen_eval.json`.

The lower score is intentional evidence, not a regression to hide. It shows that
the directory can often choose the right category but still lacks specific pages
for:

- Hamburg public transport and Christmas-transport questions: no evidence;
- London museum wheelchair access: no evidence rather than a transport page;
- Paris Pride and New Year: city homepages score only 1–2, not a specific event
  page;
- Berlin concert cancellation and London theatre refunds: jurisdiction/policy
  guidance is not yet specific enough.

The M6 set was also re-run after the stricter filtering: **nDCG@5 0.889,
precision@3 0.931, helpful top-1 12/12, 24 judged top-five results**. The drop
from the earlier M6 figure reflects returning fewer loosely related links, not
loss of the top answer.

## Verification

- Python suite: **268 tests, OK**
- `tests/una_safety_test.php`: **9/9**
- `tests/una_staging_test.php`: **10/10**
- M5 usefulness benchmark: **8/8**, zero unrelated top results
- API and PUKE demos: re-run after the final search changes
- Dashboard: HTTP 200 on loopback after restart

## Limits

- The M7 judgements are internal first-pass grades, not an external human panel.
- The snapshot is permissioned and small; this is not open-web recall.
- Official links are navigation and do not prove live dates, prices, stock or
  availability.
- No production write, public Wiki publication, deployment or new crawl occurred.
- Page creation and the UNA HTTP/session/CSRF operator path remain blocked.
