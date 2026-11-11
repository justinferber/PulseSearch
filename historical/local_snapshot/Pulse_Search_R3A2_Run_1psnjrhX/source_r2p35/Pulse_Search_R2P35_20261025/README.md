# Pulse Search R2-P35 — Hybrid Search Architecture Foundation

**Research-only / no deployment.** This is the first structural replacement candidate for the fixed rewrite chains used in R2-P29–P34. It reads the accepted independent Pulse Search SQLite research clone **read-only** and compares expected **retrieval**, not factual answer accuracy. The accepted crawler, API, source scope, original research index and robots policy stay unchanged.

## Components

1. **Lexical retrieval:** deterministic BM25-inspired scoring over URL/title/approved indexed body, with title emphasis and corpus-local IDF, not just broad FTS5 OR. FTS5 corpus is verified for provenance; moving to efficient true FTS5 candidate generation for large indexes is a later gate. This R2-P35 shadow evaluates 120 approved pages.
2. **Similarity:** corpus-local distributional word-context similarity PLUS character n-gram cosine handles some related phrases, inflections and spelling variants. **This is a genuine statistical distributional signal, but not pretrained contextual-language semantic comprehension.** A real local-only sentence-embedding adapter is supplied separately (`offline_encoder.py`) but **disabled by default** until an owner-approved, SHA-pinned and rights-reviewed local model is available. It will never auto-fetch or install model weights. Any future actual model quality must be evaluated for multilingual/geo/time queries and source-domain changes.
3. **Intent:** extract date/year, location contradictions, event collection intent, subject, series, disallowed explicit exclusions, dynamic vs historic requests. Strict year applies to title editions; that is not confirmation of real event date.
4. **Evidence extraction:** internal-only text-pattern and hash signals for time, date, currency, cancellation, accessibility and availability. Evidence extraction is not an evidence **verification** or natural-language answer generator. No copyrighted publisher body snippet is written to the review outputs. All sources remain `metadata_only`.
5. **Calibrated abstention gate:** architecture has a judgement-based calibrator interface and explicit uncertainty labels. With zero fresh independent 50+ labelled examples, **the confidence labels are heuristics and no calibrated factual probabilities are claimed**. Live price/availability/open-now/weather is withheld. Fact questions return source link only or abstain; they never assert prices, times, or cancellation.
6. **Evaluation:** SHA-bound accepted 120-page owner research index; 109 frozen earlier probes + 20 newly sealed questions, total 376 test methods (20+14+15+12+10+20+285), report split by cohort, no new crawling, API or database writes. No automatic production promotion even if every check passes.

## Recommended release route (NOT separate weekly rewrites)

- **R2-P35 — Foundation** (this package): integrated lexical, similarity and intent/risk pipeline; read-only side-by-side acceptance; independent first-report benchmark.
- **R3-A — Genuine semantic & diversity gate:** owner-approved model and licence manifest, local inference without paid provider or network, encoder latency/memory benchmarking, multilingual/typo/date, unseen publisher and topic stratification. Check independent, human-judged recall@5 and precision@1 against lexical and current candidate. Prevent extra source-scope rights violations.
- **R3-B — Evidence & facts:** structured claim type, source document edition and timestamp, minimal permissible attribution/citations, contradictory source resolution, stale claim warnings, checkable answer-vs-abstain labels, false factual claim target explicitly quantified; no generated unsupported prose.
- **R3-C — Calibration, shadow API and guarded canary:** holdouts supplied by independent reviewer, threshold calibration based on sufficient labeled judgments, alert on coverage vs answerability, regression across diverse publishers, schema and auth/security testing, founder-controlled promotion/rollback, robots/rights acceptance. **HOLD** until each separate gate passes.

## Owner WSL command

Save `Pulse_Search_R2P35_Hybrid_Architecture_20261025.zip` to `C:\Users\justi\Desktop\pulseunity\ChatGPTCode`, verify package SHA from the assistant message, extract to that folder, and execute:

`bash "$D/Pulse_Search_R2P35_20261025/OnePass.sh"`

Outputs: unique `Pulse_Search_R2P35_Run_*/shadow/r2p35_hybrid_report.json` and HTML. `FINAL_EXIT_CODE=0` means only successful **research diagnostic**, never verified fact accuracy or live integration.

## Safety limitations

- No license permitting republishing page bodies established; no publisher content exported.
- A substring or pattern in a page is not verified factual evidence.
- Large-system production scaling cannot be inferred from 120 pages and 7 origins.
- This package does not install semantic model dependencies, access any paid API, or contact publishers.
- Semantic model requirements, trust/security audits, independent human judgements and deployment rights are outstanding gates.

Detailed route, clear completion gates, and boundaries: [R3_RELEASE_ROUTE.md](R3_RELEASE_ROUTE.md).
