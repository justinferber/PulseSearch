"""Local, read-only monitoring console for the R3-A3F crawler.

Serves an owner-facing HTML report plus a machine-readable JSON download. It
never starts a crawl, never writes to the staging index and never contacts a
third-party site: it renders whatever the crawler persisted.
"""

from __future__ import annotations

import argparse
import html
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from .classify import CATEGORIES
from .config import CrawlConfig
from .crawler import build_report
from .staging import StagingIndex
from .store import Store

CSS = """
:root{--bg:#0b1020;--panel:#141b2d;--line:#26304a;--ink:#e8ecf7;--muted:#95a2bd;
--accent:#6ea8fe;--good:#4ade80;--warn:#fbbf24;--bad:#f87171}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:28px 32px 12px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,#111a2e,#0b1020)}
h1{margin:0 0 6px;font-size:24px;letter-spacing:.2px}
.sub{color:var(--muted);font-size:14px}
main{padding:24px 32px 60px;max-width:1280px}
.grid{display:grid;gap:16px}
.cards{grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}
.card .k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
.card .v{font-size:28px;font-weight:650;margin-top:6px}
.card .n{color:var(--muted);font-size:12px;margin-top:4px}
section{margin-top:26px}
h2{font-size:17px;margin:0 0 12px;letter-spacing:.2px}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);font-size:13px;vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.06em}
tr:last-child td{border-bottom:none}
.bar{height:8px;background:#1d2740;border-radius:99px;overflow:hidden;min-width:120px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,#4f8cff,#7ee0c1)}
.pill{display:inline-block;padding:2px 8px;border-radius:99px;font-size:12px;border:1px solid var(--line);color:var(--muted)}
.pill.good{color:var(--good);border-color:#1f5136}
.pill.bad{color:var(--bad);border-color:#5b2530}
.pill.warn{color:var(--warn);border-color:#5a4620}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.two{grid-template-columns:1fr 1fr}
form{display:flex;gap:8px;margin:8px 0 14px}
input,select,button{background:#0f1729;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:14px}
button{background:#1b2a4a;cursor:pointer}
button:hover{background:#24365e}
code{background:#0f1729;padding:1px 6px;border-radius:6px;font-size:12px}
.foot{margin-top:30px;color:var(--muted);font-size:12px}
ul.tight{margin:0;padding-left:18px}
ul.tight li{margin:2px 0}
"""


def _bar(value: int, peak: int) -> str:
    pct = 0 if peak <= 0 else max(2, round(value / peak * 100))
    return f"<div class='bar'><i style='width:{pct}%'></i></div>"


def render_html(report: dict, staging: StagingIndex, query: str = "", category: str = "") -> str:
    funnel = report["funnel"]
    categories = report["categories"]
    peak = max(categories["counts"].values() or [1])
    results = staging.search(query, category or None, 20) if query.strip() else []
    run = report.get("run") or {}
    counters = {}
    if run.get("counters"):
        try:
            counters = json.loads(run["counters"])
        except ValueError:
            counters = {}
    stop = counters.get("stop_reason", "n/a")
    rows = []
    for name in CATEGORIES:
        count = categories["counts"].get(name, 0)
        state = "good" if count else "warn"
        rows.append(
            f"<tr><td>{html.escape(name)}</td><td>{_bar(count, peak)}</td>"
            f"<td>{count}</td><td><span class='pill {state}'>"
            f"{'covered' if count else 'not yet covered'}</span></td></tr>"
        )
    docs = "".join(
        f"<tr><td><a href='{html.escape(d['url'])}' rel='noopener noreferrer'>"
        f"{html.escape(d['title'][:90])}</a></td><td>{html.escape(d['category'])}</td>"
        f"<td>{d['depth']}</td><td>{html.escape(d['source_id'])}</td>"
        f"<td>{d['confidence']:.2f}</td></tr>"
        for d in report["documents"]
    ) or "<tr><td colspan='5'>No accepted documents yet.</td></tr>"
    search_rows = "".join(
        f"<tr><td><a href='{html.escape(r['url'])}'>{html.escape(r['title'][:100])}</a></td>"
        f"<td>{html.escape(r['category'])}</td><td>{html.escape(r['snippet'][:160])}</td></tr>"
        for r in results
    )
    source_rows = "".join(
        f"<tr><td>{html.escape(s['source_id'])}</td><td>{html.escape(s['origin'])}</td>"
        f"<td>{html.escape(s['rights_status'])}</td><td>{s['documents']}</td>"
        f"<td>{'yes' if s['index_allowed'] else 'no'}</td></tr>"
        for s in report["sources"]
    ) or "<tr><td colspan='5'>No sources registered.</td></tr>"
    rejection_rows = "".join(
        f"<tr><td>{html.escape(reason)}</td><td>{count}</td></tr>"
        for reason, count in report["rejections"].items()
    ) or "<tr><td colspan='2'>none</td></tr>"
    target = report["daily_target_model"]
    needed = target["gross_fetches_needed_at_observed_yield"]
    safety = report["safety"]
    external = ", ".join(c["origin"] for c in report["external_candidates"][:6]) or "none recorded"
    sitemaps = report["sitemap_candidates"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Pulse Search R3-A3F crawler console</title><style>{CSS}</style></head><body>
<header><h1>Pulse Search · R3-A3F depth-3 crawler</h1>
<div class="sub">Offline staging run · generation {html.escape(report['generated_at'])} ·
stop reason <code>{html.escape(str(stop))}</code> · max depth {report['depth']['max_depth_configured']} ·
final status <span class="pill warn">PRODUCTION HOLD</span></div></header>
<main>
<div class="grid cards">
  <div class="card"><div class="k">Fetched</div><div class="v">{funnel['fetched']}</div>
    <div class="n">queue {sum(funnel['queue'].values())} · deepest {report['depth']['deepest_fetched']}</div></div>
  <div class="card"><div class="k">Accepted</div><div class="v">{funnel['accepted']}</div>
    <div class="n">yield {funnel['acceptance_rate']*100:.1f}% of fetches</div></div>
  <div class="card"><div class="k">Searchable now</div><div class="v">{funnel['indexed_searchable']}</div>
    <div class="n">staging index, separate from the pinned index</div></div>
  <div class="card"><div class="k">Categories</div><div class="v">{categories['covered']}/18</div>
    <div class="n">{len(categories['uncovered'])} not yet covered</div></div>
  <div class="card"><div class="k">Rejected</div><div class="v">{funnel['rejected']}</div>
    <div class="n">reasons listed below</div></div>
  <div class="card"><div class="k">Depth-4 fetches</div><div class="v">{safety['depth4_fetches']}</div>
    <div class="n">must be zero · unapproved hosts {safety['unapproved_host_requests']}</div></div>
</div>

<section><h2>Progress towards 1,000 accepted pages/day</h2>
<table><tr><th>Measure</th><th>Value</th><th>Note</th></tr>
<tr><td>Target</td><td>{target['target_new_pages_per_day']}</td><td>aim, never a quota to fake</td></tr>
<tr><td>Observed acceptance</td><td>{target['observed_acceptance_rate']*100:.1f}%</td><td>accepted ÷ fetched in this run</td></tr>
<tr><td>Gross fetches needed</td><td>{needed if needed is not None else 'n/a'}</td><td>at the observed yield; capped at {target['gross_fetch_ceiling']}/day</td></tr>
<tr><td>Per-host daily ceiling</td><td>{report['politeness']['per_host_daily_ceiling']}</td><td>at {report['politeness']['min_interval_s']}s spacing, one request in flight</td></tr>
<tr><td>Claim status</td><td><span class="pill warn">SIMULATION ONLY</span></td><td>1,000/day is not claimed from an offline run</td></tr>
</table></section>

<section><h2>18-category coverage</h2><table>
<tr><th>Category</th><th>Distribution</th><th>Pages</th><th>Status</th></tr>{''.join(rows)}
</table></section>

<section class="grid two">
<div><h2>Funnel</h2><table>
<tr><th>Stage</th><th>Count</th></tr>
<tr><td>URLs discovered</td><td>{funnel['discovered']}</td></tr>
<tr><td>Queued / blocked</td><td>{funnel['queue'].get('queued',0)} / {funnel['queue'].get('blocked',0)}</td></tr>
<tr><td>Fetched</td><td>{funnel['fetched']}</td></tr>
<tr><td>Accepted</td><td>{funnel['accepted']}</td></tr>
<tr><td>Searchable</td><td>{funnel['indexed_searchable']}</td></tr>
<tr><td>Off-domain candidates</td><td>{len(report['external_candidates'])}</td></tr>
<tr><td>Sitemap candidates</td><td>{len(sitemaps)}</td></tr>
</table></div>
<div><h2>Rejections by reason</h2><table>
<tr><th>Reason</th><th>Count</th></tr>{rejection_rows}
</table></div></section>

<section><h2>Sources and rights</h2><table>
<tr><th>Source</th><th>Origin</th><th>Rights basis</th><th>Docs</th><th>Index allowed</th></tr>
{source_rows}</table></section>

<section><h2>Freshness, errors and safety</h2><table>
<tr><th>Signal</th><th>Value</th></tr>
<tr><td>Revalidated unchanged (304)</td><td>{report['freshness']['revalidated_unchanged']}</td></tr>
<tr><td>Updated documents</td><td>{report['freshness']['changed_or_updated']}</td></tr>
<tr><td>Rate limited (429/503)</td><td>{report['errors']['rate_limited']}</td></tr>
<tr><td>Robots denials</td><td>{report['robots']['denied']}</td></tr>
<tr><td>Removed or denied (403/404/410/451)</td><td>{report['errors']['removed_or_denied']}</td></tr>
<tr><td>Mean / p95 latency</td><td>{report['latency']['mean_ms']} ms / {report['latency']['p95_ms']} ms</td></tr>
<tr><td>Off-domain hosts seen</td><td>{html.escape(external)}</td></tr>
<tr><td>Body storage</td><td>{html.escape(safety['body_storage'])}</td></tr>
<tr><td>Events Engine writes</td><td>{safety['events_engine_writes']}</td></tr>
</table></section>

<section><h2>Search the staging index</h2>
<form method="get" action="/search">
<input name="q" value="{html.escape(query)}" placeholder="e.g. Diwali, CSD Berlin, Stadtfest, flower show" size="42">
<select name="category"><option value="">All categories</option>
{''.join(f'<option value="{html.escape(c)}"{" selected" if c==category else ""}>{html.escape(c)}</option>' for c in CATEGORIES)}
</select><button type="submit">Search</button></form>
<table><tr><th>Title</th><th>Category</th><th>Snippet</th></tr>
{search_rows or "<tr><td colspan='3'>Run a search to see staged results and source links.</td></tr>"}</table></section>

<section><h2>Accepted documents ({len(report['documents'])})</h2>
<table><tr><th>Title</th><th>Category</th><th>Depth</th><th>Source</th><th>Confidence</th></tr>{docs}</table></section>

<div class="foot">Read-only local console · data from the crawler and staging databases ·
<a href="/api/report.json">report JSON</a> · <a href="/download">download JSON report</a> ·
No third-party content is republished here; titles and short snippets only.</div>
</main></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "PulseConsole/1.0"

    def log_message(self, *args):
        return

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/health":
            self._send(200, b'{"ok":true}', "application/json")
            return
        report = build_report(self.server.store, self.server.staging, self.server.config)
        if parsed.path == "/api/report.json":
            self._send(200, json.dumps(report, indent=2).encode("utf-8"), "application/json")
            return
        if parsed.path == "/download":
            self._send(
                200,
                json.dumps(report, indent=2).encode("utf-8"),
                "application/json",
                {"Content-Disposition": 'attachment; filename="r3a3f_crawl_report.json"'},
            )
            return
        query = (params.get("q") or [""])[0]
        category = (params.get("category") or [""])[0]
        body = render_html(report, self.server.staging, query, category).encode("utf-8")
        self._send(200, body, "text/html; charset=utf-8")


def serve(db_path: str, staging_path: str, port: int = 8787) -> HTTPServer:
    # Single-threaded on purpose: the sqlite handles are opened once here and
    # must be used from the same thread. A local read-only console has no need
    # for concurrent request handling.
    store = Store(db_path)
    staging = StagingIndex(staging_path)
    server = HTTPServer(("127.0.0.1", port), _Handler)
    server.store = store
    server.staging = staging
    server.config = CrawlConfig(allow_loopback=True, loopback_hosts=("127.0.0.1",),
                                min_interval_s=0.0)
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only R3-A3F crawler console")
    parser.add_argument("--db", required=True)
    parser.add_argument("--staging", required=True)
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    server = serve(args.db, args.staging, args.port)
    print(f"dashboard: http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
