# R3-A3E — independent grading acceptance protocol

**11 November 2026 | Standalone Pulse Search | No grades have been invented or signed**

## Status of the blinded pack

The owner's workbook (`PulseSearch_R3A3D_Blind_Independent_Grading_54_20261111.xlsx`)
and the sealed engine map (`PulseSearch_R3A3D_Engine_Mapping_Keep_Sealed_20261111.csv`)
were produced outside this machine and are **not present on this host**. They were
searched for by exact filename across the project, Downloads, Desktop and
Documents. This is a transfer gap, not evidence that they were never created.

**`BLIND_PACK_VALID=HOLD_WORKBOOK_NOT_PRESENT_LOCALLY`.** No row was regenerated,
and no grade was filled in.

## Replay-side integrity: PASS

`tools/verify_blind_grading_input.py` validates the committed replay without the
sealed map, the model weights or the owner database:

```
status: PASS_REPLAY_INTEGRITY_REVIEW_EXPORT_NOT_SUPPLIED
frozen_queries: 54
engine_query_combinations: 108
ranked_candidates: 423  (baseline 72 + BGE 351)
explicit_empty_combinations: 32
comparable_bge_top1_url_agreement: 44/44
bge_no_result_combinations: 10
human_independent_signoff: HOLD_UNVERIFIED
production: HOLD
```

Ranked rows and the 72/351 split match the workbook's stated composition. No
candidate exceeds rank 10, and no duplicate canonical URL appears within a
result list.

## Deterministic fingerprints for the workbook

Computed from the immutable replay with the engine mapping masked, so they can be
recomputed from any correct export regardless of which engine became "A" or "B":

| Artefact | Expected rows | Canonical SHA-256 |
| --- | --- | --- |
| Candidate Review | 423 | `798f7ac5b712e842d79e1128da751133b3fd718e40ac96fa9228543d4a9312dc` |
| No Results | 32 | `d1e1668a12034923c93f3cb5035b28f7f7021bb43c7b775ec2f4955422038f66` |

Fingerprint construction: per probe, the ordered `[rank, title, url]` list of each
pool, serialised as canonical JSON (`sort_keys`, no whitespace). A transformed
export — reordered candidates, an invented row, a truncated rank, or a dropped
empty receipt — will not reproduce these digests.

## How to validate the workbook once transferred

1. Export the `Candidate Review` worksheet to CSV and the `No Results` worksheet
   to CSV (UTF-8, header row intact).
2. Run:

```bash
python tools/verify_blind_grading_input.py \
  --replay docs/evidence/r3a3d_frozen54_replay.json \
  --frozen data/frozen_54.csv \
  --candidates "/path/to/EXPORTED-Candidate Review.csv" \
  --empty "/path/to/EXPORTED-No Results.csv"
```

The validator requires 423 and 32 rows respectively, masked `A`/`B` engine labels,
contiguous ranks 1–10, candidate sets identical to the replay per probe, and
`Recorded status = NO RESULTS` on every abstention row. A partially completed row
(score without reviewer, or reviewer without UTC date) is rejected rather than
counted.

## Scoring rules (unchanged from the assignment)

- Reviewers enter relevance **0–3** per returned candidate, plus constraint
  breach, edition correctness, captured primary-source evidence, reviewer ID and
  UTC timestamp.
- Negative queries receive a separate abstention judgement.
- Unverified factual-answer queries remain uncategorically unverified until a
  source is checked.
- The 25 priority cases are double-graded when a second reviewer exists;
  discrepancies are recorded, not averaged away.
- Owner first-pass grading must not be described as independent signoff.

## Denominator rules for consolidation

- **No recall figures.** A complete relevance set does not exist for this corpus.
- Report paired P@1, P@5, MRR@5 and noise@5 on the **signed subset only**, with
  the exact denominator stated.
- Report constraint/exclusion violation rate and edition coverage separately from
  relevance.
- Keep factual-answer abstention separate from search-result relevance.
- Any metric computed before every candidate row is signed must carry
  `SIGNED_SUBSET_ONLY`.

## Signoff audit

| Field | Value |
| --- | --- |
| Signed candidate judgements | **0** |
| Source-verified judgements | **0** |
| Reviewers identified | none |
| Sealed map exposure to reviewers | none (map not on this host) |
| Grades auto-filled or model-generated | none |
| Production decision | **HOLD** |

`tools/grade_independent.py` refuses unsigned rows and returns
`HOLD_PENDING_FULL_REPLAY_AND_INDEPENDENT_EVIDENCE` until real grades exist.
