# FB2 — Owner correction: Destination Events approval already exists
**11 November 2026.** Applies to standalone Pulse Search R3-A3F PR #10. No crawler has been authorised to send its first live third-party HTTP request by this instruction alone.

## Owner confirmation — do not lose this fact

The project owner explicitly confirms: **“I do have Destination Events' approval for London Parade Mine Media is the official partner.”**

This supersedes the repeated suggestion that the owner needs to seek new permission from Destination Events merely to establish a relationship. **Do not ask them to obtain approval they say they already have.**

Record the existing approval as an **owner-attested organiser authorisation**, distinct from a machine-validated permission scope. The exact approval terms / documentary reference were not provided in this statement. Do not invent a written agreement, signer, dates, contractual rights or rights over all pages. Do not treat `All Rights Reserved` or robots as negating an actual agreement, but equally do not extrapolate the partnership into unrestricted automated collection or public snippet licensing.

## What to do next (FB2, authorised offline)

1. Amend all operator notes, source audit, pilot proposal and dashboard to read **“Destination Events approval confirmed by owner; technical data-use scope/document reference to record”** instead of “no organiser approval” or “seek permission.” The source register now includes `owner_attestation` and `organiser_approval_status` for `london-parade-official`. Keep the existing dashboard-compatible `state=robots_reviewed` until an owner-signed admission is actually recorded.
2. Draft a short owner-facing **existing-authorisation scope record**, not a fresh approval request. Fields: organiser (Destination Events Ltd), authorised partner (Mine Media), what has already been approved, existing letter/email/agreement reference if available, named source host, exact allowed URLs, machine-readable feed availability, whether ingestion may crawl pages and/or ingest publisher-supplied data, whether title/date/route/category/links and ≤320-character snippet can be stored and displayed, audience (internal / public), media rights, recheck cadence, `Crawl-delay` 10, authorisation effective/review dates, takedown/withdrawal contact, owner attestation date.
3. If the existing arrangement permits reuse of **organiser-supplied public event metadata**, prepare that ingestion route first. It is cleaner than web scraping; it must be its own source connector, carrying publisher-supplied provenance and a data-use policy, not be mislabeled a 3-hop crawl.
4. Keep all current exclusions for `/shop/`, `/takepart/`, `/account/`, forms, personal participant information and third-party ticketing. Confirm canonical host and `www` redirects, and final narrow review of the initial paths.
5. Produce the smallest possible **P1 London Parade readiness pack**: authorisation scope record, source registry diff, owner activation checklist, offline path tests, report fields. No code redesign. Retain City Hall `/events` as the fallback source and Lord Mayor's Show as `RIGHTS_HOLD`.
6. Recheck the narrowly outstanding `robots.txt -> /admin` same-origin redirect test from the PR review, if not already resolved, without expanding web-crawler scope.
7. When the exact existing approval's scope is recorded (by an owner-attested statement or a reference to existing paperwork), present it for the owner's explicit **first-live-request decision**. Do not self-activate by merely changing `approved=true` in an imported JSON.

## Status boundary

**Existing Destination Events approval:** Owner confirmed.  
**Precise crawler/indexing/redisplay scope:** Not yet evidenced in the provided message; capture it once, do not insist on another redundant permission request.  
**Real sources admitted:** 0.  
**Third-party crawler requests under Pulse Search:** 0 reported.  
**F3 and production:** HOLD until separately authorised.

**Important:** This is a standalone Pulse Search source decision, not permission to publish into the Pulse UNITY Events Engine or to use other event organisers' content.
