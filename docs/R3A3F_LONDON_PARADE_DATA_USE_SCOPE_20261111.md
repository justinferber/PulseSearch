# R3-A3F — London Parade existing-authorisation scope record

**Date:** 11 November 2026. **Status:** `OWNER_CONFIRMED_LONDON_PARADE_CONTENT_RIGHTS_P1_SCOPE_READY` ·
**`approved=false` · `index_allowed=false` · `REAL_SOURCES_ADMITTED=0` · F3 = HOLD · Production HOLD.**

This is **not** a fresh permission request. The owner has confirmed that **Destination Events Ltd
has already approved London Parade work and that Mine Media is the official London Parade partner**.
The purpose of this record is to capture what that existing authorisation covers — once — so the
crawler does not act beyond it and the owner is not asked for duplicate approval.

Source: owner attestation in the FB2 thread, 11 November 2026 (quoted in
`docs/FB2_R3A3F_LONDON_PARADE_EXISTING_APPROVAL_20261111.md`). The latest owner confirmation states: **“London Parade is just One of 100s of Mine Media clients. Yes we are approved to use any text or imagery we want.”** The owner answered yes to the proposed internal Pulse Search test that includes event metadata and ≤320-character excerpts. This establishes owner-attested content-use rights for London Parade and the proposed internal test; do not keep requesting additional Destination Events approval. The owner did not supply a letter, separate contract reference, signer or validity date in this conversation, so those remain unverified supporting metadata, not blockers to re-ask an already answered permissions question.

## 1. Recorded fields

| Field | Value | Status |
| --- | --- | --- |
| Organiser | Destination Events Ltd | attested |
| Authorised partner | Mine Media (official London Parade partner) | attested |
| What has already been approved | Mine Media official partnership and use of London Parade text and imagery, including internal Pulse Search title/date/category/link/≤320-character excerpt test | **owner confirmed 11 November 2026** |
| Existing letter / email / agreement reference | **not provided**; owner direct attestation `OWNER_DIRECT_ATTESTATION_2026-11-11_LONDON_PARADE` | optional supplementary evidence; do not require duplicate approval |
| Named source host | `https://londonparade.com` (apex used by all internal links) | verified read-only |
| Canonical host / `www` behaviour | apex `londonparade.com` serves the site; `www` is outside the proposed P1 scope and must remain unadmitted | apex-only scope is sufficient; no need for organiser to verify www |
| Reviewed public pages | `/about/`, `/parade-location-timing/`, `/londonparade-participants/`, `/news-archive`, `/festivals/concerts/` | prepared |
| Reviewed seeds | `/about/`, `/parade-location-timing/` | prepared |
| Machine-readable feed available | **unknown** — ask whether the existing arrangement includes an authorised JSON/CSV/API feed | open |
| Ingestion route | public-page crawl by Pulse Search; publisher-supplied feed **only if** the existing arrangement covers it | open |
| Title, date, route, category, canonical link | approved for proposed internal search test | confirmed by owner |
| Short excerpt | ≤320 characters, no page body in P1 by engineering choice | approved for internal pilot by owner |
| Audience | internal Mine Media/Pulse Search review for P1 | confirmed as proposed test; production publishing separate decision |
| Media rights (images) | use of London Parade imagery approved by owner attestation | confirmed; images still not ingested in P1 by design |
| Recheck cadence | 24h conditional revalidation, 168h for 404 rechecks | proposed |
| Crawl-delay | **10 seconds**, as published in `robots.txt` | observed and enforced |
| Effective date / review date | **not stated** | to record from existing paperwork |
| Takedown / withdrawal contact | `contact@londonparade.com` (general); named contact to confirm | provisional |
| Owner attestation date | 11 November 2026 | recorded |

## 2. Owner-confirmed permission scope and pilot limits

**Owner confirmed:** Destination Events has approved Mine Media to use London Parade text and imagery, and Mine Media is the official event partner. This expressly answers the prior question about an **internal-only Pulse Search test** using event titles, edition dates, categories, URLs and short text excerpts of up to 320 characters. A separate letter or contract identifier was not supplied in the conversation; do not invent one or repeatedly request a new organiser approval.

**P1 technical limits, not contractual denials:** We will initially ingest only public event metadata and ≤320-character excerpts, with no page-body storage, image copying or media downloads. The broader text and image permission need not be exercised during this bounded crawler test. Public production release, third-party works, participant personal information, external ticketing domains and other Mine Media clients are outside P1, and would require separate source-policy decisions.

The content-use approval is now **recorded**. The remaining step is the owner's separate decision to **activate one first live crawler run**, with source scope and budget logged at activation.

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

- Owner attestation: recorded and expanded to confirm London Parade text and imagery rights, including the internal metadata/snippet pilot (`owner_attestation` in the three-source register).
- Scope record: this document plus `docs/evidence/r3a3f_london_parade_scope.json`.
- Content-use rights: **owner-confirmed**; no additional Destination Events approval required. 
- Operational admission: **not yet enacted** — `owner_authorisation` stays null, `approved=false`, `index_allowed=false` until the separate first-live authorisation is recorded.
- First live request: **not yet authorised**. The content-use scope is confirmed; obtain only a distinct live-pilot go/no-go from the owner and log the narrow source configuration.
- No redundant permission request or contract-signature chase is necessary for the confirmed content-use rights. Feed availability is optional and not a precondition to the small P1 webpage test.
