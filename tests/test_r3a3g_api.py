"""Versioned API: auth, limits, schema, provenance and draft-only Wiki."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_broad_r3a3g.api import Consumer, RateLimiter, build_server  # noqa: E402
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402
from pulse_search_broad_r3a3g.wiki import WikiService, WikiStore  # noqa: E402

TOKEN = "test-token-not-a-secret"
ARTICLES = json.loads((ROOT / "config/wiki_articles.json").read_text(encoding="utf-8"))["articles"]


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="r3a3g-api-"))
        staging = StagingIndex(cls.tmp / "staging.sqlite")
        staging.add_document({
            "url": "https://pulseunity.co/knowledge", "source_id": "fixture",
            "title": "Pulse UNITY Knowledge Engine",
            "snippet": "The knowledge engine answers questions from curated sources.",
            "category": "Other", "category_confidence": 0.8, "categories": ["Other"],
            "depth": 1, "fetched_at": "2026-11-11T10:00:00+00:00",
            "content_hash": "fixture-api",
        }, [], index_allowed=True)
        staging.close()
        wiki = WikiStore(cls.tmp / "wiki.sqlite")
        WikiService(wiki).propose(ARTICLES[0])
        wiki.close()
        cls.search_token = "search-only-token"
        cls.server = build_server(
            str(cls.tmp / "staging.sqlite"),
            {"puke": Consumer("puke", TOKEN, frozenset({
                "health:read", "search:read", "answer:read", "wiki:propose"})),
             "search-only": Consumer("search-only", cls.search_token,
                                     frozenset({"search:read"}))},
            port=0, wiki_path=str(cls.tmp / "wiki.sqlite"))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def request(self, path, payload=None, token=TOKEN, method=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.base + path, data=data, method=method or ("POST" if data else "GET"),
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json",
                     "Connection": "close"})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.load(response), dict(response.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read()), dict(exc.headers)

    def test_health_requires_a_bearer_token(self):
        status, body, _ = self.request("/v1/health", token="wrong")
        self.assertEqual(status, 401)
        self.assertEqual(body["status"], "UNAUTHENTICATED")

    def test_search_returns_cards_and_request_id(self):
        status, body, _ = self.request("/v1/search", {"query": "knowledge engine"})
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "staging_results")
        self.assertTrue(body["result_cards"])
        self.assertTrue(body["request_id"])
        self.assertIn("retrieved_at", body)
        self.assertIn("source_ids", body)

    def test_answer_has_claim_evidence_and_citations(self):
        status, body, _ = self.request(
            "/v1/answer", {"question": "When is Glastonbury on next year?"})
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ANSWERED")
        self.assertTrue(body["claim_evidence"])
        self.assertTrue(body["citations"])
        self.assertIn("request_id", body)

    def test_weather_is_official_handoff_without_live_value(self):
        status, body, _ = self.request(
            "/v1/answer", {"question": "What is the weather in London tomorrow?"})
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "OFFICIAL_LINKS")
        self.assertEqual(body["response_mode"], "OFFICIAL_LINKS")
        self.assertNotIn("°C", body["answer"])

    def test_wiki_candidates_are_draft_only(self):
        status, body, _ = self.request("/v1/wiki-candidates", {"article": ARTICLES[0]})
        self.assertEqual(status, 200)
        self.assertIn(body["status"], ("draft_created", "duplicate", "update_draft"))
        self.assertEqual(body["publication"], "DRAFT_ONLY")

    def test_nested_member_context_is_rejected_at_service_boundary(self):
        article = dict(ARTICLES[0])
        article["claims"] = [dict(claim) for claim in article["claims"]]
        article["claims"][0]["member_context"] = "private"
        status, body, _ = self.request("/v1/wiki-candidates", {"article": article})
        self.assertEqual(status, 422)
        self.assertNotIn("secret", json.dumps(body))

    def test_unknown_search_fields_are_rejected(self):
        status, _, _ = self.request("/v1/search", {"query": "Berlin", "context": {"user": "x"}})
        self.assertEqual(status, 422)

    def test_invalid_queries_and_bodies_are_rejected(self):
        status, _, _ = self.request("/v1/search", {"query": ""})
        self.assertEqual(status, 422)
        status, _, _ = self.request("/v1/search", {"query": "x" * 401})
        self.assertEqual(status, 422)
        status, body, _ = self.request("/v1/wiki-candidates", {"topic_id": "bad",
                                                             "title": "Bad"})
        self.assertEqual(status, 422)

    def test_rate_limit_is_per_consumer(self):
        original = self.server.limiter
        self.server.limiter = RateLimiter(limit=2, window_s=60)
        try:
            self.assertEqual(self.request("/v1/search", {"query": "one"})[0], 200)
            self.assertEqual(self.request("/v1/search", {"query": "two"})[0], 200)
            status, body, headers = self.request("/v1/search", {"query": "three"})
            self.assertEqual(status, 429)
            self.assertEqual(body["status"], "RATE_LIMITED")
            self.assertIn("Retry-After", headers)
        finally:
            self.server.limiter = original

    def test_scope_denies_wiki_write_for_search_only_token(self):
        article = {"topic_id": "guide-berlin-concert-tickets", "title": "Blocked",
                   "claims": [{"text": "Start at the Berlin events calendar.",
                               "evidence": ["ev-berlin-events"]}]}
        status, body, _ = self.request("/v1/wiki-candidates", {"article": article},
                                       token=self.search_token)
        self.assertEqual(status, 403)
        self.assertEqual(body["required_scope"], "wiki:propose")
        status, _, _ = self.request("/v1/answer", {"question": "Glastonbury dates?"},
                                    token=self.search_token)
        self.assertEqual(status, 403)

    def test_answer_claim_evidence_is_sentence_level(self):
        status, body, _ = self.request(
            "/v1/answer", {"question": "When is Glastonbury on next year?"})
        self.assertEqual(status, 200)
        self.assertTrue(body["claim_evidence"])
        self.assertTrue(all("support" in item for item in body["claim_evidence"]))
        self.assertNotEqual(body["claim_evidence"][0]["claim"], body["answer"])

    def test_invalid_utf8_is_rejected(self):
        import socket
        sock = socket.create_connection(("127.0.0.1", self.server.server_address[1]), 5)
        body = b"{\"query\": \"\xff\"}"
        sock.sendall(("POST /v1/search HTTP/1.1\r\nHost: localhost\r\n"
                      f"Authorization: Bearer {TOKEN}\r\nContent-Type: application/json\r\n"
                      f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode()
                     + body)
        response = sock.recv(4096)
        sock.close()
        self.assertIn(b" 400 ", response)

    def test_capabilities_and_no_cors_by_default(self):
        status, body, headers = self.request("/v1/capabilities")
        self.assertEqual(status, 200)
        self.assertTrue(body["capabilities"]["local_index"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)


if __name__ == "__main__":
    unittest.main()
