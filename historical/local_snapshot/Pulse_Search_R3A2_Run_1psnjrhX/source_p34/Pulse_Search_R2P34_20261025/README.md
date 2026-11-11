# Pulse Search R2-P34 — owner-index heldout retrieval generalisation

This is a standalone Pulse Search **read-only research experiment**, not an API/crawler/index update.

R2-P33's owner WSL comparison proved R2-P31 baseline 23/56 wrong retrieval, R2-P32 candidate 6/56, and R2-P33 candidate 0/56 on 71 older probes. R2-P33 still missed **4 of 14** checkable queries in an untouched 18-probe holdout, and verified zero factual answers.

R2-P34 adds only general syntax/paraphrase repairs for the 4 misses: *booking*, sentence-final *work*, *editions* as historical-series intent, and *apart from* as exclusion. It narrows series results to the named series in the query (e.g. London Open House is distinct from City Hall Open House) and does not map queries to exact URLs. Full source is shipped.

**Frozen local checks (118 index metadata rows reconstructed from owner-approved records):**
- Original 71: 56/56 checkable retrieval behaviours, 15 factual ungraded.
- Previously sealed 18: 14/14 checkable retrieval behaviours, 4 factual ungraded.
- **New untouched 20 authored after candidate freeze**: **9/16** checkable retrieval behaviours, **7 remaining errors**, **4 factual ungraded**. Those errors are reported, not tuned away.
- 14 new unittest methods, plus unchanged 15+12+10+20+285 regressions: **356/356 passed locally**.
- A full disposable 120-row SQLite rehearsal also passed; because it is synthetic and bypasses the exact owner-file SHA check only in the unshipped rehearsal harness, it does not establish owner acceptance. One of the missing proxy pages (City Hall Open House 2026) resolves one fresh probe, so the synthetic database recorded **6** fresh retrieval misses rather than 7. The actual owner-index result is pending.

## Owner validation

Save `Pulse_Search_R2P34_Holdout_Generalisation_20261025.zip` to your established `ChatGPTCode` folder. SHA-check outer ZIP before extracting, then run `Pulse_Search_R2P34_20261025/OnePass.sh`. It checks all nested SHA pinned releases and the original 120-page owner database digest. Exact owner index SHA256 `bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d`.

The launcher reproduces the prior R2-P33 owner 89-probe three-way audit with exact expected baseline distributions, then evaluates R2-P34 on all 109 probes (71 + 18 + 20), retaining original 36 positive/negative first-result guards. Outputs generated only under a fresh disposable `Pulse_Search_R2P34_Run_*/shadow` folder; makes **no network calls, no paid provider calls, no source writes, and no publication claims**. Original SQLite opened `mode=ro` + `PRAGMA query_only=ON`; original SHA reverified at end.

`FINAL_EXIT_CODE=0` means tests and diagnostic ran and earlier accepted behaviours were not regressed. It **does not mean 100% factual answer accuracy** and does **not** authorise deployment. New fresh-holdout errors remain diagnostic findings.

Limits: metadata-only rights, index only 120 approved pages and seven origins, no live-weather/commerce facts, source body term presence doesn't prove answer claims, earlier query sets were known during development. Human judgements on the fresh answers are needed before product integration.
