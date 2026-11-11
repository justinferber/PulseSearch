"""Offline three-source demonstration for the R3-A3F crawler.

Two phases, deliberately separate:

1. **Unadmitted register.** The three owner-selected candidates exist only as
   proposal records. Importing seeds for them is refused, `run` refuses to
   start, and the three synthetic origins receive zero requests. This is the
   evidence that selecting a candidate is not admitting it.
2. **Offline simulation.** The same three fixtures are admitted as *synthetic*
   sources (rights_status SYNTHETIC_*) to exercise discovery, depth-3 chains,
   robots refusals, off-origin redirect refusal, duplicate rejection, edition
   separation and per-source dashboard figures. This never touches a real host.

Writes `docs/evidence/r3a3f_three_source_offline.json`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_crawler_r3a3f import cli  # noqa: E402
from pulse_search_crawler_r3a3f.config import CrawlConfig  # noqa: E402
from pulse_search_crawler_r3a3f.crawler import Crawler, build_report  # noqa: E402
from pulse_search_crawler_r3a3f.registry import load_registry  # noqa: E402
from pulse_search_crawler_r3a3f.sitesim import (  # noqa: E402
    Route, RouteServer, build_three_source_network, page_html)
from pulse_search_crawler_r3a3f.staging import StagingIndex  # noqa: E402
from pulse_search_crawler_r3a3f.store import Store, utc_now  # noqa: E402

FROZEN_REPLAY_SHA = "bf0bee88909a537d10e7e7090c7f64fc8929981a862c06d36226ac801d3d2577"
OWNER_INDEX = Path(
    "C:/Users/justi/Desktop/pulseunity/ChatGPTCode/"
    "Pulse_Search_R2P27C_Run_gURzKuV2/live/expanded_live_100_research_index.sqlite"
)
OWNER_INDEX_SHA = "bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d"
REGISTRY = ROOT / "docs/evidence/r3a3f_three_source_admission.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class VirtualClock:
    """Advance time on sleep so pacing is exercised without real waits."""

    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def fresh(path: Path) -> Path:
    if path.exists():
        try:
            shutil.rmtree(path)
        except PermissionError:
            candidate = path.with_name(path.name + "_run")
            index = 2
            while candidate.exists():
                candidate = path.with_name(f"{path.name}_run{index}")
                index += 1
            path = candidate
            print(f"note: {path.name} in use; writing to {path}", flush=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def search_hits(staging: StagingIndex, query: str, needle: str) -> bool:
    return any(needle.lower() in (row["title"] + " " + row["url"]).lower()
               for row in staging.search(query, None, 25))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "docs/evidence/r3a3f_three_source_offline.json"))
    parser.add_argument("--data", default=str(ROOT / "data/r3a3f_three_source"))
    parser.add_argument("--max-fetches", type=int, default=500)
    args = parser.parse_args()

    data = fresh(Path(args.data))
    register = load_registry(REGISTRY)
    owner_sha_before = sha256_file(OWNER_INDEX) if OWNER_INDEX.exists() else None
    frozen_sha = sha256_file(ROOT / "docs/evidence/r3a3d_frozen54_replay.json")

    network = build_three_source_network()
    # A public loopback host that is never admitted. The Show's /route/ would
    # redirect there; the gate must refuse before the request is issued.
    outside = RouteServer().start()
    outside.set("/robots.txt", Route(body=b"User-agent: *\nAllow: /\n",
                                     mime="text/plain; charset=utf-8"))
    outside.set("/events", Route(body=page_html(
        "Unadmitted procession host", "Public page on a host that was never admitted.")))
    network.servers["lord-mayors-show"].set(
        "/route/", Route(status=302, headers={"Location": outside.base + "/events"}))

    config = CrawlConfig(
        allow_loopback=True,
        min_interval_s=0.0,
        loopback_hosts=tuple(server.base.replace("http://", "")
                             for server in network.servers.values()),
        max_depth=3,
        max_fetches_per_day=5000,
        pilot_http_attempts_per_day=5000,
        pilot_accepted_documents_per_day=5000,
        pilot_run_minutes_max=180.0,
    )
    try:
        # ---------------------------------------------------------- phase 1
        unadmitted_dir = fresh(Path(str(data) + "_unadmitted"))
        proposal_payload = {
            "sources": [
                {
                    "source_id": source["source_id"],
                    "origin": source["origin"],
                    "allowed_paths": source["allowed_paths"] or ["/events"],
                    "rights_status": source["rights_status"],
                    "approved": False,
                    "index_allowed": False,
                    "owner_authorisation": "",
                }
                for source in register["sources"]
            ],
            "seeds": {source["source_id"]: [source["proposed_seeds"][0]]
                      for source in register["sources"]},
        }
        proposal_file = unadmitted_dir / "proposal.json"
        proposal_file.write_text(json.dumps(proposal_payload), encoding="utf-8")
        db = str(unadmitted_dir / "crawl.sqlite")
        staging_path = str(unadmitted_dir / "staging.sqlite")
        import_exit = cli.main(["sources", "--db", db, "--staging", staging_path,
                                "--file", str(proposal_file)])
        run_exit = cli.main(["run", "--db", db, "--staging", staging_path,
                             "--max-fetches", "1"])
        registry_hits = network.hits()
        unadmitted_zero = all(value == 0 for value in registry_hits.values())
        unadmitted_report = build_report(Store(db), StagingIndex(staging_path), config,
                                         registry=register)
        real_admitted = unadmitted_report["source_register"]["real_sources_admitted"]

        # ---------------------------------------------------------- phase 2
        store = Store(data / "crawl.sqlite")
        staging = StagingIndex(data / "staging.sqlite")
        for name, server in network.servers.items():
            store.add_source(
                source_id=name,
                origin=server.base,
                allowed_paths=["/events"] if name == "city-hall" else ["/"],
                rights_status="SYNTHETIC_FIXTURE_NOT_A_REAL_PUBLISHER",
                index_allowed=True,
                store_body=False,
                approved=True,
                owner_authorisation="OFFLINE_SIMULATION_ONLY",
                notes="offline simulator source for a candidate shape; no third-party content",
            )
            for seed in network.seeds[name]:
                store.add_seed(name, seed, note="offline candidate seed")

        clock = VirtualClock()
        crawler = Crawler(store, staging, config, clock=clock, sleep=clock.sleep)
        for seed in store.seeds():
            crawler.register_seed(seed["source_id"], seed["url"])
        first = crawler.run(max_fetches=args.max_fetches)
        attempts_after_first = store.budget_snapshot()["http_attempts"]

        # Restart: the persisted counters must continue, not reset. Re-open one
        # completed URL as a page that fell due, so the second process must
        # perform a real request and pay for it from the same ledger.
        due = store.conn.execute(
            "SELECT url FROM frontier WHERE state='done' AND source_id='london-parade' "
            "ORDER BY url LIMIT 1").fetchone()
        if due:
            store.conn.execute(
                "UPDATE frontier SET state='queued', next_retry=NULL WHERE url=?",
                (due["url"],))
            store.conn.commit()
        restarted = Crawler(store, staging, config, clock=clock, sleep=clock.sleep)
        second = restarted.run(max_fetches=5)
        attempts_after_second = store.budget_snapshot()["http_attempts"]

        report = build_report(store, staging, config, historical_index=OWNER_INDEX,
                              expected_index_sha256=OWNER_INDEX_SHA, registry=register)
        owner_sha_after = sha256_file(OWNER_INDEX) if OWNER_INDEX.exists() else None
        documents = staging.all_documents(2000)
        urls = {doc["url"] for doc in documents}
        source_docs = {name: [doc for doc in documents if doc["source_id"] == name]
                       for name in network.servers}
        source_stats = {name: {"documents": len(docs),
                               "categories": sorted({doc["category"] for doc in docs}),
                               "deepest": max((doc["depth"] for doc in docs), default=0)}
                        for name, docs in source_docs.items()}
        queries = {
            "London Parade": "parade",
            "Lord Mayor's Show": "mayor",
            "City Hall events": "city hall",
            "Diwali": "diwali",
            "procession route": "route",
            "2027 parade": "2027",
        }
        query_results = {
            query: [row["title"] for row in staging.search(query, None, 10)]
            for query in queries
        }
        show_2026 = [doc for doc in source_docs["lord-mayors-show"]
                     if "dates-and-routes" in doc["url"]]
        parade_2026 = [doc for doc in source_docs["london-parade"]
                       if "2026-review" in doc["url"]]
        parade_2027 = [doc for doc in source_docs["london-parade"]
                       if "2027-celebrate" in doc["url"]]
        checks = {
            "THREE_CANDIDATES_REGISTERED_FOR_REVIEW": len(register["sources"]) == 3
            and all(not s["approved"] and not s["index_allowed"] for s in register["sources"]),
            "UNADMITTED_IMPORT_REFUSED": import_exit == 2,
            "UNADMITTED_RUN_REFUSED": run_exit == 3,
            "UNADMITTED_ZERO_REQUESTS": unadmitted_zero,
            "REAL_SOURCES_ADMITTED_0": real_admitted == 0,
            "THIRD_PARTY_CRAWLER_REQUESTS_0": outside.hits == [],
            "MAX_HOPS_3": report["depth"]["deepest_fetched"] <= 3
            and report["depth"]["depth4_fetches"] == 0
            and network.depth4_hits() == 0,
            "ALL_THREE_SOURCES_STAGED": all(stats["documents"] > 0
                                            for stats in source_stats.values()),
            "CITY_HALL_WHATS_ON_NOT_FETCHED": network.servers["city-hall"].hits_for("/whats-on") == 0,
            "CITY_HALL_SEARCH_NOT_FETCHED": network.servers["city-hall"].hits_for("/search") == 0,
            "PARADE_FORMS_AND_SHOP_NOT_FETCHED": all(
                network.servers["london-parade"].hits_for(path) == 0
                for path in ("/shop/", "/takepart/", "/account/", "/admin/")),
            "SHOW_TERMS_NOT_FETCHED": network.servers["lord-mayors-show"].hits_for("/terms-of-use/") == 0,
            "SHOW_BOOK_NOT_FETCHED": network.servers["lord-mayors-show"].hits_for("/book/") == 0,
            "OFF_ORIGIN_REDIRECT_BLOCKED": outside.hits == []
            and report["redirects"]["by_decision"].get("blocked:off_origin", 0) >= 1,
            "PARADE_2027_EDITION_PRESENT": bool(parade_2027),
            "PARADE_2026_EDITION_SEPARATE": bool(parade_2026)
            and all("2027" not in (doc.get("dates") or "") + (doc.get("snippet") or "")
                    for doc in parade_2026),
            "SHOW_2026_EDITION_PRESENT": any("2026" in (doc.get("dates") or "")
                                             + (doc.get("snippet") or "")
                                             for doc in show_2026),
            "CANCELLED_EDITION_RECORDED": any("2021-parade-cancelled" in url for url in urls),
            "DUPLICATE_SYNDICATION_REJECTED": report["rejections"].get("duplicate_exact", 0) >= 1,
            "NO_FORM_OR_PORTAL_DOCUMENTS": not any(
                token in url for url in urls
                for token in ("/takepart/", "/shop/", "/account/", "/book/")),
            "RELEVANCE_LONDON_PARADE": search_hits(staging, "London Parade", "parade"),
            "RELEVANCE_LORD_MAYORS_SHOW": search_hits(staging, "Lord Mayor's Show", "mayor"),
            "RELEVANCE_CITY_HALL": search_hits(staging, "City Hall events", "city hall"),
            "RELEVANCE_DIWALI": search_hits(staging, "Diwali", "diwali"),
            "PER_SOURCE_DASHBOARD_FIELDS": all(
                stats["documents"] > 0 and stats["categories"]
                for stats in source_stats.values()),
            "BUDGET_PERSISTS_ACROSS_RESTART": attempts_after_second > attempts_after_first > 0,
            "NOVELTY_PINNED_READ_ONLY": report["novelty"]["status"] == "MEASURED_READ_ONLY"
            and report["novelty"]["pin_match"] is True
            and report["novelty"]["historical_index_pages"] >= 120,
            "OWNER_INDEX_UNTOUCHED": owner_sha_before == owner_sha_after,
            "FROZEN_54_UNCHANGED": frozen_sha == FROZEN_REPLAY_SHA,
            "SOURCE_REGISTER_IN_REPORT": len(report["source_register"]["candidates"]) == 3,
        }
        evidence = {
            "kind": "R3A3F_THREE_SOURCE_OFFLINE_EVIDENCE",
            "schema": "pulse-search-r3a3f-evidence/v2",
            "generated_at": utc_now(),
            "mode": "offline_loopback_simulator",
            "third_party_requests": 0,
            "registry": {
                "path": str(REGISTRY.relative_to(ROOT)),
                "sources": [source["source_id"] for source in register["sources"]],
                "states": {source["source_id"]: source["state"] for source in register["sources"]},
                "import_exit": import_exit,
                "run_exit": run_exit,
                "hits_while_unadmitted": registry_hits,
                "real_sources_admitted": real_admitted,
            },
            "runs": {"first": first, "restart": second},
            "restart": {"http_attempts_after_first": attempts_after_first,
                        "http_attempts_after_second": attempts_after_second},
            "per_source": source_stats,
            "queries": query_results,
            "redirects": {
                "followed_hops": report["redirects"]["followed_hops"],
                "blocked_hops": report["redirects"]["blocked_hops"],
                "by_decision": report["redirects"]["by_decision"],
                "unadmitted_target_hits": list(outside.hits),
            },
            "network_hits": network.hits(),
            "budget": report["pilot_budget"],
            "novelty": report["novelty"],
            "checks": checks,
            "checks_passed": sum(1 for value in checks.values() if value),
            "checks_total": len(checks),
            "failed": [name for name, value in checks.items() if not value],
            "report": report,
            "integrity": {
                "owner_index_sha256_before": owner_sha_before,
                "owner_index_sha256_after": owner_sha_after,
                "owner_index_pin_match": owner_sha_after == OWNER_INDEX_SHA,
                "frozen_54_replay_sha256": frozen_sha,
                "frozen_54_pin_match": frozen_sha == FROZEN_REPLAY_SHA,
            },
            "limits": {
                "live_third_party_requests": 0,
                "real_sources_admitted": 0,
                "signed_human_grading": "PENDING",
                "production": "HOLD",
            },
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        print(json.dumps({
            "evidence": str(out),
            "checks_passed": evidence["checks_passed"],
            "checks_total": evidence["checks_total"],
            "failed": evidence["failed"],
            "documents": report["index"]["documents"],
            "per_source": {name: stats["documents"] for name, stats in source_stats.items()},
            "fetched": report["funnel"]["fetched"],
        }, indent=2))
        store.close()
        staging.close()
        return 0 if evidence["checks_passed"] == evidence["checks_total"] else 1
    finally:
        network.stop()
        outside.shutdown()
        outside.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
