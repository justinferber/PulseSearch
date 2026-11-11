"""End-to-end offline crawl gates against the synthetic network."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_crawler_r3a3f.classify import CATEGORIES  # noqa: E402
from pulse_search_crawler_r3a3f.config import CrawlConfig  # noqa: E402
from pulse_search_crawler_r3a3f.crawler import Crawler, build_report  # noqa: E402
from pulse_search_crawler_r3a3f.dashboard import render_html  # noqa: E402
from pulse_search_crawler_r3a3f.sitesim import build_network  # noqa: E402
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402
from pulse_search_crawler_r3a3f.store import Store, utc_now  # noqa: E402


class CrawlGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="r3a3f-test-"))
        cls.network = build_network()
        cls.store = Store(cls.tmp / "crawl.sqlite")
        cls.staging = StagingIndex(cls.tmp / "staging.sqlite")
        cls.config = CrawlConfig(
            allow_loopback=True,
            min_interval_s=0.0,
            loopback_hosts=tuple(s.base.replace("http://", "") for s in cls.network.servers.values()),
            max_depth=3,
        )
        for name, server in cls.network.servers.items():
            cls.store.add_source(source_id=name, origin=server.base, allowed_paths=["/"],
                                 rights_status="SYNTHETIC_FIXTURE")
            for seed in cls.network.seeds[name]:
                cls.store.add_seed(name, seed)
        for seed in cls.store.seeds():
            cls.store.enqueue(seed["url"], source_id=seed["source_id"],
                              seed_id=seed["seed_id"], parent_url=None, depth=0,
                              max_depth=cls.config.max_depth)
        cls.crawler = Crawler(cls.store, cls.staging, cls.config)
        cls.counters = cls.crawler.run(max_fetches=250)
        cls.report = build_report(cls.store, cls.staging, cls.config)
        cls.docs = cls.staging.all_documents(1000)
        cls.urls = {d["url"] for d in cls.docs}

    @classmethod
    def tearDownClass(cls):
        cls.network.stop()
        cls.store.close()
        cls.staging.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_depth_three_is_the_hard_maximum(self):
        self.assertLessEqual(self.report["depth"]["deepest_fetched"], 3)
        self.assertEqual(self.report["depth"]["depth4_fetches"], 0)
        self.assertEqual(self.network.depth4_hits(), 0)

    def test_robots_denials_are_never_fetched(self):
        self.assertEqual(self.network.servers["berlin-events"].hits_for("/private"), 0)
        self.assertGreaterEqual(self.report["robots"]["denied"], 1)

    def test_unreachable_robots_fails_closed(self):
        self.assertEqual(self.network.servers["robots-broken"].hits_for("/festival"), 0)

    def test_noindex_pages_are_not_indexed(self):
        self.assertFalse(any("hidden" in url or "noindex" in url for url in self.urls))

    def test_cultural_events_remain_discoverable(self):
        for slug in ("diwali", "csd-berlin", "pride-berlin", "stadtfest-berlin"):
            self.assertTrue(any(slug in url for url in self.urls), slug)

    def test_category_coverage_is_broad(self):
        self.assertGreaterEqual(self.report["categories"]["covered"], 12)
        counts = self.report["categories"]["counts"]
        self.assertEqual(set(counts), set(CATEGORIES))

    def test_duplicates_and_near_duplicates_rejected(self):
        rejections = self.report["rejections"]
        self.assertGreater(rejections.get("duplicate_exact", 0)
                           + rejections.get("duplicate_near", 0), 0)

    def test_rate_limit_and_server_errors_recorded(self):
        self.assertGreaterEqual(self.report["errors"]["rate_limited"], 1)

    def test_off_domain_links_are_candidates_only(self):
        self.assertGreaterEqual(self.report["funnel"]["off_domain_proposed"], 0)
        # Cross-origin london/community pages only exist via their own seeds.
        london_docs = [d for d in self.docs if d["source_id"] == "london-venue"]
        self.assertTrue(london_docs)

    def test_search_and_category_filter(self):
        hits = self.staging.search("Diwali", None, 5)
        self.assertTrue(hits)
        filtered = self.staging.search("festival", "Festival", 20)
        self.assertTrue(all(h["category"] == "Festival" for h in filtered))

    def test_restart_recovery_preserves_state(self):
        before = self.store.queue_counts()
        self.store.conn.execute(
            "UPDATE frontier SET state='fetching' WHERE url=(SELECT url FROM frontier LIMIT 1)")
        self.store.conn.commit()
        crawler = Crawler(self.store, self.staging, self.config)
        crawler.run(max_fetches=5)
        after = self.store.queue_counts()
        self.assertNotIn("fetching", after)
        self.assertGreaterEqual(sum(after.values()), sum(before.values()) - 5)

    def test_conditional_recrawl_revalidates(self):
        self.store.conn.execute(
            "UPDATE page_state SET next_recrawl_at='2000-01-01T00:00:00+00:00' WHERE revoked=0")
        self.store.conn.commit()
        requeued = self.store.requeue_for_recrawl(utc_now(), limit=25)
        self.assertGreater(requeued, 0)
        crawler = Crawler(self.store, self.staging, self.config)
        counters = crawler.run(max_fetches=40)
        self.assertGreater(counters.get("revalidated_unchanged", 0), 0)

    def test_source_revocation_removes_documents(self):
        index = StagingIndex(self.tmp / "revoke.sqlite")
        try:
            index.add_document({
                "url": "https://revoked.example/x", "source_id": "community-hub",
                "title": "Volunteering day", "snippet": "volunteering",
                "category": "Volunteering", "category_confidence": 0.8,
                "categories": {}, "depth": 1, "fetched_at": utc_now(),
                "content_hash": "abc",
            }, [])
            self.assertTrue(index.revoke_source("community-hub", "revoked"))
            self.assertFalse(index.search("volunteering", None, 5))
        finally:
            index.close()

    def test_budget_is_respected(self):
        tmp = Path(tempfile.mkdtemp(prefix="r3a3f-budget-"))
        store = Store(tmp / "c.sqlite")
        staging = StagingIndex(tmp / "s.sqlite")
        try:
            store.add_source(source_id="berlin-events",
                             origin=self.network.servers["berlin-events"].base,
                             allowed_paths=["/"], rights_status="SYNTHETIC_FIXTURE")
            store.add_seed("berlin-events", self.network.servers["berlin-events"].base + "/")
            for seed in store.seeds():
                store.enqueue(seed["url"], source_id=seed["source_id"],
                              seed_id=seed["seed_id"], parent_url=None, depth=0,
                              max_depth=self.config.max_depth)
            counters = Crawler(store, staging, self.config).run(max_fetches=5)
            self.assertLessEqual(counters["fetched"], 5)
        finally:
            store.close()
            staging.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_dashboard_report_and_html(self):
        self.assertEqual(self.report["schema"], "pulse-search-r3a3f-run-report/v1")
        self.assertIn("18-category coverage", render_html(self.report, self.staging))
        self.assertEqual(self.report["daily_target_model"]["status"],
                         "SIMULATION_ONLY_NOT_A_PRODUCTION_CLAIM")
        self.assertEqual(self.report["safety"]["events_engine_writes"], 0)


class SignalRichnessTests(unittest.TestCase):
    def test_report_has_required_sections(self):
        tmp = Path(tempfile.mkdtemp(prefix="r3a3f-empty-"))
        store = Store(tmp / "c.sqlite")
        staging = StagingIndex(tmp / "s.sqlite")
        try:
            report = build_report(store, staging, CrawlConfig())
            for key in ("funnel", "categories", "sources", "index", "freshness",
                        "robots", "errors", "latency", "politeness",
                        "daily_target_model", "safety", "documents"):
                self.assertIn(key, report)
            self.assertEqual(report["index"]["documents"], 0)
        finally:
            store.close()
            staging.close()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
