"""Exercise the versioned API and save request/response fixtures."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_broad_r3a3g.api import build_server  # noqa: E402
from pulse_search_broad_r3a3g.wiki import WikiService, WikiStore  # noqa: E402
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402

TOKEN = "local-demo-token"


def call(base, path, payload=None, token=TOKEN):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        base + path, data=data, method="POST" if data else "GET",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="r3a3g-api-demo-"))
    staging = StagingIndex(tmp / "staging.sqlite")
    for url, title, snippet in [
        ("https://pulseunity.co/knowledge", "Pulse UNITY Knowledge Engine",
         "The engine returns cited evidence or an honest no-evidence state."),
        ("https://www.berlin.de/events/", "Berlin events calendar",
         "Official city event listings with organiser links."),
    ]:
        staging.add_document({
            "url": url, "source_id": "demo", "title": title, "snippet": snippet,
            "category": "Other", "category_confidence": 0.8, "categories": ["Other"],
            "depth": 1, "fetched_at": "2026-11-11T10:00:00+00:00",
            "content_hash": f"demo-{abs(hash(url))}"}, [], index_allowed=True)
    staging.close()
    wiki = WikiStore(tmp / "wiki.sqlite")
    WikiService(wiki).propose({
        "topic_id": "demo-wiki", "title": "Demo Wiki topic", "summary": "Public evidence only.",
        "claims": [{"text": "Use official forecast services for current weather.",
                    "sources": ["https://www.bbc.co.uk/weather",
                                "https://weather.metoffice.gov.uk/forecast/uk"]}],
        "verified_at": "2026-11-11"})
    wiki.close()
    server = build_server(str(tmp / "staging.sqlite"), {"puke": TOKEN}, port=0,
                          wiki_path=str(tmp / "wiki.sqlite"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    fixtures = []
    try:
        for label, path, payload, token in [
            ("unauthenticated", "/v1/health", None, "wrong"),
            ("health", "/v1/health", None, TOKEN),
            ("capabilities", "/v1/capabilities", None, TOKEN),
            ("search", "/v1/search", {"query": "knowledge engine"}, TOKEN),
            ("answer_event", "/v1/answer", {"question": "When is Glastonbury on next year?"}, TOKEN),
            ("answer_weather", "/v1/answer",
             {"question": "What is the weather in London tomorrow?"}, TOKEN),
            ("no_evidence", "/v1/answer", {"question": "When is the Moon Parade?"}, TOKEN),
            ("wiki_candidate", "/v1/wiki-candidates", {"article": {
                "topic_id": "demo-api-topic", "title": "Demo API topic", "summary": "Draft only.",
                "claims": [{"text": "Use an official forecast service.",
                            "sources": ["https://www.bbc.co.uk/weather",
                                        "https://weather.metoffice.gov.uk/forecast/uk"]}],
                "verified_at": "2026-11-11"}}, TOKEN),
        ]:
            status, body = call(base, path, payload, token)
            fixtures.append({"case": label, "request": {"path": path, "body": payload},
                             "status": status, "response": body})
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(tmp, ignore_errors=True)
    evidence = {"kind": "R3A3G_API_DEMO", "generated_at": "2026-11-11",
                "mode": "LOCAL_LOOPBACK_TOKEN_TEST", "fixtures": fixtures,
                "note": "No public bind. The token is a local test fixture, not a secret."}
    out = ROOT / "docs/evidence/r3a3g_api_demo.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({"cases": len(fixtures),
                      "statuses": {f["case"]: f["status"] for f in fixtures},
                      "evidence": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
