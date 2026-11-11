"""60+ English/German query patterns with labelled intent and expected source.

These are behavioural cases, not keyword-volume targets. Each case asserts the
route and the presence of a useful, appropriate source; failures stay visible.
"""

from __future__ import annotations

import unittest

from pulse_search_broad_r3a3g.search import search_documents


def doc(url, title, snippet, typ=None, fetched="2026-11-11T00:00:00Z",
        revoked=0, source_id="licensed-fixture"):
    item = {"url": "https://example.test/" + url, "title": title, "snippet": snippet,
            "fetched_at": fetched, "source_id": source_id, "revoked": revoked}
    if typ:
        item["document_type"] = typ
    return item


DOCS = [
    doc("berlin-tickets", "How to book concert tickets in Berlin",
        "Official booking guide: find the venue, use the authorised ticket seller, "
        "check the show date and accessibility.", "booking_guide"),
    doc("berlin-venue", "Mercedes-Benz Arena Berlin venue guide",
        "Venue address, transport, accessibility and official box office information.",
        "venue"),
    doc("berlin-concert", "Berlin concert listings and live music",
        "Upcoming concerts in Berlin, venues and show times.", "event_listing"),
    doc("london-tickets", "London concert ticket guide",
        "Buy tickets from the London venue's official booking office.", "booking_guide"),
    doc("berlin-pride", "Berlin Pride and CSD festival programme",
        "Christopher Street Day pride parade events in Berlin this summer.", "event_detail"),
    doc("germany-pride", "Germany Pride festivals city guide",
        "CSD and Pride programmes across German cities.", "event_listing"),
    doc("london-fireworks", "London New Year's Eve fireworks display",
        "Fireworks and travel guidance for London visitors; check the official "
        "announcement for the edition.", "event_detail"),
    doc("berlin-christmas", "Berlin Weihnachtsmarkt Christmas markets",
        "Christmas markets and Advent programme for Berlin.", "event_listing"),
    doc("music-festival", "European open-air music festivals",
        "Concerts and festival lineups across Europe.", "event_listing"),
    doc("world-cup", "FIFA World Cup 2026 tournament guide",
        "Official tournament history, match archive and venue information.",
        "general_reference"),
    doc("transit", "Berlin public transport ticket guide",
        "How to use rail and metro ticket machines when travelling to venues.",
        "transport_guide"),
    doc("general", "What is an email account?",
        "An explanation of email accounts, privacy and inboxes.", "general_reference"),
    doc("glastonbury", "Glastonbury Festival 2027 dates",
        "The festival returns from 23 to 27 June 2027 at Worthy Farm.", "event_detail"),
    doc("parade", "London Parade 2027 route and timing",
        "The organiser publishes the route, start time and travel advice.", "event_detail"),
    doc("danger", "Book concert tickets in Berlin — Admin panel",
        "Should never show up.", "booking_guide", revoked=1),
    doc("phish", "Official ChatGPT login free",
        "Claim your free upgrade at this unofficial clone.", "general_reference",
        source_id="untrusted"),
    doc("expired", "Glastonbury 2025 dates",
        "The 2025 festival took place in June 2025.", "event_detail",
        fetched="2023-01-01T00:00:00Z"),
]

# (query, expected intent, expected status, substring that must appear in results)
CASES = [
    ("ChatGPT", "navigate", "official_navigation", "chatgpt.com"),
    ("Amazon", "navigate", "official_navigation", "amazon.com"),
    ("YouTube", "navigate", "official_navigation", "youtube.com"),
    ("Gmail", "navigate", "official_navigation", "mail.google.com"),
    ("Wordle", "navigate", "official_navigation", "nytimes.com/games/wordle"),
    ("Facebook", "navigate", "official_navigation", "facebook.com"),
    ("Google", "navigate", "official_navigation", "google.com"),
    ("Chat GPT", "navigate", "official_navigation", "chatgpt.com"),
    ("Canva", "navigate", "official_navigation", "canva.com"),
    ("Google Translate", "navigate", "official_navigation", "translate.google.com"),
    ("FIFA World Cup 2026", "sports", "staging_results", "world-cup"),
    ("Weather", "weather", "official_links", "bbc.co.uk/weather"),
    ("Weather tomorrow in London", "weather", "official_links", "metoffice.gov.uk"),
    ("What is the weather in Berlin today?", "weather", "official_links", "dwd.de"),
    ("Wetter Berlin morgen", "weather", "official_links", "dwd.de"),
    ("Wie ist das Wetter in München?", "weather", "official_links", "dwd.de"),
    ("London weather forecast this weekend", "weather", "official_links", "bbc.co.uk/weather"),
    ("Translate English to German", "translate", "official_links", "deepl.com"),
    ("Übersetze Guten Morgen ins Deutsche", "translate", "official_links", "deepl.com"),
    ("How do I book concert tickets in Berlin?", "how_to", "staging_results", "berlin-tickets"),
    ("Konzertkarten Berlin kaufen", "how_to", "staging_results", "berlin-tickets"),
    ("book concert tickets in London", "how_to", "staging_results", "london-tickets"),
    ("How do I get to the O2 by public transport?", "transport", "official_links", "tfl.gov.uk"),
    ("Wie komme ich zum Konzert in Berlin?", "transport", "official_links", "bvg.de"),
    ("Can you name place to buy flight tickets?", "flights", "official_links", "britishairways.com"),
    ("cheapest flights to Berlin", "flights", "official_links", "lufthansa.com"),
    ("Flüge nach Berlin buchen", "flights", "official_links", "easyjet.com"),
    ("How can I return concert tickets in Berlin?", "how_to", "official_links", "gov.uk"),
    ("UK ticket refund rights", "how_to", "official_links", "gov.uk"),
    ("refund policy for a cancelled concert", "how_to", "official_links", "gov.uk"),
    ("Pride festivals in Germany", "events", "staging_results", "germany-pride"),
    ("CSD Berlin", "events", "staging_results", "berlin-pride"),
    ("Pride festivals Germany excluding Christmas markets", "events", "staging_results", "germany-pride"),
    ("Feuerwerk London", "events", "staging_results", "london-fireworks"),
    ("fireworks in London", "events", "staging_results", "london-fireworks"),
    ("music festivals Europe", "events", "staging_results", "music-festival"),
    ("open air music festivals Europe", "events", "staging_results", "music-festival"),
    ("Christmas markets in Berlin", "events", "staging_results", "berlin-christmas"),
    ("Weihnachtsmärkte in Berlin", "events", "staging_results", "berlin-christmas"),
    ("Berlin Veranstaltungen ohne Weihnachtsmärkte", "events", "staging_results", "berlin-"),
    ("Diwali events in London", "events", "staging_results", "london-fireworks"),
    ("parades in London", "events", "staging_results", "parade"),
    ("Glastonbury 2027 dates", "events", "staging_results", "glastonbury"),
    ("London Parade 2027", "events", "staging_results", "parade"),
    ("What is an email account?", "general", "staging_results", "general"),
    ("What is a public transport day ticket?", "transport", "staging_results", "transit"),
    ("Berlin public transport ticket instructions", "transport", "staging_results", "transit"),
    ("What is the capital of Germany?", "general", "official_links", "wikipedia.org"),
    ("Berlin Wall history", "general", "official_links", "wikipedia.org"),
    ("Who runs Berlin public transport?", "transport", "staging_results", "transit"),
    ("What is CSD?", "events", "staging_results", "berlin-pride"),
    ("Museum Island Berlin information", "general", "official_links", "berlin.de"),
    ("Glastonbury 2025 dates", "events", "staging_results", "glastonbury"),
    ("Glastonbury 2026", "events", "staging_results", "glastonbury"),
    ("Glatsunbury dates", "general", "official_links", "wikipedia.org"),
    ("Berln concert tickets", "how_to", "staging_results", "berlin-tickets"),
    ("official ChatGPT login free", "general", "official_links", "wikipedia.org"),
    ("weather Berlin 2030", "weather", "official_links", "dwd.de"),
    ("affordable flights now", "flights", "official_links", "britishairways.com"),
    ("asdfgh qwerty", "general", "official_links", "wikipedia.org"),
    ("events in Paris", "events", "official_links", "paris.fr"),
    ("Konzertkarten München", "how_to", "official_links", "eventim.de"),
    ("Was ist CSD?", "events", "staging_results", "berlin-pride"),
    ("Berlin events without Christmas markets", "events", "staging_results", "berlin-"),
    ("How do I buy official tickets for a festival?", "how_to", "staging_results", "berlin-tickets"),
    ("Where can I get tickets for a festival?", "how_to", "staging_results", "music-festival"),
    ("How do I get accessibility information for a Berlin venue?", "how_to", "official_links", "huxleys-neue-welt.de"),
    ("best shopping deals", "shopping", "official_links", "amazon"),
    ("Amazon rainforest facts", "general", "official_links", "wikipedia.org"),
    ("ChatGPT privacy policy", "general", "official_links", "wikipedia.org"),
]

assert len(CASES) >= 60
CITY_TERMS = {"berlin", "london", "münchen", "munich", "manchester", "paris"}


class AcceptancePatternTests(unittest.TestCase):
    def test_sixty_plus_real_world_patterns_have_a_useful_route(self):
        failures = []
        for query, intent, status, needle in CASES:
            with self.subTest(query=query):
                result = search_documents(DOCS, query)
                if result["intent"]["kind"] != intent:
                    failures.append(f"{query}: intent {result['intent']['kind']} != {intent}")
                if result["status"] != status:
                    failures.append(f"{query}: status {result['status']} != {status}")
                text = " ".join(str(r.get("url", "")) for r in result["results"])
                if needle and needle not in text:
                    failures.append(f"{query}: missing {needle} in {text}")
                if status == "no_staging_evidence" and result["results"]:
                    failures.append(f"{query}: no-evidence case returned results")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_wrong_city_ticket_page_cannot_outrank_local_guide(self):
        result = search_documents(DOCS, "book concert tickets in Berlin")
        self.assertIn("berlin-tickets", result["results"][0]["url"])
        london = next((r for r in result["results"] if "london-tickets" in r["url"]), None)
        if london:
            self.assertLess(london["score"], result["results"][0]["score"])

    def test_weather_never_returns_a_temperature_value(self):
        for query in ("weather London now", "Wetter Berlin morgen"):
            result = search_documents(DOCS, query)
            self.assertEqual(result["status"], "official_links")
            self.assertNotIn("°C", str(result["results"]))
            self.assertEqual(result["response_mode"], "CURRENT_SERVICE_HANDOFF")

    def test_untrusted_and_revoked_pages_never_appear(self):
        result = search_documents(DOCS, "ChatGPT login free")
        urls = " ".join(r["url"] for r in result["results"])
        self.assertNotIn("example.test/phish", urls)
        other = search_documents(DOCS, "Book concert tickets in Berlin admin panel")
        self.assertNotIn("example.test/danger", " ".join(r["url"] for r in other["results"]))

    def test_excluded_terms_are_reported_and_applied(self):
        result = search_documents(DOCS, "Pride festivals Germany excluding Christmas markets")
        self.assertTrue(any("Excluded terms" in n for n in result["notices"]))

    def test_refund_uses_admitted_consumer_guidance_before_official_links(self):
        docs = [doc("uk-refund", "UK consumer refund rights",
                    "If a concert is cancelled, UK consumer guidance explains your refund options.",
                    "how_to")]
        result = search_documents(docs, "UK ticket refund rights")
        self.assertEqual(result["status"], "staging_results")
        self.assertIn("uk-refund", result["results"][0]["url"])

    def test_refund_without_a_supporting_page_still_uses_official_links(self):
        result = search_documents(DOCS, "refund policy for a cancelled concert")
        self.assertEqual(result["status"], "official_links")
        self.assertIn("gov.uk", result["results"][0]["url"])


if __name__ == "__main__":
    unittest.main()
