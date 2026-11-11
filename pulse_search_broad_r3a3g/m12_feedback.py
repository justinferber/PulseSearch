"""Privacy-conscious reviewed feedback and ranking proposals.

Only aggregate, de-identified query shape plus a source domain and a reviewed
verdict are stored. Raw questions are never persisted. A review proposal is
advisory until an operator applies it; clicks never promote a source.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

VERDICTS = {"helpful", "irrelevant", "stale", "broken", "insufficient"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def query_shape(question: str) -> tuple[str, str]:
    text = " ".join(re.findall(r"[a-z0-9]+", str(question or "").lower()))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]
    if "christmas" in text and "market" in text:
        kind = "christmas_market_list"
    elif re.search(r"\b(how|renew|apply|access|wheelchair|refund)\b", text):
        kind = "how_to"
    elif re.search(r"\b(when|date|dates|open|opening)\b", text):
        kind = "event_date"
    elif re.search(r"\b(compare|versus|vs|easiest|better)\b", text):
        kind = "comparison"
    else:
        kind = "general"
    return digest, kind


class FeedbackStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS feedback(
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 query_key TEXT NOT NULL,
                 query_shape TEXT NOT NULL,
                 source_domain TEXT NOT NULL,
                 verdict TEXT NOT NULL,
                 reviewer TEXT NOT NULL,
                 note TEXT NOT NULL,
                 reviewed_at TEXT NOT NULL,
                 applied INTEGER NOT NULL DEFAULT 1
               )"""
        )
        self.conn.commit()

    def record(self, question: str, source_domain: str, verdict: str,
               reviewer: str, note: str = "") -> int:
        if verdict not in VERDICTS:
            raise ValueError("unsupported feedback verdict")
        if not reviewer.strip():
            raise ValueError("reviewed feedback requires a reviewer")
        domain = str(source_domain or "").lower().strip(".")
        if not domain or "/" in domain or " " in domain:
            raise ValueError("source_domain must be a bare domain")
        key, shape = query_shape(question)
        cursor = self.conn.execute(
            """INSERT INTO feedback(query_key, query_shape, source_domain, verdict,
                 reviewer, note, reviewed_at) VALUES(?,?,?,?,?,?,?)""",
            (key, shape, domain, verdict, reviewer.strip(), note[:300], utc_now()),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def score(self, source_domain: str) -> int:
        """Small reviewed adjustment; never an automatic click-derived boost."""
        row = self.conn.execute(
            """SELECT
                 SUM(CASE WHEN verdict='helpful' THEN 2
                          WHEN verdict='irrelevant' THEN -2
                          WHEN verdict='stale' THEN -1
                          WHEN verdict='broken' THEN -2
                          ELSE 0 END) AS score
               FROM feedback WHERE source_domain=? AND applied=1""",
            (str(source_domain or "").lower().strip("."),),
        ).fetchone()
        return int(row["score"] or 0)

    def outcomes(self, query_key: str | None = None) -> list[dict]:
        sql = "SELECT * FROM feedback"
        params: list = []
        if query_key:
            sql += " WHERE query_key=?"
            params.append(query_key)
        sql += " ORDER BY id"
        return [dict(row) for row in self.conn.execute(sql, params)]

    def proposal(self) -> dict:
        """A reviewable aggregate proposal, not an automatic source promotion."""
        rows = self.conn.execute(
            """SELECT source_domain,
                      SUM(verdict='helpful') AS helpful,
                      SUM(verdict IN ('irrelevant','stale','broken')) AS negative,
                      COUNT(*) AS reviews
                 FROM feedback GROUP BY source_domain
                ORDER BY (helpful - negative) DESC, reviews DESC, source_domain"""
        ).fetchall()
        return {"generated_at": utc_now(), "automatic_apply": False,
                "requires": "operator_review",
                "sources": [dict(row) for row in rows]}

    def export(self) -> list[dict]:
        return self.outcomes()

    def close(self) -> None:
        self.conn.close()
