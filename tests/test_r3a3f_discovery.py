"""Discovery-intent gates: seasonal and outdoor event discovery.

These tests exist because a depth-limited crawler that only follows a
homepage's generic links will miss Christmas markets, CSD/Pride programmes,
carnivals and open-air festivals. The intent layer must improve discovery
without ever blocking a topic or bypassing robots, scope or depth.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_crawler_r3a3f import topics  # noqa: E402
from pulse_search_crawler_r3a3f.classify import classify  # noqa: E402
from pulse_search_crawler_r3a3f.config import CrawlConfig  # noqa: E402
from pulse_search_crawler_r3a3f.crawler import Crawler, build_report  # noqa: E402
from pulse_search_crawler_r3a3f.sitesim import build_network  # noqa: E402
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402
from pulse_search_crawler_r3a3f.store import Store  # noqa: E402


class IntentMatchingTests(unittest.TestCase):
    def test_english_and_german_christmas_terms(self):
        for phrase in ("Christmas markets 2026", "Weihnachtsmarkt am Rathaus",
                       "Adventsmarkt mit Glühwein", "Xmas market stalls"):
            slug, score = topics.best_intent(phrase)
            self.assertEqual(slug, "christmas_markets", phrase)
            self.assertGreater(score, 0)

    def test_pride_csd_and_carnival_terms(self):
        self.assertEqual(topics.best_intent("CSD Berlin")[0], "pride")
        self.assertEqual(topics.best_intent("Christopher Street Day parade")[0], "pride")
        self.assertEqual(topics.best_intent("Karneval Umzug")[0], "parades")
        self.assertEqual(topics.best_intent("open air festival lineup")[0], "music_festivals")

    def test_unrelated_text_has_no_intent(self):
        self.assertEqual(topics.best_intent("Library opening hours")[0], None)

    def test_seasonality_raises_priority_in_season(self):
        december = topics.intent_boost({"christmas_markets": 2.0}, 12)
        july = topics.intent_boost({"christmas_markets": 2.0}, 7)
        self.assertGreater(december, july)
        june_pride = topics.intent_boost({"pride": 2.0}, 6)
        january_pride = topics.intent_boost({"pride": 2.0}, 1)
        self.assertGreater(june_pride, january_pride)

    def test_hub_detection(self):
        self.assertGreaterEqual(
            topics.hub_score("What's on in Berlin", "Events calendar and listings", 24), 0.5)
        self.assertLess(topics.hub_score("Contact us", "Office hours", 2), 0.5)


class GermanClassificationTests(unittest.TestCase):
    def test_weihnachtsmarkt_is_a_market(self):
        result = classify("Weihnachtsmarkt Berlin 2026",
                          "Adventsmarkt mit Glühwein und Ständen am Rathaus.")
        self.assertEqual(result.primary, "Market")

    def test_karneval_umzug_is_a_parade(self):
        result = classify("Karneval Umzug Berlin",
                          "Karneval parade with an Umzug through the streets and costumes.")
        self.assertEqual(result.primary, "Parades & Processions")

    def test_csd_remains_pride(self):
        result = classify("CSD Berlin", "Christopher Street Day pride parade and queer festival.")
        self.assertEqual(result.primary, "Pride & Community")


class DiscoveryCrawlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="r3a3f-discovery-"))
        cls.network = build_network()
        cls.store = Store(cls.tmp / "crawl.sqlite")
        cls.staging = StagingIndex(cls.tmp / "staging.sqlite")
        cls.config = CrawlConfig(
            allow_loopback=True, min_interval_s=0.0,
            loopback_hosts=tuple(s.base.replace("http://", "") for s in cls.network.servers.values()),
            focus_month=12,
        )
        for name, server in cls.network.servers.items():
            cls.store.add_source(source_id=name, origin=server.base, allowed_paths=["/"],
                                 rights_status="SYNTHETIC_FIXTURE",
                                 approved=True, index_allowed=True,
                                 probe_policy=["/whats-on", "/events/christmas"],
                                 probe_budget_per_run=2)
            for seed in cls.network.seeds[name]:
                cls.store.add_seed(name, seed)
        crawler = Crawler(cls.store, cls.staging, cls.config)
        for seed in cls.store.seeds():
            crawler.register_seed(seed["source_id"], seed["url"])
        cls.counters = crawler.run(max_fetches=260)
        cls.report = build_report(cls.store, cls.staging, cls.config)
        cls.urls = {d["url"] for d in cls.staging.all_documents(1000)}

    @classmethod
    def tearDownClass(cls):
        cls.network.stop()
        cls.store.close()
        cls.staging.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_listing_hub_probes_are_queued_and_fetched(self):
        self.assertGreater(self.report["discovery"]["probes_total"], 0)
        self.assertTrue(any(url.endswith("/whats-on") for url in self.urls))

    def test_seasonal_pages_are_discovered(self):
        for slug in ("weihnachtsmarkt", "open-air-festival", "karneval-umzug"):
            self.assertTrue(any(slug in url for url in self.urls), slug)

    def test_discovery_intents_are_counted(self):
        intents = {item["slug"]: item["documents"] for item in self.report["discovery"]["intents"]}
        self.assertGreater(intents.get("christmas_markets", 0), 0)
        self.assertGreater(intents.get("music_festivals", 0), 0)
        self.assertGreater(intents.get("parades", 0), 0)
        self.assertGreater(intents.get("pride", 0), 0)

    def test_anchor_intent_raises_priority_without_breaking_depth(self):
        rows = [dict(r) for r in self.store.conn.execute(
            "SELECT url, priority, min_depth FROM frontier WHERE category_hint IS NOT NULL")]
        self.assertTrue(any(r["priority"] > 100 for r in rows))
        self.assertLessEqual(self.report["depth"]["deepest_fetched"], 3)
        self.assertEqual(self.report["depth"]["depth4_fetches"], 0)

    def test_intent_never_blocks_a_topic(self):
        # Pride, Diwali, CSD and Stadtfest remain present while Christmas is in season.
        for slug in ("pride-berlin", "diwali", "csd-berlin", "stadtfest-berlin"):
            self.assertTrue(any(slug in url for url in self.urls), slug)
        self.assertEqual(self.report["discovery"]["semantics"],
                         "priority_hint_only_no_topic_blocking")


if __name__ == "__main__":
    unittest.main()
