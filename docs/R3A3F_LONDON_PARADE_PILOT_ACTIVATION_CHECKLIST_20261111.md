# R3-A3F — London Parade first-pilot activation checklist (owner-facing)

**Status:** prepared, **not activated** · `REAL_SOURCES_ADMITTED=0` · `THIRD_PARTY_CRAWLER_REQUESTS=0` ·
F3 = HOLD · Production HOLD · PR #10 draft.

Everything on this page is offline unless the owner signs the last two items. Destination Events
approval is **already attested**; the remaining work is recording its technical scope, not obtaining
new partnership approval.

## A. Scope and authorisation

| # | Item | Status | Evidence |
| --- | --- | --- | --- |
| A1 | Owner attestation of existing Destination Events approval and official Mine Media partnership | **RECORDED** | `docs/FB2_R3A3F_LONDON_PARADE_EXISTING_APPROVAL_20261111.md`; `owner_attestation` in the register |
| A2 | Existing-authorisation scope record completed from the agreement (reference, signer, dates, audience, snippet/redisplay rights, feed availability) | **PENDING** | `docs/R3A3F_LONDON_PARADE_DATA_USE_SCOPE_20261111.md` §1 |
| A3 | Canonical host and `www` redirect chain confirmed with the organiser | **PENDING** | scope record §1 |
| A4 | Reviewed seed list and permitted paths signed off | **PREPARED** | `/about/`, `/parade-location-timing/`, `/londonparade-participants/`, `/news-archive`, `/festivals/concerts/` |
| A5 | Admission record written with a distinct `owner_authorisation` reference | **PENDING** | store/CLI reject approval without it |
| A6 | Separate explicit **first-live-request** authorisation | **PENDING** | this checklist, item D2 |

## B. Technical readiness (verified offline)

| # | Item | Status | Evidence |
| --- | --- | --- | --- |
| B1 | 10-second crawl delay preserved, independent of future robots changes | **PASS** | `crawl_delay_floor_s=10` + regression test |
| B2 | One request in flight, full `Retry-After`, conditional revalidation | **PASS** | `HostPacer`, existing tests |
| B3 | Persisted caps: 20 accepted/day, 300 attempts/day, 30 minutes/day | **PASS** | `pilot_budget`, restart test |
| B4 | Depth 3, zero guessed-path probes | **PASS** | config + demos |
| B5 | Exclusions: shop, apply form, account, contact form, admin/login, Ticketmaster | **PASS** | robots + administrative-path tests |
| B6 | robots.txt redirects cannot reach an unapproved host, admin page or bypass pacing/budget | **PASS** | `_robots_redirect_gate` + closeout tests |
| B7 | Metadata-only storage with ≤320-character snippet, no body | **PASS** | staging rights mode |
| B8 | Edition separation, cancelled history, no invented future dates | **PASS** | three-source demo checks |
| B9 | Dashboard and JSON export show scope, state, per-source counts and novelty | **PASS** | `http://127.0.0.1:8787/`, `/api/report.json` |

## C. Proposed first-run limits

| Limit | Value |
| --- | --- |
| Seeds | `https://londonparade.com/parade-location-timing/`, `https://londonparade.com/about/` |
| Paths | the five reviewed sections only |
| Accepted documents | 20/day |
| Network attempts | ≤300/day (robots, hops and retries included) |
| Duration | ≤30 minutes/day |
| Spacing | ≥10s per host (robots `Crawl-delay`) |
| Depth | 3 |
| Probes | 0 |
| Storage | title, URL, dates, category, ≤320-char excerpt |

## D. Go / no-go

**D1 — owner signs the scope.** Confirm A2–A4 against the existing agreement, including whether the
index is internal-only. If the agreement is silent on snippet/redisplay, approve the narrow default
(metadata + ≤320-character excerpt, internal review, attribution and link-back) explicitly.

**D2 — owner authorises the first live request.** Only then: record the admission with
`owner_authorisation` (a distinct reference, not a repeated status string), enable the source, and run
one bounded P1 session. `approved=true` in a JSON file alone does not authorise anything: the store
and preflight reject approval without the documented reference.

**Expected first-run artefacts (kept as evidence):**
`report.redirects` (every hop, followed or blocked), `pilot_budget.today`, `url_admission.by_decision`,
per-source documents/categories/depth/duplicates, `novelty` with the SHA-256 pin, and the console JSON
download.

**Stop immediately if:** a non-200 robots, a robots denial, any off-origin redirect, any admin route,
a 429/503 (honour `Retry-After`, then stop the host), acceptance below 10% after 100 fetches, any
depth-4 request, any body storage attempt, any cap reached, or the owner's kill switch
(`set_source_enabled(source_id, false)`).

## E. Fallbacks

- **City Hall `/events`** remains the alternative if London Parade's scope record cannot be completed;
  it still needs its terms basis, contact and written admission.
- **Lord Mayor's Show** remains `RIGHTS_HOLD`; its terms permit linking only to the home page and
  forbid deep links.
