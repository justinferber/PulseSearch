"""18-category coverage classifier.

The taxonomy is the owner-confirmed UNA Events list mirrored read-only as
*coverage inspiration* for a general search engine. A page is labelled with
one primary category plus optional secondary labels and the evidence that
produced it. Nothing here writes to any Events system, and no category is
ever blocked: Diwali, Pride, CSD Berlin and Stadtfest Berlin pages classify
normally and stay searchable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CATEGORIES: tuple[str, ...] = (
    "Conference",
    "Festival",
    "Fundraiser",
    "Lecture",
    "Market",
    "Meal",
    "Social Mixer",
    "Tour",
    "Volunteering",
    "Workshop",
    "Other",
    "Horticulture & Flower Shows",
    "Music & Performance",
    "Sport & Fitness",
    "Parades & Processions",
    "Pride & Community",
    "Exhibitions & Trade Shows",
    "Arts & Culture",
)

KEYWORDS: dict[str, tuple[str, ...]] = {
    "Conference": ("conference", "congress", "summit", "convention", "symposium",
                   "delegates", "keynote", "plenary", "trade fair"),
    "Festival": ("festival", "diwali", "stadtfest", "carnival", "fiesta", "celebrations",
                 "oktoberfest", "eid", "lunar new year", "hanukkah", "midsummer",
                 "light festival", "street party"),
    "Fundraiser": ("fundraiser", "fundraising", "charity gala", "benefit concert",
                   "donation", "sponsored walk", "bake sale", "appeal night"),
    "Lecture": ("lecture", "public talk", "speaker", "seminar", "panel discussion",
                "keynote address", "book talk", "guest lecture"),
    "Market": ("market", "farmers market", "flea market", "craft fair", "bazaar",
               "vendor stalls", "christmas market", "food market"),
    "Meal": ("dinner", "lunch", "brunch", "supper", "banquet", "tasting menu",
             "community meal", "breakfast", "food sharing"),
    "Social Mixer": ("mixer", "networking", "meetup", "social evening", "happy hour",
                     "networking drinks", "gathering"),
    "Tour": ("guided tour", "walking tour", "sightseeing", "excursion", "city walk",
             "open house", "guided walk", "heritage trail"),
    "Volunteering": ("volunteer", "volunteering", "clean-up", "community service",
                     "tree planting", "food bank", "litter pick", "befriending"),
    "Workshop": ("workshop", "masterclass", "hands-on", "training session", "course",
                 "tutorial", "skills session", "repair cafe"),
    "Other": (),
    "Horticulture & Flower Shows": ("flower show", "horticulture", "garden show",
                                    "botanical", "plant fair", "allotment", "orchid",
                                    "gardening"),
    "Music & Performance": ("concert", "live music", "orchestra", "band", "opera",
                            "theatre", "theater", "dance performance", "recital",
                            "dj set", "choir", "musical"),
    "Sport & Fitness": ("marathon", "half marathon", "10k", "race", "football",
                        "match", "tournament", "fitness", "yoga", "cycling", "swim",
                        "parkrun", "sports day"),
    "Parades & Processions": ("parade", "procession", "march", "lantern parade",
                              "carnival parade", "cortege"),
    "Pride & Community": ("pride", "lgbtq", "lgbt", "queer", "csd", "diversity",
                          "trans", "community festival", "inclusion"),
    "Exhibitions & Trade Shows": ("exhibition", "expo", "trade show", "gallery",
                                  "museum exhibition", "showcase", "biennale"),
    "Arts & Culture": ("art", "culture", "cultural", "heritage", "film", "cinema",
                       "literature", "poetry", "book fair", "museum", "crafts"),
}

WORD_RE = re.compile(r"[a-z0-9&']+")


@dataclass
class CategoryResult:
    primary: str
    confidence: float
    labels: dict[str, float] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    uncertain: bool = False

    def as_dict(self) -> dict:
        return {
            "primary": self.primary,
            "confidence": round(self.confidence, 4),
            "labels": {k: round(v, 4) for k, v in self.labels.items()},
            "evidence": self.evidence[:8],
            "uncertain": self.uncertain,
        }


def _hits(haystack: str, phrase: str) -> int:
    if " " in phrase or "&" in phrase:
        return haystack.count(phrase)
    return len(re.findall(r"\b" + re.escape(phrase) + r"\b", haystack))


def classify(title: str, text: str, url: str = "", jsonld: list[dict] | None = None) -> CategoryResult:
    title_l = title.lower()
    text_l = text.lower()[:60_000]
    url_l = url.lower()
    scores: dict[str, float] = {name: 0.0 for name in CATEGORIES}
    evidence: dict[str, list[str]] = {name: [] for name in CATEGORIES}
    for category, phrases in KEYWORDS.items():
        for phrase in phrases:
            t_hits = _hits(title_l, phrase)
            b_hits = _hits(text_l, phrase)
            u_hits = 1 if phrase.replace(" ", "-") in url_l or phrase.replace(" ", "") in url_l else 0
            if not (t_hits or b_hits or u_hits):
                continue
            scores[category] += 3.0 * min(t_hits, 3) + min(b_hits, 6) * 0.6 + u_hits * 0.8
            evidence[category].append(phrase)
    for blob in jsonld or []:
        types = blob.get("@type")
        if isinstance(types, list):
            types = " ".join(str(t) for t in types)
        if types and "event" in str(types).lower():
            scores["Festival"] += 0.5
    positive = {k: v for k, v in scores.items() if v > 0 and k != "Other"}
    if not positive:
        return CategoryResult(primary="Other", confidence=0.05, labels={}, evidence=[], uncertain=True)
    total = sum(positive.values())
    top_name = max(positive, key=lambda k: (positive[k], k))
    top = positive[top_name]
    confidence = min(1.0, (top / (total + 2.0)) + min(0.25, top / 40.0))
    labels = {k: round(v / total, 4) for k, v in sorted(positive.items(), key=lambda kv: -kv[1])}
    secondary = [k for k, v in positive.items() if k != top_name and v >= 0.55 * top]
    for name in secondary:
        labels.setdefault(name, round(positive[name] / total, 4))
    return CategoryResult(
        primary=top_name,
        confidence=round(confidence, 4),
        labels=labels,
        evidence=evidence[top_name],
        uncertain=confidence < 0.18,
    )


def category_coverage(documents: list[dict]) -> dict[str, int]:
    counts = {name: 0 for name in CATEGORIES}
    for doc in documents:
        primary = doc.get("category") or "Other"
        counts[primary] = counts.get(primary, 0) + 1
    return counts
