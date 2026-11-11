# R3-A3 independent grading review

Source workbook: `Pulse_Search_R3A3_Owner_Review_20261026.xlsx` (19,133 bytes, 26 Oct 2026 14:24:33).
This review re-derives the numbers from the workbook XML and the R3-A2 report; it does **not** add human grades.

## 1. Workbook structure

| Sheet | Rows | Content |
| --- | --- | --- |
| `START HERE` | 19 | Headline: 54 frozen tests, baseline/BGE 19/27, 8 reported recoveries, human approval NOT YET, recommended decision "retain HOLD" |
| `Priority 25` | 29 | 8 recoveries + 8 anomalies + 11 fact cases (with overlaps), each with "evidence still needed" |
| `All 54` | 58 | Full ledger: baseline verdict, BGE verdict, provisional 0–3 grade, assessment, top result, URL; human grade and source-verified columns empty |
| `Method and gates` | 17 | Stage/status table and the independence policy |

## 2. Derived grade distribution

| Provisional grade | Count | Meaning as used in the workbook |
| --- | --- | --- |
| 3 | 32 | Top result title directly matches the query (`PROVISIONAL_TOP1_RELEVANT`, `PROVISIONAL_SAFETY_PASS`, `PROVISIONAL_EXCLUSION_PASS`, `PROVISIONAL_YEAR_MATCH`) |
| 2 | 8 | Partial: `EXCLUSION_PASS_WITH_NOISE`, `SERIES_BOUNDARY_REVIEW`, `CONFLICT_WITH_ENGINE_VERDICT` |
| 1 | 3 | Incomplete: `INCOMPLETE_EDITION_COVERAGE` |
| blank | 11 | `FACT_EVIDENCE_REQUIRED` — a grade would be fabricated |

Verification: `probe_total = 54`, and the ledger row count equals the workbook's `All 54` sheet. Baseline and BGE `PASS_RETRIEVAL` recomputed from the R3-A2 report are 19 and 27, matching the workbook headline.

## 3. Where the grades and the engine disagree

The workbook flags these itself; I confirm each from the underlying report:

1. **`exclude_diwali` (grade 2, `CONFLICT_WITH_ENGINE_VERDICT`).** All five exported BGE links omit Diwali, yet the engine verdict is `FAIL_EXCLUSION_LEAK`. Either the exclusion filter leaked on an unexported candidate, or the verdict is wrong. **Unresolvable from the export** — it needs the full candidate set and the filter trace. This is the single most misleading row in the ledger.
2. **Open House edition/series rows (`event_series_2`, `event_series_3`, `x09`: grade 1; `catalog_history`, `x14`: grade 2).** The engine reports missing editions while the top result is the 2025 edition. It cannot be determined from metadata whether 2024 is absent from the corpus, filtered out, or dropped by the 5-link truncation.
3. **`exclude_games`, `x12` (grade 2, "noise").** Exclusion is respected in exported links, but some returned items may not be festivals at all. That is a relevance-classification question, not an exclusion failure, and the grade reflects it.
4. **Fact rows (blank).** `x21` is `FAIL_FACT_STATUS` while the rest abstain. Both are correct behaviour for unverifiable facts; the difference is a status-label consistency question worth one test, not a quality signal.
5. **Truncation.** `r3a2_eval.py` exports only `links[:5]` while `limit=10`, and the review HTML shows one link. Every "all candidates" judgement in R3-A3 therefore rests on a five-item view.

## 4. What this grading does and does not establish

**Establishes:** a defensible, reproducible ordering of the 54 probes by apparent answer quality at title level; a clean negative-query record (10/10 safety passes for both engines); and an honest, deliberately blank fact column.

**Does not establish:** relevance (no independent human labels), correctness (no page bodies, no capture dates), completeness (truncated candidates), ranking quality (no precision@1/recall@5 computed), or any factual claim (0 verified).

## 5. Reproducibility

`tools/verify_evidence.py` re-derives the counts from the workbook and the report, so a reviewer can confirm this table without trusting it:

```bash
python tools/verify_evidence.py --root /path/to/ChatGPTCode
```

Exit code 0 means the numbers in this document still describe the files on disk.
