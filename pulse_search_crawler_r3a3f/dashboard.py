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
    discovery = report.get("discovery") or {}
    fairness = report.get("fairness") or {}
    redirects = report.get("redirects") or {}
    novelty = report.get("novelty") or {}
    redirect_rows = "".join(
        f"<tr><td>{html.escape(str(decision))}</td><td>{count}</td></tr>"
        for decision, count in (redirects.get("by_decision") or {}).items()
    ) or "<tr><td colspan='2'>No redirects followed or blocked.</td></tr>"
    register = report.get("source_register") or {}
    candidates = register.get("candidates") or []
    candidate_rows = "".join(
        f"<tr><td>{html.escape(str(c['source_id']))}<div class='sub'>{html.escape(str(c['host']))}</div></td>"
        f"<td><span class='pill {'good' if c['state'] == 'owner_approved' else 'warn'}'>"
        f"{html.escape(str(c['state']))}</span></td>"
        f"<td>{'yes' if c['approved'] else 'no'} / {'yes' if c['index_allowed'] else 'no'}</td>"
        f"<td>{html.escape(str(c['rights_status']))}</td>"
        f"<td>{html.escape(', '.join(c['allowed_paths']) or '—')}</td>"
        f"<td>{c['staged_documents']} / {c['categories_covered']}</td>"
        f"<td>{c['discovered_links']} / {c['deepest_depth']}</td>"
        f"<td>{c['duplicates']}</td>"
        f"<td>{html.escape(str((c.get('novelty') or {}).get('novel_documents', '—')))}</td></tr>"
        for c in candidates
    ) or "<tr><td colspan='9'>No candidate register supplied.</td></tr>"
    novelty_line = (
        "Novelty versus the pinned index: "
        f"{novelty.get('novel_documents')} new of {novelty.get('staged_documents')} staged · "
        f"{novelty.get('already_in_historical_index')} already present in "
        f"{novelty.get('historical_index_pages')} historical pages."
        if novelty.get("status") == "MEASURED_READ_ONLY"
        else "Novelty versus the pinned index: not computed for this report."
    )
    provenance_rows = "".join(
        f"<tr><td>{html.escape(label)}</td><td>{count}</td><td>{html.escape(note)}</td></tr>"
        for label, count, note in (
            ("Admitted seeds", discovery.get("seed_admissions", 0),
             "owner-approved entry points"),
            ("Genuine link discoveries", discovery.get("genuine_link_discoveries", 0),
             "anchor on a fetched page; parent recorded"),
            ("Approved guessed probes", discovery.get("guessed_path_probes", 0),
             "reviewed listing paths; no link or parent claimed"),
            ("Successful pages", funnel["accepted"], "indexed or updated in staging"),
            ("Rejected pages", funnel["rejected"], "each with an explicit reason"),
        )
    )
    fairness_shares = fairness.get("share_by_source", {})
    fairness_fetches = fairness.get("fetches_by_source", {})
    fairness_rows = "".join(
        f"<tr><td>{html.escape(str(source))}</td><td>{count}</td>"
        f"<td>{fairness_shares.get(source, 0):.1%}</td></tr>"
        for source, count in sorted(fairness_fetches.items(), key=lambda kv: -kv[1])
    ) or "<tr><td colspan='3'>No fetches recorded yet.</td></tr>"
    intent_rows = "".join(
        f"<tr><td>{html.escape(i['label'])}</td><td>{i['documents']}</td>"
        f"<td>{'in season' if i['in_season'] else ''}</td>"
        f"<td>{html.escape(', '.join(i['categories']))}</td></tr>"
        for i in discovery.get("intents", [])
    ) or "<tr><td colspan='4'>No discovery intents configured.</td></tr>"
    prioritised_rows = "".join(
        f"<tr><td>{html.escape(p['url'])}</td><td>{p['priority']}</td>"
        f"<td>{html.escape(str(p['category_hint'] or ''))}</td></tr>"
        for p in discovery.get("prioritised", [])[:6]
    ) or "<tr><td colspan='3'>No intent-prioritised URLs yet.</td></tr>"
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

<section><h2>Discovery provenance — links, reviewed probes, outcomes</h2>
<div class="sub">Every URL records how it was admitted. A guessed listing path is never
reported as a discovered hyperlink: it carries an approval reference and no parent page.
In-season month: {discovery.get('seasonal_month', 'n/a')} · rechecks waiting:
{discovery.get('rechecks_waiting', 0)}.</div>
<table><tr><th>Origin of URL</th><th>Count</th><th>Meaning</th></tr>{provenance_rows}</table>
<div class="sub" style="margin-top:10px">Useful discoveries (staged documents carrying an intent):
{discovery.get('useful_discoveries', 0)} · {discovery.get('useful_per_100_fetches', 0)} per 100 fetches.</div>

<h2 style="margin-top:22px">Crawl budget fairness by source</h2>
<div class="sub">Fetches alternate between approved hosts, and no source may spend more than
{fairness.get('max_source_share_allowed', 0):.0%} of a multi-source run budget; the run defers
work instead. Largest share of this run's fetches
{fairness.get('max_source_share', 0):.1%} · fairness mode
<code>{html.escape(str(fairness.get('fairness_mode', 'n/a')))}</code>.</div>
<table><tr><th>Source</th><th>Fetches</th><th>Share of fetches</th></tr>{fairness_rows}</table>

<h2 style="margin-top:22px">Discovery focus — outdoor festivals, music, parades, seasonal markets</h2>
<div class="sub">Listing probes within approved paths: {discovery.get('probes_completed', 0)}/
{discovery.get('probes_total', 0)} completed. Intent reorders discovery and labels documents;
no topic, host or category is ever blocked.</div>
<table><tr><th>Intent</th><th>Documents</th><th>Season</th><th>Feeds categories</th></tr>{intent_rows}</table>
<table style="margin-top:12px"><tr><th>Priority-raised URL</th><th>Priority</th><th>Hint</th></tr>
{prioritised_rows}</table></section>

<section><h2>Three proposed sources — candidate, not admitted</h2>
<div class="sub">Owner scope decision: <code>{html.escape(str(register.get('owner_decision', 'n/a')))}</code>.
Real sources admitted: <b>{register.get('real_sources_admitted', 0)}</b>. A candidate is never presented
as crawled or indexed: the document, link and novelty figures below come only from the offline
synthetic fixtures named in the register, never from the real hosts.</div>
<table><tr><th>Candidate</th><th>State</th><th>Approved / index</th><th>Rights basis</th>
<th>Proposed paths</th><th>Docs / categories</th><th>Links / depth</th><th>Duplicates</th><th>Novel</th></tr>
{candidate_rows}</table></section>

<section><h2>Sources and rights</h2>
<div class="sub">{html.escape(novelty_line)}</div><table>
<tr><th>Source</th><th>Origin</th><th>Rights basis</th><th>Docs</th><th>Index allowed</th></tr>
{source_rows}</table></section>

<section><h2>Redirects — every hop re-authorised</h2>
<div class="sub">Followed hops {redirects.get('followed_hops', 0)} · blocked hops
{redirects.get('blocked_hops', 0)}. Each destination is re-checked for approved source,
path scope, robots, request budget and host pacing before the request is issued;
off-origin redirects are refused even to public hosts.</div>
<table><tr><th>Decision</th><th>Hops</th></tr>{redirect_rows}</table></section>

<section><h2>Freshness, errors and safety</h2><table>
<tr><th>Signal</th><th>Value</th></tr>
<tr><td>Revalidated unchanged (304)</td><td>{report['freshness']['revalidated_unchanged']}</td></tr>
<tr><td>Updated documents</td><td>{report['freshness']['changed_or_updated']}</td></tr>
<tr><td>Rate limited (429/503)</td><td>{report['errors']['rate_limited']}</td></tr>
<tr><td>Robots denials</td><td>{report['robots']['denied']}</td></tr>
<tr><td>Removed or denied (403/404/410/451)</td><td>{report['errors']['removed_or_denied']}</td></tr>
<tr><td>Redirect hops followed / blocked</td><td>{redirects.get('followed_hops', 0)} / {redirects.get('blocked_hops', 0)}</td></tr>
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
        report = build_report(self.server.store, self.server.staging, self.server.config,
                              historical_index=self.server.historical_index,
                              expected_index_sha256=self.server.index_sha256,
                              registry=self.server.registry)
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


def serve(db_path: str, staging_path: str, port: int = 8787,
          historical_index: str | None = None, registry_path: str | None = None,
          index_sha256: str | None = None) -> HTTPServer:
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
    server.historical_index = historical_index
    server.index_sha256 = index_sha256
    server.registry = None
    if registry_path:
        from .registry import load_registry

        server.registry = load_registry(registry_path)
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only R3-A3F crawler console")
    parser.add_argument("--db", required=True)
    parser.add_argument("--staging", required=True)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--historical-index", default=None,
                        help="optional pinned index for read-only novelty comparison")
    parser.add_argument("--index-sha256", default=None,
                        help="expected SHA-256 of the historical index (pin check)")
    parser.add_argument("--registry", default=None,
                        help="optional three-candidate source register JSON")
    args = parser.parse_args(argv)
    server = serve(args.db, args.staging, args.port, args.historical_index,
                   registry_path=args.registry, index_sha256=args.index_sha256)
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
