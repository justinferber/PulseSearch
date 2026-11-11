#!/usr/bin/env python3
"""R3-A3E hardening tests for the PR #8 review gates.

New dev tree only. The accepted engine is imported read-only; nothing here
touches the owner index, the pinned model or the historical snapshots.

Covered review gates:
  1. fail-closed index/model pins (an unpinned read cannot claim verification)
  2. per-entity coordinated negation, paraphrases and contradictions
  3. deeper retrieval / refill so `limit` is honoured after filtering
  4. partial retrieval is recorded and never reported as complete
  5. query-local negation only: no suppression of Diwali, Pride, CSD or Stadtfest
"""
from __future__ import annotations

import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[1]
SNAPSHOT = REPO / "historical" / "local_snapshot"
sys.path.insert(0, str(REPO / "tools"))

import r3a3e_constraint_layer as layer  # noqa: E402

hc = layer.load_engine(SNAPSHOT)
from hybrid_core import HybridIndex  # noqa: E402

# Origins are real: the accepted engine gates retrieval by query geography, so a
# Berlin edition has to sit on a Berlin origin to be retrievable at all.
CORPUS = [
    ("https://www.london.gov.uk", "/events/diwali-square-2025", "Diwali on the Square 2025"),
    ("https://www.london.gov.uk", "/events/diwali-square-2026", "Diwali on the Square 2026"),
    ("https://www.berlin.de", "/events/pride-berlin-2026", "Pride Berlin 2026"),
    ("https://www.berlin.de", "/events/csd-berlin-2026", "CSD Berlin 2026"),
    ("https://www.berlin.de", "/events/stadtfest-berlin-2026", "Stadtfest Berlin 2026"),
    ("https://www.london.gov.uk", "/events/london-open-house-2023", "London Open House 2023"),
    ("https://www.london.gov.uk", "/events/london-open-house-2024", "London Open House 2024"),
    ("https://www.london.gov.uk", "/events/london-open-house-2025", "London Open House 2025"),
    ("https://www.london.gov.uk", "/events/london-open-house-undated", "London Open House archive"),
    ("https://www.london.gov.uk", "/events/eid-square-2025", "Eid on the Square 2025"),
]


def fixture_rows():
    return [
        {
            "url": origin + path,
            "title": title,
            "body": f"{title} annual event page.",
            "fetched_at": "2026-10-26",
            "source_id": "fixture_source",
            "display_mode": "metadata_only",
        }
        for origin, path, title in CORPUS
    ]


def paths(results):
    return [r["url"].rsplit("/", 1)[-1] for r in results]


class StubEngine:
    """Deterministic engine for retrieval-shape tests (no real corpus involved)."""

    def __init__(self, rows, fail_queries=()):
        self.rows = rows
        self.fail_queries = set(fail_queries)
        self.calls = []

    def search(self, query, limit=10):
        self.calls.append((query, limit))
        if query in self.fail_queries:
            raise RuntimeError("synthetic sub-query failure")
        tokens = [t for t in re.findall(r"[a-z0-9]+", query.casefold()) if len(t) > 2]
        hits = [r for r in self.rows
                if all(t in (r["title"] + " " + r["body"]).casefold() for t in tokens)]
        return {"results": hits[:limit], "status": "OK"}


def stub(prefix, count, body="london events page"):
    return [{"url": f"https://example.org/{prefix}-{i}", "title": f"{prefix} {i}", "body": body}
            for i in range(count)]


class IntegrityGateTests(unittest.TestCase):
    def test_pin_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "index.sqlite"
            target.write_bytes(b"not the accepted corpus")
            with self.assertRaises(SystemExit) as caught:
                layer.verify_pin(target, "0" * 64, "OWNER_INDEX")
            self.assertIn("HOLD_OWNER_INDEX_SHA_MISMATCH", str(caught.exception))

    def test_missing_index_fails_closed(self):
        with self.assertRaises(SystemExit) as caught:
            layer.verify_pin(Path("does-not-exist.sqlite"), "0" * 64, "OWNER_INDEX")
        self.assertIn("HOLD_OWNER_INDEX_ABSENT", str(caught.exception))

    def test_pin_match_returns_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "payload.bin"
            target.write_bytes(b"pinned bytes")
            digest = layer.sha256_file(target)
            self.assertEqual(layer.verify_pin(target, digest, "OWNER_INDEX"), digest)

    def test_read_rows_rejects_wrong_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "index.sqlite"
            sqlite3.connect(target).close()
            with self.assertRaises(SystemExit) as caught:
                layer.read_rows(target, expected_pin="0" * 64)
            self.assertIn("HOLD_OWNER_INDEX_SHA_MISMATCH", str(caught.exception))

    def test_unpinned_read_receipt_says_pin_not_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "fixture.sqlite"
            db = sqlite3.connect(target)
            db.execute("create table sources(source_id text primary key, display_mode text,"
                       " approved int, enabled int)")
            db.execute("create table pages(url text primary key, title text, body text,"
                       " fetched_at text, source_id text, indexed int)")
            db.execute("insert into sources values('s','metadata_only',1,1)")
            db.executemany("insert into pages values(?,?,?,?,?,1)",
                           [(f"https://example.org/{i}", f"t{i}", "b", "2026-10-26", "s")
                            for i in range(120)])
            db.commit()
            db.close()
            rows, receipt = layer.read_rows(target, expected_pin=None)
            self.assertEqual(len(rows), 120)
            self.assertFalse(receipt["pin_enforced"])
            self.assertEqual(receipt["sha256_before"], receipt["sha256_after"])

    def test_dense_mode_requires_model_dir(self):
        with self.assertRaises(SystemExit) as caught:
            layer.run(["--index", "x", "--snapshot", "y", "--frozen", "z",
                       "--out", "o", "--dense"])
        self.assertIn("HOLD_DENSE_REQUIRES_MODEL_DIR", str(caught.exception))


class QueryLocalNegationTests(unittest.TestCase):
    """Owner gate: negation is per-request, never global event suppression."""

    def setUp(self):
        self.layer = layer.ConstrainedSearch(hc, HybridIndex(fixture_rows()), "hybrid_constrained")

    def test_positive_searches_still_retrieve_their_edition(self):
        for query, expected in (
            ("Diwali events", "diwali-square-2025"),
            ("Pride Berlin events", "pride-berlin-2026"),
            ("CSD Berlin", "csd-berlin-2026"),
            ("Stadtfest Berlin", "stadtfest-berlin-2026"),
        ):
            with self.subTest(query=query):
                result = self.layer.search(query, limit=10)
                self.assertIn(expected, paths(result["results"]))

    def test_generic_events_search_does_not_suppress_any_edition(self):
        result = self.layer.search("Berlin events", limit=10)
        found = set(paths(result["results"]))
        for expected in ("pride-berlin-2026", "csd-berlin-2026", "stadtfest-berlin-2026"):
            self.assertIn(expected, found)

    def test_explicit_negation_omits_only_the_named_entity(self):
        result = self.layer.search("Berlin events excluding CSD Berlin", limit=10)
        found = set(paths(result["results"]))
        self.assertNotIn("csd-berlin-2026", found)
        self.assertIn("pride-berlin-2026", found)
        self.assertIn("stadtfest-berlin-2026", found)

    def test_follow_up_search_without_negation_retrieves_again(self):
        self.layer.search("Berlin events excluding CSD Berlin", limit=10)
        result = self.layer.search("CSD Berlin", limit=10)
        self.assertIn("csd-berlin-2026", paths(result["results"]))

    def test_negation_does_not_persist_in_the_wrapper(self):
        before = set(paths(self.layer.search("Berlin events", limit=10)["results"]))
        self.layer.search("Berlin events excluding CSD Berlin", limit=10)
        after = set(paths(self.layer.search("Berlin events", limit=10)["results"]))
        self.assertEqual(before, after)

    def test_semantics_are_declared_in_every_result(self):
        result = self.layer.search("Diwali events", limit=10)
        self.assertEqual(result["metrics_scope"]["exclusion_semantics"], "QUERY_LOCAL_NEGATION_ONLY")
        self.assertFalse(result["metrics_scope"]["global_event_suppression"])
        self.assertFalse(result["metrics_scope"]["index_or_source_mutation"])


class CoordinatedExclusionTests(unittest.TestCase):
    def setUp(self):
        self.layer = layer.ConstrainedSearch(hc, HybridIndex(fixture_rows()), "hybrid_constrained")

    def test_conjunction_splits_into_separate_entities(self):
        d = layer.decompose(hc, "Berlin events other than Diwali and Pride")
        self.assertEqual(d.exclusions, ("Diwali", "Pride"))

    def test_three_entity_list_splits(self):
        d = layer.decompose(hc, "Berlin events other than Diwali on the Square, Pride Berlin and CSD Berlin")
        self.assertEqual(d.exclusions, ("Diwali on the Square", "Pride Berlin", "CSD Berlin"))

    def test_multi_word_entity_is_not_split(self):
        d = layer.decompose(hc, "Find London events in 2025 other than Diwali on the Square")
        self.assertEqual(d.exclusions, ("Diwali on the Square",))

    def test_trailing_scope_is_not_part_of_the_entity(self):
        d = layer.decompose(hc, "Berlin events excluding CSD Berlin in 2026")
        self.assertEqual(d.exclusions, ("CSD Berlin",))

    def test_each_coordinated_exclusion_is_applied(self):
        result = self.layer.search("Berlin events other than Pride Berlin and CSD Berlin", limit=10)
        found = set(paths(result["results"]))
        self.assertNotIn("pride-berlin-2026", found)
        self.assertNotIn("csd-berlin-2026", found)
        self.assertIn("stadtfest-berlin-2026", found)

    def test_contradictory_exclusion_is_withheld(self):
        result = self.layer.search("Diwali on the Square 2027 excluding Diwali", limit=10)
        self.assertEqual(result["status"], "WITHHELD_CONTRADICTORY_EXCLUSION")
        self.assertEqual(result["results"], [])

    def test_missing_title_year_is_outside_the_requested_set(self):
        result = self.layer.search("London Open House 2024", limit=10)
        found = set(paths(result["results"]))
        self.assertIn("london-open-house-2024", found)
        self.assertNotIn("london-open-house-undated", found)


class RefillTests(unittest.TestCase):
    def test_refill_reaches_deeper_candidates_after_filtering(self):
        rows = stub("Diwali", 6) + stub("london", 12)
        engine = StubEngine(rows)
        layer_ = layer.ConstrainedSearch(hc, engine, "hybrid_constrained")
        result = layer_.search("London events other than Diwali", limit=5)
        self.assertEqual(len(result["results"]), 5)
        self.assertTrue(all("Diwali" not in r["title"] for r in result["results"]))
        self.assertTrue(result["refilled"])
        self.assertGreater(max(p["depth"] for p in result["search_passes"]), 10)

    def test_limit_is_honoured_without_duplicates(self):
        engine = StubEngine(stub("london", 12))
        layer_ = layer.ConstrainedSearch(hc, engine, "hybrid_constrained")
        result = layer_.search("London events", limit=3)
        urls = [r["url"] for r in result["results"]]
        self.assertLessEqual(len(urls), 3)
        self.assertEqual(len(urls), len(set(urls)))

    def test_no_refill_when_first_pass_already_satisfies_limit(self):
        engine = StubEngine(stub("london", 12))
        layer_ = layer.ConstrainedSearch(hc, engine, "hybrid_constrained")
        result = layer_.search("London events", limit=10)
        self.assertEqual(len(result["results"]), 10)
        self.assertFalse(result["refilled"])


class PartialRetrievalTests(unittest.TestCase):
    def setUp(self):
        rows = stub("London Open House", 1, body="london open house edition") + [
            {"url": "https://example.org/oh-2024", "title": "London Open House 2024",
             "body": "london open house edition"},
            {"url": "https://example.org/oh-2025", "title": "London Open House 2025",
             "body": "london open house edition"},
        ]
        self.engine = StubEngine(rows, fail_queries={"london open house 2025"})
        self.layer = layer.ConstrainedSearch(hc, self.engine, "hybrid_constrained")

    def test_failed_year_subquery_is_reported_not_swallowed(self):
        result = self.layer.search("London Open House 2024 and 2025", limit=10)
        self.assertEqual(result["retrieval_status"], "PARTIAL_SUBQUERY_FAILED")
        self.assertEqual(result["year_coverage"]["2025"]["status"], "FAILED")

    def test_successful_years_are_still_reported(self):
        result = self.layer.search("London Open House 2024 and 2025", limit=10)
        self.assertEqual(result["year_coverage"]["2024"]["status"], "RETRIEVED")

    def test_partial_failure_does_not_raise_or_invent_results(self):
        result = self.layer.search("London Open House 2024 and 2025", limit=10)
        found = [r["url"] for r in result["results"]]
        self.assertNotIn("https://example.org/oh-2025", found)
        self.assertIn("https://example.org/oh-2024", found)
        self.assertTrue(any(d["status"] == "FAILED" for d in result["diagnostics"]))

    def test_incomplete_coverage_never_claims_complete(self):
        result = self.layer.search("London Open House 2024 and 2025", limit=10)
        self.assertNotEqual(result["retrieval_status"], "COMPLETE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
