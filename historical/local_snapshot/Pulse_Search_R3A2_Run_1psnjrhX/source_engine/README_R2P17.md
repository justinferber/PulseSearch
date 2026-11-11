# Pulse Search R2-P17 — Multi-Origin Research Index Consolidation

Independent, zero-paid-API search engine. This is an **offline research index consolidation**, not a production release or grant of commercial publication rights.

## Reused owner-accepted evidence

- R2-P16 accepted *live* research database: `Pulse_Search_R2P16_Run_lrLrh7/owner_pilot/independent_research_clone.sqlite` containing 4 indexed City Hall event webpages and 112 separate sitemap URL leads.
- R2-P12 earlier real-source pilot database, located by the runner through an exact cryptographic match of its `pilot/query_results.json` against the owner-human-reviewed `results_sha256 = 98eea7d517d308060fa9457fcfcb07496d551d26b9092ce446fd72c56495f0cf`. No arbitrary or unmatched pilot is accepted.
- Original R2-P12 human judgements included in `owner_review_r2p12.json` for provenance and comparison. **Do not re-grade new first results automatically.**

## What the component does

1. Open both owner databases read-only. Verify the original R2-P12 query result digest, index fingerprint, question/grade binding, and approved source scopes. Verify exactly four expected City Hall pages and 112 candidates in the R2-P16 index.
2. Copy the R2-P16 DB to a fresh temporary SQLite DB using SQLite's read-only backup facility. Preserve original candidate URLs and existing page records.
3. Incorporate previously indexed, original-source-approved pages from R2-P12 into the new research copy, recording unchanged origin and URL provenance, rights basis and original fetched timestamps.
4. **Intentionally skip the R2-P12 City Hall `/media-centre/` source** because R2-P16 already approves the same origin under a *different* `/events/` path. That conflict needs an independent source-policy decision; this build cannot silently expand the City Hall source approval.
5. Query the resulting multiple-origin FTS index against 15 previously reviewed questions and four City Hall tests. Mark first hits without prior relevance grade for fresh human review. Suppress explicit wrong-year matches; report no-match honestly.
6. Check source DB SHA-256s have not changed. Produce `combined_report.json`, `search_review.html` and a separate `combined_research_index.sqlite` in a new owner audit folder.

## Safety / limits

- No crawls, HTTP requests, Brave API calls, external search or source reapproval.
- No writes to either original database. Original source metadata retained. Any mismatched fingerprint or unexpected scope produces `HOLD` (exit 2).
- No snippet/commercial display rights are inferred; internal metadata research only.
- Search results are **unverified unless graded for that exact URL**, and a previously graded result in a new ranking is not evidence of production relevance.
- Combining two small, preselected research corpora is not broad open-web coverage.

## WSL

Save the `Pulse_Search_R2P17_Complete_20261023.zip` to `C:\Users\justi\Desktop\pulseunity\ChatGPTCode` and extract into that folder. Run the one-pass script `Pulse_Search_R2P17_OnePass_20261023.sh` to verify the manifest and run all tests. Set `PULSE_SEARCH_RUN_OWNER_AUDIT=1` to run the bounded read-only merger against the previously accepted original databases. It performs no network requests.
