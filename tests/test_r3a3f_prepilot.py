"""Pre-pilot safeguards, one class per review finding.

1. Fail-closed source admission and indexing.
2. Guessed listing probes are separate from genuine links, with provenance.
3. Per-host pacing covers robots, content, long delays and Retry-After.
4. Temporary 404 listing pages are rechecked on a bounded schedule.
5. Source fairness under a fixed budget, and measured useful discoveries.

Everything runs on loopback against RouteServer; no third party is contacted.
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
from pulse_search_crawler_r3a3f.pacing import HostPacer  # noqa: E402
from pulse_search_crawler_r3a3f.sitesim import Route, RouteServer, page_html  # noqa: E402
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402
from pulse_search_crawler_r3a3f.store import Store, utc_now  # noqa: E402

ALLOW = b"User-agent: *\nAllow: /\n"
FILLER = (" Visitors can find practical details for this listing here, including dates, "
          "opening times, accessibility, transport and contact information. The organisers "
          "publish programme updates and any changes to the schedule on this page.")


class FakeClock:
    """Deterministic clock so pacing waits assert exactly without sleeping."""

    def __init__(self, start: float = 1_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def make_server(robots: bytes = ALLOW) -> RouteServer:
    server = RouteServer().start()
    server.set("/robots.txt", Route(body=robots, mime="text/plain; charset=utf-8"))
    return server


def page(title: str, text: str, links: list | None = None) -> Route:
    return Route(body=page_html(title, text + FILLER, links=links))


class Env:
    """One isolated store + staging + loopback config per test."""

    def __init__(self, servers: list[RouteServer], **config_kwargs):
        self.tmp = Path(tempfile.mkdtemp(prefix="r3a3f-prepilot-"))
        self.servers = servers
        self.store = Store(self.tmp / "crawl.sqlite")
        self.staging = StagingIndex(self.tmp / "staging.sqlite")
        self.config = CrawlConfig(
            allow_loopback=True,
            min_interval_s=0.0,
            loopback_hosts=tuple(s.base.replace("http://", "") for s in servers),
            max_depth=3,
            **config_kwargs,
        )

    def admit(self, source_id: str, server: RouteServer, seed: str = "/",
              probes: list[str] | None = None, budget: int = 0,
              index_allowed: bool = True) -> dict:
        source = self.store.add_source(
            source_id=source_id, origin=server.base, allowed_paths=["/"],
            rights_status="SYNTHETIC_FIXTURE", approved=True,
            index_allowed=index_allowed, probe_policy=probes or [],
            probe_budget_per_run=budget,
        )
        if seed:
            self.store.add_seed(source_id, server.base + seed)
        return source

    def crawl(self, budget: int = 20, clock=None) -> dict:
        if clock is None:
            crawler = Crawler(self.store, self.staging, self.config)
        else:
            crawler = Crawler(self.store, self.staging, self.config,
                              clock=clock, sleep=clock.sleep)
        for seed in self.store.seeds():
            self.store.enqueue(seed["url"], source_id=seed["source_id"],
                               seed_id=seed["seed_id"], parent_url=None, depth=0,
                               max_depth=self.config.max_depth, method="seed",
                               approval_ref=f"source:{seed['source_id']}:admitted_seed")
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


class FailClosedTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server()
        self.env = Env([self.server])

    def tearDown(self):
        self.env.close()

    def test_new_source_defaults_to_unadmitted_and_unindexable(self):
        source = self.env.store.add_source(
            source_id="pending", origin=self.server.base, allowed_paths=["/"])
        self.assertFalse(source["approved"])
        self.assertFalse(source["index_allowed"])
        self.assertEqual(source["probe_policy"], "[]")
        with self.assertRaises(ValueError):
            self.env.store.add_seed("pending", self.server.base + "/")

    def test_unapproved_frontier_row_is_rejected_without_a_request(self):
        self.env.store.add_source(
            source_id="pending", origin=self.server.base, allowed_paths=["/"])
        self.env.store.conn.execute(
            """INSERT INTO frontier(url,source_id,seed_id,parent_url,min_depth,state,
                 priority,category_hint,discovery_method,approval_ref,discovered_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (self.server.base + "/", "pending", None, None, 0, "queued", 100,
             None, "seed", None, utc_now()),
        )
        self.env.store.conn.commit()
        counters = self.env.crawl(budget=5)
        self.assertEqual(counters.get("reject_unapproved_source"), 1)
        self.assertEqual(self.server.hits, [])
        self.assertEqual(self.env.staging.stats()["documents"], 0)

    def test_reimport_cannot_deapprove_an_admitted_source(self):
        self.env.admit("site", self.server)
        with self.assertRaises(ValueError):
            self.env.store.add_source(source_id="site", origin=self.server.base,
                                      allowed_paths=["/"], approved=False,
                                      index_allowed=False)

    def test_staging_index_requires_explicit_approval(self):
        record = {
            "url": "https://example.org/a", "source_id": "site", "title": "A",
            "snippet": "a", "category": "Festival", "category_confidence": 0.9,
            "categories": {}, "depth": 1, "fetched_at": utc_now(),
            "content_hash": "hash",
        }
        indexed, outcome = self.env.staging.add_document(record, [])
        self.assertFalse(indexed)
        self.assertEqual(outcome, "rights_denied_index")
        self.assertEqual(self.env.staging.stats()["documents"], 0)
        indexed, outcome = self.env.staging.add_document(record, [], index_allowed=True)
        self.assertTrue(indexed)
        self.assertEqual(outcome, "indexed")

    def test_fetchable_but_unindexable_source_is_not_indexed(self):
        self.server.set("/", page("Festival in Berlin", "Festival programme with live music."))
        self.env.admit("site", self.server, index_allowed=False)
        counters = self.env.crawl(budget=5)
        self.assertGreaterEqual(counters.get("reject_rights_denied_index", 0), 1)
        self.assertEqual(self.env.staging.stats()["documents"], 0)


class ProbeProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server()
        self.server.set("/", page(
            "Venue home", "Community venue with festival and market programme.",
            links=[("/child", "Event child")]))
        self.server.set("/child", page("Festival child", "Festival with music and stalls."))
        self.server.set("/probe", page("Market probe", "Market stalls and local vendors."))
        self.env = Env([self.server])

    def tearDown(self):
        self.env.close()

    def test_probe_is_labelled_and_claims_no_parent(self):
        self.env.admit("site", self.server, probes=["/probe"], budget=1)
        self.env.crawl(budget=10)
        probes = self.env.rows(
            "SELECT * FROM frontier WHERE discovery_method='guessed_path_probe'")
        self.assertEqual(len(probes), 1)
        self.assertIsNone(probes[0]["parent_url"])
        self.assertEqual(probes[0]["approval_ref"], "source:site:probe_policy")
        links = self.env.rows(
            "SELECT * FROM frontier WHERE discovery_method='link' AND url LIKE '%/child'")
        self.assertTrue(links)
        self.assertEqual(links[0]["parent_url"], self.server.base + "/")
        self.assertTrue(links[0]["approval_ref"].startswith("link:"))
        report = build_report(self.env.store, self.env.staging, self.env.config)
        self.assertGreaterEqual(report["discovery"]["genuine_link_discoveries"], 1)
        self.assertEqual(report["discovery"]["guessed_path_probes"], 1)
        self.assertEqual(report["discovery"]["by_method"]["seed"], 1)

    def test_no_probe_policy_means_no_guessed_requests(self):
        self.env.admit("site", self.server)
        self.env.crawl(budget=10)
        self.assertEqual(self.env.rows(
            "SELECT url FROM frontier WHERE discovery_method='guessed_path_probe'"), [])
        self.assertEqual(self.server.hits_for("/probe"), 0)


class PacingTests(unittest.TestCase):
    def setUp(self):
        self.env = Env([make_server()])

    def tearDown(self):
        self.env.close()

    def test_wait_is_not_capped_by_the_socket_timeout(self):
        clock = FakeClock()
        pacer = HostPacer(self.env.store, clock=clock, sleep=clock.sleep)
        host = "example.org"
        self.env.store.host(host)
        self.env.store.note_request(host, clock.now, 600.0)
        decision = pacer.wait(host, 3.0)
        self.assertAlmostEqual(decision.waited_s, 600.0, places=3)
        self.assertAlmostEqual(clock.now, 1_000_600.0, places=3)

    def test_retry_after_blocks_the_host_for_the_full_duration(self):
        clock = FakeClock()
        pacer = HostPacer(self.env.store, clock=clock, sleep=clock.sleep)
        host = "example.org"
        self.env.store.host(host)
        pacer.record_retry_after(host, 900.0)
        decision = pacer.wait(host, 3.0)
        self.assertAlmostEqual(decision.waited_s, 900.0, places=3)

    def test_robots_and_content_share_one_schedule(self):
        server = self.env.servers[0]
        server.set("/robots.txt", Route(
            body=b"User-agent: *\nAllow: /\nCrawl-delay: 7\n",
            mime="text/plain; charset=utf-8"))
        server.set("/", page("Venue home", "Community venue with festival programme."))
        self.env.admit("site", server)
        clock = FakeClock()
        self.env.crawl(budget=3, clock=clock)
        self.assertEqual(len(self.env.rows(
            "SELECT url FROM fetch_log WHERE outcome='robots'")), 1)
        # robots.txt is fetched, then the content request must respect the
        # published Crawl-delay before it is issued.
        self.assertGreaterEqual(self.env.last_crawler.pacer.total_waited_s, 7.0)
        state = self.env.store.host(server.base.replace("http://", ""))
        self.assertAlmostEqual(state["next_allowed_at"] - state["last_request_at"], 7.0,
                               places=3)
        self.assertEqual(self.env.staging.stats()["documents"], 1)

    def test_retry_after_is_stored_for_the_host(self):
        server = self.env.servers[0]
        server.set("/", Route(status=429, body=b"slow down",
                              headers={"Retry-After": "120"}))
        self.env.admit("site", server)
        self.env.crawl(budget=3)
        host = server.base.replace("http://", "")
        state = self.env.store.host(host)
        self.assertGreaterEqual(state["blocked_until"] - state["last_request_at"], 119.0)


class RecheckTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server()
        self.server.set("/", page(
            "Venue home", "Community venue with festival and market programme.",
            links=[("/seasonal", "Seasonal listing"), ("/gone", "Removed listing")]))
        self.server.set("/seasonal", Route(status=404, body=b"not found yet"))
        self.server.set("/gone", Route(status=410, body=b"gone for good"))
        self.env = Env([self.server])

    def tearDown(self):
        self.env.close()

    def test_404_is_scheduled_and_recovered_when_the_listing_appears(self):
        self.env.admit("site", self.server)
        first = self.env.crawl(budget=8)
        self.assertGreaterEqual(first.get("recheck_scheduled", 0), 1)
        row = self.env.rows("SELECT * FROM frontier WHERE url LIKE '%/seasonal'")[0]
        self.assertEqual(row["state"], "recheck")
        self.assertIsNotNone(row["recheck_at"])
        self.assertEqual(row["recheck_count"], 1)

        self.server.set("/seasonal", page("Christmas market listing",
                                          "Christmas market with Advent stalls and gluehwein."))
        self.env.store.conn.execute(
            "UPDATE frontier SET recheck_at='2000-01-01T00:00:00+00:00', "
            "next_retry='2000-01-01T00:00:00+00:00' WHERE url LIKE '%/seasonal'")
        self.env.store.conn.commit()
        self.env.crawl(budget=8)
        doc = self.env.staging.get(self.server.base + "/seasonal")
        self.assertIsNotNone(doc)
        row = self.env.rows("SELECT * FROM frontier WHERE url LIKE '%/seasonal'")[0]
        self.assertEqual(row["state"], "done")
        self.assertEqual(row["recheck_count"], 1)

    def test_410_is_permanent_and_never_rechecked(self):
        self.env.admit("site", self.server)
        counters = self.env.crawl(budget=8)
        self.assertGreaterEqual(counters.get("gone_permanent", 0), 1)
        row = self.env.rows("SELECT * FROM frontier WHERE url LIKE '%/gone'")[0]
        self.assertEqual(row["state"], "blocked")
        self.assertEqual(row["last_error"], "http_410")
        self.assertIsNone(row["recheck_at"])

    def test_rechecks_are_bounded(self):
        env = Env([self.server], max_rechecks=1)
        try:
            env.admit("site", self.server)
            env.crawl(budget=8)
            env.store.conn.execute(
                "UPDATE frontier SET recheck_at='2000-01-01T00:00:00+00:00', "
                "next_retry='2000-01-01T00:00:00+00:00' WHERE state='recheck'")
            env.store.conn.commit()
            counters = env.crawl(budget=8)
            self.assertGreaterEqual(counters.get("gone_after_rechecks", 0), 1)
            row = env.rows("SELECT * FROM frontier WHERE url LIKE '%/seasonal'")[0]
            self.assertEqual(row["state"], "blocked")
        finally:
            env.close()


class FairnessTests(unittest.TestCase):
    def _fanout_server(self, prefix: str, children: int) -> RouteServer:
        server = make_server()
        links = [(f"/{prefix}-{i}", f"Listing {i}") for i in range(children)]
        server.set("/", page(f"{prefix} hub", "Community festival listings index page.",
                             links=links))
        for i in range(children):
            server.set(f"/{prefix}-{i}", page(
                f"{prefix} festival listing {i}",
                "Festival programme with live music, market stalls and a parade."))
        return server

    def test_budget_is_shared_across_approved_sources(self):
        servers = [self._fanout_server(f"a{n}", 8) for n in range(3)]
        env = Env(servers)
        try:
            for index, server in enumerate(servers):
                env.admit(f"source-{index}", server)
            counters = env.crawl(budget=24)
            report = build_report(env.store, env.staging, env.config)
            fetches = report["fairness"]["fetches_by_source"]
            self.assertEqual(len(fetches), 3)
            self.assertTrue(all(count >= 4 for count in fetches.values()), fetches)
            self.assertLessEqual(report["fairness"]["max_source_share"], 0.7)
            self.assertEqual(report["fairness"]["fairness_mode"],
                             "avoid_same_host_then_budget_share_cap")
            self.assertLessEqual(counters["fetched"], 24)
        finally:
            env.close()

    def test_oversized_host_is_capped_and_work_is_deferred(self):
        big = self._fanout_server("big", 30)
        small = make_server()
        small.set("/", page("Small venue", "Community venue with festival programme."))
        env = Env([big, small], max_host_share=0.7)
        try:
            env.admit("big", big)
            env.admit("small", small)
            counters = env.crawl(budget=20)
            report = build_report(env.store, env.staging, env.config)
            cap = 14  # ceil(20 * 0.7)
            self.assertLessEqual(report["fairness"]["fetches_by_source"]["big"], cap)
            self.assertGreaterEqual(report["fairness"]["fetches_by_source"]["small"], 1)
            self.assertEqual(counters["stop_reason"], "host_deferred")
        finally:
            env.close()


class UsefulDiscoveryTests(unittest.TestCase):
    def test_useful_discoveries_are_measured(self):
        server = make_server()
        server.set("/", page("City events hub", "Events calendar and listings.",
                             links=[("/xmas", "Christmas markets 2026"),
                                    ("/pride", "CSD Berlin pride programme")]))
        server.set("/xmas", page("Christmas markets 2026",
                                 "Christmas market with Advent stalls and gluehwein."))
        server.set("/pride", page("CSD Berlin pride 2026",
                                  "CSD Berlin Pride parade and LGBTQ community festival."))
        env = Env([server])
        try:
            env.admit("site", server)
            env.crawl(budget=10)
            report = build_report(env.store, env.staging, env.config)
            discovery = report["discovery"]
            self.assertGreaterEqual(discovery["useful_discoveries"], 2)
            self.assertGreater(discovery["useful_per_100_fetches"], 0)
            intents = {i["slug"]: i["documents"] for i in discovery["intents"]}
            self.assertGreater(intents.get("christmas_markets", 0), 0)
            self.assertGreater(intents.get("pride", 0), 0)
        finally:
            env.close()

    def test_out_of_season_events_are_still_indexed(self):
        server = make_server()
        server.set("/", page("City events hub", "Events calendar and listings.",
                             links=[("/xmas", "Christmas markets 2026")]))
        server.set("/xmas", page("Christmas markets 2026",
                                 "Christmas market with Advent stalls and gluehwein."))
        env = Env([server], focus_month=7)
        try:
            env.admit("site", server)
            env.crawl(budget=6)
            self.assertIsNotNone(env.staging.get(server.base + "/xmas"))
            report = build_report(env.store, env.staging, env.config)
            self.assertEqual(report["discovery"]["seasonal_month"], 7)
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
