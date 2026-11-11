"""Run the 60+ labelled queries and publish measured acceptance evidence."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_broad_r3a3g.search import search_documents  # noqa: E402
from tests.test_r3a3g_acceptance import CASES, DOCS  # noqa: E402


def host(url: str) -> str:
    return (urlsplit(url).hostname or "").replace("www.", "")


def main() -> int:
    rows, failures = [], []
    recall_at_3 = 0
    mrr = 0.0
    wrong_city = 0
    unsupported = 0
    no_evidence = 0
    hosts, result_count = set(), 0
    started = time.perf_counter()
    for query, intent, status, needle in CASES:
        t0 = time.perf_counter()
        result = search_documents(DOCS, query)
        latency = (time.perf_counter() - t0) * 1000
        urls = [r["url"] for r in result["results"]]
        rank = next((i + 1 for i, url in enumerate(urls) if needle and needle in url), 0)
        if rank and rank <= 3:
            recall_at_3 += 1
        if rank:
            mrr += 1 / rank
        if result["intent"]["kind"] != intent or result["status"] != status or \
                (needle and not rank):
            failures.append({"query": query, "expected": [intent, status, needle],
                             "got": [result["intent"]["kind"], result["status"], urls[:3]]})
        q = query.lower()
        if any(city in q for city in ("berlin", "london")) and urls:
            other = "london" if "berlin" in q else "berlin"
            if other in urls[0].lower():
                wrong_city += 1
        if result["status"] in ("staging_results", "official_links") and not urls:
            unsupported += 1
        if result["status"] == "no_staging_evidence":
            no_evidence += 1
        for url in urls:
            if host(url):
                hosts.add(host(url))
        result_count += len(urls)
        rows.append({"query": query, "intent": result["intent"]["kind"],
                     "status": result["status"],
                     "response_mode": result.get("response_mode"),
                     "top_urls": urls[:3], "latency_ms": round(latency, 2)})
    n = len(CASES)
    evidence = {
        "kind": "R3A3G_ACCEPTANCE_DEMO",
        "generated_at": "2026-11-11",
        "mode": "OFFLINE_LABELLED_FIXTURES",
        "queries": n,
        "metrics": {
            "recall_at_3": round(recall_at_3 / n, 3),
            "mrr": round(mrr / n, 3),
            "wrong_city_rate": round(wrong_city / n, 3),
            "unsupported_result_rate": round(unsupported / n, 3),
            "no_evidence_cases": no_evidence,
            "source_diversity": round(len(hosts) / max(1, result_count), 3),
            "mean_latency_ms": round(sum(r["latency_ms"] for r in rows) / n, 2),
        },
        "failures": failures,
        "rows": rows,
        "limits": ["Labelled offline fixtures only; this is not open-web accuracy.",
                   "Source diversity is bounded by the fixture corpus."],
    }
    path = ROOT / "docs/evidence/r3a3g_acceptance.json"
    path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({"queries": n, "failures": len(failures),
                      "metrics": evidence["metrics"], "evidence": str(path)}, indent=2))
    return 0 if len(failures) <= 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
