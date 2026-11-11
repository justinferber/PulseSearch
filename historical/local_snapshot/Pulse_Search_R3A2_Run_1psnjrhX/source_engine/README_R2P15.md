# Pulse Search R2-P15 — Offline Multi-Question Candidate Re-evaluation

**Standalone general-purpose search-engine milestone.** This is an additive read-only tool built on the accepted R2-P14B crawler/database schema, with no paid search providers and no connections to other Pulse UNITY systems.

## Evidence already established on the owner's WSL host

- R2-P14B verified 174 tests locally.
- The live City Hall experiment crawled six sitemap documents, examined 8,156 immediate sitemap entries, staged 112 scoped URL leads, independently discovered the exact official London NYE 2026 page, fetched/indexed the one approved target and returned it through the own index.
- No paid search API was used. The underlying data is **internal metadata-only research**, not general commercial reuse approval.

## What R2-P15 tests

R2-P14B recorded a query-specific discovery score. R2-P15 leaves all those records unchanged and **re-scores the stored URL catalog at query time** for six independent questions. That prevents the New Year's Eve scoring from being treated as permanent search ranking.

R2-P15 never crawls or indexes a page. A sitemap candidate URL does not prove that a page exists now, satisfies the query, is allowed to be indexed, or carries commercial reuse rights. All matches are marked `UNVERIFIED_URL_CANDIDATE`. Even an empty result means only 'no candidate in this bounded staged set'.

## How to run

Extract the outer `Pulse_Search_R2P15_Complete_20261023.zip` into the usual Windows `ChatGPTCode` folder so the engine ZIP and one-pass script are both there.

```bash
D="$(wslpath -u 'C:\Users\justi\Desktop\pulseunity\ChatGPTCode')"
bash "$D/Pulse_Search_R2P15_OnePass_20261023.sh"
echo "TEST_EXIT_CODE=$?"
```

If the local tests pass, run the **read-only owner research audit** against the previous completed live R2-P14B folder:

```bash
PULSE_SEARCH_RUN_OWNER_AUDIT=1 bash "$D/Pulse_Search_R2P15_OnePass_20261023.sh"
echo "AUDIT_EXIT_CODE=$?"
```

If the database lives in a different folder, set `PULSE_SEARCH_R2P14B_RUN_DIR` to its actual path before running. It defaults to `$D/Pulse_Search_R2P14B_Run_qR4X82` from the accepted live result.

The owner audit produces `candidate_report.json` and `candidate_review.html` in a fresh private R2-P15 run folder. There is no network access in this module; no original database mutation. The tool checks that all staged candidate URLs remain within the source's approved scope.

## Interpretation

Positive: a candidate URL can be found and prioritised for different questions without a paid search call.

Not proven: content relevance, freshness, a working public answer, unseen page discovery across other websites, general internet breadth, subscriber rights, or live update scheduling. The next milestone should preserve a broader query-neutral candidate inventory and select a small reviewed sample for independent page verification.
