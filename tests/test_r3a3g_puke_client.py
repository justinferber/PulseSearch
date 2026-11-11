"""Separate-client contract: statuses, provenance, no member context."""

from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_broad_r3a3g.api import Consumer, build_server  # noqa: E402
from pulse_search_broad_r3a3g.client import PulseSearchClient, PulseSearchError  # noqa: E402
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402

TOKEN = "puke-client-test-token"


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="puke-client-test-"))
        staging = StagingIndex(cls.tmp / "staging.sqlite")
        staging.add_document({
            "url": "https://www.csd-berlin.de/", "source_id": "csd",
            "title": "CSD Berlin", "snippet": "CSD Berlin route, dates and accessibility.",
            "category": "Other", "category_confidence": 0.9, "categories": ["Other"],
            "depth": 1, "fetched_at": "2026-11-11T10:00:00+00:00",
            "content_hash": "puke-csd", "source_authority": "official",
        }, [], index_allowed=True)
        staging.close()
        cls.server = build_server(
            str(cls.tmp / "staging.sqlite"),
            {"puke": Consumer("puke", TOKEN, frozenset({
                "health:read", "search:read", "answer:read"}))},
            port=0)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_client_health_and_capabilities(self):
        client = PulseSearchClient(self.base, TOKEN)
        self.assertEqual(client.health()["status"], "OK")
        caps = client.capabilities()
        self.assertTrue(caps["capabilities"]["local_index"])

    def test_client_returns_links_or_explicit_no_evidence(self):
        client = PulseSearchClient(self.base, TOKEN)
        hit = client.search("CSD Berlin route")
        self.assertEqual(hit["status"], "staging_results")
        self.assertTrue(hit["result_cards"])
        miss = client.answer("When is the Moon Parade?")
        self.assertEqual(miss.status, "NO_EVIDENCE")
        self.assertFalse(miss.has_evidence)

    def test_remote_origin_requires_explicit_opt_in(self):
        with self.assertRaises(ValueError):
            PulseSearchClient("https://search.example.com", TOKEN)
        client = PulseSearchClient("https://search.example.com", TOKEN, allow_remote=True)
        self.assertEqual(client.base_url, "https://search.example.com")

    def test_member_context_is_blocked_client_side(self):
        client = PulseSearchClient(self.base, TOKEN)
        with self.assertRaises(ValueError):
            client._call("/v1/answer", {"question": "x", "member_context": "secret"})

    def test_nested_member_material_and_pii_are_blocked(self):
        client = PulseSearchClient(self.base, TOKEN)
        with self.assertRaises(ValueError):
            client._call("/v1/answer", {"question": {"member_context": "secret"}})
        with self.assertRaises(ValueError):
            client.wiki_candidate({
                "topic_id": "x", "title": "x", "summary": "x", "verified_at": "2026-11-11",
                "claims": [{"text": "Contact person@example.com", "evidence": ["ev-x"],
                            "fact_id": "fact-x"}]})

    def test_bad_token_is_reported(self):
        client = PulseSearchClient(self.base, "wrong")
        with self.assertRaises(PulseSearchError) as context:
            client.health()
        self.assertEqual(context.exception.status, 401)


if __name__ == "__main__":
    unittest.main()
