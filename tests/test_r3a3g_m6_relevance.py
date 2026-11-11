"""M6 relevance metric and judgement-set integrity checks."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.r3a3g_m6_relevance_eval import dcg, key

ROOT = Path(__file__).resolve().parents[1]


class RelevanceMetricTests(unittest.TestCase):
    def test_graded_dcg_rewards_a_relevant_top_result(self):
        self.assertGreater(dcg([3, 0, 0]), dcg([0, 3, 0]))

    def test_url_key_ignores_www_and_trailing_slash(self):
        self.assertEqual(key("https://www.example.org/path/"), "example.org/path")

    def test_judgement_set_is_signed_and_graded(self):
        config = json.loads((ROOT / "config/m6_relevance.json").read_text(encoding="utf-8"))
        self.assertEqual(config["reviewer"], "FB2 internal relevance review")
        self.assertEqual(config["reviewed_at"], "2026-11-11")
        self.assertGreaterEqual(len(config["queries"]), 12)
        for query in config["queries"]:
            self.assertTrue(query["id"])
            self.assertTrue(query["query"])
            self.assertTrue(query["grades"])
            self.assertTrue(all(g in (0, 1, 2, 3) for g in query["grades"].values()))


if __name__ == "__main__":
    unittest.main()
