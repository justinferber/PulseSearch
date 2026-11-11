"""Explicit SearXNG JSON search-provider adapter for discovering useful webpages.

SearXNG: GET /search?q=...&format=json (format must be enabled by the owner).
No scheduled requests, no automatic crawling or permanent indexing.
Only an owner-selected local/loopback instance is accepted by default.
Results are ephemeral leads, not evidence of a content licence or live accuracy.
"""
from __future__ import annotations

import html
import ipaddress
import json
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE = 1_000_000


class ProviderError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ProviderError("provider_redirect_refused")


def _local_service(url: str) -> bool:
    p = urlsplit(url)
    if p.scheme != "http" or p.username or p.password or not p.hostname or p.path not in ("", "/"):
        return False
    try:
        return ipaddress.ip_address(p.hostname).is_loopback
    except ValueError:
        return p.hostname.lower() == "localhost"


def _safe_public_result(url: str) -> bool:
    try:
        p = urlsplit(url)
        if p.scheme not in ("https", "http") or not p.hostname or p.username or p.password:
            return False
        if p.hostname.endswith((".local", ".internal", ".invalid", ".test")):
            return False
        try:
            return ipaddress.ip_address(p.hostname).is_global
        except ValueError:
            return p.hostname.isascii()
    except ValueError:
        return False


def _text(s: str, cap: int) -> str:
    return " ".join(re.sub(r"<[^>]*>", " ", html.unescape(str(s or ""))).split())[:cap]


class SearxNG:
    def __init__(self, service: str, *, allow_remote: bool = False, timeout_s: float = 5.0):
        if not isinstance(service, str) or not service:
            raise ProviderError("missing_provider_url")
        if not _local_service(service):
            p = urlsplit(service)
            if not (allow_remote and p.scheme == "https" and p.hostname and
                    not p.username and not p.password and p.path in ("", "/")):
                raise ProviderError("provider_must_be_explicit_local_instance_or_approved_https")
        self.base = service.rstrip("/")
        self.timeout = min(max(float(timeout_s), 0.1), 10.0)

    def _request(self, url: str) -> dict:
        request = Request(url, headers={"User-Agent": "PulseSearch-R3A3G/0.1",
                                         "Accept": "application/json"})
        opener = build_opener(NoRedirect())
        try:
            with opener.open(request, timeout=self.timeout) as response:
                if "json" not in (response.headers.get("Content-Type") or "").lower():
                    raise ProviderError("provider_not_json")
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise ProviderError("provider_response_too_large")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise ProviderError("provider_unavailable") from exc
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise ProviderError("provider_invalid_json") from exc
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ProviderError("provider_missing_results")
        return data

    def search(self, query: str, *, limit: int = 10, language: str = "all",
               transport=None) -> dict:
        q = (query or "").strip()
        if not q or len(q) > 300:
            raise ProviderError("query_length_invalid")
        if not re.fullmatch(r"[a-zA-Z]{2,8}|all", language):
            raise ProviderError("language_invalid")
        params = urlencode({"q": q, "format": "json", "language": language, "pageno": 1})
        endpoint = self.base + "/search?" + params
        # transport is injected only for offline tests. No external requests
        # are made until a caller explicitly invokes search with a provider.
        raw = (transport or self._request)(endpoint)
        if not isinstance(raw, dict) or not isinstance(raw.get("results"), list):
            raise ProviderError("provider_missing_results")
        results = []
        seen = set()
        for hit in raw["results"]:
            if not isinstance(hit, dict):
                continue
            url = str(hit.get("url") or "")
            if not _safe_public_result(url) or url in seen:
                continue
            seen.add(url)
            results.append({
                "url": url,
                "title": _text(hit.get("title", ""), 160),
                "snippet": _text(hit.get("content", ""), 320),
                "source_kind": "provider_discovery_not_admitted",
                "verified_live": False,
                "indexed": False,
                "rights_verified": False,
            })
            if len(results) >= max(1, min(int(limit), 25)):
                break
        return {
            "query": q,
            "provider": "configured_searxng_json",
            "status": "provider_results_unverified",
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "results": results,
            "answer": None,
            "note": "Discovery leads only. URLs/content are not crawler-admitted; source rights, current facts and links need separate verification.",
        }
