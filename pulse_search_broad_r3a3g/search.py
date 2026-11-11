"""Pulse Search broad-query retrieval over an existing, permissioned staging index.

No network, no new crawling, no imports of the immutable October index.
Weather, stock and live sports cannot be presented as current without providers.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict
from urllib.parse import urlsplit

# Verified-site *navigation*, not admission to crawl or permission to copy content.
OFFICIAL_NAVIGATION = {
    "chatgpt": ("ChatGPT", "https://chatgpt.com/"),
    "amazon": ("Amazon", "https://www.amazon.com/"),
    "youtube": ("YouTube", "https://www.youtube.com/"),
    "gmail": ("Gmail", "https://mail.google.com/"),
    "wordle": ("Wordle", "https://www.nytimes.com/games/wordle/index.html"),
    "facebook": ("Facebook", "https://www.facebook.com/"),
    "google": ("Google", "https://www.google.com/"),
    "google translate": ("Google Translate", "https://translate.google.com/"),
    "walmart": ("Walmart", "https://www.walmart.com/"),
    "canva": ("Canva", "https://www.canva.com/"),
}
ALIASES = {"chat gpt": "chatgpt", "yt": "youtube", "g mail": "gmail"}
STOP = frozenset("""a an and are at be can do does for from get how i in is it me my
near of on or the there this to what when where which who why with you your
find show tell please best information about und der die das ein eine im
den zu mit für wie kann ich ist wo gibt es tickets ticket""".split())
GEOGRAPHIES = ("berlin", "london", "hamburg", "munich", "münchen",
               "paris", "manchester", "new york", "birmingham", "glasgow")
# Query expansion improves recall without pretending to create evidence.
EXPAND = {
    "fireworks": ("firework", "feuerwerk", "silvester", "display"),
    "firework": ("fireworks", "feuerwerk"),
    "pride": ("csd", "christopher street day", "lgbtq"),
    "csd": ("pride", "christopher street day"),
    "festival": ("festivals", "stadtfest"),
    "festivals": ("festival", "stadtfest"),
    "concert": ("concerts", "konzert", "gig"),
    "concerts": ("concert", "konzert", "gig"),
    "gig": ("concert", "concerts", "konzert"),
    "book": ("booking", "buy", "kaufen"),
    "booking": ("book", "tickets", "karten"),
    "tickets": ("ticket", "karten", "eintrittskarten"),
    "christmas": ("weihnachtsmarkt", "advent"),
    "market": ("markt", "weihnachtsmarkt"),
    "markets": ("market", "markt", "weihnachtsmarkt"),
    "travel": ("transport", "verkehr", "train"),
    "transport": ("travel", "bahn", "train"),
}
WORDS = re.compile(r"[^\W_]+", re.UNICODE)
BOOKING = re.compile(r"\b(book|booking|buy|purchase|ticket|tickets|karten|eintritt|kaufen|reserv|checkout)\b", re.I)
HOWTO = re.compile(r"\b(how|wie|guide|instructions?|steps?|where to buy|where can i|get tickets)\b", re.I)
EVENTS = re.compile(r"\b(fireworks?|pride|csd|festival|festivals|concert|concerts|gig|"
                    r"music|christmas|weihnachtsmarkt|diwali|parade|procession|events?|"
                    r"stadfest|stadtfest|karneval|sport|tournament)\b", re.I)
WEATHER = re.compile(r"\b(weather|forecast|temperature|rainfall|wetter|vorhersage)\b", re.I)
SPORTS = re.compile(r"\b(fifa|world cup|football score|match result|live score)\b", re.I)
TRANSLATE = re.compile(r"\b(translate|translation|übersetz|translate into)\b", re.I)
FRESH = re.compile(r"\b(today|tomorrow|now|live|currently|this evening|this weekend|"
                   r"heute|morgen|jetzt|aktuell|tonight)\b", re.I)
FAKE_NAV = re.compile(r"\b(login|sign in|official|website|site)\b", re.I)


def normal(text: str) -> str:
    return " ".join(WORDS.findall(unicodedata.normalize("NFKC", text).casefold()))


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(w for w in WORDS.findall(normal(text)) if w not in STOP and len(w) > 1)


@dataclass(frozen=True)
class SearchIntent:
    kind: str
    query: str
    tokens: tuple[str, ...]
    expanded: tuple[str, ...]
    location: str | None
    needs_live_data: bool
    official_navigation: str | None = None

    def as_dict(self) -> dict:
        d = asdict(self)
        d["tokens"] = list(self.tokens)
        d["expanded"] = list(self.expanded)
        return d


def classify_query(query: str) -> SearchIntent:
    raw = (query or "").strip()
    q = normal(raw)
    # Only exact brand names or the brand name followed by official/login/site
    # trigger navigation. Other queries about the brand need actual documents.
    nav = ALIASES.get(q, q)
    if nav not in OFFICIAL_NAVIGATION:
        nav = re.sub(r"\s+(official|website|site|login|sign in)$", "", nav)
        nav = ALIASES.get(nav, nav)
        if not FAKE_NAV.search(q):
            nav = ""
    if nav in OFFICIAL_NAVIGATION and (q == nav or q in ALIASES or FAKE_NAV.search(q)):
        kind = "navigate"
    elif WEATHER.search(q):
        kind = "weather"
    elif TRANSLATE.search(q):
        kind = "translate"
    elif HOWTO.search(q) and (BOOKING.search(q) or any(k in q for k in ("how do", "how to", "wie kann", "how can"))):
        kind = "how_to"
    elif SPORTS.search(q):
        kind = "sports"
    elif EVENTS.search(q):
        kind = "events"
    elif re.search(r"\b(shop|shopping|price|buy|product|store)\b", q):
        kind = "shopping"
    else:
        kind = "general"
    location = next((city for city in GEOGRAPHIES if re.search(r"\b"+re.escape(city)+r"\b", q)), None)
    tokens = tuple(dict.fromkeys(tokenize(q)))
    extended = list(tokens)
    for word in tokens:
        for alias in EXPAND.get(word, ()):
            for part in tokenize(alias):
                if part not in extended:
                    extended.append(part)
    # For offline retrieval, weather/current results must NEVER masquerade as live.
    needs_live = kind == "weather" or bool(FRESH.search(q) and kind in ("sports", "shopping", "events"))
    return SearchIntent(kind, raw, tokens, tuple(extended[:32]), location, needs_live,
                        nav if kind == "navigate" else None)


def document_type(doc: dict) -> str:
    declared = doc.get("document_type")
    if declared:
        return str(declared)
    t = normal(" ".join(str(doc.get(k) or "") for k in ("title", "snippet", "url")))
    if BOOKING.search(t) and (HOWTO.search(t) or "guide" in t):
        return "booking_guide"
    if "how to" in t or "faq" in t or "instructions" in t or "anleitung" in t:
        return "how_to"
    if "transport" in t or "public transit" in t or "getting there" in t:
        return "transport_guide"
    if "venue" in t or "arena" in t or "stadium" in t:
        return "venue"
    if "calendar" in t or "listings" in t or "whats on" in t:
        return "event_listing"
    if EVENTS.search(t):
        return "event_detail"
    return "general_reference"


def _score(doc: dict, intent: SearchIntent) -> tuple[float, list[str]]:
    title = normal(str(doc.get("title") or ""))
    snippet = normal(str(doc.get("snippet") or ""))
    url = normal(str(doc.get("url") or ""))
    t = set(tokenize(title))
    s = set(tokenize(snippet))
    u = set(tokenize(url))
    core = set(intent.tokens)
    matched_core = core & (t | s | u)
    # At least one true query term must match; synonym-only is not sufficient.
    if core and not matched_core:
        return (0.0, [])
    if not core:
        return (0.0, [])
    score = 0.0
    reasons: list[str] = []
    for word in intent.tokens:
        if word in t:
            score += 5.0
        if word in s:
            score += 1.6
        if word in u:
            score += 0.8
    for word in set(intent.expanded) - core:
        if word in t:
            score += 1.1
        elif word in s:
            score += 0.45
    # Prefer pages that match the complete purpose, not an accidental word.
    coverage = len(matched_core) / len(core)
    score += coverage * 6.0
    if coverage < 0.25:
        score *= 0.5
    typ = document_type(doc)
    if intent.kind == "how_to":
        if typ in ("booking_guide", "how_to"):
            score += 8.0
            reasons.append("instruction_page")
        if BOOKING.search(title+" "+snippet) and ("concert" in intent.tokens or "tickets" in intent.tokens):
            score += 2.0
    elif intent.kind == "events" and typ in ("event_detail", "event_listing"):
        score += 3.0
        reasons.append("event_page")
    elif intent.kind == "shopping" and typ in ("product", "shopping_guide"):
        score += 3.0
    if intent.location:
        text = title+" "+snippet+" "+url
        if intent.location in text:
            score += 6.0
            reasons.append("location_match")
        elif any(city in text for city in GEOGRAPHIES if city != intent.location):
            # Never rank a London-only ticketing page as Berlin-specific.
            score *= 0.20
            reasons.append("location_mismatch")
    if coverage == 1.0:
        reasons.append("all_query_terms")
    return (round(score, 3), reasons)


def search_documents(documents: list[dict], query: str, limit: int = 10) -> dict:
    """Search already admitted/staged documents only, no network or writes.

    Source URLs are unmodified. A matching source snippet is evidence for
    navigation, NOT evidence that a time-sensitive claim is still true.
    """
    intent = classify_query(query)
    if intent.kind == "navigate" and intent.official_navigation:
        name, url = OFFICIAL_NAVIGATION[intent.official_navigation]
        return {"query": query, "intent": intent.as_dict(), "status": "official_navigation",
                "results": [{"title": name, "url": url, "source_kind": "curated_official_link",
                             "verified_live": False}], "answer": None,
                "note": "Navigation registry is not a crawler source allowlist."}
    if intent.kind == "weather" or (intent.kind == "translate" and not documents):
        return {"query": query, "intent": intent.as_dict(), "status": "live_provider_required",
                "results": [], "answer": None,
                "note": "A current provider or translation capability must be connected; no fabricated result."}
    scored = []
    for doc in documents:
        if doc.get("revoked") or not doc.get("url"):
            continue
        score, reasons = _score(doc, intent)
        if score <= 0:
            continue
        scored.append({"title": doc.get("title", ""), "url": doc["url"],
                       "snippet": doc.get("snippet", ""), "source_id": doc.get("source_id"),
                       "fetched_at": doc.get("fetched_at"),
                       "document_type": document_type(doc),
                       "score": score, "ranking_reasons": reasons,
                       "source_kind": "permissioned_staging_document",
                       "verified_live": False})
    scored.sort(key=lambda d: (-d["score"], d["url"]))
    hits = scored[:max(0, min(int(limit), 50))]
    # A dated event snippet is not a live booking guarantee; make no claims
    # about available tickets, weather or an actual transaction.
    status = "staging_results" if hits else "no_staging_evidence"
    if intent.needs_live_data:
        status = "staging_context_fresh_provider_required" if hits else "live_provider_required"
    return {"query": query, "intent": intent.as_dict(), "status": status,
            "results": hits, "answer": None,
            "note": "Sources are offline-indexed evidence; verify current dates, prices and booking availability separately."}


def search_staging(staging, query: str, limit: int = 10, scan_limit: int = 5000) -> dict:
    """Work with the existing StagingIndex without changing its schema.

    R3-A3G's first bounded implementation uses a read-only capped scan for
    offline evaluation. Before high-volume release replace this with indexed
    candidate generation and measure recall over larger collections.
    """
    return search_documents(staging.all_documents(scan_limit), query, limit)
