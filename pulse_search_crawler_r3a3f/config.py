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
    # Fail-closed operation: an unreviewed source may neither be fetched nor
    # indexed. These exist so the intent is explicit at every call site.
    require_source_admission: bool = True
    require_index_approval: bool = True
    # 404 is a lifecycle, not a permanent verdict: a seasonal listing can
    # appear later. Rechecks are bounded and long-TTL; 410/451 stay permanent.
    max_rechecks: int = 2
    recheck_after_hours: float = 24.0
    recheck_listing_hours: float = 168.0
    # Fairness guard: no single host may consume more than this share of the
    # per-run fetch budget while another approved host still has work.
    max_host_share: float = 0.7
    rights_default: str = "metadata_and_short_snippet"
    # Hard pilot limits. They are persisted per UTC day in the store, so a
    # crash and restart cannot reset the counter and spend the allowance
    # twice. The offline simulator opts into larger numbers explicitly.
    pilot_http_attempts_per_day: int = 300
    pilot_accepted_documents_per_day: int = 20
    pilot_run_minutes_max: float = 30.0

    def validate(self) -> None:
        if not 0 <= self.max_depth <= 3:
            raise ConfigError("max_depth must be between 0 and 3")
        if self.max_fetches_per_day <= 0:
            raise ConfigError("max_fetches_per_day must be positive")
        if self.max_inflight_per_host != 1:
            raise ConfigError("only one in-flight request per host is approved")
        if not 0.0 <= self.near_dup_threshold <= 1.0:
            raise ConfigError("near_dup_threshold must be within 0..1")
        if not 0.1 <= self.max_host_share <= 1.0:
            raise ConfigError("max_host_share must be within 0.1..1.0")
        if self.max_rechecks < 0 or self.max_rechecks > 10:
            raise ConfigError("max_rechecks must be within 0..10")
        if self.recheck_after_hours <= 0 or self.recheck_listing_hours <= 0:
            raise ConfigError("recheck intervals must be positive")
        if self.focus_month is not None and not 1 <= self.focus_month <= 12:
            raise ConfigError("focus_month must be 1..12")
        if self.pilot_http_attempts_per_day <= 0:
            raise ConfigError("pilot_http_attempts_per_day must be positive")
        if self.pilot_accepted_documents_per_day <= 0:
            raise ConfigError("pilot_accepted_documents_per_day must be positive")
        if self.pilot_run_minutes_max <= 0:
            raise ConfigError("pilot_run_minutes_max must be positive")
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
