"""Ten different M8 questions through the real standalone API."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_broad_r3a3g.api import Consumer, build_server  # noqa: E402
from pulse_search_broad_r3a3g.client import PulseSearchClient  # noqa: E402
from pulse_search_broad_r3a3g.wiki import WikiStore  # noqa: E402
from tools.r3a3g_m8_demo import build_index  # noqa: E402

TOKEN = "m8-local-api-token"
QUESTIONS = [
    "Hamburg public transport tickets",
    "London museum wheelchair access",
    "Can I refund concert tickets in Germany?",
    "Paris Pride dates",
    "How do I renew a UK passport?",
    "When should I call NHS 111?",
    "Berlin museum opening hours",
    "Berlin Christmas market public transport",
    "Berlin Uber Arena accessibility",
    "What is the Moon Parade route?",
]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="m8-api-"))
    try:
        build_index(tmp / "staging.sqlite")
        wiki = WikiStore(tmp / "wiki.sqlite")
        wiki.close()
        server = build_server(
            str(tmp / "staging.sqlite"),
            {"puke": Consumer("puke", TOKEN, frozenset({
                "health:read", "search:read", "answer:read", "wiki:propose"}))},
            port=0, wiki_path=str(tmp / "wiki.sqlite"))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        client = PulseSearchClient(base, TOKEN)
        cases = []
        try:
            for question in QUESTIONS:
                result = client.search(question, limit=5)
                cases.append({
                    "question": question,
                    "status": result.get("status"),
                    "result_types": result.get("result_types"),
                    "top": (result.get("results") or [{}])[0].get("url"),
                    "source_receipts": result.get("source_receipts"),
                    "unverified_leads": result.get("unverified_leads"),
                })
        finally:
            server.shutdown()
            server.server_close()
        evidence = {
            "kind": "R3A3G_M8_STANDALONE_API_DEMO",
            "generated_at": json.loads((ROOT / "docs/evidence/r3a3g_m8_source_snapshot.json")
                                       .read_text(encoding="utf-8"))["captured_at"],
            "mode": "AUTHENTICATED_LOOPBACK_API",
            "cases": cases,
            "summary": {
                "questions": len(cases),
                "with_indexed_result": sum(1 for c in cases if "permissioned_staging_document"
                                           in (c["result_types"] or [])),
                "with_official_navigation": sum(1 for c in cases
                                                  if c["status"] == "official_links"),
                "no_evidence": sum(1 for c in cases if c["status"] == "no_staging_evidence"),
            },
            "notes": ["Temporary provider leads are absent because no SearXNG is configured.",
                      "Source receipts distinguish indexed pages from official navigation."],
        }
        out = ROOT / "docs/evidence/r3a3g_m8_api_demo.json"
        out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(evidence["summary"], indent=2))
        print("wrote", out)
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
