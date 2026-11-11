# FB2 OWNER DIRECTIVE — R3-A3F: add London Parade and Lord Mayor's Show; keep City Hall
**Issued 11 November 2026.** Scope: **standalone Pulse Search**; no Pulse UNITY Events Engine, UNA publication or Mine Media website deployment. **Source selection and offline implementation authorised; first live third-party request NOT authorised.**

## Current Git base

- Repository: `justinferber/PulseSearch`
- Branch: `fb2/r3-a3f-depth3-category-crawler-20261111`
- Draft PR #10: https://github.com/justinferber/PulseSearch/pull/10
- The last FB2 security commit was `1b79e613ce7de560704cd3709f9beb4d3a3a4cb0`; owner scope-only candidate update followed at `89b0338134fa3973a38a49eab9c6a8324d1d2e8f`.
- Candidate proposal JSON already extended: `docs/evidence/r3a3f_pilot_source_proposal.json`. Preserve and reconcile the human-readable pilot proposal.

## Owner decision

**Retain City Hall and ADD London Parade plus the Lord Mayor's Show as three named source candidates.** This selects a source portfolio, not approval to crawl any of them. Keep all real hosts `approved=false`, `index_allowed=false`, `probe_policy=[]`; the new source records must not circumvent these gates.

| Candidate | Public starting site | Source controller / rights review | Initial scope proposal |
| --- | --- | --- | --- |
| A — London City Hall | https://www.london.gov.uk/events | GLA website permissions and robots | `www.london.gov.uk` only, `/events` only; `/whats-on` still excluded |
| B — London Parade | https://londonparade.com/ | Destination Events Ltd; Mine Media has an event relationship but must obtain explicit crawling/indexing permission from authorised organiser | Confirm canonical hostname, paths and permission, then admit reviewed individual seeds only; no default `/` or guessed paths |
| C — Lord Mayor's Show | https://www.lordmayorsshow.london/ | Show organiser / content rights controller; published terms may restrict reuse and deep linking | Confirm exact canonical hostname, current robots and licence; homepage/path seeds only after explicit permission; City of London corroboration site is a *separate* host |

The events themselves are useful ranking and edition test cases, including the **2027 London Parade** (formerly LNYDP), and the **2026 Lord Mayor's Show**. Do not infer or publish the year/date for a new edition from last year's page. Do not confuse public organizer event pages with event approval/publishing.

## F0. Source discovery/rights audit: NO crawler requests

1. Verify each site's actual canonical hostname, working public pages, page type, robots rules, site terms/licensing, organiser, data controller, copyright/usage restrictions, indexing/snippet rights, and takedown contact. Use independent read-only public research/manual browser for rights/robots as authorised; **do not run the Pulse Search crawler against the sites**.
2. Write three separate evidence-backed source admission proposals with `source_id`, exact origin, narrow allowed paths (avoid default `/`), URL seeds, robots snapshot/version and timestamp, contact, permission/rights basis, explicit `approved=false`, `index_allowed=false` until an owner-authorised decision, `store_body=false`, `probe_policy=[]`, per-host rate budgets and `approval_ref`. An organiser partnership alone is NOT a scraping licence.
3. Prefer an explicit organiser-supplied public feed (JSON/CSV), with negotiated rights, for London Parade where possible. Such a feed is a **distinct input connector** with its own provenance/permission; do not silently treat it as ordinary crawler depth.
4. City Hall: retain only `/events`; 107 historical URLs already indexed must be excluded from "novel" counts. Verify the existing URLs and that the root `/events` really links to eligible subpages, rather than assuming guessed paths work.
5. London Parade: verify current official page architecture before proposing `/news/`, `/about/`, event detail pages, etc. Exclude registration forms, private participant data, ticketing sessions and account portals. Seek explicit authorised organiser permission for crawling, link retention, snippets, ongoing recrawling and takedown.
6. Lord Mayor's Show: review restrictive website conditions separately for extraction, snippet copying and deep linking. If no permission exists, record `RIGHTS_HOLD` and propose a direct licensed feed or allowed public metadata/link-only route. City of London pages and event subdomains are not automatically covered by the Show host's admission.
7. Reflect sources distinctly in the dashboard: `candidate`, `robots_reviewed`, `rights_hold`, `owner_approved` as separate auditable states. **Never present a candidate source as crawled or indexed.**

## F1. Offline implementation and testing: authorised now

8. Finish previously requested *technical* pre-pilot corrections, if not already committed: ensure initial queued URL is checked for source origin, scope and indexing permission BEFORE robots or content network requests; enforce every same-host GET→redirect pacing gap; enforce total HTTP attempts including robots+redirects+retries, P1 20 accepted/day, ≤300 network requests/day, ≤30-minute run, zero guessed probes, persisted limits across restarts; pin SHA-256 of the 120-page historical novelty reference and report meaningful net-new qualifying documents. An import manifest's `approved=true` alone cannot confer owner authorisation.
9. Run deterministic offline test sites for **all three** proposed sources, each with distinct host, rights, `robots.txt`, 301/302 redirects and provenance. Include historic/previous vs current editions; article, event page and listing; false dates, cancelled events; duplicate syndicated material; noindex/robots denial; off-domain redirects and disallowed paths. With pending approvals assert **zero external requests**, **zero documents newly indexed from those three real hosts**, and no hidden path expansion.
10. Build *standalone search* relevance tests for City Hall listings, London Parade (annual New Year's Day parade, performances, route/times) and Lord Mayor's Show (civic procession, history and programme) across event information, local-language and generic category queries. Positive searches must find both named parades, and Pride/Diwali/CSD/Stadtfest continue to remain retrievable. Explicit query-local exclusion must not mutate crawler source access.
11. Show in the existing localhost console: three candidates and separate permissions; offline simulation; genuine depth-0/1/2/3 link chain; discovered/accepted/novel page counts per source; dates and document provenance; downloadable JSON evidence.
12. Re-run the existing crawler suites, archived 25/25 modules 419 tests, original 54 frozen replay and byte pins. Never grade the user's workbook automatically or contaminate the accepted 120-page corpus. Keep PR #10 draft; leave production on HOLD.

## F2. First live pilot — requires separate future owner authorisation

- The owner has selected **three candidates**, not authorised the first external GET. After F0/F1 evidence, recommend **one** approved source for P1: possibly London Parade first **if** Destination Events explicitly grants crawling and indexing rights; otherwise City Hall if its use basis is established; Lord Mayor's Show only after its restrictions are addressed.
- P1 cap: **20 accepted documents/day**, and **≤300 total network attempts/day** across any approved source, **≤30 minutes per run**, no guessed probes, one in-flight per host and ≥3s spacing or stricter source rules. Keep owner kill switch and no automated schedule.
- More hosts, more paths, higher throughput and eventually ~1,000 *relevant new indexed* pages/day require separately approved stages and actual measured useful-page yield; this event-first experiment is not a 1,000/day guarantee.

## Deliverables

1. Commit corrected human-readable `docs/R3A3F_PILOT_SOURCE_PROPOSAL_20261111.md` to agree with updated machine JSON; include three individually reviewable source tables and pending rights checks.
2. Three source-admission **proposals**, each unadmitted by default; provide evidence URL, robots and rights findings, safe path/seed proposal, contact and per-host budget. Do not invent permission.
3. Test and fix five pending operational gates; updated offline tests, logs and a SHA-pinned evidence report.
4. Dashboard showing all three candidates with state, category coverage and JSON export; details usable by the owner in Chrome.
5. Exact Git commit, passing test totals, unresolved source issues, and a clear `F3=HOLD` or narrowly recommended pilot review decision. **Do not start live crawling, production promotion or merge the draft PR.**

**Acceptance labels:** `THREE_CANDIDATES_REGISTERED_FOR_REVIEW=PASS`, `REAL_SOURCES_ADMITTED=0`, `THIRD_PARTY_CRAWLER_REQUESTS=0`, `MAX_HOPS=3`, `ORIGINAL_INDEX_UNTOUCHED=PASS`, `SIGNED_HUMAN_GRADING=PENDING`, `PRODUCTION=HOLD`.
