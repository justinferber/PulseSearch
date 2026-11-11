"""M8 source, provenance and discovery-boundary checks."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pulse_search_broad_r3a3g.discovery import SearxngDiscovery
from pulse_search_broad_r3a3g.search import search_documents
from pulse_search_crawler_r3a3f.safe_fetch import FetchResult
from pulse_search_crawler_r3a3f.staging import StagingIndex
from tools.r3a3g_capture_real_sources import CapturePolicy

ROOT = Path(__file__).resolve().parents[1]


class M8Tests(unittest.TestCase):
    def test_provider_is_honestly_not_configured(self):
        result = SearxngDiscovery(None).search("Hamburg HVV tickets")
        self.assertEqual(result["status"], "NOT_CONFIGURED")
        self.assertTrue(result["verified"] is False)
        self.assertEqual(result["leads"], [])

    def test_remote_provider_is_rejected(self):
        with self.assertRaises(ValueError):
            SearxngDiscovery("https://search.example.com")

    def test_provider_does_not_follow_redirects(self):
        hits = []

        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(302)
                self.send_header("Location", "http://example.com/escaped")
                self.end_headers()

            def log_message(self, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            result = SearxngDiscovery(f"http://127.0.0.1:{server.server_address[1]}").search("test")
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(len(hits), 1)

    def test_capture_attempt_ceiling_issues_no_request(self):
        class FakeFetcher:
            calls = 0

            def fetch(self, *args, **kwargs):
                self.calls += 1
                return FetchResult(args[0], args[0], status=200)

        policy = CapturePolicy({"id": "test", "url": "https://www.example.test/",
                                "approved": True, "approval_ref": "FB2-M9",
                                "rights": "public_metadata_and_short_snippet"})
        policy.attempts = 8
        fake = FakeFetcher()
        result = policy.paced_fetch(fake, "https://www.example.test/", max_bytes=1,
                                    user_agent="test")
        self.assertEqual(result.error, "capture_attempt_ceiling")
        self.assertEqual(fake.calls, 0)

    def test_curator_metadata_is_not_returned_as_page_excerpt(self):
        docs = [{"url": "https://www.example.test/tate-access", "title": "Accessibility",
                 "snippet": "Step-free routes and accessible entrances are available.",
                 "source_id": "tate", "metadata": '{"topics": ["museum", "wheelchair"]}',
                 "source_authority": "official", "document_type": "how_to",
                 "specificity": "specific"}]
        result = search_documents(docs, "museum wheelchair")
        self.assertEqual(result["status"], "staging_results")
        card = result["results"][0]
        self.assertIn("Step-free", card["snippet"])
        self.assertNotIn("museum", card["snippet"].lower())
        self.assertEqual(card["metadata"]["topics"], ["museum", "wheelchair"])
        self.assertEqual(card["metadata_source"], "curator_assigned")
        self.assertEqual(card["support_basis"], "metadata_assisted")
        self.assertEqual(card["evidence_class"], "curator_metadata_navigation")
        self.assertEqual(card["source_kind"], "curator_metadata_navigation")
        self.assertFalse(card["verified_fact"])

    def test_source_manifest_has_rights_and_specific_pages(self):
        manifest = json.loads((ROOT / "config/m8_sources.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(manifest["sources"]), 10)
        for source in manifest["sources"]:
            self.assertEqual(source["rights"], "public_metadata_and_short_snippet")
            self.assertTrue(source["approved"])
            self.assertTrue(source["approval_ref"])
            self.assertIn(source["jurisdiction"], ("DE", "GB", "FR"))

    def test_index_preserves_m8_metadata_and_revocation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            index = StagingIndex(Path(tmp) / "staging.sqlite")
            record = {
                "url": "https://www.example.test/page", "source_id": "m8-test",
                "title": "Specific page", "snippet": "Hamburg transport tickets",
                "category": "Other", "category_confidence": 0.9, "categories": ["Other"],
                "depth": 1, "fetched_at": "2026-11-11T18:00:00+00:00",
                "content_hash": "m8-test", "rights_mode": "public_metadata_and_short_snippet",
                "source_authority": "official", "document_type": "transport_ticket_guide",
                "language": "en", "jurisdiction": "DE", "specificity": "specific",
                "metadata": '{"topics":["transport"],"jurisdiction":"DE"}',
                "provenance": '{"approval_ref":"FB2-M8"}',
            }
            self.assertEqual(index.add_document(record, [], index_allowed=True),
                             (True, "indexed"))
            row = index.get(record["url"])
            self.assertEqual(row["jurisdiction"], "DE")
            self.assertEqual(row["document_type"], "transport_ticket_guide")
            self.assertEqual(json.loads(row["metadata"]), {"topics": ["transport"],
                                                         "jurisdiction": "DE"})
            # A refresh must replace rights and source identity, not retain
            # stale approval from an earlier capture.
            refreshed = {**record, "source_id": "m8-test-v2",
                         "rights_mode": "evaluation_metadata_only",
                         "provenance": '{"approval_ref":"FB2-M9"}'}
            self.assertEqual(index.add_document(refreshed, [], index_allowed=True),
                             (True, "updated"))
            row = index.get(record["url"])
            self.assertEqual(row["source_id"], "m8-test-v2")
            self.assertEqual(row["rights_mode"], "evaluation_metadata_only")
            self.assertEqual(row["provenance"], '{"approval_ref":"FB2-M9"}')
            self.assertTrue(index.revoke(record["url"], "test"))
            self.assertEqual(index.get(record["url"])["revoked"], 1)
            self.assertEqual(index.get(record["url"])["revoked_reason"], "test")
            blocked = index.add_document(record, [], index_allowed=True)
            self.assertEqual(blocked, (False, "revoked_requires_explicit_admission"))
            self.assertEqual(index.get(record["url"])["revoked"], 1)
            reactivated = {**record, "rights_mode": "evaluation_metadata_only"}
            admitted = index.add_document(reactivated, [], index_allowed=True,
                                          allow_reactivation=True)
            self.assertEqual(admitted, (True, "updated"))
            self.assertEqual(index.get(record["url"])["revoked"], 0)
            self.assertEqual(index.get(record["url"])["rights_mode"],
                             "evaluation_metadata_only")
            index.close()

    def test_m8_questions_are_new_and_frozen(self):
        m8 = json.loads((ROOT / "config/m8_questions.json").read_text(encoding="utf-8"))
        old = set()
        for name in ("m6_relevance.json", "m7_unseen_questions.json"):
            data = json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))
            old.update(q["query"].strip().lower() for q in data["queries"])
        new = {q["query"].strip().lower() for q in m8["queries"]}
        self.assertGreaterEqual(len(new), 20)
        self.assertFalse(new & old)


if __name__ == "__main__":
    unittest.main()
