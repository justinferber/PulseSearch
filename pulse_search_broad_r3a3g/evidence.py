"""Admitted evidence for Wiki candidates.

A URL supplied by a caller is not evidence. Evidence must be registered with
its publisher, rights basis, verification date, topic scope and a short
supporting excerpt. The registry is intentionally small and curated: adding a
source is an editorial decision, not a side effect of a proposal request.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "before", "by", "check", "for",
    "from", "has", "if", "in", "is", "it", "its", "of", "on", "or", "that",
    "the", "their", "then", "this", "to", "use", "with", "your",
}
ALLOWED_RIGHTS = {"public_guidance", "official_reference", "event_announcement"}


class EvidenceError(ValueError):
    pass


def canonical_url(url: str) -> str:
    parts = urlsplit(str(url or "").strip())
    if parts.scheme != "https" or not parts.hostname:
        raise EvidenceError("evidence URLs must be absolute https URLs")
    host = parts.hostname.lower().rstrip(".")
    path = re.sub(r"/+", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return f"https://{host}{path}"


def registrable_domain(host: str) -> str:
    labels = [p for p in str(host or "").lower().strip(".").split(".") if p]
    if len(labels) <= 2:
        return ".".join(labels)
    # Common two-label public suffixes used by the curated sources.
    if ".".join(labels[-2:]) in {"co.uk", "org.uk", "gov.uk", "ac.uk"}:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", str(text or "").lower())
            if len(w) > 2 and w not in STOPWORDS}


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    url: str
    title: str
    publisher: str
    rights: str
    verified_at: str
    excerpt: str
    topics: tuple[str, ...]
    supports: tuple[str, ...]

    @property
    def domain(self) -> str:
        return registrable_domain(urlsplit(self.url).hostname or "")

    def supports_claim(self, claim: str) -> bool:
        claim_tokens = tokens(claim)
        support_tokens = set(tokens(" ".join(self.supports))) | tokens(self.excerpt)
        return bool(claim_tokens & support_tokens)


class EvidenceRegistry:
    def __init__(self, records: list[dict] | None = None):
        self._records: dict[str, Evidence] = {}
        self._by_url: dict[str, Evidence] = {}
        for raw in records or []:
            item = Evidence(
                evidence_id=str(raw["evidence_id"]),
                url=canonical_url(raw["url"]),
                title=str(raw.get("title") or ""),
                publisher=str(raw.get("publisher") or ""),
                rights=str(raw.get("rights") or ""),
                verified_at=str(raw.get("verified_at") or ""),
                excerpt=str(raw.get("excerpt") or ""),
                topics=tuple(raw.get("topics") or ()),
                supports=tuple(raw.get("supports") or ()),
            )
            if not item.evidence_id or not item.publisher:
                raise EvidenceError("evidence needs an id and publisher")
            if item.rights not in ALLOWED_RIGHTS:
                raise EvidenceError(f"unsupported rights class for {item.evidence_id}")
            try:
                date.fromisoformat(item.verified_at)
            except ValueError as exc:
                raise EvidenceError(f"invalid verification date for {item.evidence_id}") from exc
            if item.evidence_id in self._records or item.url in self._by_url:
                raise EvidenceError(f"duplicate evidence {item.evidence_id}")
            self._records[item.evidence_id] = item
            self._by_url[item.url] = item

    @classmethod
    def from_file(cls, path: str | Path) -> "EvidenceRegistry":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data.get("evidence") if isinstance(data, dict) else data)

    def get(self, ref: str, *, topic_id: str, claim: str) -> Evidence:
        key = str(ref or "").strip()
        record = self._records.get(key)
        if record is None:
            try:
                record = self._by_url.get(canonical_url(key))
            except EvidenceError:
                record = None
        if record is None:
            raise EvidenceError(f"evidence is not admitted: {key or '<empty>'}")
        if topic_id not in record.topics and "*" not in record.topics:
            raise EvidenceError(f"evidence {record.evidence_id} is not admitted for {topic_id}")
        if not record.supports_claim(claim):
            raise EvidenceError(f"evidence {record.evidence_id} does not support the claim")
        return record

    def require_independent(self, evidence: list[Evidence], minimum: int = 2) -> None:
        publishers = {e.publisher.strip().lower() for e in evidence}
        domains = {e.domain for e in evidence}
        if len(publishers) < minimum or len(domains) < minimum:
            raise EvidenceError(
                "article needs at least two independent publishers/domains; "
                "multiple URLs from one publisher do not count")
