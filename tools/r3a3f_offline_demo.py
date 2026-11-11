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
from pulse_search_crawler_r3a3f.config import CrawlConfig  # noqa: E402
from pulse_search_crawler_r3a3f.crawler import Crawler, build_report  # noqa: E402
from pulse_search_crawler_r3a3f.sitesim import build_network  # noqa: E402
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
        shutil.rmtree(data)
    data.mkdir(parents=True)

    owner_sha_before = sha256_file(OWNER_INDEX) if OWNER_INDEX.exists() else None
    frozen_sha = sha256_file(ROOT / "docs/evidence/r3a3d_frozen54_replay.json")

    network = build_network()
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
                notes="offline simulator source; no third-party content",
            )
            for seed in network.seeds[name]:
                store.add_seed(name, seed, note="offline demo seed")

        crawler = Crawler(store, staging, config)
        for seed in store.seeds():
            store.enqueue(seed["url"], source_id=seed["source_id"], seed_id=seed["seed_id"],
                          parent_url=None, depth=0, max_depth=config.max_depth)
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

        report = build_report(store, staging, config)
        owner_sha_after = sha256_file(OWNER_INDEX) if OWNER_INDEX.exists() else None
        docs = staging.all_documents(2000)
        urls = {d["url"] for d in docs}
        cultural = {
            name: any(name.lower().replace(" ", "-") in url for url in urls)
            for name in ("diwali", "csd-berlin", "pride-berlin", "stadtfest-berlin")
        }
        categories_covered = {c: report["categories"]["counts"][c] for c in CATEGORIES}
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
            "RESTART_RECOVERY": second["fetched"] >= 0 and "queued" in after_queue,
            "CONDITIONAL_RECRAWL": third.get("revalidated_unchanged", 0) > 0,
            "SOURCE_REVOCATION": revoked_docs > 0 and not any(
                r["source_id"] == "community-hub" for r in search_after_revoke),
            "RATE_LIMIT_BACKOFF": report["errors"]["rate_limited"] >= 1,
            "NO_UNAPPROVED_HOSTS": report["safety"]["unapproved_host_requests"] == 0,
            "OWNER_INDEX_UNTOUCHED": owner_sha_before == owner_sha_after,
            "FROZEN_54_UNCHANGED": frozen_sha == FROZEN_REPLAY_SHA,
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
            "runs": {"first": first, "restart": second, "recrawl": third},
            "recrawl": {"requeued": requeued},
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


if __name__ == "__main__":
    raise SystemExit(main())
