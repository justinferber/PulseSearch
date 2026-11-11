# R3-A3F — London Parade existing-authorisation scope record

**Date:** 11 November 2026. **Status:** `OWNER_ATTESTED_EXISTING_APPROVAL_SCOPE_TO_RECORD` ·
**`approved=false` · `index_allowed=false` · `REAL_SOURCES_ADMITTED=0` · F3 = HOLD · Production HOLD.**

This is **not** a fresh permission request. The owner has confirmed that **Destination Events Ltd
has already approved London Parade work and that Mine Media is the official London Parade partner**.
The purpose of this record is to capture what that existing authorisation covers — once — so the
crawler does not act beyond it and the owner is not asked for duplicate approval.

Source: owner attestation in the FB2 thread, 11 November 2026 (quoted in
`docs/FB2_R3A3F_LONDON_PARADE_EXISTING_APPROVAL_20261111.md`). The attestation did **not** include a
letter, email or contract reference, signer, validity dates, or page-level scope. Those fields are
left explicitly blank rather than invented.

## 1. Recorded fields

| Field | Value | Status |
| --- | --- | --- |
| Organiser | Destination Events Ltd | attested |
| Authorised partner | Mine Media (official London Parade partner) | attested |
| What has already been approved | Event partnership plus approval for London Parade work; precise crawler/indexing/redisplay scope not stated in the message | attested, scope pending |
| Existing letter / email / agreement reference | **not provided** | to record from existing paperwork |
| Named source host | `https://londonparade.com` (apex used by all internal links) | verified read-only |
| Canonical host / `www` behaviour | apex `londonparade.com` serves the site; one read-only check of `https://www.londonparade.com/` returned the same home page. The redirect chain was not observable from that fetch — confirm with the organiser before the first live run | partially verified |
| Reviewed public pages | `/about/`, `/parade-location-timing/`, `/londonparade-participants/`, `/news-archive`, `/festivals/concerts/` | prepared |
| Reviewed seeds | `/about/`, `/parade-location-timing/` | prepared |
| Machine-readable feed available | **unknown** — ask whether the existing arrangement includes an authorised JSON/CSV/API feed | open |
| Ingestion route | public-page crawl by Pulse Search; publisher-supplied feed **only if** the existing arrangement covers it | open |
| Title, date, route, category, canonical link | proposed for storage and display | coverage to confirm against agreement |
| Short excerpt | ≤320 characters, no page body | proposed; snippet/redisplay right to confirm |
| Audience | internal Mine Media/Pulse Search review by default | public display not assumed |
| Media rights (images, video, audio) | **not claimed** | excluded |
| Recheck cadence | 24h conditional revalidation, 168h for 404 rechecks | proposed |
| Crawl-delay | **10 seconds**, as published in `robots.txt` | observed and enforced |
| Effective date / review date | **not stated** | to record from existing paperwork |
| Takedown / withdrawal contact | `contact@londonparade.com` (general); named contact to confirm | provisional |
| Owner attestation date | 11 November 2026 | recorded |

## 2. What the approval is taken to cover — and not cover

**Taken to cover:** that Mine Media may work with London Parade as official partner, and that using
London Parade's public event information for Pulse Search is not an unauthorised partnership use.

**Not established by the attestation, and therefore not assumed:** permission to crawl at unlimited
depth or rate; permission to store page bodies; permission to display excerpts publicly; permission
for images, video or audio; permission covering third-party content embedded on the site; permission
for ticketing hosts; permission lasting beyond an unstated term; permission for other organisers'
events.

The site's “All Rights Reserved” footer is noted but does not override an actual agreement; equally,
the partnership is not extrapolated into unrestricted automated collection or a public snippet
licence. If the existing paperwork is silent on crawl/snippet/redisplay, the owner decides the
narrowest safe scope (metadata plus ≤320-character excerpt, internal review) rather than expanding it
by inference.

## 3. Scope actually prepared for the pilot

- **Origin:** `https://londonparade.com` only.
- **Paths (reviewed):** `/about/`, `/parade-location-timing/`, `/londonparade-participants/`,
  `/news-archive`, `/festivals/concerts/`, plus public 2027 edition and news pages linked from them.
- **Seeds:** `/parade-location-timing/` and `/about/`.
- **Depth:** 3 link hops; zero guessed-path probes.
- **Excluded:** `/shop/`, `/takepart/` (application form), `/account/`, `/contact/` (form),
  administrative/login routes, participant personal data, `ticketmaster.co.uk` and all other hosts.
- **Pacing:** 10s floor per host, enforced independently of a future robots change; one request in
  flight; `Retry-After` honoured in full.
- **Caps:** 20 accepted documents/day, ≤300 network attempts/day, ≤30 minutes per UTC day
  (persisted), metadata + ≤320-character snippet, no body storage.
- **Edition discipline:** 2027 only as announced; earlier editions labelled as past; cancelled
  editions recorded as history; never infer a future date from an older page.

## 4. Evidence status

- Owner attestation: recorded (`owner_attestation` in the three-source register).
- Scope record: this document plus `docs/evidence/r3a3f_london_parade_scope.json`.
- Admission: **not recorded** — `owner_authorisation` stays null, `approved=false`,
  `index_allowed=false`.
- First live request: **not authorised**. It requires the owner to confirm this scope and give a
  separate go/no-go after the activation checklist is complete.
- No redundant permission request is to be sent to Destination Events for the partnership itself; the
  only open question is the technical scope and feed availability.
