"""Official-service directory: useful navigation when live data is unavailable.

These are reviewed public entry points, not crawler admissions and not a
licence to scrape. A weather card says "see the current forecast there"; it is
never presented as an observation. No paid API is required for any of this.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from urllib.parse import quote_plus

VERIFIED_AT = "2026-11-11"


@dataclass(frozen=True)
class OfficialLink:
    title: str
    url: str
    publisher: str
    description: str
    kind: str
    countries: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()

    def card(self) -> dict:
        data = asdict(self)
        data["countries"] = list(self.countries)
        data["topics"] = list(self.topics)
        data["aliases"] = list(self.aliases)
        data["source_kind"] = "official_directory"
        data["verified_live"] = False
        data["verified_at"] = VERIFIED_AT
        return data


LINKS: tuple[OfficialLink, ...] = (
    # Weather: national forecast services. No direct local URL is invented.
    OfficialLink("BBC Weather", "https://www.bbc.co.uk/weather", "BBC",
                 "Current conditions and forecasts for UK and international cities.",
                 "weather", ("GB", "GLOBAL"), ("weather", "forecast")),
    OfficialLink("Met Office UK forecast", "https://weather.metoffice.gov.uk/forecast/uk",
                 "Met Office", "Official UK national weather service forecasts and warnings.",
                 "weather", ("GB",), ("weather", "forecast")),
    OfficialLink("Deutscher Wetterdienst (DWD)", "https://www.dwd.de/", "DWD",
                 "Germany's national weather service: warnings, forecasts and climate information.",
                 "weather", ("DE",), ("weather", "forecast", "wetter")),
    # Translation: use a translator; never claim a translation was performed.
    OfficialLink("DeepL Translator", "https://www.deepl.com/translator", "DeepL",
                 "Translate text between languages in the browser.",
                 "translate", (), ("translate", "translation", "übersetzen")),
    OfficialLink("Google Translate", "https://translate.google.com/", "Google",
                 "Translate text, documents and web pages.",
                 "translate", (), ("translate", "translation")),
    # Berlin concert/ticket guidance.
    OfficialLink("Eventim Berlin", "https://www.eventim.de/city/berlin-8/", "Eventim",
                 "Authorised ticketing agency; check the event page for the official seller.",
                 "tickets", ("DE",), ("tickets", "konzert", "concert", "berlin")),
    OfficialLink("Eventim Germany", "https://www.eventim.de/", "Eventim",
                 "Authorised ticketing agency; check the event page for the official seller.",
                 "tickets", ("DE",), ("tickets", "konzert", "concert")),
    OfficialLink("Berlin.de events calendar", "https://www.berlin.de/events/", "Berlin.de",
                 "City events calendar with organiser and venue links.",
                 "events", ("DE",), ("events", "berlin", "concert", "festival")),
    OfficialLink("Berlin.de museums", "https://www.berlin.de/en/museums/", "Berlin.de",
                 "Official Berlin museum directory and visitor information.",
                 "events", ("DE",), ("berlin", "museum", "accessibility", "culture")),
    OfficialLink("Hamburg city portal", "https://www.hamburg.de/", "Hamburg",
                 "Official Hamburg services, events and transport information.",
                 "events", ("DE",), ("hamburg", "events", "transport", "christmas")),
    OfficialLink("Hamburg tourism", "https://www.hamburg.com/", "Hamburg Tourism",
                 "Official Hamburg visitor information, events and Christmas markets.",
                 "events", ("DE",), ("hamburg", "events", "christmas", "music")),
    OfficialLink("Munich city portal", "https://www.muenchen.de/", "Munich",
                 "Official Munich services, events and transport information.",
                 "events", ("DE",), ("munich", "events", "transport", "christmas")),
    OfficialLink("Uber Arena Berlin", "https://www.uber-arena.de/",
                 "Uber Arena", "Venue programme, official box office and travel information.",
                 "venue", ("DE",), ("concert", "venue", "berlin"),
                 ("Mercedes-Benz Arena Berlin", "Mercedes-Benz Arena")),
    OfficialLink("Columbiahalle Berlin", "https://www.columbiahalle.de/", "Columbiahalle",
                 "Venue programme and official ticket information.",
                 "venue", ("DE",), ("concert", "venue", "berlin")),
    OfficialLink("Huxley's Neue Welt", "https://www.huxleys-neue-welt.de/", "Huxley's",
                 "Venue programme, box office and accessibility information.",
                 "venue", ("DE",), ("concert", "venue", "berlin")),
    OfficialLink("Uber Eats Music Hall Berlin", "https://www.uber-eats-music-hall.de/",
                 "Uber Eats Music Hall",
                 "Venue programme, accessibility information and official ticketing links.",
                 "venue", ("DE",), ("concert", "venue", "berlin"),
                 ("Verti Music Hall", "Verti Music Hall Berlin")),
    # London venues.
    OfficialLink("The O2", "https://www.theo2.co.uk/", "The O2",
                 "Official venue programme, ticketing and travel guidance.",
                 "venue", ("GB",), ("concert", "venue", "london")),
    OfficialLink("Roundhouse", "https://www.roundhouse.org.uk/", "Roundhouse",
                 "Official venue programme, tickets and access information.",
                 "venue", ("GB",), ("concert", "venue", "london")),
    OfficialLink("Southbank Centre", "https://www.southbankcentre.co.uk/", "Southbank Centre",
                 "Official programme, booking and access information.",
                 "venue", ("GB",), ("concert", "venue", "london")),
    # Transport.
    OfficialLink("Transport for London", "https://tfl.gov.uk/", "TfL",
                 "Official London transport status, journey planner and fares.",
                 "transport", ("GB",), ("transport", "travel", "london")),
    OfficialLink("BVG Berlin", "https://www.bvg.de/", "BVG",
                 "Official Berlin public transport journey planner and tickets.",
                 "transport", ("DE",), ("transport", "travel", "berlin")),
    OfficialLink("S-Bahn Berlin", "https://www.s-bahn-berlin.de/", "S-Bahn Berlin",
                 "Official Berlin S-Bahn timetables and service information.",
                 "transport", ("DE",), ("transport", "travel", "berlin")),
    # Flights: seller checks and direct airlines.
    OfficialLink("British Airways", "https://www.britishairways.com/", "British Airways",
                 "Book direct with the airline; fare rules and baggage are shown before payment.",
                 "flights", (), ("flights", "airline")),
    OfficialLink("Lufthansa", "https://www.lufthansa.com/", "Lufthansa",
                 "Book direct with the airline; fare rules and baggage are shown before payment.",
                 "flights", (), ("flights", "airline")),
    OfficialLink("easyJet", "https://www.easyjet.com/", "easyJet",
                 "Book direct with the airline; fare rules and baggage are shown before payment.",
                 "flights", (), ("flights", "airline")),
    OfficialLink("Ryanair", "https://www.ryanair.com/", "Ryanair",
                 "Book direct with the airline; fare rules and baggage are shown before payment.",
                 "flights", (), ("flights", "airline")),
    OfficialLink("UK Civil Aviation Authority (ATOL)", "https://www.caa.co.uk/", "CAA",
                 "Check ATOL protection and consumer advice before booking a package.",
                 "flights", ("GB",), ("flights", "refund", "protection")),
    OfficialLink("ABTA", "https://www.abta.com/", "ABTA",
                 "Check whether a travel agent is a member and what protection applies.",
                 "flights", ("GB",), ("flights", "agent")),
    # Sports and general reference.
    OfficialLink("FIFA", "https://www.fifa.com/", "FIFA",
                 "Official tournament information, fixtures and ticketing announcements.",
                 "sports", (), ("sports", "world cup", "football")),
    OfficialLink("UEFA", "https://www.uefa.com/", "UEFA",
                 "Official competition information and ticketing announcements.",
                 "sports", (), ("sports", "football")),
    OfficialLink("NHS 111", "https://111.nhs.uk/", "NHS",
                 "NHS 111 urgent and emergency care guidance for England.",
                 "reference", ("GB",), ("nhs", "111", "urgent", "medical")),
    OfficialLink("Wikipedia", "https://en.wikipedia.org/wiki/Special:Search?search={query}",
                 "Wikimedia", "General reference; verify time-sensitive facts against a primary source.",
                 "reference", (), ("general", "reference", "factual")),
    OfficialLink("GOV.UK", "https://www.gov.uk/search/all?keywords={query}", "GOV.UK",
                 "Official UK government guidance and public services.",
                 "reference", ("GB",), ("refund", "consumer", "guidance")),
    OfficialLink("Verbraucherzentrale",
                 "https://www.verbraucherzentrale.de/wissen/vertraege-reklamation",
                 "Verbraucherzentrale",
                 "German consumer advice for contracts, cancellations and refunds.",
                 "reference", ("DE",), ("refund", "consumer", "cancellation", "tickets")),
    OfficialLink("Berlin.de service portal", "https://www.berlin.de/en/", "Berlin.de",
                 "Official city services, transport and visitor information.",
                 "reference", ("DE",), ("berlin", "guidance", "transport")),
    # Event discovery: city/organiser calendars, not ticket resellers.
    OfficialLink("CSD Berlin", "https://www.csd-berlin.de/", "Berlin Pride",
                 "Berlin Pride/CSD organiser programme and route information.",
                 "events", ("DE",), ("pride", "csd", "berlin")),
    OfficialLink("visitBerlin Christmas markets",
                 "https://www.visitberlin.de/en/christmas-markets-berlin", "visitBerlin",
                 "City tourism guide to Berlin's Christmas markets and opening periods.",
                 "events", ("DE",), ("christmas", "weihnachtsmarkt", "market")),
    OfficialLink("Mayor of London", "https://www.london.gov.uk/", "Mayor of London",
                 "Official London announcements, including New Year's Eve fireworks arrangements.",
                 "events", ("GB",), ("fireworks", "london", "new year")),
    OfficialLink("London Pride", "https://prideinlondon.org/", "Pride in London",
                 "Official Pride in London programme, route and access information.",
                 "events", ("GB",), ("pride", "london", "lgbtq")),
    OfficialLink("Manchester Pride", "https://www.manchesterpride.com/", "Manchester Pride",
                 "Official Manchester Pride programme and access information.",
                 "events", ("GB",), ("pride", "manchester", "lgbtq")),
    OfficialLink("Visit London events", "https://www.visitlondon.com/things-to-do/events",
                 "Visit London", "Official London events listings and visitor guidance.",
                 "events", ("GB",), ("events", "london", "festival")),
    OfficialLink("European Festivals Association", "https://www.efa-aef.eu/", "EFA",
                 "Directory of European festival organisations and members.",
                 "events", (), ("festival", "music", "europe")),
    OfficialLink("Glastonbury Festival", "https://www.glastonburyfestivals.co.uk/",
                 "Glastonbury Festivals",
                 "Official festival dates, ticket information and travel guidance.",
                 "events", ("GB",), ("festival", "music", "glastonbury")),
    OfficialLink("Paris.fr events", "https://www.paris.fr/", "Ville de Paris",
                 "Official city information and event announcements.",
                 "events", ("FR",), ("events", "paris")),
    OfficialLink("Visit Paris Region", "https://www.visitparisregion.com/", "Visit Paris Region",
                 "Official tourism events and visitor guidance for Paris.",
                 "events", ("FR",), ("events", "paris")),
    # Shopping navigation (marketplace seller checks, no price claims).
    OfficialLink("Amazon UK", "https://www.amazon.co.uk/", "Amazon",
                 "Marketplace; check the seller and returns policy before buying.",
                 "shopping", ("GB",), ("shopping", "shop", "buy")),
    OfficialLink("Amazon Germany", "https://www.amazon.de/", "Amazon",
                 "Marketplace; check the seller and returns policy before buying.",
                 "shopping", ("DE",), ("shopping", "shop", "kaufen")),
    OfficialLink("Google Shopping", "https://www.google.com/shopping", "Google",
                 "Compare listed sellers; verify the retailer and final price on its own site.",
                 "shopping", (), ("shopping", "compare", "price")),
)

WEATHER_QUERIES = {"weather", "forecast", "wetter", "vorhersage", "temperature", "rain"}


def _cards(links: list[OfficialLink], query: str, limit: int) -> list[dict]:
    out = []
    for link in links[:limit]:
        card = link.card()
        card["url"] = card["url"].replace("{query}", quote_plus(query))
        out.append(card)
    return out


def _matches(link: OfficialLink, kinds: set[str], topics: set[str], country: str) -> bool:
    if link.kind in kinds:
        return True
    if topics & set(link.topics):
        return True
    return False


CITY_ALIASES = {
    "berlin": "berlin", "london": "london", "paris": "paris",
    "hamburg": "hamburg", "munich": "munich", "münchen": "munich",
    "munchen": "munich", "cologne": "cologne", "köln": "cologne",
    "koeln": "cologne", "frankfurt": "frankfurt", "stuttgart": "stuttgart",
    "manchester": "manchester", "birmingham": "birmingham", "glasgow": "glasgow",
}
COUNTRY_FOR_CITY = {
    "berlin": "DE", "hamburg": "DE", "munich": "DE", "cologne": "DE",
    "frankfurt": "DE", "stuttgart": "DE", "london": "GB", "manchester": "GB",
    "birmingham": "GB", "glasgow": "GB", "paris": "FR",
}
FACETS = {
    "access": ("accessibility", "accessible", "barrierefrei", "wheelchair", "bag",
               "step-free"),
    "tickets": ("ticket", "tickets", "book", "booking", "buy", "seller", "karten"),
    "venue": ("venue", "venues", "arena", "hall", "theatre", "theater", "museum"),
    "transport": ("transport", "travel", "journey", "planner", "bvg", "tfl", "s-bahn"),
    "refund": ("refund", "refunds", "return", "cancel", "cancellation"),
}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(w) > 1}


def _requested_city(query: str, city: str | None) -> str:
    if city:
        return CITY_ALIASES.get(str(city).lower(), str(city).lower())
    q = set(_words(query))
    return next((CITY_ALIASES[c] for c in CITY_ALIASES if c in q), "")


def _link_text(link: OfficialLink) -> str:
    return " ".join((link.title, link.description, link.url,
                     " ".join(link.topics), " ".join(link.aliases))).lower()


def _link_cities(link: OfficialLink) -> set[str]:
    text = _link_text(link)
    return {city for city in set(CITY_ALIASES.values()) if city in text}


def _names_venue(link: OfficialLink, q: str) -> bool:
    """True when the query names this venue (including its old name)."""
    for name in (link.title,) + link.aliases:
        words = [w for w in name.lower().replace("'", "").split()
                 if w not in ("the", "berlin")]
        if words and all(w in q for w in words):
            return True
    return False


def _facet_score(link: OfficialLink, query: str, city: str) -> int:
    q = _words(query)
    text = _link_text(link)
    score = 0
    if city:
        if city in _link_cities(link):
            score += 12
        elif _link_cities(link):
            return -1000
    for facet, words in FACETS.items():
        if any(w in q for w in words):
            if link.kind == "venue" and facet in ("access", "venue"):
                score += 8
            elif link.kind == "transport" and facet == "transport":
                score += 8
            elif link.kind == "tickets" and facet in ("tickets", "venue"):
                score += 14
            elif link.kind == "events" and facet in ("access", "venue"):
                score += 2
    if "museum" in q and "museum" in text:
        score += 10
    for word in q:
        if word in text:
            score += 2
    return score


def _rank_official(chosen: list[OfficialLink], query: str, city: str) -> list[OfficialLink]:
    return sorted(chosen, key=lambda l: (-_facet_score(l, query, city), l.title))


def links_for(kind: str, query: str, city: str | None = None,
              country: str | None = None, limit: int = 8) -> list[dict]:
    """Return reviewed official entry points for an intent.

    ``weather`` always returns national services so a forecast question is
    useful even with no live adapter; the caller must label it as navigation.
    """
    q = (query or "").lower()
    if "nhs" in q and "111" in q:
        nhs = next((link for link in LINKS if link.title == "NHS 111"), None)
        if nhs is not None:
            return _cards([nhs], query, limit)
    loc = _requested_city(query, city)
    topics = {w for w in q.replace("?", " ").replace(",", " ").split() if w}
    kinds = {kind}
    if kind in ("weather", "forecast"):
        kinds |= {"weather"}
        q_words = _words(q)
        q_cities = {CITY_ALIASES[c] for c in CITY_ALIASES if c in q_words}
        has_de = loc in ("berlin", "hamburg", "munich", "cologne", "frankfurt",
                         "stuttgart") or bool(q_cities & {"berlin", "hamburg", "munich",
                         "cologne", "frankfurt", "stuttgart"}) or "german" in q or "deutsch" in q
        has_gb = loc in ("london", "manchester", "birmingham", "glasgow") or \
            bool(q_cities & {"london", "manchester", "birmingham", "glasgow"}) or \
            "uk" in q or "britain" in q
        c = (country or ("MIXED" if has_de and has_gb else "DE" if has_de else
                         "GB" if has_gb else "")).upper()
        chosen = [l for l in LINKS if l.kind == "weather" and
                  (not l.countries or c in l.countries or "GLOBAL" in l.countries)]
        if c == "MIXED":
            chosen = [l for l in LINKS if l.kind == "weather"]
        elif c == "DE":
            chosen.sort(key=lambda l: 0 if l.countries == ("DE",) else 1)
        elif c == "GB":
            chosen.sort(key=lambda l: 0 if "GB" in l.countries else 1)
        return _cards(chosen, query, limit)
    if kind == "translate":
        return _cards([l for l in LINKS if l.kind == "translate"], query, limit)
    if kind in ("tickets", "how_to", "events"):
        c = COUNTRY_FOR_CITY.get(loc, "") if loc else \
            "DE" if ("german" in q or "konzert" in q) else \
            "GB" if ("uk" in q or "britain" in q) else ""
        topics = []
        if "pride" in q or "csd" in q or "lgbt" in q:
            topics.append("pride")
        if "christmas" in q or "weihnachtsmarkt" in q or "advent" in q:
            topics.append("christmas")
        if "firework" in q or "new year" in q or "silvester" in q:
            topics.append("fireworks")
        if "festival" in q or "music" in q or "konzert" in q:
            topics.append("festival")
        if "parade" in q:
            topics.append("parade")
        discovery = [l for l in LINKS if l.kind == "events" and
                     any(t in l.topics for t in topics)] if topics else []
        is_ticket = any(w in q for w in ("ticket", "book", "buy", "konzert",
                                         "concert", "venue", "karten"))
        is_access = any(w in q for w in ("accessibility", "accessible", "bag",
                                         "barrierefrei", "wheelchair"))
        venue_access = is_access and any(w in q for w in (
            "venue", "arena", "hall", "theatre", "theater", "club", "stadium",
            "museum"))
        venues = [l for l in LINKS if l.kind == "venue"
                  and (not c or not l.countries or c in l.countries)]
        sellers = [l for l in LINKS if l.kind == "tickets"
                   and (not c or not l.countries or c in l.countries)]
        # An accessibility question about a venue/museum needs that venue or
        # museum page. It must not steal a Pride/parade/festival query from its
        # organiser, and "music hall" is a venue, not an event topic.
        event_context = any(w in q for w in (
            "pride", "csd", "parade", "festival", "festivals", "fireworks",
            "christmas", "market", "markets", "events", "music")) and not venue_access
        if c == "DE":
            sellers.sort(key=lambda l: 0 if ("Berlin" in l.title) == ("berlin" in q) else 1)
        named_venues = [l for l in LINKS if l.kind == "venue" and _names_venue(l, q)]
        if named_venues:
            return _cards(_rank_official(named_venues, query, loc), query, limit)
        if not c:
            # A ticket query without a city must not fan out to every venue in
            # the directory. Use a named discovery result or return no evidence.
            sellers = []
            venues = []
        if is_ticket and topics:
            # Tickets for a named event belong to its organiser or an authorised
            # seller, not to every venue that happens to be in the city.
            booking = sellers
        else:
            booking = venues if (is_access and not event_context) else \
                (sellers + venues if is_ticket else [])
        calendars = [l for l in LINKS if l.kind == "events" and
                     (not c or not l.countries or c in l.countries)]
        if loc:
            discovery = [l for l in discovery if loc in _link_cities(l)]
            calendars = [l for l in calendars if loc in _link_cities(l)]
        if "museum" in q:
            museums = [l for l in calendars if "museum" in l.title.lower()]
            return _cards(_rank_official(museums, query, loc), query, limit)
        if is_access:
            # No calendar padding: an access question gets the venue or the
            # organiser it names, and nothing else. If it names a venue, do not
            # list every other venue in the same city.
            chosen = discovery
            if venue_access:
                named = []
                for link in venues:
                    names = (link.title,) + link.aliases
                    if any(all(word in q for word in name.lower().split()
                               if word not in ("the", "berlin")) for name in names):
                        named.append(link)
                chosen = named or venues
            return _cards(_rank_official(chosen, query, loc), query, limit)
        if is_ticket and not topics:
            # A ticket/venue query must not be padded with generic city, Pride
            # or festival calendars that do not sell the requested tickets.
            calendars = []
        if topics:
            topical = [l for l in calendars if any(t in l.topics for t in topics)]
            generic = [l for l in calendars if "events" in l.title.lower()]
            calendars = topical + [l for l in generic if l not in topical]
        calendars = [l for l in calendars if "museum" not in l.title.lower()]
        if c == "DE" and ("music" in q or "festival" in q) and not is_access:
            calendars.sort(key=lambda l: 0 if "Berlin.de" == l.publisher else 1)
        if "refund" in q or "return" in q or "cancel" in q:
            gov = [l for l in LINKS if l.publisher == "GOV.UK"]
            de = [l for l in LINKS if l.publisher == "Verbraucherzentrale"]
            caa = [l for l in LINKS if l.publisher == "CAA"]
            # Consumer guidance follows the jurisdiction of the question.
            wants_de = c == "DE" or any(w in q for w in
                                        ("germany", "german", "deutschland", "deutsch"))
            refund = (de + gov) if wants_de else gov
            refund += caa if any(w in q for w in
                                 ("flight", "airline", "airfare")) else []
            return _cards(refund, query, limit)
        # Do not turn an arbitrary phrase into a city calendar. A handoff needs
        # either a recognised topic, a known city/country, or a booking intent.
        if kind in ("events", "how_to") and not discovery and not booking and not c:
            return []
        chosen = []
        for link in discovery + booking + calendars:
            if link not in chosen:
                chosen.append(link)
        if loc and (discovery or calendars) and not booking and not any(
                loc in _link_text(link) for link in discovery + calendars):
            return []
        chosen = [l for l in chosen if _facet_score(l, query, loc) > -1000]
        return _cards(_rank_official(chosen, query, loc), query, limit)
    if kind in ("transport", "travel"):
        c = COUNTRY_FOR_CITY.get(loc, "") if loc else \
            "DE" if "berlin" in q else "GB" if "london" in q else ""
        chosen = [l for l in LINKS if l.kind == "transport"
                  and (not c or not l.countries or c in l.countries)]
        chosen = [l for l in chosen if _facet_score(l, query, loc) > -1000]
        return _cards(_rank_official(chosen, query, loc), query, limit)
    if kind in ("flights", "buy_flights"):
        return _cards([l for l in LINKS if l.kind == "flights"], query, limit)
    if kind in ("sports", "shopping"):
        chosen = [l for l in LINKS if l.kind == kind]
        if kind == "shopping":
            c = COUNTRY_FOR_CITY.get(loc, "") if loc else \
                "DE" if "berlin" in q else "GB" if "london" in q else ""
            chosen.sort(key=lambda l: 0 if c and c in l.countries else 1)
        return _cards(chosen, query, limit)
    if kind in ("general", "reference", "index_lookup"):
        out = []
        for link in LINKS:
            if link.kind == "reference":
                out.append(OfficialLink(
                    link.title, link.url.replace("{query}", quote_plus(query)),
                    link.publisher, link.description, link.kind,
                    link.countries, link.topics).card())
        return out[:limit]
    return []
