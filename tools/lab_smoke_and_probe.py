#!/usr/bin/env python3
"""Read-only lab smoke + frozen-query path probe for the recovered engine.

Phase 1 (API): build a throwaway index from a locally generated loopback fixture,
start the ORIGINAL API handler, and prove auth, /health, /v1/stats and /v1/search
answer with real indexed rows.
Phase 2 (probe): send all 54 frozen questions through the accepted lexical search
path and the recovered hybrid ranker, recording an explicit receipt per query.

This is NOT the frozen R3-A2/R3-A3 replay: it scores an 8-page synthetic corpus,
so its counts establish the query path only and are labelled
LAB_QUERY_PATH_ONLY. Relevance assertions here test ranking on pages this
harness authored; they are never combined with October scoring.
Nothing is written outside --work; no network egress beyond 127.0.0.1.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import http.server
import json
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

TOKEN = "lab-readonly-token-0123456789abcdef"

FIXTURES = {
    "/": ("Pulse Search lab index home", "Locally generated laboratory index used only for a read-only API smoke test."),
    "/gp-registration": ("Register with a GP surgery", "A new patient asks a local practice to accept them; the practice checks eligibility and address. The doctor at the surgery confirms registration for the patient."),
    "/driving-licence": ("Apply for a first provisional driving licence", "A learner motorist applies for a provisional licence before driving lessons begin."),
    "/register-to-vote": ("Register to vote in UK elections", "The electoral register records eligible residents so they can vote."),
    "/blood-tests": ("Laboratory blood tests", "A clinician requests blood screening and the laboratory reports results."),
    "/javascript": ("What is JavaScript", "JavaScript is a programming language used for interactive behaviour in web pages."),
    "/http-protocol": ("Hypertext Transfer Protocol", "HTTP is a request and response protocol used to transfer web resources."),
    "/events/armed-forces-day-2027": ("Armed Forces Day 2027", "A civic event page for Armed Forces Day in 2027."),
    "/passport-renewal": ("Renew a passport", "A passport holder renews an expiring passport before travel."),
    "/library-membership": ("Join a public library", "A resident joins a library and borrows books."),
}

# Exact-answer relevance expectations for the lab corpus ONLY: which authored page
# must be the top hit for a real question. These are genuine ranking assertions
# (not HTTP status checks), kept separate from the frozen October verdicts.
RELEVANCE = (
    ("search_doctor", "/gp-registration", "new patient asks to see a doctor"),
    ("search_javascript", "/javascript", "what JavaScript programming is"),
    ("search_vote", "/register-to-vote", "register to vote"),
    ("search_blood", "/blood-tests", "arrange blood screening"),
    ("search_licence", "/driving-licence", "learner motorist provisional licence"),
)


class Fixture(http.server.BaseHTTPRequestHandler):
    hits: list[str] = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        Fixture.hits.append(self.path)
        if self.path == "/robots.txt":
            status, mime, body = 200, "text/plain", b"User-agent: PulseSearchBot\nAllow: /\n"
        elif self.path in FIXTURES:
            title, text = FIXTURES[self.path]
            body = (
                f"<!DOCTYPE html><html><head><title>{title}</title></head><body>"
                f"<h1>{title}</h1><p>{text}</p>"
                + "".join(f'<a href="{p}">{p}</a>' for p in FIXTURES if p != "/")
                + "</body></html>"
            ).encode()
            status, mime = 200, "text/html"
        else:
            status, mime, body = 404, "text/html", b"not found"
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def get(url, token=None, timeout=6):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    started = time.perf_counter()
    try:
        with urlopen(Request(url, headers=headers), timeout=timeout) as r:
            return r.status, json.loads(r.read().decode()), (time.perf_counter() - started) * 1000
    except HTTPError as exc:
        payload = exc.read().decode()
        exc.close()
        try:
            parsed = json.loads(payload)
        except ValueError:
            parsed = {"raw": payload[:120]}
        return exc.code, parsed, (time.perf_counter() - started) * 1000


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine-dir", required=True, type=Path)
    ap.add_argument("--hybrid-dir", type=Path, help="directory holding hybrid_core.py")
    ap.add_argument("--frozen", required=True, type=Path)
    ap.add_argument("--work", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--accepted-index", type=Path, help="optional: record the accepted owner index hash")
    ap.add_argument("--model-dir", type=Path, help="optional: record pinned BGE weight presence")
    args = ap.parse_args(argv)

    accepted_index_sha = None
    if args.accepted_index is not None and args.accepted_index.is_file():
        accepted_index_sha = hashlib.sha256(args.accepted_index.read_bytes()).hexdigest()
    else:
        args.accepted_index = None

    sys.path.insert(0, str(args.engine_dir.resolve()))
    import pulse_search_engine as e  # noqa: E402

    args.work.mkdir(parents=True, exist_ok=True)
    db = args.work / "lab_index.sqlite"
    for stale in (db, Path(str(db) + "-wal"), Path(str(db) + "-shm")):
        if stale.exists():
            stale.unlink()

    fixture = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    ft = threading.Thread(target=fixture.serve_forever, daemon=True)
    ft.start()
    base = f"http://127.0.0.1:{fixture.server_port}"
    sources = args.work / "lab_sources.json"
    sources.write_text(json.dumps([{
        "source_id": "labfixture",
        "origin": base,
        "allowed_paths": ["/"],
        "collection_approved": True,
        "display_mode": "metadata_only",
        "rights_basis": "Locally generated synthetic pages authored for this smoke test only",
    }]), encoding="utf-8")

    e.initdb(db)
    t0 = time.perf_counter()
    # R3-A3E: the fixture defines ten pages; the previous cap of eight silently
    # dropped /register-to-vote and /library-membership from the FTS table, which
    # is what made the voting query return the GP page. Index the whole fixture.
    crawl = e.crawl(db, sources, [base + "/"], max_pages=12, max_depth=1, min_delay=0.01, allow_local=True)
    crawl_ms = (time.perf_counter() - t0) * 1000
    index_sha = hashlib.sha256(db.read_bytes()).hexdigest()

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), e.make_handler(db, TOKEN))
    st = threading.Thread(target=srv.serve_forever, daemon=True)
    st.start()
    api = f"http://127.0.0.1:{srv.server_port}"
    checks = []
    try:
        for name, path, token, expect in (
            ("unauth_search", "/v1/search?q=doctor", None, 401),
            ("wrong_token", "/v1/search?q=doctor", "wrong-token-value", 401),
            ("health", "/health", TOKEN, 200),
            ("stats", "/v1/stats", TOKEN, 200),
            ("search_doctor", "/v1/search?q=doctor&limit=10", TOKEN, 200),
            ("search_javascript", "/v1/search?q=javascript+programming&limit=10", TOKEN, 200),
            ("search_vote", "/v1/search?q=register+to+vote", TOKEN, 200),
            ("search_blood", "/v1/search?q=blood+screening&limit=10", TOKEN, 200),
            ("search_licence", "/v1/search?q=provisional+driving+licence&limit=10", TOKEN, 200),
            ("limit_out_of_range", "/v1/search?q=doctor&limit=999", TOKEN, 400),
            ("unknown_route", "/v1/nope", TOKEN, 404),
        ):
            status, payload, ms = get(api + path, token)
            checks.append({"check": name, "status": status, "expected": expect,
                           "pass": status == expect, "latency_ms": round(ms, 2),
                           "count": payload.get("count"),
                           "titles": [r["title"] for r in payload.get("results", [])][:3],
                           "urls": [r["url"] for r in payload.get("results", [])][:10],
                           "indexed_pages": payload.get("indexed_pages")})

        import sqlite3
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            "SELECT p.url,p.title,p.body,s.display_mode,p.fetched_at FROM pages p "
            "JOIN sources s ON s.source_id=p.source_id WHERE p.indexed=1")]
        conn.close()
    finally:
        srv.shutdown()
        st.join()
        srv.server_close()
        fixture.shutdown()
        ft.join()
        fixture.server_close()

    def search_payload(name):
        for c in checks:
            if c["check"] == name:
                return c
        return {"urls": [], "count": None}

    relevance = []
    for name, suffix, intent in RELEVANCE:
        row = search_payload(name)
        urls = row.get("urls") or []
        rank = next((i + 1 for i, u in enumerate(urls) if u.endswith(suffix)), None)
        relevance.append({
            "check": name,
            "intent": intent,
            "expected_path_suffix": suffix,
            "top1_url": urls[0] if urls else "",
            "expected_rank": rank,
            "result_count": row.get("count"),
            "assertion": ("TOP1_IS_EXPECTED" if rank == 1
                          else "EXPECTED_IN_TOP10" if rank else "EXPECTED_ABSENT"),
            "pass": rank == 1,
        })
    relevance_passed = sum(1 for r in relevance if r["pass"])

    hybrid = {"available": False}
    try:
        if args.hybrid_dir is None:
            raise RuntimeError("no --hybrid-dir supplied")
        sys.path.insert(0, str(args.hybrid_dir.resolve()))
        import hybrid_core
        hi = hybrid_core.HybridIndex(rows)
        hybrid = {"available": True, "capabilities": hi.capabilities, "indexed_rows": hi.n}
    except Exception as exc:  # noqa: BLE001 - reported, never hidden
        hybrid = {"available": False, "reason": f"{type(exc).__name__}: {exc}"}

    frozen = list(csv.DictReader(args.frozen.open(newline="", encoding="utf-8")))
    probe = []
    with e.dbopen(db) as conn:
        for q in frozen:
            for mode, fn in (
                ("A_engine_fts", lambda text: e.search(conn, text, limit=10)),
                ("H_hybrid_lexical", (lambda text: hi.search(text, limit=10)["results"]) if hybrid["available"] else None),
            ):
                if fn is None:
                    probe.append({"probe_id": q["probe_id"], "mode": mode, "status": "REPLAY_NOT_RUN",
                                  "count": 0, "latency_ms": None, "top_titles": "", "top_urls": ""})
                    continue
                t = time.perf_counter()
                try:
                    hits = fn(q["question"])
                    err = ""
                except Exception as exc:  # noqa: BLE001
                    hits, err = [], f"{type(exc).__name__}: {exc}"
                ms = (time.perf_counter() - t) * 1000
                probe.append({
                    "probe_id": q["probe_id"], "mode": mode,
                    "status": "RESULTS" if hits else "EXPLICIT_ZERO_RESULT",
                    "count": len(hits), "latency_ms": round(ms, 2),
                    "top_titles": " | ".join(h["title"] for h in hits[:10]),
                    "top_urls": " | ".join(h["url"] for h in hits[:10]),
                    "error": err,
                })

    def summarise(mode):
        rows_m = [p for p in probe if p["mode"] == mode]
        lat = sorted(p["latency_ms"] for p in rows_m if p["latency_ms"] is not None)
        def pct(p):
            return round(lat[min(len(lat) - 1, int(len(lat) * p))], 2) if lat else None
        return {
            "queries": len(rows_m),
            "with_results": sum(p["status"] == "RESULTS" for p in rows_m),
            "explicit_zero_or_unrun": sum(p["status"] != "RESULTS" for p in rows_m),
            "errors": sum(bool(p.get("error")) for p in rows_m),
            "latency_ms_p50": pct(0.50), "latency_ms_p95": pct(0.95),
        }

    report = {
        "kind": "LAB_API_SMOKE_AND_QUERY_PATH_PROBE_NOT_FROZEN_REPLAY",
        "warning": "Accepted owner index and BGE weights absent; these counts carry no retrieval-quality meaning.",
        "environment": {"python": sys.version.split()[0], "platform": sys.platform,
                        "engine_version": e.VERSION},
        "engine_source_sha256": hashlib.sha256((args.engine_dir / "pulse_search_engine.py").read_bytes()).hexdigest(),
        "lab_index": {"sha256": index_sha, "indexed_pages": crawl["index_pages"],
                      "crawl_outcomes": crawl["outcomes"], "crawl_ms": round(crawl_ms, 2),
                      "fetch_requests": crawl["fetch_requests"],
                      "network_scope": "127.0.0.1 loopback fixture only"},
        "accepted_owner_index_present": accepted_index_sha is not None,
        "accepted_owner_index_sha256": accepted_index_sha,
        "accepted_owner_index_expected_sha256": "bb8e52025a1a25f55141507a02621db190e54bf1fc4d4da8db4248357368c35d",
        "bge_weights_present": bool(args.model_dir and (args.model_dir / "model.safetensors").is_file()),
        "api_checks": checks,
        "api_checks_passed": f"{sum(c['pass'] for c in checks)}/{len(checks)}",
        "relevance_assertions": relevance,
        "relevance_assertions_passed": f"{relevance_passed}/{len(relevance)}",
        "hybrid": hybrid,
        "probe_summary": {m: summarise(m) for m in ("A_engine_fts", "H_hybrid_lexical")},
        "frozen_queries_probed": len(frozen),
        "probe_rows": probe,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in
                      ("api_checks_passed", "relevance_assertions_passed",
                       "relevance_assertions", "probe_summary", "hybrid", "lab_index")},
                     indent=2)[:3600])
    print(f"WROTE {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
