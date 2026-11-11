# Pulse Search R2-P29 — 120-Page Relevance Shadow (25 October 2026)

**Research only. Not deployed to the API, not a new crawl, not a general search-quality claim.**

Purpose: compare the original broad-OR ranker with a limited 12-question title/path/year/intent-gated **read-only** shadow ranker against the **actual owner-held 120-page SQLite research clone**.

## Original evidence

- The exact R2-P27C owner's live run report is bundled and SHA-bound. Its result `LIVE_100_NEW_INDEXED_CLONE_ONLY_PASS` confirms 103 new City Hall event pages, 120 indexed pages total. The 121 HTTP requests belong to the **previous** successful live crawl, not this package.
- Exact R2-P24 corrected human grades are bundled and SHA-bound; **7 direct, 2 partial, 1 related, 1 irrelevant top1 and one no-result**, before the 120-page expansion.
- Accepted R2-P21 engine is byte-for-byte included (sha `984fd5126cd229f756ee7cc32153e6e50f979634047044d046181825f5b809e5`) and runs 285 unchanged regression tests. No accepted file is modified.
- This experiment has 20 new focused tests, including wrong-event/wrong-year, GP/NHS, GOV.UK, MDN, live-shop/weather abstention and deterministic ranking.

## Owner machine command

1. Save complete release ZIP to `C:\Users\justi\Desktop\pulseunity\ChatGPTCode`.
2. Verify the *outer ZIP* SHA provided in the ChatGPT download answer and unpack using `python3 -m zipfile -e` to the same folder.
3. Run `bash "$D/Pulse_Search_R2P29_20261025/OnePass.sh"`, where `D="$(wslpath -u 'C:\Users\justi\Desktop\pulseunity\ChatGPTCode')"`.
4. Read generated `r2p29_shadow_report.json` and `r2p29_shadow_review.html` from a fresh `Pulse_Search_R2P29_Run_...` folder; share these files or the WSL terminal output for acceptance.

## Safety gates

- Read-only SQLite `mode=ro&immutable=1` + `PRAGMA query_only=ON`, SHA-256 checked before/after; fixed owner research clone path: `Pulse_Search_R2P27C_Run_gURzKuV2/live/expanded_live_100_research_index.sqlite`.
- Requires 120 active pages, 120 FTS rows, 7 indexed sources, and **103 exact owner-report URL/title entries** in the owner clone.
- Reproduces the **12 existing R2-P27C first-three result lists** using the accepted `pulse_search_engine.search` before comparing proposed rank changes; holds on drift or unexpected sources/metadata.
- Does not alter any SQLite page, table, approved source, source permissions, user account, search API or production ranking configuration.
- **Zero network requests**, paid search-provider calls, new crawling, and publisher content redistribution. The output contains only search metadata, not raw page bodies.
- NEW result URLs have `previous_human_grade=null` and never count automatically as correct. Previously known useful top1 URLs (9 questions) must remain top1; both live-local questions must abstain; the previously rated London NYE main event result must return to top1. If a gate fails, the output is `HOLD_KNOWN_HUMAN_QUALITY_GATE` and the experiment is **not accepted**.

## Experimental ranking contract and limitations

The pre-existing corpus of 120 pages is small and unusually event-heavy. This experimental reranker retrieves up to 200 pages from existing FTS5, then uses title/path matching, an exact requested event year, and conservative rules for live opening-hours and weather queries. This intentionally favours precision over recall and **may hide relevant pages with poor titles or paraphrases**; it does not prove generalized semantic relevance or availability of live data. A real public rollout would require larger unbiased benchmarks, better source breadth, full records rights/licences and continuing security tests.

The entire package is independent **Pulse Search**; no Pulse UNITY Events/UNA/AWS integration or automated event publication is permitted or attempted.
