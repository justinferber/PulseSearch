"""Versioned, scoped Pulse Search API for PUKE and other authorised clients.

Security defaults: loopback bind, mandatory bearer token, per-consumer scopes,
thread-safe rate limits, bounded JSON bodies, no CORS, no query text in logs,
and draft-only Wiki proposals. The public internet must not reach this service
before an independent security review.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import quote, urlsplit

from . import privacy
from .answers import AnswerService, load_pack
from .discovery import SearxngDiscovery
from .search import search_staging
from .wiki import WikiError, WikiPolicy, WikiService, WikiStore

MAX_BODY = 16_384
MAX_QUERY = 400
READ_TIMEOUT = 10.0
VERSION = "1.2"

SCOPES = {
    "health:read", "search:read", "answer:read", "wiki:propose",
}
PATH_SCOPES = {
    "/v1/health": "health:read",
    "/v1/capabilities": "health:read",
    "/v1/search": "search:read",
    "/v1/answer": "answer:read",
    "/v1/wiki-candidates": "wiki:propose",
}


@dataclass(frozen=True)
class Consumer:
    name: str
    token: str
    scopes: frozenset[str]

    def allows(self, scope: str) -> bool:
        return "*" in self.scopes or scope in self.scopes


class ForbiddenScope(PermissionError):
    def __init__(self, required: str):
        self.required = required
        super().__init__(f"missing scope: {required}")


class ReadOnlyIndex:
    def __init__(self, path: str):
        target = Path(path).resolve(strict=True)
        self.conn = sqlite3.connect("file:" + quote(str(target), safe="/:" ) + "?mode=ro",
                                    uri=True, timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.fts = bool(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='doc_fts'").fetchone())

    def close(self):
        self.conn.close()

    def all_documents(self, limit: int = 5000) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM docs WHERE revoked=0 ORDER BY doc_id LIMIT ?",
            (max(1, min(int(limit), 5000)),)).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, category: str | None = None, limit: int = 10) -> list[dict]:
        if self.fts and query.strip():
            terms = [t for t in re.findall(r"[A-Za-z0-9]+", query)][:12]
            expression = " OR ".join('"' + t + '"*' for t in terms) or query
            rows = self.conn.execute(
                "SELECT d.*, bm25(doc_fts) AS bm25 FROM doc_fts JOIN docs d ON d.doc_id=doc_fts.rowid"
                " WHERE doc_fts MATCH ? AND d.revoked=0 ORDER BY bm25(doc_fts) LIMIT ?",
                (expression, limit)).fetchall()
            return [dict(r) for r in rows]
        like = f"%{query}%"
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM docs WHERE revoked=0 AND (title LIKE ? OR snippet LIKE ?)"
            " ORDER BY doc_id DESC LIMIT ?", (like, like, limit)).fetchall()]


class RateLimiter:
    def __init__(self, limit: int = 60, window_s: int = 60):
        self.limit = limit
        self.window = window_s
        self.events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, consumer: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            bucket = self.events[consumer]
            while bucket and now - bucket[0] > self.window:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False, max(1, int(self.window - (now - bucket[0])))
            bucket.append(now)
            return True, 0


class _Handler(BaseHTTPRequestHandler):
    server_version = f"PulseSearchAPI/{VERSION}"
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        return

    def _json(self, status: int, body: dict, extra: dict | None = None):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def _unauthenticated(self, message: str):
        self._json(401, {"status": "UNAUTHENTICATED", "error": message},
                   {"WWW-Authenticate": "Bearer"})

    def _consumer(self) -> Consumer | None:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        supplied = header[7:].strip()
        if not supplied:
            return None
        for consumer in self.server.consumers.values():
            if hmac.compare_digest(supplied, consumer.token):
                return consumer
        return None

    def _require(self, scope: str) -> Consumer | None:
        consumer = self._consumer()
        if not consumer:
            self._unauthenticated("bearer token required")
            return None
        if not consumer.allows(scope):
            self._json(403, {"status": "FORBIDDEN", "required_scope": scope,
                             "consumer": consumer.name})
            return None
        return consumer

    def _body(self) -> dict:
        self.connection.settimeout(READ_TIMEOUT)
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("transfer-encoding is not accepted")
        length_header = self.headers.get("Content-Length")
        try:
            length = int(length_header or 0)
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if length <= 0 or length > MAX_BODY:
            raise ValueError("invalid body length")
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise ValueError("content-type must be application/json")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError("incomplete body")
        try:
            data = json.loads(raw.decode("utf-8", errors="strict"))
        except UnicodeDecodeError as exc:
            raise ValueError("body must be valid UTF-8") from exc
        if not isinstance(data, dict):
            raise ValueError("body must be a JSON object")
        return data

    def do_OPTIONS(self):
        self._json(405, {"status": "METHOD_NOT_ALLOWED"})

    def do_GET(self):
        request_id = uuid.uuid4().hex
        path = urlsplit(self.path).path
        scope = PATH_SCOPES.get(path)
        if scope is None:
            self._json(404, {"status": "NOT_FOUND", "request_id": request_id})
            return
        consumer = self._require(scope)
        if not consumer:
            return
        if path == "/v1/health":
            self._json(200, {"status": "OK", "service": "pulse-search",
                             "api_version": VERSION, "request_id": request_id,
                             "time_utc": now_iso(), "consumer": consumer.name})
            return
        if path == "/v1/capabilities":
            self._json(200, {
                "status": "OK", "api_version": VERSION, "request_id": request_id,
                "consumer": consumer.name, "scopes": sorted(consumer.scopes),
                "capabilities": {"local_index": True,
                                 "ephemeral_provider": self.server.discovery.configured,
                                 "provider_leads_separate": True,
                                 "live_weather": False,
                                 "wiki_candidates": self.server.wiki is not None,
                                 "languages": ["en", "de"], "max_results": 20},
                "endpoints": ["POST /v1/search", "POST /v1/answer",
                              "POST /v1/wiki-candidates"],
                "notices": ["Read-only local index. Temporary provider leads are separate and unverified.",
                            "Wiki candidates are drafts only; this service has no publish endpoint."],
            })
            return
        self._json(404, {"status": "NOT_FOUND", "request_id": request_id})

    def do_POST(self):
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        path = urlsplit(self.path).path
        scope = PATH_SCOPES.get(path)
        if scope is None:
            self._json(404, {"status": "NOT_FOUND", "request_id": request_id})
            return
        consumer = self._require(scope)
        if not consumer:
            return
        allowed, retry = self.server.limiter.allow(consumer.name)
        if not allowed:
            self._json(429, {"status": "RATE_LIMITED", "request_id": request_id,
                             "retry_after_s": retry}, {"Retry-After": str(retry)})
            return
        try:
            payload = self._body()
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"status": "BAD_REQUEST", "error": str(exc),
                             "request_id": request_id})
            return
        try:
            if path == "/v1/search":
                response = self._search(payload, request_id)
            elif path == "/v1/answer":
                response = self._answer(payload, request_id)
            elif path == "/v1/wiki-candidates":
                response = self._wiki(payload, request_id, consumer)
            else:
                self._json(404, {"status": "NOT_FOUND", "request_id": request_id})
                return
        except ForbiddenScope as exc:
            self._json(403, {"status": "FORBIDDEN", "required_scope": exc.required,
                             "request_id": request_id})
            return
        except (ValueError, WikiError, privacy.PrivacyError) as exc:
            self._json(422, {"status": "INVALID_REQUEST", "error": str(exc),
                             "request_id": request_id})
            return
        response["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        self._json(200, response)

    def _search(self, payload: dict, request_id: str) -> dict:
        clean = privacy.public_search(payload)
        query = clean["query"].strip()
        if not query or len(query) > MAX_QUERY:
            raise ValueError(f"query must be 1..{MAX_QUERY} characters")
        limit = max(1, min(int(clean["limit"]), 20))
        index = self.server.open_index()
        try:
            result = search_staging(index, query, limit=limit, enforce_support=True)
        finally:
            index.close()
        leads = self.server.discovery.search(query, limit=5)
        result.update({"request_id": request_id, "retrieved_at": now_iso(),
                       "source_ids": sorted({r.get("source_id") or "" for r in
                                             result.get("results", []) if r.get("source_id")}),
                       "source_receipts": source_receipts(result.get("results", [])),
                       "result_types": result_types(result),
                       "unverified_leads": leads,
                       "result_cards": result.get("results", [])})
        return result

    def _answer(self, payload: dict, request_id: str) -> dict:
        question = privacy.public_answer(payload)["question"].strip()
        if not question or len(question) > MAX_QUERY:
            raise ValueError(f"question must be 1..{MAX_QUERY} characters")
        index = self.server.open_index()
        try:
            service = AnswerService(index, self.server.pack)
            answer = service.answer(question).as_dict()
        finally:
            index.close()
        citations = []
        for item in answer["citations"]:
            enriched = dict(item)
            enriched["evidence_id"] = "ev-" + hashlib.sha256(
                str(item.get("url") or "").encode()).hexdigest()[:12]
            citations.append(enriched)
        return {"status": answer["status"], "response_mode": response_mode(answer["status"]),
                "answer": answer["answer"], "intent": answer["intent"],
                "claim_evidence": claim_evidence(answer["answer"], citations),
                "citations": citations, "freshness": answer["freshness"],
                "confidence": answer["confidence"], "limits": answer["limits"],
                "notices": answer["limits"], "request_id": request_id,
                "retrieved_at": now_iso()}

    def _wiki(self, payload: dict, request_id: str, consumer: Consumer) -> dict:
        if self.server.wiki is None:
            return {"status": "NOT_AVAILABLE", "request_id": request_id,
                    "notices": ["Wiki candidate workflow is not configured."]}
        if set(payload) != {"article"}:
            raise privacy.PrivacyError("wiki request must contain exactly one article object")
        article = privacy.public_article(payload["article"])
        result = self.server.wiki.propose(article)
        result.update({"status": result.get("result", "draft"), "request_id": request_id,
                       "consumer": consumer.name, "publication": "DRAFT_ONLY",
                       "notices": ["Draft proposal only. No Wiki page was published.",
                                   "Evidence must already be admitted in the source registry."]})
        return result


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", str(text or "").lower())
            if len(w) > 3}


def claim_evidence(answer_text: str, citations: list[dict]) -> list[dict]:
    """Attribute each sentence, and label text that is only navigation.

    A domain allowlist is not fact verification. Sentences that do not share
    evidence terms with a citation are explicitly marked unverified rather than
    being presented as supported by the whole answer.
    """
    text = str(answer_text or "").strip()
    if not text:
        return []
    pieces: list[str] = []
    for line in text.splitlines():
        line = line.strip().lstrip("-* ").strip()
        if not line:
            continue
        pieces.extend(re.split(r"(?<=[.!?])\s+", line))
    out = []
    for sentence in [p.strip() for p in pieces if p.strip()]:
        sentence_tokens = _tokens(sentence)
        matches = []
        for citation in citations:
            evidence_tokens = _tokens(
                f"{citation.get('title', '')} {citation.get('publisher', '')}")
            if sentence_tokens & evidence_tokens:
                matches.append(citation)
        support = "ATTRIBUTED_SENTENCE" if matches else "UNVERIFIED_TEXT"
        out.append({
            "claim": sentence,
            "support": support,
            "citation_evidence_ids": [c.get("evidence_id") for c in matches],
            "citations": matches,
        })
    return out


def source_receipts(results: list[dict]) -> list[dict]:
    """Return the provenance needed to distinguish evidence from navigation."""
    out = []
    for item in results:
        out.append({
            "url": item.get("url"), "source_id": item.get("source_id"),
            "publisher": item.get("publisher"),
            "source_kind": item.get("source_kind"),
            "rights_mode": item.get("rights_mode"),
            "fetched_at": item.get("fetched_at"),
            "verified_live": bool(item.get("verified_live", False)),
            "provenance": item.get("provenance"),
        })
    return out


def result_types(result: dict) -> list[str]:
    if result.get("results"):
        return sorted({str(item.get("source_kind") or "result") for item in result["results"]})
    return ["no_evidence"]


def response_mode(status: str) -> str:
    return {"ANSWERED": "EXTRACTIVE_ANSWER", "OFFICIAL_LINKS": "OFFICIAL_LINKS",
            "LIVE_SOURCE_REQUIRED": "CURRENT_SERVICE_HANDOFF",
            "NO_EVIDENCE": "NO_EVIDENCE", "REFUSED": "REFUSED",
            "NEEDS_CLARIFICATION": "CLARIFICATION"}.get(status, "NO_EVIDENCE")


def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalise_consumers(consumers: dict) -> dict[str, Consumer]:
    out: dict[str, Consumer] = {}
    for name, value in (consumers or {}).items():
        if isinstance(value, Consumer):
            consumer = value
        elif isinstance(value, str):
            consumer = Consumer(str(name), value,
                                frozenset({"health:read", "search:read", "answer:read"}))
        elif isinstance(value, dict):
            scopes = value.get("scopes") or ()
            if isinstance(scopes, str):
                scopes = [s.strip() for s in scopes.split(",") if s.strip()]
            unknown = set(scopes) - SCOPES - {"*"}
            if unknown:
                raise ValueError(f"unknown scopes: {', '.join(sorted(unknown))}")
            consumer = Consumer(str(name), str(value.get("token") or ""),
                                frozenset(scopes))
        else:
            raise ValueError("consumer must be a token string, dict or Consumer")
        if not consumer.token:
            raise ValueError(f"consumer {consumer.name} has no token")
        if consumer.name in out:
            raise ValueError(f"duplicate consumer {consumer.name}")
        out[consumer.name] = consumer
    if not out:
        raise ValueError("at least one API consumer is required")
    return out


def build_server(staging_path: str, tokens: dict, port: int = 8788,
                 host: str = "127.0.0.1", pack_path: str = "config/knowledge_pack.json",
                 wiki_path: str | None = None,
                 wiki_evidence_path: str | None = None,
                 discovery: SearxngDiscovery | None = None) -> ThreadingHTTPServer:
    consumers = normalise_consumers(tokens)
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError("refusing a non-loopback bind; public exposure needs a separate review")
    wiki = None
    if wiki_path and Path(wiki_path).exists():
        wiki = WikiService(WikiStore(wiki_path, create=False),
                           evidence_path=wiki_evidence_path)
    pack = load_pack(pack_path)
    server = ThreadingHTTPServer((host, port), _Handler)
    server.daemon_threads = True
    server.request_queue_size = 64
    server.consumers = consumers
    server.limiter = RateLimiter()
    server.wiki = wiki
    server.pack = pack
    server.discovery = discovery or SearxngDiscovery(None)
    server.staging_path = staging_path
    server.open_index = lambda: ReadOnlyIndex(staging_path)
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pulse Search read-only API")
    parser.add_argument("--staging", required=True)
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--token", default=os.environ.get("PULSE_API_TOKEN", ""),
                        help="bearer token; prefer PULSE_API_TOKEN over argv")
    parser.add_argument("--consumer", default="puke")
    parser.add_argument("--scopes", default="health:read,search:read,answer:read",
                        help="comma-separated scopes; add wiki:propose for draft creation")
    parser.add_argument("--wiki", default=None,
                        help="local Wiki workflow database (draft-only API)")
    parser.add_argument("--knowledge", default="config/knowledge_pack.json")
    args = parser.parse_args(argv)
    if not args.token:
        parser.error("set PULSE_API_TOKEN or pass --token; unauthenticated mode is not supported")
    scopes = frozenset(s.strip() for s in args.scopes.split(",") if s.strip())
    unknown = scopes - SCOPES - {"*"}
    if unknown:
        parser.error(f"unknown scopes: {', '.join(sorted(unknown))}")
    discovery = None
    if os.environ.get("PULSE_SEARXNG_URL"):
        discovery = SearxngDiscovery(os.environ["PULSE_SEARXNG_URL"])
    server = build_server(
        args.staging,
        {args.consumer: Consumer(args.consumer, args.token, scopes)},
        args.port, pack_path=args.knowledge, wiki_path=args.wiki,
        discovery=discovery)
    print(f"pulse-search api: http://127.0.0.1:{args.port}/v1/health (consumer={args.consumer})",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
