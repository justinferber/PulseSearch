"""Safe answer layer for the Pulse UNITY knowledge engine.

Design rule: **no answer without evidence**. Every answer is assembled from
either a structured, owner-curated fact (with a source URL and verification
date) or a page already accepted into the staging index. Page text is treated
as quoted evidence, never as instructions. Answers that need live data the
build does not have (weather without a provider, live fares) say so instead of
guessing.

The public contract is :meth:`AnswerService.answer` -> :class:`Answer`, which
serialises to JSON for the Pulse UNITY server.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ANSWERED = "ANSWERED"
NO_EVIDENCE = "NO_EVIDENCE"
LIVE_SOURCE_REQUIRED = "LIVE_SOURCE_REQUIRED"
NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
REFUSED = "REFUSED"

INJECTION_RE = re.compile(
    r"(ignore\s+(all\s+)?(previous|prior)\s+instructions?"
    r"|disregard\s+(the\s+)?(above|previous)"
    r"|system\s*:|assistant\s*:|you\s+must\s+(say|answer|respond))",
    re.I,
)
SENSITIVE_RE = re.compile(
    r"\b(diagnose|medical advice|legal advice|should i invest|credit card number|"
    r"my password|suicide|self[- ]harm)\b",
    re.I,
)
WEATHER_WORDS = re.compile(
    r"\b(weather|forecast|temperature|raining|rain|sunny|cloudy|windy|how (hot|cold)|"
    r"degrees)\b", re.I)
BUY_WORDS = re.compile(r"\b(buy|book|get|find|cheap|cheapest|compare|purchase)\b", re.I)
EVENT_WHEN_WORDS = re.compile(
    r"\b(when|what date|what dates|dates?|start|starts|begin|begins|how long|what day)\b", re.I)
PLACE_WORDS = re.compile(r"\b(where|venue|location|located|address)\b", re.I)
TICKET_WORDS = re.compile(r"\b(tickets?|ticketing|resale|sold out)\b", re.I)

MAX_QUESTION_CHARS = 400
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "did", "do",
    "does", "for", "from", "has", "have", "how", "i", "in", "is", "it", "me", "my",
    "of", "on", "or", "please", "tell", "that", "the", "their", "there", "this", "to",
    "was", "we", "what", "when", "where", "which", "who", "why", "will", "with", "you",
    "your", "today", "now",
}


class WeatherError(RuntimeError):
    """The live weather provider could not be used safely."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _fmt_date(value: date) -> str:
    return f"{value.strftime('%A')} {value.day} {value.strftime('%B %Y')}"


def _host(url: str) -> str:
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ""
    return parts.hostname.lower()


class _HostPolicy:
    def __init__(self, trusted_hosts: list[str]):
        self.trusted = [h.lower().strip(".") for h in trusted_hosts if h]

    def allows(self, url: str) -> bool:
        host = _host(url)
        if not host:
            return False
        return any(host == t or host.endswith("." + t) for t in self.trusted)


def clean_question(text: str) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_QUESTION_CHARS]


def neutralise_snippet(text: str, limit: int) -> str:
    """Quote-index text without letting it read as an instruction."""
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if INJECTION_RE.search(text):
        text = INJECTION_RE.sub("[instruction-like text removed]", text)
    return text[:limit].strip()


def load_pack(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    policy = data.get("policy") or {}
    trusted = policy.get("trusted_hosts") or []
    if not trusted:
        raise ValueError("knowledge pack policy.trusted_hosts must not be empty")
    if not 1 <= int(policy.get("max_snippet_chars", 320)) <= 500:
        raise ValueError("max_snippet_chars must be within 1..500")
    if int(policy.get("weather_ttl_minutes", 30)) <= 0:
        raise ValueError("weather_ttl_minutes must be positive")
    if not data.get("events") and not data.get("buying") and not data.get("weather_locations"):
        raise ValueError("knowledge pack has no usable facts")
    return data


@dataclass
class Citation:
    title: str
    url: str
    publisher: str = ""
    retrieved_at: str = ""
    kind: str = "source"

    def as_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "publisher": self.publisher,
                "retrieved_at": self.retrieved_at, "kind": self.kind}


@dataclass
class Answer:
    status: str
    intent: str
    question: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    confidence: float = 0.0
    freshness: str = ""
    limits: list[str] = field(default_factory=list)
    followups: list[str] = field(default_factory=list)
    gates: dict = field(default_factory=dict)
    pack_version: str = ""

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "intent": self.intent,
            "question": self.question,
            "answer": self.answer,
            "citations": [c.as_dict() for c in self.citations],
            "confidence": round(self.confidence, 2),
            "freshness": self.freshness,
            "limits": self.limits,
            "followups": self.followups,
            "gates": self.gates,
            "pack_version": self.pack_version,
        }


class OpenMeteoProvider:
    """Keyless live weather adapter.

    Only used when a caller explicitly enables live weather. It contacts one
    host (api.open-meteo.com) for current conditions; no member data is sent.
    """

    name = "Open-Meteo"
    attribution = "Open-Meteo (CC BY 4.0)"
    homepage = "https://open-meteo.com/"

    def __init__(self, timeout_s: float = 8.0, base: str = "https://api.open-meteo.com/v1/forecast"):
        self.timeout_s = timeout_s
        self.base = base

    def current(self, places: list[dict]) -> dict:
        lat = ",".join(f"{float(p['latitude']):.4f}" for p in places)
        lon = ",".join(f"{float(p['longitude']):.4f}" for p in places)
        query = urllib.parse.urlencode({
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
            "timezone": "UTC",
        })
        request = urllib.request.Request(
            f"{self.base}?{query}",
            headers={"User-Agent": "PulseUnityKnowledge/0.1 (+https://pulseunity.co)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                payload = json.loads(response.read(64_000).decode("utf-8"))
        except (OSError, ValueError) as exc:  # network, HTTP or JSON failure
            raise WeatherError(type(exc).__name__) from exc
        blocks = payload if isinstance(payload, list) else [payload]
        if len(blocks) != len(places):
            raise WeatherError("provider returned a different number of locations")
        locations = []
        observed = None
        for place, block in zip(places, blocks):
            current = block.get("current") or {}
            observed = observed or current.get("time")
            locations.append({
                "name": place["name"],
                "temperature_c": current.get("temperature_2m"),
                "apparent_c": current.get("apparent_temperature"),
                "precipitation_mm": current.get("precipitation"),
                "wind_kmh": current.get("wind_speed_10m"),
                "condition": weather_code_text(current.get("weather_code")),
            })
        return {"observed_at": observed, "locations": locations,
                "attribution": self.attribution, "provider": self.name}


WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 56: "freezing drizzle", 57: "heavy freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain",
    67: "heavy freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
    77: "snow grains", 80: "light showers", 81: "showers", 82: "violent showers",
    85: "light snow showers", 86: "snow showers", 95: "thunderstorm",
    96: "thunderstorm with hail", 99: "severe thunderstorm with hail",
}


def weather_code_text(code) -> str:
    try:
        return WMO.get(int(code), f"weather code {code}")
    except (TypeError, ValueError):
        return "condition unavailable"


class AnswerService:
    def __init__(self, staging=None, pack: dict | None = None, weather=None, clock=utc_now):
        self.staging = staging
        self.pack = pack or {}
        policy = self.pack.get("policy") or {}
        self.hosts = _HostPolicy(policy.get("trusted_hosts") or [])
        self.snippet_chars = int(policy.get("max_snippet_chars", 320))
        self.weather_ttl = timedelta(minutes=int(policy.get("weather_ttl_minutes", 30)))
        self.event_recheck_days = int(policy.get("event_recheck_days", 180))
        self.weather = weather
        self.clock = clock

    # ------------------------------------------------------------------ public
    def answer(self, question: str, now: datetime | None = None) -> Answer:
        q = clean_question(question)
        now = (now or self.clock()).astimezone(timezone.utc)
        base = {"trusted_hosts_only": True, "live_fares": False, "generated_text": False,
                "untrusted_hits_blocked": 0}
        if not q:
            return self._simple(NEEDS_CLARIFICATION, "unknown", q,
                                "Ask a question about an event, the weather, or where to buy tickets.",
                                gates=base)
        if SENSITIVE_RE.search(q):
            return self._simple(
                REFUSED, "sensitive", q,
                "I can't help with medical, legal, financial or account-security advice. "
                "Please use a qualified professional or the official service.",
                gates=base, limits=["No personal data is processed by this answer layer."])
        event = self._match_event(q)
        locations = self._match_locations(q)
        if WEATHER_WORDS.search(q):
            return self._weather(q, locations, now, base)
        if re.search(r"\bflights?\b|\bairfare|\bairline", q, re.I) and BUY_WORDS.search(q):
            return self._flights(q, base)
        if event and TICKET_WORDS.search(q):
            return self._tickets(q, event, now, base)
        if event and (EVENT_WHEN_WORDS.search(q) or not q.endswith("?")):
            return self._event_when(q, event, now, base)
        if event and PLACE_WORDS.search(q):
            return self._event_place(q, event, base)
        if event:
            return self._event_when(q, event, now, base)
        return self._index_answer(q, now, base)

    # ------------------------------------------------------------------ helpers
    def _simple(self, status, intent, question, text, **kwargs) -> Answer:
        return Answer(status=status, intent=intent, question=question, answer=text,
                      pack_version=str(self.pack.get("version", "")), **kwargs)

    def _match_event(self, q: str) -> dict | None:
        low = q.lower()
        best = None
        for event in self.pack.get("events") or []:
            names = [event.get("name", "")] + list(event.get("aliases") or [])
            for name in names:
                if name and re.search(rf"\b{re.escape(name.lower())}\b", low):
                    if best is None or len(name) > len(best[1]):
                        best = (event, name)
        return best[0] if best else None

    def _match_locations(self, q: str) -> list[dict]:
        low = q.lower()
        found = []
        for place in self.pack.get("weather_locations") or []:
            names = [place.get("name", "")] + list(place.get("aliases") or [])
            if any(n and re.search(rf"\b{re.escape(n.lower())}\b", low) for n in names):
                found.append(place)
        return found

    def _cite(self, citation: dict, kind: str = "source") -> Citation | None:
        url = citation.get("url", "")
        if not self.hosts.allows(url):
            return None
        return Citation(title=citation.get("title") or citation.get("name", ""), url=url,
                        publisher=citation.get("publisher", ""),
                        retrieved_at=citation.get("retrieved_at", ""), kind=kind)

    def _target_year(self, q: str, now: datetime) -> int | None:
        low = q.lower()
        if "next year" in low:
            return now.year + 1
        if "this year" in low:
            return now.year
        match = re.search(r"\b(20\d{2})\b", low)
        return int(match.group(1)) if match else None

    # ------------------------------------------------------------------ weather
    def _weather(self, q, locations, now, gates) -> Answer:
        supported = ", ".join(p["name"] for p in self.pack.get("weather_locations") or [])
        if not locations:
            return self._simple(
                NEEDS_CLARIFICATION, "weather", q,
                f"Which place do you mean? I can answer current conditions for: {supported}.",
                gates=gates, followups=["What is the weather in London today?"])
        if self.weather is None:
            return self._simple(
                LIVE_SOURCE_REQUIRED, "weather", q,
                "I can't answer live weather without a provider connection, and I won't guess. "
                "This build has the weather connector switched off. Enable it with "
                "--live-weather (keyless Open-Meteo adapter) or connect your own provider.",
                gates=gates, limits=["Live weather is an external data dependency, not an indexed fact."])
        try:
            snapshot = self.weather.current(locations)
        except WeatherError as exc:
            return self._simple(
                LIVE_SOURCE_REQUIRED, "weather", q,
                "The weather provider could not be reached or returned an unusable response, "
                "so there is no current observation to report. Try again shortly.",
                gates=gates, limits=[f"Provider error: {exc}."])
        observed = _parse_iso(snapshot.get("observed_at", ""))
        if observed is None:
            return self._simple(
                LIVE_SOURCE_REQUIRED, "weather", q,
                "The weather provider returned no usable observation time, so I won't present "
                "its values as current.", gates=gates)
        age = now - observed
        if age > self.weather_ttl:
            return self._simple(
                LIVE_SOURCE_REQUIRED, "weather", q,
                f"The latest observation is {int(age.total_seconds() // 60)} minutes old, beyond "
                f"the {int(self.weather_ttl.total_seconds() // 60)}-minute freshness limit. "
                "I won't present it as current weather.", gates=gates)
        lines = []
        for place in snapshot.get("locations") or []:
            temp = place.get("temperature_c")
            feels = place.get("apparent_c")
            wind = place.get("wind_kmh")
            rain = place.get("precipitation_mm")
            text = f"{place.get('name')}: {temp} °C"
            if feels is not None and feels != temp:
                text += f" (feels like {feels} °C)"
            text += f", {place.get('condition')}"
            if wind is not None:
                text += f", wind {wind} km/h"
            if rain:
                text += f", {rain} mm precipitation"
            lines.append(text + ".")
        attribution = snapshot.get("attribution") or getattr(self.weather, "attribution", "provider")
        body = (f"As of {observed.strftime('%H:%M UTC on %d %b %Y')}: "
                + " ".join(lines) + f" Source: {attribution}.")
        return self._simple(
            ANSWERED, "weather", q, body,
            citations=[Citation(title=attribution, url=getattr(
                self.weather, "homepage", "https://open-meteo.com/"),
                publisher=str(attribution), retrieved_at=_iso(observed), kind="live_weather")],
            confidence=0.9, freshness=_iso(observed), gates=gates,
            limits=["Current observation, not a forecast.", "Live data is not stored in the index."],
            followups=["What is the weather in Berlin today?"])

    # ------------------------------------------------------------------ events
    def _event_when(self, q, event, now, gates) -> Answer:
        try:
            start = date.fromisoformat(event["start"])
            end = date.fromisoformat(event["end"])
        except (KeyError, ValueError):
            return self._simple(NO_EVIDENCE, "event_date", q,
                                "The knowledge pack entry for this event has no valid date.",
                                gates=gates)
        target = self._target_year(q, now)
        if target and start.year != target:
            return self._simple(
                NO_EVIDENCE, "event_date", q,
                f"The pack has {event['name']} in {start.year}, not {target}. I won't move an "
                "announced date to fit the question.", gates=gates,
                limits=["Ask the organiser or check the official page for other editions."])
        citation = self._cite(event.get("source") or {})
        if citation is None:
            return self._simple(NO_EVIDENCE, "event_date", q,
                                "This event's source is not on the trusted-source list.",
                                gates=gates)
        days = (end - start).days + 1
        body = (f"{event['name']} is scheduled for {_fmt_date(start)} to {_fmt_date(end)} "
                f"({days} days)")
        if event.get("venue"):
            body += f" at {event['venue']}"
        body += "."
        if event.get("date_note"):
            body += " " + event["date_note"]
        limits = []
        verified = _parse_iso(event.get("verified_at", ""))
        if verified and (now - verified).days > self.event_recheck_days:
            limits.append("This fact is older than the recheck window; confirm on the official page.")
        if end < now.date() - timedelta(days=1):
            limits.append("This edition has finished; the next edition is not in the pack yet.")
        return Answer(
            status=ANSWERED, intent="event_date", question=q, answer=body,
            citations=[citation], confidence=0.95 if not limits else 0.8,
            freshness=_iso(verified) if verified else "unverified",
            limits=limits, gates=gates, pack_version=str(self.pack.get("version", "")),
            followups=[f"Where is {event['name']}?", f"Are tickets for {event['name']} available?"])

    def _event_place(self, q, event, gates) -> Answer:
        citation = self._cite(event.get("source") or {})
        if citation is None or not event.get("venue"):
            return self._simple(NO_EVIDENCE, "event_place", q,
                                "No venue with a trusted source is recorded for this event.",
                                gates=gates)
        body = f"{event['name']} is held at {event['venue']}."
        if event.get("venue_note"):
            body += " " + event["venue_note"]
        return Answer(status=ANSWERED, intent="event_place", question=q, answer=body,
                      citations=[citation], confidence=0.9, gates=gates,
                      pack_version=str(self.pack.get("version", "")))

    def _tickets(self, q, event, now, gates) -> Answer:
        citation = self._cite(event.get("source") or {})
        if citation is None or not event.get("ticket_note"):
            return self._simple(NO_EVIDENCE, "event_tickets", q,
                                "No ticket status with a trusted source is recorded for this event.",
                                gates=gates)
        body = (f"{event['name']}: {event['ticket_note']} Only use the organiser's official "
                "channel; Pulse Unity does not sell tickets or add a markup.")
        citations = [citation]
        official = self._cite(event.get("ticket_source") or {})
        if official:
            citations.append(official)
        return Answer(status=ANSWERED, intent="event_tickets", question=q, answer=body,
                      citations=citations, confidence=0.9, gates=gates,
                      limits=["Ticket availability changes quickly; the official page is authoritative."],
                      pack_version=str(self.pack.get("version", "")))

    # ------------------------------------------------------------------ buying
    def _flights(self, q, gates) -> Answer:
        guidance = (self.pack.get("buying") or {}).get("flights") or {}
        channels = guidance.get("channels") or []
        citations = [c for c in (self._cite(ch, "official_channel") for ch in channels) if c]
        if not citations:
            return self._simple(NO_EVIDENCE, "buy_flights", q,
                                "No trusted booking channels are configured.", gates=gates)
        lines = [guidance.get("intro") or
                 "Buy directly from the airline or a licensed agent, not from an unofficial reseller."]
        lines += [f"- {ch['name']}: {ch['url']}" for ch in channels]
        if guidance.get("note"):
            lines.append(guidance["note"])
        lines.append("I can't quote or rank live fares, and I won't invent prices.")
        return Answer(status=ANSWERED, intent="buy_flights", question=q,
                      answer="\n".join(lines), citations=citations, confidence=0.85,
                      gates=gates, pack_version=str(self.pack.get("version", "")),
                      limits=["No live fares or availability.", "No affiliate or referral links."])

    # ------------------------------------------------------------------ index
    def _index_answer(self, q, now, gates) -> Answer:
        if self.staging is None:
            return self._simple(NO_EVIDENCE, "index_lookup", q,
                                "There is no searchable index connected to this answer service.",
                                gates=gates)
        rows = []
        mode = "fts"
        try:
            from .search import search_staging

            response = search_staging(self.staging, q, limit=8)
            rows = response.get("results") or []
            mode = str(response.get("retrieval_mode") or response.get("status") or "ranked")
        except Exception:
            # The answer must still work if the broad-ranking adapter is
            # unavailable; fall back to the index's own FTS query.
            rows = self.staging.search(index_query(q), limit=8)
            mode = "fts_fallback"
        gates = dict(gates, retrieval_mode=mode)
        trusted = []
        blocked = 0
        for row in rows:
            if self.hosts.allows(row.get("url", "")) and not row.get("revoked"):
                trusted.append(row)
            else:
                blocked += 1
        gates = dict(gates, untrusted_hits_blocked=blocked, retrieval_mode=mode)
        if not trusted:
            reason = ("I found pages, but none are on the trusted-source list, so I won't cite them."
                      if blocked else "The index has no accepted page that answers this.")
            return self._simple(NO_EVIDENCE, "index_lookup", q,
                                reason + " Try a more specific question, or add a curated fact "
                                "with a source to the knowledge pack.", gates=gates)
        top = trusted[0]
        snippet = neutralise_snippet(top.get("snippet", ""), self.snippet_chars)
        if not snippet:
            return self._simple(NO_EVIDENCE, "index_lookup", q,
                                "The matching page has no quotable snippet.", gates=gates)
        body = f"From the indexed page “{top['title']}”: {snippet}"
        citation = Citation(title=top["title"], url=top["url"],
                            publisher=url_host(top["url"]), retrieved_at=top.get("fetched_at", ""),
                            kind="indexed_page")
        return Answer(status=ANSWERED, intent="index_lookup", question=q, answer=body,
                      citations=[citation], confidence=0.6, freshness=top.get("fetched_at", ""),
                      gates=gates, pack_version=str(self.pack.get("version", "")),
                      limits=["Quoted from an indexed page; not independently verified.",
                              "Only the accepted title and short snippet are stored."])


def index_query(question: str) -> str:
    """Keyword form for the index: FTS treats terms as AND, so drop filler."""
    terms = [t for t in re.findall(r"[A-Za-z0-9]+", question.lower())
             if t not in STOPWORDS and len(t) > 1]
    return " ".join(terms[:8]) or question


def url_host(url: str) -> str:
    return _host(url)


def render_answer_for_web(answer: Answer, escape) -> str:
    """Small HTML block used by the local console; ``escape`` is html.escape."""
    pill = {"ANSWERED": "good", "LIVE_SOURCE_REQUIRED": "warn",
            "NO_EVIDENCE": "warn", "REFUSED": "bad",
            "NEEDS_CLARIFICATION": "warn"}.get(answer.status, "warn")
    citations = "".join(
        f"<li><a href='{escape(c.url)}' rel='noopener noreferrer'>{escape(c.title)}</a>"
        f" <span class='sub'>{escape(c.publisher or url_host(c.url))}</span></li>"
        for c in answer.citations
    )
    limits = "".join(f"<li>{escape(item)}</li>" for item in answer.limits)
    body = escape(answer.answer).replace("\n", "<br>")
    return (
        f"<div class='answer'><div><span class='pill {pill}'>{escape(answer.status)}</span> "
        f"<b>{escape(answer.intent)}</b> · confidence {answer.confidence:.2f} · "
        f"freshness {escape(answer.freshness or 'n/a')}</div>"
        f"<p>{body}</p>"
        + (f"<div class='sub'>Sources</div><ul class='tight'>{citations}</ul>" if citations else "")
        + (f"<div class='sub'>Limits</div><ul class='tight'>{limits}</ul>" if limits else "")
        + "</div>"
    )
