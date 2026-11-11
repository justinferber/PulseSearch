"""Crawl configuration.

Defaults follow the approved architecture: max three link hops, one in-flight
request per host, at least three seconds between requests to a host, and a
5,000 fetch/day ceiling. Loopback access exists only for the offline
simulator and must be opted into explicitly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


class ConfigError(RuntimeError):
    """Raised when a configuration could lead to an unsafe live crawl."""


@dataclass
class CrawlConfig:
    user_agent: str = (
        "PulseSearchFB2/0.1 (+https://github.com/justinferber/PulseSearch; "
        "research crawler; contact=owner)"
    )
    max_depth: int = 3
    max_fetches_per_day: int = 5000
    target_new_pages_per_day: int = 1000
    min_interval_s: float = 3.0
    max_inflight_per_host: int = 1
    timeout_s: float = 10.0
    max_bytes: int = 2_000_000
    max_redirects: int = 5
    max_links_per_page: int = 200
    min_text_chars: int = 250
    near_dup_threshold: float = 0.90
    category_min_confidence: float = 0.18
    recrawl_after_hours: int = 24
    allow_loopback: bool = False
    loopback_hosts: tuple[str, ...] = ()
    sitemap_policy: str = "candidate_only"
    discovery_probes: bool = True
    focus_month: int | None = None
    rights_default: str = "metadata_and_short_snippet"

    def validate(self) -> None:
        if not 0 <= self.max_depth <= 3:
            raise ConfigError("max_depth must be between 0 and 3")
        if self.max_fetches_per_day <= 0:
            raise ConfigError("max_fetches_per_day must be positive")
        if self.max_inflight_per_host != 1:
            raise ConfigError("only one in-flight request per host is approved")
        if not 0.0 <= self.near_dup_threshold <= 1.0:
            raise ConfigError("near_dup_threshold must be within 0..1")
        if self.focus_month is not None and not 1 <= self.focus_month <= 12:
            raise ConfigError("focus_month must be 1..12")
        if self.sitemap_policy not in ("candidate_only", "deny"):
            raise ConfigError("sitemaps may only be recorded as candidates")
        if not self.allow_loopback and self.min_interval_s < 3.0:
            raise ConfigError("live crawling requires at least 3s between host requests")
        if self.allow_loopback and not self.loopback_hosts:
            raise ConfigError("loopback crawling requires an explicit host allowlist")

    def permits_host(self, hostport: str, is_loopback: bool) -> bool:
        if is_loopback:
            return self.allow_loopback and hostport in self.loopback_hosts
        return True

    def as_dict(self) -> dict:
        data = asdict(self)
        data["loopback_hosts"] = list(self.loopback_hosts)
        return data
