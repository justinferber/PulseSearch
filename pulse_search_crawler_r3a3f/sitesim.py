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
        self.routes[path] = route

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
               ("/events/diwali", "Diwali festival of lights")])))
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
