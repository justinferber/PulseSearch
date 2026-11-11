"""Separate staging index for newly accepted pages.

This database is deliberately independent of the immutable 120-page October
index (SHA-256 bb8e5202...). Nothing here can read or write that file, and no
accepted historical evidence is reindexed.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import quality
from .urls import is_administrative_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs(
  doc_id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL UNIQUE,
  canonical_url TEXT NOT NULL, source_id TEXT NOT NULL, seed_id TEXT,
  parent_url TEXT, title TEXT NOT NULL, snippet TEXT NOT NULL,
  category TEXT NOT NULL, category_confidence REAL NOT NULL,
  category_uncertain INTEGER NOT NULL DEFAULT 0,
  categories TEXT NOT NULL, depth INTEGER NOT NULL, fetched_at TEXT NOT NULL,
  content_hash TEXT NOT NULL, shingle_count INTEGER NOT NULL DEFAULT 0,
  etag TEXT, last_modified TEXT, lang TEXT, dates TEXT, rights_mode TEXT NOT NULL,
  fetch_status INTEGER, mime TEXT, intent TEXT, indexed_at TEXT NOT NULL,
  revoked INTEGER NOT NULL DEFAULT 0, revoked_reason TEXT,
  source_authority TEXT, document_type TEXT, language TEXT,
  jurisdiction TEXT, specificity TEXT, provenance TEXT, metadata TEXT);
CREATE INDEX IF NOT EXISTS idx_docs_category ON docs(category, revoked);
CREATE INDEX IF NOT EXISTS idx_docs_source ON docs(source_id, revoked);
CREATE TABLE IF NOT EXISTS doc_shingles(
  doc_id INTEGER NOT NULL, shingle INTEGER NOT NULL,
  PRIMARY KEY(doc_id, shingle));
CREATE INDEX IF NOT EXISTS idx_shingle ON doc_shingles(shingle);
CREATE TABLE IF NOT EXISTS rejected_pages(
  url TEXT PRIMARY KEY, source_id TEXT, depth INTEGER, reason TEXT,
  detail TEXT, seen_at TEXT);
CREATE TABLE IF NOT EXISTS query_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, category TEXT,
  hits INTEGER, at_utc TEXT);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS doc_fts
  USING fts5(title, snippet, url);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fts_tokens(query: str) -> str:
    terms = re.findall(r"[A-Za-z0-9]+", query or "")
    return " ".join(f'"{t}"*' for t in terms[:12])


class StagingIndex:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(docs)")}
        if columns and "intent" not in columns:  # migrate pre-discovery staging DBs
            self.conn.execute("ALTER TABLE docs ADD COLUMN intent TEXT")
            self.conn.commit()
        for name in ("source_authority", "document_type", "language",
                     "jurisdiction", "specificity", "provenance", "metadata"):
            if columns and name not in columns:
                self.conn.execute(f"ALTER TABLE docs ADD COLUMN {name} TEXT")
                self.conn.commit()
        try:
            self.conn.executescript(FTS_SCHEMA)
            self.fts = True
        except sqlite3.OperationalError:
            self.fts = False
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "StagingIndex":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ dedup
    def near_duplicate(self, shingle_list: list[int], threshold: float) -> dict | None:
        if not shingle_list:
            return None
        marks = ",".join("?" for _ in shingle_list)
        rows = self.conn.execute(
            f"""SELECT s.doc_id, COUNT(*) overlap, d.shingle_count, d.url, d.title
                FROM doc_shingles s JOIN docs d ON d.doc_id=s.doc_id
                WHERE s.shingle IN ({marks}) AND d.revoked=0
                GROUP BY s.doc_id ORDER BY overlap DESC LIMIT 3""",
            shingle_list,
        ).fetchall()
        for row in rows:
            union = len(shingle_list) + row["shingle_count"] - row["overlap"]
            if union <= 0:
                continue
            score = row["overlap"] / union
            if score >= threshold:
                return {"doc_id": row["doc_id"], "similarity": round(score, 4),
                        "url": row["url"], "title": row["title"]}
        return None

    def exact_duplicate(self, content_hash: str) -> dict | None:
        row = self.conn.execute(
            "SELECT doc_id, url, title FROM docs WHERE content_hash=? AND revoked=0 LIMIT 1",
            (content_hash,),
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------ write
    def add_document(self, record: dict, shingle_list: list[int], *,
                     index_allowed: bool = False) -> tuple[bool, str]:
        """Insert an accepted page. Returns (indexed, reason).

        Fail closed: indexing requires an explicit rights decision. A source
        that may be fetched is not automatically a source that may be stored.
        """
        if not index_allowed:
            self.record_rejection(record.get("url", ""), record.get("source_id", ""),
                                  int(record.get("depth", 0)), "rights_denied_index",
                                  "index_allowed=False")
            return False, "rights_denied_index"
        # Defence in depth: even if an administrative URL reached staging, it
        # must never become searchable.
        if is_administrative_path(record.get("url", "")):
            self.record_rejection(record.get("url", ""), record.get("source_id", ""),
                                  int(record.get("depth", 0)), "administrative_path",
                                  "admin or authentication route")
            return False, "administrative_path"
        existing = self.conn.execute(
            "SELECT doc_id FROM docs WHERE url=?", (record["url"],)
        ).fetchone()
        if existing:
            self.conn.execute(
                """UPDATE docs SET source_id=?, title=?, snippet=?, category=?,
                     category_confidence=?, category_uncertain=?, categories=?, depth=?,
                     fetched_at=?, content_hash=?, shingle_count=?, etag=?, last_modified=?,
                     lang=?, dates=?, rights_mode=?, source_authority=?, document_type=?,
                     language=?, jurisdiction=?, specificity=?, provenance=?, metadata=?,
                     indexed_at=?, revoked=0
                   WHERE doc_id=?""",
                (record["source_id"], record["title"], record["snippet"], record["category"],
                 record["category_confidence"], int(record.get("category_uncertain", 0)),
                 json.dumps(record["categories"]),
                 record["depth"], record["fetched_at"], record["content_hash"],
                 len(shingle_list), record.get("etag"), record.get("last_modified"),
                 record.get("lang", ""), json.dumps(record.get("dates", [])),
                 record.get("rights_mode", "metadata_and_short_snippet"),
                 record.get("source_authority"), record.get("document_type"),
                 record.get("language"), record.get("jurisdiction"),
                 record.get("specificity"), record.get("provenance"),
                 record.get("metadata"), utc_now(), existing["doc_id"]),
            )
            self.conn.execute("DELETE FROM doc_shingles WHERE doc_id=?", (existing["doc_id"],))
            doc_id = existing["doc_id"]
            outcome = "updated"
        else:
            cursor = self.conn.execute(
                """INSERT INTO docs(url,canonical_url,source_id,seed_id,parent_url,title,
                     snippet,category,category_confidence,category_uncertain,categories,
                     depth,fetched_at,content_hash,shingle_count,etag,last_modified,lang,
                     dates,rights_mode,fetch_status,mime,source_authority,
                     document_type,language,jurisdiction,specificity,provenance,metadata,indexed_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (record["url"], record.get("canonical_url", record["url"]),
                 record["source_id"], record.get("seed_id"), record.get("parent_url"),
                 record["title"], record["snippet"], record["category"],
                 record["category_confidence"], int(record.get("category_uncertain", 0)),
                 json.dumps(record["categories"]),
                 record["depth"], record["fetched_at"], record["content_hash"],
                 len(shingle_list), record.get("etag"), record.get("last_modified"),
                 record.get("lang", ""), json.dumps(record.get("dates", [])),
                 record.get("rights_mode", "metadata_and_short_snippet"),
                 record.get("fetch_status"), record.get("mime", ""),
                 record.get("source_authority"), record.get("document_type"),
                 record.get("language"), record.get("jurisdiction"),
                 record.get("specificity"), record.get("provenance"),
                 record.get("metadata"), utc_now()),
            )
            doc_id = cursor.lastrowid
            outcome = "indexed"
        self.conn.execute("UPDATE docs SET intent=? WHERE doc_id=?",
                          (record.get("intent"), doc_id))
        for shingle in shingle_list:
            self.conn.execute(
                "INSERT OR IGNORE INTO doc_shingles(doc_id,shingle) VALUES(?,?)",
                (doc_id, shingle),
            )
        if self.fts:
            self.conn.execute("DELETE FROM doc_fts WHERE rowid=?", (doc_id,))
            self.conn.execute(
                "INSERT INTO doc_fts(rowid,title,snippet,url) VALUES(?,?,?,?)",
                (doc_id, record["title"], record["snippet"], record["url"]),
            )
        self.conn.commit()
        return True, outcome

    def revoke(self, url: str, reason: str) -> bool:
        row = self.conn.execute("SELECT doc_id FROM docs WHERE url=?", (url,)).fetchone()
        if not row:
            return False
        self.conn.execute(
            "UPDATE docs SET revoked=1, revoked_reason=? WHERE doc_id=?", (reason, row["doc_id"])
        )
        self.conn.execute("DELETE FROM doc_shingles WHERE doc_id=?", (row["doc_id"],))
        if self.fts:
            self.conn.execute("DELETE FROM doc_fts WHERE rowid=?", (row["doc_id"],))
        self.conn.commit()
        return True

    def revoke_source(self, source_id: str, reason: str) -> int:
        rows = self.conn.execute(
            "SELECT doc_id FROM docs WHERE source_id=? AND revoked=0", (source_id,)
        ).fetchall()
        for row in rows:
            self.conn.execute(
                "UPDATE docs SET revoked=1, revoked_reason=? WHERE doc_id=?", (reason, row["doc_id"])
            )
            self.conn.execute("DELETE FROM doc_shingles WHERE doc_id=?", (row["doc_id"],))
            if self.fts:
                self.conn.execute("DELETE FROM doc_fts WHERE rowid=?", (row["doc_id"],))
        self.conn.commit()
        return len(rows)

    def record_rejection(self, url: str, source_id: str, depth: int, reason: str, detail: str = "") -> None:
        self.conn.execute(
            """INSERT INTO rejected_pages(url,source_id,depth,reason,detail,seen_at)
               VALUES(?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET
                 reason=excluded.reason, detail=excluded.detail, seen_at=excluded.seen_at""",
            (url, source_id, depth, reason, detail[:300], utc_now()),
        )
        self.conn.commit()

    # ------------------------------------------------------------------- read
    def search(self, query: str, category: str | None = None, limit: int = 10) -> list[dict]:
        params: list = []
        if self.fts and query.strip():
            sql = ("SELECT d.*, bm25(doc_fts) AS rank FROM doc_fts "
                   "JOIN docs d ON d.doc_id=doc_fts.rowid "
                   "WHERE doc_fts MATCH ? AND d.revoked=0")
            params.append(_fts_tokens(query))
        else:
            like = f"%{query}%"
            sql = ("SELECT d.*, 0 AS rank FROM docs d WHERE d.revoked=0 "
                   "AND (d.title LIKE ? OR d.snippet LIKE ? OR d.url LIKE ?)")
            params.extend([like, like, like])
        if category:
            sql += " AND d.category=?"
            params.append(category)
        sql += " ORDER BY rank LIMIT ?" if self.fts and query.strip() else " ORDER BY d.indexed_at DESC LIMIT ?"
        params.append(limit)
        rows = [dict(r) for r in self.conn.execute(sql, params)]
        self.conn.execute(
            "INSERT INTO query_log(query,category,hits,at_utc) VALUES(?,?,?,?)",
            (query, category or "", len(rows), utc_now()),
        )
        self.conn.commit()
        return rows

    def stats(self) -> dict:
        total = self.conn.execute("SELECT COUNT(*) n FROM docs WHERE revoked=0").fetchone()["n"]
        revoked = self.conn.execute("SELECT COUNT(*) n FROM docs WHERE revoked=1").fetchone()["n"]
        by_category = {
            row["category"]: row["n"]
            for row in self.conn.execute(
                "SELECT category, COUNT(*) n FROM docs WHERE revoked=0 GROUP BY category ORDER BY n DESC"
            )
        }
        by_source = {
            row["source_id"]: row["n"]
            for row in self.conn.execute(
                "SELECT source_id, COUNT(*) n FROM docs WHERE revoked=0 GROUP BY source_id ORDER BY n DESC"
            )
        }
        by_depth = {
            int(row["depth"]): row["n"]
            for row in self.conn.execute(
                "SELECT depth, COUNT(*) n FROM docs WHERE revoked=0 GROUP BY depth ORDER BY depth"
            )
        }
        rejected = {
            row["reason"]: row["n"]
            for row in self.conn.execute(
                "SELECT reason, COUNT(*) n FROM rejected_pages GROUP BY reason ORDER BY n DESC"
            )
        }
        by_intent = {
            row["intent"]: row["n"]
            for row in self.conn.execute(
                "SELECT intent, COUNT(*) n FROM docs WHERE revoked=0 AND intent IS NOT NULL "
                "GROUP BY intent ORDER BY n DESC"
            )
        }
        return {
            "documents": total,
            "revoked": revoked,
            "by_category": by_category,
            "by_source": by_source,
            "by_depth": by_depth,
            "by_intent": by_intent,
            "rejections": rejected,
            "fts": self.fts,
        }

    def all_documents(self, limit: int = 5000) -> list[dict]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM docs WHERE revoked=0 ORDER BY doc_id LIMIT ?", (limit,)
            )
        ]

    def get(self, url: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM docs WHERE url=?", (url,)).fetchone()
        return dict(row) if row else None
