"""Controlled one-page capture for evaluation metadata.

Every request goes through the reviewed Fetcher: DNS/private-IP checks, pinned
connections, bounded redirects, per-hop scope checks, robots.txt, a request
ceiling and host pacing. A source must carry explicit owner approval and an
evaluation-only rights class. Only title and meta description are stored.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_crawler_r3a3f.config import CrawlConfig  # noqa: E402
from pulse_search_crawler_r3a3f.robots import (  # noqa: E402
    MAX_ROBOTS_BYTES, decision_for_status,
)
from pulse_search_crawler_r3a3f.safe_fetch import Fetcher, FetchResult  # noqa: E402
from pulse_search_broad_r3a3g.evidence import registrable_domain  # noqa: E402

CONFIG = ROOT / "config/real_sources.json"
OUT = ROOT / "docs/evidence/r3a3g_real_source_snapshot.json"
BLOCKED_PATHS = ("/admin", "/login", "/signin", "/checkout", "/cart", "/account",
                 "/search", "/private")


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


class CapturePolicy:
    def __init__(self, source: dict):
        self.source = source
        self.domain = registrable_domain(urllib.parse.urlsplit(source["url"]).hostname or "")
        if not source.get("approved") or not source.get("approval_ref"):
            raise ValueError(f"{source['id']}: explicit owner approval is required")
        if source.get("rights") not in (
                "evaluation_metadata_only", "public_metadata_and_short_snippet"):
            raise ValueError(f"{source['id']}: unsupported rights class")
        self.last_request: dict[str, float] = {}
        self.attempts = 0
        self.robots_checked: set[str] = set()

    def target_denial(self, target: str) -> str | None:
        parts = urllib.parse.urlsplit(target)
        if parts.scheme != "https":
            return "https_required"
        host = (parts.hostname or "").lower()
        if registrable_domain(host) != self.domain:
            return "off_approved_domain"
        path = (parts.path or "/").lower()
        if any(path.startswith(prefix) for prefix in BLOCKED_PATHS):
            return "out_of_scope_path"
        return None

    def attempt_denial(self) -> str | None:
        if self.attempts >= 8:
            return "capture_attempt_ceiling"
        self.attempts += 1
        return None

    def request_gate(self, url: str) -> str | None:
        """Apply scope, attempt ceiling and pacing before any request."""
        denial = self.target_denial(url)
        if denial:
            return denial
        denial = self.attempt_denial()
        if denial:
            return denial
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        wait = max(0.0, 3.0 - (time.monotonic() - self.last_request.get(host, 0.0)))
        if wait:
            time.sleep(wait)
        self.last_request[host] = time.monotonic()
        return None

    def redirect_gate(self, fetcher: Fetcher, target: str) -> str | None:
        denial = self.target_denial(target)
        if denial:
            return denial
        parts = urllib.parse.urlsplit(target)
        host = (parts.hostname or "").lower()
        if host not in self.robots_checked:
            robots_url = "https://" + (parts.netloc or host) + "/robots.txt"
            denial = self.request_gate(robots_url)
            if denial:
                return denial
            robots = fetcher.fetch(
                robots_url, max_bytes=MAX_ROBOTS_BYTES,
                redirect_gate=lambda hop: self.target_denial(hop))
            if robots.error:
                return "redirect_robots_error"
            rules = decision_for_status(robots.status, robots.body, fetcher.config.user_agent)
            if not rules.can_fetch(parts.path or "/"):
                return "redirect_robots_denied"
            self.robots_checked.add(host)
        return self.request_gate(target)

    def paced_fetch(self, fetcher: Fetcher, url: str, *, max_bytes: int,
                    user_agent: str):
        # The gate covers robots, the initial request and every redirect hop.
        denial = self.request_gate(url)
        if denial:
            return FetchResult(url, url, error=denial)
        return fetcher.fetch(
            url, max_bytes=max_bytes, extra_headers={"Accept": "text/html"},
            redirect_gate=lambda target: self.redirect_gate(fetcher, target))


def capture(source: dict, fetcher: Fetcher) -> dict:
    policy = CapturePolicy(source)
    user_agent = fetcher.config.user_agent
    robots_url = "https://" + urllib.parse.urlsplit(source["url"]).netloc + "/robots.txt"
    robots_result = policy.paced_fetch(
        fetcher, robots_url, max_bytes=MAX_ROBOTS_BYTES, user_agent=user_agent)
    if robots_result.error:
        return {"status": 0, "final_url": source["url"], "title": "", "description": "",
                "error": f"robots_error:{robots_result.error}",
                "robots_source": "unreachable_fail_closed",
                "approval_ref": source["approval_ref"],
                "rights": source["rights"], "redirect_chain": []}
    rules = decision_for_status(robots_result.status, robots_result.body, user_agent)
    policy.robots_checked.add((urllib.parse.urlsplit(source["url"]).hostname or "").lower())
    path = urllib.parse.urlsplit(source["url"]).path or "/"
    if not rules.can_fetch(path):
        return {"status": 0, "final_url": source["url"], "title": "", "description": "",
                "error": "robots_denied", "robots_source": rules.source,
                "approval_ref": source["approval_ref"],
                "rights": source["rights"], "redirect_chain": []}
    result = policy.paced_fetch(
        fetcher, source["url"], max_bytes=600_000, user_agent=user_agent)
    if result.error:
        return {"status": result.status or 0, "final_url": result.final_url,
                "title": "", "description": "", "error": result.error,
                "robots_source": rules.source, "approval_ref": source["approval_ref"],
                "rights": source["rights"], "redirect_chain": result.chain,
                "redirect_hops": result.hops}
    content_type = result.headers.get("content-type", "")
    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    if match:
        charset = match.group(1)
    parser = Metadata()
    parser.feed(result.body.decode(charset, errors="replace"))
    return {"status": result.status, "final_url": result.final_url,
            "title": " ".join(parser.title.split())[:300],
            "description": " ".join(parser.description.split())[:600],
            "content_type": content_type, "robots_source": rules.source,
            "approval_ref": source["approval_ref"], "rights": source["rights"],
            "redirect_chain": result.chain, "redirect_hops": result.hops}


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    fetcher = Fetcher(CrawlConfig(min_interval_s=3.0, timeout_s=20.0,
                                  max_bytes=600_000, max_redirects=3))
    pages = []
    for source in config["sources"]:
        record = capture(source, fetcher)
        pages.append({**source, **record})
        print(f"{record['status']:>3} {source['id']:<24} {record.get('title', '')[:70]}")
    payload = {
        "kind": "R3A3G_REAL_SOURCE_SNAPSHOT",
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "CONTROLLED_SINGLE_PAGE_EVALUATION_METADATA",
        "not_a_crawler_admission": True,
        "controls": {
            "ssrf_private_ip_guard": "pulse_search_crawler_r3a3f.netguard",
            "robots": "RFC9309-style, fail closed",
            "redirects": "same registrable domain, per-hop re-check",
            "pacing_s": 3.0, "attempt_ceiling_per_source": 8,
            "rights": "evaluation_metadata_only",
            "owner_approval_required": True,
        },
        "pages": pages,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
