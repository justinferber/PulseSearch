"""M8 real-source demonstration over captured specific pages.

No network is used here. Pages come from the controlled M8 snapshot and the
earlier snapshot; every indexed page carries its source and rights receipt.
Queries exercise different intents and must show either a useful page/official
handoff or an honest no-evidence result.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_broad_r3a3g.api import source_receipts  # noqa: E402
from pulse_search_broad_r3a3g.discovery import SearxngDiscovery  # noqa: E402
from pulse_search_broad_r3a3g.search import search_staging  # noqa: E402
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402

M8 = ROOT / "docs/evidence/r3a3g_m8_source_snapshot.json"
LEGACY = ROOT / "docs/evidence/r3a3g_real_source_snapshot.json"
OUT = ROOT / "docs/evidence/r3a3g_m8_demo.json"

CASES = [
    ("hamburg-transport", "Hamburg public transport tickets"),
    ("london-museum-access", "London museum wheelchair access"),
    ("german-concert-refund", "Can I refund concert tickets in Germany?"),
    ("paris-pride", "Paris Pride dates"),
    ("uk-passport", "How do I renew a UK passport?"),
    ("london-theatre-refund", "London theatre ticket refund policy"),
    ("berlin-museum-hours", "Berlin museum opening hours Sunday"),
    ("berlin-christmas-transport", "Berlin Christmas market public transport"),
    ("nhs-urgent-care", "When should I call NHS 111?"),
    ("berlin-venue-access", "Berlin Uber Arena accessibility and bag policy"),
    ("paris-events", "What events are on in Paris this weekend?"),
    ("uk-consumer-refund", "UK consumer refund rights"),
    ("hamburg-christmas", "Hamburg Christmas market travel"),
    ("unsupported-query", "What is the Moon Parade route?"),
]


def load_pages() -> list[dict]:
    pages = []
    for path, kind in ((LEGACY, "r3a3g"), (M8, "m8")):
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for page in payload.get("pages", []):
            if page.get("status") != 200 or not page.get("title"):
                continue
            pages.append({**page, "_snapshot": kind,
                          "_captured_at": payload.get("captured_at")})
    return pages


def build_index(path: Path) -> None:
    index = StagingIndex(path)
    for page in load_pages():
        # Page text and curator tags are separate fields. Tags may rank a
        # candidate, but must never be rendered as if the page said them.
        body = page.get("description") or page.get("title") or ""
        metadata = {
            "topics": page.get("topics") or [],
            "jurisdiction": page.get("jurisdiction"),
            "document_type": page.get("document_type"),
            "source_authority": page.get("authority"),
        }
        provenance = {
            "source_id": page.get("id"), "final_url": page.get("final_url"),
            "captured_at": page.get("_captured_at"),
            "approval_ref": page.get("approval_ref"),
            "rights": page.get("rights"),
            "snapshot": page.get("_snapshot"),
        }
        index.add_document({
            "url": page.get("final_url") or page["url"],
            "source_id": page.get("id"),
            "title": page["title"], "snippet": body,
            "metadata": json.dumps(metadata, ensure_ascii=False),
            "category": "Other", "category_confidence": 0.9,
            "categories": ["Other"], "depth": 1,
            "fetched_at": page.get("_captured_at"),
            "content_hash": "m8-" + str(page.get("id")),
            "rights_mode": page.get("rights", "unknown"),
            "source_authority": page.get("authority"),
            "document_type": page.get("document_type"),
            "language": page.get("language"),
            "jurisdiction": page.get("jurisdiction"),
            "specificity": page.get("specificity"),
            "provenance": json.dumps(provenance, ensure_ascii=False),
        }, [], index_allowed=True)
    index.close()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="m8-demo-"))
    try:
        build_index(tmp / "staging.sqlite")
        index = StagingIndex(tmp / "staging.sqlite")
        provider = SearxngDiscovery(None)
        cases = []
        try:
            for case_id, query in CASES:
                result = search_staging(index, query, limit=5, enforce_support=True)
                cases.append({
                    "id": case_id, "query": query, "status": result.get("status"),
                    "response_mode": result.get("response_mode"),
                    "results": result.get("results", []),
                    "source_receipts": source_receipts(result.get("results", [])),
                    "unverified_leads": provider.search(query, limit=3),
                    "note": result.get("note"),
                })
        finally:
            index.close()
        evidence = {
            "kind": "R3A3G_M8_REAL_SOURCE_DEMO",
            "generated_at": json.loads(M8.read_text(encoding="utf-8"))["captured_at"],
            "mode": "CONTROLLED_LOCAL_INDEX",
            "cases": cases,
            "summary": {
                "cases": len(cases),
                "with_specific_result": sum(
                    1 for c in cases if c["status"] in ("staging_results", "official_links")
                ),
                "no_evidence": sum(1 for c in cases if c["status"] == "no_staging_evidence"),
                "provider_leads": "NOT_CONFIGURED",
            },
            "limits": ["No live dates, prices, availability or facts are asserted.",
                       "Provider leads are unverified metadata and are never merged into results."],
        }
        OUT.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(evidence["summary"], indent=2))
        for case in cases:
            top = (case["results"] or [{}])[0]
            print(case["id"], case["status"], top.get("url", "none"))
        print("wrote", OUT)
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
