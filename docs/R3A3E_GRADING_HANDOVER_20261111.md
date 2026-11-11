# R3-A3E hardening and grading handover — 11 November 2026

Candidate work over the accepted October engine. **Not merged, not activated, production HOLD.**

## 1. Blinded pack: validated, not regenerated

The transfer ZIP arrived locally and was extracted to a private folder outside Git
(`_private_grading_r3a3e/`, containing the workbook, both CSV exports, the README and a
BGE run log). Nothing from that folder is committed. The sealed engine mapping was not
in the ZIP and was never present.

All three published SHA-256 fingerprints match the received bytes exactly:

| File | SHA-256 | Match |
| --- | --- | --- |
| `PulseSearch_R3A3D_Blind_Independent_Grading_54_20261111.xlsx` | `5d4ebb46…f58537a7` | yes |
| `EXPORTED-Candidate Review.csv` | `154c01f5…4b76da5dd` | yes |
| `EXPORTED-No Results.csv` | `1bd65d16…ede5e43e` | yes |

Validator result: **`PASS_REPLAY_AND_REVIEW_INPUT_INTEGRITY`** against the immutable
R3-A3D replay (`bf0bee88…`, 116,577 bytes):

* 54 frozen queries, 108 engine-query combinations
* **423** ranked candidates, all matched row-for-row to replay rank/title/URL in masked
  A/B order, with 54 unique probe IDs
* **32** explicit no-result receipts matched to the exact replay combinations
* 423 ungraded candidate rows; 0 structurally complete grade rows
* 44/44 comparable nonempty BGE top-1 URLs

Workbook structure was checked independently of the exports. It has six sheets
(`START HERE`, `Case Navigator`, `Priority 25`, `Candidate Review`, `No Results`,
`PROVENANCE`); the review sheets carry **3 banner rows + 1 header + 423** and
**3 banner + 1 header + 32** respectively. The first attempt failed here — a raw
`<row>` count read 427 and looked like a mismatch — so the check now anchors on the
`Probe ID` header and cross-checks the workbook's probe-ID histogram against the CSV
export. Grade cells are deliberately **not** interpreted: no machine value may be
mistaken for a human signature.

Receipt: `docs/evidence/r3a3e_grading_transfer_validation.json`.

**Human signed grades remain 0.** No relevance, source or abstention judgement has been
made by a reviewer, and none can be made by this repository.

## 2. Code-review gates from PR #8

| Gate | Resolution |
| --- | --- |
| 1. Index hash enforcement | `read_rows()` verifies the accepted index SHA-256 **before and after** the read, fails closed on absence/mismatch/mutation, and records the receipt. Row count (120) is now a secondary check, never the gate. Dense mode also pins the model manifest (`3955a9a2…`) and weights (`3c9f3166…`, 133,466,304 bytes). |
| 2. Coordinated exclusions | One negation clause is split into separate entities, so `excluding Diwali and Pride` is two constraints and `other than A, B and C` is three. Each entity is tested on its own; multi-word entities stay whole; trailing scope (`in 2026`) is not part of the entity. |
| 3. Deeper retrieval / refill | The wrapper escalates depth (10 → 50 → 120) whenever constraints leave fewer than the requested `limit`, so a request for 10 results is refilled from deeper ranks instead of returning a short list. `refilled` and `search_passes` are recorded. |
| 4. Silent year failures | Per-year sub-queries record `RETRIEVED` / `EMPTY` / `FAILED` in `year_coverage` with diagnostics. Any failure sets `retrieval_status = PARTIAL_SUBQUERY_FAILED`, and a failure is sticky across depths, so incomplete edition coverage can never be reported as complete. |
| 5. Metric separation | Every result carries `metrics_scope`: exclusion semantics, no global suppression, no persisted state, retrieval metric and `relevance_metric = ENGINEER_AUTHORED_URL_EXPECTATION_NOT_HUMAN_GRADE`, human grades 0. |

## 3. Owner clarification: query-local negation only

The `exclude_*` behaviour is a **per-request result filter**, never global event
suppression. The layer mutates no index content, source admission, crawler setting,
event qualification, blocklist or category visibility, and keeps no state between calls.

Verified on a fixture containing Diwali, Pride Berlin, CSD Berlin and Stadtfest Berlin:

* `Diwali events`, `Pride Berlin events`, `CSD Berlin`, `Stadtfest Berlin` each retrieve
  their indexed edition
* a generic `Berlin events` search returns all three Berlin editions
* only `Berlin events excluding CSD Berlin` omits CSD, and only for that request
* the next search without a negative clause retrieves CSD again
* two coordinated exclusions are applied separately and do not bleed across queries

Terminology in new material is **query-specific exclusion / negation compliance**. The
frozen tests and historical evidence are preserved unchanged.

## 4. Re-measured with pins enforced

Both 54-case runs now refuse to start unless the index (and, for dense, the model) hash
matches. Results are unchanged from the pre-hardening measurement:

| Engine | before | after | recoveries | regressions | partial retrieval |
| --- | --- | --- | --- | --- | --- |
| Hybrid lexical | 19/54 | **29/54** | 10 | 0 | 0 |
| BGE dense (pinned) | 27/54 | **33/54** | 6 | 0 | 0 |

Evidence: `docs/evidence/r3a3e_constraint_layer_54.json`,
`…_54_bge.json`. These remain engineer-authored URL expectations, not quality scores.

Candidate rankings are written to a **separate comparison set**
(`r3a3e_candidate_ranking_comparison_{hybrid,bge}.json`), explicitly labelled
`NOT_HISTORICAL_BASELINE` with `baseline_source = docs/evidence/r3a3d_frozen54_replay.json`.
The historical grading baseline is not replaced, overwritten or re-scored.

## 5. Tests

`tests/test_r3a3e_constraints.py` 12/12 (original defect reproductions and repairs) and
`tests/test_r3a3e_hardening.py` **26/26**, covering: pin mismatch/absence/read receipt,
dense guard, query-local negation, coordinated entities, contradiction withholding,
missing title year, refill depth and limit, and sticky partial retrieval.

Archived POSIX matrix remains **25/25 modules, 419 tests** (unchanged by this round).

## 6. Gates

```
REPLAY_REPRODUCED=PASS
BLIND_PACK_VALID=PASS (3/3 published hashes; 423/32 rows; workbook shape cross-checked)
SIGNED_HUMAN_GRADING=0
INDEX_MODEL_PINS=ENFORCED
ORIGINAL_REGRESSION=PASS 25/25 modules, 419 tests
CONSTRAINT_HARDENING=PR8_GATES_ADDRESSED (38 new unit tests)
PRODUCTION=HOLD
```

Next acceptance remains a genuine independent blind review by a human, graded against
the validated pack, followed by an owner adoption decision. No merge, no activation, no
public crawling, no index or model change.
