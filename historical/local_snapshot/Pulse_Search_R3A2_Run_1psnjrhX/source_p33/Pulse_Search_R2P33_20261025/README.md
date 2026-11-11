# Pulse Search R2-P33 — Real owner 120-page three-way retrieval comparison

**Research only. No crawler, API or index integration. No network calls, no paid search APIs and no writes to the accepted database.**

## Critical correction to R2-P32 owner log

The 23 reported retrieval errors came from **R2-P31**, because R2-P32's owner audit invoked `evaluate(..., p31)` without the optional `candidate` argument. The R2-P32 candidate had only been evaluated offline. This version independently computes three columns, R2-P31 (baseline), R2-P32 candidate and R2-P33 candidate, against the **same pinned owner database** and verifies all original R2-P32 baseline URLs against the uploaded owner report.

R2-P33 adds limited, explainable generic paraphrases to the earlier candidate. The 71 frozen R2-P32 probes were used during development; we explicitly flag that as in-sample. **18 newly written probes were left untouched**; four failed during local metadata testing and are intentionally preserved as possible errors. Rankings do not contain query-to-URL lookups and no web evidence is invented.

## Validation

- Exact ZIP/member SHA-256 pins for original P32/P31/P29/P21 acceptance chain and uploaded R2-P32/R2-P31 owner reports.
- Original owner research database must be SHA256 `bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d`, SQLite quick_check OK, 120 indexed pages, 120 FTS records, 7 sources; read-only open.
- 15 new R2-P33 tests plus 12 previous P32, 10 P31, 20 P29 and 285 original crawler tests.
- R2-P31 original 36 query outputs faithfully reproduced. The sole planned changed first result is the old London Open House series query, for which an exact London Open House page is preferred over City Hall Open House.
- All 71 previous owner baseline queries reproduced against the original report, evaluated using three rankers.
- 18 additional untouched holdouts are reported with any misses. Factual claims are **never** scored as verified answers merely because a title or body keyword appears.
- Automatically saves JSON and HTML with each probe outcome. Never exports publisher body text (all relevant sites are `metadata_only` where applicable).

## How to run

Save the ZIP to `C:\Users\justi\Desktop\pulseunity\ChatGPTCode`; use the SHA-pinned one-pass command provided alongside the download. The owner runner requires only previously accepted R2-P27C owner database already in that folder, not a fresh crawl.

**Research acceptance means the comparison ran successfully, not that factual search accuracy is near 100% or deployment is approved.**
