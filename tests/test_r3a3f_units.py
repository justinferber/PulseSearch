"""Unit gates: canonicalisation, traps, robots precedence, classification."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_crawler_r3a3f import quality  # noqa: E402
from pulse_search_crawler_r3a3f.classify import CATEGORIES, classify  # noqa: E402
from pulse_search_crawler_r3a3f.config import ConfigError, CrawlConfig  # noqa: E402
from pulse_search_crawler_r3a3f.robots import decision_for_status, parse_robots  # noqa: E402
from pulse_search_crawler_r3a3f.urls import (  # noqa: E402
    UrlError,
    canonicalize,
    in_scope,
    is_indexable_shape,
    origin_of,
)


class CanonicalisationTests(unittest.TestCase):
    def test_tracking_fragment_and_default_port_removed(self):
        url = "HTTP://Example.COM:80/a/../b/?utm_source=x&b=2&a=1#frag"
        self.assertEqual(canonicalize(url), "http://example.com/b?a=1&b=2")

    def test_unknown_parameters_are_preserved(self):
        self.assertEqual(canonicalize("https://e.org/x?id=7"), "https://e.org/x?id=7")

    def test_credentials_rejected(self):
        with self.assertRaises(UrlError):
            canonicalize("https://user:pass@example.com/x")

    def test_unsupported_scheme_rejected(self):
        for bad in ("file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)"):
            with self.assertRaises(UrlError):
                canonicalize(bad)

    def test_origin_and_scope(self):
        self.assertEqual(origin_of("https://Berlin.de:443/events/x"), "https://berlin.de")
        self.assertTrue(in_scope("https://b.de/events/x", "https://b.de", ["/events"]))
        self.assertFalse(in_scope("https://b.de/other", "https://b.de", ["/events"]))


class TrapTests(unittest.TestCase):
    def test_infinite_pagination_refused(self):
        self.assertFalse(is_indexable_shape("https://e.org/cal?page=1000")[0])
        self.assertTrue(is_indexable_shape("https://e.org/cal?page=2")[0])

    def test_repeated_segments_and_assets_refused(self):
        self.assertFalse(is_indexable_shape("https://e.org/a/b/a/b/a")[0])
        self.assertFalse(is_indexable_shape("https://e.org/poster.png")[0])

    def test_session_identifier_refused(self):
        self.assertFalse(is_indexable_shape("https://e.org/x?phpsessid=abc")[0])


class RobotsTests(unittest.TestCase):
    def test_longest_match_wins(self):
        rules = parse_robots(
            "User-agent: *\nDisallow: /events\nAllow: /events/public\n",
            "PulseSearchFB2/0.1",
        )
        self.assertTrue(rules.can_fetch("/events/public/one"))
        self.assertFalse(rules.can_fetch("/events/private"))

    def test_equal_length_tie_breaks_toward_allow(self):
        rules = parse_robots("User-agent: *\nDisallow: /x\nAllow: /x\n", "Bot/1")
        self.assertTrue(rules.can_fetch("/x"))

    def test_wildcard_and_end_anchor(self):
        rules = parse_robots("User-agent: *\nDisallow: /*.pdf$\n", "PulseSearchFB2/0.1")
        self.assertFalse(rules.can_fetch("/docs/a.pdf"))
        self.assertTrue(rules.can_fetch("/docs/a.pdf.html"))

    def test_specific_agent_group_beats_star(self):
        text = "User-agent: *\nAllow: /\n\nUser-agent: PulseSearchFB2\nDisallow: /\n"
        rules = parse_robots(text, "PulseSearchFB2/0.1")
        self.assertFalse(rules.can_fetch("/anything"))
        star = parse_robots(text, "OtherBot/1.0")
        self.assertTrue(star.can_fetch("/anything"))

    def test_fail_closed_statuses(self):
        self.assertTrue(decision_for_status(503, b"", "Bot/1").deny_all)
        self.assertTrue(decision_for_status(403, b"", "Bot/1").deny_all)
        self.assertTrue(decision_for_status(404, b"", "Bot/1").allow_all)

    def test_crawl_delay_and_sitemap_parsed(self):
        rules = parse_robots(
            "User-agent: *\nCrawl-delay: 7\nSitemap: https://e.org/sitemap.xml\n", "Bot/1")
        self.assertEqual(rules.crawl_delay, 7.0)
        self.assertEqual(rules.sitemaps, ["https://e.org/sitemap.xml"])


class ClassificationTests(unittest.TestCase):
    def test_taxonomy_is_eighteen(self):
        self.assertEqual(len(CATEGORIES), 18)
        self.assertEqual(len(set(CATEGORIES)), 18)

    def test_diwali_and_stadtfest_are_festivals(self):
        for title, text in (
            ("Diwali celebration Berlin 2026", "Diwali festival of lights with lanterns and music."),
            ("Stadtfest Berlin 2026", "Stadtfest Berlin street festival with market stalls."),
        ):
            result = classify(title, text, "/events/x")
            self.assertEqual(result.primary, "Festival")
            self.assertGreater(result.confidence, 0.2)

    def test_csd_and_pride_are_pride_and_community(self):
        result = classify("CSD Berlin pride 2026",
                          "CSD Berlin Pride parade and LGBTQ community festival.", "/events/csd")
        self.assertEqual(result.primary, "Pride & Community")

    def test_sport_and_horticulture(self):
        self.assertEqual(classify("Berlin half marathon", "The 10k race and marathon route.",
                                  "/sport").primary, "Sport & Fitness")
        self.assertEqual(classify("Spring flower show", "Horticulture and garden show displays.",
                                  "/flowers").primary, "Horticulture & Flower Shows")

    def test_unrelated_page_is_uncertain(self):
        result = classify("Opening times", "General information about local services.", "/x")
        self.assertTrue(result.uncertain)
        self.assertEqual(result.primary, "Other")


class QualityTests(unittest.TestCase):
    def test_jaccard_of_identical_text(self):
        a = set(quality.shingles("the quick brown fox jumps over the lazy dog again and again"))
        self.assertEqual(quality.jaccard(a, a), 1.0)

    def test_near_duplicate_scores_high(self):
        base = "community hall hosts conferences markets and workshops with a kitchen and stage " * 3
        a = set(quality.shingles(base))
        b = set(quality.shingles(base + " parking"))
        self.assertGreater(quality.jaccard(a, b), 0.8)

    def test_thin_content_rejected(self):
        ok, reason = quality.is_acceptable_text("too short", 250)
        self.assertFalse(ok)
        self.assertEqual(reason, "thin_content")


class ConfigTests(unittest.TestCase):
    def test_live_crawl_requires_three_second_spacing(self):
        with self.assertRaises(ConfigError):
            CrawlConfig(min_interval_s=0.5).validate()

    def test_loopback_requires_host_allowlist(self):
        with self.assertRaises(ConfigError):
            CrawlConfig(allow_loopback=True, min_interval_s=0.0).validate()

    def test_depth_four_config_rejected(self):
        with self.assertRaises(ConfigError):
            CrawlConfig(max_depth=4).validate()

    def test_simulator_config_valid(self):
        CrawlConfig(allow_loopback=True, min_interval_s=0.0,
                    loopback_hosts=("127.0.0.1:8080",)).validate()


if __name__ == "__main__":
    unittest.main()
