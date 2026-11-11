"""Novelty against the pinned historical index (read-only, SHA-256 verified).

A pilot must be able to answer "how much of this is new?" without reindexing
or touching the owner's 120-page index. This module opens that database with
SQLite's read-only URI mode, verifies its SHA-256 against the pinned value
before reading a single page, and compares it with the staging index. Nothing
is written to either database.

The hash check matters: without it a substituted or re-exported index would
silently change what "novel" means, and the pilot's acceptance claim with it.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from .urls import UrlError, canonicalize

PINNED_INDEX_SHA256 = "bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d"


class NoveltyPinMismatch(RuntimeError):
    """Raised when the reference index is not the pinned, accepted file."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(url: str) -> str | None:
    try:
        return canonicalize(url)
    except (UrlError, ValueError):
        return None


def _historical(index_path: str | Path, expect_sha256: str | None) -> tuple[set[str], str]:
    path = Path(index_path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    digest = sha256_file(path)
    if expect_sha256 and digest != expect_sha256:
        raise NoveltyPinMismatch(
            f"historical index {path} has SHA-256 {digest}; expected {expect_sha256}")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT url FROM pages").fetchall()
    finally:
        conn.close()
    return {canonical for canonical in (_canonical(row[0]) for row in rows) if canonical}, digest


def historical_urls(index_path: str | Path, expect_sha256: str | None = None) -> set[str]:
    return _historical(index_path, expect_sha256)[0]


def _block(historical: set[str], staged: set[str], index_path, digest: str,
           expect_sha256: str | None) -> dict:
    novel = sorted(staged - historical)
    return {
        "status": "MEASURED_READ_ONLY",
        "historical_index": str(index_path),
        "historical_index_sha256": digest,
        "expected_index_sha256": expect_sha256,
        "pin_match": (digest == expect_sha256) if expect_sha256 else None,
        "historical_index_pages": len(historical),
        "staged_documents": len(staged),
        "already_in_historical_index": len(staged & historical),
        "novel_documents": len(novel),
        "novel_sample": novel[:20],
    }


def overlap(staging, index_path: str | Path, expect_sha256: str | None = None) -> dict:
    """Compare staged documents with the pinned index, without modifying either."""
    historical, digest = _historical(index_path, expect_sha256)
    staged = {
        canonical
        for canonical in (_canonical(doc["url"]) for doc in staging.all_documents(100000))
        if canonical
    }
    return _block(historical, staged, index_path, digest, expect_sha256)


def overlap_by_source(staging, index_path: str | Path,
                      expect_sha256: str | None = None) -> dict[str, dict]:
    """Novelty per staged source, so three candidates are never pooled into one claim."""
    historical, digest = _historical(index_path, expect_sha256)
    staged: dict[str, set[str]] = {}
    for doc in staging.all_documents(100000):
        canonical = _canonical(doc["url"])
        if canonical:
            staged.setdefault(doc["source_id"], set()).add(canonical)
    return {
        source_id: _block(historical, urls, index_path, digest, expect_sha256)
        for source_id, urls in sorted(staged.items())
    }
