"""M8 source, provenance and discovery-boundary checks."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pulse_search_broad_r3a3g.discovery import SearxngDiscovery
from pulse_search_crawler_r3a3f.staging import StagingIndex

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
                "provenance": '{"approval_ref":"FB2-M8"}',
            }
            self.assertEqual(index.add_document(record, [], index_allowed=True),
                             (True, "indexed"))
            row = index.get(record["url"])
            self.assertEqual(row["jurisdiction"], "DE")
            self.assertEqual(row["document_type"], "transport_ticket_guide")
            self.assertTrue(index.revoke(record["url"], "test"))
            self.assertEqual(index.get(record["url"])["revoked"], 1)
            self.assertEqual(index.get(record["url"])["revoked_reason"], "test")
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
