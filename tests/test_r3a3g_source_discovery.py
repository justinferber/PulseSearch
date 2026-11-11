"""External source discovery must remain review-only and never admit hosts."""
from __future__ import annotations

import unittest

from pulse_search_broad_r3a3g.source_discovery import (
    is_reviewable_origin, rank_external_candidates, candidates_from_store,
)


class CandidateDiscoveryTests(unittest.TestCase):
    def test_safety_filters_and_review_only_state(self):
        rows = [
            {"origin": "https://www.berlin.de", "referrer_url": "https://approved.example/events",
             "sightings": 3},
            {"origin": "https://tickets.example.com", "referrer_url": "https://approved.example/booking-guide",
             "sightings": 2},
            {"origin": "http://127.0.0.1", "referrer_url": "https://approved.example/admin",
             "sightings": 50},
            {"origin": "http://169.254.169.254", "referrer_url": "https://approved.example/",
             "sightings": 90},
            {"origin": "file:///tmp/private", "referrer_url": "", "sightings": 999},
            {"origin": "https://owner:password@othersite.com", "referrer_url": "", "sightings": 900},
            {"origin": "https://localhost.local", "referrer_url": "", "sightings": 800},
        ]
        candidates = rank_external_candidates(rows)
        origins = {x["origin"] for x in candidates}
        self.assertEqual(origins, {"https://www.berlin.de", "https://tickets.example.com"})
        for x in candidates:
            self.assertEqual(x["status"], "CANDIDATE_ONLY_NO_FETCH_PERMISSION")
            self.assertIn("owner_admission", x["requires"])

    def test_multiple_mentions_are_grouped_without_trusting_them(self):
        rows = [
            {"origin": "https://festival.example.org",
             "referrer_url": "https://host.example/events", "sightings": 2},
            {"origin": "https://festival.example.org",
             "referrer_url": "https://host.example/concert", "sightings": 2},
        ]
        candidates = rank_external_candidates(rows)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["sightings"], 4)
        self.assertEqual(candidates[0]["observed_referrer_count"], 2)
        self.assertEqual(candidates[0]["status"], "CANDIDATE_ONLY_NO_FETCH_PERMISSION")

    def test_no_mutations_or_external_network_calls(self):
        class StubStore:
            calls = 0

            def external_candidates(self, limit=5000):
                self.calls += 1
                return [{"origin": "https://venue.org",
                         "referrer_url": "https://host.org/events",
                         "sightings": 1}]
        store = StubStore()
        candidates = candidates_from_store(store)
        self.assertEqual(store.calls, 1)
        self.assertEqual(len(candidates), 1)

    def test_rejects_private_address_ranges_and_nonstandard_ports(self):
        for origin in ("http://10.0.0.1", "http://192.168.1.5",
                       "http://[::1]", "https://example.org:8000",
                       "https://site.invalid", "ftp://example.org"):
            with self.subTest(origin=origin):
                self.assertFalse(is_reviewable_origin(origin))


if __name__ == "__main__":
    unittest.main()
