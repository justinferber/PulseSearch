#!/usr/bin/env python3
"""R3-A3D genuine frozen 54x2 replay: accepted owner index vs pinned local BGE.

Read-only. Runs the *original* R3-A2 modules (`hybrid_core`, `semantic_ranker`,
`r3a_local_model`, `r3a_eval.check_output`) over the *original* engineer-authored
case sets (30 R3-A1 + 24 R3-A2 frozen), against the accepted 120-page owner index
and the pinned WSL BGE stage.

Substitution, stated plainly: the original wrapper `r3a2_eval.py` refuses to run
without `Pulse_Search_R3A1_Run_*/shadow/r3a1_quality_report.json` (an absent
generated artefact). This harness drops only that wrapper guard; every ranker,
question, expectation, hash pin and read-only SQLite gate is the original one.

No publisher body is exported. No network, no downloads, no index writes.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import os
import sqlite3
import statistics
import sys
import time
from contextlib import closing
from pathlib import Path

INDEX_SHA = "bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d"
MODEL_MANIFEST_SHA = "3955a9a2ca390314555ddb6a11b2ed16210657b689cab1b8e708653d3c63c437"
WEIGHTS_SHA = "3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad"
WEIGHTS_BYTES = 133466304
PARTITIONS = ("r3a1_original_30", "new_24_frozen")


def sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def bootstrap(snapshot):
    """Put the original R3-A2 / R3-A1 / R2-P35 modules on sys.path (no PYTHONPATH)."""
    snapshot = Path(snapshot)
    r3a2 = snapshot / "Pulse_Search_R3A2R2_20261026"
    loader = r3a2 / "accepted_loader"
    r35 = snapshot / "Pulse_Search_R3A2_Run_1psnjrhX" / "source_r2p35" / "Pulse_Search_R2P35_20261025"
    for path in (loader, r3a2, r35):
        if not path.is_dir():
            raise SystemExit("HOLD_MISSING_SOURCE_DIR=" + str(path))
        sys.path.insert(0, str(path))
    return r3a2


def load_rows(index):
    """Same read-only load and corpus gates as the original r3a2_eval.py."""
    with closing(sqlite3.connect(Path(index).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA query_only").fetchone()[0] != 1:
            raise ValueError("HOLD_READONLY_NOT_ENABLED")
        counts = (
            db.execute("select count(*) from pages where indexed=1").fetchone()[0],
            db.execute("select count(*) from page_fts").fetchone()[0],
            db.execute(
                "select count(distinct p.source_id) from pages p join sources s using(source_id)"
                " where p.indexed=1 and s.approved=1 and s.enabled=1"
            ).fetchone()[0],
        )
        if counts != (120, 120, 7):
            raise ValueError("HOLD_UNAPPROVED_INDEX_STATE=" + repr(counts))
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("HOLD_DATABASE_QUICK_CHECK")
        rows = [
            dict(r)
            for r in db.execute(
                """select p.url,p.title,p.body,p.fetched_at,p.source_id,s.display_mode
                   from pages p join sources s using(source_id)
                   where p.indexed=1 and s.approved=1 and s.enabled=1 order by p.url"""
            )
        ]
    if len(rows) != 120:
        raise ValueError("HOLD_APPROVED_COUNT_DRIFT")
    return rows, counts


def historic_index(frozen):
    """Frozen 26 October verdicts, used only to measure replay agreement."""
    out = {}
    with open(frozen, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            out[row["probe_id"]] = row
    return out


def timed(fn, *args, **kwargs):
    start = time.perf_counter()
    value = fn(*args, **kwargs)
    return value, (time.perf_counter() - start) * 1000.0


def percentiles(values):
    if not values:
        return {}
    ordered = sorted(values)
    def pick(q):
        return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]
    return {
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(pick(0.95), 3),
        "max_ms": round(ordered[-1], 3),
    }


def main(args):
    os.environ.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        HF_HUB_DISABLE_XET="1",
        PIP_NO_INDEX="1",
        TOKENIZERS_PARALLELISM="false",
    )
    index = Path(args.index).resolve()
    model_dir = Path(args.model_dir).resolve()
    out = Path(args.out)
    if out.exists():
        raise SystemExit("HOLD_OUTPUT_ALREADY_EXISTS=" + str(out))

    if sha(index) != INDEX_SHA:
        raise SystemExit("HOLD_OWNER_INDEX_SHA_MISMATCH")
    if not (model_dir / "model.safetensors").is_file():
        raise SystemExit("HOLD_MODEL_WEIGHT_ABSENT")
    weight = model_dir / "model.safetensors"
    if weight.stat().st_size != WEIGHTS_BYTES or sha(weight) != WEIGHTS_SHA:
        raise SystemExit("HOLD_MODEL_WEIGHT_SHA_OR_SIZE_MISMATCH")
    if sha(model_dir / "PULSE_APPROVED_MODEL.sha256") != MODEL_MANIFEST_SHA:
        raise SystemExit("HOLD_MODEL_MANIFEST_SHA_MISMATCH")

    bootstrap(args.snapshot)
    from hybrid_core import HybridIndex
    from semantic_ranker import DenseConstrainedIndex
    from r3a_local_model import PinnedSentenceEncoder
    from r3a_eval import check_output
    from r3a_cases import CASES as ORIGINAL
    from r3a2_extra_cases import CASES as EXTRA

    rows, counts = load_rows(index)
    baseline = HybridIndex(rows)
    encoder = PinnedSentenceEncoder(model_dir)
    dense, build_ms = timed(DenseConstrainedIndex, rows, encoder)

    probes = []
    baseline_ms, dense_ms = [], []
    for partition, seq in (("r3a1_original_30", ORIGINAL), ("new_24_frozen", EXTRA)):
        for cid, question, kind, expect in seq:
            old, old_ms = timed(baseline.search, question, limit=10)
            new, new_ms = timed(dense.search, question, limit=10)
            baseline_ms.append(old_ms)
            dense_ms.append(new_ms)

            def verdict_of(result, returned):
                verdict, note = check_output(kind, expect, returned)
                if kind == "fact_unverified" and result["status"] not in (
                    "SOURCE_LINK_ONLY_FACT_UNVERIFIED",
                    "WITHHELD_NO_GROUNDED_INDEX_RESULT",
                    "WITHHELD_REQUIRES_LIVE_SOURCE",
                ):
                    verdict = "FAIL_FACT_STATUS"
                return verdict, note

            old_verdict, _ = verdict_of(old, old["results"])
            new_verdict, _ = verdict_of(new, new["results"])
            probes.append(
                {
                    "partition": partition,
                    "id": cid,
                    "query": question,
                    "expected_kind": kind,
                    "expected_value": expect,
                    "baseline": {
                        "verdict": old_verdict,
                        "status": old["status"],
                        "count": len(old["results"]),
                        "top": [{"title": r["title"], "url": r["url"]} for r in old["results"][:10]],
                    },
                    "bge_dense": {
                        "verdict": new_verdict,
                        "status": new["status"],
                        "count": len(new["results"]),
                        "top": [{"title": r["title"], "url": r["url"]} for r in new["results"][:10]],
                    },
                    "publisher_body_exported": False,
                    "factual_answer_verified": False,
                }
            )
            if sha(index) != INDEX_SHA:
                raise SystemExit("HOLD_OWNER_INDEX_MUTATED_DURING_REPLAY")

    by_partition = {}
    for name in PARTITIONS:
        subset = [p for p in probes if p["partition"] == name]
        by_partition[name] = {
            rank: dict(collections.Counter(p[rank]["verdict"] for p in subset))
            for rank in ("baseline", "bge_dense")
        }
    valid = [p for p in probes if p["expected_kind"] != "fact_unverified"]
    deltas = {
        "newly_recovered": [
            p["id"] for p in valid
            if p["baseline"]["verdict"].startswith("FAIL")
            and not p["bge_dense"]["verdict"].startswith("FAIL")
        ],
        "new_regressions": [
            p["id"] for p in valid
            if not p["baseline"]["verdict"].startswith("FAIL")
            and p["bge_dense"]["verdict"].startswith("FAIL")
        ],
    }

    frozen = historic_index(args.frozen)
    baseline_match = sum(
        1 for p in probes
        if frozen.get(p["id"], {}).get("baseline_oct26_verdict") == p["baseline"]["verdict"]
    )
    bge_match = sum(
        1 for p in probes
        if frozen.get(p["id"], {}).get("bge_oct26_verdict") == p["bge_dense"]["verdict"]
    )
    bge_top1_match = sum(
        1 for p in probes
        if frozen.get(p["id"], {}).get("historic_bge_top_url")
        and p["bge_dense"]["top"]
        and frozen[p["id"]]["historic_bge_top_url"] == p["bge_dense"]["top"][0]["url"]
    )
    baseline_pass = sum(1 for p in probes if p["baseline"]["verdict"] == "PASS_RETRIEVAL")
    bge_pass = sum(1 for p in probes if p["bge_dense"]["verdict"] == "PASS_RETRIEVAL")
    provenance_path = model_dir / "PULSE_MODEL_PROVENANCE.json"
    provenance = (
        json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.is_file() else {}
    )
    report = {
        "status": "READ_ONLY_TRUE_BGE_REPLAY_COMPLETED_NOT_DEPLOYED",
        "harness": "tools/frozen54_replay.py",
        "harness_note": (
            "Original rankers, case sets and check_output; only the absent R3-A1 shadow-report "
            "wrapper guard of r3a2_eval.py is dropped."
        ),
        "model_kind": "REAL_LOCAL_PINNED_BGE_SENTENCE_EMBEDDINGS",
        "model_manifest_sha256": encoder.manifest_sha256,
        "model_verified_files": encoder.verified_file_count,
        "model_provenance": provenance,
        "owner_index_sha256_before_after": INDEX_SHA,
        "corpus": {"pages": counts[0], "fts": counts[1], "approved_sources": counts[2]},
        "question_total": len(probes),
        "distribution": by_partition,
        "deltas": deltas,
        "replay_agreement": {
            "baseline_verdict_matches": f"{baseline_match}/{len(probes)}",
            "bge_verdict_matches": f"{bge_match}/{len(probes)}",
            # Legacy 54-denominator key kept so older reports stay readable; the
            # correct measure is comparable-nonempty, since a query with no BGE
            # result has no top URL to agree or disagree with.
            "bge_top1_url_matches": f"{bge_top1_match}/{len(probes)}",
            "bge_top1_url_matches_comparable":
                f"{bge_top1_match}/{sum(1 for p in probes if p['bge_dense']['top'])}",
            "bge_no_result_combinations": sum(1 for p in probes if not p["bge_dense"]["top"]),
            "baseline_pass_retrieval": f"{baseline_pass}/{len(probes)}",
            "bge_pass_retrieval": f"{bge_pass}/{len(probes)}",
        },
        "latency": {
            "baseline": percentiles(baseline_ms),
            "bge_dense": percentiles(dense_ms),
            "dense_index_build_ms": round(build_ms, 3),
        },
        "human_labels_independent": False,
        "signed_human_grades": 0,
        "factual_answers_verified": 0,
        "no_publisher_body_export": True,
        "network_requests": 0,
        "owner_index_writes": 0,
        "production_integration": "HOLD_INDEPENDENT_GRADING",
        "limitations": [
            "Dense cosine scores are not calibrated probabilities",
            "Expectations are engineer-authored, not independent human labels",
            "120 approved pages from 7 sources do not establish global retrieval quality",
            "Retrieval cannot waive geography, edition, exclusion or source-rights rules",
            "No factual answer, price, availability or cancellation has been verified",
        ],
        "probes": probes,
    }

    out.mkdir(parents=True)
    (out / "r3a3d_frozen54_replay.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (out / "r3a3d_blind_reviewer_workbook.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "probe_id", "question", "baseline_top1_url", "bge_top1_url",
                "human_relevance_0_to_3", "answer_supported_yes_no_unknown",
                "independent_reviewer", "comments",
            ]
        )
        for p in probes:
            writer.writerow(
                [
                    p["id"], p["query"],
                    p["baseline"]["top"][0]["url"] if p["baseline"]["top"] else "",
                    p["bge_dense"]["top"][0]["url"] if p["bge_dense"]["top"] else "",
                    "", "", "", "",
                ]
            )
    if sha(index) != INDEX_SHA:
        raise SystemExit("HOLD_OWNER_INDEX_MUTATED_AFTER_REPLAY")
    summary = {
        "status": report["status"],
        "corpus": report["corpus"],
        "distribution": by_partition,
        "deltas": deltas,
        "replay_agreement": report["replay_agreement"],
        "latency": report["latency"],
        "model_verified_files": encoder.verified_file_count,
        "owner_index_writes": 0,
    }
    print(json.dumps(summary, indent=2))
    print("REPORT=" + str(out / "r3a3d_frozen54_replay.json"))
    print("WORKBOOK=" + str(out / "r3a3d_blind_reviewer_workbook.csv"))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", required=True)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--frozen", required=True)
    parser.add_argument("--snapshot", required=True, help="historical/local_snapshot directory")
    parser.add_argument("--out", required=True)
    parsed = parser.parse_args()
    try:
        sys.exit(main(parsed))
    except SystemExit:
        raise
    except Exception as exc:  # explicit, labelled hold rather than a traceback-only failure
        print("HOLD_REPLAY:" + type(exc).__name__ + ":" + str(exc), file=sys.stderr)
        sys.exit(2)
