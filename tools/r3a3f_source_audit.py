"""Read-only audit of the owner's 120-page index: source registry proposal.

Opens the accepted October index with mode=ro, verifies its pinned SHA-256 and
derives the distinct source hosts already represented. It never writes to the
index, never fetches a URL and never infers source permission from the mere
presence of a page.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

PIN = "bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d"
DEFAULT_INDEX = (
    "C:/Users/justi/Desktop/pulseunity/ChatGPTCode/"
    "Pulse_Search_R2P27C_Run_gURzKuV2/live/expanded_live_100_research_index.sqlite"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", default=DEFAULT_INDEX)
    parser.add_argument("--out", default="docs/evidence/r3a3f_source_registry_proposal.json")
    args = parser.parse_args()
    path = Path(args.index)
    if not path.exists():
        print(json.dumps({"status": "HOLD_INDEX_NOT_FOUND", "path": str(path)}))
        return 2
    digest = sha256_file(path)
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name")]
    page_table = next((t for t in tables if t in ("pages", "documents", "docs")), None)
    pages: list[dict] = []
    if page_table:
        rows = conn.execute(f"SELECT * FROM {page_table}").fetchall()
        for row in rows:
            data = dict(row)
            url = data.get("url") or data.get("source_url") or ""
            if not url:
                continue
            pages.append({"url": url, "title": data.get("title", "")})
    hosts = Counter(urlsplit(p["url"]).netloc.lower() for p in pages if p["url"])
    schemes = Counter(urlsplit(p["url"]).scheme for p in pages if p["url"])
    proposal = {
        "kind": "R3A3F_SOURCE_REGISTRY_PROPOSAL",
        "status": "PROPOSAL_ONLY_NOT_ADMITTED",
        "index_path": str(path),
        "index_sha256": digest,
        "index_pin": PIN,
        "index_pin_match": digest == PIN,
        "read_only": True,
        "tables": tables,
        "page_count": len(pages),
        "distinct_hosts": len(hosts),
        "schemes": dict(schemes),
        "hosts": [
            {
                "host": host,
                "pages": count,
                "example_url": next(p["url"] for p in pages if urlsplit(p["url"]).netloc.lower() == host),
                "rights_status": "NOT_ASSESSED",
                "index_allowed": None,
                "note": "Presence in the accepted index is not permission to crawl. "
                        "Each host needs an explicit owner admission, robots review and "
                        "rights/terms basis before any live fetch.",
            }
            for host, count in hosts.most_common()
        ],
        "reminder": "bytebytego.com and nginx.org appear as technical references, not event sources.",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "OK", "pin_match": proposal["index_pin_match"],
                      "pages": len(pages), "hosts": len(hosts), "out": str(out)}, indent=2))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
