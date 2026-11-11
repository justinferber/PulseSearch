"""R3-A3G broad searches: intent, relevance, general how-to and navigation.

Only immutable in-memory fixtures. No external requests or admitted hosts.
"""
from __future__ import annotations

import unittest

from pulse_search_broad_r3a3g.search import (
    OFFICIAL_NAVIGATION, classify_query, document_type, search_documents,
    search_staging,
)


def doc(url, title, snippet, typ=None, **extra):
    result = {"url": "https://example.test/" + url, "title": title,
              "snippet": snippet, "fetched_at": "2026-11-11T00:00:00Z",
              "source_id": "offline-licensed-fixture", "revoked": 0}
    if typ:
        result["document_type"] = typ
    result.update(extra)
    return result


DOCS = [
    doc("berlin-tickets", "How to book concert tickets in Berlin",
        "Official concert booking guide: find the venue, choose the official ticket seller, "
        "select the performance date and review accessible ticket policies.",
        "booking_guide"),
    doc("berlin-concert", "Berlin concert listings and live music",
        "Find upcoming concerts in Berlin, venues and show times.", "event_listing"),
    doc("london-concert", "London concert ticket guide",
        "Buy tickets from the London venue's official booking office.", "booking_guide"),
    doc("berlin-pride", "Berlin Pride and CSD festival programme",
        "Christopher Street Day pride parade events in Berlin this summer.", "event_detail"),
    doc("germany-pride", "Germany Pride festivals city guide",
        "CSD and Pride programmes across German cities.", "event_listing"),
    doc("london-fireworks", "London New Year's Eve fireworks display",
        "Fireworks and travel guidance for London visitors. Edition date must be confirmed.",
        "event_detail"),
    doc("berlin-christmas", "Berlin Weihnachtsmarkt Christmas markets",
        "Christmas markets and Advent programme for Berlin.", "event_listing"),
    doc("music-festival", "European open-air music festivals",
        "Concerts and festival lineups across Europe.", "event_listing"),
    doc("world-cup", "FIFA World Cup 2026 tournament guide",
        "Official tournament history, match scheduling archive and venue information.",
        "general_reference"),
    doc("transit", "Berlin public transport ticket guide",
        "How to use rail and public transport ticket machines when travelling to venues.",
        "transport_guide"),
    doc("general", "What is an email account?",
        "An explanation of email accounts, privacy and inboxes.", "general_reference"),
    doc("danger", "Book concert tickets in Berlin — Admin panel",
        "Should never show up.", "booking_guide", revoked=1),
]


class StubIndex:
    def all_documents(self, limit=5000):
        return DOCS[:limit]


class IntentTests(unittest.TestCase):
    def test_15_common_searches_are_recognised_without_volume_data(self):
        samples = {
            "ChatGPT": "navigate", "Amazon": "navigate", "YouTube": "navigate",
            "Gmail": "navigate", "Wordle": "navigate", "Weather": "weather",
            "Facebook": "navigate", "Google": "navigate",
            "FIFA World Cup 2026": "sports", "Chat GPT": "navigate",
            "Weather tomorrow": "weather", "Translate": "translate",
            "Google Translate": "navigate", "Walmart": "navigate",
            "Canva": "navigate",
        }
        self.assertEqual(len(samples), 15)
        for query, kind in samples.items():
            with self.subTest(query=query):
                self.assertEqual(classify_query(query).kind, kind)

    def test_navigation_uses_official_site_not_phishing_or_unapproved_crawl(self):
        for q in ("Chat GPT", "YouTube", "Gmail", "Wordle", "Canva"):
            result = search_documents([], q)
            self.assertEqual(result["status"], "official_navigation")
            self.assertTrue(result["results"][0]["url"].startswith("https://"))
            self.assertFalse(result["results"][0]["verified_live"])
        self.assertEqual(classify_query("Amazon rainforest").kind, "general")
        self.assertEqual(classify_query("ChatGPT privacy policy").kind, "general")
        self.assertEqual(len(OFFICIAL_NAVIGATION), 10)

    def test_live_weather_refuses_to_invent_a_forecast(self):
        response = search_documents(DOCS, "weather tomorrow in Berlin")
        self.assertEqual(response["status"], "live_provider_required")
        self.assertEqual(response["results"], [])
        self.assertIsNone(response["answer"])

    def test_no_claimed_translation_without_a_provider(self):
        response = search_documents([], "translate good morning into German")
        self.assertEqual(response["status"], "live_provider_required")


class RelevanceTests(unittest.TestCase):
    def test_berlin_ticket_howto_returns_an_actual_guide_first(self):
        result = search_documents(DOCS, "How do I book tickets for a concert in Berlin?")
        self.assertEqual(result["intent"]["kind"], "how_to")
        self.assertEqual(result["results"][0]["url"], "https://example.test/berlin-tickets")
        self.assertIn("instruction_page", result["results"][0]["ranking_reasons"])
        self.assertNotIn("https://example.test/danger", [d["url"] for d in result["results"]])
        self.assertIsNone(result["answer"])  # no unsupported generated instructions

    def test_geography_reduces_wrong_city_rank(self):
        result = search_documents(DOCS, "book concert in Berlin")
        hits = {r["url"]: r["score"] for r in result["results"]}
        self.assertGreater(hits["https://example.test/berlin-tickets"],
                           hits["https://example.test/london-concert"])

    def test_fireworks_are_searchable(self):
        result = search_documents(DOCS, "fireworks in London")
        self.assertEqual(result["results"][0]["url"], "https://example.test/london-fireworks")

    def test_pride_and_csd_have_multi_city_coverage(self):
        result = search_documents(DOCS, "Pride festivals in Germany")
        self.assertEqual(result["results"][0]["url"], "https://example.test/germany-pride")
        other = search_documents(DOCS, "CSD Berlin")
        self.assertEqual(other["results"][0]["url"], "https://example.test/berlin-pride")

    def test_music_and_christmas_events_not_blocked(self):
        result = search_documents(DOCS, "open air music festivals Europe")
        self.assertTrue(any("music-festival" in x["url"] for x in result["results"]))
        other = search_documents(DOCS, "Christmas markets Berlin")
        self.assertEqual(other["results"][0]["url"], "https://example.test/berlin-christmas")

    def test_general_information_does_not_need_event_date(self):
        result = search_documents(DOCS, "what is an email account")
        self.assertEqual(result["results"][0]["document_type"], "general_reference")
        self.assertIn("general", result["results"][0]["url"])

    def test_fifa_results_do_not_claim_live_scores(self):
        result = search_documents(DOCS, "FIFA World Cup 2026")
        self.assertEqual(result["intent"]["kind"], "sports")
        self.assertIn("world-cup", result["results"][0]["url"])
        self.assertIsNone(result["answer"])

    def test_readonly_adapter_only_needs_all_documents(self):
        result = search_staging(StubIndex(), "tickets for a concert in Berlin")
        self.assertEqual(result["intent"]["location"], "berlin")
        self.assertTrue(result["results"])

    def test_no_evidence_means_no_fabricated_answer(self):
        result = search_documents([], "How can I return concert tickets in Berlin?")
        self.assertEqual(result["status"], "no_staging_evidence")
        self.assertEqual(result["results"], [])
        self.assertIsNone(result["answer"])

    def test_declared_type_wins_over_heuristic(self):
        self.assertEqual(document_type(doc("x","City concerts", "Music venue",
                                             "official_booking_guide")), "official_booking_guide")


if __name__ == "__main__":
    unittest.main()
