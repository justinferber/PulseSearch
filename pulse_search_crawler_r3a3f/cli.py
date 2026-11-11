"""Command line entry points for the offline R3-A3F crawler.

The import path is deliberately stricter than the store: a JSON record must
state every admission field explicitly, and a record that claims approval
without a reviewed rights basis is rejected. There is no default that could
turn an incomplete file into a crawling authorisation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import CrawlConfig
from .crawler import Crawler, build_report
from .novelty import PINNED_INDEX_SHA256
from .registry import load_registry
from .staging import StagingIndex
from .store import Store
from .urls import UrlError, canonicalize, in_scope

ADMISSION_FIELDS = ("source_id", "origin", "allowed_paths", "rights_status",
                    "approved", "index_allowed")
NOT_REVIEWED_STATUSES = frozenset({"", "NOT_ASSESSED", "PENDING_REVIEW",
                                   "PENDING_TERMS_REVIEW"})


class AdmissionError(ValueError):
    """Raised when a source record is not a complete owner-reviewed decision."""


def load_sources(payload: dict) -> list[dict]:
    """Validate a source file without registering anything.

    Missing admission fields are an error, never an implicit approval. This is
    the import-time equivalent of the store's fail-closed defaults.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise AdmissionError("source file must contain a 'sources' array")
    records: list[dict] = []
    for index, source in enumerate(payload["sources"]):
        if not isinstance(source, dict):
            raise AdmissionError(f"source #{index} is not an object")
        source_id = source.get("source_id", f"#{index}")
        missing = [field for field in ADMISSION_FIELDS if field not in source]
        if missing:
            raise AdmissionError(
                f"source {source_id} is missing {', '.join(missing)}; admission "
                "fields have no defaults and must be stated explicitly")
        if not isinstance(source["approved"], bool) or not isinstance(source["index_allowed"], bool):
            raise AdmissionError(
                f"source {source_id}: approved and index_allowed must be booleans")
        paths = source["allowed_paths"]
        if not isinstance(paths, list) or not paths or not all(
                isinstance(path, str) and path.startswith("/") for path in paths):
            raise AdmissionError(
                f"source {source_id}: allowed_paths must be explicit absolute paths")
        if source["index_allowed"] and not source["approved"]:
            raise AdmissionError(
                f"source {source_id}: cannot index a source that is not admitted")
        if source["approved"] and str(source["rights_status"]) in NOT_REVIEWED_STATUSES:
            raise AdmissionError(
                f"source {source_id}: an admitted source needs a reviewed rights basis, "
                f"not {source['rights_status']!r}")
        authorisation = str(source.get("owner_authorisation") or "").strip()
        synthetic = str(source["rights_status"]).upper().startswith("SYNTHETIC")
        if source["approved"] and not synthetic:
            # The flag cannot authorise itself, and the rights status is a
            # finding, not a decision: a distinct written owner decision is
            # required before a real host may be admitted.
            if not authorisation:
                raise AdmissionError(
                    f"source {source_id}: admitting a real host needs a documented "
                    "owner_authorisation reference")
            if authorisation.upper() == str(source["rights_status"]).strip().upper():
                raise AdmissionError(
                    f"source {source_id}: owner_authorisation must be a distinct "
                    "decision reference, not a copy of the rights status")
        records.append(source)
    return records


def validate_seeds(records: list[dict], seeds: dict) -> None:
    """Refuse seeds for unadmitted sources or outside an approved path."""
    by_id = {record["source_id"]: record for record in records}
    for source_id, urls in seeds.items():
        source = by_id.get(source_id)
        if source is None:
            raise AdmissionError(f"seeds reference unknown source {source_id!r}")
        if not source["approved"]:
            raise AdmissionError(f"seeds reference unadmitted source {source_id!r}")
        for url in urls:
            try:
                canonical = canonicalize(url)
            except (UrlError, ValueError) as exc:
                raise AdmissionError(f"seed {url!r}: {exc}") from exc
            if not in_scope(canonical, source["origin"], source["allowed_paths"]):
                raise AdmissionError(
                    f"seed {canonical} is outside {source_id}'s approved scope")


def preflight(store: Store) -> list[str]:
    """Reasons a run must not start. Used before any network request."""
    problems: list[str] = []
    admitted = store.sources()
    if not admitted:
        problems.append("no admitted source: refusing to crawl")
    for source in admitted:
        if str(source["rights_status"]) in NOT_REVIEWED_STATUSES:
            problems.append(
                f"{source['source_id']}: admitted without a reviewed rights basis")
        if not json.loads(source["allowed_paths"] or "[]"):
            problems.append(f"{source['source_id']}: no approved path")
        synthetic = str(source["rights_status"]).upper().startswith("SYNTHETIC")
        if not synthetic and not (source.get("owner_authorisation") or "").strip():
            problems.append(
                f"{source['source_id']}: admitted without a documented owner authorisation")
    return problems


def _open(paths: argparse.Namespace) -> tuple[Store, StagingIndex]:
    return Store(paths.db), StagingIndex(paths.staging)


def cmd_sources(args: argparse.Namespace) -> int:
    store, staging = _open(args)
    try:
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
        records = load_sources(payload)
        seeds = payload.get("seeds", {})
        if not isinstance(seeds, dict):
            raise AdmissionError("'seeds' must map source_id to a list of URLs")
        validate_seeds(records, seeds)
        for source in records:
            store.add_source(
                source_id=source["source_id"],
                origin=source["origin"],
                allowed_paths=source["allowed_paths"],
                rights_status=source["rights_status"],
                index_allowed=source["index_allowed"],
                store_body=bool(source.get("store_body", False)),
                contact=source.get("contact", ""),
                owner_authorisation=source.get("owner_authorisation", ""),
                notes=source.get("notes", ""),
                approved=source["approved"],
                probe_policy=source.get("probe_policy", []),
                probe_budget_per_run=int(source.get("probe_budget_per_run", 0)),
                crawl_delay_floor_s=float(source.get("crawl_delay_floor_s", 0.0)),
            )
        admitted_seeds = 0
        for source_id, urls in seeds.items():
            for url in urls:
                store.add_seed(source_id, url, note="cli admission")
                admitted_seeds += 1
        print(json.dumps({"sources_imported": len(records),
                          "sources_admitted": sum(1 for r in records if r["approved"]),
                          "seeds_admitted": admitted_seeds}))
        return 0
    except (AdmissionError, ValueError, OSError) as exc:
        print(json.dumps({"error": "source_admission_rejected", "detail": str(exc),
                          "sources_admitted": 0, "seeds_admitted": 0}))
        return 2
    finally:
        store.close()
        staging.close()


def cmd_run(args: argparse.Namespace) -> int:
    store, staging = _open(args)
    try:
        problems = preflight(store)
        if problems:
            print(json.dumps({"error": "crawl_refused", "detail": problems,
                              "sources_admitted": len(store.sources())}))
            return 3
        config = CrawlConfig(
            allow_loopback=args.allow_loopback,
            loopback_hosts=tuple(args.loopback_host or ()),
            min_interval_s=0.0 if args.allow_loopback else 3.0,
        )
        crawler = Crawler(store, staging, config)
        counters = crawler.run(max_fetches=args.max_fetches)
        print(json.dumps({"counters": counters,
                          "report": build_report(store, staging, config)},
                         indent=2)[:4000])
        return 0
    finally:
        store.close()
        staging.close()


def cmd_report(args: argparse.Namespace) -> int:
    store, staging = _open(args)
    try:
        config = CrawlConfig()
        registry = load_registry(args.registry) if args.registry else None
        report = build_report(store, staging, config,
                              historical_index=args.historical_index,
                              expected_index_sha256=args.index_sha256,
                              registry=registry)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        print(args.out)
        return 0
    finally:
        store.close()
        staging.close()


def cmd_dashboard(args: argparse.Namespace) -> int:
    from .dashboard import serve

    server = serve(args.db, args.staging, args.port, args.historical_index,
                   registry_path=args.registry, index_sha256=args.index_sha256)
    print(f"dashboard: http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pulse_search_crawler_r3a3f")
    sub = parser.add_subparsers(dest="command", required=True)

    sources = sub.add_parser("sources", help="register explicitly admitted sources")
    sources.add_argument("--db", required=True)
    sources.add_argument("--staging", required=True)
    sources.add_argument("--file", required=True)
    sources.set_defaults(func=cmd_sources)

    run = sub.add_parser("run", help="run or resume the crawl")
    run.add_argument("--db", required=True)
    run.add_argument("--staging", required=True)
    run.add_argument("--max-fetches", type=int, default=None)
    run.add_argument("--allow-loopback", action="store_true")
    run.add_argument("--loopback-host", action="append", default=None,
                     help="loopback host:port allowed for the offline simulator")
    run.set_defaults(func=cmd_run)

    report = sub.add_parser("report", help="write the JSON run report")
    report.add_argument("--db", required=True)
    report.add_argument("--staging", required=True)
    report.add_argument("--out", required=True)
    report.add_argument("--historical-index", default=None,
                        help="optional pinned index for read-only novelty comparison")
    report.add_argument("--index-sha256", default=PINNED_INDEX_SHA256,
                        help="expected SHA-256 of the historical index (pin check)")
    report.add_argument("--registry", default=None,
                        help="optional three-candidate source register JSON")
    report.set_defaults(func=cmd_report)

    dash = sub.add_parser("dashboard", help="serve the read-only console")
    dash.add_argument("--db", required=True)
    dash.add_argument("--staging", required=True)
    dash.add_argument("--port", type=int, default=8787)
    dash.add_argument("--historical-index", default=None,
                      help="optional pinned index for read-only novelty comparison")
    dash.add_argument("--index-sha256", default=PINNED_INDEX_SHA256,
                      help="expected SHA-256 of the historical index (pin check)")
    dash.add_argument("--registry", default=None,
                      help="optional three-candidate source register JSON")
    dash.set_defaults(func=cmd_dashboard)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
