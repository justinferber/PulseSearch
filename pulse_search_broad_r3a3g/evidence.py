"""Admitted evidence and exact fact binding for Wiki candidates.

A URL or a shared word is not evidence. Each publishable claim must name a
registered fact id; the claim text must equal that fact text (after
normalisation), and the fact must be bound to admitted evidence with a topic,
rights class and verification date. Anything else fails closed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

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
    if ".".join(labels[-2:]) in {"co.uk", "org.uk", "gov.uk", "ac.uk"}:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def normal_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))


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

    @property
    def domain(self) -> str:
        return registrable_domain(urlsplit(self.url).hostname or "")


@dataclass(frozen=True)
class Fact:
    fact_id: str
    text: str
    evidence_ids: tuple[str, ...]


class EvidenceRegistry:
    def __init__(self, records: list[dict] | None = None,
                 facts: list[dict] | None = None):
        self._records: dict[str, Evidence] = {}
        self._by_url: dict[str, Evidence] = {}
        self._facts: dict[str, Fact] = {}
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
        for raw in facts or []:
            fact_id = str(raw.get("fact_id") or "")
            text = str(raw.get("text") or "").strip()
            evidence_ids = tuple(str(x) for x in (raw.get("evidence") or ()))
            if not fact_id or not text or not evidence_ids:
                raise EvidenceError("fact needs an id, text and evidence")
            if fact_id in self._facts:
                raise EvidenceError(f"duplicate fact {fact_id}")
            missing = [eid for eid in evidence_ids if eid not in self._records]
            if missing:
                raise EvidenceError(f"fact {fact_id} names unknown evidence {missing[0]}")
            self._facts[fact_id] = Fact(fact_id, text, evidence_ids)

    @classmethod
    def from_file(cls, path: str | Path) -> "EvidenceRegistry":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return cls(data.get("evidence"), data.get("facts"))
        return cls(data)

    def get_fact(self, fact_id: str, *, topic_id: str, claim: str) -> tuple[Fact, list[Evidence]]:
        fact = self._facts.get(str(fact_id or ""))
        if fact is None:
            raise EvidenceError(f"fact is not admitted: {fact_id or '<empty>'}")
        if normal_text(claim) != normal_text(fact.text):
            raise EvidenceError(f"claim text does not match admitted fact {fact.fact_id}")
        records = [self._records[eid] for eid in fact.evidence_ids]
        if not any(topic_id in record.topics or "*" in record.topics for record in records):
            raise EvidenceError(f"fact {fact.fact_id} is not admitted for {topic_id}")
        if not all(record.rights in ALLOWED_RIGHTS for record in records):
            raise EvidenceError(f"fact {fact.fact_id} has unpublishable rights")
        return fact, records

    def get(self, fact_id: str, *, topic_id: str, claim: str) -> Evidence:
        """Compatibility helper: the first evidence record for an exact fact."""
        _, records = self.get_fact(fact_id, topic_id=topic_id, claim=claim)
        return records[0]

    def require_independent(self, evidence: list[Evidence], minimum: int = 2) -> None:
        publishers = {e.publisher.strip().lower() for e in evidence}
        domains = {e.domain for e in evidence}
        if len(publishers) < minimum or len(domains) < minimum:
            raise EvidenceError(
                "article needs at least two independent publishers/domains; "
                "multiple URLs from one publisher do not count")
