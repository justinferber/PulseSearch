"""Offline broad-search command against the existing *staging* SQLite file.

Example:
  python -m pulse_search_broad_r3a3g.cli --staging data/r3a3f_three_source/staging.sqlite \
    "How do I book tickets for a concert in Berlin?"

No network and no writes: SQLite is opened mode=ro. The immutable 120-page
October index is NOT used here, nor is the source-admission register modified.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from .search import search_staging


class ReadOnlyStaging:
    def __init__(self, path: str):
        target = Path(path).resolve(strict=True)
        # URI mode=ro must be used, rather than constructing StagingIndex
        # (whose constructor can migrate schema and start a WAL).
        self.conn = sqlite3.connect("file:" + quote(str(target), safe="/:") +
                                    "?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row

    def all_documents(self, limit: int = 5000) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM docs WHERE revoked=0 ORDER BY doc_id LIMIT ?",
            (max(1, min(int(limit), 5000)),),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only broad staging search")
    parser.add_argument("query", help="Natural language search query")
    parser.add_argument("--staging", required=True, help="Existing staging.sqlite file")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    with_path = ReadOnlyStaging(args.staging)
    try:
        result = search_staging(with_path, args.query, args.limit)
    finally:
        with_path.close()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
