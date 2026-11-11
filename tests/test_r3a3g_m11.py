"""M11 regressions from the four poor M10 API searches, using admitted sources."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pulse_search_broad_r3a3g.answers import NAVIGATION_ONLY, AnswerService
from pulse_search_broad_r3a3g.search import search_staging
from pulse_search_crawler_r3a3f.staging import StagingIndex
from tools.r3a3g_m8_demo import build_index


class M11RealQueryRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        path = Path(cls.tmp.name) / "staging.sqlite"
        build_index(path)
        cls.index = StagingIndex(path)

    @classmethod
    def tearDownClass(cls):
        cls.index.close()
        cls.tmp.cleanup()

    def search(self, query: str) -> dict:
        return search_staging(self.index, query, limit=5, enforce_support=True)

    def urls(self, result: dict) -> list[str]:
        return [str(item.get("url") or "") for item in result.get("results") or []]

    def test_berlin_museum_hours_do_not_return_christmas_markets(self):
        result = self.search("Berlin museum opening hours")
        self.assertEqual(result["status"], "official_links")
        self.assertTrue(any("berlin.de/en/museums" in url for url in self.urls(result)))
        self.assertFalse(any("christmas" in url.lower() for url in self.urls(result)))

    def test_london_museum_access_does_not_return_theatre_pages(self):
        result = self.search("London museum wheelchair access")
        urls = self.urls(result)
        self.assertTrue(urls)
        self.assertTrue(all("tate.org.uk" in url for url in urls), urls)

    def test_german_refund_question_does_not_return_uk_consumer_guidance(self):
        result = self.search("Can I refund concert tickets in Germany?")
        urls = self.urls(result)
        self.assertTrue(any("verbraucherzentrale.de" in url for url in urls), urls)
        self.assertFalse(any("gov.uk" in url for url in urls), urls)

    def test_nhs_111_is_an_official_entry_point(self):
        result = self.search("When should I call NHS 111?")
        self.assertEqual(result["status"], "official_links")
        self.assertEqual(self.urls(result)[0], "https://111.nhs.uk/")

    def test_hamburg_transport_does_not_return_a_berlin_market(self):
        result = self.search("Hamburg public transport tickets")
        urls = self.urls(result)
        self.assertTrue(any("hvv.de" in url for url in urls), urls)
        self.assertFalse(any("visitberlin.de" in url for url in urls), urls)

    def test_passport_answer_has_no_unrelated_secondary_cards(self):
        result = self.search("How do I renew a UK passport?")
        urls = self.urls(result)
        self.assertEqual(urls[0], "https://www.gov.uk/apply-renew-passport")
        for marker in ("consumer-protection", "tate.org.uk", "tfl.gov.uk",
                       "glastonburyfestivals"):
            self.assertFalse(any(marker in url for url in urls), (marker, urls))

    def test_answer_layer_does_not_quote_metadata_navigation(self):
        service = AnswerService(
            self.index, {"version": "m11-test",
                         "policy": {"trusted_hosts": ["tate.org.uk"]}})
        answer = service.answer("London museum wheelchair access")
        self.assertEqual(answer.status, NAVIGATION_ONLY)
        self.assertFalse(answer.answer.startswith("From the indexed page"))
        self.assertTrue(all(c.kind == "indexed_navigation" for c in answer.citations))


if __name__ == "__main__":
    unittest.main()
