#!/usr/bin/env python3
"""R3-A3E fail-before-fix constraint tests (new dev tree only).

The accepted October engine is imported read-only. These tests assert the
reproduced defects first (so a silent regression in the evidence is caught),
then assert the new constraint layer repairs them at *every* returned rank.

Runs on stdlib + the pure-Python hybrid path: no BGE weights, no torch, no
network, no owner-index writes.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[1]
SNAPSHOT = REPO / "historical" / "local_snapshot"
sys.path.insert(0, str(REPO / "tools"))

import r3a3e_constraint_layer as layer  # noqa: E402

hc = layer.load_engine(SNAPSHOT)
from hybrid_core import HybridIndex  # noqa: E402

ROWS = [
    ("/events/diwali-square-2025", "Diwali on the Square 2025"),
    ("/events/diwali-square-2026", "Diwali on the Square 2026"),
    ("/events/eid-square-2025", "Eid on the Square 2025"),
    ("/events/london-open-house-2023", "London Open House 2023"),
    ("/events/london-open-house-2024", "London Open House 2024"),
    ("/events/london-open-house-2025", "London Open House 2025"),
    ("/events/city-hall-open-house-2026", "City Hall Open House 2026"),
    ("/events/london-games-festival-2026", "London Games Festival 2026"),
    ("/events/st-patricks-festival-2026", "St Patrick's Festival 2026"),
    ("/events/pride-parade-2026", "Pride Parade 2026"),
    ("/events/london-new-years-eve-2026", "London New Year's Eve 2026"),
    ("/events/st-georges-day-2025", "St George's Day 2025"),
]


def fixture_rows():
    return [
        {
            "url": "https://www.london.gov.uk" + path,
            "title": title,
            "body": f"{title} London event page.",
            "fetched_at": "2026-10-26",
            "source_id": "london_events_p14",
            "display_mode": "metadata_only",
        }
        for path, title in ROWS
    ]


class DeclarationTests(unittest.TestCase):
    def test_engine_source_is_untouched_snapshot(self):
        self.assertTrue((SNAPSHOT / "Pulse_Search_R3A2R2_20261026" / "accepted_hybrid" / "hybrid_core.py").is_file())

    def test_decomposition_reads_other_than(self):
        d = layer.decompose(hc, "Find London events in 2025 other than Diwali on the Square")
        self.assertEqual(d.exclusions, ("Diwali on the Square",))
        self.assertEqual(d.years, ("2025",))
        self.assertNotIn("other than", d.clean_query.lower())

    def test_decomposition_keeps_all_requested_years(self):
        d = layer.decompose(hc, "London Open House editions from 2023, 2024 and 2025")
        self.assertEqual(d.years, ("2023", "2024", "2025"))
        self.assertEqual(d.phrase, ("london", "open", "house"))
        self.assertTrue(d.series_like)


class ReproducedDefectTests(unittest.TestCase):
    """The defects, demonstrated on the untouched engine with a local fixture."""

    def setUp(self):
        self.base = HybridIndex(fixture_rows())

    def test_original_diwali_query_leaks_forbidden_page(self):
        result = self.base.search("Find London events in 2025 other than Diwali on the Square", limit=10)
        urls = [r["url"] for r in result["results"]]
        self.assertTrue(any(u.endswith("/events/diwali-square-2025") for u in urls),
                        "the accepted engine is expected to leak here; if it no longer does, "
                        "re-derive the defect finding rather than deleting this test")

    def test_original_multi_year_collapses_to_last_year(self):
        result = self.base.search("What are the 2024 and 2025 London Open House editions?", limit=10)
        urls = [r["url"] for r in result["results"]]
        self.assertTrue(any(u.endswith("london-open-house-2025") for u in urls))
        self.assertFalse(any(u.endswith("london-open-house-2024") for u in urls))

    def test_original_series_admits_other_series(self):
        result = self.base.search("Past editions of London Open House", limit=10)
        urls = [r["url"] for r in result["results"]]
        self.assertTrue(any(u.endswith("city-hall-open-house-2026") for u in urls))


class RepairedBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.base = HybridIndex(fixture_rows())
        self.layer = layer.ConstrainedSearch(hc, self.base, "hybrid_constrained")

    def test_diwali_excluded_at_every_rank(self):
        result = self.layer.search("Find London events in 2025 other than Diwali on the Square", limit=10)
        urls = [r["url"] for r in result["results"]]
        self.assertTrue(urls, "other known 2025 events must remain discoverable")
        self.assertFalse(any(u.endswith("/events/diwali-square-2025") for u in urls))
        self.assertFalse(any(u.endswith("/events/diwali-square-2026") for u in urls))
        self.assertEqual(result["constraint_compliance"], "ALL_RETURNED_RANKS_PASS")
        self.assertEqual(layer.verdict("exclude_nonempty", "/events/diwali-square-2025",
                                       result["results"])[0], "PASS_RETRIEVAL")

    def test_multi_year_returns_both_editions(self):
        result = self.layer.search("What are the 2024 and 2025 London Open House editions?", limit=10)
        urls = [r["url"] for r in result["results"]]
        self.assertTrue(any(u.endswith("london-open-house-2024") for u in urls))
        self.assertTrue(any(u.endswith("london-open-house-2025") for u in urls))
        self.assertEqual(layer.verdict("all",
                                       "/events/london-open-house-2024|/events/london-open-house-2025",
                                       result["results"])[0], "PASS_RETRIEVAL")

    def test_three_editions_returned(self):
        result = self.layer.search("London Open House editions from 2023, 2024 and 2025", limit=10)
        urls = [r["url"] for r in result["results"]]
        for year in ("2023", "2024", "2025"):
            self.assertTrue(any(u.endswith(f"london-open-house-{year}") for u in urls), year)

    def test_series_excludes_different_series(self):
        result = self.layer.search("Past editions of London Open House", limit=10)
        titles = [r["title"].casefold() for r in result["results"]]
        self.assertGreaterEqual(len(titles), 2)
        self.assertTrue(all("london open house" in t for t in titles), titles)
        self.assertEqual(layer.verdict("series_many", "london open house", result["results"])[0],
                         "PASS_RETRIEVAL")

    def test_single_year_queries_still_filter_to_that_year(self):
        result = self.layer.search("Diwali on the Square 2025", limit=10)
        self.assertTrue(result["results"])
        for r in result["results"]:
            self.assertIn("2025", r["title"])

    def test_limit_and_duplicates_respected(self):
        result = self.layer.search("London Open House", limit=3)
        urls = [r["url"] for r in result["results"]]
        self.assertLessEqual(len(urls), 3)
        self.assertEqual(len(urls), len(set(urls)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
