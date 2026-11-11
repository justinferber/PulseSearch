"""Read-only R3-A3C grading regression tests. Does not run search or validate fact claims."""
import csv
import unittest
from pathlib import Path

from tools.grade_independent import assess


ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "data" / "frozen_54.csv"


class IndependentGradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with FROZEN.open(newline="", encoding="utf-8") as f:
            cls.questions = list(csv.DictReader(f))

    def test_frozen_54_unique_and_previous_questions_intact(self):
        self.assertEqual(len(self.questions), 54)
        self.assertEqual(len({q["probe_id"] for q in self.questions}), 54)
        self.assertEqual(sum(q["kind"] == "no_result" for q in self.questions), 10)
        self.assertEqual(sum(q["kind"] == "fact_unverified" for q in self.questions), 11)
        self.assertIn("exclude_diwali", {q["probe_id"] for q in self.questions})

    def test_no_fake_grade_without_replay(self):
        report = assess(self.questions, [], [])
        self.assertEqual(report["signed_candidate_judgements"], 0)
        self.assertEqual(report["candidate_rows_loaded"], 0)
        self.assertIn("HOLD", report["overall_decision"])

    def test_one_signed_grade_yields_partial_metrics_not_acceptance(self):
        p = self.questions[0]["probe_id"]
        results = [{"probe_id": p, "engine": "A", "rank": "1",
                    "title": "Example", "url": "https://example.org/"}]
        grades = [{"probe_id": p, "engine": "A", "rank": "1",
                   "relevance": "3", "reviewer_id": "independent-r1",
                   "source_verified": "NO"}]
        report = assess(self.questions, results, grades)
        self.assertEqual(report["by_engine"]["A"]["precision_at_1_signed_subset"], 1.0)
        self.assertEqual(report["by_engine"]["A"]["queries_with_signed_top5_labels"], 1)
        self.assertEqual(report["source_verified_judgements"], 0)
        self.assertIn("HOLD", report["overall_decision"])

    def test_unsigned_labels_rejected(self):
        p = self.questions[0]["probe_id"]
        results = [{"probe_id": p, "engine": "A", "rank": "1",
                    "title": "Example", "url": "https://example.org/"}]
        grades = [{"probe_id": p, "engine": "A", "rank": "1",
                   "relevance": "3", "reviewer_id": "", "source_verified": "YES"}]
        with self.assertRaises(ValueError):
            assess(self.questions, results, grades)


if __name__ == "__main__":
    unittest.main()
