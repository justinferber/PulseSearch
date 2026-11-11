"""Prioritise genuinely discovered external source *candidates* for owner review.

The existing crawler records off-origin links without fetching them. This
module groups those references, identifies likely useful source families and
makes an auditable, review-only queue. It never changes source admission.
"""
from __future__ import annotations

import ipaddress
import math
import re
from collections import defaultdict
from urllib.parse import urlsplit

from .search import classify_query

KEYWORDS = {
    "events": ("events", "event", "calendar", "festival", "pride", "csd",
               "fireworks", "feuerwerk", "weihnachtsmarkt", "concert", "konzert",
               "live music", "parade", "procession", "stadfest", "stadtfest"),
    "ticketing_guides": ("tickets", "ticket", "booking", "how-to", "guide",
                         "help", "faq", "support", "tickets kaufen", "vorverkauf"),
    "venues": ("venue", "arena", "stadium", "theatre", "theater", "hall", "museum"),
    "travel": ("transport", "rail", "train", "bahn", "bus", "visit", "tourism"),
    "general": ("about", "information", "research", "encyclopedia", "wiki"),
}


def is_reviewable_origin(origin: str) -> bool:
    """Avoid unsafe/noisy origins entering a proposed source queue."""
    try:
        u = urlsplit(origin)
        if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
            return False
        if not u.hostname.isascii() or u.hostname.endswith((".local", ".internal", ".invalid", ".test")):
            return False
        if u.port not in (None, 80, 443):
            return False
        try:
            ip = ipaddress.ip_address(u.hostname)
        except ValueError:
            return True  # DNS safety remains the network fetcher's responsibility
        return ip.is_global
    except ValueError:
        return False


def source_families(origin: str, referrer: str) -> list[str]:
    p = urlsplit(origin)
    # Host and observed link context are *weak* signals, never rights evidence.
    text = (p.hostname or "").replace("-", " ").replace(".", " ") + " " + (
        urlsplit(referrer).path.replace("-", " ").replace("/", " ")
    )
    text = text.lower()
    families = []
    for name, keys in KEYWORDS.items():
        if any(re.search(r"\b" + re.escape(k) + r"\b", text) for k in keys):
            families.append(name)
    return families or ["unclassified"]


def rank_external_candidates(rows: list[dict], limit: int = 100) -> list[dict]:
    grouped = defaultdict(lambda: {"referrers": set(), "sightings": 0, "families": set()})
    for row in rows:
        origin = str(row.get("origin") or "")
        referrer = str(row.get("referrer_url") or "")
        if not is_reviewable_origin(origin):
            continue
        item = grouped[origin]
        item["referrers"].add(referrer)
        item["sightings"] += max(0, int(row.get("sightings", 1)))
        item["families"].update(source_families(origin, referrer))
    result = []
    for origin, item in grouped.items():
        families = sorted(item["families"] - {"unclassified"}) or ["unclassified"]
        n = len(item["referrers"])
        result.append({
            "origin": origin,
            "status": "CANDIDATE_ONLY_NO_FETCH_PERMISSION",
            "source_families": families,
            "observed_referrer_count": n,
            "sightings": item["sightings"],
            "example_referrers": sorted(item["referrers"])[:4],
            # Visibility in the graph and topical promise are useful for triage.
            # No algorithm can turn this into source trust or legal admission.
            "review_priority": round(math.log1p(item["sightings"]) + 0.25 * n +
                                     (0.75 if families != ["unclassified"] else 0), 3),
            "requires": ["owner_admission", "robots_review", "source_rights_review",
                         "verified_exact_seeds", "takedown_contact"],
        })
    result.sort(key=lambda x: (-x["review_priority"], x["origin"]))
    return result[:max(0, min(limit, 500))]


def candidates_from_store(store, limit: int = 100) -> list[dict]:
    """Read only; no requests, mutations or source approvals."""
    return rank_external_candidates(store.external_candidates(limit=5000), limit)
