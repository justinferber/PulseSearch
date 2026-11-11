"""Three-candidate offline behaviour: fixtures only, zero third-party requests.

The candidates stay unadmitted in the register; the crawler is then pointed at
three synthetic fixtures of the same shape so discovery, edition separation,
robots refusals, redirect refusal and per-source reporting are tested without
contacting a real host.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_crawler_r3a3f.config import CrawlConfig  # noqa: E402
from pulse_search_crawler_r3a3f.crawler import Crawler, build_report  # noqa: E402
from pulse_search_crawler_r3a3f.registry import load_registry  # noqa: E402
from pulse_search_crawler_r3a3f.sitesim import (  # noqa: E402
    Route, build_three_source_network, page_html)
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402
from pulse_search_crawler_r3a3f.store import Store  # noqa: E402

REGISTRY = ROOT / "docs/evidence/r3a3f_three_source_admission.json"


class VirtualClock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class ThreeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="r3a3f-three-"))
        cls.network = build_three_source_network()
        cls.outside = page_html("Unadmitted host", "Public page on a host never admitted.")
        cls.network.servers["lord-mayors-show"].set(
            "/route/", Route(status=302, headers={"Location": "https://procession.invalid/"}))
        cls.store = Store(cls.tmp / "crawl.sqlite")
        cls.staging = StagingIndex(cls.tmp / "staging.sqlite")
        cls.clock = VirtualClock()
        cls.config = CrawlConfig(
            allow_loopback=True, min_interval_s=0.0,
            loopback_hosts=tuple(s.base.replace("http://", "")
                                 for s in cls.network.servers.values()),
            max_depth=3, max_fetches_per_day=5000,
            pilot_http_attempts_per_day=5000,
            pilot_accepted_documents_per_day=5000,
            pilot_run_minutes_max=180.0,
        )
        for name, server in cls.network.servers.items():
            cls.store.add_source(
                source_id=name, origin=server.base,
                allowed_paths=["/events"] if name == "city-hall" else ["/"],
                rights_status="SYNTHETIC_FIXTURE", approved=True, index_allowed=True,
                owner_authorisation="OFFLINE_SIMULATION_ONLY")
            for seed in cls.network.seeds[name]:
                cls.store.add_seed(name, seed)
        crawler = Crawler(cls.store, cls.staging, cls.config,
                          clock=cls.clock, sleep=cls.clock.sleep)
        for seed in cls.store.seeds():
            crawler.register_seed(seed["source_id"], seed["url"])
        cls.counters = crawler.run(max_fetches=300)
        cls.report = build_report(cls.store, cls.staging, cls.config,
                                  registry=load_registry(REGISTRY))
        cls.docs = cls.staging.all_documents(2000)

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls.staging.close()
        cls.network.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def urls(self) -> set[str]:
        return {doc["url"] for doc in self.docs}

    def test_candidates_are_registered_but_unadmitted(self):
        register = load_registry(REGISTRY)
        self.assertEqual(len(register["sources"]), 3)
        for source in register["sources"]:
            self.assertFalse(source["approved"])
            self.assertFalse(source["index_allowed"])
            self.assertEqual(source["owner_authorisation"], None)
            self.assertIn(source["state"], ("candidate", "robots_reviewed", "rights_hold"))

    def test_depth_is_limited_to_three(self):
        self.assertEqual(self.report["depth"]["deepest_fetched"], 3)
        self.assertEqual(self.report["depth"]["depth4_fetches"], 0)
        self.assertEqual(self.network.depth4_hits(), 0)

    def test_every_source_produced_documents_and_report_fields(self):
        by_source = {row["source_id"]: row for row in self.report["sources"]}
        for name in self.network.servers:
            row = by_source[name]
            self.assertGreater(row["documents"], 0, name)
            self.assertTrue(row["categories"], name)
            self.assertGreaterEqual(row["deepest_depth"], 1, name)
            self.assertGreater(row["discovered_links"], 0, name)

    def test_city_hall_scope_and_robots_are_respected(self):
        self.assertEqual(self.network.servers["city-hall"].hits_for("/whats-on"), 0)
        self.assertEqual(self.network.servers["city-hall"].hits_for("/search"), 0)

    def test_parade_forms_commerce_and_admin_are_never_fetched(self):
        parade = self.network.servers["london-parade"]
        for path in ("/shop/", "/takepart/", "/account/", "/admin/"):
            self.assertEqual(parade.hits_for(path), 0, path)
        self.assertFalse(any(token in url for url in self.urls()
                             for token in ("/takepart/", "/shop/", "/account/")))

    def test_show_restrictive_pages_are_never_fetched(self):
        show = self.network.servers["lord-mayors-show"]
        self.assertEqual(show.hits_for("/terms-of-use/"), 0)
        self.assertEqual(show.hits_for("/book/"), 0)

    def test_off_origin_procession_redirect_is_blocked(self):
        self.assertGreaterEqual(
            self.report["redirects"]["by_decision"].get("blocked:off_origin", 0), 1)

    def test_editions_stay_separate(self):
        url_map = {doc["url"]: doc for doc in self.docs}
        parade_2027 = [doc for url, doc in url_map.items() if "2027-celebrate" in url]
        parade_2026 = [doc for url, doc in url_map.items() if "2026-review" in url]
        self.assertTrue(parade_2027)
        self.assertTrue(parade_2026)
        for doc in parade_2026:
            self.assertNotIn("2027", (doc.get("dates") or "") + (doc.get("snippet") or ""))

    def test_cancelled_and_duplicate_material_are_handled(self):
        self.assertTrue(any("2021-parade-cancelled" in url for url in self.urls()))
        self.assertGreaterEqual(self.report["rejections"].get("duplicate_exact", 0), 1)

    def test_searches_find_all_three_sources(self):
        for query, needle in (("London Parade", "parade"),
                              ("Lord Mayor's Show", "mayor"),
                              ("City Hall events", "city hall"),
                              ("Diwali", "diwali")):
            hits = self.staging.search(query, None, 20)
            self.assertTrue(any(needle in (row["title"] + row["url"]).lower()
                                for row in hits), query)

    def test_register_block_reports_zero_real_admissions(self):
        block = self.report["source_register"]
        self.assertEqual(len(block["candidates"]), 3)
        self.assertEqual(block["real_sources_admitted"], 0)
        self.assertEqual(block["status"], "PROPOSAL_ONLY_NOT_ADMITTED")


if __name__ == "__main__":
    unittest.main()
