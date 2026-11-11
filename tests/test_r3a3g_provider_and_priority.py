"""Provider is opt-in and discovery-only; no external requests in tests."""
from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlsplit

from pulse_search_broad_r3a3g.providers import SearxNG, ProviderError
from pulse_search_crawler_r3a3f import topics


class SearxProviderTests(unittest.TestCase):
    def test_service_must_be_configured_locally_by_default(self):
        with self.assertRaises(ProviderError):
            SearxNG("https://some-public-search.example.org")
        self.assertIsInstance(SearxNG("http://127.0.0.1:8080"), SearxNG)

    def test_manual_offline_transport_never_indexes_pages(self):
        observed = []

        def stub(url):
            observed.append(url)
            return {"results": [
                {"url": "https://www.berlin.de/events/listings", "title": "<b>Berlin concerts</b>",
                 "content": "Official city event <i>guide</i>"},
                {"url": "https://www.berlin.de/events/listings", "title": "Duplicate",
                 "content": "Duplicate"},
                {"url": "http://127.0.0.1:8000/private", "title": "Private", "content": ""},
                {"url": "javascript:alert(1)", "title": "Unsafe", "content": ""},
                {"url": "https://venue.example.org/tickets", "title": "Concert tickets", "content": "How to buy."},
            ]}
        adapter = SearxNG("http://127.0.0.1:8080")
        result = adapter.search("concert tickets in Berlin", transport=stub)
        self.assertEqual(result["status"], "provider_results_unverified")
        self.assertEqual(len(result["results"]), 2)
        self.assertFalse(result["results"][0]["rights_verified"])
        self.assertFalse(result["results"][0]["indexed"])
        self.assertFalse(result["results"][0]["verified_live"])
        self.assertEqual(result["results"][0]["title"], "Berlin concerts")
        params = parse_qs(urlsplit(observed[0]).query)
        self.assertEqual(params["q"][0], "concert tickets in Berlin")
        self.assertEqual(params["format"][0], "json")

    def test_invalid_provider_response_fails_closed(self):
        adapter = SearxNG("http://localhost:8888")
        with self.assertRaises(ProviderError):
            adapter.search("music festivals", transport=lambda u: {"bad": []})
        with self.assertRaises(ProviderError):
            adapter.search("x" * 301, transport=lambda u: {"results": []})


class BroadDiscoveryPrioritiesTests(unittest.TestCase):
    def test_crawler_prioritises_fireworks(self):
        self.assertEqual(topics.best_intent("Fireworks display in London")[0], "fireworks")

    def test_crawler_prioritises_booking_instructions(self):
        self.assertEqual(topics.best_intent("How to buy tickets for concerts")[0],
                         "ticketing_guides")

    def test_crawler_prioritises_venue_travel_information(self):
        self.assertEqual(topics.best_intent("Public transport and visitor guide")[0],
                         "visitor_guides")

    def test_priority_never_changes_admission(self):
        # These are scores only; a page cannot be fetched without passing
        # the existing source/rights/robots gates in the core crawler.
        self.assertGreater(topics.intent_boost({"ticketing_guides": 1.0}, 11), 0)
        self.assertGreater(topics.intent_boost({"fireworks": 1.0}, 11), 0)


if __name__ == "__main__":
    unittest.main()
