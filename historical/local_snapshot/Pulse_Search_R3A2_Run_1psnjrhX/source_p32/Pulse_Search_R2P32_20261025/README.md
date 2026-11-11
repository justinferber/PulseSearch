# Pulse Search R2-P32 — Evidence + adversarial ranking comparison

**Research only.** Owner R2-P31 was provisional PASS on the 120-page independent search index. The human-graded results remain limited; title/URL matching alone is not a factual answer. This release introduces 55 adversarial development probes, 16 **post-development** holdout probes, and an indexed-body **signal-only** audit. The probes are not webpage content licences or assertions of answers.

The frozen 55-probe development matrix has 44 objectively checkable retrieval behaviours and 11 fact questions which **cannot be verified from a matching title**. R2-P31 baseline initially missed 16 of the 44 on the 118-record metadata proxy; an experimental R2-P32 intent-reformulation and exclusion-aware wrapper corrected the 44 on that proxy. A separately evaluated 16-question holdout includes 12 checkable probes and 4 factual questions; SIX retrieval misses were found there and **deliberately not patched** in R2-P32. Actual owner DB may differ, and only the owner's run can establish real counts.

### Owner acceptance

1. Keep `Pulse_Search_R2P32_Evidence_Adversarial_20261025.zip` under `C:\Users\justi\Desktop\pulseunity\ChatGPTCode`.
2. Verify ZIP hash per handover, extract into ChatGPTCode, run `bash "$D/Pulse_Search_R2P32_20261025/OnePass.sh"`.
3. Send the terminal summary or upload `r2p32_adversarial_report.json` plus `r2p32_adversarial_review.html` from the printed output directory.

The runner SHA-verifies itself, original R2-P31 source, owner JSON, and owner SQLite; verifies 12 new unit-test methods + 10 existing R2-P31 + 20 R2-P29 + 285 accepted engine regressions, then opens accepted 120-page owner SQLite via URI `mode=ro`, SQLite `query_only=ON`; source remains completely unchanged. It verifies all 36 prior R2-P31 result lists against the unchanged accepted ranker, then compares old and candidate against 71 stress questions. No publisher text is exported—source display_mode `metadata_only` remains respected. Only signal counts, titles, URLs, SHA, and fetched metadata leave the internal read-only scan. No website/network requests or paid search APIs. No production integration.

**Interpretation:** An exit code 0 means only that this read-only DIAGNOSTIC completed without source-integrity violations. It does not certify perfect retrieval or factual accuracy. The report includes failures; 6/16 local metadata-proxy heldout mistakes are known already and remain for a later correction cycle. All original engine/API/crawler code and indexes remain protected.
