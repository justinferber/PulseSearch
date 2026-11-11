"""Demonstrate a separate PUKE client asking arbitrary questions."""

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
from pulse_search_broad_r3a3g.client import PulseSearchClient, PulseSearchError  # noqa: E402
from pulse_search_broad_r3a3g.wiki import WikiService, WikiStore  # noqa: E402
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402

ARTICLES = json.loads((ROOT / "config/wiki_articles.json").read_text(encoding="utf-8"))["articles"]

TOKEN = "local-puke-client-token"


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="puke-client-"))
    snapshot = json.loads((ROOT / "docs/evidence/r3a3g_real_source_snapshot.json")
                          .read_text(encoding="utf-8"))
    usable = [p for p in snapshot["pages"] if p.get("status") == 200
              and p.get("title") and p.get("description")]
    staging = StagingIndex(tmp / "staging.sqlite")
    for page in usable:
        staging.add_document({
            "url": page["url"], "source_id": page["id"], "title": page["title"],
            "snippet": page["description"], "category": "Other",
            "category_confidence": 0.9, "categories": ["Other"], "depth": 1,
            "fetched_at": snapshot["captured_at"], "content_hash": f"puke-{page['id']}",
            "source_authority": page.get("authority", "official"),
        }, [], index_allowed=True)
    staging.close()
    wiki = WikiStore(tmp / "wiki.sqlite")
    wiki.close()
    server = build_server(
        str(tmp / "staging.sqlite"),
        {"puke": Consumer("puke", TOKEN, frozenset({
            "health:read", "search:read", "answer:read", "wiki:propose"}))},
        port=0, wiki_path=str(tmp / "wiki.sqlite"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    client = PulseSearchClient(base, TOKEN)
    cases = []
    try:
        health = client.health()
        for question in [
            "What is the weather in London tomorrow?",
            "When is CSD Berlin 2027?",
            "When is Glastonbury Festival 2027?",
            "London New Year's Eve fireworks tickets",
            "Berlin Christmas market public transport",
            "When is the Moon Parade?",
        ]:
            result = client.answer(question)
            search = client.search(question, limit=5)
            cases.append({
                "question": question, "status": result.status,
                "response_mode": result.response_mode, "answer": result.answer,
                "links": len(result.links), "citations": len(result.citations),
                "claim_evidence": len(result.claim_evidence),
                "request_id": result.request_id,
                "has_evidence": result.has_evidence,
                "search_status": search.get("status"),
                "search_results": [
                    {"title": r.get("title"), "url": r.get("url"),
                     "source_kind": r.get("source_kind")}
                    for r in (search.get("results") or [])[:3]],
            })
        chain_question = "How do I book concert tickets in Berlin?"
        chain_search = client.search(chain_question, limit=3)
        chain_answer = client.answer(chain_question)
        wiki = client.wiki_candidate(ARTICLES[0])
        try:
            client.wiki_candidate({"title": "blocked", "member_context": "private"})
            context_blocked = False
        except ValueError:
            context_blocked = True
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(tmp, ignore_errors=True)
    evidence = {
        "kind": "R3A3G_PUKE_CLIENT_DEMO",
        "generated_at": snapshot["captured_at"],
        "mode": "SEPARATE_LOOPBACK_CLIENT",
        "health": health, "cases": cases,
        "chain": {"query": chain_question,
                  "search_status": chain_search.get("status"),
                  "search_top": (chain_search.get("results") or [{}])[0].get("url"),
                  "answer_status": chain_answer.status,
                  "answer_citations": len(chain_answer.citations),
                  "claim_evidence": len(chain_answer.claim_evidence)},
        "wiki_candidate": {"status": wiki.get("status"),
                           "publication": wiki.get("publication")},
        "member_context_blocked_client_side": context_blocked,
        "note": "No member context is sent. The client is a separate process/contract, not part of the API server.",
    }
    out = ROOT / "docs/evidence/r3a3g_puke_client_demo.json"
    out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"cases": len(cases),
                      "statuses": [c["status"] for c in cases],
                      "wiki": evidence["wiki_candidate"],
                      "context_blocked": context_blocked, "evidence": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
