"""HTML understanding: title, main text, links, canonical and structured data."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin

SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "nav", "footer", "aside", "form"}
DATE_PATTERN = re.compile(
    r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{4})\b"
)
ISO_DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


@dataclass
class ExtractedPage:
    title: str = ""
    text: str = ""
    links: list[str] = field(default_factory=list)
    canonical: str | None = None
    lang: str = ""
    noindex: bool = False
    nofollow: bool = False
    headings: list[str] = field(default_factory=list)
    jsonld: list[dict] = field(default_factory=list)
    description: str = ""
    dates: list[str] = field(default_factory=list)
    link_texts: dict[str, str] = field(default_factory=dict)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.headings: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.link_texts: dict[str, str] = {}
        self._anchor_href: str | None = None
        self._anchor_buffer: list[str] = []
        self.canonical: str | None = None
        self.lang = ""
        self.noindex = False
        self.nofollow = False
        self.description = ""
        self.jsonld_raw: list[str] = []
        self._skip = 0
        self._in_title = 0
        self._in_h = 0
        self._in_jsonld = 0
        self._json_buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and a.get("lang"):
            self.lang = a["lang"][:20]
        if tag in SKIP_TAGS:
            self._skip += 1
        if tag == "title":
            self._in_title += 1
        if tag in ("h1", "h2"):
            self._in_h += 1
        if tag == "meta":
            name = a.get("name", "").lower()
            if name in ("robots", "pulsesearchbot", "googlebot"):
                rules = a.get("content", "").lower()
                if "noindex" in rules or "none" in rules:
                    self.noindex = True
                if "nofollow" in rules or "none" in rules:
                    self.nofollow = True
            if name in ("description", "og:description") and a.get("content"):
                self.description = a["content"][:500]
        if tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canonical = a.get("href") or None
        if tag == "script" and "ld+json" in a.get("type", "").lower():
            self._in_jsonld += 1
            self._json_buffer = []
        if tag == "a" and a.get("href"):
            self.links.append((a["href"], a.get("rel", "").lower()))
            self._anchor_href = a["href"]
            self._anchor_buffer = []

    def handle_endtag(self, tag):
        if tag == "a" and self._anchor_href:
            anchor = " ".join(" ".join(self._anchor_buffer).split())[:160]
            if anchor:
                self.link_texts[self._anchor_href] = anchor
            self._anchor_href = None
            self._anchor_buffer = []
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        if tag == "title":
            self._in_title = max(0, self._in_title - 1)
        if tag in ("h1", "h2"):
            self._in_h = max(0, self._in_h - 1)
        if tag == "script" and self._in_jsonld:
            self._in_jsonld -= 1
            raw = "".join(self._json_buffer).strip()
            if raw:
                self.jsonld_raw.append(raw)
            self._json_buffer = []

    def handle_data(self, data):
        if self._in_jsonld:
            self._json_buffer.append(data)
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._anchor_href:
            self._anchor_buffer.append(text)
        if self._in_title:
            self.title_parts.append(text)
        if self._in_h:
            self.headings.append(text[:200])
        if not self._skip:
            self.text_parts.append(text)


def extract_page(raw: bytes, base_url: str, charset: str = "utf-8") -> ExtractedPage:
    try:
        markup = raw.decode(charset, "replace")
    except LookupError:
        markup = raw.decode("utf-8", "replace")
    parser = _Parser()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:  # malformed markup must still yield whatever parsed
        pass
    text = " ".join(parser.text_parts)
    title = " ".join(parser.title_parts).strip() or (parser.headings[0] if parser.headings else "")
    links: list[str] = []
    link_texts: dict[str, str] = {}
    for href, rel in parser.links:
        if "nofollow" in rel:
            continue
        if href.startswith(("mailto:", "tel:", "javascript:", "data:", "#")):
            continue
        absolute = urljoin(base_url, href).split("#", 1)[0]
        if absolute.startswith(("http://", "https://")):
            links.append(absolute)
            anchor = parser.link_texts.get(href)
            if anchor and absolute not in link_texts:
                link_texts[absolute] = anchor
    jsonld = []
    for blob in parser.jsonld_raw:
        try:
            import json

            value = json.loads(blob)
        except ValueError:
            continue
        jsonld.append(value if isinstance(value, dict) else {"@graph": value})
    dates = DATE_PATTERN.findall(text)[:5] + ISO_DATE_PATTERN.findall(text)[:5]
    return ExtractedPage(
        title=title[:300],
        text=text[:200_000],
        links=links,
        canonical=parser.canonical,
        lang=parser.lang,
        noindex=parser.noindex,
        nofollow=parser.nofollow,
        headings=parser.headings[:40],
        jsonld=jsonld[:10],
        description=parser.description,
        dates=dates,
        link_texts=link_texts,
    )
