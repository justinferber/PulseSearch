"""The five pre-pilot operational gates, exercised before any live request.

1. A queued URL is checked for origin, exact path scope and indexing
   permission before robots.txt or content is requested.
2. Every network attempt, robots and redirect hops included, is counted.
3. Total HTTP attempts, accepted documents and run duration are hard limits
   persisted in the store, so a restart cannot reset the day.
4. Novelty verifies the SHA-256 of the historical index before reading it.
5. A real host needs a distinct, documented owner authorisation.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_crawler_r3a3f.config import CrawlConfig  # noqa: E402
from pulse_search_crawler_r3a3f.crawler import Crawler, build_report  # noqa: E402
from pulse_search_crawler_r3a3f.novelty import NoveltyPinMismatch, overlap  # noqa: E402
from pulse_search_crawler_r3a3f.sitesim import Route, RouteServer, page_html  # noqa: E402
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402
from pulse_search_crawler_r3a3f.store import Store  # noqa: E402

ALLOW = b"User-agent: *\nAllow: /\n"
TEXT = ("Community venue programme with dates, opening times, accessibility, transport "
        "and contact information for visitors and organisers.")


class VirtualClock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class GateEnv:
    def __init__(self, server: RouteServer, **kwargs):
        self.tmp = Path(tempfile.mkdtemp(prefix="r3a3f-gates-"))
        self.server = server
        self.store = Store(self.tmp / "crawl.sqlite")
        self.staging = StagingIndex(self.tmp / "staging.sqlite")
        self.config = CrawlConfig(
            allow_loopback=True, min_interval_s=0.0,
            loopback_hosts=(server.base.replace("http://", ""),),
            max_depth=3, **kwargs,
        )
        self.clock = VirtualClock()

    def admit(self, *, approved=True, index_allowed=True, paths=("/",),
              rights="SYNTHETIC_FIXTURE", authorisation="OFFLINE_SIMULATION_ONLY"):
        self.store.add_source(
            source_id="site", origin=self.server.base, allowed_paths=list(paths),
            rights_status=rights, approved=approved, index_allowed=index_allowed,
            owner_authorisation=authorisation)

    def crawler(self) -> Crawler:
        return Crawler(self.store, self.staging, self.config,
                       clock=self.clock, sleep=self.clock.sleep)

    def close(self) -> None:
        self.store.close()
        self.staging.close()
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)


def make_server(robots: bytes = ALLOW) -> RouteServer:
    server = RouteServer().start()
    server.set("/robots.txt", Route(body=robots, mime="text/plain; charset=utf-8"))
    return server


class PreNetworkAdmissionTests(unittest.TestCase):
    def test_out_of_scope_url_never_triggers_robots_or_content(self):
        server = make_server()
        server.set("/private/notes", Route(body=page_html("Private notes", TEXT)))
        env = GateEnv(server)
        try:
            env.admit(paths=["/events"])
            env.store.enqueue(server.base + "/private/notes", source_id="site",
                              seed_id=None, parent_url=server.base + "/events",
                              depth=1, max_depth=3, method="link",
                              approval_ref="link:" + server.base + "/events")
            counters = env.crawler().run(max_fetches=1)
            self.assertEqual(server.hits, [])
            self.assertEqual(counters.get("reject_out_of_scope"), 1)
            refused = env.store.url_admission_counts()
            self.assertEqual(refused.get("refused:out_of_scope"), 1)
        finally:
            env.close()

    def test_unindexable_source_is_refused_before_robots(self):
        server = make_server()
        server.set("/", Route(body=page_html("Venue home", TEXT)))
        env = GateEnv(server)
        try:
            env.admit(index_allowed=False)
            crawler = env.crawler()
            crawler.register_seed("site", server.base + "/")
            counters = crawler.run(max_fetches=1)
            self.assertEqual(server.hits, [])
            self.assertEqual(counters.get("reject_rights_denied_index"), 1)
        finally:
            env.close()

    def test_allowed_url_records_its_admission(self):
        server = make_server()
        server.set("/", Route(body=page_html("Venue home", TEXT)))
        env = GateEnv(server)
        try:
            env.admit()
            crawler = env.crawler()
            crawler.register_seed("site", server.base + "/")
            crawler.run(max_fetches=1)
            self.assertGreaterEqual(
                env.store.url_admission_counts().get("allowed:", 0), 1)
        finally:
            env.close()


class PersistedBudgetTests(unittest.TestCase):
    def test_http_attempt_cap_survives_a_restart(self):
        server = make_server()
        for index in range(6):
            server.set(f"/p{index}", Route(body=page_html(
                f"Page {index}", TEXT, links=[f"/p{index + 1}"] if index < 5 else [])))
        server.set("/", Route(body=page_html("Home", TEXT, links=["/p0"])))
        env = GateEnv(server, pilot_http_attempts_per_day=3)
        try:
            env.admit()
            crawler = env.crawler()
            crawler.register_seed("site", server.base + "/")
            counters = crawler.run(max_fetches=20)
            self.assertEqual(counters.get("stop_reason"), "http_attempts_cap_reached")
            self.assertEqual(env.store.budget_snapshot()["http_attempts"], 3)
            hits_after_first = len(server.hits)
            self.assertLessEqual(hits_after_first, 3)
            # A fresh process reads the same ledger and sends nothing more.
            second = env.crawler().run(max_fetches=20)
            self.assertEqual(second.get("stop_reason"), "http_attempts_cap_reached")
            self.assertEqual(len(server.hits), hits_after_first)
            self.assertEqual(env.store.budget_snapshot()["http_attempts"], 3)
        finally:
            env.close()

    def test_accepted_document_cap_is_persisted(self):
        server = make_server()
        for index in range(5):
            server.set(f"/p{index}", Route(body=page_html(
                f"Page {index}", TEXT, links=[f"/p{index + 1}"] if index < 4 else [])))
        server.set("/", Route(body=page_html("Home", TEXT, links=["/p0"])))
        env = GateEnv(server, pilot_accepted_documents_per_day=2)
        try:
            env.admit()
            crawler = env.crawler()
            crawler.register_seed("site", server.base + "/")
            counters = crawler.run(max_fetches=10)
            self.assertIn(counters.get("stop_reason"),
                          {"accepted_documents_cap_reached", "queue_empty"})
            self.assertEqual(env.store.budget_snapshot()["accepted_documents"], 2)
            self.assertEqual(env.staging.stats()["documents"], 2)
            env.crawler().run(max_fetches=10)
            self.assertEqual(env.staging.stats()["documents"], 2)
        finally:
            env.close()

    def test_run_duration_cap_uses_persisted_seconds(self):
        server = make_server()
        server.set("/", Route(body=page_html("Home", TEXT)))
        env = GateEnv(server, pilot_run_minutes_max=1.0)
        try:
            env.admit()
            env.store.budget_add(run_seconds=90.0)
            counters = env.crawler().run(max_fetches=5)
            self.assertEqual(counters.get("stop_reason"), "run_minutes_cap_reached")
            self.assertEqual(server.hits, [])
            report = build_report(env.store, env.staging, env.config)
            self.assertEqual(report["pilot_budget"]["caps"]["run_minutes_max"], 1.0)
        finally:
            env.close()


class NoveltyPinTests(unittest.TestCase):
    def _index(self, tmp: Path) -> Path:
        path = tmp / "historical.sqlite"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE pages(url TEXT)")
        conn.execute("INSERT INTO pages VALUES('https://example.org/a')")
        conn.commit()
        conn.close()
        return path

    def test_wrong_sha_is_refused_before_reading(self):
        tmp = Path(tempfile.mkdtemp(prefix="r3a3f-pin-"))
        staging = StagingIndex(tmp / "staging.sqlite")
        try:
            index = self._index(tmp)
            digest = hashlib.sha256(index.read_bytes()).hexdigest()
            with self.assertRaises(NoveltyPinMismatch):
                overlap(staging, index, expect_sha256="0" * 64)
            block = overlap(staging, index, expect_sha256=digest)
            self.assertTrue(block["pin_match"])
            self.assertEqual(block["historical_index_pages"], 1)
            store = Store(tmp / "crawl.sqlite")
            try:
                report = build_report(store, staging, CrawlConfig(),
                                      historical_index=index,
                                      expected_index_sha256="0" * 64)
            finally:
                store.close()
            self.assertEqual(report["novelty"]["status"], "PIN_MISMATCH")
        finally:
            staging.close()
            shutil.rmtree(tmp, ignore_errors=True)


class OwnerAuthorisationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="r3a3f-auth-"))
        self.store = Store(self.tmp / "crawl.sqlite")

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_real_host_needs_a_distinct_documented_authorisation(self):
        with self.assertRaises(ValueError):
            self.store.add_source(source_id="real", origin="https://example.org",
                                  allowed_paths=["/events"], rights_status="OPEN_LICENCE",
                                  approved=True, index_allowed=True)
        with self.assertRaises(ValueError):
            self.store.add_source(source_id="real", origin="https://example.org",
                                  allowed_paths=["/events"], rights_status="OPEN_LICENCE",
                                  approved=True, index_allowed=True,
                                  owner_authorisation="OPEN_LICENCE")
        source = self.store.add_source(
            source_id="real", origin="https://example.org", allowed_paths=["/events"],
            rights_status="OPEN_LICENCE", approved=True, index_allowed=True,
            owner_authorisation="OWNER_DECISION_2026-11-11_R3A3F")
        self.assertEqual(source["owner_authorisation"], "OWNER_DECISION_2026-11-11_R3A3F")

    def test_synthetic_fixture_keeps_its_explicit_exemption(self):
        source = self.store.add_source(
            source_id="sim", origin="http://127.0.0.1:9", allowed_paths=["/"],
            rights_status="SYNTHETIC_FIXTURE", approved=True, index_allowed=True)
        self.assertEqual(source["approved"], 1)


if __name__ == "__main__":
    unittest.main()
