"""Command line entry points for the offline R3-A3F crawler."""

from __future__ import annotations

import argparse
import json

from .config import CrawlConfig
from .crawler import Crawler, build_report
from .staging import StagingIndex
from .store import Store


def _open(paths: argparse.Namespace) -> tuple[Store, StagingIndex]:
    return Store(paths.db), StagingIndex(paths.staging)


def cmd_sources(args: argparse.Namespace) -> int:
    store, staging = _open(args)
    payload = json.loads(open(args.file, encoding="utf-8").read())
    for source in payload["sources"]:
        store.add_source(
            source_id=source["source_id"],
            origin=source["origin"],
            allowed_paths=source.get("allowed_paths", ["/"]),
            rights_status=source.get("rights_status", "proposed_internal_research"),
            index_allowed=source.get("index_allowed", True),
            store_body=source.get("store_body", False),
            contact=source.get("contact", ""),
            notes=source.get("notes", ""),
            approved=source.get("approved", True),
        )
    for source_id, urls in payload.get("seeds", {}).items():
        for url in urls:
            store.add_seed(source_id, url, note="cli admission")
    print(json.dumps({"sources": len(payload["sources"]),
                      "seeds": sum(len(v) for v in payload.get("seeds", {}).values())}))
    store.close()
    staging.close()
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    store, staging = _open(args)
    config = CrawlConfig(allow_loopback=args.allow_loopback,
                         min_interval_s=0.0 if args.allow_loopback else CrawlConfig.min_interval_s)
    crawler = Crawler(store, staging, config)
    counters = crawler.run(max_fetches=args.max_fetches)
    print(json.dumps({"counters": counters, "report": build_report(store, staging, config)},
                     indent=2)[:4000])
    store.close()
    staging.close()
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    store, staging = _open(args)
    config = CrawlConfig()
    report = build_report(store, staging, config)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(args.out)
    store.close()
    staging.close()
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    from .dashboard import serve

    server = serve(args.db, args.staging, args.port)
    print(f"dashboard: http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pulse_search_crawler_r3a3f")
    sub = parser.add_subparsers(dest="command", required=True)

    sources = sub.add_parser("sources", help="register sources and seeds from JSON")
    sources.add_argument("--db", required=True)
    sources.add_argument("--staging", required=True)
    sources.add_argument("--file", required=True)
    sources.set_defaults(func=cmd_sources)

    run = sub.add_parser("run", help="run or resume the crawl")
    run.add_argument("--db", required=True)
    run.add_argument("--staging", required=True)
    run.add_argument("--max-fetches", type=int, default=None)
    run.add_argument("--allow-loopback", action="store_true")
    run.set_defaults(func=cmd_run)

    report = sub.add_parser("report", help="write the JSON run report")
    report.add_argument("--db", required=True)
    report.add_argument("--staging", required=True)
    report.add_argument("--out", required=True)
    report.set_defaults(func=cmd_report)

    dash = sub.add_parser("dashboard", help="serve the read-only console")
    dash.add_argument("--db", required=True)
    dash.add_argument("--staging", required=True)
    dash.add_argument("--port", type=int, default=8787)
    dash.set_defaults(func=cmd_dashboard)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
