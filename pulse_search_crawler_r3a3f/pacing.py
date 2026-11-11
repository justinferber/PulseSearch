"""Per-host pacing shared by robots, redirects and content requests.

The defect this replaces: `sleep(min(timeout, remaining))` returned early
whenever a host's next slot was further away than the socket timeout, and
robots.txt requests did not go through the same schedule at all. Here every
network attempt on a host — robots, content and each redirect hop — must pass
through `wait()` before it is issued and `record()` afterwards, so the
minimum interval, a published Crawl-delay and a full Retry-After all apply to
one shared timeline.

Clock and sleep are injectable so tests can assert exact waits without
spending wall-clock time.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class PaceDecision:
    host: str
    waited_s: float
    next_allowed_s: float
    blocked_until_s: float | None

    @property
    def deferred(self) -> bool:
        return self.waited_s > 0


class HostPacer:
    def __init__(self, store, clock=time.time, sleep=time.sleep):
        self.store = store
        self.clock = clock
        self.sleep = sleep
        self.total_waited_s = 0.0
        self.waits: list[dict] = []

    def wait(self, host: str, interval_s: float) -> PaceDecision:
        """Block until this host may be contacted again, for the full duration."""
        state = self.store.host(host)
        now = self.clock()
        next_allowed = float(state.get("next_allowed_at") or 0.0)
        blocked_until = float(state.get("blocked_until") or 0.0)
        target = max(next_allowed, blocked_until)
        waited = 0.0
        if target > now:
            # Deliberately uncapped: a 10-minute Retry-After means wait
            # ten minutes, or let the caller defer the URL instead.
            waited = target - now
            self.sleep(waited)
            self.total_waited_s += waited
            self.waits.append({"host": host, "waited_s": round(waited, 3)})
        return PaceDecision(
            host=host,
            waited_s=round(waited, 3),
            next_allowed_s=self.clock() + interval_s,
            blocked_until_s=blocked_until or None,
        )

    def record(self, host: str, interval_s: float, retry_after_s: float | None = None) -> PaceDecision:
        """Record an issued request. Every network attempt must call this."""
        now = self.clock()
        self.store.note_request(host, now, interval_s)
        if retry_after_s:
            self.store.note_retry_after(host, now + max(0.0, retry_after_s))
        return PaceDecision(host=host, waited_s=0.0, next_allowed_s=now + interval_s,
                            blocked_until_s=(now + retry_after_s) if retry_after_s else None)

    def record_retry_after(self, host: str, retry_after_s: float) -> float:
        """Block the host for the published Retry-After, in full."""
        until = self.clock() + max(0.0, retry_after_s)
        self.store.note_retry_after(host, until)
        return until

    @staticmethod
    def interval_for(config_interval: float, crawl_delay: float | None) -> float:
        return max(float(config_interval), float(crawl_delay or 0.0))
