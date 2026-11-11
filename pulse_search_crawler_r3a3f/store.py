"""Crawler state database: sources, seeds, frontier, host schedule, audit log.

The frontier is the crawl's durable memory. Depth is a minimum: if a URL is
rediscovered through a shorter path its minimum depth drops, but an already
fetched URL is never replayed just because a longer path was found first.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from . import quality
from .urls import UrlError, canonicalize, host_port, in_scope, is_indexable_shape, origin_of

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(
  source_id TEXT PRIMARY KEY, origin TEXT NOT NULL UNIQUE, host TEXT NOT NULL,
  allowed_paths TEXT NOT NULL, rights_status TEXT NOT NULL,
  index_allowed INTEGER NOT NULL DEFAULT 0, store_body INTEGER NOT NULL DEFAULT 0,
  contact TEXT, notes TEXT, approved INTEGER NOT NULL DEFAULT 0,
  probe_policy TEXT NOT NULL DEFAULT '[]', probe_budget_per_run INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 1, admitted_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS seeds(
  seed_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
  note TEXT, admitted_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS frontier(
  url TEXT PRIMARY KEY, source_id TEXT NOT NULL, seed_id TEXT, parent_url TEXT,
  min_depth INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
  priority INTEGER NOT NULL DEFAULT 100, discovered_at TEXT NOT NULL,
  last_fetch TEXT, next_retry TEXT, attempts INTEGER NOT NULL DEFAULT 0,
  robots_decision TEXT, category_hint TEXT, last_status INTEGER, last_error TEXT,
  discovery_method TEXT NOT NULL DEFAULT 'link', approval_ref TEXT,
  recheck_at TEXT, recheck_count INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_frontier_state ON frontier(state, min_depth, priority);
CREATE TABLE IF NOT EXISTS page_state(
  url TEXT PRIMARY KEY, source_id TEXT, etag TEXT, last_modified TEXT,
  content_hash TEXT, indexed_at TEXT, next_recrawl_at TEXT,
  revoked INTEGER NOT NULL DEFAULT 0, revoked_reason TEXT);
CREATE TABLE IF NOT EXISTS host_state(
  host TEXT PRIMARY KEY, last_request_at REAL, next_allowed_at REAL,
  blocked_until REAL, robots_source TEXT, robots_fetched_at REAL,
  failures INTEGER NOT NULL DEFAULT 0, disabled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS fetch_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT, host TEXT, depth INTEGER,
  status INTEGER, mime TEXT, bytes INTEGER, outcome TEXT, reason TEXT,
  at_utc TEXT, latency_ms INTEGER, requests INTEGER);
CREATE TABLE IF NOT EXISTS edges(
  from_url TEXT, to_url TEXT, depth INTEGER, admitted INTEGER, reason TEXT,
  seen_at TEXT, PRIMARY KEY(from_url, to_url));
CREATE TABLE IF NOT EXISTS external_candidates(
  origin TEXT, referrer_url TEXT, first_seen TEXT, sightings INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(origin, referrer_url));
CREATE TABLE IF NOT EXISTS run_log(
  run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT,
  config TEXT, counters TEXT);
CREATE TABLE IF NOT EXISTS rejections(
  url TEXT PRIMARY KEY, source_id TEXT, depth INTEGER, reason TEXT, detail TEXT,
  seen_at TEXT);
CREATE TABLE IF NOT EXISTS sitemap_candidates(
  url TEXT PRIMARY KEY, source_id TEXT, robots_origin TEXT, policy TEXT, seen_at TEXT);
CREATE TABLE IF NOT EXISTS redirect_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT, depth INTEGER,
  from_url TEXT, to_url TEXT, hop INTEGER, status INTEGER, decision TEXT,
  reason TEXT, at_utc TEXT);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _paths(value) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = [value]
    return [v for v in value if isinstance(v, str) and v.startswith("/")]


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Add pre-pilot columns to databases created by the first build."""
        def columns(table: str) -> set[str]:
            return {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}

        for name, ddl in (("discovery_method", "TEXT NOT NULL DEFAULT 'link'"),
                          ("approval_ref", "TEXT"),
                          ("recheck_at", "TEXT"),
                          ("recheck_count", "INTEGER NOT NULL DEFAULT 0")):
            if name not in columns("frontier"):
                self.conn.execute(f"ALTER TABLE frontier ADD COLUMN {name} {ddl}")
        for name, ddl in (("probe_policy", "TEXT NOT NULL DEFAULT '[]'"),
                          ("probe_budget_per_run", "INTEGER NOT NULL DEFAULT 0")):
            if name not in columns("sources"):
                self.conn.execute(f"ALTER TABLE sources ADD COLUMN {name} {ddl}")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------------------------------------------------------------- sources
    def add_source(
        self,
        *,
        source_id: str,
        origin: str,
        allowed_paths: list[str],
        rights_status: str = "NOT_ASSESSED",
        index_allowed: bool = False,
        store_body: bool = False,
        contact: str = "",
        notes: str = "",
        approved: bool = False,
        probe_policy: list[str] | None = None,
        probe_budget_per_run: int = 0,
    ) -> dict:
        """Register a source. Defaults are fail-closed: no fetch, no indexing.

        Admission is a reviewed decision per host and path. An unreviewed JSON
        record can therefore never approve a whole host, and an already
        admitted source cannot be silently de-approved or re-scoped by a later
        import — that needs an explicit owner decision.
        """
        origin = origin.rstrip("/")
        if urlsplit(origin).path not in ("", "/"):
            raise ValueError("source origin must be a root origin")
        paths = sorted(set(allowed_paths or []))
        if approved and not paths:
            raise ValueError("an admitted source needs at least one reviewed path")
        existing = self.conn.execute(
            "SELECT * FROM sources WHERE source_id=?", (source_id,)
        ).fetchone()
        if existing:
            if existing["origin"] != origin:
                raise ValueError(f"source {source_id} is already registered to {existing['origin']}")
            was_admitted = bool(existing["approved"] or existing["index_allowed"])
            if was_admitted and (not approved or not index_allowed):
                raise ValueError(
                    f"source {source_id} is already admitted; refusing to de-approve it "
                    "through import. Retire it explicitly instead."
                )
            if was_admitted and (json.loads(existing["allowed_paths"]) != paths
                                 or existing["rights_status"] != rights_status):
                raise ValueError(
                    f"admitted source {source_id} changed scope or rights basis; "
                    "re-admission needs an explicit owner decision"
                )
        self.conn.execute(
            """INSERT INTO sources(source_id,origin,host,allowed_paths,rights_status,
                 index_allowed,store_body,contact,notes,approved,probe_policy,
                 probe_budget_per_run,enabled,admitted_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,?)
               ON CONFLICT(source_id) DO UPDATE SET
                 allowed_paths=excluded.allowed_paths, rights_status=excluded.rights_status,
                 index_allowed=excluded.index_allowed, store_body=excluded.store_body,
                 contact=excluded.contact, notes=excluded.notes, approved=excluded.approved,
                 probe_policy=excluded.probe_policy,
                 probe_budget_per_run=excluded.probe_budget_per_run""",
            (source_id, origin, host_port(origin + "/"), json.dumps(paths),
             rights_status, int(index_allowed), int(store_body), contact, notes,
             int(approved), json.dumps(sorted(set(probe_policy or []))),
             int(probe_budget_per_run), utc_now()),
        )
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone())

    def sources(self, enabled_only: bool = True) -> list[dict]:
        query = "SELECT * FROM sources" + (" WHERE enabled=1 AND approved=1" if enabled_only else "")
        return [dict(r) for r in self.conn.execute(query + " ORDER BY source_id")]

    def source(self, source_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
        return dict(row) if row else None

    def source_for_url(self, url: str) -> dict | None:
        try:
            origin = origin_of(url)
            canonical = canonicalize(url)
        except (UrlError, ValueError):
            return None
        for source in self.sources():
            if source["origin"].rstrip("/") != origin:
                continue
            if in_scope(canonical, origin, _paths(source["allowed_paths"])):
                return source
        return None

    def set_source_enabled(self, source_id: str, enabled: bool) -> None:
        self.conn.execute("UPDATE sources SET enabled=? WHERE source_id=?", (int(enabled), source_id))
        self.conn.commit()

    # ------------------------------------------------------------------ seeds
    def add_seed(self, source_id: str, url: str, note: str = "") -> str:
        source = self.source(source_id)
        if not source:
            raise ValueError(f"unknown source: {source_id}")
        if not source["approved"]:
            raise ValueError(f"source {source_id} is not admitted for crawling")
        canonical = canonicalize(url)
        if not in_scope(canonical, source["origin"], _paths(source["allowed_paths"])):
            raise ValueError(f"seed outside approved scope: {canonical}")
        seed_id = f"{source_id}:{len(self.seeds(source_id)) + 1}"
        self.conn.execute(
            "INSERT OR IGNORE INTO seeds(seed_id,source_id,url,note,admitted_at) VALUES(?,?,?,?,?)",
            (seed_id, source_id, canonical, note, utc_now()),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT seed_id FROM seeds WHERE url=?", (canonical,)).fetchone()
        return row["seed_id"] if row else seed_id

    def seeds(self, source_id: str | None = None) -> list[dict]:
        query = "SELECT * FROM seeds"
        args: tuple = ()
        if source_id:
            query += " WHERE source_id=?"
            args = (source_id,)
        return [dict(r) for r in self.conn.execute(query + " ORDER BY url", args)]

    # --------------------------------------------------------------- frontier
    def enqueue(
        self,
        url: str,
        *,
        source_id: str,
        seed_id: str | None,
        parent_url: str | None,
        depth: int,
        max_depth: int,
        priority: int | None = None,
        hint: str | None = None,
        method: str = "link",
        approval_ref: str | None = None,
    ) -> str:
        """Admit a URL. Returns new|promoted|duplicate|depth_refused|trap.

        `priority` and `hint` come from anchor-text discovery intent; they only
        change fetch order and labelling, never whether a URL may be crawled.
        `method` records provenance: seed, link or guessed_path_probe. A guessed
        probe never claims a parent page that did not actually link it.
        """
        try:
            canonical = canonicalize(url)
        except (UrlError, ValueError):
            return "trap"
        usable, shape = is_indexable_shape(canonical)
        if not usable:
            self.record_edge(parent_url, canonical, depth, False, shape)
            return "trap"
        if depth > max_depth:
            self.record_edge(parent_url, canonical, depth, False, "depth_beyond_max")
            return "depth_refused"
        existing = self.conn.execute(
            "SELECT min_depth, state FROM frontier WHERE url=?", (canonical,)
        ).fetchone()
        if existing:
            if depth < existing["min_depth"]:
                self.conn.execute(
                    "UPDATE frontier SET min_depth=?, priority=MAX(priority,?), "
                    "category_hint=COALESCE(category_hint,?), "
                    "parent_url=COALESCE(?,parent_url) WHERE url=?",
                    (depth, priority if priority is not None else 0, hint, parent_url, canonical),
                )
                if existing["state"] == "blocked":
                    self.conn.execute(
                        "UPDATE frontier SET state='queued', last_error=NULL WHERE url=?", (canonical,)
                    )
                self.record_edge(parent_url, canonical, depth, True, "reached_at_shallower_depth")
                self.conn.commit()
                return "promoted"
            self.record_edge(parent_url, canonical, depth, True, "already_known")
            self.conn.commit()
            return "duplicate"
        self.conn.execute(
            """INSERT INTO frontier(url,source_id,seed_id,parent_url,min_depth,state,
                 priority,category_hint,discovery_method,approval_ref,discovered_at)
               VALUES(?,?,?,?,?,'queued',?,?,?,?,?)""",
            (canonical, source_id, seed_id, parent_url, depth,
             priority if priority is not None else 100 - depth * 10, hint,
             method, approval_ref, utc_now()),
        )
        self.record_edge(parent_url, canonical, depth, True, "admitted")
        self.conn.commit()
        return "new"

    def claim_next(
        self,
        *,
        max_depth: int,
        now_ts: str,
        blocked_hosts: set[str] | None = None,
        avoid_host: str | None = None,
        capped_hosts: set[str] | None = None,
    ) -> dict | None:
        """Claim one URL, preferring a different host from the last fetch.

        Fairness matters under a fixed budget: without it a single host with
        many high-priority URLs can consume the whole run and starve other
        approved sources and categories.
        """
        rows = self.conn.execute(
            """SELECT * FROM frontier
               WHERE state='queued' AND min_depth<=?
                 AND (next_retry IS NULL OR next_retry<=?)
               ORDER BY priority DESC, min_depth, discovered_at
               LIMIT 500""",
            (max_depth, now_ts),
        ).fetchall()
        fallback = None
        for row in rows:
            host = host_port(row["url"])
            if blocked_hosts and host in blocked_hosts:
                continue
            if capped_hosts and host in capped_hosts:
                # A host that used its share is deferred even if its queue is
                # long: the remaining budget belongs to the other sources.
                continue
            if avoid_host and host == avoid_host:
                fallback = fallback or row
                continue
            self.conn.execute("UPDATE frontier SET state='fetching' WHERE url=?", (row["url"],))
            self.conn.commit()
            return dict(row)
        if fallback is not None:
            self.conn.execute("UPDATE frontier SET state='fetching' WHERE url=?", (fallback["url"],))
            self.conn.commit()
            return dict(fallback)
        return None

    def schedule_recheck(self, url: str, hours: float, reason: str) -> None:
        """Recheck a temporary absence later without blocking the URL forever."""
        until = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="seconds")
        self.conn.execute(
            """UPDATE frontier SET state='recheck', recheck_at=?, next_retry=?,
                 recheck_count=recheck_count+1, last_error=? WHERE url=?""",
            (until, until, reason, url),
        )
        self.conn.commit()

    def reactivate_rechecks(self, now_ts: str) -> int:
        cursor = self.conn.execute(
            """UPDATE frontier SET state='queued', next_retry=NULL
               WHERE state='recheck' AND recheck_at IS NOT NULL AND recheck_at<=?""",
            (now_ts,),
        )
        self.conn.commit()
        return cursor.rowcount

    def discovery_method_counts(self) -> dict[str, int]:
        return {
            row["discovery_method"]: row["n"]
            for row in self.conn.execute(
                "SELECT discovery_method, COUNT(*) n FROM frontier GROUP BY discovery_method"
            )
        }

    def finish(
        self,
        url: str,
        *,
        state: str = "done",
        status: int | None = None,
        error: str | None = None,
        next_retry: str | None = None,
        robots: str | None = None,
    ) -> None:
        attempts = self.conn.execute("SELECT attempts FROM frontier WHERE url=?", (url,)).fetchone()
        self.conn.execute(
            """UPDATE frontier SET state=?, last_fetch=?, attempts=?, next_retry=?,
                 robots_decision=COALESCE(?,robots_decision),
                 last_status=COALESCE(?,last_status), last_error=?
               WHERE url=?""",
            (state, utc_now(), (attempts["attempts"] if attempts else 0) + 1,
             next_retry, robots, status, error, url),
        )
        self.conn.commit()

    def reset_inflight(self) -> int:
        cursor = self.conn.execute("UPDATE frontier SET state='queued' WHERE state='fetching'")
        self.conn.commit()
        return cursor.rowcount

    def queue_counts(self) -> dict[str, int]:
        return {
            row["state"]: row["n"]
            for row in self.conn.execute(
                "SELECT state, COUNT(*) n FROM frontier GROUP BY state"
            )
        }

    def depth_histogram(self) -> dict[int, int]:
        return {
            int(row["min_depth"]): row["n"]
            for row in self.conn.execute(
                "SELECT min_depth, COUNT(*) n FROM frontier GROUP BY min_depth ORDER BY min_depth"
            )
        }

    def deepest_fetched(self) -> int:
        row = self.conn.execute(
            "SELECT MAX(depth) d FROM fetch_log WHERE outcome NOT IN ('robots_denied')"
        ).fetchone()
        return int(row["d"] or 0) if row else 0

    # ------------------------------------------------------------ host state
    def host(self, host: str) -> dict:
        row = self.conn.execute("SELECT * FROM host_state WHERE host=?", (host,)).fetchone()
        if row:
            return dict(row)
        self.conn.execute("INSERT INTO host_state(host) VALUES(?)", (host,))
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM host_state WHERE host=?", (host,)).fetchone())

    def note_request(self, host: str, now_epoch: float, interval_s: float) -> None:
        self.conn.execute(
            "UPDATE host_state SET last_request_at=?, next_allowed_at=? WHERE host=?",
            (now_epoch, now_epoch + interval_s, host),
        )
        self.conn.commit()

    def note_retry_after(self, host: str, until_epoch: float) -> None:
        self.conn.execute(
            "UPDATE host_state SET blocked_until=? WHERE host=?", (until_epoch, host)
        )
        self.conn.commit()

    def note_host_failure(self, host: str, disable: bool = False) -> None:
        self.conn.execute(
            "UPDATE host_state SET failures=failures+1, disabled=? WHERE host=?",
            (int(disable), host),
        )
        self.conn.commit()

    def note_robots(self, host: str, source: str) -> None:
        import time

        self.conn.execute(
            "UPDATE host_state SET robots_source=?, robots_fetched_at=? WHERE host=?",
            (source, time.time(), host),
        )
        self.conn.commit()

    # ---------------------------------------------------------------- page state
    def page_state(self, url: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM page_state WHERE url=?", (url,)).fetchone()
        return dict(row) if row else None

    def upsert_page_state(
        self,
        url: str,
        *,
        source_id: str,
        etag: str | None,
        last_modified: str | None,
        content_hash: str,
        next_recrawl_at: str,
    ) -> None:
        self.conn.execute(
            """INSERT INTO page_state(url,source_id,etag,last_modified,content_hash,
                 indexed_at,next_recrawl_at,revoked) VALUES(?,?,?,?,?,?,?,0)
               ON CONFLICT(url) DO UPDATE SET etag=excluded.etag,
                 last_modified=excluded.last_modified, content_hash=excluded.content_hash,
                 indexed_at=excluded.indexed_at, next_recrawl_at=excluded.next_recrawl_at,
                 revoked=0, revoked_reason=NULL""",
            (url, source_id, etag, last_modified, content_hash, utc_now(), next_recrawl_at),
        )
        self.conn.commit()

    def mark_revoked(self, url: str, reason: str) -> None:
        self.conn.execute(
            "UPDATE page_state SET revoked=1, revoked_reason=? WHERE url=?", (reason, url)
        )
        self.conn.commit()

    def requeue_for_recrawl(self, now_ts: str, limit: int = 50) -> int:
        """Re-open due pages for a conditional revalidation pass."""
        due = self.recrawl_due(now_ts, limit)
        requeued = 0
        for row in due:
            cursor = self.conn.execute(
                "UPDATE frontier SET state='queued', next_retry=NULL WHERE url=? AND state='done'",
                (row["url"],))
            requeued += cursor.rowcount
        self.conn.commit()
        return requeued

    def recrawl_due(self, now_ts: str, limit: int = 200) -> list[dict]:
        return [
            dict(r)
            for r in self.conn.execute(
                """SELECT * FROM page_state WHERE revoked=0 AND next_recrawl_at IS NOT NULL
                   AND next_recrawl_at<=? ORDER BY next_recrawl_at LIMIT ?""",
                (now_ts, limit),
            )
        ]

    # ------------------------------------------------------------------- audit
    def record_edge(self, parent: str | None, url: str, depth: int, admitted: bool, reason: str) -> None:
        if not parent:
            return
        self.conn.execute(
            """INSERT INTO edges(from_url,to_url,depth,admitted,reason,seen_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(from_url,to_url) DO UPDATE SET depth=excluded.depth,
                 admitted=excluded.admitted, reason=excluded.reason""",
            (parent, url, depth, int(admitted), reason, utc_now()),
        )

    def record_external(self, origin: str, referrer: str) -> None:
        self.conn.execute(
            """INSERT INTO external_candidates(origin,referrer_url,first_seen,sightings)
               VALUES(?,?,?,1) ON CONFLICT(origin,referrer_url)
               DO UPDATE SET sightings=sightings+1""",
            (origin, referrer, utc_now()),
        )
        self.conn.commit()

    def log_fetch(
        self,
        *,
        url: str,
        host: str,
        depth: int,
        status: int | None,
        mime: str,
        size: int,
        outcome: str,
        reason: str,
        latency_ms: int,
        requests: int,
    ) -> None:
        self.conn.execute(
            """INSERT INTO fetch_log(url,host,depth,status,mime,bytes,outcome,reason,
                 at_utc,latency_ms,requests) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (url, host, depth, status, mime, size, outcome, reason,
             utc_now(), latency_ms, requests),
        )
        self.conn.commit()

    def record_rejection(self, url: str, source_id: str, depth: int, reason: str, detail: str = "") -> None:
        self.conn.execute(
            """INSERT INTO rejections(url,source_id,depth,reason,detail,seen_at)
               VALUES(?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET
                 reason=excluded.reason, detail=excluded.detail, seen_at=excluded.seen_at""",
            (url, source_id, depth, reason, detail[:300], utc_now()),
        )
        self.conn.commit()

    def record_sitemap(self, url: str, source_id: str, robots_origin: str) -> None:
        """Sitemap URLs are discovery candidates, never automatic depth-0 seeds."""
        self.conn.execute(
            """INSERT OR IGNORE INTO sitemap_candidates(url,source_id,robots_origin,policy,seen_at)
               VALUES(?,?,?,'candidate_only_requires_review',?)""",
            (url, source_id, robots_origin, utc_now()),
        )
        self.conn.commit()

    def log_redirect(self, *, source_id: str, depth: int, from_url: str | None,
                     to_url: str, hop: int, status: int | None, decision: str,
                     reason: str = "") -> None:
        self.conn.execute(
            """INSERT INTO redirect_log(source_id,depth,from_url,to_url,hop,status,
                 decision,reason,at_utc) VALUES(?,?,?,?,?,?,?,?,?)""",
            (source_id, depth, from_url, to_url, hop, status, decision, reason, utc_now()),
        )
        self.conn.commit()

    def redirect_log(self, limit: int = 200) -> list[dict]:
        return [
            dict(r) for r in self.conn.execute(
                "SELECT * FROM redirect_log ORDER BY id DESC LIMIT ?", (limit,))
        ]

    def redirect_counts(self) -> dict[str, int]:
        return {
            f"{row['decision']}:{row['reason']}": row["n"]
            for row in self.conn.execute(
                "SELECT decision, reason, COUNT(*) n FROM redirect_log "
                "GROUP BY decision, reason ORDER BY n DESC")
        }

    def sitemap_candidates(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM sitemap_candidates ORDER BY url LIMIT 500")]

    def fetches_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        row = self.conn.execute(
            "SELECT COUNT(*) n FROM fetch_log WHERE substr(at_utc,1,10)=?", (today,)
        ).fetchone()
        return int(row["n"])

    def outcome_counts(self) -> dict[str, int]:
        return {
            row["outcome"]: row["n"]
            for row in self.conn.execute(
                "SELECT outcome, COUNT(*) n FROM fetch_log GROUP BY outcome ORDER BY n DESC"
            )
        }

    def rejection_counts(self) -> dict[str, int]:
        return {
            row["reason"]: row["n"]
            for row in self.conn.execute(
                "SELECT reason, COUNT(*) n FROM rejections GROUP BY reason ORDER BY n DESC"
            )
        }

    def external_candidates(self, limit: int = 50) -> list[dict]:
        return [
            dict(r)
            for r in self.conn.execute(
                "SELECT * FROM external_candidates ORDER BY sightings DESC, origin LIMIT ?", (limit,)
            )
        ]

    def start_run(self, run_id: str, config: dict) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO run_log(run_id,started_at,config) VALUES(?,?,?)",
            (run_id, utc_now(), json.dumps(config)),
        )
        self.conn.commit()

    def finish_run(self, run_id: str, counters: dict) -> None:
        self.conn.execute(
            "UPDATE run_log SET finished_at=?, counters=? WHERE run_id=?",
            (utc_now(), json.dumps(counters), run_id),
        )
        self.conn.commit()

    def latest_run(self) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM run_log ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def content_hash_for(self, url: str) -> str | None:
        row = self.conn.execute("SELECT content_hash FROM page_state WHERE url=?", (url,)).fetchone()
        return row["content_hash"] if row else None

    def purge_page(self, url: str, reason: str) -> None:
        self.mark_revoked(url, reason)
        self.conn.execute("UPDATE page_state SET revoked=1, revoked_reason=? WHERE url=?", (reason, url))
        self.conn.commit()
