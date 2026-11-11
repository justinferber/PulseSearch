# Pulse Search R2-P21 — Independent three-source coverage expansion

**Purpose:** Expand actual indexed coverage beyond the 14-page/7-origin research baseline to selected new publisher pages in three already-known origins (GOV.UK, NHS and MDN). This is an internal, technical metadata research pilot, **not** production, source-wide authorisation, content reproduction or subscription publication approval.

## Why

The owner accepted R2-P20 human-review score on 24 Oct 2026: of 12 previously unseen questions, nine returned first hits (two direct, four partly useful, two merely related, one irrelevant) and three held-back live-data queries all had `unsure` assessments. The tiny corpus omits original-publisher pages that address ordinary questions. Building a larger real index is more useful than iterating solely on synthetic or hand-tailored filters.

## Exact pages being considered for one-off indexing

- NHS blood tests `https://www.nhs.uk/tests-and-treatments/blood-tests/` — candidate for blood-test booking guidance.
- GOV.UK Council Tax bands `https://www.gov.uk/council-tax-bands` — service information for looking up a band; does **not** provide an arbitrary household's band without user-provided address and a separate lookup.
- MDN JavaScript learning `https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Scripting/What_is_JavaScript` — JavaScript learning.

These are **manually researched original-publisher seed URLs**, and are not falsely described as Pulse Search sitemap discoveries. The independent crawler and index will fetch and process the bytes if permitted. URLs must not be copied from Brave or any paid search provider. A hand-researched source lead is a legitimate but different form of discovery than R2-P14B sitemap discovery.

## Security and source-policy handling

1. Verify the owner R2-P17 original search index against its exact previously owner-scored SHA-256 `7a12e77fc5867fa27428023c30858f33488c5343c0e4a59a2d5455a721ef02ed`; also bind the exact owner R2-P20 human review (`e046bef682aa3e5f55ba1fdae79613e6a798d5c16cab4e6ead783c1af1ac51a6`). Verify 14 indexed pages, seven indexed sources, 112 prior City Hall candidate URLs, and unchanged source policies. No owner database write is allowed.
2. Clone original SQLite with the accepted read-only SQLite backup method. In the clone ONLY, after explicit separate operator approval, add **one exact path** to each of three existing source allowlists. Do not authorise an entire web domain or arbitrary URLs. Preserve original rights restrictions and append internal-only purpose.
3. Bounded live crawl: *at most three exact new URLs*, `max_depth=0`, minimum two-second per-origin delay, scoped robots checks, no sitemap fetching or discovered-link follow, public HTTPS/SSRF checks, redirects/noindex restrictions per existing crawler. No paid search API or external search-engine request.
4. Compare old/new 14 pages, full-text index integrity, owner database hash, and six illustrative ordinary search questions. All *new* first results remain **human-ungraded**. Return explicit HOLD when any of the three new pages cannot be indexed. In a partial run the completed clone/report is retained as evidence.
5. No production API changes, source reapproval in accepted databases, or permission to republish third-party text. Commercial use requires a separate terms/licence review. Do not use this research result to assert live availability or personal account facts.

## Acceptance

- Local tests: existing 269 + 16 new R2-P21 tests = **285**. Live network is not involved.
- Owner offline preflight: exact original owner index+review SHA checked, clone created unchanged, zero network, zero new pages, status `READ_ONLY_PREFLIGHT_PASS_LIVE_PENDING`.
- Optional live: explicit `PULSE_SEARCH_RUN_LIVE=1 PULSE_SEARCH_APPROVE_THREE_NEW_PATHS=YES` owner action. If all three exact pages are fetched and indexed in the clone, `RESEARCH_CLONE_ALL_THREE_INDEXED_NOT_PRODUCTION` (exit 0). Otherwise report `LIVE_PARTIAL_OR_NO_NEW_PAGES_HOLD` (exit 2). This tests three-source retrieval and indexing, **not** autonomous URL discovery, long-term freshness, relevance at web scale, or commercial rights.

## WSL

Save `Pulse_Search_R2P21_Complete_20261024.zip` to `C:\Users\justi\Desktop\pulseunity\ChatGPTCode`, extract it there, then run `bash "$D/Pulse_Search_R2P21_OnePass_20261024.sh"`. To bind the owner evidence, use `PULSE_SEARCH_RUN_OWNER_AUDIT=1` with the same command. Only if separately approved, set both `PULSE_SEARCH_RUN_LIVE=1` and `PULSE_SEARCH_APPROVE_THREE_NEW_PATHS=YES` to fetch the three pages. Reports live in unique run folders under ChatGPTCode. No source database or production API writes.
