# R3-A3F — first capped pilot: three candidate sources, individually reviewable

**Status: `PROPOSAL_ONLY_NOT_ADMITTED` · `REAL_SOURCES_ADMITTED=0` · F3 = HOLD · Production HOLD.**
The owner selected three candidates (City Hall, London Parade, the Lord Mayor's Show). Selection is
scope, not permission. Every record below keeps `approved=false`, `index_allowed=false`,
`probe_policy=[]`; no third-party request has been made. Machine-readable twins:

- `docs/evidence/r3a3f_three_source_admission.json` — the three-candidate register with audit evidence.
- `docs/evidence/r3a3f_pilot_source_proposal.json` — schema v3, reconciled with this document.
- `docs/R3A3F_SOURCE_AUDITS_20261111.md` — the full F0 findings.

## 1. Candidates at a glance

| # | Candidate | Origin & proposed scope | Controller | Robots (11 Nov 2026) | Rights state | Owner state |
| --- | --- | --- | --- | --- | --- | --- |
| A | **London City Hall** | `https://www.london.gov.uk`, `/events` only | GLA | 200; allows `/events`; no Crawl-delay; sitemap present | `PENDING_TERMS_REVIEW` | `robots_reviewed` |
| B | **London Parade** | `https://londonparade.com`, no path admitted; 5 pages reviewed | Destination Events Ltd — **text and imagery rights confirmed by owner, including internal Pulse Search test** | 200; `Allow: /`, **Crawl-delay 10**, search yes / AI-train no, no sitemap | `OWNER_CONFIRMED_DESTINATION_EVENTS_TEXT_AND_IMAGERY` | `robots_reviewed` |
| C | **Lord Mayor's Show** | `https://www.lordmayorsshow.london`, no path admitted | Show organisers (to confirm) | **404 — no robots.txt** | `PENDING_RESTRICTIVE_TERMS_AND_PERMISSION` | `rights_hold` |

`/whats-on` stays excluded from A. Cross-links to `cityoflondon.gov.uk`, `procession.`/`api.`
subdomains, `lnydp.com` and Ticketmaster convey no admission.

## 2. Source A — London City Hall (proposed record, not applied)

| Field | Proposed value |
| --- | --- |
| `source_id` | `london-gov-uk-events` |
| `origin` | `https://www.london.gov.uk` |
| `allowed_paths` | `["/events"]` |
| `proposed_seeds` | `https://www.london.gov.uk/events` |
| `rights_status` | `PENDING_TERMS_REVIEW` |
| `approved` / `index_allowed` | `false` / `false` |
| `store_body` / snippet | `false` / ≤320 characters |
| `probe_policy` / budget | `[]` / `0` |
| Robots snapshot | 200; allows `/events`; disallows `/search`, `/print/`, `/admin/`, `/user/*`, filter query parameters; no Crawl-delay; sitemap |
| Contact | owner to confirm |
| Historical baseline | 107 pages already in the pinned index |
| Pending | terms/re-use basis; confirm `/events` links eligible subpages and whether it paginates; contact and takedown recipient; written decision |

## 3. Source B — London Parade (proposed record, not applied)

| Field | Proposed value |
| --- | --- |
| `source_id` | `london-parade-official` |
| `origin` | `https://londonparade.com` |
| `allowed_paths` | `[]` — **nothing admitted**; review candidates only |
| `proposed_seeds` (review) | `/parade-location-timing/`, `/about/` |
| Further review candidates | `/londonparade-participants/`, `/news-archive`, `/festivals/concerts/` |
| `rights_status` | `OWNER_CONFIRMED_DESTINATION_EVENTS_TEXT_AND_IMAGERY` |
| `approved` / `index_allowed` | `false` / `false` |
| `probe_policy` / budget | `[]` / `0` |
| Robots snapshot | 200; `Allow: /`; `Crawl-delay: 10`; `Content-Signal search=yes, ai-train=no, use=reference`; no sitemap |
| Contact | `contact@londonparade.com`; named scope and takedown contact to confirm |
| Event basis | 2027 edition, 1 January 2027, 1pm |
| Excluded | `/shop/`, `/takepart/`, `/account/`, `/contact/`, Ticketmaster |
| Outstanding | Content-use rights confirmed by owner. First-live-run go/no-go and owner-authorised source admission remain pending. Apex host only; no need to admit `www`. Feed availability optional. |

Destination Events' approval, Mine Media's official partnership and London Parade **text and imagery use rights** are **confirmed by owner**, including the proposed internal Pulse Search metadata and short-snippet test. Do not ask for another organiser permission. The pilot stays technically narrow; no public production switch is implied.

The confirmed scope is recorded in `docs/R3A3F_LONDON_PARADE_DATA_USE_SCOPE_20261111.md`. The first live crawler run still needs a distinct operational owner decision. If a structured public feed is available it becomes a separate input
connector with its own provenance, not a crawler depth shortcut.

## 4. Source C — Lord Mayor's Show (proposed record, not applied)

| Field | Proposed value |
| --- | --- |
| `source_id` | `lord-mayors-show-official` |
| `origin` | `https://www.lordmayorsshow.london` |
| `allowed_paths` | `[]` — **nothing admitted**; `RIGHTS_HOLD` |
| `proposed_seeds` (review) | `/` (home page only, consistent with the terms) |
| Further review candidates | `/history/`, `/history/*`, `/programme/`, `/lord-mayors-procession/`, `/practicalities/where-to-go/`, `/closures/` |
| `rights_status` | `PENDING_RESTRICTIVE_TERMS_AND_PERMISSION` |
| `approved` / `index_allowed` | `false` / `false` |
| `probe_policy` / budget | `[]` / `0` |
| Robots snapshot | **404** — no robots.txt; absence is not permission |
| Terms | all rights reserved; links **only to the home page**; deep links, framing and links from non-owned sites forbidden; no automated-collection or snippet licence |
| Contact | `enquiries@lordmayorsshow.london` |
| Event basis | 2026 Show, Saturday 14 November 2026, 11am |
| Excluded | `/terms-of-use/`, `/book/`, `procession.` and `api.` subdomains, `cityoflondon.gov.uk` |
| Pending | explicit permission or a licensed-feed/link-only arrangement; host and subdomain scope; reviewer and evidence |

## 5. Novelty: 107 known pages are not 107 new pages

`novelty.py` opens the pinned index with SQLite `mode=ro` **and verifies its SHA-256**
(`bb8e5202…7368c35d`) before reading a single URL. It reports `historical_index_pages`,
`staged_documents`, `already_in_historical_index`, `novel_documents` and a sample, and the same block
per source. A pilot's daily figure must be quoted as **novel documents**, with the overlap stated:
for City Hall the 107-page baseline is expected overlap from day one.

## 6. Hard pilot limits (persisted, not per-process)

| Limit | Value | Where enforced |
| --- | --- | --- |
| Accepted documents | **20/day** (P1) | store ledger `pilot_budget`, checked before indexing and at each loop |
| Total network attempts | **≤300/day**, including robots, redirect hops and retries | fetcher attempt gate, same ledger |
| Run duration | **≤30 minutes**, cumulative per UTC day | persisted `run_seconds` + loop check |
| Depth | 3 link hops from an approved seed | frontier and pre-network check |
| Redirects | ≤5 per claimed URL, each re-authorised | redirect gate + `redirect_log` |
| Probes | **0** | `probe_policy=[]`, budget 0 |
| Pacing | one in flight; ≥3s or the host's stricter Crawl-delay (10s for B) | `HostPacer`, shared by robots/content/redirects |
| Storage | metadata + ≤320-char snippet; **no body** | staging rights mode |

The ledger lives in the crawl database, so a crash and restart cannot reset the day's allowance.

## 7. Phases

| Phase | Scope | Exit |
| --- | --- | --- |
| **P0 — compliance review (no fetching)** | F0 audits, robots/terms reading, contact confirmation, written decision per source | Written admission record with `owner_authorisation` |
| **P1 — one source, 20 accepted/day, 3 days** | `/events` (A) or a permitted B seed; zero probes | Zero robots violations, zero off-origin requests, novelty recorded, acceptance ≥15% |
| **P2 — 100 accepted/day, 7 days** | Same paths | Acceptance ≥20%, no 429 storm, one recheck outcome |
| **P3 — second path or second host** | Separate owner decision and record | New admission |

## 8. Stop conditions

Any one halts the run: fetch to an unadmitted host; indexing with `index_allowed=0`; a
robots-disallowed request; a followed off-origin/out-of-scope redirect; robots 5xx/403 or three
consecutive 5xx; a 429/503 (honour the full `Retry-After`, then stop the host); acceptance below 10%
after 100 fetches; any depth-4 request; any non-HTML parse or body storage; any pilot cap reached;
owner kill switch.

## 9. F3 decision

**F3 = HOLD.** Recommended first live source: **City Hall `/events`**, provided its terms/re-use basis
is recorded and `/events` is confirmed as the listing. London Parade now has an owner-confirmed rights basis and is the preferred first live pilot candidate, subject only to separate operational admission and a bounded first-live decision. The Lord Mayor's Show stays
`RIGHTS_HOLD` until its restrictive terms are addressed.

The first external GET, the merge of PR #10 and any production promotion each require separate owner
authorisation. Until then the code refuses to run with no admitted source, and this document admits
nothing.

## Owner permission update — 11 November 2026

The owner confirms Mine Media is Destination Events' official London Parade partner and is authorised to use London Parade **text and imagery**, expressly confirming the proposed internal Pulse Search test with event information and ≤320-character excerpts. This **closes the organiser content-use rights question** for the limited P1 test; no fresh organiser permission is required. The P1 design still excludes image downloading, page bodies, login/application areas, personal participant information, other hosts and production publishing. Treat the attestation as an owner statement, not an invented signed contract. The source remains `approved=false`, `index_allowed=false` until the owner separately authorises the actual first live crawler run; keep City Hall as fallback and Lord Mayor's Show on rights HOLD.
