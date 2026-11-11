#!/usr/bin/env python3
"""Read-only R3-A3E replay and blind-review integrity validator.

Stdlib only. Never uses the sealed engine map, model weights or the owner DB.
Does not turn provisional/machine grades into human sign-off.
Use --candidates /path/to/EXPORTED-'Candidate Review'.csv for workbook-row check.
Use --empty /path/to/EXPORTED-'No Results'.csv for abstention-row check.
"""
import argparse
import collections
import csv
import json
import sys
from pathlib import Path

INDEX_PIN = "bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d"
MODEL_PIN = "3955a9a2ca390314555ddb6a11b2ed16210657b689cab1b8e708653d3c63c437"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def csv_rows(path):
    if not path:
        return []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def pairs(p, engine):
    return [(str(i), hit["title"], hit["url"])
            for i, hit in enumerate(p[engine]["top"], start=1)]


def verify(replay, frozen, candidates=None, empties=None):
    require(replay.get("status") == "READ_ONLY_TRUE_BGE_REPLAY_COMPLETED_NOT_DEPLOYED",
            "not the genuine R3-A3D replay")
    require(replay.get("question_total") == 54, "not 54 queries")
    require(replay.get("corpus") == {"pages": 120, "fts": 120, "approved_sources": 7},
            "accepted corpus shape does not match")
    require(replay.get("owner_index_sha256_before_after") == INDEX_PIN, "wrong index pin")
    require(replay.get("model_manifest_sha256") == MODEL_PIN, "wrong BGE model pin")
    require(replay.get("owner_index_writes") == 0, "reported owner index writes")
    require(replay.get("network_requests") == 0, "reported network use during replay")
    require(replay.get("human_labels_independent") is False, "unexpected human-label claim")
    require(replay.get("signed_human_grades") == 0, "this fixture must be ungraded")

    ids = [r["probe_id"] for r in frozen]
    require(len(ids) == 54 and len(set(ids)) == 54, "frozen fixture not unique/54")
    by_id = {r["probe_id"]: r for r in frozen}
    probes = replay.get("probes")
    require(isinstance(probes, list) and len(probes) == 54, "replay probe count !=54")
    require({p["id"] for p in probes} == set(ids), "replay/frozen IDs mismatch")

    lengths = collections.Counter()
    both = {}
    zero = []
    expected_candidates = {}
    expected_empties = {}
    for p in probes:
        q = by_id[p["id"]]
        require(p["query"] == q["question"], "frozen query changed: " + p["id"])
        require(p["expected_kind"] == q["kind"], "frozen kind changed: " + p["id"])
        required = []
        missing = 0
        for e in ("baseline", "bge_dense"):
            top = p[e]["top"]
            require(isinstance(top, list) and len(top) <= 10, "bad top10: " + p["id"])
            require(p[e]["count"] == len(top), "candidate count mismatch: " + p["id"])
            require(len({x["url"] for x in top}) == len(top),
                    "duplicate canonical URL in top list: " + p["id"])
            lengths[e] += len(top)
            if top:
                required.append(tuple(pairs(p, e)))
            else:
                missing += 1
        both[p["id"]] = required
        expected_candidates[p["id"]] = sum(len(x) for x in required)
        expected_empties[p["id"]] = missing
        zero.extend([p["id"]] * missing)

    require(lengths["baseline"] == 72 and lengths["bge_dense"] == 351,
            "historical replay candidate counts differ")
    require(sum(lengths.values()) == 423, "expected 423 ranked candidates")
    require(len(zero) == 32, "expected 32 explicit no-result combinations")

    comparable = 0
    top1_match = 0
    for p in probes:
        top = p["bge_dense"]["top"]
        if top:
            comparable += 1
            if top[0]["url"] == by_id[p["id"]]["historic_bge_top_url"]:
                top1_match += 1
    require(comparable == 44 and top1_match == 44,
            "top-URL historical comparison unexpectedly changed")

    diwali = next(p for p in probes if p["id"] == "exclude_diwali")
    bge_leaks = [(n, x["url"]) for n, x in enumerate(diwali["bge_dense"]["top"], 1)
                 if "diwali" in x["url"].casefold()]
    require(bge_leaks and bge_leaks[0][0] == 8, "Diwali rank-8 regression evidence missing")
    # A clear failure gate; this validator doesn't silently treat the leak as acceptable.
    failed_constraints = {"exclude_diwali": "BGE_FORBIDDEN_URL_RANK8"}
    byprobe = {p["id"]: p for p in probes}
    for name in ("catalog_history", "x14", "event_series_2", "event_series_3", "x09"):
        require(name in byprobe, "missing edition probe: " + name)
    paths = set()
    for name in ("catalog_history", "x14"):
        for x in byprobe[name]["bge_dense"]["top"]:
            paths.add(x["url"])
    require(any("london-open-house-2023" in x for x in paths) and
            any("london-open-house-2024" in x for x in paths),
            "expected indexed historical editions not seen")

    verified_review_rows = 0
    unsigned_review_rows = 0
    if candidates is not None:
        require(len(candidates) == 423, "candidate-review CSV must have 423 rows")
        pool = collections.defaultdict(lambda: collections.defaultdict(list))
        for r in candidates:
            key = r["Probe ID"].strip()
            require(key in by_id, "candidate review has unknown query")
            require(r["Question"] == by_id[key]["question"], "question mismatch")
            label = r["Engine"].strip()
            require(label in ("A", "B"), "engine labels must remain masked A/B")
            actual = (str(int(r["Rank"])), r["Title returned"], r["Source URL"])
            require(1 <= int(r["Rank"]) <= 10, "invalid rank")
            pool[key][label].append(actual)
            grade = r.get("Score 0–3", "").strip()
            reviewer = r.get("Reviewer ID", "").strip()
            date = r.get("Review date UTC", "").strip()
            if grade or reviewer or date:
                require(grade in ("0", "1", "2", "3") and reviewer and date,
                        "partial/unsigned grade entry: " + key)
                verified_review_rows += 1  # Structural only; human identity NOT verified.
            else:
                unsigned_review_rows += 1
        for key in ids:
            observed = [tuple(sorted(pool[key][label], key=lambda x: int(x[0])))
                        for label in ("A", "B") if pool[key][label]]
            require(collections.Counter(observed) == collections.Counter(both[key]),
                    "rank/title/URL candidate mismatch for " + key)
        # Never call structurally present signatures 'independently signed'.
    if empties is not None:
        require(len(empties) == 32, "no-result review CSV must have 32 rows")
        actual_zero = collections.Counter()
        for r in empties:
            key = r["Probe ID"].strip()
            require(key in by_id, "unknown no-result probe")
            require(r["Original question"] == by_id[key]["question"], "no-result question mismatch")
            require(r["Engine"].strip() in ("A", "B"), "unblinded no-result engine label")
            require(r["Recorded status"].strip() == "NO RESULTS", "invalid zero receipt")
            actual_zero[key] += 1
        require(actual_zero == collections.Counter(zero), "no-result receipts don't match replay")
    return {
        "status": "PASS_REPLAY_AND_REVIEW_INPUT_INTEGRITY" if candidates is not None and empties is not None
                  else "PASS_REPLAY_INTEGRITY_REVIEW_EXPORT_NOT_SUPPLIED",
        "frozen_queries": 54,
        "engine_query_combinations": 108,
        "ranked_candidates": 423,
        "explicit_empty_combinations": 32,
        "comparable_bge_top1_url_agreement": "44/44",
        "bge_no_result_combinations": 54 - comparable,
        "confirmed_exclusion_defects": failed_constraints,
        "candidate_review_csv_rows_checked": None if candidates is None else len(candidates),
        "no_results_csv_rows_checked": None if empties is None else len(empties),
        "grade_rows_structurally_complete_NOT_HUMAN_VERIFIED": verified_review_rows,
        "ungraded_candidate_rows": unsigned_review_rows if candidates is not None else None,
        "human_independent_signoff": "HOLD_UNVERIFIED",
        "quality_scores": "HOLD_UNTIL_GENUINE_INDEPENDENT_GRADING",
        "production": "HOLD"
    }


def main():
    pa = argparse.ArgumentParser()
    pa.add_argument("--replay", default="docs/evidence/r3a3d_frozen54_replay.json")
    pa.add_argument("--frozen", default="data/frozen_54.csv")
    pa.add_argument("--candidates", help="CSV exported from workbook Candidate Review worksheet")
    pa.add_argument("--empty", help="CSV exported from workbook No Results worksheet")
    args = pa.parse_args()
    with open(args.replay, encoding="utf-8") as f:
        replay = json.load(f)
    answer = verify(replay, csv_rows(args.frozen),
                    csv_rows(args.candidates) if args.candidates else None,
                    csv_rows(args.empty) if args.empty else None)
    print(json.dumps(answer, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError, OSError) as ex:
        print("HOLD_BLIND_REVIEW_INPUT=" + str(ex), file=sys.stderr)
        sys.exit(2)
