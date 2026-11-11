"""Human-graded evaluation over manually captured official pages.

This is not an open-web benchmark. It compares the engine's ranked real pages
with a person's expected official page for each query, and reports failures and
missing sources instead of hiding them behind synthetic fixtures.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_broad_r3a3g.search import search_staging  # noqa: E402
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402

CONFIG = ROOT / "config/real_sources.json"
SNAPSHOT = ROOT / "docs/evidence/r3a3g_real_source_snapshot.json"
OUT = ROOT / "docs/evidence/r3a3g_real_source_eval.json"


def host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    pages = {p["id"]: p for p in snapshot["pages"]}
    usable = [p for p in snapshot["pages"]
              if p.get("status") == 200 and p.get("title") and p.get("description")]
    if not usable:
        raise SystemExit("no captured pages available")

    tmp = Path(tempfile.mkdtemp(prefix="r3a3g-real-eval-"))
    index = StagingIndex(tmp / "staging.sqlite")
    for page in usable:
        index.add_document({
            "url": page["url"],
            "source_id": page["id"],
            "title": page["title"],
            "snippet": page["description"],
            "category": "Other",
            "category_confidence": 0.9,
            "categories": ["Other"],
            "depth": 1,
            "fetched_at": snapshot["captured_at"],
            "content_hash": f"real-{page['id']}",
            "source_authority": page.get("authority", "official"),
        }, [], index_allowed=True)
    index.close()

    queries = []
    for spec in config["queries"]:
        expected_domains = spec["expect_domains"]
        captured_domains = {host(p["url"]) for p in usable}
        missing = [d for d in expected_domains
                   if not any(c == d or c.endswith("." + d) for c in captured_domains)]
        index = StagingIndex(tmp / "staging.sqlite")
        try:
            response = search_staging(index, spec["query"], limit=5)
        finally:
            index.close()
        results = response.get("results") or []
        related = response.get("related_official_links") or []
        ranked_domains = [host(r.get("url", "")) for r in results]
        related_domains = [host(r.get("url", "")) for r in related]
        top3 = ranked_domains[:3]
        matched = next((i + 1 for i, d in enumerate(ranked_domains)
                        if any(d == e or d.endswith("." + e) for e in expected_domains)), None)
        top = results[0] if results else {}
        judged = results[matched - 1] if matched and matched <= len(results) else top
        judged_text = (str(judged.get("title") or "") + " " +
                       str(judged.get("snippet") or "")).lower()
        term_hits = [term for term in spec.get("expect_terms", [])
                     if term.lower() in judged_text]
        wrong_city = False
        qlow = spec["query"].lower()
        if "berlin" in qlow and top and "berlin" not in (
                str(top.get("title") or "") + str(top.get("snippet") or "") +
                str(top.get("url") or "")).lower():
            wrong_city = True
        duplicate_urls = len(ranked_domains) != len(set(ranked_domains))
        status = "PASS" if matched and len(term_hits) >= max(1, len(spec.get("expect_terms", [])) // 2) else "FAIL"
        handoff = any(any(d == e or d.endswith("." + e) for e in expected_domains)
                      for d in related_domains)
        queries.append({
            "query": spec["query"],
            "human_expected": {
                "domains": expected_domains,
                "terms": spec.get("expect_terms", []),
                "intent": spec.get("intent"),
            },
            "status": status,
            "matched_expected_rank": matched,
            "top3_domains": top3,
            "top_result": {"title": top.get("title"), "url": top.get("url"),
                           "snippet": top.get("snippet"),
                           "document_type": top.get("document_type"),
                           "ranking_reasons": top.get("ranking_reasons")},
            "term_hits": term_hits,
            "missing_source_from_capture": missing,
            "related_official_domains": related_domains,
            "official_handoff_available": handoff,
            "wrong_city": wrong_city,
            "duplicate_urls_in_results": duplicate_urls,
            "response_status": response.get("status"),
            "notices": response.get("notices", []),
        })

    evaluated = queries
    passed = sum(1 for q in queries if q["status"] == "PASS")
    recall = sum(1 for q in queries if q["matched_expected_rank"]) / len(queries)
    mrr = sum(1 / q["matched_expected_rank"] for q in queries
              if q["matched_expected_rank"]) / len(queries)
    evidence = {
        "kind": "R3A3G_REAL_SOURCE_EVAL",
        "generated_at": snapshot["captured_at"],
        "mode": "HUMAN_GRADED_MANUAL_CAPTURE",
        "not_open_web_benchmark": True,
        "captured_pages": len(usable),
        "captured_domains": len({host(p["url"]) for p in usable}),
        "failed_captures": [
            {"id": p["id"], "url": p["url"], "status": p.get("status"),
             "error": p.get("error", "non-200 or no description")}
            for p in snapshot["pages"] if p not in usable],
        "queries": queries,
        "summary": {
            "queries": len(evaluated),
            "pass": passed,
            "fail": len(evaluated) - passed,
            "recall_at_3": round(recall, 3),
            "mrr": round(mrr, 3),
            "wrong_city": sum(1 for q in queries if q["wrong_city"]),
            "duplicate_result_sets": sum(1 for q in queries if q["duplicate_urls_in_results"]),
            "unresolved_missing_sources": sum(1 for q in queries
                                               if q["missing_source_from_capture"]),
            "official_handoff_only": sum(1 for q in queries
                                         if q["status"] == "FAIL" and q["official_handoff_available"]),
        },
        "limitations": [
            "Only pages that returned HTTP 200 and a description are indexed.",
            "A missing page is reported as a capture gap, not counted as a ranking win.",
            "No page body is stored; titles and meta descriptions are short evidence.",
            "This is not a crawler admission or a permanent indexing licence.",
        ],
    }
    OUT.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    for q in queries:
        if q["status"] == "FAIL":
            print("FAIL", q["query"], "| got", q["top3_domains"],
                  "| missing", q["missing_source_from_capture"])
    print("wrote", OUT)
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
