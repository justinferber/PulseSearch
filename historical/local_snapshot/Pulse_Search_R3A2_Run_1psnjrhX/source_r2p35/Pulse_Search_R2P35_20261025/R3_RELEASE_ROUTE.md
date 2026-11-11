# Pulse Search — Stronger Architectural Route (R2-P35 → R3)

**Owner directive 25 Oct 2026:** stop releasing incremental special-case rewrites for individual questions. Replace with a tested general retrieval-and-evidence architecture capable of handling unseen questions while respecting user trust, publisher rights and crawl safety. This concerns standalone Pulse Search, **not** Pulse UNITY Events.

## Architecture, not another synonym patch

```
Independent approved crawler → indexed SQLite records and FTS5
                                    ↓
User query → Intent and hard constraints (year, place, negation, fresh facts)
                                    ↓
Lexical BM25 candidate generation + semantic similarity (offline context / local dense)
                                    ↓
Hybrid reranker (source/edition/intent constraints; abstention first)
                                    ↓
Evidence extractor + source timestamp and publication rights gate
                                    ↓
Human-calibrated decision: source links / answer with citation / explicitly abstain
                                    ↓
Scoped authenticated API canary → rollback
```

**What R2-P35 delivers immediately:** a separate, read-only prototype that indexes approved page title, URL and internally accessible body; computes a BM25-like score, subword cosine and corpus-local distributional context vectors; extracts year/location, broad collection and exclusion intent; records *non-textual* evidence signatures; refuses unsupported live data; offers an owner-approved offline sentence-encoder plugin without fetching weights; and runs independent frozen probes without changing the live ranker.

**What R2-P35 does NOT deliver:** a pretrained contextual embedding model, semantic answer generation, verified factual claims, independent calibration, licensing of third-party body snippets, production-speed large-scale FTS5 retrieval, source diversity, or deployed changes. Its contextual co-occurrence mechanism sees only the tiny existing local corpus and cannot learn absent world knowledge. FTS5 is validated as an accepted corpus/source index; it is not yet used as a scalable first-stage candidate engine in this prototype.

## One coherent programme, with three major acceptance gates

### Gate A — Real semantic coverage, beyond 120 webpages

- Benchmark on **unseen**, independently written queries, graded for relevant top-1 and top-5, including spelling/phrasing, multi-intent queries, yearly editions, contradicting geographies, site-specific searches, and unseen topics. Report both precision AND recall and no-answer cases; stratify by covered/uncovered domain.
- Verify local-only sentence embedding model licensing, operator-approved model files and SHA-256 manifest, no remote code, network fetch or paid API. Benchmark separate off-by-default semantic scores vs lexical-only and distributional-only before blending; secure scaling with a trusted on-prem inference endpoint if appropriate.
- Expand coverage only from approved publisher sources, robots/scope compliant, with deduplication and provenance. The 7 origins and 120-page static corpus cannot answer unrestricted internet questions.
- Keep BM25/FTS5 as first-stage candidate retrieval when corpus grows (batch and query latency acceptance); blend with multilingual contextual semantic vectors only after model is pinned, tested and permitted.

### Gate B — Evidence and factual answer trust

- Detect whether a question asks for a **source**, explanation, live fact, past event edition, current fee, availability, cancellation or eligibility. Factual answer mode must be separate from link retrieval mode.
- Build structured, auditable claims from *licensable* first-party or source-authorised fields and permissible attribution. Verify the correct page, exact edition, event location, source timestamps, subject, relevant paragraph/sentence, negation and contradictions. No quote/reproduction beyond rights.
- Classify missing, stale, conflicting, unsupported and time-sensitive evidence separately. **Never** infer today's opening hours, ticket availability, weather, a price or cancellation merely from title/body token presence.
- Run independent human fact checking: answer must match source; citation must lead to the supporting passage, not merely the webpage. Unknown is a successful safe outcome when information is absent.

### Gate C — Calibration, canary and release governance

- Only after enough **independent** relevance and fact labels, calibrate confidence separately for retrieval and factual answers, with explicit coverage vs correctness curves. Present uncertainty bins based on measured reliability, not arbitrary algorithm scores.
- Never use the evaluation set to create query-specific URL shortcuts or continual threshold tweaks. Create sealed, externally authored holdouts and an immutable run ledger. Publish the denominator and known source coverage.
- Founder-authorised promotion to shadow search API, then guarded small canary after security, rights, freshness, latency, robots, restart/recovery and rollback checks. Fail closed and preserve the existing ranker until acceptance; no unattended production writes.

## Practical outcome

The architecture aims for **correct evidence-supported answers on answerable indexed questions**, not a synthetic '100%' that rewards returning only one known URL. Its key scorecard fields are: independent precision@1, recall@5, answer-supported rate, unsupported factual assertion count, correct abstention, source freshness, domain coverage, latency and rights exceptions.
