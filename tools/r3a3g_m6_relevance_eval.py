"""M6 graded relevance evaluation: judge destinations, not domains.

The query labels live in ``config/m6_relevance.json`` and are deliberately
separate from the search implementation. A URL not listed is unjudged and gets
no credit; this makes unknown results visible instead of awarding them a domain
match. Metrics are nDCG@5, precision@3 and helpful top-1.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_broad_r3a3g.search import search_staging  # noqa: E402
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402

SNAPSHOT = ROOT / "docs/evidence/r3a3g_real_source_snapshot.json"
CONFIG = ROOT / "config/m6_relevance.json"
OUT = ROOT / "docs/evidence/r3a3g_m6_relevance_eval.json"


def key(url: str) -> str:
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = (parts.path or "/").rstrip("/") or "/"
    return host + path


def dcg(grades: list[int]) -> float:
    return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(grades))


def evaluate(config: dict, pages: list[dict]) -> dict:
    reviewer = str(config.get("reviewer") or "").strip()
    reviewed_at = str(config.get("reviewed_at") or "").strip()
    if not reviewer or not reviewed_at:
        raise ValueError("reviewer and reviewed_at are required")
    queries = config.get("queries") or []
    if len({q.get("id") for q in queries}) != len(queries):
        raise ValueError("query ids must be unique")
    usable = [p for p in pages if p.get("status") == 200 and p.get("title")]
    captured_at = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["captured_at"]
    tmp = Path(tempfile.mkdtemp(prefix="r3a3g-m6-relevance-"))
    index = StagingIndex(tmp / "staging.sqlite")
    for page in usable:
        index.add_document({
            "url": page["url"], "source_id": page["id"], "title": page["title"],
            "snippet": page.get("description") or "", "category": "Other",
            "category_confidence": 0.9, "categories": ["Other"], "depth": 1,
            "fetched_at": captured_at,
            "content_hash": "m6-" + page["id"],
            "source_authority": page.get("authority", "official"),
        }, [], index_allowed=True)
    index.close()
    cases = []
    for item in queries:
        labels = {key(url): int(grade) for url, grade in (item.get("grades") or {}).items()}
        if any(g not in (0, 1, 2, 3) for g in labels.values()):
            raise ValueError(f"invalid grade in {item.get('id')}")
        index = StagingIndex(tmp / "staging.sqlite")
        try:
            response = search_staging(index, item["query"], limit=5, enforce_support=True)
        finally:
            index.close()
        results = response.get("results") or []
        top = results[:5]
        grades = [labels.get(key(r.get("url", "")), 0) for r in top]
        judged = [labels[key(r.get("url", ""))] for r in top
                  if key(r.get("url", "")) in labels]
        ideal = sorted(labels.values(), reverse=True)[:5]
        ndcg = dcg(grades) / dcg(ideal) if dcg(ideal) else 0.0
        cases.append({
            "id": item["id"], "query": item["query"],
            "status": response.get("status"),
            "top": [{"title": r.get("title"), "url": r.get("url"),
                     "grade": labels.get(key(r.get("url", "")), 0)} for r in top],
            "precision_at_3": round(sum(g >= 2 for g in grades[:3]) / max(1, len(grades[:3])), 3),
            "helpful_top1": bool(grades and grades[0] >= 2),
            "ndcg_at_5": round(ndcg, 3),
            "judged_at_5": len(judged),
        })
    summary = {
        "queries": len(cases),
        "mean_ndcg_at_5": round(sum(c["ndcg_at_5"] for c in cases) / len(cases), 3),
        "mean_precision_at_3": round(sum(c["precision_at_3"] for c in cases) / len(cases), 3),
        "helpful_top1_rate": round(sum(c["helpful_top1"] for c in cases) / len(cases), 3),
        "judged_at_5": sum(c["judged_at_5"] for c in cases),
    }
    shutil.rmtree(tmp, ignore_errors=True)
    return {"kind": "R3A3G_M6_GRADED_RELEVANCE", "reviewer": reviewer,
            "reviewed_at": reviewed_at, "cases": cases, "summary": summary,
            "limitations": ["Internal first-pass grades; not an external reviewer.",
                            "Captured pages only; unjudged results score zero.",
                            "No live dates, prices or availability are asserted."]}


def main(config_path: Path = CONFIG, out_path: Path = OUT) -> int:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    pages = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["pages"]
    result = evaluate(config, pages)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    for case in result["cases"]:
        print(case["id"], case["status"], "ndcg", case["ndcg_at_5"],
              "top", (case["top"][0]["url"] if case["top"] else "none"))
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    raise SystemExit(main(args.config, args.output))
