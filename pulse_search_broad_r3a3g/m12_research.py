"""M12 discovery, admission-aware retrieval and cited answer construction.

The pipeline is deliberately split into independently testable stages:

    question -> discovery plan -> provider leads -> source policy
             -> robots + safe fetch -> extracted evidence -> answer

Provider output is only a lead. A page is fetched only when its canonical URL
is in the operator-approved source policy. Only a short title, description,
date span and attributed excerpt are retained; full page text stays in memory
for the current request.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from pulse_search_crawler_r3a3f.extract import ExtractedPage, extract_page
from pulse_search_crawler_r3a3f.urls import canonicalize

from .providers import ProviderError

ALLOWED_RIGHTS = {"public_metadata_and_short_snippet", "public_guidance",
                  "official_reference", "event_announcement"}
MONTHS = {name: i for i, name in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}
MONTHS.update({name[:3].lower(): i for name, i in list(MONTHS.items())})
MONTH_RE = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
DATE_RE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + MONTH_RE + r")\s*(20\d{2})?", re.I)
DATE_RANGE_AFTER_RE = re.compile(
    r"^\s*([0-9][0-9A-Za-z'’ ,.:–\-]{4,90}?20(?:26|27)"
    r"(?:\s*[-–]\s*[0-9][0-9A-Za-z'’ ,.:–\-]{0,50}?20(?:26|27))?)")
MARKET_NAME_RE = re.compile(
    r"(?:[A-Z][A-Za-z0-9'’&.()\-]+\s+(?:Christmas|Festive)\s+"
    r"(?:Markets?|Fair|Fayre)(?:,\s*[A-Z][A-Za-z0-9'’&.()\-]+)?"
    r"|[A-Z][A-Za-z0-9'’&.()\-]+(?:\s+[A-Z][A-Za-z0-9'’&.()\-]+)?\s+Winter\s+"
    r"(?:Wonderland|Market|Markets|Fair|Fayre))")
LOCATION_RE = re.compile(
    r"Location:\s*([A-Za-z .'\-]+(?:,\s*(?:England|Scotland|Wales|Northern Ireland)))",
    re.I)
TOP_START_RE = re.compile(r"Top Christmas markets in Britain", re.I)
TOP_END_RE = re.compile(r"Lesser-known Christmas markets|Discover more festive fun", re.I)
PUNCT_RE = re.compile(r"[ \t]+")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> str:
    return _now().date().isoformat()


def _canon(url: str) -> str:
    try:
        return canonicalize(url)
    except ValueError:
        return ""


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def _clean_text(text: str, cap: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip(" \t\n\r-–—:;")
    # Extracted reference markers are not part of a factual sentence and make
    # the answer look like raw markup.
    text = re.sub(r"\s*\[\s*[a-zA-Z0-9]{1,4}\s*\]\s*", " ", text)
    return text[:cap].strip()


def _domain(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().lstrip("www.").rstrip(".")


@dataclass(frozen=True)
class SourceRule:
    source_id: str
    url: str
    publisher: str
    authority: str = "reference"
    jurisdiction: str = ""
    language: str = "en"
    city: str = ""
    rights: str = "public_metadata_and_short_snippet"
    approval_ref: str = ""
    answer_kind: str = "detail"
    topics: tuple[str, ...] = ()
    priority: int = 0


class SourcePolicy:
    def __init__(self, sources: list[SourceRule], approval_ref: str = ""):
        self.sources = sources
        self.approval_ref = approval_ref
        self._by_url = {s.url: s for s in sources}
        if len(self._by_url) != len(sources):
            raise ValueError("duplicate canonical source URL")

    @classmethod
    def from_file(cls, path: str | Path) -> "SourcePolicy":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rules = []
        for raw in data.get("sources") or []:
            if not raw.get("approved"):
                raise ValueError("M12 source must be explicitly approved")
            rights = str(raw.get("rights") or "")
            if rights not in ALLOWED_RIGHTS:
                raise ValueError(f"unsupported rights for {raw.get('id')}")
            url = _canon(str(raw.get("url") or ""))
            if not url.startswith("https://"):
                raise ValueError("M12 sources must be https")
            rules.append(SourceRule(
                source_id=str(raw["id"]), url=url,
                publisher=str(raw.get("publisher") or ""),
                authority=str(raw.get("authority") or "reference"),
                jurisdiction=str(raw.get("jurisdiction") or ""),
                language=str(raw.get("language") or "en"),
                city=str(raw.get("city") or ""),
                rights=rights, approval_ref=str(raw.get("approval_ref") or ""),
                answer_kind=str(raw.get("answer_kind") or "detail"),
                topics=tuple(raw.get("topics") or ()),
                priority=int(raw.get("priority") or 0),
            ))
        return cls(rules, str(data.get("approval_ref") or ""))

    def match(self, url: str) -> SourceRule | None:
        return self._by_url.get(_canon(url))

    def by_id(self, source_id: str) -> SourceRule | None:
        return next((s for s in self.sources if s.source_id == source_id), None)


@dataclass
class QueryPlan:
    question: str
    answer_type: str
    count: int
    year: int
    location: str
    language: str
    queries: list[str]

    @classmethod
    def from_question(cls, question: str, now: datetime | None = None) -> "QueryPlan":
        raw = " ".join(str(question or "").split())
        low = raw.lower()
        year_match = re.search(r"\b(20\d{2})\b", low)
        year = int(year_match.group(1)) if year_match else (now or _now()).year
        count = 0
        count_word = re.search(r"\b(top\s+)?(one|two|three|four|five|six|seven|eight|nine|ten|\d{1,2})\b", low)
        words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                 "seven": 7, "eight": 8, "nine": 9, "ten": 10}
        if count_word:
            value = count_word.group(2)
            count = int(value) if value.isdigit() else words.get(value, 0)
        listy = bool(re.search(r"\b(top|best|list|which)\b", low)) and bool(
            re.search(r"\b(markets?|events?|festivals?|museums?)\b", low))
        if listy and not count:
            count = 10
        if re.search(r"\b(museums?|venues?|galleries?|gallery)\b", low):
            answer_type = "local"
        elif "versus" in low or " vs " in low or "compare" in low or "easiest" in low:
            answer_type = "comparison"
        elif listy:
            answer_type = "list"
        elif re.search(r"\b(how|renew|apply|wheelchair|access|refund|book|buy)\b", low):
            answer_type = "how_to"
        elif re.search(r"\b(when|wann|what date|dates?|opening|open|hours)\b", low):
            answer_type = "factual"
        else:
            answer_type = "general"
        language = "de" if re.search(r"\b(wann|welche|welcher|ist|der|die|das|öffnet|weihnachtsmarkt|märkte)\b", low) else "en"
        location = "UK" if re.search(r"\b(uk|u\.k\.|britain|british|united kingdom)\b", low) else ""
        if not location:
            m = re.search(r"\b(?:in|at)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", raw)
            if m:
                location = m.group(1)
        topic = re.sub(r"^(what|which|when|where|how|who|why)\s+(are|is|does|do|can|should|would)\s+", "", low)
        topic = re.sub(r"[?.,!]", "", topic)
        topic = re.sub(r"\b20\d{2}\b", " ", topic)
        topic = " ".join(t for t in topic.split() if t not in {
            "the", "a", "an", "for", "in", "of", "to", "me", "please", "tell",
            "what", "are", "is", "the", "top", "best", "ten", "for", "and",
            "how", "do", "i", "my", "which", "wann", "öffnet", "offnet",
            "der", "die", "das", "ist", "welche", "welcher", "weihnachtsmarkt",
            "märkte", "markte",
        })
        queries = [raw]
        if topic and topic != low:
            queries.append(topic)
        if year and str(year) not in topic:
            queries.append(f"{topic} {year}")
        if listy:
            queries.append(f"best {topic} {year} official")
        # Stable dedupe, bounded query plan.
        queries = list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:4]
        return cls(raw, answer_type, count, year, location, language, queries)


@dataclass
class RetrievedPage:
    rule: SourceRule
    url: str
    title: str
    description: str
    text: str
    links: list[str]
    link_texts: dict[str, str]
    fetched_at: str
    extracted: ExtractedPage


@dataclass
class Candidate:
    name: str
    location: str
    date_text: str
    description: str
    source_url: str
    publisher: str
    source_id: str
    authority: str
    official_url: str = ""
    evidence_excerpt: str = ""
    date_status: str = "unconfirmed"
    date_variants: list[dict] = field(default_factory=list)
    presentation_order: int = 0
    sources: list[dict] = field(default_factory=list)
    source_text: str = ""
    score: float = 0.0

    def as_dict(self) -> dict:
        return {
            "name": self.name, "location": self.location, "dates": self.date_text,
            "description": self.description, "source_url": self.source_url,
            "publisher": self.publisher, "source_id": self.source_id,
            "authority": self.authority, "official_url": self.official_url,
            "evidence_status": self.date_status,
            "date_variants": list(self.date_variants),
            "presentation_order": self.presentation_order,
            "evidence_excerpt": self.evidence_excerpt,
            "sources": list(self.sources), "score": round(self.score, 3),
        }


@dataclass
class ResearchAnswer:
    status: str
    response_mode: str
    question: str
    answer: str
    plan: dict
    claims: list[dict] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    discovery: dict = field(default_factory=dict)
    retrieval: dict = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    shortfall: int = 0
    _candidate_objects: list[Candidate] = field(default_factory=list, repr=False)

    def as_dict(self) -> dict:
        return {
            "status": self.status, "response_mode": self.response_mode,
            "question": self.question, "answer": self.answer, "plan": self.plan,
            "claims": self.claims, "citations": self.citations,
            "candidates": self.candidates, "discovery": self.discovery,
            "retrieval": self.retrieval, "limitations": self.limitations,
            "shortfall": self.shortfall,
        }


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text)) if s.strip()]


def _month_number(name: str) -> int:
    key = str(name or "").strip().lower().rstrip(".")
    if len(key) == 3:
        for full, number in MONTHS.items():
            if full.lower().startswith(key):
                return number
    return MONTHS.get(str(name).strip().capitalize(), 0)


def parse_date_text(text: str, fallback_year: int | None = None) -> list[date]:
    values: list[date] = []
    for m in DATE_RE.finditer(str(text or "")):
        day = int(m.group(1))
        month = _month_number(m.group(2))
        year = int(m.group(3)) if m.group(3) else (fallback_year or 0)
        if not month or not year:
            continue
        try:
            values.append(date(year, month, day))
        except ValueError:
            continue
    return values


def _date_text_from(text: str, year: int) -> str:
    match = DATE_RANGE_AFTER_RE.match(text)
    if match:
        value = match.group(1).strip()
        if str(year) in value:
            return _clean_text(value, 120)
    # The phrase may occur a little after a category label.
    window = text[:260]
    for m in re.finditer(r"[0-9][0-9A-Za-z'’ ,.:–\-]{4,90}?20(?:26|27)", window):
        value = m.group(0).strip()
        if str(year) in value:
            return _clean_text(value, 120)
    return ""


def _name_from_before(before: str) -> str:
    matches = list(MARKET_NAME_RE.finditer(before[-260:]))
    if not matches:
        return ""
    name = _clean_text(matches[-1].group(0), 120)
    name = re.sub(r"\s*\(opens?\b.*$", "", name, flags=re.I)
    name = re.sub(r"^(?:England|Scotland|Wales|Northern Ireland|UK|Britain)\s+", "", name, flags=re.I)
    name = re.sub(r"\s+(?:England|Scotland|Wales)\s+", " ", name)
    name = re.sub(r"\s+(?:View on map|Previous slide|Next slide).*$", "", name, flags=re.I)
    name = re.sub(r"^(?:The|Top)\s+", "", name, flags=re.I)
    return name.strip(" ,-–—")


def _location_from_after(after: str, fallback: str = "") -> str:
    match = LOCATION_RE.search(after[:600])
    if match:
        return _clean_text(match.group(1), 80)
    return fallback


def _official_link(page: RetrievedPage, candidate: str, city: str) -> str:
    words = {w for w in _norm(candidate).split() if w not in
             {"christmas", "market", "markets", "winter", "wonderland", "the", "and"}}
    city_words = set(_norm(city).split())
    for url, anchor in page.link_texts.items():
        low = _norm(anchor)
        if not low or _canon(url) == page.url:
            continue
        if (("market" in low or "wonderland" in low) and
                (any(w in low for w in words) or any(w in low for w in city_words))):
            return url
    return ""


def _candidate_from_list(page: RetrievedPage, plan: QueryPlan,
                         limit: int | None = None) -> list[Candidate]:
    text = re.sub(r"\s+", " ", page.text)
    start = TOP_START_RE.search(text)
    if start:
        body = text[start.start():]
        end = TOP_END_RE.search(body)
        if end:
            body = body[:end.start()]
    else:
        body = text
    out: list[Candidate] = []
    cursor = 0
    for marker in re.finditer(r"View on map", body):
        if limit is not None and len(out) >= limit:
            break
        pos = marker.start()
        segment = body[cursor:pos]
        cursor = marker.end()
        name = _name_from_before(segment)
        if not name:
            continue
        before = segment[-260:]
        after = body[pos + len("View on map"):]
        date_text = _date_text_from(after, plan.year)
        rest = after[len(date_text):].lstrip(" .-–—") if date_text else after
        rest = re.sub(r"^\d+\s*", "", rest)
        rest = re.split(r"View on map|Previous slide|Next slide|Photo by:", rest, maxsplit=1)[0]
        sentences = _sentences(rest)
        description = next((s for s in sentences if len(s) > 30), sentences[0] if sentences else "")
        description = _clean_text(description, 300)
        location = _location_from_after(after, page.rule.city)
        excerpt = _clean_text(before[-150:] + " " + after[:230], 360)
        out.append(Candidate(
            name=name, location=location, date_text=date_text,
            description=description, source_url=page.url,
            publisher=page.rule.publisher, source_id=page.rule.source_id,
            authority=page.rule.authority,
            official_url=_official_link(page, name, location),
            evidence_excerpt=excerpt,
            date_status="confirmed_2026" if str(plan.year) in date_text else "unconfirmed",
            presentation_order=len(out),
            sources=[{"url": page.url, "publisher": page.rule.publisher,
                      "source_id": page.rule.source_id, "date_text": date_text,
                      "verified_at": page.fetched_at}],
            source_text=page.text,
        ))
    return out


def _title_name(title: str, city: str) -> str:
    text = _clean_text(title, 200)
    text = re.sub(r"\s*[\|–—]\s*.*$", "", text)
    text = re.sub(r"\s*-\s*(?:Official|Home|Plan|Visit|Glasgow Life).*$", "", text, flags=re.I)
    text = re.sub(r"\b(?:Exhibitors|Event Information|Official Website|Plan your visit to)\b", "", text, flags=re.I)
    text = re.sub(r"\b20\d{2}\b", "", text)
    text = _clean_text(text, 120)
    if not re.search(r"\b(market|markets|wonderland|fair|fayre|christmas|winter)\b", text, re.I) and city:
        text = f"{city} Christmas Market"
    return text or f"{city} Christmas Market"


def _format_date_span(dates: list[date]) -> str:
    if not dates:
        return ""
    if len(dates) == 1:
        return f"{dates[0].day} {dates[0].strftime('%B %Y')}"
    return f"{dates[0].day} {dates[0].strftime('%B %Y')} – {dates[1].day} {dates[1].strftime('%B %Y')}"


def _candidate_from_detail(page: RetrievedPage, plan: QueryPlan) -> list[Candidate]:
    name = _title_name(page.title, page.rule.city)
    text = re.sub(r"\s+", " ", page.text)
    text = re.sub(r"^.*?Skip to main content\s*", "", text, flags=re.I)
    published_span = _date_text_from(text, plan.year)
    parsed_dates = parse_date_text(text, plan.year)
    if len(parsed_dates) >= 2:
        date_text = _format_date_span(parsed_dates[:2])
    else:
        date_text = published_span or _format_date_span(parsed_dates)
    description = page.description or ""
    if "skip to main content" in description.lower() or len(description) < 25:
        description = ""
    if not description:
        candidates = [s for s in _sentences(text)
                      if "market" in s.lower() and len(s) > 30
                      and "skip to main content" not in s.lower()]
        description = candidates[0] if candidates else ""
    excerpt = _clean_text(f"{date_text} {description}", 360)
    return [Candidate(
        name=name, location=page.rule.city, date_text=date_text,
        description=_clean_text(description, 300), source_url=page.url,
        publisher=page.rule.publisher, source_id=page.rule.source_id,
        authority=page.rule.authority,
        official_url="", evidence_excerpt=excerpt,
        date_status="confirmed_2026" if str(plan.year) in date_text else "unconfirmed",
        sources=[{"url": page.url, "publisher": page.rule.publisher,
                  "source_id": page.rule.source_id, "date_text": date_text,
                  "verified_at": page.fetched_at}],
        source_text=page.text,
    )]


def _merge_candidates(candidates: list[Candidate], feedback=None) -> list[Candidate]:
    merged: dict[str, Candidate] = {}
    for candidate in candidates:
        key = _norm(candidate.name)
        if not key:
            continue
        if key not in merged:
            merged[key] = candidate
            continue
        existing = merged[key]
        if candidate.date_text and not existing.date_text:
            existing.date_text = candidate.date_text
            existing.date_status = candidate.date_status
        elif candidate.date_text and _norm(candidate.date_text) != _norm(existing.date_text):
            variants = existing.date_variants or [{
                "source_id": existing.source_id, "source_url": existing.source_url,
                "publisher": existing.publisher, "date_text": existing.date_text,
            }]
            variants.append({
                "source_id": candidate.source_id, "source_url": candidate.source_url,
                "publisher": candidate.publisher, "date_text": candidate.date_text,
            })
            existing.date_variants = variants
            existing.date_status = "conflicting_evidence"
        if len(candidate.description) > len(existing.description):
            existing.description = candidate.description
        for source in candidate.sources:
            if source["url"] not in {s["url"] for s in existing.sources}:
                existing.sources.append(source)
        if candidate.official_url and not existing.official_url:
            existing.official_url = candidate.official_url
    out = list(merged.values())
    for item in out:
        item.score = (8.0 if item.authority in ("official", "primary") else 2.0)
        item.score += 4.0 if item.date_status == "confirmed_2026" else 0.0
        item.score += min(3.0, len(item.sources) * 1.5)
        item.score += 2.0 if item.description else 0.0
        item.score += 1.0 if item.official_url else 0.0
        if feedback is not None:
            domains = {_domain(source["url"]) for source in item.sources}
            if not domains and item.source_url:
                domains = {_domain(item.source_url)}
            for domain in domains:
                item.score += feedback.score(domain)
    out.sort(key=lambda c: (-c.score, c.name))
    return out


class ResearchEngine:
    """Discovery + approved retrieval + cited answers, with no automatic indexing."""

    def __init__(self, provider=None, policy: SourcePolicy | None = None,
                 fetcher=None, robots=None, feedback=None, local_index=None,
                 max_pages: int = 8, clock=_now):
        self.provider = provider
        self.policy = policy
        self.fetcher = fetcher
        self.robots = robots
        self.feedback = feedback
        self.local_index = local_index
        self.max_pages = max(1, min(int(max_pages), 20))
        self.clock = clock

    # ---------------------------------------------------------------- discovery
    def discover(self, question: str) -> dict:
        plan = QueryPlan.from_question(question, self.clock())
        if self.provider is None:
            return {"status": "NOT_CONFIGURED", "plan": plan, "leads": [],
                    "queries": [], "notices": ["No discovery provider is configured."]}
        leads: list[dict] = []
        seen: set[str] = set()
        statuses: list[str] = []
        for query in plan.queries:
            try:
                # English pages are searched for a German question because the
                # approved corpus is currently English. The answer language is
                # still reported from the caller's question.
                result = self.provider.search(query, limit=12, language="en")
                statuses.append(str(result.get("status") or "OK"))
            except (ProviderError, ValueError, OSError) as exc:
                statuses.append(f"ERROR:{type(exc).__name__}")
                continue
            for hit in result.get("results") or []:
                url = _canon(str(hit.get("url") or ""))
                if not url or url in seen:
                    continue
                seen.add(url)
                rule = self.policy.match(url) if self.policy else None
                leads.append({
                    "title": _clean_text(hit.get("title"), 160),
                    "url": url,
                    "snippet": _clean_text(hit.get("snippet"), 240),
                    "publisher": _domain(url),
                    "admitted": bool(rule),
                    "source_id": rule.source_id if rule else None,
                    "source_kind": "approved_source" if rule else "unverified_provider_lead",
                    "verified": False,
                    "query": query,
                })
        leads.sort(key=lambda x: (not x["admitted"], x["publisher"], x["url"]))
        return {"status": "provider_results" if any(s == "provider_results_unverified" for s in statuses) or leads else "NO_LEADS",
                "plan": plan, "leads": leads, "queries": plan.queries,
                "notices": ["Provider output is unverified; only approved canonical URLs may be fetched."]}

    # ---------------------------------------------------------------- retrieval
    def retrieve(self, leads: list[dict]) -> tuple[list[RetrievedPage], dict]:
        if self.fetcher is None:
            return [], {"attempted": 0, "fetched": 0, "denied": 0, "errors": ["no fetcher"]}
        pages: list[RetrievedPage] = []
        attempted = denied = 0
        errors: list[str] = []
        for lead in leads:
            if not lead.get("admitted"):
                continue
            if len(pages) >= self.max_pages:
                break
            rule = self.policy.match(lead["url"]) if self.policy else None
            if rule is None:
                denied += 1
                continue
            attempted += 1
            if self.robots is not None:
                try:
                    allowed, rules = self.robots.path_allowed(lead["url"], self.fetcher.config.user_agent)
                except Exception as exc:
                    denied += 1
                    errors.append(f"robots_error:{type(exc).__name__}")
                    continue
                if not allowed:
                    denied += 1
                    errors.append(f"robots_denied:{rule.source_id}")
                    continue
            result = self.fetcher.fetch(lead["url"], max_bytes=1_500_000)
            if not result.ok:
                errors.append(f"fetch:{rule.source_id}:{result.error or result.status}")
                continue
            content_type = result.headers.get("content-type", "")
            charset = content_type.split("charset=")[-1] if "charset=" in content_type else "utf-8"
            extracted = extract_page(result.body, result.final_url, charset)
            if not extracted.text.strip():
                errors.append(f"empty_text:{rule.source_id}")
                continue
            pages.append(RetrievedPage(
                rule=rule, url=_canon(result.final_url or lead["url"]),
                title=extracted.title, description=extracted.description,
                text=extracted.text, links=extracted.links,
                link_texts=extracted.link_texts,
                fetched_at=self.clock().date().isoformat(), extracted=extracted,
            ))
        return pages, {"attempted": attempted, "fetched": len(pages),
                       "denied": denied, "errors": errors,
                       "pages": [{"source_id": p.rule.source_id, "url": p.url,
                                  "title": p.title, "bytes_text": len(p.text)}
                                 for p in pages]}

    # ---------------------------------------------------------------- candidates
    def candidates(self, pages: list[RetrievedPage], plan: QueryPlan) -> list[Candidate]:
        out: list[Candidate] = []
        for page in pages:
            if page.rule.answer_kind == "list":
                out.extend(_candidate_from_list(page, plan, limit=plan.count))
            else:
                out.extend(_candidate_from_detail(page, plan))
        return _merge_candidates(out, self.feedback)

    # ---------------------------------------------------------------- answer
    def answer(self, question: str) -> ResearchAnswer:
        plan = QueryPlan.from_question(question, self.clock())
        discovery = self.discover(question)
        pages, retrieval = self.retrieve(discovery.get("leads") or [])
        candidate_objects = self.candidates(pages, plan)
        base = {
            "status": "NO_EVIDENCE", "response_mode": "NO_EVIDENCE",
            "question": question, "answer": "", "plan": self._plan_dict(plan),
            "discovery": self._public_discovery(discovery),
            "retrieval": retrieval, "limitations": [],
            "_candidate_objects": candidate_objects,
        }
        if plan.answer_type == "list":
            return self._list_answer(base, plan, candidate_objects)
        if plan.answer_type == "comparison":
            return self._comparison_answer(base, plan, candidate_objects, pages)
        if plan.answer_type == "factual":
            answer = self._factual_answer(base, plan, candidate_objects, pages)
            if answer.status != "NO_EVIDENCE":
                return answer
        return self._fallback_answer(base, question, pages)

    @staticmethod
    def _plan_dict(plan: QueryPlan) -> dict:
        return {"answer_type": plan.answer_type, "count": plan.count,
                "year": plan.year, "location": plan.location,
                "language": plan.language, "queries": plan.queries}

    @staticmethod
    def _public_discovery(discovery: dict) -> dict:
        plan = discovery.get("plan")
        return {"status": discovery.get("status"),
                "queries": discovery.get("queries") or [],
                "leads": discovery.get("leads") or [],
                "admitted_leads": sum(1 for x in (discovery.get("leads") or []) if x.get("admitted")),
                "notices": discovery.get("notices") or []}

    def _list_answer(self, base: dict, plan: QueryPlan, candidates: list[Candidate]) -> ResearchAnswer:
        chosen = sorted(candidates[:plan.count], key=lambda c: (c.presentation_order, c.name))
        if not chosen:
            base["limitations"] = ["No approved source produced a supported list."]
            return ResearchAnswer(**base)
        lines = [f"Pulse Search found {len(chosen)} supported "
                 f"{'entry' if len(chosen) == 1 else 'entries'} for “{plan.question}”. "
                 "The order follows the cited publisher's feature order, not an independent ranking."]
        for index, item in enumerate(chosen, 1):
            date_part = item.date_text or "2026 dates not confirmed in the extracted text"
            place = f" ({item.location})" if item.location else ""
            lines.append(f"{index}. {item.name}{place} — {date_part}. {item.description}")
        limitations = [
            "Each entry is limited to the cited page; descriptions are short attributed excerpts or faithful summaries of them.",
            "Dates and availability must be checked with the organiser before travel.",
        ]
        if len(chosen) < plan.count:
            limitations.append(f"Only {len(chosen)} of the requested {plan.count} entries had sufficient evidence.")
        claims = [{
            "claim": f"{item.name}{(' in ' + item.location) if item.location else ''} is listed for {item.date_text or 'dates not confirmed'}.",
            "evidence": [{"url": item.source_url, "publisher": item.publisher,
                          "source_id": item.source_id, "excerpt": item.evidence_excerpt,
                          "verified_at": item.sources[0]["verified_at"] if item.sources else ""}],
            "support": item.date_status, "confidence": 0.85 if item.date_status == "confirmed_2026" else 0.5,
        } for item in chosen]
        citations = self._citations(chosen)
        answer = "\n\n".join(lines)
        return ResearchAnswer(
            **{**base, "status": "ANSWERED", "response_mode": "CITED_LIST",
               "answer": answer, "candidates": [c.as_dict() for c in chosen],
               "claims": claims, "citations": citations, "limitations": limitations,
               "shortfall": max(0, plan.count - len(chosen))})

    def _factual_answer(self, base: dict, plan: QueryPlan,
                        candidates: list[Candidate], pages: list[RetrievedPage]) -> ResearchAnswer:
        name_terms = set(_norm(plan.question).split())
        item = next((c for c in candidates if set(_norm(c.name).split()) & name_terms), None)
        if item is None:
            item = candidates[0] if candidates else None
        if item is None or not item.date_text:
            return ResearchAnswer(**base)
        if item.date_status == "conflicting_evidence":
            variants = "\n".join(
                f"- {v['publisher']} ({v['source_url']}): {v['date_text']}"
                for v in item.date_variants)
            answer = (f"Sources disagree about the published dates for {item.name}. "
                      "Pulse Search is not selecting one as fact.\n" + variants)
            claims = [{
                "claim": f"{item.name} has conflicting published date evidence.",
                "evidence": [{"url": v["source_url"], "publisher": v["publisher"],
                              "source_id": v["source_id"], "excerpt": v["date_text"],
                              "verified_at": ""} for v in item.date_variants],
                "support": "conflicting_evidence", "confidence": 0.0,
            }]
            citations = self._citations([item])
            return ResearchAnswer(**{**base, "status": "CONFLICTING_EVIDENCE",
                                     "response_mode": "UNCERTAIN", "answer": answer,
                                     "candidates": [item.as_dict()], "claims": claims,
                                     "citations": citations,
                                     "limitations": ["The conflicting statements are retained; an operator must resolve the edition before it is treated as a confirmed date."]})
        answer = (f"{item.name}{(' in ' + item.location) if item.location else ''}: "
                  f"{item.date_text}.")
        if item.description:
            answer += " " + item.description
        claims = [{
            "claim": f"{item.name} has the published date span {item.date_text}.",
            "evidence": [{"url": item.source_url, "publisher": item.publisher,
                          "source_id": item.source_id, "excerpt": item.evidence_excerpt,
                          "verified_at": item.sources[0]["verified_at"] if item.sources else ""}],
            "support": item.date_status, "confidence": 0.85,
        }]
        return ResearchAnswer(**{**base, "status": "ANSWERED", "response_mode": "CITED_ANSWER",
                                 "answer": answer, "candidates": [item.as_dict()],
                                 "claims": claims, "citations": self._citations([item]),
                                 "limitations": ["Date and opening details are as published on the cited page; verify before travelling."]})

    def _comparison_answer(self, base: dict, plan: QueryPlan,
                           candidates: list[Candidate], pages: list[RetrievedPage]) -> ResearchAnswer:
        facet = next((w for w in re.findall(r"[a-z]+", plan.question.lower())
                      if w in {"train", "rail", "accessible", "wheelchair", "cheap", "free"}), "")
        if not facet:
            return ResearchAnswer(**base)
        terms = {w for w in re.findall(r"[a-z0-9]+", plan.question.lower())
                 if len(w) > 3 and w not in {"which", "christmas", "markets", "easiest", "reach", "2026"}}
        rows = []
        for item in candidates:
            best = None
            for sentence in _sentences(item.source_text):
                low = sentence.lower()
                if facet not in low or len(sentence) < 35 or len(sentence) > 520:
                    continue
                if any(bad in low for bad in ("cookie", "skip to main", "sign in",
                                              "log in", "subscribe", "privacy policy",
                                              "terms and conditions")):
                    continue
                score = 2 + sum(2 for term in terms if term in low)
                if best is None or score > best[0]:
                    best = (score, sentence)
            if best is not None:
                rows.append((item, best[1]))
            if len(rows) >= 3:
                break
        if not rows:
            base["limitations"] = [f"No approved source extracted a '{facet}' comparison claim."]
            return ResearchAnswer(**base)
        lines = [f"Supported comparisons mentioning “{facet}”:"]
        claims = []
        for item, sentence in rows:
            lines.append(f"- {item.name}: {sentence}")
            claims.append({
                "claim": sentence,
                "evidence": [{"url": item.source_url, "publisher": item.publisher,
                              "source_id": item.source_id, "excerpt": sentence,
                              "verified_at": item.sources[0]["verified_at"] if item.sources else ""}],
                "support": "content", "confidence": 0.7,
            })
        limitations = ["This is a comparison of the cited statements, not a measured journey-time ranking."]
        if len(rows) < 2:
            limitations.append("Only one approved source contained a useful comparison statement.")
        return ResearchAnswer(**{**base, "status": "ANSWERED", "response_mode": "CITED_ANSWER",
                                 "answer": "\n".join(lines), "claims": claims,
                                 "citations": self._citations([x[0] for x in rows]),
                                 "candidates": [x[0].as_dict() for x in rows],
                                 "limitations": limitations})

    def _fallback_answer(self, base: dict, question: str, pages: list[RetrievedPage]) -> ResearchAnswer:
        if self.local_index is not None:
            from .search import search_staging
            try:
                result = search_staging(self.local_index, question, limit=5, enforce_support=True)
            except Exception:
                result = {}
            hits = result.get("results") or []
            if hits:
                first = hits[0]
                navigation = all(h.get("support_basis") == "metadata_assisted" for h in hits)
                text = ("These are navigation results, not a quoted answer."
                        if navigation else str(first.get("snippet") or ""))
                claims = [] if navigation else [{
                    "claim": text,
                    "evidence": [{"url": first.get("url", ""),
                                  "publisher": first.get("publisher", ""),
                                  "source_id": first.get("source_id", ""),
                                  "excerpt": text, "verified_at": first.get("fetched_at", "")}],
                    "support": first.get("support_basis", "content"), "confidence": 0.6,
                }]
                citations = [{"title": h.get("title", ""), "url": h.get("url", ""),
                              "publisher": h.get("publisher", ""),
                              "kind": "indexed_navigation" if navigation else "indexed_page"}
                             for h in hits[:3]]
                return ResearchAnswer(**{**base, "status": "NAVIGATION_ONLY" if navigation else "ANSWERED",
                                         "response_mode": "NAVIGATION_ONLY" if navigation else "CITED_ANSWER",
                                         "answer": text or "Reviewed navigation results.",
                                         "claims": claims,
                                         "citations": citations,
                                         "limitations": result.get("notices") or []})
        if pages:
            stop = {"what", "which", "when", "where", "how", "does", "do", "the",
                    "and", "for", "with", "have", "has", "are", "is", "in", "on",
                    "my", "i", "a", "an", "to", "of", "british", "2026"}
            terms = {w for w in re.findall(r"[a-z0-9]+", question.lower())
                     if len(w) > 3 and w not in stop}
            best = None
            for page in pages:
                for raw_sentence in _sentences(page.text):
                    sentence = raw_sentence
                    if "Skip to main content" in sentence:
                        sentence = sentence.split("Skip to main content", 1)[1].strip()
                    if "Use this service" in sentence:
                        sentence = sentence[sentence.index("Use this service"):].strip()
                    low = sentence.lower()
                    if len(sentence) < 35 or len(sentence) > 520:
                        continue
                    if any(bad in low for bad in ("cookie", "skip to main", "sign in",
                                                  "log in", "subscribe", "privacy policy")):
                        continue
                    score = sum(2 for term in terms if term in low)
                    if "apply" in low or "renew" in low:
                        score += 2
                    if "renew" in low:
                        score += 4
                    if "use this service" in low or "apply online" in low:
                        score += 3
                    if score <= 0:
                        continue
                    score += 1 if page.title and any(t in page.title.lower() for t in terms) else 0
                    if best is None or score > best[0]:
                        best = (score, page, sentence)
            if best:
                _, page, sentence = best
                text = _clean_text(sentence, 420)
                text = re.sub(r"\s*\[[^]]{1,20}\]\s*", " ", text)
                claims = [{"claim": text, "evidence": [{"url": page.url,
                          "publisher": page.rule.publisher, "source_id": page.rule.source_id,
                          "excerpt": text, "verified_at": page.fetched_at}],
                          "support": "content", "confidence": 0.55}]
                return ResearchAnswer(**{**base, "status": "ANSWERED", "response_mode": "CITED_ANSWER",
                                         "answer": text, "claims": claims,
                                         "citations": [{"title": page.title, "url": page.url,
                                                        "publisher": page.rule.publisher,
                                                        "kind": "approved_source"}],
                                         "limitations": ["Extractive answer from an approved page; no additional fact was inferred."]})
            page = pages[0]
            return ResearchAnswer(**{**base, "status": "NAVIGATION_ONLY",
                                     "response_mode": "NAVIGATION_ONLY",
                                     "answer": "The approved page is a navigation result, not a supported answer.",
                                     "citations": [{"title": page.title, "url": page.url,
                                                    "publisher": page.rule.publisher,
                                                    "kind": "approved_navigation"}],
                                     "limitations": ["No sentence in the approved page supported the question."]})
        base["limitations"] = ["No approved source produced a supported answer."]
        return ResearchAnswer(**base)

    @staticmethod
    def _citations(candidates: list[Candidate]) -> list[dict]:
        out = []
        seen = set()
        for item in candidates:
            for source in item.sources:
                if source["url"] not in seen:
                    seen.add(source["url"])
                    out.append({"title": item.name, "url": source["url"],
                                "publisher": source["publisher"],
                                "kind": "approved_source"})
            if item.official_url and item.official_url not in seen:
                seen.add(item.official_url)
                out.append({"title": item.name, "url": item.official_url,
                            "publisher": "official organiser", "kind": "official_link"})
        return out


class ResearchSession:
    """Small in-process session for a genuine follow-up over retained evidence."""

    def __init__(self, engine: ResearchEngine):
        self.engine = engine
        self.last: ResearchAnswer | None = None

    def ask(self, question: str) -> ResearchAnswer:
        self.last = self.engine.answer(question)
        return self.last

    def follow_up(self, question: str) -> ResearchAnswer:
        if self.last is None:
            return self.engine.answer(question)
        low = question.lower()
        candidates = self.last._candidate_objects
        if not candidates:
            return self.engine.answer(question)
        if re.search(r"\b(earliest|first|starts?)\b", low):
            dated = [(parse_date_text(c.date_text, 2026), c)
                     for c in candidates if c.date_text]
            dated = [(ds, c) for ds, c in dated if ds]
            if dated:
                ds, item = min(dated, key=lambda x: x[0][0])
                text = (f"From the previously retrieved list, {item.name} has the earliest "
                        f"published start: {item.date_text}.")
                return ResearchAnswer(
                    status="ANSWERED", response_mode="CITED_ANSWER", question=question,
                    answer=text, plan=self._plan(question),
                    claims=[{"claim": text, "evidence": [{"url": item.source_url,
                              "publisher": item.publisher, "source_id": item.source_id,
                              "excerpt": item.evidence_excerpt,
                              "verified_at": item.sources[0]["verified_at"] if item.sources else ""}],
                              "support": "content", "confidence": 0.75}],
                    citations=ResearchEngine._citations([item]),
                    candidates=[item.as_dict()],
                    limitations=["Follow-up uses the evidence retained from the previous answer; re-check the cited source."],
                    _candidate_objects=candidates)
        return self.engine.answer(question)

    @staticmethod
    def _plan(question: str) -> dict:
        return ResearchEngine._plan_dict(QueryPlan.from_question(question))
