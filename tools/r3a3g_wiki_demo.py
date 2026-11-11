"""Build ten-plus local Wiki drafts and exercise the editorial workflow."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_broad_r3a3g.wiki import (  # noqa: E402
    LocalPublisher, WikiPolicy, WikiService, WikiStore,
)

DB = ROOT / "data/r3a3g_wiki/wiki.sqlite"


def main() -> int:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    store = WikiStore(DB)
    service = WikiService(store, LocalPublisher())
    articles = json.loads((ROOT / "config/wiki_articles.json").read_text(encoding="utf-8"))["articles"]
    created = []
    for article in articles:
        result = service.propose(article)
        created.append({"topic_id": article["topic_id"], "slug": article["slug"],
                        "result": result["result"]})
    # Update and duplicate handling on the Berlin booking guide.
    first = dict(articles[0])
    first["claims"] = articles[0]["claims"] + [{
        "text": "Confirm the venue's accessibility arrangements on its own page before booking.",
        "sources": ["https://www.mercedes-benz-arena.de/"]}]
    update = service.propose(first)
    duplicate = service.propose(articles[0])
    # Editorial approval and a local-only publication test.
    published = []
    policy = WikiPolicy(auto_publish_enabled=True, authorised_by="LOCAL_TEST_POLICY_ONLY",
                        allowed_categories=("general",))
    for article in articles[:3]:
        service.approve(article["topic_id"], "local-test-editor")
        published.append(service.publish(article["topic_id"], policy,
                                         reviewer="local-test-editor"))
    rejected = service.reject(articles[4]["topic_id"], "local-test-editor",
                              "needs a city-specific source")
    revoked = service.flag_source(articles[1]["claims"][0]["sources"][0],
                                  "source withdrawn in test")
    pages = store.list()
    evidence = {
        "kind": "R3A3G_WIKI_DEMO",
        "generated_at": "2026-11-11",
        "mode": "LOCAL_TEST_WIKI_ONLY",
        "db": str(DB.relative_to(ROOT)),
        "articles": created,
        "update": update,
        "duplicate": duplicate,
        "published": published,
        "rejected": rejected,
        "revocation": revoked,
        "status_counts": {status: sum(1 for p in pages if p["status"] == status)
                          for status in sorted({p["status"] for p in pages})},
        "publication_note": "Published only to the local test publisher. No Pulse UNITY/UNA Wiki write occurred.",
    }
    out = ROOT / "docs/evidence/r3a3g_wiki_demo.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({"drafts": len(created), "update": update["result"],
                      "duplicate": duplicate["result"],
                      "published": len(published), "status_counts": evidence["status_counts"],
                      "evidence": str(out)}, indent=2))
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
