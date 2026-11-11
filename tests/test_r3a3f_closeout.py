"""Closeout regressions: robots redirects, admin routes, tracked artefacts.

robots.txt is fetched before the per-URL redirect gate has a row, so it needs
its own authority check. A redirect there must not reach an unapproved host or
bypass pacing, the run ceiling or the daily attempt ledger.
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
from pulse_search_crawler_r3a3f.sitesim import Route, RouteServer, page_html  # noqa: E402
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402
from pulse_search_crawler_r3a3f.store import Store  # noqa: E402

TEXT = ("Community venue programme with dates, opening times, accessibility, transport "
        "and contact information for visitors and organisers.")


class VirtualClock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class Env:
    def __init__(self, servers: list[RouteServer], **kwargs):
        self.tmp = Path(tempfile.mkdtemp(prefix="r3a3f-closeout-"))
        self.servers = servers
        self.store = Store(self.tmp / "crawl.sqlite")
        self.staging = StagingIndex(self.tmp / "staging.sqlite")
        self.config = CrawlConfig(
            allow_loopback=True, min_interval_s=kwargs.pop("min_interval_s", 0.0),
            loopback_hosts=tuple(s.base.replace("http://", "") for s in servers),
            max_depth=3, **kwargs)
        self.clock = VirtualClock()
        self.crawler = Crawler(self.store, self.staging, self.config,
                               clock=self.clock, sleep=self.clock.sleep)

    def admit(self, server: RouteServer, source_id: str = "site", seed: str = "/"):
        self.store.add_source(
            source_id=source_id, origin=server.base, allowed_paths=["/"],
            rights_status="SYNTHETIC_FIXTURE", approved=True, index_allowed=True,
            owner_authorisation="OFFLINE_SIMULATION_ONLY")
        self.store.add_seed(source_id, server.base + seed)

    def run(self, budget: int = 10) -> dict:
        for seed in self.store.seeds():
            self.crawler.register_seed(seed["source_id"], seed["url"])
        return self.crawler.run(max_fetches=budget)

    def rows(self, sql: str) -> list[dict]:
        return [dict(row) for row in self.store.conn.execute(sql)]

    def close(self) -> None:
        self.store.close()
        self.staging.close()
        for server in self.servers:
            server.shutdown()
            server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)


class RobotsRedirectTests(unittest.TestCase):
    def test_off_origin_robots_redirect_is_blocked_before_the_request(self):
        origin = RouteServer().start()
        outside = RouteServer().start()
        outside.set("/robots.txt", Route(body=b"User-agent: *\nAllow: /\n",
                                         mime="text/plain; charset=utf-8"))
        origin.set("/robots.txt", Route(
            status=301, headers={"Location": outside.base + "/robots.txt"}))
        origin.set("/", Route(body=page_html("Venue", TEXT)))
        env = Env([origin, outside])
        try:
            env.admit(origin)
            counters = env.run(budget=4)
            self.assertEqual(outside.hits, [])
            self.assertEqual(origin.hits_for("/robots.txt"), 1)
            self.assertNotIn("/", origin.hits)
            blocked = env.rows(
                "SELECT * FROM redirect_log WHERE decision='blocked'")
            self.assertTrue(blocked)
            self.assertEqual(blocked[0]["reason"], "off_origin")
            self.assertEqual(blocked[0]["source_id"], "site")
            # A refused robots fetch fails closed: no content request follows.
            self.assertEqual(counters.get("reject_robots_denied", 0), 1)
        finally:
            env.close()

    def test_same_origin_robots_redirect_is_followed_paced_and_counted(self):
        origin = RouteServer().start()
        origin.set("/robots.txt", Route(
            status=302, headers={"Location": "/robots-real.txt"}))
        origin.set("/robots-real.txt", Route(
            body=b"User-agent: *\nAllow: /\nCrawl-delay: 3\n",
            mime="text/plain; charset=utf-8"))
        origin.set("/", Route(body=page_html("Venue", TEXT)))
        env = Env([origin], min_interval_s=3.0)
        try:
            env.admit(origin)
            env.run(budget=3)
            self.assertEqual(origin.hits_for("/robots-real.txt"), 1)
            self.assertIn("/", origin.hits)
            self.assertIsNotNone(env.staging.get(origin.base + "/"))
            followed = env.rows(
                "SELECT * FROM redirect_log WHERE decision='followed'")
            self.assertTrue(followed)
            self.assertEqual(followed[0]["hop"], 1)
            # robots, its redirect, then content: all three attempts counted.
            self.assertGreaterEqual(env.store.budget_snapshot()["http_attempts"], 3)
            # Three requests, two pacing gaps of at least 3s: robots -> its
            # redirect -> content.
            self.assertGreaterEqual(env.crawler.pacer.total_waited_s, 6.0)
        finally:
            env.close()

    def test_robots_redirect_destination_respects_the_daily_attempt_cap(self):
        origin = RouteServer().start()
        origin.set("/robots.txt", Route(
            status=302, headers={"Location": "/robots-real.txt"}))
        origin.set("/robots-real.txt", Route(
            body=b"User-agent: *\nAllow: /\n", mime="text/plain; charset=utf-8"))
        origin.set("/", Route(body=page_html("Venue", TEXT)))
        env = Env([origin], pilot_http_attempts_per_day=1)
        try:
            env.admit(origin)
            counters = env.run(budget=3)
            self.assertEqual(env.store.budget_snapshot()["http_attempts"], 1)
            self.assertEqual(origin.hits_for("/robots-real.txt"), 0)
            self.assertNotIn("/", origin.hits)
            self.assertIn(counters.get("stop_reason"),
                          {"http_attempts_cap_reached", "queue_empty"})
        finally:
            env.close()


class AdministrativeRouteTests(unittest.TestCase):
    def test_admin_links_are_never_queued_or_fetched(self):
        server = RouteServer().start()
        server.set("/robots.txt", Route(body=b"User-agent: *\nAllow: /\n",
                                        mime="text/plain; charset=utf-8"))
        server.set("/", Route(body=page_html(
            "Venue", TEXT,
            links=["/admin/panel", "/wp-admin/", "/login", "/events/programme"])))
        server.set("/events/programme", Route(body=page_html(
            "Programme", TEXT)))
        for path in ("/admin/panel", "/wp-admin/", "/login"):
            server.set(path, Route(body=page_html("Admin", TEXT)))
        env = Env([server])
        try:
            env.admit(server)
            counters = env.run(budget=10)
            for path in ("/admin/", "/wp-admin/", "/login"):
                self.assertEqual(server.hits_for(path), 0, path)
            self.assertGreaterEqual(counters.get("trap_refused", 0), 3)
            urls = {row["url"] for row in env.rows("SELECT url FROM frontier")}
            self.assertFalse(any("/admin/" in url or "/wp-admin/" in url
                                 or url.endswith("/login") for url in urls))
            report = build_report(env.store, env.staging, env.config)
            self.assertEqual(report["depth"]["depth4_fetches"], 0)
        finally:
            env.close()

    def test_staging_refuses_an_administrative_document_directly(self):
        tmp = Path(tempfile.mkdtemp(prefix="r3a3f-admin-"))
        staging = StagingIndex(tmp / "staging.sqlite")
        try:
            indexed, outcome = staging.add_document({
                "url": "https://example.org/admin/panel", "source_id": "site",
                "title": "Admin panel", "snippet": "Admin", "category": "Other",
                "category_confidence": 0.1, "categories": ["Other"], "depth": 1,
                "fetched_at": "2026-11-11T00:00:00+00:00", "content_hash": "x",
            }, [1, 2, 3], index_allowed=True)
            self.assertFalse(indexed)
            self.assertEqual(outcome, "administrative_path")
            self.assertEqual(staging.search("Admin panel", None, 10), [])
        finally:
            staging.close()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
