"""Run the full offline R3-A3F demonstration and write immutable evidence.

Starts the synthetic six-origin network on loopback, admits each origin as a
reviewed source, crawls to depth 3, then exercises restart recovery, a
conditional recrawl and source revocation. No third-party host is contacted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_crawler_r3a3f.classify import CATEGORIES  # noqa: E402
from pulse_search_crawler_r3a3f.cli import AdmissionError, load_sources  # noqa: E402
from pulse_search_crawler_r3a3f.config import CrawlConfig  # noqa: E402
from pulse_search_crawler_r3a3f.crawler import Crawler, build_report  # noqa: E402
from pulse_search_crawler_r3a3f.sitesim import (  # noqa: E402
    Route, RouteServer, build_network, page_html)
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402
from pulse_search_crawler_r3a3f.store import Store, utc_now  # noqa: E402

FROZEN_REPLAY_SHA = "bf0bee88909a537d10e7e7090c7f64fc8929981a862c06d36226ac801d3d2577"
OWNER_INDEX = Path(
    "C:/Users/justi/Desktop/pulseunity/ChatGPTCode/"
    "Pulse_Search_R2P27C_Run_gURzKuV2/live/expanded_live_100_research_index.sqlite"
)
OWNER_INDEX_SHA = "bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "docs/evidence/r3a3f_offline_run.json"))
    parser.add_argument("--data", default=str(ROOT / "data/r3a3f_offline"))
    parser.add_argument("--max-fetches", type=int, default=400)
    args = parser.parse_args()

    data = Path(args.data)
    if data.exists():
        try:
            shutil.rmtree(data)
        except PermissionError:
            # A read-only dashboard can hold the sqlite file open on Windows.
            candidate = data.with_name(data.name + "_run")
            index = 2
            while candidate.exists():
                candidate = data.with_name(f"{data.name}_run{index}")
                index += 1
            data = candidate
            print(f"note: previous data dir is in use; writing to {data}", flush=True)
    data.mkdir(parents=True, exist_ok=True)

    owner_sha_before = sha256_file(OWNER_INDEX) if OWNER_INDEX.exists() else None
    frozen_sha = sha256_file(ROOT / "docs/evidence/r3a3d_frozen54_replay.json")

    network = build_network()
    # A public origin that is never admitted. A redirect to it must be refused
    # even though the page is readable: that host was never reviewed.
    outside = RouteServer().start()
    outside.set("/robots.txt", Route(body=b"User-agent: *\nAllow: /\n",
                                     mime="text/plain; charset=utf-8"))
    outside.set("/events", Route(body=page_html(
        "Unadmitted events", "Public events page on a host that was never admitted.")))
    network.servers["berlin-events"].set(
        "/redirect/offsite",
        Route(status=302, headers={"Location": outside.base + "/events"}))
    store = Store(data / "crawl.sqlite")
    staging = StagingIndex(data / "staging.sqlite")
    config = CrawlConfig(
        allow_loopback=True,
        min_interval_s=0.0,
        loopback_hosts=tuple(server.base.replace("http://", "") for server in network.servers.values()),
        max_depth=3,
        max_fetches_per_day=5000,
    )
    try:
        for name, server in network.servers.items():
            store.add_source(
                source_id=name,
                origin=server.base,
                allowed_paths=["/"],
                rights_status="SYNTHETIC_FIXTURE_NOT_A_REAL_PUBLISHER",
                index_allowed=True,
                store_body=False,
                approved=True,
                probe_policy=["/whats-on", "/events/christmas"] if name == "berlin-events" else [],
                probe_budget_per_run=2 if name == "berlin-events" else 0,
                notes="offline simulator source; no third-party content",
            )
            for seed in network.seeds[name]:
                store.add_seed(name, seed, note="offline demo seed")

        crawler = Crawler(store, staging, config)
        for seed in store.seeds():
            crawler.register_seed(seed["source_id"], seed["url"])
        first = crawler.run(max_fetches=args.max_fetches)

        # Restart recovery: a crash leaves one row 'fetching'; a fresh process
        # must reset it, keep depth history and continue without re-crawling.
        interrupted = store.conn.execute(
            "SELECT url FROM frontier WHERE state='done' LIMIT 1").fetchone()
        if interrupted:
            store.conn.execute("UPDATE frontier SET state='fetching' WHERE url=?",
                               (interrupted["url"],))
            store.conn.commit()
        crawler2 = Crawler(store, staging, config)
        before_queue = store.queue_counts()
        second = crawler2.run(max_fetches=50)
        after_queue = store.queue_counts()
        interrupted_after = (store.conn.execute(
            "SELECT state FROM frontier WHERE url=?", (interrupted["url"],)).fetchone()["state"]
            if interrupted else None)

        # Admission is a reviewed decision: an unreviewed source record must
        # stay fetch-disabled and index-disabled by default.
        unreviewed = store.add_source(
            source_id="unreviewed-example", origin="https://unreviewed.example",
            allowed_paths=["/"], rights_status="NOT_ASSESSED")
        fail_closed_default = (not unreviewed["approved"]
                               and not unreviewed["index_allowed"]
                               and unreviewed["probe_policy"] == "[]")

        # The CLI has no approval defaults either: an incomplete record or an
        # approval without a reviewed rights basis is refused at import time.
        try:
            load_sources({"sources": [{"source_id": "incomplete",
                                       "origin": "https://example.org"}]})
            cli_rejects_incomplete = False
        except AdmissionError:
            cli_rejects_incomplete = True
        try:
            load_sources({"sources": [{
                "source_id": "unreviewed", "origin": "https://example.org",
                "allowed_paths": ["/events"], "rights_status": "NOT_ASSESSED",
                "approved": True, "index_allowed": True}]})
            cli_rejects_unreviewed_rights = False
        except AdmissionError:
            cli_rejects_unreviewed_rights = True

        # Temporary-absence recheck: the Christmas listing 404s out of season
        # and appears later. It must be rechecked, not buried as gone.
        network.enable_seasonal_listing()
        store.conn.execute(
            "UPDATE frontier SET recheck_at='2000-01-01T00:00:00+00:00', "
            "next_retry='2000-01-01T00:00:00+00:00' "
            "WHERE url LIKE '%/events/christmas' AND state='recheck'")
        store.conn.commit()
        rechecks_waiting = store.conn.execute(
            "SELECT COUNT(*) n FROM frontier WHERE state='recheck'").fetchone()["n"]
        reactivated = store.reactivate_rechecks(utc_now())
        crawler_recheck = Crawler(store, staging, config)
        recheck_run = crawler_recheck.run(max_fetches=25)

        # Conditional recrawl: make five pages due, then re-run.
        store.conn.execute(
            "UPDATE page_state SET next_recrawl_at='2000-01-01T00:00:00+00:00' WHERE revoked=0")
        store.conn.commit()
        requeued = store.requeue_for_recrawl(utc_now(), limit=40)
        crawler3 = Crawler(store, staging, config)
        third = crawler3.run(max_fetches=60)

        # Revocation must remove already-staged documents from search.
        revoked_docs = staging.revoke_source("community-hub", "source_revoked_demo")
        search_after_revoke = staging.search("volunteering", None, 10)

        report = build_report(store, staging, config, historical_index=OWNER_INDEX)
        owner_sha_after = sha256_file(OWNER_INDEX) if OWNER_INDEX.exists() else None
        docs = staging.all_documents(2000)
        urls = {d["url"] for d in docs}
        cultural = {
            name: any(name.lower().replace(" ", "-") in url for url in urls)
            for name in ("diwali", "csd-berlin", "pride-berlin", "stadtfest-berlin")
        }
        categories_covered = {c: report["categories"]["counts"][c] for c in CATEGORIES}
        probe_rows = [dict(r) for r in store.conn.execute(
            "SELECT url, parent_url, approval_ref, discovery_method FROM frontier "
            "WHERE discovery_method='guessed_path_probe'")]
        link_rows = store.conn.execute(
            "SELECT COUNT(*) n FROM frontier WHERE discovery_method='link' "
            "AND parent_url IS NOT NULL").fetchone()["n"]
        seasonal_indexed = any("/events/christmas" in url for url in urls)
        network_pages = sum(len(server.routes) for server in network.servers.values())
        forbidden_hits = network.hits_forbidden() if hasattr(network, "hits_forbidden") else {}
        checks = {
            "DEPTH_MAX_3": report["depth"]["deepest_fetched"] <= 3
            and report["depth"]["depth4_fetches"] == 0
            and network.depth4_hits() == 0,
            "ROBOTS_DENIED_NOT_FETCHED": network.servers["berlin-events"].hits_for("/private") == 0,
            "ROBOTS_5xx_FAIL_CLOSED": network.servers["robots-broken"].hits_for("/festival") == 0,
            "NOINDEX_NOT_INDEXED": not any("hidden" in url for url in urls),
            "DUPLICATES_REJECTED": report["rejections"].get("duplicate_exact", 0)
            + report["rejections"].get("duplicate_near", 0) > 0,
            "CULTURAL_EVENTS_DISCOVERABLE": all(cultural.values()),
            "CATEGORY_COVERAGE_18_OF_18": all(v for v in categories_covered.values()),
            "FIXTURE_NETWORK_100_PLUS": network_pages >= 100,
            "RESTART_RECOVERY": "fetching" not in after_queue
            and interrupted_after not in (None, "fetching")
            and sum(after_queue.values()) >= sum(before_queue.values()),
            "SOURCE_ADMISSION_FAIL_CLOSED": fail_closed_default,
            "CONDITIONAL_RECRAWL": third.get("revalidated_unchanged", 0) > 0,
            "SOURCE_REVOCATION": revoked_docs > 0 and not any(
                r["source_id"] == "community-hub" for r in search_after_revoke),
            "RATE_LIMIT_BACKOFF": report["errors"]["rate_limited"] >= 1,
            "NO_UNAPPROVED_HOSTS": report["safety"]["unapproved_host_requests"] == 0,
            "OWNER_INDEX_UNTOUCHED": owner_sha_before == owner_sha_after,
            "FROZEN_54_UNCHANGED": frozen_sha == FROZEN_REPLAY_SHA,
            "DISCOVERY_PROBES_QUEUED": report["discovery"]["probes_total"] > 0,
            "DISCOVERY_INTENTS_FOUND": any(
                item["documents"] for item in report["discovery"]["intents"]),
            "SEASONAL_EVENT_PAGES_DISCOVERED": all(
                any(slug in url for url in urls)
                for slug in ("weihnachtsmarkt", "open-air-festival", "karneval-umzug")),
            "GENUINE_LINKS_SEPARATE_FROM_PROBES": link_rows > 0
            and all(row["parent_url"] is None for row in probe_rows)
            and all(row["approval_ref"] for row in probe_rows),
            "RECHECK_RECOVERY": rechecks_waiting >= 1 and reactivated >= 1
            and seasonal_indexed,
            "HOST_FAIRNESS_UNDER_BUDGET": len(report["fairness"]["fetches_by_source"]) >= 4
            and all(v > 0 for v in report["fairness"]["fetches_by_source"].values()),
            "USEFUL_DISCOVERY_MEASURED": report["discovery"]["useful_per_100_fetches"] > 0,
            "REDIRECT_OFF_ORIGIN_BLOCKED": outside.hits == []
            and report["redirects"]["by_decision"].get("blocked:off_origin", 0) >= 1,
            "REDIRECT_ROBOTS_BLOCKED": network.servers["berlin-events"].hits_for("/private") == 0
            and report["redirects"]["by_decision"].get("blocked:robots_denied", 0) >= 1,
            "REDIRECT_HOPS_LOGGED": report["redirects"]["followed_hops"] >= 3
            and report["redirects"]["blocked_hops"] >= 2
            and len(report["redirects"]["log"]) >= 5,
            "SOURCE_ADMISSION_EXPLICIT": cli_rejects_incomplete
            and cli_rejects_unreviewed_rights,
            "NOVELTY_MEASURED": report["novelty"]["status"] == "MEASURED_READ_ONLY"
            and report["novelty"]["historical_index_pages"] >= 100,
        }
        evidence = {
            "kind": "R3A3F_OFFLINE_DEMO_EVIDENCE",
            "schema": "pulse-search-r3a3f-evidence/v1",
            "generated_at": utc_now(),
            "mode": "offline_loopback_simulator",
            "third_party_requests": 0,
            "network_pages": network_pages,
            "network_hits": network.hits(),
            "depth4_sentinel_hits": network.depth4_hits(),
            "forbidden_hits": forbidden_hits,
            "runs": {"first": first, "restart": second, "recheck": recheck_run,
                     "recrawl": third},
            "recrawl": {"requeued": requeued},
            "restart": {"interrupted_url": interrupted["url"] if interrupted else None,
                        "state_after_restart": interrupted_after,
                        "queue_before": before_queue, "queue_after": after_queue},
            "admission_defaults": {"source_id": unreviewed["source_id"],
                                   "approved": bool(unreviewed["approved"]),
                                   "index_allowed": bool(unreviewed["index_allowed"]),
                                   "probe_policy": unreviewed["probe_policy"]},
            "source_admission_cli": {
                "incomplete_record_rejected": cli_rejects_incomplete,
                "unreviewed_rights_rejected": cli_rejects_unreviewed_rights,
            },
            "redirects": {
                "followed_hops": report["redirects"]["followed_hops"],
                "blocked_hops": report["redirects"]["blocked_hops"],
                "by_decision": report["redirects"]["by_decision"],
                "log_sample": report["redirects"]["log"][:20],
                "unadmitted_target_hits": list(outside.hits),
            },
            "novelty": report["novelty"],
            "recheck": {"waiting_before": rechecks_waiting,
                        "reactivated": reactivated,
                        "seasonal_listing_indexed": seasonal_indexed,
                        "probe_provenance": probe_rows,
                        "genuine_links_with_parent": link_rows},
            "revocation": {"revoked_documents": revoked_docs,
                           "remaining_hits": len(search_after_revoke)},
            "cultural_pages_present": cultural,
            "category_counts": categories_covered,
            "checks": checks,
            "checks_passed": sum(1 for v in checks.values() if v),
            "checks_total": len(checks),
            "report": report,
            "integrity": {
                "owner_index_sha256_before": owner_sha_before,
                "owner_index_sha256_after": owner_sha_after,
                "owner_index_pin": OWNER_INDEX_SHA,
                "owner_index_pin_match": owner_sha_after == OWNER_INDEX_SHA,
                "frozen_54_replay_sha256": frozen_sha,
                "frozen_54_pin_match": frozen_sha == FROZEN_REPLAY_SHA,
            },
            "limits": {
                "live_1000_per_day": "NOT_CLAIMED",
                "human_grading": 0,
                "old_419_tests": "separate archived matrix run",
                "model_integrity": "not exercised by the crawler (no embedding call)",
                "production": "HOLD",
            },
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"evidence": str(out), "checks_passed": evidence["checks_passed"],
                          "checks_total": evidence["checks_total"],
                          "failed": [k for k, v in checks.items() if not v],
                          "documents": report["index"]["documents"],
                          "categories_covered": report["categories"]["covered"],
                          "fetched": report["funnel"]["fetched"]}, indent=2))
        return 0 if evidence["checks_passed"] == evidence["checks_total"] else 1
    finally:
        store.close()
        staging.close()
        network.stop()
        outside.shutdown()
        outside.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
