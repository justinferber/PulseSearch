"""Novelty against the pinned historical index (read-only).

A pilot must be able to answer "how much of this is new?" without reindexing
or touching the owner's 120-page index. This module opens that database with
SQLite's read-only URI mode, reads the page URLs, and compares them with the
staging index. Nothing is written to either database.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .urls import UrlError, canonicalize


def _canonical(url: str) -> str | None:
    try:
        return canonicalize(url)
    except (UrlError, ValueError):
        return None


def historical_urls(index_path: str | Path) -> set[str]:
    path = Path(index_path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT url FROM pages").fetchall()
    finally:
        conn.close()
    return {canonical for canonical in (_canonical(row[0]) for row in rows) if canonical}


def overlap(staging, index_path: str | Path) -> dict:
    """Compare staged documents with the pinned index, without modifying either."""
    historical = historical_urls(index_path)
    staged = {
        canonical
        for canonical in (_canonical(doc["url"]) for doc in staging.all_documents(100000))
        if canonical
    }
    novel = sorted(staged - historical)
    return {
        "status": "MEASURED_READ_ONLY",
        "historical_index": str(index_path),
        "historical_index_pages": len(historical),
        "staged_documents": len(staged),
        "already_in_historical_index": len(staged & historical),
        "novel_documents": len(novel),
        "novel_sample": novel[:20],
    }
