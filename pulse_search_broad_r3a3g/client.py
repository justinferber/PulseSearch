"""Standalone client for the versioned Pulse Search API.

This is the PUKE-side contract: a separate process asks arbitrary questions,
receives links/answer evidence or an explicit no-evidence state, and never
sends member context to Pulse Search or an external engine.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


class PulseSearchError(RuntimeError):
    def __init__(self, message: str, status: int = 0, body: dict | None = None):
        super().__init__(message)
        self.status = status
        self.body = body or {}


@dataclass(frozen=True)
class QueryResult:
    status: str
    response_mode: str
    answer: str
    links: tuple[dict, ...]
    citations: tuple[dict, ...]
    claim_evidence: tuple[dict, ...]
    request_id: str
    raw: dict

    @property
    def has_evidence(self) -> bool:
        return bool(self.citations or self.links)


class PulseSearchClient:
    """Loopback/private-network client; remote use must be explicitly enabled."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 8.0,
                 allow_remote: bool = False):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("base_url must be an http(s) URL")
        host = parsed.hostname.lower()
        if not allow_remote and host not in ("127.0.0.1", "::1", "localhost"):
            raise ValueError("remote Pulse Search requires allow_remote=True and a private network")
        if not token.strip():
            raise ValueError("a bearer token is required")
        self.base_url = base_url.rstrip("/")
        self._token = token
        self.timeout = timeout

    def _call(self, path: str, payload: dict | None = None) -> dict:
        data = None
        method = "GET"
        headers = {"Authorization": f"Bearer {self._token}",
                   "Accept": "application/json", "User-Agent": "PUKE-PulseSearchClient/1.1"}
        if payload is not None:
            if any(k in payload for k in ("member_context", "user_context", "email")):
                raise ValueError("member context must never be sent to Pulse Search")
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            method = "POST"
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=data,
                                         method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read(1_000_000).decode("utf-8"))
                if not isinstance(body, dict):
                    raise PulseSearchError("API returned a non-object response")
                return body
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read(64_000).decode("utf-8"))
            except Exception:
                body = {}
            raise PulseSearchError(
                f"Pulse Search returned HTTP {exc.code}: {body.get('status', 'error')}",
                exc.code, body) from exc
        except (OSError, ValueError) as exc:
            raise PulseSearchError(f"Pulse Search request failed: {exc}") from exc

    def health(self) -> dict:
        return self._call("/v1/health")

    def capabilities(self) -> dict:
        return self._call("/v1/capabilities")

    def search(self, query: str, limit: int = 8) -> dict:
        return self._call("/v1/search", {"query": query, "limit": limit})

    def answer(self, question: str) -> QueryResult:
        body = self._call("/v1/answer", {"question": question})
        citations = tuple(body.get("citations") or ())
        links = tuple(body.get("links") or body.get("result_cards") or ())
        return QueryResult(
            status=str(body.get("status") or "NO_EVIDENCE"),
            response_mode=str(body.get("response_mode") or "NO_EVIDENCE"),
            answer=str(body.get("answer") or ""),
            links=links, citations=citations,
            claim_evidence=tuple(body.get("claim_evidence") or ()),
            request_id=str(body.get("request_id") or ""), raw=body)

    def ask(self, question: str) -> QueryResult:
        return self.answer(question)

    def wiki_candidate(self, article: dict) -> dict:
        if any(k in article for k in ("member_context", "user_context", "email")):
            raise ValueError("member context must never be sent to the Wiki workflow")
        body = self._call("/v1/wiki-candidates", {"article": article})
        if body.get("publication") != "DRAFT_ONLY":
            raise PulseSearchError("Wiki candidate response was not marked DRAFT_ONLY",
                                   body=body)
        return body
