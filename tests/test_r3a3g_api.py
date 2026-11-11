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

from pulse_search_broad_r3a3g.api import RateLimiter, build_server  # noqa: E402
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402
from pulse_search_broad_r3a3g.wiki import WikiService, WikiStore  # noqa: E402

TOKEN = "test-token-not-a-secret"


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
        WikiService(wiki).propose({
            "topic_id": "api-draft", "title": "API draft topic", "summary": "Summary",
            "claims": [{"text": "A neutral sourced claim.", "sources": [
                "https://www.bbc.co.uk/weather", "https://weather.metoffice.gov.uk/forecast/uk"]}],
            "verified_at": "2026-11-11",
        })
        wiki.close()
        cls.server = build_server(str(cls.tmp / "staging.sqlite"), {"puke": TOKEN},
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
                     "Content-Type": "application/json"})
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
        article = {"topic_id": "new-api-topic", "title": "New API topic",
                   "summary": "A sourced draft.",
                   "claims": [{"text": "Use official forecast services.",
                               "sources": ["https://www.bbc.co.uk/weather",
                                           "https://weather.metoffice.gov.uk/forecast/uk"]}],
                   "verified_at": "2026-11-11"}
        status, body, _ = self.request("/v1/wiki-candidates", {"article": article})
        self.assertEqual(status, 200)
        self.assertIn(body["status"], ("draft_created", "duplicate"))
        self.assertEqual(body["publication"], "DRAFT_ONLY")

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

    def test_capabilities_and_no_cors_by_default(self):
        status, body, headers = self.request("/v1/capabilities")
        self.assertEqual(status, 200)
        self.assertTrue(body["capabilities"]["local_index"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)


if __name__ == "__main__":
    unittest.main()
