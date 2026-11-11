"""Adversarial redirect tests: a destination is a new URL, not an exemption.

Every redirect hop must pass approved-source, path-scope, robots, request-budget
and pacing checks before its request is issued. Off-origin redirects are refused
even when the target host is public and separately admitted.
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

ALLOW = b"User-agent: *\nAllow: /\n"
FILLER = (" Visitors can find practical details here, including dates, opening times, "
          "accessibility, transport and contact information for the organisers.")


class FakeClock:
    def __init__(self, start: float = 1_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def page(title: str, text: str, links: list | None = None) -> Route:
    return Route(body=page_html(title, text + FILLER, links=links))


def make_server(robots: bytes = ALLOW) -> RouteServer:
    server = RouteServer().start()
    server.set("/robots.txt", Route(body=robots, mime="text/plain; charset=utf-8"))
    return server


class Env:
    def __init__(self, servers: list[RouteServer], **config_kwargs):
        self.tmp = Path(tempfile.mkdtemp(prefix="r3a3f-redirect-"))
        self.servers = servers
        self.store = Store(self.tmp / "crawl.sqlite")
        self.staging = StagingIndex(self.tmp / "staging.sqlite")
        self.config = CrawlConfig(
            allow_loopback=True, min_interval_s=0.0,
            loopback_hosts=tuple(s.base.replace("http://", "") for s in servers),
            max_depth=3, **config_kwargs)

    def admit(self, source_id: str, server: RouteServer, paths=("/",), seed: str = "/"):
        self.store.add_source(
            source_id=source_id, origin=server.base, allowed_paths=list(paths),
            rights_status="SYNTHETIC_FIXTURE", approved=True, index_allowed=True)
        if seed:
            self.store.add_seed(source_id, server.base + seed)

    def crawl(self, budget: int = 10, clock=None) -> dict:
        crawler = (Crawler(self.store, self.staging, self.config)
                   if clock is None else
                   Crawler(self.store, self.staging, self.config,
                           clock=clock, sleep=clock.sleep))
        for seed in self.store.seeds():
            crawler.register_seed(seed["source_id"], seed["url"])
        self.last_crawler = crawler
        return crawler.run(max_fetches=budget)

    def rows(self, sql: str, args: tuple = ()) -> list[dict]:
        return [dict(r) for r in self.store.conn.execute(sql, args)]

    def close(self) -> None:
        self.store.close()
        self.staging.close()
        for server in self.servers:
            server.shutdown()
            server.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)


class RedirectGateTests(unittest.TestCase):
    def test_in_scope_chain_is_followed_logged_and_paced(self):
        server = make_server(b"User-agent: *\nAllow: /\nCrawl-delay: 3\n")
        server.set("/", page("Venue home", "Community venue programme.",
                             links=[("/hop0", "Start")]))
        server.set("/hop0", Route(status=302, headers={"Location": "/events/one"}))
        server.set("/events/one", Route(status=302, headers={"Location": "/events/two"}))
        server.set("/events/two", page("Festival listing", "Festival with music and stalls."))
        env = Env([server])
        clock = FakeClock()
        try:
            env.admit("site", server)
            env.crawl(budget=4, clock=clock)
            report = build_report(env.store, env.staging, env.config)
            self.assertEqual(report["redirects"]["followed_hops"], 2)
            self.assertEqual(report["redirects"]["blocked_hops"], 0)
            log = env.rows("SELECT * FROM redirect_log ORDER BY hop")
            self.assertEqual([row["decision"] for row in log], ["followed", "followed"])
            self.assertEqual([row["hop"] for row in log], [1, 2])
            self.assertIsNotNone(env.staging.get(server.base + "/hop0"))
            # robots (Crawl-delay 3) then two redirect hops each wait their turn.
            self.assertGreaterEqual(env.last_crawler.pacer.total_waited_s, 9.0)
        finally:
            env.close()

    def test_off_origin_redirect_to_an_admitted_host_is_blocked(self):
        first = make_server()
        second = make_server()
        first.set("/", page("Venue home", "Community venue programme.",
                            links=[("/go", "Partner")]))
        first.set("/go", Route(status=302, headers={"Location": second.base + "/events"}))
        second.set("/events", page("Partner events", "Festival programme on another host."))
        env = Env([first, second])
        try:
            env.admit("first", first)
            env.admit("second", second, seed="")
            counters = env.crawl(budget=6)
            self.assertEqual(second.hits, [])
            self.assertGreaterEqual(counters.get("redirect_blocked_off_origin", 0), 1)
            blocked = env.rows(
                "SELECT * FROM redirect_log WHERE decision='blocked'")
            self.assertEqual(blocked[0]["reason"], "off_origin")
        finally:
            env.close()

    def test_out_of_scope_redirect_is_blocked(self):
        server = make_server()
        server.set("/events", page("Events", "Festival programme listing.",
                                   links=[("/events/go", "Details")]))
        server.set("/events/go", Route(status=302, headers={"Location": "/private/notes"}))
        server.set("/private/notes", page("Private notes", "Internal notes about the venue."))
        env = Env([server])
        try:
            env.admit("site", server, paths=["/events"], seed="/events")
            env.crawl(budget=6)
            self.assertEqual(server.hits_for("/private"), 0)
            blocked = env.rows("SELECT * FROM redirect_log WHERE decision='blocked'")
            self.assertEqual(blocked[0]["reason"], "out_of_scope")
        finally:
            env.close()

    def test_robots_denied_redirect_is_blocked(self):
        server = make_server(b"User-agent: *\nAllow: /\nDisallow: /private\n")
        server.set("/", page("Venue home", "Community venue programme.",
                             links=[("/go", "Members")]))
        server.set("/go", Route(status=302, headers={"Location": "/private/secret"}))
        server.set("/private/secret", page("Private page", "Members page about the venue."))
        env = Env([server])
        try:
            env.admit("site", server)
            counters = env.crawl(budget=6)
            self.assertEqual(server.hits_for("/private"), 0)
            self.assertGreaterEqual(counters.get("redirect_blocked_robots_denied", 0), 1)
            blocked = env.rows("SELECT * FROM redirect_log WHERE decision='blocked'")
            self.assertEqual(blocked[0]["reason"], "robots_denied")
        finally:
            env.close()

    def test_redirect_chain_stops_at_the_request_budget(self):
        server = make_server()
        server.set("/a", Route(status=302, headers={"Location": "/b"}))
        server.set("/b", Route(status=302, headers={"Location": "/c"}))
        server.set("/c", page("End", "Festival programme at the end of the chain."))
        # max_redirects=1 -> request ceiling for one claimed URL is 2.
        env = Env([server], max_redirects=1)
        try:
            env.admit("site", server, seed="/a")
            env.crawl(budget=1)
            blocked = env.rows("SELECT * FROM redirect_log WHERE decision='blocked'")
            self.assertTrue(blocked)
            self.assertEqual(blocked[0]["reason"], "request_budget_exhausted")
            self.assertLessEqual(env.last_crawler.fetcher.requests, 2)
        finally:
            env.close()

    def test_off_origin_redirect_to_unresolvable_host_never_resolves(self):
        server = make_server()
        server.set("/", page("Venue home", "Community venue programme.",
                             links=[("/go", "Elsewhere")]))
        server.set("/go", Route(status=302,
                                headers={"Location": "https://outside.invalid/events"}))
        env = Env([server])
        try:
            env.admit("site", server)
            counters = env.crawl(budget=4)
            self.assertGreaterEqual(counters.get("redirect_blocked_off_origin", 0), 1)
            self.assertEqual(counters.get("fetch_error", 0), 0)
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
