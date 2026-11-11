"""Source-cited Wiki drafts, editorial workflow and a publisher boundary.

Pulse Search proposes public-evidence-only articles. It is not the Wiki owner
and must not write into Pulse UNITY/UNA directly. This module implements the
consumer-side queue, duplicate/update handling, approval and a local publisher
for tests. A real UNA Wiki adapter must implement :class:`WikiPublisher` after
its ACL/API is verified; no endpoint is invented here.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = """
CREATE TABLE IF NOT EXISTS wiki_pages(
  topic_id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, locale TEXT NOT NULL DEFAULT 'en',
  title TEXT NOT NULL, summary TEXT NOT NULL, body TEXT NOT NULL,
  status TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
  sources TEXT NOT NULL, claims TEXT NOT NULL, verified_at TEXT NOT NULL,
  updated_at TEXT NOT NULL, published_at TEXT, reviewer TEXT,
  rights_class TEXT NOT NULL, evidence_ref TEXT,
  pending_body TEXT, pending_claims TEXT, pending_sources TEXT,
  flag_reason TEXT);
CREATE TABLE IF NOT EXISTS wiki_aliases(alias TEXT PRIMARY KEY, topic_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wiki_revisions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, topic_id TEXT NOT NULL, version INTEGER NOT NULL,
  body TEXT NOT NULL, status TEXT NOT NULL, note TEXT, diff TEXT,
  created_at TEXT NOT NULL, reviewer TEXT);
"""

TRANSIENT_RE = re.compile(r"(°c|°f|£\s?\d|\$\s?\d|€\s?\d|sold out|in stock|"
                          r"currently\s+\d|price\s*:)", re.I)
PII_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d\s-]{8,}\d")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class WikiError(ValueError):
    pass


class PublisherNotConfigured(WikiError):
    pass


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:80]


@dataclass(frozen=True)
class WikiPolicy:
    auto_publish_enabled: bool = False
    authorised_by: str | None = None
    allowed_categories: tuple[str, ...] = ()
    min_sources: int = 2
    max_age_days: int = 365


@dataclass
class WikiPage:
    topic_id: str
    slug: str
    title: str
    summary: str
    body: str
    status: str
    version: int
    sources: list[dict]
    claims: list[dict]
    verified_at: str
    updated_at: str
    published_at: str | None = None
    reviewer: str | None = None
    rights_class: str = "public_guidance"
    evidence_ref: str | None = None
    pending_body: str | None = None
    flag_reason: str | None = None


class WikiPublisher:
    """Adapter boundary for the real Pulse UNITY/UNA Wiki."""

    def publish(self, page: WikiPage) -> dict:
        raise PublisherNotConfigured("Wiki publisher is not configured")

    def unpublish(self, page: WikiPage, reason: str) -> dict:
        raise PublisherNotConfigured("Wiki publisher is not configured")


class LocalPublisher(WikiPublisher):
    """Test/demo publisher; records publication in the local workflow store."""

    def publish(self, page: WikiPage) -> dict:
        return {"ok": True, "target": "local-test-wiki", "slug": page.slug,
                "version": page.version, "published_at": utc_now()}

    def unpublish(self, page: WikiPage, reason: str) -> dict:
        return {"ok": True, "target": "local-test-wiki", "slug": page.slug,
                "unpublished_reason": reason}


class WikiStore:
    def __init__(self, path: str | Path, create: bool = True):
        self.path = Path(path)
        if not create and not self.path.exists():
            raise FileNotFoundError(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=15, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _row(self, topic_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM wiki_pages WHERE topic_id=?",
                                (topic_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        for key in ("sources", "claims", "pending_claims", "pending_sources"):
            data[key] = json.loads(data[key] or "[]")
        return data

    def get(self, topic: str) -> dict | None:
        row = self._row(topic)
        if row:
            return row
        row = self.conn.execute(
            "SELECT topic_id FROM wiki_aliases WHERE alias=?", (slugify(topic),)
        ).fetchone()
        return self._row(row["topic_id"]) if row else None

    def list(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM wiki_pages ORDER BY updated_at DESC")]

    def revisions(self, topic_id: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM wiki_revisions WHERE topic_id=? ORDER BY id", (topic_id,))]


class WikiService:
    def __init__(self, store: WikiStore, publisher: WikiPublisher | None = None):
        self.store = store
        self.publisher = publisher or LocalPublisher()

    # ------------------------------------------------------------------ create
    def propose(self, article: dict, *, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        topic_id = str(article.get("topic_id") or "").strip()
        title = str(article.get("title") or "").strip()
        if not topic_id or not title:
            raise WikiError("topic_id and title are required")
        claims = article.get("claims") or []
        if not isinstance(claims, list) or not claims:
            raise WikiError("at least one claim is required")
        sources, body_lines = [], []
        for claim in claims:
            text = str((claim or {}).get("text") or "").strip()
            urls = [u for u in (claim or {}).get("sources") or [] if str(u).startswith("https://")]
            if not text or not urls:
                raise WikiError("each claim needs text and an https source")
            if PII_RE.search(text):
                raise WikiError("claim contains personal data")
            if TRANSIENT_RE.search(text):
                raise WikiError("transient price/stock/observation text is not publishable")
            body_lines.append(f"- {text}")
            for url in urls:
                if not any(s["url"] == url for s in sources):
                    sources.append({"url": url, "title": urls_title(url),
                                    "publisher": urlsplit(url).hostname or ""})
        rights = str(article.get("rights_class") or "public_guidance")
        if rights not in ("public_guidance", "official_reference", "event_announcement"):
            raise WikiError("unsupported rights class")
        if len({s["url"] for s in sources}) < 2:
            raise WikiError("article needs at least two distinct sources")
        verified = str(article.get("verified_at") or now.date().isoformat())
        try:
            verified_date = date.fromisoformat(verified)
        except ValueError as exc:
            raise WikiError("verified_at must be an ISO date") from exc
        if verified_date > now.date() + timedelta(days=1):
            raise WikiError("verified_at cannot be in the future")
        summary = str(article.get("summary") or "").strip()
        body = self._render(title, summary, body_lines, sources, verified)
        digest = hashlib.sha256(body.encode()).hexdigest()
        existing = self.store.get(topic_id)
        alias = slugify(article.get("alias") or title)
        if existing:
            if hashlib.sha256(str(existing["body"]).encode()).hexdigest() == digest:
                return {"result": "duplicate", "topic_id": existing["topic_id"],
                        "slug": existing["slug"], "status": existing["status"]}
            diff = "\n".join(difflib.unified_diff(
                str(existing["body"]).splitlines(), body.splitlines(),
                fromfile=f"{existing['slug']}@{existing['version']}",
                tofile="proposed", lineterm=""))
            self.store.conn.execute(
                "UPDATE wiki_pages SET pending_body=?, pending_claims=?, pending_sources=?,"
                " status='draft_update', updated_at=? WHERE topic_id=?",
                (body, json.dumps(claims), json.dumps(sources), utc_now(),
                 existing["topic_id"]))
            self.store.conn.execute(
                "INSERT INTO wiki_revisions(topic_id,version,body,status,note,diff,created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (existing["topic_id"], existing["version"] + 1, body, "draft_update",
                 "proposed update", diff, utc_now()))
            self.store.conn.commit()
            return {"result": "update_draft", "topic_id": existing["topic_id"],
                    "slug": existing["slug"], "diff": diff,
                    "previous_version": existing["version"]}
        slug = slugify(article.get("slug") or title)
        if self.store.conn.execute("SELECT 1 FROM wiki_pages WHERE slug=?", (slug,)).fetchone():
            raise WikiError("slug already belongs to another topic")
        self.store.conn.execute(
            """INSERT INTO wiki_pages(topic_id,slug,locale,title,summary,body,status,version,
                 sources,claims,verified_at,updated_at,rights_class,evidence_ref)
               VALUES(?,?,?,?,?,?,'draft',1,?,?,?,?,?,?)""",
            (topic_id, slug, str(article.get("locale") or "en"), title, summary, body,
             json.dumps(sources), json.dumps(claims), verified, utc_now(), rights,
             str(article.get("evidence_ref") or "")))
        self.store.conn.execute(
            "INSERT OR IGNORE INTO wiki_aliases(alias,topic_id) VALUES(?,?)",
            (alias, topic_id))
        self.store.conn.execute(
            "INSERT INTO wiki_revisions(topic_id,version,body,status,note,created_at)"
            " VALUES(?,?,?,?,?,?)", (topic_id, 1, body, "draft", "created", utc_now()))
        self.store.conn.commit()
        return {"result": "draft_created", "topic_id": topic_id, "slug": slug}

    # ------------------------------------------------------------------ review
    def approve(self, topic_id: str, reviewer: str) -> dict:
        if not reviewer.strip():
            raise WikiError("reviewer is required")
        page = self._page(topic_id)
        if page.status not in ("draft", "draft_update", "draft_flagged"):
            raise WikiError(f"cannot approve from {page.status}")
        self.store.conn.execute(
            "UPDATE wiki_pages SET status='approved', reviewer=?, updated_at=? WHERE topic_id=?",
            (reviewer, utc_now(), topic_id))
        self.store.conn.commit()
        return {"result": "approved", "topic_id": topic_id, "status": "approved",
                "reviewer": reviewer}

    def reject(self, topic_id: str, reviewer: str, reason: str) -> dict:
        page = self._page(topic_id)
        if page.status not in ("draft", "draft_update", "approved", "draft_flagged"):
            raise WikiError(f"cannot reject from {page.status}")
        self.store.conn.execute(
            "UPDATE wiki_pages SET status='rejected', reviewer=?, updated_at=? WHERE topic_id=?",
            (reviewer, utc_now(), topic_id))
        self.store.conn.commit()
        return {"result": "rejected", "topic_id": topic_id, "reason": reason}

    # ------------------------------------------------------------------ publish
    def publish(self, topic_id: str, policy: WikiPolicy, reviewer: str | None = None) -> dict:
        page = self._page(topic_id)
        if page.status != "approved":
            raise WikiError("only an approved draft may be published")
        if not policy.auto_publish_enabled:
            raise WikiError("publication is not authorised: automatic publishing is off")
        if not policy.authorised_by:
            raise WikiError("publication ruleset has no authorised owner")
        if reviewer is None and not policy.auto_publish_enabled:
            raise WikiError("reviewer required")
        claims = self.store._row(topic_id) or {}
        sources = claims.get("pending_sources") or claims.get("sources") or []
        if len({s["url"] for s in sources}) < policy.min_sources:
            raise WikiError("not enough independent sources")
        verified = date.fromisoformat(page.verified_at)
        if (datetime.now(timezone.utc).date() - verified).days > policy.max_age_days:
            raise WikiError("verification is too old to publish")
        pending = claims.get("pending_body")
        body = pending or page.body
        result = self.publisher.publish(page)
        self.store.conn.execute(
            "UPDATE wiki_pages SET body=?, status='published', published_at=?,"
            " reviewer=?, version=version+(CASE WHEN pending_body IS NULL THEN 0 ELSE 1 END),"
            " pending_body=NULL, pending_claims=NULL, pending_sources=NULL, updated_at=?"
            " WHERE topic_id=?",
            (body, utc_now(), reviewer or policy.authorised_by, utc_now(), topic_id))
        self.store.conn.commit()
        return {"result": "published", "topic_id": topic_id, "publisher": result,
                "status": "published"}

    def unpublish(self, topic_id: str, reason: str) -> dict:
        page = self._page(topic_id)
        result = self.publisher.unpublish(page, reason)
        self.store.conn.execute(
            "UPDATE wiki_pages SET status='unpublished', flag_reason=?, updated_at=?"
            " WHERE topic_id=?", (reason, utc_now(), topic_id))
        self.store.conn.commit()
        return {"result": "unpublished", "topic_id": topic_id, "reason": reason,
                "publisher": result}

    def flag_source(self, url: str, reason: str) -> dict:
        flagged = []
        for page in self.store.list():
            sources = json.loads(page["sources"] or "[]")
            if not any(s.get("url") == url for s in sources):
                continue
            if page["status"] == "published":
                self.publisher.unpublish(self._page(page["topic_id"]), reason)
            self.store.conn.execute(
                "UPDATE wiki_pages SET status=?, flag_reason=?, updated_at=? WHERE topic_id=?",
                ("flagged" if page["status"] == "published" else "draft_flagged",
                 reason, utc_now(), page["topic_id"]))
            flagged.append(page["topic_id"])
        self.store.conn.commit()
        return {"result": "flagged", "source": url, "reason": reason, "topics": flagged}

    # ------------------------------------------------------------------ helpers
    def _page(self, topic_id: str) -> WikiPage:
        row = self.store._row(topic_id)
        if not row:
            raise WikiError("unknown topic")
        return WikiPage(
            topic_id=row["topic_id"], slug=row["slug"], title=row["title"],
            summary=row["summary"], body=row["body"], status=row["status"],
            version=row["version"], sources=row["sources"], claims=row["claims"],
            verified_at=row["verified_at"], updated_at=row["updated_at"],
            published_at=row["published_at"], reviewer=row["reviewer"],
            rights_class=row["rights_class"], evidence_ref=row["evidence_ref"],
            pending_body=row["pending_body"], flag_reason=row["flag_reason"])

    def _render(self, title, summary, claim_lines, sources, verified) -> str:
        source_lines = "\n".join(f"- [{s['title']}]({s['url']})" for s in sources)
        return (f"# {title}\n\n{summary}\n\n## Guidance\n" + "\n".join(claim_lines)
                + f"\n\n## Sources\n{source_lines}\n\n"
                  f"_Last verified: {verified}. Public-evidence draft; check the linked "
                  "official page before acting._\n")


def urls_title(url: str) -> str:
    host = urlsplit(url).hostname or url
    return host[4:] if host.startswith("www.") else host
