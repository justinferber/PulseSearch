"""Official-service directory: useful navigation when live data is unavailable.

These are reviewed public entry points, not crawler admissions and not a
licence to scrape. A weather card says "see the current forecast there"; it is
never presented as an observation. No paid API is required for any of this.
"""

from __future__ import annotations

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

    def card(self) -> dict:
        data = asdict(self)
        data["countries"] = list(self.countries)
        data["topics"] = list(self.topics)
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
    OfficialLink("Eventim Germany", "https://www.eventim.de/", "Eventim",
                 "Authorised ticketing agency; check the event page for the official seller.",
                 "tickets", ("DE",), ("tickets", "konzert", "concert")),
    OfficialLink("Berlin.de events calendar", "https://www.berlin.de/events/", "Berlin.de",
                 "City events calendar with organiser and venue links.",
                 "events", ("DE",), ("events", "berlin", "concert", "festival")),
    OfficialLink("Mercedes-Benz Arena Berlin", "https://www.mercedes-benz-arena.de/",
                 "Mercedes-Benz Arena", "Venue programme, official box office and travel information.",
                 "venue", ("DE",), ("concert", "venue", "berlin")),
    OfficialLink("Columbiahalle Berlin", "https://www.columbiahalle.de/", "Columbiahalle",
                 "Venue programme and official ticket information.",
                 "venue", ("DE",), ("concert", "venue", "berlin")),
    OfficialLink("Huxley's Neue Welt", "https://www.huxleys-neue-welt.de/", "Huxley's",
                 "Venue programme, box office and accessibility information.",
                 "venue", ("DE",), ("concert", "venue", "berlin")),
    OfficialLink("Verti Music Hall", "https://www.verti-music-hall.de/", "Verti Music Hall",
                 "Venue programme and official ticketing links.",
                 "venue", ("DE",), ("concert", "venue", "berlin")),
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
    OfficialLink("Wikipedia", "https://en.wikipedia.org/wiki/Special:Search?search={query}",
                 "Wikimedia", "General reference; verify time-sensitive facts against a primary source.",
                 "reference", (), ("general", "reference", "factual")),
    OfficialLink("GOV.UK", "https://www.gov.uk/search/all?keywords={query}", "GOV.UK",
                 "Official UK government guidance and public services.",
                 "reference", ("GB",), ("refund", "consumer", "guidance")),
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
    OfficialLink("Visit London events", "https://www.visitlondon.com/things-to-do/events",
                 "Visit London", "Official London events listings and visitor guidance.",
                 "events", ("GB",), ("events", "london", "festival")),
    OfficialLink("European Festivals Association", "https://www.efa-aef.eu/", "EFA",
                 "Directory of European festival organisations and members.",
                 "events", (), ("festival", "music", "europe")),
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


def links_for(kind: str, query: str, city: str | None = None,
              country: str | None = None, limit: int = 8) -> list[dict]:
    """Return reviewed official entry points for an intent.

    ``weather`` always returns national services so a forecast question is
    useful even with no live adapter; the caller must label it as navigation.
    """
    q = (query or "").lower()
    topics = {w for w in q.replace("?", " ").replace(",", " ").split() if w}
    kinds = {kind}
    if kind in ("weather", "forecast"):
        kinds |= {"weather"}
        has_de = "berlin" in q or "german" in q or "deutsch" in q or "münchen" in q or "munchen" in q
        has_gb = "london" in q or "manchester" in q or "uk" in q or "britain" in q
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
        c = "DE" if ("berlin" in q or "german" in q or "konzert" in q) else \
            "GB" if ("london" in q or "manchester" in q or "uk" in q) else \
            "FR" if "paris" in q else ""
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
        booking = [l for l in LINKS if l.kind in ("tickets", "venue")
                   and (not c or not l.countries or c in l.countries)] if is_ticket else []
        calendars = [l for l in LINKS if l.kind == "events" and
                     (not c or not l.countries or c in l.countries)]
        chosen = []
        for link in discovery + booking + calendars:
            if link not in chosen:
                chosen.append(link)
        if "refund" in q or "return" in q or "cancel" in q:
            refund = [l for l in LINKS if
                      (l.kind == "reference" or l.publisher == "CAA") and
                      ("GOV.UK" == l.publisher or "CAA" == l.publisher)]
            chosen = refund + chosen
        return _cards(chosen, query, limit)
    if kind in ("transport", "travel"):
        c = "DE" if "berlin" in q else "GB" if "london" in q else ""
        return _cards([l for l in LINKS if l.kind == "transport"
                       and (not c or not l.countries or c in l.countries)], query, limit)
    if kind in ("flights", "buy_flights"):
        return _cards([l for l in LINKS if l.kind == "flights"], query, limit)
    if kind in ("sports", "shopping"):
        chosen = [l for l in LINKS if l.kind == kind]
        if kind == "shopping":
            c = "DE" if "berlin" in q else "GB" if "london" in q else ""
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
