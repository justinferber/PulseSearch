# R3A3G M9 — correct the review findings

M9 is a corrective pass, not another planning milestone or benchmark. It keeps
the independent search/PUKE/Wiki boundaries from M8.

## Corrections

### 1. Page text and curator metadata are separate

`docs` now has a separate `metadata` column. Captured descriptions remain in
`snippet`; reviewed topics, jurisdiction, document type and authority are stored
as curator metadata and returned as a separate card object. Search may use those
tags for candidate ranking/admission, but a card reports
`support_basis: "metadata_assisted"` when the support came from tags rather than
page text. It never renders tags as a quotation.

`tools/r3a3g_m8_demo.py` and the evaluator index only the captured description
as the excerpt and pass tags through `metadata`.

### 2. Evidence is admitted before generic link fallback

The early refund handoff was removed. Refund questions now rank admitted pages
first and enforce support before falling back. A supporting consumer page is
returned; otherwise reviewed official navigation remains the safe fallback.
A general consumer-advice page may be admitted with
`metadata_assisted` support when its reviewed tags cover the refund topic.

### 3. Rights and source identity refresh on update

`add_document()` now refreshes `source_id`, `rights_mode`, `metadata` and
`provenance` when an existing URL is captured again. A prior evaluation-only
approval cannot silently become a Wiki content licence. The M8 manifest
approval remains evaluation approval only; no Wiki publication was performed.

### 4. Network bounds are explicit

`SearxngDiscovery` uses a no-follow redirect opener and verifies the final URL
is still loopback. A provider redirect is reported as `UNAVAILABLE` and the
destination is not fetched.

`CapturePolicy.paced_fetch()` calls the per-source attempt ceiling before every
robots or page request, so a denied attempt issues no network request. The
existing pacing, redirect gate, robots and SSRF controls remain in place.

### 5. UNA transaction and test isolation

UNA now re-reads the latest revision inside the transaction, writes the actual
`profile_id` rather than `0`, and checks the requested base revision again
during retraction. The staging test clones a dedicated disposable block,
deletes its revisions and block in cleanup, and no longer writes to the existing
`wiki-home` block.

## Evidence

- M8 source capture: **10/11 HTTP 200**; Berlin museums remains a documented
  redirect failure.
- M8 demonstration: **13/14** cases produced a specific or official result;
  one honest no-evidence result, and provider leads remain `NOT_CONFIGURED`.
- Standalone authenticated API (PUKE client): **10 questions** —
  **7 indexed results**, **2 official navigation**, **1 no evidence**.
- Frozen 22-question M8 evaluation after M9 changes:
  - nDCG@5 **0.608**
  - returned-link Precision@3 **0.394**
  - fixed-denominator Precision@3 **0.212**
  - helpful top-1 **0.591** (13/22)
  - judged top-five **15**
- Python suite: **278 tests OK** on the final run. One earlier run hit a
  transient Windows `WinError 10053` connection abort; the clean rerun passed.
- UNA guard: **9/9**; UNA staging: **10/10**.

## Remaining limits

- UNA page creation still requires operator UI approval; the HTTP/session/CSRF
  path is not yet validated.
- No SearXNG endpoint is configured, so live provider leads are not claimed.
- The Berlin museums source remains a failed redirect capture.
- The API still has weak answers for some city/date queries; the M9 demo does
  not turn those into invented evidence.
- No production deployment, uncontrolled crawl, crawler admission, public Wiki
  publication or paid integration occurred.
