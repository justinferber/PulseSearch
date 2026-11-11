# R3-A3F — proposal for the first capped pilot (source by source)

**Status: `PROPOSAL_ONLY_NOT_ADMITTED`.** This document proposes an admission set and budgets. It
does not admit a source, does not authorise a fetch, and changes no default: every source still
starts `approved=False`, `index_allowed=False`, `probe_policy=[]`, and the CLI rejects an import that
omits any admission field or claims approval without a reviewed rights basis. **Production remains
HOLD.** No third-party host has been contacted. Machine-readable twin:
`docs/evidence/r3a3f_pilot_source_proposal.json`.

## 1. Basis and the one candidate

The host list comes from the read-only audit of the owner's accepted 120-page index
(`docs/evidence/r3a3f_source_registry_proposal.json`, index SHA-256 `bb8e5202…7368c35d`, 120 pages,
7 hosts). Presence in that index is **not** permission to crawl.

| Host | Pages in index | Event relevance | Role |
| --- | --- | --- | --- |
| `www.london.gov.uk` | 107 | High — city events listings | **Phase 1 candidate, `/events` only** |
| `www.gov.uk` | 4 | None — service pages | Excluded |
| `www.nhs.uk` | 4 | None — health services | Excluded |
| `developer.mozilla.org` | 2 | None — technical reference | Excluded |
| `docs.python.org` | 1 | None — technical reference | Excluded |
| `www.rfc-editor.org` | 1 | None — technical reference | Excluded |
| `www.sqlite.org` | 1 | None — technical reference | Excluded |

`/whats-on` is **removed** from the proposal pending verification that the path exists, is stable,
and is covered by the same terms and robots permissions as `/events`. A path that has not been
verified is not proposed, even when it is linked from the site.

One host only, on purpose: a single-source pilot isolates crawler behaviour (robots, pacing, yield,
404 lifecycle, redirect refusal) from cross-source fairness, which is already measured offline.

## 2. Admission record (proposed, **not applied**)

| Field | Proposed value | Why |
| --- | --- | --- |
| `source_id` | `london-gov-uk-events` | stable and human-readable |
| `origin` | `https://www.london.gov.uk` | one origin; no scheme or subdomain variation |
| `allowed_paths` | `["/events"]` | the only path under review; no site-wide crawl |
| `rights_status` | `PENDING_TERMS_REVIEW` | must become an explicit basis before approval |
| `approved` | `false` | flips only on a documented owner decision |
| `index_allowed` | `false` | flips only if the terms permit snippet indexing |
| `store_body` | `false` | metadata and a ≤320-character snippet only |
| `probe_policy` | `[]` | **no guessed-path probes in Phase 1** |
| `probe_budget_per_run` | `0` | probes stay off until a reviewed policy exists |
| `contact` | owner contact address | required by the user agent |
| `daily_page_cap` | `100` accepted documents/day | the stated pilot cap |
| `crawl_delay` | parsed from robots on the first request; `min_interval_s` stays ≥3s | never exceed the published delay |

Nothing here is written by this commit. The proposal is data for the owner's decision, not an
admission record.

## 3. Verification required before approval (owner, manual)

These steps are deliberately manual and outside the crawler; the pilot must not "discover" its own
permissions by fetching.

1. Read `https://www.london.gov.uk/robots.txt` in a browser and record the agent rules, any
   `Crawl-delay`, and any sitemap references.
2. Read the site's terms / copyright / re-use statement and record the basis for fetching `/events`
   and for indexing a title plus a short snippet.
3. Confirm that `/events` exists as a listing section, and whether it paginates or is filtered by
   query parameters (those shapes need a separate decision).
4. Confirm the contact address for the user agent, and who receives a takedown request.
5. Record the decision (approve / deny / change scope) with a date and a reviewer.

Only after step 5 may `approved=True` and — separately — `index_allowed=True` be set through the CLI
or the store.

## 4. New pages versus the 107 already in the historical index

107 of the 120 pinned pages are already `www.london.gov.uk` URLs. A pilot that reports "100 pages
crawled" without separating new from already-known pages would overstate its value.

The report now measures this directly and read-only (`novelty.py`):

* `historical_index_pages` — canonical URLs in the pinned index;
* `staged_documents` — canonical URLs in the staging index;
* `already_in_historical_index` — the overlap;
* `novel_documents` — staged URLs not in the pinned index, with a `novel_sample`.

The comparison opens the pinned index with SQLite `mode=ro` and never writes to it. The console shows
the same line under **Sources and rights**, and `report --historical-index <path>` exports it in JSON.
A pilot's daily acceptance figure must be reported as **novel documents**, with the overlap stated
next to it; the 107-page baseline is the expected overlap from day one.

## 5. Budgets

| Budget | Value | Rationale |
| --- | --- | --- |
| Accepted documents | ≤100/day, of which novel documents tracked separately | the pilot cap |
| Gross fetches | ≤300/day | conservative live yield; well inside the 5,000 ceiling |
| Requests per host | one in flight, ≥3s apart | politeness is never traded for volume |
| Redirect hops | ≤5 per claimed URL, each re-authorised | see §6 |
| Probe fetches | **0** | no guessed paths in Phase 1 |
| Rechecks | 404 only, ≤2 per URL, 24h for `/events` pages | a temporary absence is not a verdict |
| Run length | ≤30 minutes, then exit | no long-lived daemon |

## 6. Redirect policy during the pilot

A redirect is a new URL. Before any redirect destination is requested, the crawler re-checks: the
source is admitted and enabled; the destination is on the **same origin** and inside
`allowed_paths`; robots allows the destination path; the run's request ceiling is not exhausted; and
the host's pacing slot has been waited for. Off-origin redirects are refused even when the target is
a public site or a separately admitted host — that host would need its own admission and its own
seed. Every hop is recorded in `redirect_log` with its decision and reason and appears in the JSON
report and console.

## 7. Phases

| Phase | Scope | Exit criterion |
| --- | --- | --- |
| **P0 — compliance review (no fetching)** | The five manual steps in §3 | Written admission of the record in §2 |
| **P1 — `/events`, 20 accepted pages/day, 3 days** | Probes off; redirect refusal and pacing instrumented | Zero robots violations, zero off-origin requests, novel-document count recorded, acceptance ≥15% |
| **P2 — `/events`, 100 accepted pages/day, 7 days** | Same scope; rechecks observed | Acceptance ≥20%, no 429 storm, one recheck outcome recorded |
| **P3 — second path or second host** | Only after P2 review, with its own decision | Separate owner decision |

## 8. Stop conditions (any one halts the run)

1. Any fetch to a host without an admitted source, or indexing with `index_allowed=0`.
2. Any request inside a robots-disallowed path.
3. Any followed redirect outside the approved origin and path.
4. Three consecutive 5xx from the host, or robots returning 5xx/403 → host disabled for the run.
5. Any `429`/`503`: honour the full `Retry-After`, then stop the host for that run.
6. Acceptance below 10% after 100 fetches → stop and review.
7. Any depth-4 request.
8. Any non-HTML response parsed, or any body storage attempted.
9. Owner kill switch: `set_source_enabled(source_id, false)` and stop the scheduler.

## 9. Evidence per run

The JSON report, per-source fetch shares, the pacing log, robots rows, redirect log (followed and
blocked, with reasons), rechecks scheduled/recovered/exhausted, probe-versus-link counts
(zero probes in Phase 1), `useful_per_100_fetches`, the novelty block, and the config hash. Daily
summaries are appended to `docs/evidence/`. The pinned index and the frozen 54-case replay must keep
their hashes unchanged across the pilot.

## 10. Decisions the owner must make before Phase 1

1. Confirm `www.london.gov.uk` and the single path `/events` (or substitute a host/path).
2. Complete the §3 review and state the rights basis, including whether snippet indexing is allowed.
3. Confirm the contact address in the user agent and the takedown recipient.
4. Confirm 100 accepted pages/day, 300 fetches/day and zero probes in Phase 1.
5. Confirm retention (metadata + snippet, no body).
6. Authorise the first live request in writing.

Until decision 6, this remains a proposal; the code still refuses to fetch.
