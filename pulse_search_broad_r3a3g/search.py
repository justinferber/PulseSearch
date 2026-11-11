"""Pulse Search broad-query retrieval over an existing, permissioned staging index.

No network, no new crawling, no imports of the immutable October index.
Weather, stock and live sports cannot be presented as current without providers.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict
from urllib.parse import urlsplit

from .official import links_for

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
den zu mit für wie kann ich ist wo gibt es tickets ticket auch nach von
weather forecast today tomorrow jetzt heute morgen bitte wetter""".split())
GEOGRAPHIES = ("berlin", "london", "hamburg", "munich", "münchen", "munchen",
               "paris", "manchester", "new york", "birmingham", "glasgow",
               "cologne", "köln", "koeln", "frankfurt", "stuttgart")
# Query expansion improves recall without pretending to create evidence.
EXPAND = {
    "fireworks": ("firework", "feuerwerk", "silvester", "display"),
    "firework": ("fireworks", "feuerwerk"),
    "pride": ("csd", "christopher street day", "lgbtq"),
    "csd": ("pride", "christopher street day"),
    "festival": ("festivals", "stadtfest"),
    "festivals": ("festival", "stadtfest"),
    "concert": ("concerts", "konzert", "gig", "events", "calendar", "programme"),
    "concerts": ("concert", "konzert", "gig"),
    "gig": ("concert", "concerts", "konzert"),
    "book": ("booking", "buy", "kaufen"),
    "booking": ("book", "tickets", "karten"),
    "tickets": ("ticket", "karten", "eintrittskarten"),
    "christmas": ("weihnachtsmarkt", "advent"),
    "market": ("markt", "weihnachtsmarkt"),
    "markets": ("market", "markt", "weihnachtsmarkt"),
    "travel": ("transport", "verkehr", "train"),
    "transport": ("travel", "bahn", "train", "bvg", "tfl"),
    "wetter": ("weather", "forecast"),
    "weather": ("wetter", "forecast", "vorhersage"),
    "forecast": ("weather", "wetter", "vorhersage"),
    "konzert": ("concert", "konzerte", "gig"),
    "konzertkarten": ("concert", "tickets", "karten"),
    "konzerte": ("concert", "concerts", "gig"),
    "karten": ("tickets", "ticket", "eintrittskarten"),
    "eintrittskarten": ("tickets", "karten"),
    "feuerwerk": ("fireworks", "firework"),
    "weihnachtsmarkt": ("christmas", "market", "advent"),
    "flugzeug": ("flight", "flights", "airline"),
    "flug": ("flight", "flights"),
}
WORDS = re.compile(r"[^\W_]+", re.UNICODE)
BOOKING = re.compile(r"\b(book|booking|buy|purchase|ticket|tickets|karten|konzertkarten|eintritt|kaufen|reserv|checkout)\b", re.I)
HOWTO = re.compile(r"\b(how|wie|guide|instructions?|steps?|where to buy|where can i|get tickets|"
                   r"book|buy|purchase|kaufen|reserv\w*|refund|return|cancel)\b", re.I)
EVENTS = re.compile(r"\b(fireworks?|feuerwerk|pride|csd|festival|festivals|concert|concerts|"
                    r"konzert\w*|gig|music|christmas|weihnachtsmarkt\w*|weihnachtsm\w*|diwali|"
                    r"parades?|procession|events?|veranstaltungen?|stadfest|stadtfest|karneval|"
                    r"sport|tournament|glastonbury)\b", re.I)
WEATHER = re.compile(r"\b(weather|forecast|temperature|rainfall|wetter|vorhersage|"
                     r"regen|sonnig|bewölkung)\b", re.I)
NEGATION = re.compile(r"\b(?:excluding|without|except|nicht|ohne|ausser|außer)\b\s+(.+)$", re.I)
SPORTS = re.compile(r"\b(fifa|world cup|football score|match result|live score)\b", re.I)
TRANSLATE = re.compile(r"\b(translate|translation|übersetz\w*|translate into)\b", re.I)
FLIGHTS = re.compile(r"\b(flights?|airfare|airline|flug|flüge)\b", re.I)
TRANSPORT = re.compile(r"\b(public transport|transport|tfl|bvg|s-bahn|s bahn|sbahn|"
                       r"get to|journey|journey planner|fahrplan|wie komme|anfahrt|verkehr)\b", re.I)
REFUND = re.compile(r"\b(refund|refunds|return|returns|cancel|cancellation|erstattung|"
                    r"stornieren)\b", re.I)
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
    elif TRANSPORT.search(q):
        kind = "transport"
    elif FLIGHTS.search(q) and not EVENTS.search(q):
        kind = "flights"
    elif (HOWTO.search(q) and (BOOKING.search(q) or any(k in q for k in
                            ("how do", "how to", "wie kann", "how can")))) or \
            (BOOKING.search(q) and (EVENTS.search(q) or "ticket" in q)) or REFUND.search(q):
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
    if location and location in ("münchen", "munchen"):
        location = "munich"
    elif location in ("köln", "koeln"):
        location = "cologne"
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
    # Transport guidance often mentions tickets (machines, day passes), so it
    # must be typed before the booking heuristic or a transit guide becomes a
    # booking guide.
    if "transport" in t or "public transit" in t or "getting there" in t or "ticket machine" in t:
        return "transport_guide"
    if BOOKING.search(t) and (HOWTO.search(t) or "guide" in t):
        return "booking_guide"
    if "how to" in t or "faq" in t or "instructions" in t or "anleitung" in t:
        return "how_to"
    if "venue" in t or "arena" in t or "stadium" in t:
        return "venue"
    if "calendar" in t or "listings" in t or "whats on" in t:
        return "event_listing"
    if EVENTS.search(t):
        return "event_detail"
    return "general_reference"


def _score(doc: dict, intent: SearchIntent) -> tuple[float, list[str]]:
    """Explainable lexical/BM25/authority blend, not a learned ranker."""
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
    bm25 = doc.get("bm25")
    if isinstance(bm25, (int, float)) and bm25 < 0:
        # SQLite bm25() returns a negative value: closer to zero is better.
        score += min(4.0, 1.5 / (1.0 + abs(float(bm25))))
    authority = str(doc.get("source_authority") or "").lower()
    if authority in ("official", "primary"):
        score += 3.0
        reasons.append("official_source")
    elif authority == "reference":
        score += 1.0
    fetched = str(doc.get("fetched_at") or "")
    if fetched[:4].isdigit() and int(fetched[:4]) >= 2026:
        score += 0.6
        reasons.append("recent_fetch")
    elif fetched[:4].isdigit() and int(fetched[:4]) < 2024:
        score -= 1.0
        reasons.append("stale_fetch")
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
            purpose = set(intent.expanded) - ({intent.location} if intent.location else set())
            if purpose and not (purpose & (t | s)):
                score -= 12.0
                reasons.append("off_intent_instruction_page")
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


def _canonical_key(url: str) -> str:
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+", "/", parts.path or "/").rstrip("/") or "/"
    return host + path


def _excluded_terms(query: str) -> tuple[str, ...]:
    match = NEGATION.search(query or "")
    if not match:
        return ()
    return tuple(dict.fromkeys(tokenize(match.group(1))))


def _snippet(text: str, tokens: tuple[str, ...], cap: int = 260) -> str:
    clean = " ".join(str(text or "").split())
    if not clean:
        return ""
    low = clean.lower()
    position = min((low.find(t) for t in tokens if t in low), default=-1)
    if position > 80:
        clean = "…" + clean[max(0, position - 60):]
    return clean[:cap].rstrip()


def _diverse(items: list[dict], limit: int, per_host: int = 2) -> list[dict]:
    """Keep source diversity; if the corpus is single-host, do not drop it."""
    hosts = {(_canonical_key(item["url"]).split("/")[0]) for item in items if item.get("url")}
    if len(hosts) <= 1:
        return items[:limit]
    out, counts = [], {}
    for item in items:
        host = (_canonical_key(item["url"]).split("/")[0]) if item.get("url") else ""
        if counts.get(host, 0) >= per_host:
            continue
        counts[host] = counts.get(host, 0) + 1
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _official_response(query: str, intent: SearchIntent, mode: str, note: str) -> dict:
    cards = links_for(intent.kind, query, intent.location)
    return {"query": query, "intent": intent.as_dict(), "status": "official_links",
            "response_mode": mode, "results": cards, "official_links": cards,
            "answer": None, "notices": [note],
            "note": note}


def search_documents(documents: list[dict], query: str, limit: int = 10) -> dict:
    """Search admitted documents and reviewed official services, no network.

    A weather or translation query is a *handoff* to the official service even
    when no provider is configured. A matched snippet is evidence for a link,
    not proof that a time-sensitive claim is still true.
    """
    intent = classify_query(query)
    if intent.kind == "navigate" and intent.official_navigation:
        name, url = OFFICIAL_NAVIGATION[intent.official_navigation]
        cards = [{"title": name, "url": url, "publisher": name,
                  "description": "Official site navigation.", "kind": "navigation",
                  "source_kind": "curated_official_link", "verified_live": False,
                  "verified_at": "2026-11-11"}]
        return {"query": query, "intent": intent.as_dict(), "status": "official_navigation",
                "response_mode": "OFFICIAL_LINK", "results": cards, "official_links": cards,
                "answer": None, "notices": [],
                "note": "Navigation registry is not a crawler source allowlist."}
    if intent.kind == "weather":
        return _official_response(
            query, intent, "CURRENT_SERVICE_HANDOFF",
            "Official forecast services; Pulse Search did not fetch a live value. "
            "A current observation is not a forecast for tomorrow.")
    if intent.kind == "translate":
        return _official_response(
            query, intent, "CURRENT_SERVICE_HANDOFF",
            "Use an authorised translator; Pulse Search did not perform or claim a translation.")
    if intent.kind == "flights" or (REFUND.search(query) and intent.kind == "how_to"):
        return _official_response(
            query, intent, "OFFICIAL_LINKS",
            "No live fares, stock or refund decision is claimed; use the official channels.")
    excluded = _excluded_terms(query)
    scored = []
    seen_urls, seen_titles = set(), set()
    for doc in documents:
        if doc.get("revoked") or not doc.get("url"):
            continue
        if str(doc.get("source_id") or "").lower() in ("untrusted", "blocked", "phish"):
            continue
        text = " ".join(str(doc.get(k) or "") for k in ("title", "snippet", "url")).lower()
        if excluded and any(term in text for term in excluded):
            continue
        score, reasons = _score(doc, intent)
        if score <= 0:
            continue
        # A general question needs more than one incidental place-name match.
        core = set(intent.tokens)
        coverage = len(core & set(tokenize(str(doc.get("title") or "") + " " +
                                         str(doc.get("snippet") or ""))))
        if intent.kind in ("general", "factual", "transport") and core and \
                coverage / len(core) <= 0.5:
            continue
        if intent.location and intent.kind == "events":
            haystack = (str(doc.get("title") or "") + " " + str(doc.get("snippet") or "") +
                        " " + str(doc.get("url") or "")).lower()
            if intent.location not in haystack:
                continue
        url_key = _canonical_key(doc["url"])
        title_key = normal(str(doc.get("title") or ""))
        if url_key in seen_urls or (title_key and title_key in seen_titles):
            continue
        seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        scored.append({"title": doc.get("title", ""), "url": doc["url"],
                       "snippet": _snippet(str(doc.get("snippet") or ""), intent.tokens),
                       "publisher": (_canonical_key(doc["url"]).split("/")[0]),
                       "source_id": doc.get("source_id"),
                       "fetched_at": doc.get("fetched_at"),
                       "document_type": document_type(doc),
                       "location": intent.location,
                       "score": score, "ranking_reasons": reasons,
                       "source_kind": "permissioned_staging_document",
                       "verified_live": False})
    scored.sort(key=lambda d: (-d["score"], d["url"]))
    hits = _diverse(scored, max(0, min(int(limit), 50)))
    related = links_for(intent.kind, query, intent.location) if intent.kind in (
        "transport", "how_to") else []
    if hits:
        status = "staging_results"
        if intent.needs_live_data:
            status = "staging_context_fresh_provider_required"
        mode = "EXTRACTIVE_ANSWER" if intent.kind in ("how_to", "factual") else "SEARCH_RESULTS"
        notices = ["Snippets are attributed excerpts from admitted pages; verify current dates, "
                   "prices, stock and booking availability separately."]
        if related and intent.kind == "how_to":
            notices.append("Reviewed official entry points are listed separately; they are "
                           "navigation, not admitted page content.")
        if excluded:
            notices.append("Excluded terms: " + ", ".join(excluded))
        return {"query": query, "intent": intent.as_dict(), "status": status,
                "response_mode": mode, "results": hits, "official_links": [],
                "related_official_links": related,
                "answer": None, "notices": notices,
                "note": notices[0]}
    official = links_for(intent.kind, query, intent.location)
    if official:
        notices = ["No admitted page answered this; these are reviewed official entry points. "
                   "They are navigation, not a live value or a content licence."]
        if excluded:
            notices.append("Excluded terms: " + ", ".join(excluded))
        return {"query": query, "intent": intent.as_dict(), "status": "official_links",
                "response_mode": "OFFICIAL_LINKS", "results": official,
                "official_links": official, "related_official_links": official,
                "answer": None, "notices": notices,
                "note": notices[0]}
    return {"query": query, "intent": intent.as_dict(), "status": "no_staging_evidence",
            "response_mode": "NO_EVIDENCE", "results": [], "official_links": [],
            "related_official_links": [],
            "answer": None, "notices": ["No evidence and no reviewed official entry point."],
            "note": "No evidence and no reviewed official entry point."}


def search_staging(staging, query: str, limit: int = 10, scan_limit: int = 5000) -> dict:
    """Rank candidates from the existing staging index, without schema changes.

    Prefer indexed FTS5 OR candidate generation so relevant pages outside the
    first 5,000 document IDs are still findable. Reranking remains intent-aware.
    For databases without FTS, use a bounded read-only scan and report its
    limitation rather than pretending it exhaustively searched all pages.
    """
    intent = classify_query(query)
    if intent.kind in ("navigate", "weather"):
        response = search_documents([], query, limit)
        response["retrieval_mode"] = "navigation_or_live_provider"
        return response
    conn = getattr(staging, "conn", None)
    docs = None
    mode = "bounded_scan"
    if conn is not None and getattr(staging, "fts", False):
        # FTS5 phrase-prefix terms are bound through a query parameter and
        # cannot change SQL structure. Unicode words only, never raw user SQL.
        terms = [t for t in intent.expanded[:24] if t.isalnum()]
        if terms:
            expression = " OR ".join('"' + t + '"*' for t in terms)
            try:
                rows = conn.execute(
                    """SELECT d.*, bm25(doc_fts) AS bm25 FROM doc_fts
                       JOIN docs d ON d.doc_id=doc_fts.rowid
                       WHERE doc_fts MATCH ? AND d.revoked=0
                       ORDER BY bm25(doc_fts) LIMIT ?""",
                    (expression, max(100, min(scan_limit, 1000))),
                ).fetchall()
                docs = [dict(r) for r in rows]
                mode = "fts_candidates"
            except Exception:
                # Operational fallback should be visible to the caller. Do
                # not misrepresent a failed index query as an exhaustive result.
                mode = "fts_error_bounded_scan"
    if docs is None:
        docs = staging.all_documents(scan_limit)
    response = search_documents(docs, query, limit)
    response["retrieval_mode"] = mode
    return response
