# R3-A3E — defect findings and repairs

**11 November 2026 | Standalone Pulse Search | Research/lab scope | Production HOLD**

Accepted engine snapshots, the owner index and the BGE stage are unchanged. All
repair lives in new code (`tools/r3a3e_constraint_layer.py`) plus its tests
(`tests/test_r3a3e_constraints.py`). Index SHA-256 was re-checked after every run:
`bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d`.

## 1. `exclude_diwali` — confirmed leak, reproduced at BGE rank 8

Reproduced on the accepted index from the immutable replay: BGE returned 10
candidates and placed `Diwali on the Square 2025` at **rank 8**; the hybrid
baseline returned it at **rank 1** as its only result. The earlier five-link
export hid the leak because the forbidden page sat below the export cut.

**Root cause (code, not speculation).** `hybrid_core.EXCLUDE` is:

```
\b(?:excluding|except(?:\s+for)?|without|apart\s+from|but\s+not|not\s+including)\b
```

`other than` is absent, so `Find London events in 2025 other than Diwali on the
Square` parses with `excluded=[]`. The query then degrades to `subject`, where the
only page clearing the 0.45 title-match ratio is the Diwali page itself — hence a
one-result answer that is precisely the forbidden document.

**Repair.** The layer extends the negative-constraint surface to `other than`,
`instead of`, `excluding`, `except (for)`, `without`, `apart from`, `but not`,
`not including` and `save for`, strips the clause before retrieval, and re-applies
the exclusion to **every returned rank**, not the top five. A contradictory
exclusion (`Eid on the Square 2027 excluding Eid`) is still withheld exactly as
the original engine intends — it is not laundered into a positive answer.

**Result.** Hybrid: 10 candidates, zero Diwali URLs, `PASS_RETRIEVAL`. BGE dense:
`PASS_RETRIEVAL`. Zero regressions across the other 53 cases.

## 2. London Open House edition recall — corpus has them, ranking lost them

The corpus is not missing editions. The accepted index contains
`london-open-house-2023`, `-2024` and `-2025`, and `x14` / `catalog_history`
already retrieve all of them.

**Root cause.** `parse()` stores a single scalar year — the *last* one matched —
and `_accept` hard-filters on it:

```
year = (YEAR.findall(q) or [None])[-1]
if intent.year and r['year'] != intent.year: return False
```

`What are the 2024 and 2025 London Open House editions?` therefore keeps 2025 and
discards 2024 before ranking. `event_series_3` (2023/2024/2025) keeps only 2025.
`x09` behaves the same way. Separately, series queries admit `City Hall Open
House 2026`, a different series, which is why `x14` and `catalog_history` failed
`series_many` even with four results.

**Repair.** The layer strips years from the retrieval query, runs the original
ranker, queries each requested year separately, and enforces a year-set filter
plus a contiguous subject-phrase requirement (`london open house`) for series
queries.

**Result.** `event_series_2` → 2024 + 2025. `event_series_3` → 2023 + 2024 + 2025.
`x09` → 2024 + 2025. `x14` / `catalog_history` → the three genuine editions, with
`City Hall Open House 2026` correctly excluded. All `PASS_RETRIEVAL`; no
regressions.

## 3. Lab API relevance — two fixture defects, not engine defects

Protocol checks were already 11/11. The two relevance failures had concrete
causes in the lab harness:

1. The fixture defines ten pages but the crawl ran with `max_pages=8`, so
   `/register-to-vote` never entered the FTS table. The voting query therefore
   returned the GP page as its best lexical match.
2. `/gp-registration` body text never contained the word "doctor", so the
   `doctor` query had nothing to match and returned zero results.

**Repair (new harness/fixture code only; engine untouched).** Index the whole
fixture (`max_pages=12`) and give the synthetic GP page honest clinical
vocabulary. Re-run: **11/11 protocol, 5/5 relevance**, `doctor` → `/gp-registration`
rank 1, `register to vote` → `/register-to-vote` rank 1, and the three previously
passing assertions still rank 1.

This is an 8-page synthetic loopback corpus. It proves the query path; it says
nothing about global relevance.

## 4. Four provenance modules — the bytes were never missing

Previously reported as unrecoverable (P21, R2-P32, R2-P33, R2-P34). They were
failing because `core.autocrlf=true` rewrote the byte-pinned fixtures to CRLF on
this Windows checkout:

| Fixture | Working copy (CRLF) | Authentic bytes | Pinned digest |
| --- | --- | --- | --- |
| `owner_review_r2p20.json` | `cc1d791f…` | `e046bef6…` | `e046bef6…` |
| `owner_R2P31_report.json` | `4ab1724b…` | `3d86e678…` | `3d86e678…` |
| `owner_R2P32_report.json` | `822214e4…` | `2414d557…` | `2414d557…` |

Stripping CR from each working copy reproduced the pinned digest exactly, and the
committed Git blobs hash to the pinned values. The authentic evidence was present
in the repository the whole time. Restoring the blob bytes — with no edit to any
test, expectation or digest — and pinning those paths with
`historical/local_snapshot/**/owner_R2P3*_report.json -text` /
`owner_review_r2p20.json -text` makes the provenance chain verify.

**Result: 25/25 archived modules pass, 419 tests.** Previously 21/25 with the four
reported as fixture-missing.

## 5. Top-1 agreement — corrected denominator

`44/54` was a denominator artifact. Ten of the 54 questions produce no BGE result,
so they have no top URL to compare. **All 44/44 comparable nonempty BGE top-1 URLs
match the October ledger**; verdict agreement stays 54/54 per engine. Recorded in
`docs/evidence/r3a3e_top1_agreement_correction.json`; the historical replay JSON
is not retro-edited, and the harness now reports the comparable figure directly.

## What the layer does not fix

Four hybrid cases remain `FAIL_WRONG_TOP1` (`new_patient_doctor`,
`learner_motorist`, `x01`, `x04`) because the lexical path returns nothing for
them; BGE recovers all four. They are reported, not papered over.

## Verification performed

| Check | Result |
| --- | --- |
| Constraint unit tests (fail-before-fix + repaired) | 12/12 pass |
| Hybrid 54-case before/after | 19 → 29 `PASS_RETRIEVAL`, 0 regressions |
| BGE dense 54-case before/after | 27 → 33 `PASS_RETRIEVAL`, 0 regressions |
| Exclusion compliance at every returned rank | pass on both engines |
| Lab API | 11/11 protocol, 5/5 relevance |
| Archived POSIX modules | 25/25, 419 tests |
| Owner index SHA-256 after all runs | unchanged |
| Engine snapshot files modified | none |
