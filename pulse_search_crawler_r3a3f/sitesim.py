"""Deterministic synthetic website network for offline crawl testing.

Six loopback origins, 120+ pages, all 18 categories, plus the traps the gates
require: cycles, a fourth-hop sentinel, duplicate and near-duplicate bodies,
calendar pagination, robots denials and a 5xx robots host, 403/404, 429 and
503 with Retry-After, redirect chains, noindex, malformed markup, sitemaps,
cross-domain links and SSRF lures. Nothing here touches a real website.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .classify import CATEGORIES


def page_html(title: str, text: str, links: list[str] | None = None, *,
              robots: str | None = None, canonical: str | None = None,
              jsonld: dict | None = None, lang: str = "en") -> bytes:
    head = [f"<!doctype html><html lang='{lang}'><head><meta charset='utf-8'>",
            f"<title>{title}</title>"]
    if robots:
        head.append(f"<meta name='robots' content='{robots}'>")
    if canonical:
        head.append(f"<link rel='canonical' href='{canonical}'>")
    if jsonld:
        import json

        head.append(f"<script type='application/ld+json'>{json.dumps(jsonld)}</script>")
    head.append("</head><body><h1>" + title + "</h1>")
    head.append("<nav><a href='/'>Home</a></nav>")
    detail = (" Visitors can find practical details for this listing here, including dates, "
              "opening times, accessibility, transport and contact information. The organisers "
              "publish programme updates and any changes to the schedule on this page.")
    head.append("<main><p>" + text + detail + "</p>")
    for link in links or []:
        if isinstance(link, (tuple, list)):
            href, anchor = link
        else:
            href, anchor = link, "link"
        head.append(f"<a href='{href}'>{anchor}</a>")
    head.append("</main><footer>Pulse Search synthetic fixture</footer></body></html>")
    return "".join(head).encode("utf-8")


# Category-specific fixture copy keeps classification honest without inventing
# a human judgement about a real page.
CATEGORY_TEXT: dict[str, str] = {
    "Conference": "Annual conference with congress keynote speakers, delegates and a plenary summit programme.",
    "Festival": "Community festival with music, food stalls and celebration programming for all ages.",
    "Fundraiser": "Charity fundraiser and fundraising gala evening with donations supporting the appeal.",
    "Lecture": "Public lecture with a guest speaker, followed by a panel discussion and questions.",
    "Market": "Weekly farmers market with craft fair stalls, local vendors and seasonal produce.",
    "Meal": "Community meal and shared dinner with a tasting menu prepared by volunteers.",
    "Social Mixer": "Networking mixer and social evening for neighbours and new members.",
    "Tour": "Guided walking tour of the district with a heritage trail and open house stops.",
    "Volunteering": "Volunteering morning: tree planting, litter pick and food bank support.",
    "Workshop": "Hands-on workshop and skills training session for beginners.",
    "Other": "General information page about local services and opening times.",
    "Horticulture & Flower Shows": "Annual flower show and horticulture exhibition with garden show displays.",
    "Music & Performance": "Live music concert with orchestra, choir and a theatre performance.",
    "Sport & Fitness": "Community 10k race and half marathon, plus fitness and yoga sessions.",
    "Parades & Processions": "Lantern parade and carnival procession through the city centre.",
    "Pride & Community": "Pride and LGBTQ community programme with a diversity and inclusion focus.",
    "Exhibitions & Trade Shows": "Museum exhibition and trade show expo with gallery showcases.",
    "Arts & Culture": "Arts and culture season: film, literature, poetry and heritage crafts.",
}


@dataclass
class Route:
    status: int = 200
    body: bytes = b""
    mime: str = "text/html; charset=utf-8"
    headers: dict[str, str] = field(default_factory=dict)
    etag: str | None = None

    def with_etag(self, tag: str) -> "Route":
        self.etag = tag
        return self


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "PulseSim/1.0"

    def log_message(self, *args):  # silence test output
        return

    def do_GET(self):
        server: "RouteServer" = self.server
        server.record(self.path)
        route = server.routes.get(self.path.split("?")[0] if "?" not in server.routes else self.path)
        if route is None:
            route = server.routes.get(self.path)
        if route is None:
            route = Route(status=404, body=b"<html><body>not found</body></html>")
        if route.etag and self.headers.get("If-None-Match") == route.etag:
            self.send_response(304)
            self.send_header("ETag", route.etag)
            for key, value in route.headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(route.status)
        self.send_header("Content-Type", route.mime)
        if route.etag:
            self.send_header("ETag", route.etag)
        for key, value in route.headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(route.body)))
        self.end_headers()
        if route.status not in (204, 304):
            self.wfile.write(route.body)


class RouteServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.routes: dict[str, Route] = {}
        self.hits: list[str] = []
        self._lock = threading.Lock()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def record(self, path: str) -> None:
        with self._lock:
            self.hits.append(path)

    def set(self, path: str, route: Route) -> None:
        # Canonicalisation drops a trailing slash, so a route registered as
        # /about/ must also answer /about, exactly as a real server would.
        self.routes[path] = route
        if path != "/" and path.endswith("/"):
            self.routes[path.rstrip("/")] = route

    def hits_for(self, prefix: str) -> int:
        with self._lock:
            return sum(1 for hit in self.hits if hit.startswith(prefix))

    def start(self) -> "RouteServer":
        thread = threading.Thread(target=self.serve_forever, daemon=True)
        thread.start()
        return self


@dataclass
class SyntheticNetwork:
    servers: dict[str, RouteServer]
    seeds: dict[str, list[str]]

    def stop(self) -> None:
        for server in self.servers.values():
            server.shutdown()
            server.server_close()

    def hits(self) -> dict[str, int]:
        return {name: len(server.hits) for name, server in self.servers.items()}

    def enable_seasonal_listing(self) -> None:
        """Publish a listing that was 404 before its season.

        A Christmas-market overview genuinely does not exist in July. The
        crawler must recheck the 404 rather than treat the URL as gone forever.
        """
        self.servers["berlin-events"].set("/events/christmas", Route(body=page_html(
            "Christmas markets in Berlin 2026",
            "Christmas markets and Advent markets with Gluhwein, crafts and a winter "
            "market programme for the whole family.",
            links=[("/events/weihnachtsmarkt", "Weihnachtsmarkt stalls")])))

    def hits_forbidden(self) -> dict[str, int]:
        return {
            "private": self.servers["berlin-events"].hits_for("/private"),
            "admin": self.servers["berlin-events"].hits_for("/admin")
            + self.servers["london-venue"].hits_for("/admin"),
            "ssrf_metadata": sum(server.hits_for("/latest/meta-data") for server in self.servers.values()),
        }

    def depth4_hits(self) -> int:
        return sum(server.hits_for("/deep/4") + server.hits_for("/deep/5")
                   for server in self.servers.values())


def build_network() -> SyntheticNetwork:
    """Create six origins with the required pages and traps."""
    names = ["berlin-events", "london-venue", "community-hub", "noindex-site",
             "robots-broken", "rate-limited"]
    servers = {name: RouteServer().start() for name in names}
    berlin, london, community, noindex, broken, limited = (servers[n] for n in names)

    # robots.txt per origin
    berlin.set("/robots.txt", Route(
        body=b"User-agent: *\nDisallow: /private\nAllow: /\nCrawl-delay: 0\n"
             b"Sitemap: " + f"{berlin.base}/sitemap.xml\n".encode(),
        mime="text/plain; charset=utf-8"))
    london.set("/robots.txt", Route(
        body=b"User-agent: PulseSearchFB2\nDisallow: /admin\nAllow: /events\n",
        mime="text/plain; charset=utf-8"))
    community.set("/robots.txt", Route(
        body=b"User-agent: *\nDisallow:\n", mime="text/plain; charset=utf-8"))
    noindex.set("/robots.txt", Route(body=b"User-agent: *\nAllow: /\n",
                                     mime="text/plain; charset=utf-8"))
    broken.set("/robots.txt", Route(status=503, body=b"robots unavailable",
                                    mime="text/plain; charset=utf-8"))
    limited.set("/robots.txt", Route(body=b"User-agent: *\nAllow: /\n",
                                     mime="text/plain; charset=utf-8"))

    # ---- berlin-events: the main 18-category site -------------------------
    category_slugs = {
        "Conference": "conference", "Festival": "festival", "Fundraiser": "fundraiser",
        "Lecture": "lecture", "Market": "market", "Meal": "meal",
        "Social Mixer": "social-mixer", "Tour": "tour", "Volunteering": "volunteering",
        "Workshop": "workshop", "Other": "other",
        "Horticulture & Flower Shows": "flower-show", "Music & Performance": "music",
        "Sport & Fitness": "sport", "Parades & Processions": "parade",
        "Pride & Community": "pride", "Exhibitions & Trade Shows": "exhibition",
        "Arts & Culture": "arts",
    }
    hub_links = []
    for category, slug in category_slugs.items():
        path = f"/events/{slug}"
        hub_links.append(path)
        text = CATEGORY_TEXT[category] + " " + (
            "This page explains what visitors can expect, how to take part and "
            "who organises the programme in Berlin, with dates, accessibility "
            "notes, transport advice and contact details for the organisers.")
        berlin.set(path, Route(body=page_html(
            f"{category} in Berlin", text,
            links=["/events/" + slug + "/details", "/venue/hall", "/deep/0"],
        )).with_etag(f"etag-{slug}"))
        berlin.set(f"/events/{slug}/details", Route(body=page_html(
            f"{category} Berlin details and programme",
            text + " Full programme, accessibility notes and travel information are listed here.",
            links=["/events/" + slug, "/venue/hall", "/deep/1"],
        )).with_etag(f"etag-{slug}-details"))
    # Named cultural pages that must remain discoverable.
    berlin.set("/events/diwali", Route(body=page_html(
        "Diwali celebration Berlin 2026",
        "Diwali festival of lights with lanterns, music and community celebration in Berlin. "
        "The Diwali programme includes cultural performances and a shared meal.",
        links=["/events/festival", "/events/diwali/programme"],
        jsonld={"@type": "Event", "name": "Diwali Berlin"})).with_etag("etag-diwali"))
    berlin.set("/events/diwali/programme", Route(body=page_html(
        "Diwali programme and timings",
        "Diwali programme details: lamp lighting, Bhangra performance and a community dinner "
        "in the festival hall.")))
    berlin.set("/events/csd-berlin", Route(body=page_html(
        "CSD Berlin pride 2026",
        "CSD Berlin Pride parade and community festival with LGBTQ diversity programming, "
        "a procession through the city and a street festival.",
        links=["/events/pride", "/events/csd-berlin/route"])).with_etag("etag-csd"))
    berlin.set("/events/csd-berlin/route", Route(body=page_html(
        "CSD Berlin route and accessibility",
        "The CSD Berlin pride procession route starts at the station and ends with a "
        "community stage programme for Pride week.")))
    berlin.set("/events/pride-berlin", Route(body=page_html(
        "Pride Berlin community events",
        "Pride Berlin events include a queer community mixer, an arts exhibition and a "
        "Pride & Community panel on inclusion.")))
    berlin.set("/events/stadtfest-berlin", Route(body=page_html(
        "Stadtfest Berlin 2026",
        "Stadtfest Berlin street festival with market stalls, live music and a parade "
        "through the neighbourhood.",
        links=["/events/festival", "/events/stadtfest-berlin/stage"])).with_etag("etag-stadtfest"))
    berlin.set("/events/stadtfest-berlin/stage", Route(body=page_html(
        "Stadtfest Berlin stage programme",
        "Stadtfest Berlin stage programme with live music, choir performances and a "
        "community festival atmosphere.")))
    # The festival and pride hubs link to the named cultural editions, so
    # depth-1 discovery reaches them from the approved seed.
    berlin.set("/events/festival", Route(body=page_html(
        "Festival in Berlin", CATEGORY_TEXT["Festival"] +
        " This page explains what visitors can expect and who organises the programme in Berlin.",
        links=["/events/diwali", "/events/stadtfest-berlin", "/events/festival/details",
               "/venue/hall"])))
    berlin.set("/events/pride", Route(body=page_html(
        "Pride in Berlin", CATEGORY_TEXT["Pride & Community"] +
        " This page explains the programme and who organises it in Berlin.",
        links=["/events/csd-berlin", "/events/pride-berlin", "/events/pride/details"])))
    berlin.set("/events/market", Route(body=page_html(
        "Market in Berlin", CATEGORY_TEXT["Market"] +
        " This page lists traders, dates and accessibility notes for the market.",
        links=["/dup/a", "/dup/b", "/events/market/details"])))
    duplicate_body = (
        "The community hall hosts conferences, markets and workshops throughout the year. "
        "Rooms are accessible, with a kitchen for community meals and a stage for concerts. "
        "This listing is duplicated deliberately to prove exact-dedup behaviour.")
    berlin.set("/dup/a", Route(body=page_html("Duplicate listing", duplicate_body)))
    berlin.set("/dup/b", Route(body=page_html("Duplicate listing", duplicate_body)))

    # Venue hub, used for duplicate/near-duplicate and redirect tests.
    venue_text = ("The community hall hosts conferences, markets and workshops throughout the year. "
                  "Rooms are accessible, with a kitchen for community meals and a stage for concerts.")
    berlin.set("/venue/hall", Route(body=page_html(
        "Community hall venue", venue_text, links=["/venue/hall/rooms", "/index.html"])))
    berlin.set("/venue/hall/rooms", Route(body=page_html(
        "Community hall rooms",
        venue_text + " The upstairs room is used for lectures and the garden for flower shows.")))
    berlin.set("/index.html", Route(body=page_html(
        "Community hall venue", venue_text, links=["/venue/hall"])))  # duplicate body
    guide_links = []
    for index in range(1, 13):
        path = f"/guides/{index}"
        guide_links.append(path)
        topic = CATEGORIES[index % len(CATEGORIES)]
        berlin.set(path, Route(body=page_html(
            f"Berlin guide {index}: {topic}",
            CATEGORY_TEXT[topic] + f" Guide {index} also explains booking, access and travel "
            "for visitors, with practical notes for first-time attendees.",
            links=["/events/festival", "/venue/hall"])))
    # A listing hub with intent-bearing anchors, as a real "what's on" page.
    berlin.set("/events/weihnachtsmarkt", Route(body=page_html(
        "Weihnachtsmarkt Berlin 2026",
        "Der Weihnachtsmarkt am Rathaus öffnet mit Adventsmarkt-Ständen, Glühwein und "
        "einem winterlichen Marktprogramm für die ganze Familie.",
        links=[("/events/market", "Christmas market stalls")])))
    berlin.set("/events/christmas", Route(
        status=404, body=b"<html><body>not found out of season</body></html>"))
    berlin.set("/events/open-air-festival", Route(body=page_html(
        "Open air music festival 2026",
        "Open air music festival with a lineup of live acts, a festival stage and "
        "an evening concert series in the park.",
        links=[("/events/music", "Live music programme")])))
    berlin.set("/events/karneval-umzug", Route(body=page_html(
        "Karneval Umzug Berlin",
        "Karneval parade with an Umzug through the streets, costumes, marching groups "
        "and a street festival afterwards.",
        links=[("/events/parade", "Parade route")])))
    berlin.set("/whats-on", Route(body=page_html(
        "What's on in Berlin",
        "Whats on guide and events calendar listing festivals, markets, concerts and "
        "community celebrations across the city.",
        links=[("/events/weihnachtsmarkt", "Christmas markets 2026"),
               ("/events/open-air-festival", "Open air music festival lineup"),
               ("/events/karneval-umzug", "Carnival parade Umzug"),
               ("/events/pride-berlin", "Pride Berlin events"),
               ("/events/stadtfest-berlin", "Stadtfest street festival"),
               ("/events/diwali", "Diwali festival of lights"),
               ("/redirect/start", "Redirecting listing"),
               ("/redirect/private", "Members-only listing"),
               ("/redirect/offsite", "Partner listing")])))
    berlin.set("/", Route(body=page_html(
        "Berlin events guide", "A guide to conferences, festivals and community events in Berlin.",
        links=hub_links + guide_links + [("/whats-on", "What's on in Berlin"),
                                        "/robots.txt-page", "/sitemap.xml"])))
    # Traps and safety fixtures.
    berlin.set("/deep/0", Route(body=page_html(
        "Depth zero hub", "Depth zero page about the conference venue and market hall programme.",
        links=["/deep/1"])))
    for level in range(1, 6):
        berlin.set(f"/deep/{level}", Route(body=page_html(
            f"Depth {level} page",
            f"Depth {level} page about festival, market and workshop information. "
            f"This page must not be fetched beyond the third hop.",
            links=[f"/deep/{level + 1}", "/deep/0"])))
    berlin.set("/calendar?page=1000", Route(body=page_html(
        "Calendar page one thousand", "Infinite calendar pagination trap with festival listings.")))
    berlin.set("/private/secret", Route(body=page_html(
        "Private page", "Private internal page that robots.txt disallows for all agents.")))
    berlin.set("/admin/panel", Route(body=page_html(
        "Admin panel", "Admin panel for managing festival listings and market bookings.")))
    berlin.set("/noindex-page", Route(body=page_html(
        "Hidden page", "Noindex page about a festival that must never be searchable.",
        robots="noindex")))
    berlin.set("/header-noindex", Route(body=page_html(
        "Header hidden", "Page with an X-Robots-Tag noindex that must not be indexed."),
        headers={"X-Robots-Tag": "noindex"}))
    berlin.set("/gone", Route(status=410, body=b"<html><body>gone</body></html>"))
    berlin.set("/missing", Route(status=404, body=b"<html><body>missing</body></html>"))
    berlin.set("/malformed", Route(body=b"<html><head><title>Malformed market page</title>"
                                        b"<body><p>Unclosed tags market festival workshop "
                                        b"community meal programme with enough words to pass "
                                        b"the text gate. <a href='/events/market'>market</a>"))
    berlin.set("/sitemap.xml", Route(
        body=b"<?xml version='1.0'?><urlset><url><loc>" + f"{berlin.base}/private/secret".encode()
             + b"</loc></url></urlset>", mime="application/xml"))
    berlin.set("/redirect/start", Route(status=301, headers={"Location": "/redirect/step"}))
    # Redirects that must never be followed: a robots-disallowed path on the
    # same origin, and a public host that was never admitted.
    berlin.set("/redirect/private", Route(status=302, headers={"Location": "/private/secret"}))
    berlin.set("/redirect/offsite", Route(
        status=302, headers={"Location": "https://outside.invalid/events"}))
    berlin.set("/redirect/step", Route(status=302, headers={"Location": "/redirect/deep"}))
    berlin.set("/redirect/deep", Route(status=307, headers={"Location": "/redirect/final"}))
    berlin.set("/redirect/final", Route(status=308, headers={"Location": "/events/workshop"}))
    berlin.set("/ssrf/metadata", Route(body=page_html(
        "Metadata lure", "Page linking to a cloud metadata service that must never be fetched.",
        links=["http://169.254.169.254/latest/meta-data/"])))
    berlin.set("/ssrf/loopback", Route(body=page_html(
        "Loopback lure", "Page linking to a loopback admin port that is not approved.",
        links=[f"http://127.0.0.1:{berlin.server_address[1]}/private/secret"])))
    berlin.set("/cross-domain", Route(body=page_html(
        "Cross domain page", "Festival page linking to a venue on another approved origin.",
        links=[f"{london.base}/events/exhibition", f"{community.base}/volunteer"])))

    # ---- london-venue ------------------------------------------------------
    london.set("/events", Route(body=page_html(
        "London venue events", "Exhibition, lecture and tour programme at the riverside venue.",
        links=["/events/exhibition", "/events/lecture", "/events/tour"])))
    london.set("/events/exhibition", Route(body=page_html(
        "Riverside exhibition", CATEGORY_TEXT["Exhibitions & Trade Shows"] +
        " The gallery exhibition runs for six weeks with a trade show showcase.")))
    london.set("/events/lecture", Route(body=page_html(
        "Riverside public lecture", CATEGORY_TEXT["Lecture"] +
        " The lecture is free and takes place in the auditorium.")))
    london.set("/events/tour", Route(body=page_html(
        "Riverside guided tour", CATEGORY_TEXT["Tour"] + " Tours run hourly from the entrance.")))
    london.set("/admin", Route(status=403, body=b"<html><body>forbidden</body></html>"))

    # ---- community-hub -----------------------------------------------------
    community.set("/volunteer", Route(body=page_html(
        "Community volunteering", CATEGORY_TEXT["Volunteering"] +
        " Join the Saturday volunteering group at the community garden.")))
    community.set("/meal", Route(body=page_html(
        "Community meal", CATEGORY_TEXT["Meal"] + " Everyone is welcome at the shared table.")))
    community.set("/mixer", Route(body=page_html(
        "Neighbourhood mixer", CATEGORY_TEXT["Social Mixer"] + " New residents are especially welcome.")))

    # ---- noindex-site ------------------------------------------------------
    noindex.set("/hidden", Route(body=page_html(
        "Noindex venue", "Noindex page with festival text that must not be indexed at all.",
        robots="noindex")))

    # ---- robots-broken (503 robots -> fail closed) -------------------------
    broken.set("/festival", Route(body=page_html(
        "Broken robots festival", CATEGORY_TEXT["Festival"] + " Must not be fetched.")))
    broken.set("/private", Route(body=page_html("Broken robots private", "Must not be fetched.")))

    # ---- rate-limited (429 then 503 then success) --------------------------
    limited.set("/events/market", Route(status=429, body=b"slow down",
                                        headers={"Retry-After": "0"}))
    limited.set("/events/workshop", Route(status=503, body=b"unavailable",
                                          headers={"Retry-After": "0"}))
    limited.set("/events/festival", Route(body=page_html(
        "Rate limited festival", CATEGORY_TEXT["Festival"] + " Eventually served politely.")))

    seeds = {
        "berlin-events": [berlin.base + "/"],
        "london-venue": [london.base + "/events"],
        "community-hub": [community.base + "/volunteer"],
        "noindex-site": [noindex.base + "/hidden"],
        "robots-broken": [broken.base + "/festival"],
        "rate-limited": [limited.base + "/events/festival",
                         limited.base + "/events/market",
                         limited.base + "/events/workshop"],
    }
    return SyntheticNetwork(servers=servers, seeds=seeds)


def build_three_source_network() -> SyntheticNetwork:
    """Offline fixtures for the three owner-selected candidates.

    These are synthetic pages on loopback, not copies of the real sites. Each
    origin mirrors the *shape* the F0 audits found (listing hub, edition
    pages, history/programme, restrictive paths) plus the traps the gates must
    survive: robots denials, off-origin redirects, duplicate syndication, a
    cancelled edition, old and new editions side by side and depth-4 sentinels.
    Nothing here is fetched from a third party.
    """
    names = ("city-hall", "london-parade", "lord-mayors-show")
    servers = {name: RouteServer().start() for name in names}
    city, parade, show = (servers[name] for name in names)

    # ---- City Hall: /events only, robots allows the section ----------------
    city.set("/robots.txt", Route(
        body=b"User-agent: *\nDisallow: /search\nDisallow: /admin\nAllow: /\n"
             b"Crawl-delay: 3\nSitemap: " + f"{city.base}/sitemap.xml\n".encode(),
        mime="text/plain; charset=utf-8"))
    city_events = [
        ("diwali-city-hall", "Diwali at City Hall", "Festival",
         "Diwali festival of lights with music, lanterns and a community celebration."),
        ("london-parade-viewing", "London Parade viewing at City Hall", "Parades & Processions",
         "Watch the London Parade procession pass City Hall on New Year's Day."),
        ("lord-mayors-show-screening", "Lord Mayor's Show screening", "Arts & Culture",
         "Live screening of the Lord Mayor's Show civic procession and programme."),
        ("open-house", "City Hall open house", "Tour",
         "Guided tour of City Hall with a heritage trail and open house access."),
    ]
    city.set("/events", Route(body=page_html(
        "City Hall events listing",
        "London City Hall events listing: festivals, parades, tours and civic "
        "celebrations across the city, with dates, access notes and booking details.",
        links=[("/events/" + slug, title) for slug, title, _, _ in city_events]
        + [("/whats-on", "What's on"), ("/search?q=events", "Search events")])))
    for slug, title, category, text in city_events:
        city.set(f"/events/{slug}", Route(body=page_html(
            title, CATEGORY_TEXT[category] + " " + text,
            links=[(f"/events/{slug}/programme", "Programme"), ("/events", "All events"),
                   ("https://londonparade.com/", "Organiser website")])))
        city.set(f"/events/{slug}/programme", Route(body=page_html(
            f"{title} programme and times",
            text + " The programme lists times, access information, transport advice "
            "and the contact details for the organising team.",
            links=[(f"/events/{slug}/programme/access", "Access details"),
                   ("/events", "All events")])))
        city.set(f"/events/{slug}/programme/access", Route(body=page_html(
            f"{title} access and travel",
            "Access, step-free routes, transport and contact information for visitors "
            "attending this City Hall event.",
            links=[(f"/events/{slug}/programme/access/map", "Map"),
                   ("/events", "All events")])))
        city.set(f"/events/{slug}/programme/access/map", Route(body=page_html(
            "Depth four map", "Fourth-hop page that must never be fetched.")))
    city.set("/whats-on", Route(body=page_html(
        "What's on in London", "Unverified path that is outside the approved /events scope.")))
    city.set("/search", Route(body=page_html(
        "Search", "Search page disallowed by robots.txt.")))
    city.set("/admin", Route(body=page_html("Admin", "Admin page disallowed by robots.txt.")))

    # ---- London Parade: public pages, forms excluded by robots -------------
    parade.set("/robots.txt", Route(
        body=b"# Content-Signal: search=yes, ai-train=no, use=reference\n"
             b"User-agent: *\nAllow: /\nCrawl-delay: 10\n"
             b"Disallow: /shop/\nDisallow: /takepart/\nDisallow: /account/\n"
             b"Disallow: /admin/\n",
        mime="text/plain; charset=utf-8"))
    parade_2027 = "London Parade 2027 starts at 1pm on 1 January 2027."
    parade_2026 = "The 2026 London Parade took place on 1 January 2026 for its 40th edition."
    parade.set("/", Route(body=page_html(
        "London Parade",
        "London Parade: the New Year's Day parade through central London with bands, "
        "floats and a concert series. " + parade_2027,
        links=[("/parade-location-timing/", "When and where"), ("/about/", "About"),
               ("/londonparade-participants/", "Participants"),
               ("/festivals/concerts/", "Concert series"),
               ("/news-archive", "News archive"),
               ("/news/london-parade-2027-celebrate-new-years-day-the-london-way/", "2027 news"),
               ("/news/london-parade-2026-review/", "2026 review"),
               ("/redirect/route", "Route"),
               ("/shop/", "Shop"), ("/takepart/", "Take part"), ("/admin/", "Admin")])))
    parade.set("/parade-location-timing/", Route(body=page_html(
        "London Parade 2027 — when and where",
        parade_2027 + " The route runs through central London with viewing points "
        "along the way; grandstand tickets are sold separately.",
        links=[("/about/", "About"), ("/news-archive", "News archive")])))
    parade.set("/about/", Route(body=page_html(
        "About London Parade",
        "London Parade is an annual New Year's Day parade and festival series in "
        "central London, organised by Destination Events Ltd.",
        links=[("/londonparade-participants/", "Participants"),
               ("/festivals/concerts/", "Concert series")])))
    parade.set("/londonparade-participants/", Route(body=page_html(
        "London Parade participants",
        "Participating bands, marching groups and performance teams for the 2027 "
        "parade, with public programme information only.",
        links=[("/news/london-parade-2027-celebrate-new-years-day-the-london-way/", "2027 news"),
               ("/takepart/", "Take part")])))
    parade.set("/festivals/concerts/", Route(body=page_html(
        "London Parade concert series",
        CATEGORY_TEXT["Music & Performance"] + " Concerts run in the days before the parade.",
        links=[("/about/", "About")])))
    parade.set("/news-archive", Route(body=page_html(
        "London Parade news archive",
        "Archive of London Parade announcements across recent editions.",
        links=[("/news/london-parade-2027-celebrate-new-years-day-the-london-way/", "2027"),
               ("/news/london-parade-2026-review/", "2026 review"),
               ("/news/route-2026/", "2026 route"),
               ("/news/2021-parade-cancelled/", "2021 cancellation"),
               ("/news/route-syndicated/", "Route syndicated copy")])))
    parade.set("/news/london-parade-2027-celebrate-new-years-day-the-london-way/",
               Route(body=page_html(
                   "London Parade 2027 — celebrate New Year's Day the London way",
                   parade_2027 + " Three bands have been announced for the 2027 parade, "
                   "with the programme and route published on the official pages.",
                   links=[("/news/2027-bands/", "2027 bands announcement"),
                          ("/parade-location-timing/", "When and where")])))
    parade.set("/news/2027-bands/", Route(body=page_html(
        "Three bands announced for London Parade 2027",
        CATEGORY_TEXT["Music & Performance"] + " The bands join the 2027 parade lineup.",
        links=[("/news/2027-bands/lineup/", "Full lineup"), ("/news-archive", "Archive")])))
    parade.set("/news/2027-bands/lineup/", Route(body=page_html(
        "London Parade 2027 full lineup",
        "Full lineup of bands and performance groups for the 2027 parade, with times "
        "and route positions.",
        links=[("/news/2027-bands/lineup/times/", "Times")])))
    parade.set("/news/2027-bands/lineup/times/", Route(body=page_html(
        "Depth four times", "Fourth-hop page that must never be fetched.")))
    parade.set("/news/london-parade-2026-review/", Route(body=page_html(
        "London Parade 2026 review",
        parade_2026 + " The 40th edition featured bands and floats from across London.",
        links=[("/news-archive", "Archive")])))
    route_body = ("The parade route for the 2026 edition started in central London and "
                  "finished near the river, with public viewing points along the way.")
    parade.set("/news/route-2026/", Route(body=page_html(
        "London Parade 2026 route", route_body, links=[("/news-archive", "Archive")])))
    parade.set("/news/route-syndicated/", Route(body=page_html(
        "London Parade 2026 route", route_body, links=[("/news-archive", "Archive")])))
    parade.set("/news/2021-parade-cancelled/", Route(body=page_html(
        "London Parade 2021 cancelled",
        "The 2021 London Parade was cancelled; organisers published the decision and "
        "the planned programme for that edition was not held.",
        links=[("/news-archive", "Archive")])))
    parade.set("/redirect/route", Route(status=301,
                                        headers={"Location": "/parade-location-timing/"}))
    parade.set("/shop/", Route(body=page_html("Shop", "Shop page disallowed by robots.txt.")))
    parade.set("/takepart/", Route(body=page_html(
        "Take part", "Participant application form; must never be fetched or indexed.")))
    parade.set("/account/", Route(body=page_html(
        "Account", "Account portal; must never be fetched.")))
    parade.set("/admin/", Route(body=page_html("Admin", "Admin page disallowed by robots.txt.")))

    # ---- Lord Mayor's Show: history, programme, procession, restrictions ---
    # The real host serves no robots.txt (404). The fixture is deliberately
    # stricter: it denies the restrictive terms page and the book page so the
    # offline run proves those refusals instead of silently fetching them.
    show.set("/robots.txt", Route(
        body=b"User-agent: *\nAllow: /\nDisallow: /terms-of-use/\nDisallow: /book/\n",
        mime="text/plain; charset=utf-8"))
    show_2026 = "The 2026 Show sets off from Mansion House on Saturday 14 November 2026 at 11am."
    show.set("/", Route(body=page_html(
        "The Lord Mayor's Show",
        "The Lord Mayor's Show is the oldest civic procession in the world. " + show_2026,
        links=[("/history/", "History"), ("/programme/", "Programme"),
               ("/route/", "Procession route"), ("/lord-mayors-procession/", "Procession"),
               ("/practicalities/where-to-go/", "Where to go"),
               ("/closures/", "Road closures"),
               ("/terms-of-use/", "Terms of use"), ("/book/", "Book")])))
    show.set("/history/", Route(body=page_html(
        "History of the Lord Mayor's Show",
        CATEGORY_TEXT["Arts & Culture"] + " The Show dates back to the early 13th century.",
        links=[("/history/obstacles/", "Calamities"),
               ("/history/dates-and-routes/", "Dates and routes"),
               ("/history/ww1/", "Wartime shows")])))
    show.set("/history/obstacles/", Route(body=page_html(
        "Calamities and obstructions",
        "The Show has been cancelled only twice in 200 years, despite war and weather.",
        links=[("/history/", "History"), ("/history/ww1/", "Wartime shows")])))
    show.set("/history/ww1/", Route(body=page_html(
        "The wartime shows",
        CATEGORY_TEXT["Arts & Culture"] + " Wartime editions continued the civic tradition.",
        links=[("/history/dates-and-routes/", "Dates and routes")])))
    show.set("/history/dates-and-routes/", Route(body=page_html(
        "Dates and routes through history",
        "The 2025 Show was held on 8 November 2025. " + show_2026 +
        " Earlier editions followed the same processional route through the City.",
        links=[("/history/", "History")])))
    programme_body = (CATEGORY_TEXT["Music & Performance"] +
                      " The Show programme lists the procession order, bands, floats and "
                      "performance times for the day.")
    show.set("/programme/", Route(body=page_html(
        "Lord Mayor's Show programme", programme_body,
        links=[("/programme/timetable/", "Timetable"), ("/route/", "Route"),
               ("/programme/copy/", "Programme copy")])))
    show.set("/programme/timetable/", Route(body=page_html(
        "Show day timetable",
        "Timetable for Show day: procession, flypast, programme and road reopening.",
        links=[("/programme/", "Programme")])))
    show.set("/programme/copy/", Route(body=page_html(
        "Lord Mayor's Show programme", programme_body,
        links=[("/programme/", "Programme")])))
    show.set("/route/", Route(status=302, headers={
        "Location": "https://procession.lordmayorsshow.london/"}))
    show.set("/lord-mayors-procession/", Route(body=page_html(
        "The Lord Mayor's Procession",
        CATEGORY_TEXT["Parades & Processions"] + " The civic procession fills the City.",
        links=[("/route/", "Route"), ("/history/", "History")])))
    show.set("/practicalities/where-to-go/", Route(body=page_html(
        "Where to watch the Show",
        CATEGORY_TEXT["Tour"] + " Suggested viewing points and guided walks.",
        links=[("/practicalities/access/", "Access"), ("/closures/", "Closures")])))
    show.set("/practicalities/access/", Route(body=page_html(
        "Access at the Show",
        "Accessible viewing, step-free routes and assistance for disabled visitors.",
        links=[("/practicalities/where-to-go/", "Where to go")])))
    show.set("/closures/", Route(body=page_html(
        "Road closures on Show day",
        "Almost the whole City is closed on Show day, with buses diverted and parking "
        "suspended from the Friday afternoon.",
        links=[("/practicalities/where-to-go/", "Where to go")])))
    show.set("/terms-of-use/", Route(body=page_html(
        "Terms of use", "Restrictive terms page that must never be fetched.")))
    show.set("/book/", Route(body=page_html(
        "Book", "Book page disallowed by robots.txt.")))

    seeds = {
        "city-hall": [city.base + "/events"],
        "london-parade": [parade.base + "/"],
        "lord-mayors-show": [show.base + "/"],
    }
    return SyntheticNetwork(servers=servers, seeds=seeds)
