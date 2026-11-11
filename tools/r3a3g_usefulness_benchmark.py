"""Practical usefulness benchmark over real captured official pages.

Each query names the service a person needs. A pass requires a reviewed official
link from that service in the response, or a genuinely query-supporting admitted
page. Unrelated admitted results are reported as failures, not hidden.
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

SNAPSHOT = ROOT / "docs/evidence/r3a3g_real_source_snapshot.json"
OUT = ROOT / "docs/evidence/r3a3g_usefulness_benchmark.json"
CASES = [
    ("berlin-concert-tickets", "How do I book concert tickets in Berlin?",
     ["eventim.de", "mercedes-benz-arena.de", "columbiahalle.de"]),
    ("berlin-venue-accessibility", "Berlin concert venue accessibility and bag rules",
     ["mercedes-benz-arena.de", "huxleys-neue-welt.de", "verti-music-hall.de"]),
    ("berlin-christmas-transport", "Berlin Christmas market public transport",
     ["bvg.de", "s-bahn-berlin.de"]),
    ("london-fireworks", "London New Year's Eve fireworks tickets",
     ["london.gov.uk", "tfl.gov.uk"]),
    ("berlin-csd-2027", "Berlin CSD 2027 dates", ["csd-berlin.de"]),
    ("berlin-pride-route", "Berlin Pride route and accessibility", ["csd-berlin.de"]),
    ("glastonbury-2027", "Glastonbury Festival 2027 dates",
     ["glastonburyfestivals.co.uk", "bbc.co.uk"]),
    ("berlin-music-festivals", "Berlin music festivals",
     ["berlin.de", "glastonburyfestivals.co.uk", "efa-aef.eu"]),
]


def host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def expected(domain: str, domains: list[str]) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in domains)


def main() -> int:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    usable = [p for p in snapshot["pages"] if p.get("status") == 200 and p.get("title")]
    tmp = Path(tempfile.mkdtemp(prefix="r3a3g-useful-"))
    index = StagingIndex(tmp / "staging.sqlite")
    for page in usable:
        index.add_document({
            "url": page["url"], "source_id": page["id"], "title": page["title"],
            "snippet": page.get("description") or "", "category": "Other",
            "category_confidence": 0.9, "categories": ["Other"], "depth": 1,
            "fetched_at": snapshot["captured_at"], "content_hash": "useful-" + page["id"],
            "source_authority": page.get("authority", "official"),
        }, [], index_allowed=True)
    index.close()
    cases = []
    for case_id, query, domains in CASES:
        index = StagingIndex(tmp / "staging.sqlite")
        try:
            response = search_staging(index, query, limit=5, enforce_support=True)
        finally:
            index.close()
        results = response.get("results") or []
        cards = results + (response.get("related_official_links") or [])
        matching = [card for card in cards
                    if expected(host(card.get("url", "")), domains)]
        top = results[0] if results else {}
        top_expected = bool(top and expected(host(top.get("url", "")), domains))
        # An official response passes only if its first handoff is the service
        # the person needs; any matching card later is not enough.
        passed = bool(matching) and top_expected
        cases.append({
            "case_id": case_id, "query": query, "expected_domains": domains,
            "status": response.get("status"),
            "response_mode": response.get("response_mode"),
            "passed": passed,
            "top_result": {"title": top.get("title"), "url": top.get("url")},
            "top_result_matches_expected": top_expected,
            "matching_official_domains": sorted({host(c.get("url", "")) for c in matching}),
            "results": [{"title": c.get("title"), "url": c.get("url"),
                         "kind": c.get("source_kind")} for c in results[:5]],
            "notice": (response.get("notices") or [None])[0],
        })
    passed = sum(1 for c in cases if c["passed"])
    payload = {
        "kind": "R3A3G_USEFULNESS_BENCHMARK",
        "mode": "REAL_CAPTURED_PAGES_PLUS_REVIEWED_OFFICIAL_LINKS",
        "generated_at": snapshot["captured_at"],
        "cases": cases,
        "summary": {"cases": len(cases), "passed": passed,
                    "failed": len(cases) - passed,
                    "pass_rate": round(passed / len(cases), 3),
                    "unrelated_top_result": sum(
                        1 for c in cases if c["status"] == "staging_results"
                        and not c["top_result_matches_expected"])},
        "limitations": [
            "Official-link passes are navigation, not proof of a live value or crawler licence.",
            "A missing source remains a coverage gap; no facts are invented to fill it.",
            "This benchmark covers eight named practical queries, not open-web recall.",
        ],
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    for case in cases:
        print(("PASS" if case["passed"] else "FAIL"), case["case_id"],
              case["status"], "top=", case["top_result"]["url"])
    print("wrote", OUT)
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
