"""Guardrails for the M7 open-set relevance benchmark."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class M7UnseenBenchmarkTests(unittest.TestCase):
    def test_has_at_least_twenty_new_questions(self):
        m6 = json.loads((ROOT / "config/m6_relevance.json").read_text(encoding="utf-8"))
        m7 = json.loads((ROOT / "config/m7_unseen_questions.json").read_text(encoding="utf-8"))
        old = {q["query"].strip().lower() for q in m6["queries"]}
        new = {q["query"].strip().lower() for q in m7["queries"]}
        self.assertGreaterEqual(len(new), 20)
        self.assertFalse(old & new, "M7 questions must not overlap the M6 tuning set")
        self.assertTrue(m7.get("reviewer"))
        self.assertTrue(m7.get("reviewed_at"))
        for query in m7["queries"]:
            self.assertTrue(query.get("id"))
            for grade in (query.get("grades") or {}).values():
                self.assertIn(int(grade), (0, 1, 2, 3))


if __name__ == "__main__":
    unittest.main()
