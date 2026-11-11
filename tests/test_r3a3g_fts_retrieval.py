"""Real SQLite FTS5 integration tests for broad search, no network requests."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from pulse_search_broad_r3a3g.search import search_staging
from pulse_search_crawler_r3a3f.staging import StagingIndex


class IndexedCandidateTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="r3a3g-index-"))
        self.db = StagingIndex(self.folder / "staging.sqlite")

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.folder, ignore_errors=True)

    def add(self, n, title, snippet, *, category="Other"):
        url = f"https://approved-fixture.example.org/doc{n}"
        indexed, reason = self.db.add_document({
            "url": url,
            "source_id": "owner-approved-synthetic-fixture",
            "title": title, "snippet": snippet, "category": category,
            "category_confidence": 0.8,
            "categories": [category], "depth": 1,
            "fetched_at": "2026-11-11T10:00:00+00:00",
            "content_hash": f"fixture-{n}",
        }, [], index_allowed=True)
        self.assertTrue(indexed, reason)
        return url

    def test_late_documents_found_beyond_scanned_prefix(self):
        for i in range(24):
            self.add(i, f"General reference document {i}",
                     "Background on public facilities and guides.")
        useful = self.add(
            25, "How to book concert tickets in Berlin",
            "Official booking guide for Berlin music venue; buy concert tickets and check the show date.",
        )
        response = search_staging(
            self.db, "How do I book concert tickets in Berlin?", scan_limit=5
        )
        if self.db.fts:
            self.assertEqual(response["retrieval_mode"], "fts_candidates")
            self.assertEqual(response["results"][0]["url"], useful)
        else:
            self.assertEqual(response["retrieval_mode"], "bounded_scan")

    def test_revocation_removes_results(self):
        url = self.add(
            30, "Berlin Pride Festival 2027",
            "Official Pride programme in Berlin with accessibility notes",
            category="Pride & Community",
        )
        self.assertTrue(any(r["url"] == url for r in search_staging(self.db, "Berlin Pride")["results"]))
        self.assertTrue(self.db.revoke(url, "rights_withdrawn"))
        self.assertFalse(any(r["url"] == url for r in search_staging(self.db, "Berlin Pride")["results"]))

    def test_evergreen_page_retrieved_without_event_date(self):
        url = self.add(31, "Public transport ticket instructions in Berlin",
                       "How to use trains and metro ticket machines for venue travel.")
        result = search_staging(self.db, "Berlin public transport ticket instructions")
        self.assertEqual(result["results"][0]["url"], url)
        self.assertEqual(result["results"][0]["document_type"], "transport_guide")


if __name__ == "__main__":
    unittest.main()
