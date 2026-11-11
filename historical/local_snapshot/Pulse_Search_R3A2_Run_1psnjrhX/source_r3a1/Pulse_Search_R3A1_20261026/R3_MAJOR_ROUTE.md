# Pulse Search R3 — Major release gates

**Standalone Pulse Search**, not Pulse UNITY Events. Research/owner-review only. 

## A1: Trustworthy relevance measurement (this package)

- Fix falsely optimistic success checks: exclusion with zero alternatives is a retrieval miss; an exclusion match anywhere in results fails; each explicitly requested event edition/year must be retrieved. Keep a separate classification for no-result and unsupported factual claims.
- Evaluate a frozen, engineer-authored 30-case adversarial challenge. Clearly identify limitations: this is NOT independent human annotation or proof of global search quality. Provide a review CSV with URLs but **no publisher body prose**, respecting `metadata_only`.
- Offline genuine embedding model branch: only if owner has explicitly staged a licence-reviewed local model, SHA manifest for ALL files and needed dependencies. No automatic downloads or model-code execution (`trust_remote_code=False`). No model present means the semantic model is NOT tested, never substitute a spelling similarity surrogate under the same label.
- Compare real optional local semantic model against same baseline and fresh independent blinded labels, with precision@1, recall@5, null accuracy and latency. Ablation against lexical and lexical+lightweight similarity is required before blending. Do not publish probabilistic "confidence" without empirical calibration.

## A2: Semantic test & corpus expansion (future acceptance gate)

- Source candidate: `sentence-transformers/all-MiniLM-L6-v2` (listed as Apache-2.0 on its model card) or `BAAI/bge-small-en-v1.5` only after source/license/security/usage review. Neither is included or downloaded in this package. Pin full revision AND every file SHA and document owner licence approval. Apply offline environment and no remote code.
- Independently write 50+ new questions after weights/architecture are locked and keep the questions/ratings sealed. Include multiple domains, multilingual if supported, intended out-of-corpus queries, hard year/geo/negation constraints, and exact named editions. Use genuine human graded top-1 and top-5 relevance. Do not tune on the holdout.
- Expand beyond 7 origins/120 pages only using approved robots, licenses and source scopes; no unreviewed source-content display rights. Use FTS5 candidate generation for scale; do not linearly scan the entire web corpus or re-embed every page per query.

## B: Evidence-backed factual answer mode (separate release gate)

- Use source-approved structured data or source-licensed passage extraction; verify exact subject, edition, claim, negation, time, freshness, right to display and citation. Never make factual assertions from a body signal counter or a URL/title match.
- Distinguish source recommendation from an answer; unsupported fee/ticket availability/weather/cancellation and accessibility must abstain. Fact accuracy denominator is independently reviewed, not all queries.
- Record source URL/hash/fetched date and passage pointer **privately**. Publisher prose not replicated by default for `metadata_only` sources.

## C: Calibrated control and deployment (separate release gate)

- After 50+ blind independent labels per meaningful category, measure precision@1, recall@5, unsupported assertion count, answer correctness with citations, coverage/abstention, latency, and group-specific failure modes; do not invent a statistical calibration score from raw similarity.
- Preserve existing crawler, paid API=0, robots and publisher rights, bearer-auth API, and original research snapshot. No production deployment without explicit founder approval, independent adversarial/security check, and canary/rollback.

**Current outcome:** A1 quality instrumentation only. Real contextual embedding engine, independent factual answers, calibration, production rollout all remain HOLD.
