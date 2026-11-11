"""robots.txt handling (RFC 9309 style).

Rules are grouped per user-agent. The most specific agent token wins; if none
matches, the `*` group applies. Within a group the longest matching pattern
wins and an allow wins a tie. Unreachable or 5xx robots is a denial for every
URL on that origin, and so is an explicit 401/403.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

MAX_ROBOTS_BYTES = 512_000
CACHE_TTL_S = 24 * 60 * 60


@dataclass
class RobotsRules:
    allow_all: bool = False
    deny_all: bool = False
    rules: list[tuple[str, str]] = field(default_factory=list)  # (allow|disallow, pattern)
    crawl_delay: float | None = None
    sitemaps: list[str] = field(default_factory=list)
    source: str = "parsed"

    def can_fetch(self, path: str) -> bool:
        if self.deny_all:
            return False
        if self.allow_all:
            return True
        best_len = -1
        verdict = True
        for kind, pattern in self.rules:
            if not pattern:
                continue
            if pattern == "/":
                matched = True
            elif _pattern_regex(pattern).match(path):
                matched = True
            else:
                matched = False
            if not matched:
                continue
            specificity = len(pattern)
            if specificity > best_len or (specificity == best_len and kind == "allow"):
                best_len = specificity
                verdict = kind == "allow"
        return verdict


def _pattern_regex(pattern: str) -> re.Pattern:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    escaped = re.escape(body).replace(r"\*", ".*")
    return re.compile("^" + escaped + ("$" if anchored else ""))


def parse_robots(text: str, user_agent: str) -> RobotsRules:
    token = user_agent.split("/")[0].strip().lower()
    groups: list[dict] = []
    current_agents: list[str] = []
    current: dict | None = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if current is None or current["rules"] or current["crawl_delay"] or current["sitemaps"]:
                current = {"agents": [], "rules": [], "crawl_delay": None, "sitemaps": []}
                groups.append(current)
                current_agents = current["agents"]
            current_agents.append(value.lower())
            continue
        if current is None:
            continue
        if key in ("allow", "disallow"):
            if value:
                current["rules"].append((key, value))
        elif key == "crawl-delay":
            try:
                current["crawl_delay"] = max(0.0, float(value))
            except ValueError:
                pass
        elif key == "sitemap" and value:
            current["sitemaps"].append(value)

    exact = [g for g in groups if token and token in g["agents"]]
    chosen = exact or [g for g in groups if "*" in g["agents"]]
    if not chosen:
        return RobotsRules(allow_all=True, source="no-matching-group")
    rules: list[tuple[str, str]] = []
    delay = None
    sitemaps: list[str] = []
    for group in chosen:
        rules.extend(group["rules"])
        if delay is None and group["crawl_delay"] is not None:
            delay = group["crawl_delay"]
        sitemaps.extend(group["sitemaps"])
    return RobotsRules(rules=rules, crawl_delay=delay, sitemaps=sitemaps)


def decision_for_status(status: int, body: bytes, user_agent: str) -> RobotsRules:
    if status == 200:
        return parse_robots(body.decode("utf-8", "replace")[:MAX_ROBOTS_BYTES], user_agent)
    if status in (401, 403):
        return RobotsRules(deny_all=True, source=f"http_{status}")
    if status in (404, 410):
        return RobotsRules(allow_all=True, source=f"http_{status}_absent")
    if 500 <= status < 600:
        return RobotsRules(deny_all=True, source=f"http_{status}_fail_closed")
    return RobotsRules(deny_all=True, source=f"http_{status}_fail_closed")


class RobotsCache:
    """Origin -> RobotsRules with the 24h RFC cache recommendation."""

    def __init__(self, fetcher):
        self.fetcher = fetcher
        self._cache: dict[str, RobotsRules] = {}
        self._fetched_at: dict[str, float] = {}

    def rules(self, origin: str, user_agent: str) -> RobotsRules:
        fresh = self._fresh(origin)
        if fresh is not None:
            return fresh
        url = origin.rstrip("/") + "/robots.txt"
        result = self.fetcher.fetch(url, max_bytes=MAX_ROBOTS_BYTES)
        if result.error:
            rules = RobotsRules(deny_all=True, source=f"error:{result.error}")
        else:
            rules = decision_for_status(result.status, result.body, user_agent)
        self._cache[origin] = rules
        self._fetched_at[origin] = time.time()
        return rules

    def _fresh(self, origin: str) -> RobotsRules | None:
        rules = self._cache.get(origin)
        if rules is None:
            return None
        if time.time() - self._fetched_at.get(origin, 0) > CACHE_TTL_S:
            return None
        return rules

    def path_allowed(self, url: str, user_agent: str) -> tuple[bool, RobotsRules]:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        rules = self.rules(origin, user_agent)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        return rules.can_fetch(path), rules
