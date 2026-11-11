"""Optional temporary web discovery that never becomes indexed evidence.

A SearXNG instance is only consulted when an operator explicitly configures a
loopback base URL. Its snippets are labelled provider metadata, are never
fetched, never admitted to the index and never presented as facts. If no
provider is configured, the caller must report that honestly.
"""

from __future__ import annotations

import ipaddress
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

MAX_LEADS = 8
MAX_TITLE = 200
MAX_SNIPPET = 320


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SearxngDiscovery:
    provider = "searxng"

    def __init__(self, base_url: str | None, timeout_s: float = 4.0):
        self.base_url = (base_url or "").rstrip("/")
        self.timeout_s = timeout_s
        if self.base_url:
            parts = urlsplit(self.base_url)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                raise ValueError("SearXNG URL must be an absolute http(s) URL")
            if parts.username or parts.password:
                raise ValueError("credentials are not accepted in the provider URL")
            host = parts.hostname.lower()
            try:
                loopback = ipaddress.ip_address(host).is_loopback
            except ValueError:
                loopback = host in ("localhost", "::1")
            if not loopback:
                raise ValueError("only a locally configured loopback SearXNG is accepted")

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def search(self, query: str, limit: int = 5) -> dict:
        if not self.configured:
            return {"provider": self.provider, "status": "NOT_CONFIGURED",
                    "verified": False, "leads": [],
                    "notices": ["No SearXNG endpoint is configured; no temporary web leads were requested."]}
        limit = max(1, min(int(limit), MAX_LEADS))
        url = self.base_url + "/search?" + urlencode({
            "q": query, "format": "json", "language": "en", "safesearch": "1",
        })
        request = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "PulseSearchFB2-M8/0.1 (research; local provider)",
        })
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                if response.status != 200:
                    raise ValueError("provider status")
                raw = response.read(512_000)
                data = json.loads(raw.decode("utf-8"))
        except Exception:
            return {"provider": self.provider, "status": "UNAVAILABLE",
                    "verified": False, "leads": [],
                    "notices": ["The configured SearXNG endpoint could not be read; no leads were used."]}
        leads = []
        for item in (data.get("results") or [])[:limit]:
            if not isinstance(item, dict):
                continue
            link = str(item.get("url") or "").strip()
            parts = urlsplit(link)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                continue
            leads.append({
                "title": " ".join(str(item.get("title") or "").split())[:MAX_TITLE],
                "url": link,
                "snippet": " ".join(str(item.get("content") or "").split())[:MAX_SNIPPET],
                "publisher": parts.hostname.lower(),
                "source_kind": "unverified_provider_lead",
                "verified": False,
                "rights": "provider_metadata_only",
                "retrieved_at": _now(),
                "notices": ["Temporary search-provider metadata; not fetched, indexed, or verified."],
            })
        return {"provider": self.provider, "status": "OK", "verified": False,
                "leads": leads,
                "notices": ["Provider leads are temporary and must not be treated as admitted evidence."]}
