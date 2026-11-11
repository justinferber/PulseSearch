"""Capture one short metadata record per reviewed source.

This is deliberate manual evidence collection for evaluation, not a crawler.
It fetches one URL per registry entry, stores only title and meta description,
and records the HTTP status so blocked/renamed pages are visible.
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/real_sources.json"
OUT = ROOT / "docs/evidence/r3a3g_real_source_snapshot.json"


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        values = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() == "meta":
            name = (values.get("name") or values.get("property") or "").lower()
            if name in ("description", "og:description") and not self.description:
                self.description = html.unescape(values.get("content") or "")

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = " ".join(data.split())


def capture(url: str) -> dict:
    request = urllib.request.Request(
        url, headers={"User-Agent": "PulseSearch-Evaluation/0.1 (single reviewed page; contact owner)"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(600_000)
            content_type = response.headers.get("Content-Type", "")
            charset = "utf-8"
            match = re.search(r"charset=([\w-]+)", content_type, re.I)
            if match:
                charset = match.group(1)
            text = raw.decode(charset, errors="replace")
            parser = Metadata()
            parser.feed(text)
            return {"status": response.status, "final_url": response.geturl(),
                    "title": " ".join(parser.title.split())[:300],
                    "description": " ".join(parser.description.split())[:600],
                    "content_type": content_type}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "final_url": url, "title": "", "description": "",
                "content_type": "", "error": f"HTTP {exc.code}"}
    except Exception as exc:
        return {"status": 0, "final_url": url, "title": "", "description": "",
                "content_type": "", "error": type(exc).__name__}


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    pages = []
    for source in config["sources"]:
        record = capture(source["url"])
        pages.append({**source, **record})
        print(f"{record['status']:>3} {source['id']:<22} {record['title'][:80]}")
    payload = {"kind": "R3A3G_REAL_SOURCE_SNAPSHOT",
               "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "mode": "MANUAL_SINGLE_PAGE_EVIDENCE_ONLY",
               "not_a_crawler_admission": True,
               "pages": pages}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
