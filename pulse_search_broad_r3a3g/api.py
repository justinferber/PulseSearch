"""Versioned, read-only Pulse Search API for PUKE and other authorised clients.

Security defaults: loopback bind, mandatory bearer token, per-consumer rate
limit, bounded JSON bodies, no CORS, no query text in logs, no store writes
except the separate Wiki workflow store. The public internet must not reach
this service before an independent security review.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlsplit

from .answers import AnswerService, load_pack
from .search import search_staging
from .wiki import WikiError, WikiService, WikiStore, WikiPolicy

MAX_BODY = 16_384
MAX_QUERY = 400
VERSION = "1.0"


class ReadOnlyIndex:
    def __init__(self, path: str):
        target = Path(path).resolve(strict=True)
        self.conn = sqlite3.connect("file:" + quote(str(target), safe="/:") + "?mode=ro",
                                    uri=True)
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
        self.events = defaultdict(deque)

    def allow(self, consumer: str) -> tuple[bool, int]:
        now = time.monotonic()
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
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def _unauthenticated(self, message: str):
        self._json(401, {"status": "UNAUTHENTICATED", "error": message}, {"WWW-Authenticate": "Bearer"})

    def _consumer(self) -> str | None:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        supplied = header[7:].strip()
        if not supplied:
            return None
        for consumer, token in self.server.tokens.items():
            if hmac.compare_digest(supplied, token):
                return consumer
        return None

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            raise ValueError("invalid body length")
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            raise ValueError("content-type must be application/json")
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("body must be a JSON object")
        return data

    def do_OPTIONS(self):
        self._json(405, {"status": "METHOD_NOT_ALLOWED"})

    def do_GET(self):
        request_id = uuid.uuid4().hex
        consumer = self._consumer()
        if not consumer:
            self._unauthenticated("bearer token required")
            return
        path = urlsplit(self.path).path
        if path == "/v1/health":
            self._json(200, {"status": "OK", "service": "pulse-search", "api_version": VERSION,
                             "request_id": request_id, "time_utc": now_iso()})
            return
        if path == "/v1/capabilities":
            self._json(200, {
                "status": "OK", "api_version": VERSION, "request_id": request_id,
                "capabilities": {"local_index": True, "ephemeral_provider": False,
                                 "live_weather": False, "wiki_candidates": self.server.wiki is not None,
                                 "languages": ["en", "de"], "max_results": 20},
                "endpoints": ["POST /v1/search", "POST /v1/answer", "POST /v1/wiki-candidates"],
                "notices": ["Read-only local index. No public web search or paid provider is enabled."],
            })
            return
        self._json(404, {"status": "NOT_FOUND", "request_id": request_id})

    def do_POST(self):
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        consumer = self._consumer()
        if not consumer:
            self._unauthenticated("bearer token required")
            return
        allowed, retry = self.server.limiter.allow(consumer)
        if not allowed:
            self._json(429, {"status": "RATE_LIMITED", "request_id": request_id,
                             "retry_after_s": retry}, {"Retry-After": str(retry)})
            return
        path = urlsplit(self.path).path
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
        except (ValueError, WikiError) as exc:
            self._json(422, {"status": "INVALID_REQUEST", "error": str(exc),
                             "request_id": request_id})
            return
        response["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        self._json(200, response)

    def _search(self, payload: dict, request_id: str) -> dict:
        query = str(payload.get("query") or "").strip()
        if not query or len(query) > MAX_QUERY:
            raise ValueError(f"query must be 1..{MAX_QUERY} characters")
        limit = max(1, min(int(payload.get("limit") or 8), 20))
        index = self.server.open_index()
        try:
            result = search_staging(index, query, limit=limit)
        finally:
            index.close()
        result.update({"request_id": request_id, "retrieved_at": now_iso(),
                       "source_ids": sorted({r.get("source_id") or "" for r in
                                             result.get("results", []) if r.get("source_id")}),
                       "result_cards": result.get("results", []),
                       "consumer_context_received": bool(payload.get("consumer_context"))})
        return result

    def _answer(self, payload: dict, request_id: str) -> dict:
        question = str(payload.get("question") or "").strip()
        if not question or len(question) > MAX_QUERY:
            raise ValueError(f"question must be 1..{MAX_QUERY} characters")
        index = self.server.open_index()
        try:
            service = AnswerService(index, self.server.pack)
            answer = service.answer(question).as_dict()
        finally:
            index.close()
        return {"status": answer["status"], "response_mode": response_mode(answer["status"]),
                "answer": answer["answer"], "intent": answer["intent"],
                "claim_evidence": [{"claim": answer["answer"], "citations": answer["citations"]}],
                "citations": answer["citations"], "freshness": answer["freshness"],
                "confidence": answer["confidence"], "limits": answer["limits"],
                "notices": answer["limits"], "request_id": request_id,
                "retrieved_at": now_iso(), "context_used": bool(payload.get("context"))}

    def _wiki(self, payload: dict, request_id: str, consumer: str) -> dict:
        if self.server.wiki is None:
            return {"status": "NOT_AVAILABLE", "request_id": request_id,
                    "notices": ["Wiki candidate workflow is not configured."]}
        article = payload.get("article") if isinstance(payload.get("article"), dict) else payload
        result = self.server.wiki.propose(article)
        result.update({"status": result.get("result", "draft"), "request_id": request_id,
                       "consumer": consumer, "publication": "DRAFT_ONLY",
                       "notices": ["Draft proposal only. No Wiki page was published."]})
        return result


def response_mode(status: str) -> str:
    return {"ANSWERED": "EXTRACTIVE_ANSWER", "OFFICIAL_LINKS": "OFFICIAL_LINKS",
            "LIVE_SOURCE_REQUIRED": "CURRENT_SERVICE_HANDOFF",
            "NO_EVIDENCE": "NO_EVIDENCE", "REFUSED": "REFUSED",
            "NEEDS_CLARIFICATION": "CLARIFICATION"}.get(status, "NO_EVIDENCE")


def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_server(staging_path: str, tokens: dict[str, str], port: int = 8788,
                 host: str = "127.0.0.1", pack_path: str = "config/knowledge_pack.json",
                 wiki_path: str | None = None) -> ThreadingHTTPServer:
    if not tokens:
        raise ValueError("at least one API token is required")
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError("refusing a non-loopback bind; public exposure needs a separate review")
    wiki = WikiService(WikiStore(wiki_path, create=False)) if wiki_path and Path(wiki_path).exists() else None
    pack = load_pack(pack_path)
    server = ThreadingHTTPServer((host, port), _Handler)
    server.tokens = tokens
    server.limiter = RateLimiter()
    server.wiki = wiki
    server.pack = pack
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
    parser.add_argument("--wiki", default=None,
                        help="local Wiki workflow database (draft-only API)")
    parser.add_argument("--knowledge", default="config/knowledge_pack.json")
    args = parser.parse_args(argv)
    if not args.token:
        parser.error("set PULSE_API_TOKEN or pass --token; unauthenticated mode is not supported")
    server = build_server(args.staging, {args.consumer: args.token}, args.port,
                          pack_path=args.knowledge, wiki_path=args.wiki)
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
