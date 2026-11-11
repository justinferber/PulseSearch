"""Auto domain metrics plus signed human relevance grades.

The automatic part measures only whether a result from an expected domain is in
the top three. It does not claim that the page answers the question. The human
grade is a separate, dated review of top-1 usefulness and answer correctness.
"""

from __future__ import annotations

import json
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
LEGACY = ROOT / "docs/evidence/r3a3g_real_source_eval_legacy.json"
OUT = ROOT / "docs/evidence/r3a3g_real_source_eval.json"


def host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def domain_matches(domain: str, expected: list[str]) -> bool:
    return any(domain == e or domain.endswith("." + e) for e in expected)


def strict_metrics(ranks: list[int | None]) -> tuple[float, float]:
    recall = sum(1 for rank in ranks if rank and rank <= 3) / len(ranks)
    mrr = sum(1 / rank for rank in ranks if rank) / len(ranks)
    return round(recall, 3), round(mrr, 3)


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    usable = [p for p in snapshot["pages"]
              if p.get("status") == 200 and p.get("title")]
    if not usable:
        raise SystemExit("no captured pages available")
    legacy = {}
    if LEGACY.exists():
        old = json.loads(LEGACY.read_text(encoding="utf-8"))
        legacy = {q["query"]: q for q in old.get("queries", [])}

    tmp = Path(tempfile.mkdtemp(prefix="r3a3g-real-eval-"))
    index = StagingIndex(tmp / "staging.sqlite")
    for page in usable:
        index.add_document({
            "url": page["url"], "source_id": page["id"], "title": page["title"],
            "snippet": page.get("description") or "", "category": "Other",
            "category_confidence": 0.9, "categories": ["Other"], "depth": 1,
            "fetched_at": snapshot["captured_at"], "content_hash": f"real-{page['id']}",
            "source_authority": page.get("authority", "official"),
        }, [], index_allowed=True)
    index.close()

    queries = []
    for spec in config["queries"]:
        expected = spec["expect_domains"]
        captured_domains = {host(p["url"]) for p in usable}
        missing = [d for d in expected
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
        matched = next((i + 1 for i, d in enumerate(ranked_domains)
                        if domain_matches(d, expected)), None)
        top = results[0] if results else {}
        top_text = (str(top.get("title") or "") + " " + str(top.get("snippet") or "")).lower()
        wrong_city = False
        qlow = spec["query"].lower()
        if "berlin" in qlow and top and "berlin" not in (
                top_text + str(top.get("url") or "")).lower():
            wrong_city = True
        result_urls = [str(r.get("url") or "") for r in results]
        duplicate_urls = len(result_urls) != len(set(result_urls))
        handoff = any(domain_matches(d, expected) for d in related_domains)
        human = spec.get("human_grade") or {}
        label = str(human.get("label") or "UNREVIEWED")
        if label not in ("PASS", "PARTIAL", "FAIL", "UNREVIEWED"):
            raise SystemExit(f"invalid human grade for {spec['query']}: {label}")
        old = legacy.get(spec["query"], {})
        old_rank = old.get("matched_expected_rank")
        queries.append({
            "query": spec["query"],
            "intent": response.get("intent", {}).get("kind"),
            "expected": {"domains": expected, "terms": spec.get("expect_terms", [])},
            "automated": {
                "domain_match_rank": matched,
                "domain_match_at_3": bool(matched and matched <= 3),
                "top3_domains": ranked_domains[:3],
                "term_overlap": [t for t in spec.get("expect_terms", [])
                                 if t.lower() in top_text],
                "wrong_city": wrong_city,
                "duplicate_urls_in_results": duplicate_urls,
                "official_handoff_available": handoff,
                "response_status": response.get("status"),
            },
            "human": {
                "label": label,
                "top1_answers": human.get("top1_answers"),
                "answer_correct": human.get("answer_correct"),
                "reviewer": human.get("reviewer"),
                "reviewed_at": human.get("reviewed_at"),
                "notes": human.get("notes"),
            },
            "top_result": {"title": top.get("title"), "url": top.get("url"),
                           "snippet": top.get("snippet"),
                           "document_type": top.get("document_type"),
                           "ranking_reasons": top.get("ranking_reasons")},
            "missing_source_from_capture": missing,
            "related_official_domains": related_domains,
            "baseline": {
                "reported_status": old.get("status"),
                "domain_match_rank": old_rank,
                "domain_match_at_3": bool(old_rank and old_rank <= 3),
            },
        })

    auto_ranks = [q["automated"]["domain_match_rank"] for q in queries]
    auto_recall, auto_mrr = strict_metrics(auto_ranks)
    old_ranks = [q["baseline"]["domain_match_rank"] for q in queries]
    old_recall, old_mrr = strict_metrics(old_ranks)
    labels = {key: sum(1 for q in queries if q["human"]["label"] == key)
              for key in ("PASS", "PARTIAL", "FAIL", "UNREVIEWED")}
    old_reported = (json.loads(LEGACY.read_text(encoding="utf-8")).get("summary", {})
                    if LEGACY.exists() else {})
    evidence = {
        "kind": "R3A3G_REAL_SOURCE_EVAL",
        "generated_at": snapshot["captured_at"],
        "mode": "AUTO_DOMAIN_METRICS_PLUS_SIGNED_HUMAN_GRADES",
        "not_open_web_benchmark": True,
        "captured_pages": len(usable),
        "captured_domains": len({host(p["url"]) for p in usable}),
        "failed_captures": [
            {"id": p["id"], "url": p["url"], "status": p.get("status"),
             "error": p.get("error", "no usable title/description")}
            for p in snapshot["pages"] if p not in usable],
        "queries": queries,
        "summary": {
            "queries": len(queries),
            "auto_domain_matches": sum(1 for r in auto_ranks if r),
            "auto_domain_match_rate": round(sum(1 for r in auto_ranks if r) / len(queries), 3),
            "auto_recall_at_3": auto_recall,
            "auto_mrr": auto_mrr,
            "human_pass": labels["PASS"],
            "human_partial": labels["PARTIAL"],
            "human_fail": labels["FAIL"],
            "human_unreviewed": labels["UNREVIEWED"],
            "human_pass_rate": round(labels["PASS"] / len(queries), 3),
            "top1_helpful": sum(1 for q in queries if q["human"]["top1_answers"] is True),
            "answer_correct": sum(1 for q in queries if q["human"]["answer_correct"] is True),
            "wrong_city": sum(1 for q in queries if q["automated"]["wrong_city"]),
            "duplicate_result_sets": sum(1 for q in queries
                                         if q["automated"]["duplicate_urls_in_results"]),
            "unresolved_missing_sources": sum(1 for q in queries
                                               if q["missing_source_from_capture"]),
            "official_handoff_only": sum(1 for q in queries
                                         if q["automated"]["official_handoff_available"]
                                         and not q["automated"]["domain_match_rank"]),
        },
        "baseline_recomputed_from_legacy_ranks": {
            "source": "docs/evidence/r3a3g_real_source_eval_legacy.json",
            "reported_pass": old_reported.get("pass"),
            "reported_fail": old_reported.get("fail"),
            "reported_recall_at_3": old_reported.get("recall_at_3"),
            "reported_mrr": old_reported.get("mrr"),
            "recomputed_recall_at_3": old_recall,
            "recomputed_mrr": old_mrr,
            "note": "The legacy PASS label used domain+term overlap; this recomputation only checks whether a matching domain rank was <=3.",
        },
        "limitations": [
            "Only captured pages with a title are indexed; descriptions are short metadata.",
            "Automatic domain matching is not factual correctness.",
            "Human grades are one dated reviewer pass, not inter-annotator agreement.",
            "No page body is stored and no crawler admission is implied.",
        ],
    }
    OUT.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    print("baseline", json.dumps(evidence["baseline_recomputed_from_legacy_ranks"], indent=2))
    for q in queries:
        if q["human"]["label"] != "PASS":
            print(q["human"]["label"], q["query"], "| rank", q["automated"]["domain_match_rank"],
                  "| top", q["top_result"]["title"])
    print("wrote", OUT)
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
