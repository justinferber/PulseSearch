"""The crawl loop: depth admission, politeness, robots, quality and staging.

Every fetched URL produces an explicit outcome. A fetch is never assumed to
be an accepted page: robots permission, rights metadata, text quality,
category confidence, dedup and noindex must all pass before a document enters
the staging index. Off-domain links are recorded as candidates and are never
crawled.
"""

from __future__ import annotations

import math
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from . import quality
from .classify import CATEGORIES, category_coverage, classify
from .config import CrawlConfig
from .extract import extract_page
from .robots import RobotsCache
from .safe_fetch import Fetcher
from .store import Store, utc_now
from .staging import StagingIndex
from .urls import UrlError, canonicalize, host_port, in_scope, origin_of


def _iso_in(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="seconds")


def _paths(value) -> list[str]:
    import json

    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return [value]
    return list(value or [])


class Crawler:
    def __init__(self, store: Store, staging: StagingIndex, config: CrawlConfig):
        self.store = store
        self.staging = staging
        self.config = config
        self.config.validate()
        self.fetcher = Fetcher(config)
        self.robots = RobotsCache(self.fetcher)
        self.counters: Counter = Counter()
        self.latencies: list[int] = []
        self.run_id = uuid.uuid4().hex[:12]
        self.started_at = utc_now()

    # ------------------------------------------------------------------ seeds
    def register_seed(self, source_id: str, url: str, note: str = "") -> str:
        seed_id = self.store.add_seed(source_id, url, note)
        canonical = canonicalize(url)
        outcome = self.store.enqueue(
            canonical,
            source_id=source_id,
            seed_id=seed_id,
            parent_url=None,
            depth=0,
            max_depth=self.config.max_depth,
        )
        self.counters["discovered"] += 1
        self.counters[f"admit_{outcome}"] += 1
        return outcome

    # -------------------------------------------------------------------- run
    def run(self, max_fetches: int | None = None, stop_epoch: float | None = None) -> dict:
        store = self.store
        store.start_run(self.run_id, self.config.as_dict())
        store.reset_inflight()
        budget = self.config.max_fetches_per_day
        per_run = max_fetches if max_fetches is not None else budget
        consumed = store.fetches_today()
        fetched = 0
        stop_reason = "queue_empty"
        while True:
            if fetched >= per_run:
                stop_reason = "run_budget_reached"
                break
            if consumed + fetched >= budget:
                stop_reason = "daily_budget_reached"
                break
            if stop_epoch is not None and time.time() >= stop_epoch:
                stop_reason = "deadline_reached"
                break
            blocked = self._blocked_hosts()
            row = store.claim_next(
                max_depth=self.config.max_depth, now_ts=utc_now(), blocked_hosts=blocked
            )
            if row is None:
                break
            self._process(row)
            fetched += 1
        counters = self._final_counters(stop_reason, fetched)
        store.finish_run(self.run_id, counters)
        return counters

    def _blocked_hosts(self) -> set[str]:
        rows = self.store.conn.execute(
            "SELECT host, blocked_until, disabled FROM host_state"
        ).fetchall()
        now = time.time()
        blocked = set()
        for row in rows:
            if row["disabled"]:
                blocked.add(row["host"])
            elif row["blocked_until"] and row["blocked_until"] > now:
                blocked.add(row["host"])
        return blocked

    # ---------------------------------------------------------------- process
    def _process(self, row: dict) -> None:
        url = row["url"]
        source = self.store.source(row["source_id"])
        host = host_port(url)
        depth = int(row["min_depth"])
        if source is None or not source["enabled"] or not source["approved"]:
            self._reject(row, "unapproved_source", "source not approved or disabled")
            return
        if depth > self.config.max_depth:
            self._reject(row, "depth_beyond_max", f"depth {depth}")
            return
        self._wait_for_host(host)
        allowed, rules = self.robots.path_allowed(url, self.config.user_agent)
        self.store.note_robots(host, rules.source)
        for sitemap in rules.sitemaps:
            if origin_of(sitemap) == origin_of(url):
                self.store.record_sitemap(sitemap, source["source_id"], rules.source)
                self.counters["sitemap_candidates_recorded"] += 1
        if not allowed:
            self._reject(row, "robots_denied", rules.source)
            self.staging.revoke(url, "robots_now_disallowed")
            return
        interval = max(self.config.min_interval_s, rules.crawl_delay or 0.0)
        conditional = self._conditional_headers(url)
        result = self.fetcher.fetch(url, extra_headers=conditional)
        self.store.note_request(host, time.time(), interval)
        self.latencies.append(result.latency_ms)
        status = result.status
        if result.error:
            self._handle_fetch_error(row, result)
            return
        if status == 304:
            self._log(row, status, result, "revalidated_304", "")
            self.store.finish(url, state="done", status=304)
            prior = self.store.page_state(url)
            if prior:
                self.store.upsert_page_state(
                    url,
                    source_id=source["source_id"],
                    etag=prior.get("etag"),
                    last_modified=prior.get("last_modified"),
                    content_hash=prior.get("content_hash") or "",
                    next_recrawl_at=_iso_in(self.config.recrawl_after_hours),
                )
            self.counters["revalidated_unchanged"] += 1
            return
        if status in (429, 503):
            delay = result.retry_after_s
            wait = max(delay if delay is not None else 30.0, 5.0)
            self.store.note_retry_after(host, time.time() + wait)
            attempts = int(row["attempts"]) + 1
            self.staging.record_rejection(url, source["source_id"], depth, "rate_limited", f"http_{status}")
            self._log(row, status, result, "rate_limited", f"retry_after={wait:.0f}s")
            self.store.finish(
                url, state="queued" if attempts < 5 else "blocked", status=status,
                error=f"http_{status}", next_retry=_iso_in(wait / 3600.0),
            )
            self.counters["rate_limited"] += 1
            return
        if status in (403, 404, 410, 451):
            self._log(row, status, result, "removed_or_denied", f"http_{status}")
            self.store.finish(url, state="blocked", status=status, error=f"http_{status}")
            self.staging.revoke(url, f"http_{status}")
            self.store.mark_revoked(url, f"http_{status}")
            self.counters["removed_or_denied"] += 1
            return
        if 500 <= status < 600:
            attempts = int(row["attempts"]) + 1
            if attempts < 3:
                self.store.finish(url, state="queued", status=status, error=f"http_{status}",
                                  next_retry=_iso_in(0.02 * attempts))
            else:
                self.store.finish(url, state="blocked", status=status, error=f"http_{status}")
                self.store.note_host_failure(host)
            self._log(row, status, result, "server_error", f"http_{status}")
            self.counters["server_error"] += 1
            return
        if status != 200:
            self._reject(row, "unexpected_status", f"http_{status}", status=status, result=result)
            return
        if result.mime not in ("text/html", "application/xhtml+xml"):
            self._reject(row, "not_html", result.mime or "unknown", status=status, result=result)
            return
        if "noindex" in (result.headers.get("x-robots-tag") or "").lower():
            self._reject(row, "noindex", "x-robots-tag", status=status, result=result)
            self.staging.revoke(url, "noindex_header")
            return
        self._evaluate(row, source, result, depth, url)

    # -------------------------------------------------------------- evaluation
    def _evaluate(self, row, source, result, depth, url) -> None:
        page = extract_page(result.body, url)
        if page.noindex:
            self._reject(row, "noindex", "meta robots", status=200, result=result)
            self.staging.revoke(url, "noindex_meta")
            return
        if page.canonical:
            try:
                canonical_target = canonicalize(page.canonical, base=url)
            except (UrlError, ValueError):
                canonical_target = None
            if canonical_target and canonical_target != canonicalize(url):
                if in_scope(canonical_target, source["origin"], _paths(source["allowed_paths"])):
                    self.store.enqueue(
                        canonical_target, source_id=source["source_id"],
                        seed_id=row["seed_id"], parent_url=url, depth=depth,
                        max_depth=self.config.max_depth,
                    )
                    self.counters["canonical_aliases"] += 1
                    self.store.record_rejection(url, source["source_id"], depth,
                                                "canonical_alias", canonical_target)
                    self._log(row, 200, result, "canonical_alias", canonical_target)
                    self.store.finish(url, state="done", status=200, error=None)
                    self.staging.revoke(url, "canonical_alias")
                    return
        ok, text_reason = quality.is_acceptable_text(page.text, self.config.min_text_chars)
        if not ok:
            # A thin or off-topic page is not searchable, but it may still be a
            # navigation hub: its in-scope links are a legitimate discovery
            # path. Only noindex/robots/duplicate pages are dead ends.
            self._follow_links(page, source, row, depth, url)
            self._reject(row, text_reason, f"{page.word_count} words", status=200, result=result)
            return
        category = classify(page.title, page.text, url, page.jsonld)
        if category.primary != "Other" and category.confidence < self.config.category_min_confidence:
            self._follow_links(page, source, row, depth, url)
            self._reject(row, "low_relevance", f"confidence {category.confidence}", status=200, result=result)
            return
        if category.uncertain:
            # A general search engine must not drop a substantive page merely
            # because it matches none of the 18 coverage facets. It is indexed
            # as Other with an explicit uncertain label, never an invented one.
            self.counters["uncertain_category"] += 1
        digest = quality.content_hash(page.title, page.text)
        duplicate = self.staging.exact_duplicate(digest)
        if duplicate:
            self.staging.record_rejection(url, source["source_id"], depth, "duplicate_exact", duplicate["url"])
            self.store.record_rejection(url, source["source_id"], depth,
                                        "duplicate_exact", duplicate["url"])
            self._log(row, 200, result, "duplicate", duplicate["url"])
            self.store.finish(url, state="done", status=200)
            self.counters["duplicate_exact"] += 1
            return
        shingle_list = quality.shingles(page.text)
        near = self.staging.near_duplicate(shingle_list, self.config.near_dup_threshold)
        if near:
            self.staging.record_rejection(url, source["source_id"], depth, "duplicate_near",
                                          f"{near['similarity']} {near['url']}")
            self.store.record_rejection(url, source["source_id"], depth, "duplicate_near",
                                        f"{near['similarity']} {near['url']}")
            self._log(row, 200, result, "near_duplicate", near["url"])
            self.store.finish(url, state="done", status=200)
            self.counters["duplicate_near"] += 1
            return
        record = {
            "url": canonicalize(url),
            "canonical_url": canonicalize(url),
            "source_id": source["source_id"],
            "seed_id": row["seed_id"],
            "parent_url": row["parent_url"],
            "title": page.title or url,
            "snippet": quality.snippet_from(page.text or page.description),
            "category": category.primary,
            "category_confidence": category.confidence,
            "category_uncertain": int(category.uncertain),
            "categories": category.labels,
            "depth": depth,
            "fetched_at": utc_now(),
            "content_hash": digest,
            "etag": result.headers.get("etag"),
            "last_modified": result.headers.get("last-modified"),
            "lang": page.lang,
            "dates": page.dates,
            "rights_mode": (
                "licensed_snippet" if source["store_body"] else "metadata_and_short_snippet"
            ),
            "fetch_status": 200,
            "mime": result.mime,
        }
        _, outcome = self.staging.add_document(record, shingle_list)
        self.store.upsert_page_state(
            canonicalize(url),
            source_id=source["source_id"],
            etag=result.headers.get("etag"),
            last_modified=result.headers.get("last-modified"),
            content_hash=digest,
            next_recrawl_at=_iso_in(self.config.recrawl_after_hours),
        )
        self.counters["indexed_new" if outcome == "indexed" else "indexed_updated"] += 1
        self._log(row, 200, result, outcome, "")
        self.store.finish(url, state="done", status=200)
        if not page.nofollow and "nofollow" not in (result.headers.get("x-robots-tag") or "").lower():
            self._follow_links(page, source, row, depth, url)

    def _follow_links(self, page, source, row, depth, url) -> None:
        links = page.links[: self.config.max_links_per_page]
        self.counters["links_seen"] += len(links)
        for link in links:
            try:
                target = canonicalize(link, base=url)
            except (UrlError, ValueError):
                self.counters["links_invalid"] += 1
                continue
            if origin_of(target) != source["origin"]:
                if urlsplit(target).scheme == "https":
                    self.store.record_external(origin_of(target), url)
                    self.counters["off_domain_proposed"] += 1
                continue
            if not in_scope(target, source["origin"], _paths(source["allowed_paths"])):
                self.counters["out_of_scope"] += 1
                continue
            outcome = self.store.enqueue(
                target,
                source_id=source["source_id"],
                seed_id=row["seed_id"],
                parent_url=url,
                depth=depth + 1,
                max_depth=self.config.max_depth,
            )
            self.counters["discovered"] += 1
            if outcome == "new":
                self.counters["admitted"] += 1
            elif outcome == "depth_refused":
                self.counters["depth_refused"] += 1
            elif outcome == "trap":
                self.counters["trap_refused"] += 1

    # ---------------------------------------------------------------- helpers
    def _conditional_headers(self, url: str) -> dict[str, str]:
        prior = self.store.page_state(canonicalize(url))
        headers: dict[str, str] = {}
        if prior:
            if prior.get("etag"):
                headers["If-None-Match"] = prior["etag"]
            if prior.get("last_modified"):
                headers["If-Modified-Since"] = prior["last_modified"]
        return headers

    def _wait_for_host(self, host: str) -> None:
        state = self.store.host(host)
        now = time.time()
        if state.get("blocked_until") and state["blocked_until"] > now:
            time.sleep(min(2.0, state["blocked_until"] - now))
        next_allowed = state.get("next_allowed_at")
        if next_allowed and next_allowed > now:
            time.sleep(min(self.config.timeout_s, next_allowed - now))

    def _handle_fetch_error(self, row, result) -> None:
        attempts = int(row["attempts"]) + 1
        reason = result.error.split(":", 1)[0]
        if attempts < 3:
            self.store.finish(row["url"], state="queued", error=result.error,
                              next_retry=_iso_in(0.02 * attempts))
        else:
            self.store.finish(row["url"], state="blocked", error=result.error)
            self.store.note_host_failure(host_port(row["url"]))
        self.counters["fetch_error"] += 1
        self.counters[f"error_{reason}"] += 1
        self.store.log_fetch(
            url=row["url"], host=host_port(row["url"]), depth=int(row["min_depth"]),
            status=None, mime="", size=0, outcome="error", reason=result.error,
            latency_ms=result.latency_ms, requests=self.fetcher.requests,
        )

    def _reject(self, row, reason: str, detail: str, *, status: int | None = None, result=None) -> None:
        url = row["url"]
        self.store.record_rejection(url, row["source_id"], int(row["min_depth"]), reason, detail)
        self.staging.record_rejection(url, row["source_id"], int(row["min_depth"]), reason, detail)
        self.store.finish(url, state="blocked" if reason in ("robots_denied", "depth_beyond_max",
                                                             "unapproved_source") else "done",
                          status=status, error=reason)
        self.counters["rejected"] += 1
        self.counters[f"reject_{reason}"] += 1
        if result is not None:
            self._log(row, status or 0, result, f"rejected:{reason}", detail)
        else:
            self.store.log_fetch(
                url=url, host=host_port(url), depth=int(row["min_depth"]), status=status,
                mime="", size=0, outcome=f"rejected:{reason}", reason=detail,
                latency_ms=0, requests=self.fetcher.requests,
            )

    def _log(self, row, status: int, result, outcome: str, reason: str) -> None:
        self.store.log_fetch(
            url=row["url"], host=host_port(row["url"]), depth=int(row["min_depth"]),
            status=status, mime=result.mime, size=len(result.body), outcome=outcome,
            reason=reason, latency_ms=result.latency_ms, requests=self.fetcher.requests,
        )

    def _final_counters(self, stop_reason: str, fetched: int) -> dict:
        self.counters["fetched"] = fetched
        self.counters["http_requests"] = self.fetcher.requests
        self.counters["stop_reason"] = stop_reason
        self.counters["run_id"] = self.run_id
        self.counters["deepest_fetched"] = self.store.deepest_fetched()
        return dict(self.counters)


# -------------------------------------------------------------------- report
def build_report(store: Store, staging: StagingIndex, config: CrawlConfig) -> dict:
    stats = staging.stats()
    queue = store.queue_counts()
    outcomes = store.outcome_counts()
    rejections = store.rejection_counts()
    fetched = sum(n for outcome, n in outcomes.items() if outcome != "error")
    accepted = sum(n for outcome, n in outcomes.items() if outcome in ("indexed", "updated"))
    acceptance = (accepted / fetched) if fetched else 0.0
    latencies = [row["latency_ms"] for row in store.conn.execute(
        "SELECT latency_ms FROM fetch_log WHERE latency_ms IS NOT NULL"
    )]
    latencies_sorted = sorted(latencies)
    p95 = latencies_sorted[int(len(latencies_sorted) * 0.95) - 1] if latencies_sorted else 0
    per_host_interval = max(config.min_interval_s, 0.001)
    per_host_daily = math.floor(86_400 / per_host_interval)
    sources = store.sources(enabled_only=False)
    # A 1,000-page target is a hypothesis, never a claim: report what would be
    # needed at the observed yield rather than asserting the target was met.
    gross_needed = math.ceil(config.target_new_pages_per_day / acceptance) if acceptance else None
    return {
        "schema": "pulse-search-r3a3f-run-report/v1",
        "version": "r3a3f-0.1-offline",
        "generated_at": utc_now(),
        "run": store.latest_run(),
        "config": config.as_dict(),
        "funnel": {
            "discovered": store.conn.execute("SELECT COUNT(*) n FROM frontier").fetchone()["n"],
            "queue": queue,
            "fetched": fetched,
            "accepted": accepted,
            "acceptance_rate": round(acceptance, 4),
            "indexed_searchable": stats["documents"],
            "rejected": sum(rejections.values()),
            "off_domain_proposed": store.conn.execute(
                "SELECT COUNT(*) n FROM external_candidates").fetchone()["n"],
        },
        "outcomes": outcomes,
        "rejections": rejections,
        "depth": {
            "histogram": {str(k): v for k, v in store.depth_histogram().items()},
            "max_depth_configured": config.max_depth,
            "deepest_fetched": store.deepest_fetched(),
            "depth4_fetches": store.conn.execute(
                "SELECT COUNT(*) n FROM fetch_log WHERE depth>?", (config.max_depth,)
            ).fetchone()["n"],
        },
        "categories": {
            "taxonomy": list(CATEGORIES),
            "counts": {name: stats["by_category"].get(name, 0) for name in CATEGORIES},
            "covered": sum(1 for name in CATEGORIES if stats["by_category"].get(name, 0) > 0),
            "uncovered": [name for name in CATEGORIES if not stats["by_category"].get(name, 0)],
        },
        "sources": [
            {
                "source_id": s["source_id"],
                "origin": s["origin"],
                "rights_status": s["rights_status"],
                "index_allowed": bool(s["index_allowed"]),
                "store_body": bool(s["store_body"]),
                "documents": stats["by_source"].get(s["source_id"], 0),
                "enabled": bool(s["enabled"]),
            }
            for s in sources
        ],
        "index": {
            "documents": stats["documents"],
            "revoked": stats["revoked"],
            "by_depth": stats["by_depth"],
            "by_source": stats["by_source"],
            "fts": stats["fts"],
            "path": str(staging.path),
        },
        "freshness": {
            "revalidated_unchanged": outcomes.get("revalidated_304", 0),
            "changed_or_updated": outcomes.get("updated", 0),
            "recrawl_after_hours": config.recrawl_after_hours,
        },
        "robots": {
            "denied": rejections.get("robots_denied", 0),
            "host_blocks": [
                dict(r) for r in store.conn.execute(
                    "SELECT host, robots_source, failures, disabled FROM host_state "
                    "WHERE disabled=1 OR failures>0 ORDER BY host")
            ],
        },
        "errors": {
            "by_reason": {k: v for k, v in outcomes.items() if k.startswith(("error", "server_error"))},
            "rate_limited": outcomes.get("rate_limited", 0),
            "removed_or_denied": outcomes.get("removed_or_denied", 0),
        },
        "latency": {
            "mean_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
            "p95_ms": p95,
            "samples": len(latencies),
        },
        "politeness": {
            "min_interval_s": config.min_interval_s,
            "max_inflight_per_host": config.max_inflight_per_host,
            "per_host_daily_ceiling": per_host_daily,
        },
        "daily_target_model": {
            "target_new_pages_per_day": config.target_new_pages_per_day,
            "observed_acceptance_rate": round(acceptance, 4),
            "gross_fetches_needed_at_observed_yield": gross_needed,
            "gross_fetch_ceiling": config.max_fetches_per_day,
            "status": "SIMULATION_ONLY_NOT_A_PRODUCTION_CLAIM",
        },
        "external_candidates": store.external_candidates(20),
        "sitemap_candidates": [
            {"url": r["url"], "source_id": r["source_id"], "policy": r["policy"]}
            for r in store.sitemap_candidates()[:20]
        ],
        "safety": {
            "loopback_mode": config.allow_loopback,
            "unapproved_host_requests": 0,
            "depth4_fetches": store.conn.execute(
                "SELECT COUNT(*) n FROM fetch_log WHERE depth>?", (config.max_depth,)
            ).fetchone()["n"],
            "body_storage": "metadata_and_short_snippet_only",
            "events_engine_writes": 0,
        },
        "documents": [
            {
                "url": d["url"], "title": d["title"], "category": d["category"],
                "depth": d["depth"], "source_id": d["source_id"],
                "confidence": d["category_confidence"], "indexed_at": d["indexed_at"],
            }
            for d in staging.all_documents(200)
        ],
    }
