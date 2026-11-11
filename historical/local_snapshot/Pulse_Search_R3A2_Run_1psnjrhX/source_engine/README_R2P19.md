# Pulse Search R2-P19 — Static-index live-coverage abstention

Independent general-purpose search engine. **Offline research only, not a production API change.** No paid search-provider calls, no crawler changes, no modifications to the accepted owner databases.

## Why

The SHA-verified R2-P18 human assessment of the accepted 14-page, seven-origin R2-P17 research index recorded 13/19 directly answering top results, 2/19 partial, one irrelevant top result, and three no-index matches. The one false positive was `Where can I buy vegan boots in Manchester today?` pointing to GOV.UK voter registration. A static index without local-stock data cannot safely answer live retail stock, current weather, or real-time opening-hours questions just because one word happens to match.

## What changes / what does not

- Adds a separate *experimental read-only* query gate that marks these explicit live-data intents `LIVE_DATA_REQUIRED_NOT_VERIFIED_IN_STATIC_INDEX` and returns no unverified matching pages. This is a transparent coverage limitation, not a claim that no web result exists.
- Preserves the R2-P17 baseline first-result rankings for non-real-time questions. This gate is not deployed into the production or shadow API.
- SHA-bound original report, research SQLite database and 19 human ratings must all match the previously accepted owner evidence. Attempts to alter source data or grade binding fail closed.
- Compares 19 accepted questions under the proposed gate, then evaluates 12 new, previously unseen research queries using the same index. **Every novel result is labelled HUMAN_REVIEW_REQUIRED; no automatic relevance grades are asserted.**
- Produces JSON and HTML reports. The source input databases are read-only; no internet, web page crawls, API requests, external search-provider calls, or existing DB writes.

## Evidence and limitations

The expected earlier/experimental 19-question metrics are: direct top-1 `13 -> 13`, partial `2 -> 2`, irrelevant `1 -> 0`, no indexed match `3 -> 4`. This is a regression **on the previously human-judged pilot only**, not a general search engine evaluation. The 12 additional queries are deliberately ungraded and need human review. As future rights-cleared live-source feeds are added, sources should advertise explicit coverage capabilities and freshness. The provisional query patterns here must not permanently block legitimate live-supported results.

`PULSE_SEARCH_RUN_OWNER_AUDIT=1 bash Pulse_Search_R2P19_OnePass_20261024.sh` performs the bound research audit after tests; without that flag, it runs only local fixtures. The one-pass launcher finds the previously accepted owner report/index at `Pulse_Search_R2P17_Run_OBlIZF/owner_research`, or the read-only directory selected through `PULSE_SEARCH_R2P17_OWNER_DIR`.

## Rights

Only internal source-attributed metadata research is covered. Neither human grading nor a successful abstention regression grants public/subscription display, redistribution or commercial reproduction rights.
