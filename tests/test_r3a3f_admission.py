"""CLI admission: an incomplete file can never authorise crawling or indexing."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_crawler_r3a3f import cli  # noqa: E402
from pulse_search_crawler_r3a3f.store import Store  # noqa: E402


class CliAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="r3a3f-cli-"))
        self.db = str(self.tmp / "crawl.sqlite")
        self.staging = str(self.tmp / "staging.sqlite")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, payload: dict) -> str:
        path = self.tmp / "sources.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def run_cli(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cli.main(argv)
        return code, buffer.getvalue()

    def sources_cli(self, payload: dict) -> tuple[int, str]:
        return self.run_cli(["sources", "--db", self.db, "--staging", self.staging,
                             "--file", self.write(payload)])

    def source_rows(self) -> list[dict]:
        store = Store(self.db)
        try:
            return store.sources(enabled_only=False)
        finally:
            store.close()

    def test_missing_admission_fields_are_rejected_without_registering(self):
        code, out = self.sources_cli({"sources": [{
            "source_id": "x", "origin": "https://example.org",
            "allowed_paths": ["/events"]}]})
        self.assertEqual(code, 2)
        self.assertIn("source_admission_rejected", out)
        self.assertIn("approved", out)
        self.assertEqual(self.source_rows(), [])

    def test_approval_without_reviewed_rights_is_rejected(self):
        code, out = self.sources_cli({"sources": [{
            "source_id": "x", "origin": "https://example.org",
            "allowed_paths": ["/events"], "rights_status": "NOT_ASSESSED",
            "approved": True, "index_allowed": True}]})
        self.assertEqual(code, 2)
        self.assertIn("reviewed rights basis", out)
        self.assertEqual(self.source_rows(), [])

    def test_indexing_without_approval_is_rejected(self):
        code, _ = self.sources_cli({"sources": [{
            "source_id": "x", "origin": "https://example.org",
            "allowed_paths": ["/events"], "rights_status": "OWNER_APPROVED_RESEARCH",
            "approved": False, "index_allowed": True}]})
        self.assertEqual(code, 2)
        self.assertEqual(self.source_rows(), [])

    def test_boolean_flags_must_be_booleans(self):
        code, _ = self.sources_cli({"sources": [{
            "source_id": "x", "origin": "https://example.org",
            "allowed_paths": ["/events"], "rights_status": "OWNER_APPROVED_RESEARCH",
            "approved": "yes", "index_allowed": True}]})
        self.assertEqual(code, 2)
        self.assertEqual(self.source_rows(), [])

    def test_seed_outside_approved_scope_is_rejected_before_writing(self):
        code, out = self.sources_cli({
            "sources": [{
                "source_id": "x", "origin": "https://example.org",
                "allowed_paths": ["/events"], "rights_status": "OWNER_APPROVED_RESEARCH",
                "approved": True, "index_allowed": True}],
            "seeds": {"x": ["https://example.org/admin/panel"]}})
        self.assertEqual(code, 2)
        self.assertIn("outside", out)
        self.assertEqual(self.source_rows(), [])

    def test_explicit_admission_is_accepted(self):
        code, out = self.sources_cli({
            "sources": [{
                "source_id": "x", "origin": "https://example.org",
                "allowed_paths": ["/events"], "rights_status": "OWNER_APPROVED_RESEARCH",
                "approved": True, "index_allowed": True}],
            "seeds": {"x": ["https://example.org/events"]}})
        self.assertEqual(code, 0, out)
        rows = self.source_rows()
        self.assertEqual(rows[0]["approved"], 1)
        self.assertEqual(rows[0]["index_allowed"], 1)
        store = Store(self.db)
        try:
            self.assertEqual(len(store.seeds("x")), 1)
        finally:
            store.close()

    def test_run_refuses_when_no_source_is_admitted(self):
        code, out = self.run_cli(["run", "--db", self.db, "--staging", self.staging,
                                  "--max-fetches", "1"])
        self.assertEqual(code, 3)
        self.assertIn("crawl_refused", out)

    def test_run_refuses_an_admitted_source_without_rights(self):
        store = Store(self.db)
        try:
            store.add_source(source_id="x", origin="https://example.org",
                             allowed_paths=["/events"], rights_status="NOT_ASSESSED",
                             approved=True, index_allowed=True)
        finally:
            store.close()
        code, out = self.run_cli(["run", "--db", self.db, "--staging", self.staging,
                                  "--max-fetches", "1"])
        self.assertEqual(code, 3)
        self.assertIn("reviewed rights basis", out)


if __name__ == "__main__":
    unittest.main()
