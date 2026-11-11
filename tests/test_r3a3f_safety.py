"""Safety gates: SSRF, redirect revalidation, body bounds, scheme limits."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_crawler_r3a3f import netguard  # noqa: E402
from pulse_search_crawler_r3a3f.config import CrawlConfig  # noqa: E402
from pulse_search_crawler_r3a3f.safe_fetch import Fetcher  # noqa: E402
from pulse_search_crawler_r3a3f.sitesim import Route, RouteServer, page_html  # noqa: E402


def loopback_fetcher() -> Fetcher:
    return Fetcher(CrawlConfig(allow_loopback=True, min_interval_s=0.0,
                               loopback_hosts=("127.0.0.1",), timeout_s=5.0))


class NetguardTests(unittest.TestCase):
    def test_loopback_blocked_by_default(self):
        with self.assertRaises(netguard.UnsafeTarget):
            netguard.resolve_public("127.0.0.1", 80)

    def test_loopback_allowed_only_when_opted_in(self):
        self.assertEqual(netguard.resolve_public("127.0.0.1", 80, allow_loopback=True), "127.0.0.1")

    def test_private_and_link_local_blocked(self):
        for address in ("10.1.2.3", "192.168.1.10", "172.16.0.5", "169.254.169.254"):
            with self.assertRaises(netguard.UnsafeTarget):
                netguard.resolve_public(address, 80, allow_loopback=True)

    def test_metadata_hostname_blocked(self):
        with self.assertRaises(netguard.UnsafeTarget):
            netguard.resolve_public("metadata.google.internal", 80, allow_loopback=True)


class FetchSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = RouteServer().start()
        cls.server.set("/ok", Route(body=page_html("OK page", "Safe body text.")))
        cls.server.set("/go-private", Route(status=302, headers={"Location": "http://10.0.0.5/"}))
        cls.server.set("/big", Route(body=b"x" * 400_000,
                                     mime="text/html; charset=utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_public_mode_refuses_loopback(self):
        fetcher = Fetcher(CrawlConfig())
        result = fetcher.fetch(self.server.base + "/ok")
        self.assertIn("unsafe_target", result.error)

    def test_loopback_fetch_succeeds_when_explicitly_allowed(self):
        result = loopback_fetcher().fetch(self.server.base + "/ok")
        self.assertTrue(result.ok, result.error)
        self.assertIn("OK page", result.body.decode())

    def test_redirect_to_private_address_is_blocked(self):
        result = loopback_fetcher().fetch(self.server.base + "/go-private")
        self.assertIn("unsafe_target", result.error)
        self.assertGreaterEqual(len(result.chain), 2)

    def test_unsupported_scheme_rejected(self):
        result = loopback_fetcher().fetch("file:///etc/passwd")
        self.assertIn("scheme_not_allowed", result.error)

    def test_body_cap_enforced(self):
        result = loopback_fetcher().fetch(self.server.base + "/big", max_bytes=1000)
        self.assertTrue(result.error in ("declared_oversize", "") , result.error)
        if not result.error:
            self.assertTrue(result.truncated)
        self.assertLessEqual(len(result.body), 1000)

    def test_redirect_limit(self):
        cfg = CrawlConfig(allow_loopback=True, min_interval_s=0.0,
                          loopback_hosts=("127.0.0.1",), max_redirects=1)
        server = RouteServer().start()
        try:
            server.set("/a", Route(status=302, headers={"Location": "/b"}))
            server.set("/b", Route(status=302, headers={"Location": "/c"}))
            server.set("/c", Route(body=page_html("C", "End of chain.")))
            result = Fetcher(cfg).fetch(server.base + "/a")
            self.assertEqual(result.error, "too_many_redirects")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
