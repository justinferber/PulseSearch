# R3-A3F — three source-permission assessments (F0)

**Date:** 11 November 2026. **Method:** read-only manual browser and public research. The Pulse
Search crawler was **never pointed at any of these hosts**; `THIRD_PARTY_CRAWLER_REQUESTS=0`. Nothing
here grants permission, and no approval flag was changed. **Production: HOLD. F3: HOLD.**

Machine-readable twin: `docs/evidence/r3a3f_three_source_admission.json` (register v1, three
sources, all `approved=false`, `index_allowed=false`, `owner_authorisation=null`).

## A — London City Hall (`www.london.gov.uk`)

| Item | Finding |
| --- | --- |
| Proposed scope | origin `https://www.london.gov.uk`, `allowed_paths=["/events"]` only |
| Proposed seed | `https://www.london.gov.uk/events` |
| Controller | Greater London Authority (website and content) |
| Robots | HTTP 200 on 11 Nov 2026. `User-agent: *`; allows `/events`; disallows `/search`, `/print/`, `/entityprint/`, `/admin/`, `/user/*`, `/core/`, `/profiles/` and query-filter parameters; **no Crawl-delay**; sitemap `https://www.london.gov.uk/sitemap.xml` |
| Terms | Not yet reviewed to a citable clause; the site's privacy/accessibility page is the starting point. **No re-use basis is recorded yet.** |
| Contact for user agent | not confirmed |
| Index baseline | 107 of the 120 pinned pages are this host — expected overlap, not novelty |
| State | `robots_reviewed` |
| Unresolved | terms/re-use basis; confirmation that `/events` is a listing that links eligible subpages and whether it paginates; contact and takedown recipient; written owner decision |
| Explicitly excluded | `/whats-on` (unverified — do not reintroduce), `/search` (robots-disallowed) |

## B — London Parade (`londonparade.com`)

| Item | Finding |
| --- | --- |
| Proposed scope | **none yet** — `allowed_paths=[]` until permission exists |
| Proposed seeds (review only) | `https://londonparade.com/parade-location-timing/`, `https://londonparade.com/about/` |
| Controller / organiser | Destination Events Ltd — **approval already confirmed by owner; Mine Media is official partner** |
| Relationship | Mine Media works commercially with the event. **Commercial representation is not a crawler, indexing, link-retention or snippet licence.** |
| Robots | HTTP 200 on 11 Nov 2026, Cloudflare-managed plus site rules: `User-agent: *` `Allow: /`, `Content-Signal: search=yes, ai-train=no, use=reference`, **`Crawl-delay: 10`**, no `Sitemap:`; a long list of AI/training bots is disallowed. Crawl-delay 10 would override the 3s floor for this host. |
| Terms | No dedicated terms-of-use page found; footer reads “Londonparade.com 2025 \| All Rights Reserved”. The owner attests an existing Destination Events approval, so the footer is not treated as overriding it; the approval's technical scope (crawl, snippet, redisplay, retention) is not yet documented. |
| Contact | `contact@londonparade.com` (general); organiser permission contact to confirm |
| Event basis | 2027 edition on 1 January 2027, 1pm; 2026 was the 40th edition |
| Verified public pages worth proposing | `/about/`, `/parade-location-timing/`, `/londonparade-participants/`, `/news-archive`, `/festivals/concerts/` |
| Excluded | `/shop/`, `/takepart/` (application form), `/account/`, `/contact/` (forms), Ticketmaster (third-party host) |
| State | `robots_reviewed` (rights pending) |
| Unresolved | record the existing approval's data-use scope and document reference (do **not** request redundant approval); canonical host (apex vs `www`) and redirect behaviour; current path architecture for 2027; whether an authorised structured public feed is available |
| Preference | An existing or newly supplied organiser JSON/CSV feed is a **different connector** with its own provenance — not a crawler depth shortcut. Availability under the existing approval is unconfirmed. |

## C — Lord Mayor's Show (`www.lordmayorsshow.london`)

| Item | Finding |
| --- | --- |
| Proposed scope | **none yet** — `allowed_paths=[]`; RIGHTS_HOLD |
| Proposed seed (review only) | `https://www.lordmayorsshow.london/` (home page) |
| Controller | Show organisers; exact rights controller to confirm. The City of London page `cityoflondon.gov.uk/events/lord-mayors-show` is a **separate host** and is not admitted by this record. |
| Robots | **HTTP 404** on 11 Nov 2026 — no robots.txt is served. Absence of rules is not permission and gives no crawl-delay guidance. |
| Terms | Read on 11 Nov 2026: all intellectual property rights reserved; linking permitted **only to the home page**; “you must not… create a link to any part of our site other than the home page”; framing forbidden; links from websites not owned by the linker forbidden. No automated collection, indexing or snippet licence is granted. |
| Contact | `enquiries@lordmayorsshow.london` |
| Event basis | 2026 Show, Saturday 14 November 2026, 11am, Mansion House to Westminster |
| Public pages worth proposing **if** permission is granted | `/history/` and its subpages, `/programme/`, `/lord-mayors-procession/`, `/practicalities/where-to-go/`, `/closures/`; `/route/` currently redirects to the separate `procession.lordmayorsshow.london` host |
| Excluded | `/terms-of-use/`, `/book/`, `procession.` and `api.` subdomains (separate hosts, no admission) |
| State | `rights_hold` |
| Unresolved | explicit permission for automated discovery, snippet indexing and deep links; a licensed-feed or link-only arrangement; confirmation of canonical host and subdomain scope; reviewer, permission evidence and takedown contact |

## What this audit does **not** claim

- It does not establish permission for any host, path or snippet. For London Parade it records an owner-attested approval whose technical scope is not yet documented.
- It does not verify live crawl behaviour, response times or rate limits.
- It does not admit `cityoflondon.gov.uk`, `lnydp.com`, `ticketmaster.co.uk`, `procession.lordmayorsshow.london` or `api.lordmayorsshow.london` through a cross-link.
- The robots observations are a dated snapshot that must be re-read at the moment of admission.

## Recommended first live pilot (F3 decision, not authorisation)

1. **London City Hall `/events`** — recommended first, *if* the terms/re-use basis is recorded and
   `/events` is confirmed as the listing. Robots are reviewed, no crawl-delay applies, and the
   107-page baseline makes novelty measurable from day one.
2. **London Parade** — equally viable and higher event value, but **only** with written Destination
   Events permission; if a licensed feed is offered, use that connector instead of page extraction.
3. **Lord Mayor's Show** — last. The published terms forbid deep links and reserve all rights; without
   an explicit licence or a link-only arrangement it stays `RIGHTS_HOLD`.

All three remain `approved=false` and `index_allowed=false` until a distinct, written owner decision
is recorded (`owner_authorisation`), and the first external GET still needs its own authorisation.
