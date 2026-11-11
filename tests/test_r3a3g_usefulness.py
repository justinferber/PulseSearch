"""Regression coverage for practical official-service handoffs."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from pulse_search_broad_r3a3g.official import links_for
from pulse_search_broad_r3a3g.search import search_documents

ROOT = Path(__file__).resolve().parents[1]


def tour(title, snippet):
    return {
        "url": "https://example.test/unrelated",
        "title": title,
        "snippet": snippet,
        "source_id": "offline-fixture",
        "fetched_at": "2026-11-11T00:00:00Z",
        "source_authority": "official",
    }


class OfficialHandoffTests(unittest.TestCase):
    def test_accessibility_prioritises_venue_access_pages_not_ticket_seller(self):
        cards = links_for("how_to", "Berlin concert venue accessibility and bag rules",
                          city="Berlin", country="DE")
        self.assertTrue(cards)
        self.assertIn(cards[0]["url"], (
            "https://www.mercedes-benz-arena.de/",
            "https://www.columbiahalle.de/",
            "https://www.huxleys-neue-welt.de/",
            "https://www.verti-music-hall.de/"))
        self.assertNotIn("eventim", cards[0]["url"])

    def test_christmas_transport_starts_with_berlin_operator(self):
        cards = links_for("transport", "Berlin Christmas market public transport",
                          city="Berlin", country="DE")
        self.assertIn("bvg.de", cards[0]["url"])

    def test_pride_and_festival_queries_start_with_organiser_or_city_calendar(self):
        pride = links_for("events", "Berlin CSD 2027 dates", city="Berlin", country="DE")
        music = links_for("events", "Berlin music festivals", city="Berlin", country="DE")
        self.assertIn("csd-berlin.de", pride[0]["url"])
        self.assertIn("berlin.de", music[0]["url"])

    def test_weak_admitted_page_is_replaced_by_official_handoff(self):
        response = search_documents(
            [tour("CSD Berlin", "Christopher Street Day information")],
            "Berlin concert venue accessibility and bag rules",
            enforce_support=True,
        )
        self.assertEqual(response["status"], "official_links")
        self.assertEqual(response["response_mode"], "OFFICIAL_LINKS")
        self.assertTrue(response["official_links"])
        self.assertNotIn("csd-berlin.de", response["official_links"][0]["url"])

    def test_benchmark_has_no_unrelated_top_result(self):
        report = json.loads((ROOT / "docs/evidence/r3a3g_usefulness_benchmark.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["cases"], 8)
        self.assertEqual(report["summary"]["passed"], 8)
        self.assertEqual(report["summary"]["unrelated_top_result"], 0)
        for case in report["cases"]:
            self.assertTrue(case["top_result_matches_expected"], case["case_id"])


if __name__ == "__main__":
    unittest.main()
