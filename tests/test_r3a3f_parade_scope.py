"""London Parade scope: attested approval, prepared seeds, enforced 10s delay.

The owner attested the existing Destination Events approval. These tests keep
the recorded scope honest: the source stays unadmitted, the reviewed seeds sit
inside the reviewed paths, the evidence JSON matches the register, and the
published 10-second crawl delay is enforced even if robots.txt stops
advertising it.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_crawler_r3a3f.config import CrawlConfig  # noqa: E402
from pulse_search_crawler_r3a3f.crawler import Crawler  # noqa: E402
from pulse_search_crawler_r3a3f.registry import load_registry  # noqa: E402
from pulse_search_crawler_r3a3f.sitesim import Route, RouteServer, page_html  # noqa: E402
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402
from pulse_search_crawler_r3a3f.store import Store  # noqa: E402
from pulse_search_crawler_r3a3f.urls import in_scope  # noqa: E402

REGISTER = ROOT / "docs/evidence/r3a3f_three_source_admission.json"
SCOPE = ROOT / "docs/evidence/r3a3f_london_parade_scope.json"
TEXT = ("London Parade event information with dates, route, programme, participants, "
        "accessibility, transport and contact details for visitors and organisers.")


class VirtualClock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class ParadeScopeRecordTests(unittest.TestCase):
    def setUp(self):
        self.register = load_registry(REGISTER)
        self.source = next(s for s in self.register["sources"]
                           if s["source_id"] == "london-parade-official")
        self.scope = json.loads(SCOPE.read_text(encoding="utf-8"))

    def test_existing_approval_is_attested_but_not_admitted(self):
        self.assertTrue(self.source["owner_attestation"]["approval_claim"])
        self.assertEqual(self.source["owner_attestation"]["evidence_type"], "owner_attestation")
        self.assertFalse(self.source["approved"])
        self.assertFalse(self.source["index_allowed"])
        self.assertIsNone(self.source["owner_authorisation"])
        self.assertEqual(self.source["state"], "robots_reviewed")

    def test_reviewed_seeds_are_inside_reviewed_paths(self):
        plan = self.source["pilot_plan"]
        self.assertTrue(plan["reviewed_seeds"])
        for seed in plan["reviewed_seeds"]:
            self.assertTrue(
                in_scope(seed, self.source["origin"], plan["reviewed_paths"]), seed)
        self.assertEqual(self.source["allowed_paths"], [])

    def test_scope_record_matches_the_register(self):
        self.assertEqual(self.scope["source"]["reviewed_paths"],
                         self.source["pilot_plan"]["reviewed_paths"])
        self.assertEqual(self.scope["source"]["reviewed_seeds"],
                         self.source["pilot_plan"]["reviewed_seeds"])
        self.assertEqual(self.scope["source"]["crawl_delay_s"], 10)
        self.assertEqual(self.scope["admission"]["approved"], False)
        self.assertIsNone(self.scope["admission"]["owner_authorisation"])
        self.assertEqual(self.scope["real_sources_admitted"], 0)

    def test_exclusions_remain(self):
        excluded = " ".join(self.scope["exclusions"])
        for path in ("/shop/", "/takepart/", "/account/", "/contact/", "/admin/"):
            self.assertIn(path, excluded)
        self.assertIn("ticketmaster", excluded.lower())
        self.assertEqual(self.scope["metadata_coverage"]["page_body"], "NOT_STORED")
        self.assertEqual(self.scope["source"]["snippet_chars_max"], 320)


class CrawlDelayFloorTests(unittest.TestCase):
    def test_source_floor_keeps_ten_seconds_when_robots_drops_crawl_delay(self):
        server = RouteServer().start()
        server.set("/robots.txt", Route(body=b"User-agent: *\nAllow: /\n",
                                        mime="text/plain; charset=utf-8"))
        server.set("/", Route(body=page_html("London Parade", TEXT)))
        tmp = Path(tempfile.mkdtemp(prefix="r3a3f-parade-"))
        store = Store(tmp / "crawl.sqlite")
        staging = StagingIndex(tmp / "staging.sqlite")
        clock = VirtualClock()
        config = CrawlConfig(allow_loopback=True, min_interval_s=0.0,
                             loopback_hosts=(server.base.replace("http://", ""),),
                             max_depth=3)
        try:
            store.add_source(
                source_id="london-parade-official", origin=server.base,
                allowed_paths=["/"], rights_status="SYNTHETIC_FIXTURE",
                approved=True, index_allowed=True,
                owner_authorisation="OFFLINE_SIMULATION_ONLY",
                crawl_delay_floor_s=10.0)
            store.add_seed("london-parade-official", server.base + "/")
            crawler = Crawler(store, staging, config, clock=clock, sleep=clock.sleep)
            for seed in store.seeds():
                crawler.register_seed(seed["source_id"], seed["url"])
            crawler.run(max_fetches=2)
            self.assertIsNotNone(staging.get(server.base + "/"))
            self.assertGreaterEqual(crawler.pacer.total_waited_s, 10.0)
            source = store.source("london-parade-official")
            self.assertEqual(source["crawl_delay_floor_s"], 10.0)
        finally:
            store.close()
            staging.close()
            server.shutdown()
            server.server_close()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
