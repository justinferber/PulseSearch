"""Source-cited Wiki drafts, editorial workflow and a fail-closed publisher boundary.

Pulse Search proposes public-evidence-only articles. It is not the Wiki owner
and must not write into Pulse UNITY/UNA directly. Publication is impossible
until a publisher adapter is injected explicitly; the default adapter raises
:class:`PublisherNotConfigured`.

Every publish builds an immutable revision from the pending body, sends that
exact revision to the adapter, validates the acknowledgement, and only then
commits the local published state. Retries use a stable idempotency key.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .evidence import Evidence, EvidenceError, EvidenceRegistry, canonical_url

SCHEMA = """
CREATE TABLE IF NOT EXISTS wiki_pages(
  topic_id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, locale TEXT NOT NULL DEFAULT 'en',
  title TEXT NOT NULL, summary TEXT NOT NULL, body TEXT NOT NULL,
  status TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
  sources TEXT NOT NULL, claims TEXT NOT NULL, verified_at TEXT NOT NULL,
  updated_at TEXT NOT NULL, published_at TEXT, reviewer TEXT,
  rights_class TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'general',
  evidence_ref TEXT,
  pending_body TEXT, pending_claims TEXT, pending_sources TEXT,
  pending_version INTEGER, pending_diff TEXT, has_pending INTEGER NOT NULL DEFAULT 0,
  external_id TEXT, external_revision TEXT, external_target TEXT,
  published_checksum TEXT, last_publish_error TEXT, flag_reason TEXT);
CREATE TABLE IF NOT EXISTS wiki_aliases(alias TEXT PRIMARY KEY, topic_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wiki_revisions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, topic_id TEXT NOT NULL, version INTEGER NOT NULL,
  body TEXT NOT NULL, status TEXT NOT NULL, note TEXT, diff TEXT,
  content_hash TEXT, idempotency_key TEXT, external_id TEXT,
  created_at TEXT NOT NULL, reviewer TEXT);
CREATE TABLE IF NOT EXISTS wiki_evidence_revocations(
  url TEXT PRIMARY KEY, reason TEXT NOT NULL, revoked_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wiki_publish_attempts(
  idempotency_key TEXT PRIMARY KEY, topic_id TEXT NOT NULL, version INTEGER NOT NULL,
  state TEXT NOT NULL, receipt TEXT, error TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
"""

TRANSIENT_RE = re.compile(r"(°c|°f|£\s?\d|\$\s?\d|€\s?\d|sold out|in stock|"
                          r"currently\s+\d|price\s*:)", re.I)
PII_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d\s-]{8,}\d")
CATEGORY_RE = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class WikiError(ValueError):
    pass


class PublisherNotConfigured(WikiError):
    pass


class PublisherRejected(WikiError):
    pass


class PublisherConflict(WikiError):
    pass


class InvalidAcknowledgement(PublisherRejected):
    """The adapter returned a receipt that cannot prove the intended write.

    A malformed receipt may still mean the external side committed, so it must
    not be retried blindly. An explicit ``ok=false`` is a safe rejection.
    """

    def __init__(self, message: str, *, potentially_committed: bool = True):
        super().__init__(message)
        self.potentially_committed = potentially_committed


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:80]


def content_hash(body: str) -> str:
    return hashlib.sha256(str(body).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WikiPolicy:
    auto_publish_enabled: bool = False
    authorised_by: str | None = None
    allowed_categories: tuple[str, ...] = ()
    min_independent_publishers: int = 2
    max_age_days: int = 365


@dataclass(frozen=True)
class WikiRevision:
    """Immutable content sent to a publisher and recorded locally."""

    topic_id: str
    slug: str
    title: str
    summary: str
    body: str
    version: int
    base_version: int
    claims: tuple[dict, ...]
    sources: tuple[dict, ...]
    verified_at: str
    rights_class: str
    category: str
    checksum: str
    idempotency_key: str

    def as_dict(self) -> dict:
        return {
            "topic_id": self.topic_id, "slug": self.slug, "title": self.title,
            "summary": self.summary, "body": self.body, "version": self.version,
            "base_version": self.base_version, "claims": list(self.claims),
            "sources": list(self.sources), "verified_at": self.verified_at,
            "rights_class": self.rights_class, "category": self.category,
            "checksum": self.checksum, "idempotency_key": self.idempotency_key,
        }


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
    category: str = "general"
    evidence_ref: str | None = None
    pending_body: str | None = None
    pending_version: int | None = None
    external_id: str | None = None
    external_revision: str | None = None
    flag_reason: str | None = None


class WikiPublisher:
    """Fail-closed adapter boundary for the real Pulse UNITY/UNA Wiki."""

    target = "unconfigured"

    def publish(self, revision: WikiRevision) -> dict:
        raise PublisherNotConfigured("Wiki publisher is not configured")

    def unpublish(self, page: WikiPage, reason: str) -> dict:
        raise PublisherNotConfigured("Wiki publisher is not configured")


class LocalPublisher(WikiPublisher):
    """Explicit test/demo publisher. Never installed by default."""

    target = "local-test-wiki"

    def __init__(self):
        self._seen: dict[str, dict] = {}
        self._locked = threading.Lock()

    def publish(self, revision: WikiRevision) -> dict:
        with self._locked:
            if revision.idempotency_key in self._seen:
                return dict(self._seen[revision.idempotency_key], idempotent=True)
            receipt = {
                "ok": True,
                "target": self.target,
                "external_id": f"local:{revision.slug}",
                "revision": revision.version,
                "checksum": revision.checksum,
                "published_at": utc_now(),
            }
            self._seen[revision.idempotency_key] = receipt
            return receipt

    def unpublish(self, page: WikiPage, reason: str) -> dict:
        return {"ok": True, "target": self.target,
                "external_id": page.external_id or f"local:{page.slug}",
                "revision": page.external_revision or str(page.version),
                "unpublished_reason": reason}


class WikiStore:
    def __init__(self, path: str | Path, create: bool = True):
        self.path = Path(path)
        if not create and not self.path.exists():
            raise FileNotFoundError(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        with self._lock:
            self.conn.executescript(SCHEMA)
            self._migrate()
            self.conn.commit()

    def _migrate(self) -> None:
        additions = {
            "category": "TEXT NOT NULL DEFAULT 'general'",
            "pending_version": "INTEGER",
            "pending_diff": "TEXT",
            "has_pending": "INTEGER NOT NULL DEFAULT 0",
            "external_id": "TEXT",
            "external_revision": "TEXT",
            "external_target": "TEXT",
            "published_checksum": "TEXT",
            "last_publish_error": "TEXT",
        }
        present = {r["name"] for r in self.conn.execute("PRAGMA table_info(wiki_pages)")}
        for name, ddl in additions.items():
            if name not in present:
                self.conn.execute(f"ALTER TABLE wiki_pages ADD COLUMN {name} {ddl}")
        present = {r["name"] for r in self.conn.execute("PRAGMA table_info(wiki_revisions)")}
        for name, ddl in {"content_hash": "TEXT", "idempotency_key": "TEXT",
                          "external_id": "TEXT"}.items():
            if name not in present:
                self.conn.execute(f"ALTER TABLE wiki_revisions ADD COLUMN {name} {ddl}")

    @contextmanager
    def transaction(self):
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
            except BaseException:
                self.conn.rollback()
                raise
            else:
                self.conn.commit()

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def _row(self, topic_id: str) -> dict | None:
        with self._lock:
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
        with self._lock:
            alias = self.conn.execute(
                "SELECT topic_id FROM wiki_aliases WHERE alias=?", (slugify(topic),)
            ).fetchone()
        return self._row(alias["topic_id"]) if alias else None

    def list(self) -> list[dict]:
        with self._lock:
            rows = [dict(r) for r in self.conn.execute(
                "SELECT * FROM wiki_pages ORDER BY updated_at DESC")]
        for row in rows:
            for key in ("sources", "claims", "pending_claims", "pending_sources"):
                row[key] = json.loads(row[key] or "[]")
        return rows

    def revisions(self, topic_id: str) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM wiki_revisions WHERE topic_id=? ORDER BY id", (topic_id,))]

    def revoked_evidence(self) -> dict[str, str]:
        with self._lock:
            return {r["url"]: r["reason"] for r in self.conn.execute(
                "SELECT url, reason FROM wiki_evidence_revocations")}

    def mark_evidence_revoked(self, url: str, reason: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO wiki_evidence_revocations(url, reason, revoked_at) VALUES(?,?,?)"
                " ON CONFLICT(url) DO UPDATE SET reason=excluded.reason,"
                " revoked_at=excluded.revoked_at", (canonical_url(url), reason, utc_now()))
            self.conn.commit()

    def attempt(self, key: str) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM wiki_publish_attempts WHERE idempotency_key=?",
                (key,)).fetchone()
        return dict(row) if row else None

    def begin_attempt(self, key: str, topic_id: str, version: int) -> None:
        now = utc_now()
        with self._lock:
            self.conn.execute(
                "INSERT INTO wiki_publish_attempts(idempotency_key,topic_id,version,state,"
                "created_at,updated_at) VALUES(?,?,?,'running',?,?)"
                " ON CONFLICT(idempotency_key) DO UPDATE SET state='running',"
                " error=NULL, updated_at=excluded.updated_at", (key, topic_id, version, now, now))
            self.conn.commit()

    def finish_attempt(self, key: str, state: str, receipt: dict | None = None,
                       error: str | None = None) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE wiki_publish_attempts SET state=?, receipt=?, error=?, updated_at=?"
                " WHERE idempotency_key=?",
                (state, json.dumps(receipt) if receipt is not None else None,
                 error, utc_now(), key))
            self.conn.commit()


class WikiService:
    def __init__(self, store: WikiStore, publisher: WikiPublisher | None = None,
                 evidence: EvidenceRegistry | None = None,
                 evidence_path: str | Path | None = None):
        self.store = store
        self.publisher = publisher or WikiPublisher()
        if evidence is None:
            path = Path(evidence_path) if evidence_path else (
                Path(__file__).resolve().parents[1] / "config/wiki_evidence.json")
            evidence = EvidenceRegistry.from_file(path) if path.exists() else EvidenceRegistry()
        self.evidence = evidence
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ create
    def propose(self, article: dict, *, now: datetime | None = None) -> dict:
        with self._lock:
            return self._propose(article, now or datetime.now(timezone.utc))

    def _propose(self, article: dict, now: datetime) -> dict:
        topic_id = str(article.get("topic_id") or "").strip()
        title = str(article.get("title") or "").strip()
        summary = str(article.get("summary") or "").strip()
        category = str(article.get("category") or "general").strip().lower()
        if not topic_id or not title:
            raise WikiError("topic_id and title are required")
        if not CATEGORY_RE.match(category):
            raise WikiError("category must be a short lowercase identifier")
        claims = article.get("claims") or []
        if not isinstance(claims, list) or not claims:
            raise WikiError("at least one claim is required")
        rights = str(article.get("rights_class") or "public_guidance")
        if rights not in ("public_guidance", "official_reference", "event_announcement"):
            raise WikiError("unsupported rights class")
        verified = str(article.get("verified_at") or now.date().isoformat())
        try:
            verified_date = date.fromisoformat(verified)
        except ValueError as exc:
            raise WikiError("verified_at must be an ISO date") from exc
        if verified_date > now.date() + timedelta(days=1):
            raise WikiError("verified_at cannot be in the future")

        revoked = self.store.revoked_evidence()
        body_lines: list[str] = []
        resolved: list[dict] = []
        accepted: list[Evidence] = []
        clean_claims: list[dict] = []
        for claim in claims:
            if not isinstance(claim, dict):
                raise WikiError("each claim must be an object")
            text = str(claim.get("text") or "").strip()
            refs = claim.get("evidence") or claim.get("sources") or []
            fact_id = str(claim.get("fact_id") or "").strip()
            if not text or not isinstance(refs, list) or not refs:
                raise WikiError("each claim needs text, evidence ids and a fact_id")
            if not fact_id:
                raise WikiError("each claim needs a registered fact_id; URLs alone are not evidence")
            if "sources" in claim or "source_urls" in claim:
                raise WikiError("caller-supplied source URLs are not accepted; use fact_id")
            if PII_RE.search(text):
                raise WikiError("claim contains personal data")
            if TRANSIENT_RE.search(text):
                raise WikiError("transient price/stock/observation text is not publishable")
            try:
                _fact, fact_evidence = self.evidence.get_fact(
                    fact_id, topic_id=topic_id, claim=text)
            except EvidenceError as exc:
                raise WikiError(str(exc)) from exc
            claim_evidence: list[str] = []
            for ev in fact_evidence:
                if ev.evidence_id not in refs:
                    raise WikiError(f"fact {fact_id} is not bound to requested evidence {ev.evidence_id}")
                if ev.url in revoked:
                    raise WikiError(f"evidence is revoked: {ev.evidence_id}")
                accepted.append(ev)
                claim_evidence.append(ev.evidence_id)
                if not any(s["url"] == ev.url for s in resolved):
                    resolved.append({
                        "evidence_id": ev.evidence_id, "url": ev.url, "title": ev.title,
                        "publisher": ev.publisher, "domain": ev.domain,
                        "rights": ev.rights, "verified_at": ev.verified_at,
                        "excerpt": ev.excerpt,
                    })
            clean_claims.append({"text": text, "evidence": claim_evidence,
                                 "fact_id": fact_id})
            body_lines.append(f"- {text}")
        try:
            self.evidence.require_independent(accepted, minimum=2)
        except EvidenceError as exc:
            raise WikiError(str(exc)) from exc

        body = self._render(title, summary, body_lines, resolved, verified)
        digest = content_hash(body)
        existing = self.store.get(topic_id)
        if existing:
            if existing.get("has_pending"):
                if content_hash(existing.get("pending_body") or "") == digest:
                    return {"result": "duplicate_pending", "topic_id": existing["topic_id"],
                            "slug": existing["slug"], "status": existing["status"]}
                version = int(existing.get("pending_version") or existing["version"] + 1)
            else:
                if content_hash(existing["body"]) == digest:
                    return {"result": "duplicate", "topic_id": existing["topic_id"],
                            "slug": existing["slug"], "status": existing["status"]}
                version = existing["version"] + 1
            diff = "\n".join(difflib.unified_diff(
                str(existing["body"]).splitlines(), body.splitlines(),
                fromfile=f"{existing['slug']}@{existing['version']}",
                tofile=f"pending@{version}", lineterm=""))
            status = existing["status"]
            if status not in ("published", "flagged", "unpublished"):
                status = "draft_update"
            with self.store.transaction() as conn:
                conn.execute(
                    "UPDATE wiki_pages SET pending_body=?, pending_claims=?, pending_sources=?,"
                    " pending_version=?, pending_diff=?, has_pending=1, status=?, updated_at=?"
                    " WHERE topic_id=?",
                    (body, json.dumps(clean_claims), json.dumps(resolved), version, diff,
                     status, utc_now(), existing["topic_id"]))
                conn.execute(
                    "INSERT INTO wiki_revisions(topic_id,version,body,status,note,diff,"
                    "content_hash,created_at) VALUES(?,?,?,'draft_update',?,?,?,?)",
                    (existing["topic_id"], version, body, "proposed update", diff, digest,
                     utc_now()))
            return {"result": "update_draft", "topic_id": existing["topic_id"],
                    "slug": existing["slug"], "diff": diff,
                    "previous_version": existing["version"], "pending_version": version}

        slug = slugify(article.get("slug") or title)
        if not slug:
            raise WikiError("title does not produce a usable slug")
        with self.store.transaction() as conn:
            if conn.execute("SELECT 1 FROM wiki_pages WHERE slug=?", (slug,)).fetchone():
                raise WikiError("slug already belongs to another topic")
            conn.execute(
                """INSERT INTO wiki_pages(topic_id,slug,locale,title,summary,body,status,version,
                     sources,claims,verified_at,updated_at,rights_class,category,evidence_ref,
                     has_pending)
                   VALUES(?,?,?,?,?,?,'draft',1,?,?,?,?,?,?,?,0)""",
                (topic_id, slug, str(article.get("locale") or "en"), title, summary, body,
                 json.dumps(resolved), json.dumps(clean_claims), verified, utc_now(), rights,
                 category, str(article.get("evidence_ref") or "")))
            conn.execute(
                "INSERT OR IGNORE INTO wiki_aliases(alias,topic_id) VALUES(?,?)",
                (slugify(article.get("alias") or title), topic_id))
            conn.execute(
                "INSERT INTO wiki_revisions(topic_id,version,body,status,note,content_hash,"
                "created_at) VALUES(?,?,?,'draft','created',?,?)",
                (topic_id, 1, body, digest, utc_now()))
        return {"result": "draft_created", "topic_id": topic_id, "slug": slug}

    # ------------------------------------------------------------------ review
    def approve(self, topic_id: str, reviewer: str) -> dict:
        with self._lock:
            if not reviewer.strip():
                raise WikiError("reviewer is required")
            page = self._page(topic_id)
            if page.status not in ("draft", "draft_update", "draft_flagged",
                                   "approved_update", "published", "flagged"):
                raise WikiError(f"cannot approve from {page.status}")
            row = self.store._row(topic_id) or {}
            if row.get("has_pending"):
                status = "approved_update"
                version = int(row.get("pending_version") or page.version + 1)
                note = "pending update approved"
            else:
                status = "approved"
                version = page.version
                note = "draft approved"
            if page.status == status and not row.get("has_pending"):
                return {"result": "already_approved", "topic_id": topic_id,
                        "status": status, "reviewer": reviewer}
            with self.store.transaction() as conn:
                conn.execute(
                    "UPDATE wiki_pages SET status=?, reviewer=?, updated_at=? WHERE topic_id=?",
                    (status, reviewer, utc_now(), topic_id))
                conn.execute(
                    "UPDATE wiki_revisions SET status=?, reviewer=?, note=?"
                    " WHERE topic_id=? AND version=? AND status IN ('draft','draft_update')",
                    (status, reviewer, note, topic_id, version))
            return {"result": "approved", "topic_id": topic_id, "status": status,
                    "reviewer": reviewer, "version": version}

    def reject(self, topic_id: str, reviewer: str, reason: str) -> dict:
        with self._lock:
            if not reviewer.strip() or not reason.strip():
                raise WikiError("reviewer and reason are required")
            page = self._page(topic_id)
            if page.status not in ("draft", "draft_update", "approved", "approved_update",
                                   "draft_flagged", "flagged"):
                raise WikiError(f"cannot reject from {page.status}")
            row = self.store._row(topic_id) or {}
            had_pending = bool(row.get("has_pending"))
            final_status = page.status
            if had_pending:
                final_status = "published" if page.external_id else "rejected"
            else:
                final_status = "rejected"
            with self.store.transaction() as conn:
                conn.execute(
                    "UPDATE wiki_pages SET status=?, reviewer=?, flag_reason=?,"
                    " pending_body=NULL, pending_claims=NULL, pending_sources=NULL,"
                    " pending_version=NULL, pending_diff=NULL, has_pending=0, updated_at=?"
                    " WHERE topic_id=?",
                    (final_status, reviewer, reason if had_pending else page.flag_reason,
                     utc_now(), topic_id))
                conn.execute(
                    "UPDATE wiki_revisions SET status='rejected', reviewer=?, note=?"
                    " WHERE topic_id=? AND status IN ('draft','draft_update','approved',"
                    "'approved_update')",
                    (reviewer, reason, topic_id))
            return {"result": "rejected", "topic_id": topic_id, "reason": reason,
                    "status": final_status}

    # ------------------------------------------------------------------ publish
    def publish(self, topic_id: str, policy: WikiPolicy, reviewer: str | None = None) -> dict:
        with self._lock:
            page = self._page(topic_id)
            if page.status not in ("approved", "approved_update"):
                raise WikiError("only an approved draft or update may be published")
            if not policy.auto_publish_enabled:
                raise WikiError("publication is not authorised: automatic publishing is off")
            if not policy.authorised_by:
                raise WikiError("publication ruleset has no authorised owner")
            if reviewer is not None and not reviewer.strip():
                raise WikiError("reviewer must not be blank")
            if not policy.allowed_categories:
                raise WikiError("publication policy must declare allowed categories")
            if page.category not in policy.allowed_categories:
                raise WikiError(f"category {page.category} is not allowed by policy")
            if self.publisher.target == "unconfigured":
                raise PublisherNotConfigured("Wiki publisher is not configured")
            revision = self._revision_for_publish(page)
            self._validate_revision(revision, policy)
            key = revision.idempotency_key
            attempt = self.store.attempt(key)
            if attempt and attempt["state"] == "completed":
                return {"result": "already_published", "topic_id": topic_id,
                        "publisher": json.loads(attempt.get("receipt") or "{}"),
                        "status": "published"}
            if attempt and attempt["state"] in ("acknowledged_local_failed",):
                receipt = json.loads(attempt.get("receipt") or "{}")
                self._commit_publication(page, revision, receipt, reviewer, policy)
                return {"result": "published_after_retry", "topic_id": topic_id,
                        "publisher": receipt, "status": "published"}
            if attempt and attempt["state"] in ("needs_reconciliation", "invalid_acknowledgement"):
                raise WikiError(
                    "publisher acknowledgement is unverified; reconcile the external "
                    "revision before retrying (no blind resubmission)")
            if attempt and attempt["state"] == "running":
                raise WikiError("a publication attempt for this revision is already running")
            self.store.begin_attempt(key, topic_id, revision.version)
            try:
                receipt = self.publisher.publish(revision)
                self._validate_receipt(receipt, revision)
            except PublisherConflict:
                self.store.finish_attempt(key, "conflict", error="external revision conflict")
                raise
            except InvalidAcknowledgement as exc:
                state = "needs_reconciliation" if exc.potentially_committed else "rejected"
                self.store.finish_attempt(key, state, receipt=receipt, error=str(exc))
                with self.store.transaction() as conn:
                    conn.execute("UPDATE wiki_pages SET last_publish_error=? WHERE topic_id=?",
                                 (str(exc), topic_id))
                raise
            except Exception as exc:
                self.store.finish_attempt(key, "failed", error=str(exc))
                with self.store.transaction() as conn:
                    conn.execute("UPDATE wiki_pages SET last_publish_error=? WHERE topic_id=?",
                                 (str(exc), topic_id))
                raise PublisherRejected(f"publisher rejected the revision: {exc}") from exc
            try:
                self._commit_publication(page, revision, receipt, reviewer, policy)
            except Exception as exc:
                self.store.finish_attempt(key, "acknowledged_local_failed",
                                          receipt=receipt, error=str(exc))
                raise WikiError("publisher acknowledged the write but local commit failed; "
                                "retry will reconcile without a second external write") from exc
            self.store.finish_attempt(key, "completed", receipt=receipt)
            return {"result": "published", "topic_id": topic_id, "publisher": receipt,
                    "status": "published", "version": revision.version,
                    "checksum": revision.checksum}

    def _revision_for_publish(self, page: WikiPage) -> WikiRevision:
        row = self.store._row(page.topic_id) or {}
        pending = bool(row.get("has_pending"))
        body = str(row.get("pending_body") or page.body) if pending else page.body
        claims = row.get("pending_claims") if pending else page.claims
        sources = row.get("pending_sources") if pending else page.sources
        version = int(row.get("pending_version") or page.version + 1) if pending else page.version
        checksum = content_hash(body)
        key = hashlib.sha256(
            f"{page.topic_id}|{version}|{checksum}|{self.publisher.target}".encode()
        ).hexdigest()
        return WikiRevision(
            topic_id=page.topic_id, slug=page.slug, title=page.title, summary=page.summary,
            body=body, version=version, base_version=page.version,
            claims=tuple(claims or []), sources=tuple(sources or []),
            verified_at=page.verified_at, rights_class=page.rights_class,
            category=page.category, checksum=checksum, idempotency_key=key)

    def _validate_revision(self, revision: WikiRevision, policy: WikiPolicy) -> None:
        try:
            verified = date.fromisoformat(revision.verified_at)
        except ValueError as exc:
            raise WikiError("stored verification date is invalid") from exc
        if (datetime.now(timezone.utc).date() - verified).days > policy.max_age_days:
            raise WikiError("verification is too old to publish")
        if not revision.claims or not revision.sources:
            raise WikiError("revision has no claims or sources")
        if content_hash(revision.body) != revision.checksum:
            raise WikiError("revision checksum does not match its body")
        if revision.version < 1:
            raise WikiError("revision version must be positive")
        revoked = self.store.revoked_evidence()
        evidence: list[Evidence] = []
        for claim in revision.claims:
            text = str(claim.get("text") or "")
            fact_id = str(claim.get("fact_id") or "")
            if not fact_id:
                raise WikiError("revision claim has no registered fact_id")
            try:
                _fact, matched_records = self.evidence.get_fact(
                    fact_id, topic_id=revision.topic_id, claim=text)
            except EvidenceError as exc:
                raise WikiError(str(exc)) from exc
            for matched in matched_records:
                if matched.url in revoked:
                    raise WikiError(f"evidence was revoked: {matched.url}")
                evidence.append(matched)
        source_urls = {str(source.get("url") or "") for source in revision.sources}
        accepted_urls = {item.url for item in evidence}
        if not accepted_urls or not accepted_urls.issubset(source_urls):
            raise WikiError("revision sources do not match its admitted facts")
        try:
            self.evidence.require_independent(
                evidence, minimum=policy.min_independent_publishers)
        except EvidenceError as exc:
            raise WikiError(str(exc)) from exc

    def _validate_receipt(self, receipt: dict, revision: WikiRevision) -> None:
        if not isinstance(receipt, dict):
            raise InvalidAcknowledgement("publisher returned no receipt object")
        if receipt.get("ok") is not True:
            raise InvalidAcknowledgement("publisher did not return ok=true",
                                         potentially_committed=False)
        if str(receipt.get("target") or "") != self.publisher.target:
            raise InvalidAcknowledgement("publisher acknowledgement target does not match")
        if not str(receipt.get("external_id") or "").strip():
            raise InvalidAcknowledgement("publisher acknowledgement has no external id")
        if str(receipt.get("revision") or "") != str(revision.version):
            raise InvalidAcknowledgement("publisher acknowledged a different revision")
        if not str(receipt.get("checksum") or "").strip():
            raise InvalidAcknowledgement("publisher acknowledgement has no checksum")
        if receipt.get("checksum") != revision.checksum:
            raise InvalidAcknowledgement("publisher acknowledged different content")

    def _commit_publication(self, page: WikiPage, revision: WikiRevision, receipt: dict,
                            reviewer: str | None, policy: WikiPolicy) -> None:
        with self.store.transaction() as conn:
            conn.execute(
                "UPDATE wiki_pages SET body=?, sources=?, claims=?, version=?, status='published',"
                " published_at=?, reviewer=?, pending_body=NULL, pending_claims=NULL,"
                " pending_sources=NULL, pending_version=NULL, pending_diff=NULL, has_pending=0,"
                " external_id=?, external_revision=?, external_target=?, published_checksum=?,"
                " last_publish_error=NULL, updated_at=? WHERE topic_id=?",
                (revision.body, json.dumps(list(revision.sources)),
                 json.dumps(list(revision.claims)), revision.version, utc_now(),
                 reviewer or policy.authorised_by, receipt["external_id"],
                 str(receipt.get("revision") or revision.version), self.publisher.target,
                 revision.checksum, utc_now(), page.topic_id))
            conn.execute(
                "UPDATE wiki_revisions SET status='published', reviewer=?, note=?,"
                " external_id=?, idempotency_key=? WHERE topic_id=? AND version=?",
                (reviewer or policy.authorised_by, "published revision",
                 receipt["external_id"], revision.idempotency_key, page.topic_id,
                 revision.version))

    def unpublish(self, topic_id: str, reason: str) -> dict:
        with self._lock:
            page = self._page(topic_id)
            if not page.external_id:
                raise WikiError("page has no external publication identity")
            result = self.publisher.unpublish(page, reason)
            self._validate_unpublish(result, page)
            with self.store.transaction() as conn:
                conn.execute(
                    "UPDATE wiki_pages SET status='unpublished', flag_reason=?, updated_at=?"
                    " WHERE topic_id=?", (reason, utc_now(), topic_id))
                conn.execute(
                    "INSERT INTO wiki_revisions(topic_id,version,body,status,note,created_at)"
                    " VALUES(?,?,?,'unpublished',?,?)",
                    (topic_id, page.version, page.body, reason, utc_now()))
            return {"result": "unpublished", "topic_id": topic_id, "reason": reason,
                    "publisher": result}

    def flag_source(self, url: str, reason: str) -> dict:
        with self._lock:
            canonical = canonical_url(url)
            self.store.mark_evidence_revoked(canonical, reason)
            flagged = []
            for page in self.store.list():
                live_match = any(s.get("url") == canonical for s in page["sources"])
                pending_match = any(s.get("url") == canonical
                                    for s in (page.get("pending_sources") or []))
                if not live_match and not pending_match:
                    continue
                if page["status"] == "published" and live_match:
                    model = self._page(page["topic_id"])
                    receipt = self.publisher.unpublish(model, reason)
                    self._validate_unpublish(receipt, model)
                    status = "flagged"
                elif pending_match and page["status"] in ("published", "approved_update"):
                    status = "published"
                else:
                    status = "draft_flagged"
                with self.store.transaction() as conn:
                    conn.execute(
                        "UPDATE wiki_pages SET status=?, flag_reason=?, updated_at=?,"
                        " has_pending=CASE WHEN ? THEN 0 ELSE has_pending END,"
                        " pending_body=CASE WHEN ? THEN NULL ELSE pending_body END,"
                        " pending_claims=CASE WHEN ? THEN NULL ELSE pending_claims END,"
                        " pending_sources=CASE WHEN ? THEN NULL ELSE pending_sources END,"
                        " pending_version=CASE WHEN ? THEN NULL ELSE pending_version END,"
                        " pending_diff=CASE WHEN ? THEN NULL ELSE pending_diff END"
                        " WHERE topic_id=?",
                        (status, reason, utc_now(), int(pending_match), int(pending_match),
                         int(pending_match), int(pending_match), int(pending_match),
                         int(pending_match), page["topic_id"]))
                    conn.execute(
                        "INSERT INTO wiki_revisions(topic_id,version,body,status,note,created_at)"
                        " VALUES(?,?,?,'source_revoked',?,?)",
                        (page["topic_id"], page["version"], page["body"],
                         f"source revoked: {canonical} ({reason})", utc_now()))
                flagged.append(page["topic_id"])
            return {"result": "flagged", "source": canonical, "reason": reason,
                    "topics": flagged}

    def _validate_unpublish(self, receipt: dict, page: WikiPage) -> None:
        if not isinstance(receipt, dict) or receipt.get("ok") is not True:
            raise PublisherRejected("unpublish was not acknowledged")
        if str(receipt.get("target") or "") != self.publisher.target:
            raise PublisherRejected("unpublish acknowledgement target does not match")
        if page.external_id and str(receipt.get("external_id") or page.external_id) != page.external_id:
            raise PublisherRejected("unpublish acknowledgement has a different external id")

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
            rights_class=row["rights_class"], category=row.get("category", "general"),
            evidence_ref=row["evidence_ref"], pending_body=row["pending_body"],
            pending_version=row.get("pending_version"),
            external_id=row.get("external_id"),
            external_revision=row.get("external_revision"),
            flag_reason=row.get("flag_reason"))

    def _render(self, title, summary, claim_lines, sources, verified) -> str:
        source_lines = "\n".join(
            f"- [{s['title']}]({s['url']}) — {s['publisher']} "
            f"({s['evidence_id']}, verified {s['verified_at']})" for s in sources)
        return (f"# {title}\n\n{summary}\n\n## Guidance\n" + "\n".join(claim_lines)
                + f"\n\n## Sources\n{source_lines}\n\n"
                  f"_Last verified: {verified}. Public-evidence draft; check the linked "
                  "official page before acting._\n")
