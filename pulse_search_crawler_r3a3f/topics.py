"""Discovery intents for outdoor festivals, celebrations and seasonal events.

A general crawler that only follows whatever a homepage happens to link will
miss most Christmas markets, Pride programmes, carnivals and open-air music
festivals: those live on listing pages reached by anchor text and seasonal
paths, often in the local language (Weihnachtsmarkt, Umzug, CSD, Straßenfest).

An intent is a *discovery hint*, never a filter. It raises the priority of a
link or a listing hub and labels what was found; it never blocks a topic and
never changes what may be crawled. Pride, Diwali, CSD and Stadtfest remain
ordinary, fully discoverable content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Paths that commonly hold listings inside an already-approved origin. Probes
# are only enqueued when the path falls inside the source's approved paths and
# still pass robots, depth and rights checks.
# Four high-yield shapes only: every probe is a real request, so a long list
# buys little and costs budget on 404s. A 404 is recorded once and never retried.
PROBE_PATHS: tuple[str, ...] = (
    "/events",
    "/whats-on",
    "/calendar",
    "/veranstaltungen",
)

HUB_TERMS = (
    "what's on",
    "whats on",
    "whats-on",
    "calendar",
    "listings",
    "events guide",
    "programme",
    "program",
    "schedule",
    "veranstaltungen",
    "alle termine",
)


@dataclass(frozen=True)
class Intent:
    slug: str
    label: str
    categories: tuple[str, ...]
    keywords: tuple[str, ...]
    months: tuple[int, ...] = ()
    weight: float = 1.0
    seasonal: float = 0.6

    def as_dict(self) -> dict:
        return {
            "slug": self.slug,
            "label": self.label,
            "categories": list(self.categories),
            "months": list(self.months),
            "weight": self.weight,
        }


INTENTS: tuple[Intent, ...] = (
    Intent(
        "christmas_markets",
        "Christmas and Advent markets",
        ("Market", "Festival"),
        ("christmas market", "xmas market", "weihnachtsmarkt", "christkindlmarkt",
         "adventsmarkt", "advent market", "winter market", "festive market",
         "holiday market", "weihnachtsdorf", "glühwein"),
        months=(11, 12),
        weight=1.2,
    ),
    Intent(
        "pride",
        "Pride and CSD programmes",
        ("Pride & Community", "Festival", "Parades & Processions"),
        ("pride", "csd", "christopher street day", "pride parade", "queer festival",
         "lgbtq", "lgbt", "diversity festival"),
        months=(6, 7),
        weight=1.2,
    ),
    Intent(
        "music_festivals",
        "Open-air and live music festivals",
        ("Music & Performance", "Festival"),
        ("music festival", "open air", "openair", "live music", "lineup", "line-up",
         "concert series", "festival stage", "gig", "live act", "konzert",
         "sommerkonzert"),
        months=(5, 6, 7, 8),
        weight=1.1,
    ),
    Intent(
        "parades",
        "Parades, processions and carnivals",
        ("Parades & Processions", "Festival"),
        ("parade", "procession", "umzug", "karneval", "carnival", "street parade",
         "lantern parade", "fasching", "cortege"),
        months=(2, 11),
        weight=1.1,
    ),
    Intent(
        "outdoor_festivals",
        "Street, summer and open-air festivals",
        ("Festival", "Arts & Culture"),
        ("street festival", "strassenfest", "straßenfest", "stadtfest", "sommerfest",
         "summer festival", "open air festival", "food festival", "culture festival",
         "volksfest", "kirmes", "street party"),
        months=(5, 6, 7, 8, 9),
        weight=1.1,
    ),
    Intent(
        "diwali",
        "Diwali and light festivals",
        ("Festival",),
        ("diwali", "deepavali", "festival of lights", "lamp festival"),
        months=(10, 11),
        weight=1.1,
    ),
    Intent(
        "new_year",
        "New Year and winter celebrations",
        ("Festival", "Music & Performance"),
        ("new year", "silvester", "new year's eve", "fireworks", "winter festival"),
        months=(12, 1),
        weight=1.0,
    ),
)

INTENT_BY_SLUG = {intent.slug: intent for intent in INTENTS}

# Categories that the discovery focus is asked to surface first. Ordering only:
# nothing is excluded and no category is suppressed.
FOCUS_CATEGORIES: tuple[str, ...] = (
    "Festival",
    "Music & Performance",
    "Parades & Processions",
    "Pride & Community",
    "Market",
    "Arts & Culture",
)


def _count(text: str, keyword: str) -> int:
    if " " in keyword or "-" in keyword:
        return text.count(keyword)
    return len(re.findall(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", text))


def intent_scores(text: str, url: str = "") -> dict[str, float]:
    haystack = " ".join(f"{text} {url}".lower().split())
    scores: dict[str, float] = {}
    for intent in INTENTS:
        hits = sum(_count(haystack, keyword) for keyword in intent.keywords)
        if hits:
            scores[intent.slug] = round(hits * intent.weight, 3)
    return scores


def best_intent(text: str, url: str = "") -> tuple[str | None, float]:
    scores = intent_scores(text, url)
    if not scores:
        return None, 0.0
    slug = max(scores, key=lambda key: scores[key])
    return slug, scores[slug]


def seasonal_multiplier(intent: Intent, month: int | None) -> float:
    if not intent.months or month is None:
        return 1.0 if not intent.months else 0.8
    return 1.0 if month in intent.months else intent.seasonal


def intent_boost(scores: dict[str, float], month: int | None) -> float:
    """0..~2 priority lift, strongest for the current season."""
    total = 0.0
    for slug, score in scores.items():
        intent = INTENT_BY_SLUG[slug]
        total += min(2.0, 0.35 * score) * seasonal_multiplier(intent, month)
    return round(min(2.0, total), 3)


def hub_score(title: str, text: str, link_count: int, url: str = "") -> float:
    haystack = f"{title} {url} {text[:4000]}".lower()
    hits = sum(1 for term in HUB_TERMS if term in haystack)
    score = min(1.0, hits * 0.35)
    score += min(0.6, link_count / 40.0)
    return round(min(1.5, score), 3)


def is_event_listing(title: str, text: str, link_count: int, url: str = "") -> bool:
    return hub_score(title, text, link_count, url) >= 0.5


def focus_report(month: int | None, document_intents: dict[str, int]) -> dict:
    """Machine-readable discovery summary for the run report."""
    seasonal = []
    for intent in INTENTS:
        multiplier = seasonal_multiplier(intent, month)
        if multiplier >= 1.0 and intent.months and month in intent.months:
            seasonal.append(intent.slug)
    return {
        "focus_categories": list(FOCUS_CATEGORIES),
        "intents": [
            {**intent.as_dict(), "documents": document_intents.get(intent.slug, 0),
             "in_season": bool(intent.months and month in intent.months)}
            for intent in INTENTS
        ],
        "seasonal_month": month,
        "in_season": seasonal,
        "probe_paths": list(PROBE_PATHS),
        "semantics": "priority_hint_only_no_topic_blocking",
    }
