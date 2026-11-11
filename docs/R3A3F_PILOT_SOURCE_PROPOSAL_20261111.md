# R3-A3F — proposal for the first capped pilot (source by source)

**Status: `PROPOSAL_ONLY_NOT_ADMITTED`.** This document proposes an admission set and budgets. It
does not admit a source, does not authorise a fetch, and changes no default: every source in the
crawler still starts `approved=False`, `index_allowed=False`, `probe_policy=[]`. **Production
remains HOLD** and no third-party host has been contacted. Machine-readable twin:
`docs/evidence/r3a3f_pilot_source_proposal.json`.

## 1. Basis

The host list comes from the read-only audit of the owner's accepted 120-page index
(`docs/evidence/r3a3f_source_registry_proposal.json`, index SHA-256 `bb8e5202…7368c35d`, 120 pages,
7 hosts). Presence in that index is **not** permission to crawl; it is only evidence that the owner
already judged these pages relevant.

| Host | Pages in index | Event relevance | Proposed role |
| --- | --- | --- | --- |
| `www.london.gov.uk` | 107 | High — city events listings, festivals, seasonal programmes | **Phase 1 candidate** (single host) |
| `www.gov.uk` | 4 | None — service/how-to pages | Excluded from the pilot |
| `www.nhs.uk` | 4 | None — health services | Excluded |
| `developer.mozilla.org` | 2 | None — technical reference | Excluded |
| `docs.python.org` | 1 | None — technical reference | Excluded |
| `www.rfc-editor.org` | 1 | None — technical reference | Excluded |
| `www.sqlite.org` | 1 | None — technical reference | Excluded |

One host is proposed for Phase 1 on purpose: a pilot with one source isolates crawler behaviour
(robots, pacing, yield, 404 lifecycle) from cross-source fairness, which is already measured offline
and can be measured live in Phase 2.

Additional event hosts (Berlin city guide, venue calendars, district festival pages) are **not**
proposed here. They must be nominated by the owner with a rights basis, and this repository should
not guess at them.

## 2. Admission record for the Phase 1 candidate

Proposed values, to be confirmed by the owner after a robots and terms review:

| Field | Proposed value | Why |
| --- | --- | --- |
| `source_id` | `london-gov-uk-events` | stable, human-readable |
| `origin` | `https://www.london.gov.uk` | one origin only |
| `allowed_paths` | `["/events", "/whats-on"]` | listing and event detail paths only; no site-wide crawl |
| `rights_status` | `PENDING_TERMS_REVIEW` | must become an explicit basis, not an assumption |
| `index_allowed` | `false` until review, then `true` if the terms permit snippet indexing | fail-closed default |
| `store_body` | `false` | metadata and a ≤320-character snippet only |
| `probe_policy` | `["/whats-on", "/events"]` (reviewed) | two reviewed listing paths, each inside `allowed_paths` |
| `probe_budget_per_run` | `2` | bounds guessed requests to two per run |
| `contact` | owner contact address | required by the user agent |
| `daily_page_cap` | `100` accepted documents/day | the stated pilot cap |
| `crawl_delay` | parsed from robots at first request; `min_interval_s` stays ≥3s | never exceed the published delay |

Everything else — 3-hop maximum, one request in flight, `Retry-After` honouring, off-domain links as
candidates only, sitemap candidates requiring review, no JS rendering — is unchanged from the
audited implementation.

## 3. Budgets

| Budget | Value | Rationale |
| --- | --- | --- |
| Accepted documents | ≤100/day | pilot cap; roughly the accepted-page count of the owner's existing index |
| Gross fetches | ≤300/day | at a conservative 33% live yield; hard-stops before the 5,000 ceiling |
| Requests per host | one in flight, ≥3s apart | ≥28,800/day is theoretically allowed; the accepted-page cap binds first |
| Probe fetches | ≤2 per run | guesses stay a rounding error |
| Rechecks | 404 only, ≤2 per URL, 168h for probes / 24h otherwise | a listing that appears later is not lost; 410/451 stay permanent |
| Run length | ≤30 minutes, then exit | no long-lived daemon in the pilot |

## 4. Phases

| Phase | Scope | Exit criterion |
| --- | --- | --- |
| **P0 — compliance review (no fetching)** | Owner reads robots.txt and the site terms manually; confirms the user agent and contact; decides `index_allowed` | Written admission of the record in §2 |
| **P1 — one host, 20 accepted pages/day, 3 days** | Full instrumentation on; no probes until day 2 | Zero robots violations, zero unapproved hosts, acceptance ≥15%, pacing log complete |
| **P2 — one host, 100 accepted pages/day, 7 days** | Probes enabled; 404 lifecycle observed | Acceptance ≥20%, no 429 storm, at least one recheck outcome recorded |
| **P3 — second host** | Only after P2 review, with its own admission record | Separate owner decision |

## 5. Stop conditions (any one halts the run)

1. Any fetch to a host without an admitted source, or with `index_allowed=0` at index time.
2. Any request inside a robots-disallowed path.
3. Three consecutive 5xx from one host, or robots returning 5xx/403 → host disabled for the run.
4. Any `429`/`503`: honour the full `Retry-After`, then stop the host for that run.
5. Acceptance below 10% after 100 fetches → stop and review before continuing.
6. Depth 4 reached, or any depth-4 request — treated as a crawler defect, not a page problem.
7. Any content type other than HTML being parsed, or body storage attempted.
8. Owner kill switch: `Store.set_source_enabled(source_id, False)` plus stopping the scheduler.

## 6. Evidence the pilot must produce

Per run: the JSON report (`/api/report.json`), the per-source fetch shares, the pacing log, the
`robots` rows, scheduled/recovered/exhausted rechecks, probe-versus-link discovery counts, and
`useful_per_100_fetches`. Daily summary appended to `docs/evidence/` with the config hash so the
report can be tied to an exact configuration. Nothing in this repository rewrites the owner's pinned
120-page index or the frozen 54-case replay; a pilot must keep both hashes unchanged.

## 7. Decisions the owner must make before Phase 1

1. Approve `www.london.gov.uk/events` and `/whats-on` as the Phase 1 scope (or substitute a host).
2. State the rights basis and whether snippet indexing is permitted (`index_allowed`).
3. Confirm the contact address in the user agent.
4. Confirm 100 accepted pages/day and the 300-fetch gross ceiling.
5. Confirm the retention rule for staging documents (metadata + snippet, no body) and the takedown
   contact.
6. Authorise the first live request. Until then, this remains a proposal.
