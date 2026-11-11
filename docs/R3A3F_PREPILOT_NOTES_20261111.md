# R3-A3F — pre-pilot notes and suggestions

**Date:** 11 November 2026. **Status:** notes only. Nothing here is implemented beyond the five
review corrections in `R3A3F_IMPLEMENTATION_20261111.md`; production remains **HOLD** and no
third-party host has been contacted.

## 1. What the five corrections changed, in one line each

| Review finding | Correction |
| --- | --- |
| Admission was effectively open | `Store.add_source` defaults to `approved=False`, `index_allowed=False`, empty `probe_policy`; re-import cannot de-approve or re-scope an admitted source; `StagingIndex.add_document` refuses to index without `index_allowed=True` |
| Guessed listing pages were indistinguishable from links | Probes are a reviewed per-source `probe_policy` with a per-run budget, stored as `guessed_path_probe`, `parent_url=NULL`, `approval_ref=source:<id>:probe_policy` |
| Pacing could end early; robots bypassed it | `pacing.HostPacer` is the single schedule for robots, content and redirects; waits are uncapped; a `Retry-After` blocks the host for its full duration |
| 404 was a permanent verdict | 404 → `state='recheck'` with a long TTL (168h for probes, 24h otherwise) and `max_rechecks`; 410/451/403 permanent with distinct counters |
| Fairness and yield were asserted, not measured | `claim_next(avoid_host=…)`, a per-source budget-share cap, measured per-source shares, and `useful_discoveries` / `useful_per_100_fetches` |

## 2. Suggestions, ranked by expected value for a first pilot

### P0 — implemented in response to the second security review

Source admission is now strict at every entry point: the CLI requires each admission field
explicitly, refuses approval without a reviewed rights basis and refuses seeds outside the approved
scope, and `run` refuses to start when nothing is admitted. Redirect destinations are new URLs: each
hop is re-checked for source, path, robots, request budget and pacing before the request is issued,
off-origin hops are refused even to public hosts, and every hop is logged. The pilot proposal is
narrowed to one host and one path with no probes.

### P1 — worth doing before or during the pilot

**1. Record a per-request evidence row for every network attempt, including robots and redirects.**
*Partly done:* every redirect hop now lands in `redirect_log` with its decision and reason, and the
report exposes `redirects.by_decision`. Still missing: a `pace_log` of the wait that preceded each
request, and folding robots/first-hop request rows into one per-run request ledger. *Effort: small.
Value: high for audit and dispute handling.*

**2. Persist pacing decisions, not just outcomes.** `HostPacer.waits` lives in memory and dies with
the process. Writing `(host, waited_s, reason)` to a `pace_log` table makes "we waited 600 seconds
because of Retry-After" reconstructible after a crash, which is exactly the kind of claim an owner
will be asked to defend. *Small.*

**3. A reviewed sitemap path.** Sitemaps are currently recorded as candidates only, which is safe but
wasteful: a publisher's own sitemap is usually the cleanest listing of event pages. Add an explicit
`source.sitemap_policy = "reviewed_allow"` with `allowed_paths` filtering, still depth-1 and still
robots-gated. Keep `candidate_only` as the default. *Medium.*

**4. Structured-event extraction from JSON-LD.** The extractor already reads JSON-LD. Mapping
`schema.org/Event` (`startDate`, `location`, `offers`, `eventStatus`) into the staging record would
let the pilot measure event usefulness instead of inferring it from titles, and gives the 54-question
review real fields to grade. No extra fetching is needed. *Medium.*

**5. Per-source auto-pause on low yield.** If a source accepts <10% of 50 fetches, pause it and flag
it for review rather than spending the rest of the daily budget. The fairness cap protects other
*sources*, not the budget itself. *Small, and a good pilot guardrail.*

### P2 — after the first pilot shows where the pain is

**6. Category balance as a measured quantity, not a hope.** Fairness is now host-level. Add a
`category_min_share` report and, only if a pilot shows starvation, a soft priority nudge toward
under-covered facets. Do not add hard category quotas: they would fight the "never block a topic"
principle.

**7. Near-duplicate scaling.** The shingle join is fine at pilot scale (~10⁴ documents) and will not
be at 10⁶. A MinHash/SimHash band index keeps recall while bounding cost. *Medium, defer until
volume demands it.*

**8. Robots conformance suite.** Add the RFC 9309 examples (and Google's published edge cases) as a
table-driven test. The parser's precedence rules are tested individually but not against a corpus.
*Small; useful insurance before contacting many hosts.*

**9. Conditional GET for `robots.txt`.** We cache for 24h but always refetch after that. Storing
`ETag`/`Last-Modified` for robots would cut one request per host per day, and is polite by
construction.

**10. Crash-safe run leases.** One `run_log` row and `reset_inflight()` are enough for a single
scheduler. A `lease` column with expiry prevents two processes on one database from duplicating
work, which is a realistic operator mistake.

**11. JS-rendered and PDF listings.** Many venue pages are client-rendered. Rather than bundling a
browser, detect "HTML shell with no text" and record it as `needs_render` so the pilot can quantify
how much is invisible and decide later whether a headless renderer is worth the complexity.

### P3 — hygiene and longer-term

**12. Property-based tests for canonicalisation and scope.** `canonicalize` is the security boundary
for scope and traps; a Hypothesis suite would find the `//`, `%2e%2e`, IDN and trailing-dot cases
that examples miss.

**13. A takedown queue.** Revocation exists (`staging.revoke`, `revoke_source`). A tiny owner-facing
list of "URLs to purge, with reason and date" would make rights obligations operational rather than
procedural.

**14. Report diffing between runs.** Daily pilot reports are JSON; a `--compare` mode that shows
new hosts, changed acceptance, new rejection reasons and pacing changes would make review minutes
instead of hours.

**15. Keep the config in the evidence.** `run_log.config` already stores the config dict. Add its
hash to `docs/evidence/` so a report can be tied to an exact configuration without trusting a
document.

## 3. What a pilot must measure (so the notes above stay honest)

| Question | Signal to record |
| --- | --- |
| Is politeness real against a live host? | per-hop wait log, `robots` rows, `Retry-After` handling, zero 429 repeats |
| Is admission actually fail-closed? | every fetched URL joins to an admitted source with `index_allowed=1` |
| Are probes worth their budget? | probe fetches vs accepted documents from probed paths |
| Is discovery useful or merely prolific? | `useful_per_100_fetches`, category coverage, intent distribution |
| Is any source starved or dominant? | per-source share of fetches vs the cap, plus queued work at run end |
| Does a 404 lifecycle work in the wild? | rechecks scheduled, rechecks that became 200, rechecks exhausted |

## 4. Deliberate non-goals

No topic filtering, no scope expansion through probes, no sitemap auto-admission, no body storage
without a licensing basis, no second crawler process, and no live crawling until the owner admits a
specific host in writing.

### Second directive (three candidates) — implemented

`registry.py` records City Hall, London Parade and the Lord Mayor's Show as candidates with separate
states; all remain unadmitted. The five operational gates from the F1 list are implemented and
tested: pre-network URL admission, persisted HTTP/accepted/run-duration limits, SHA-256 pinning of
the novelty index, and a distinct documented owner authorisation for any real host. Two offline
demonstrations exist: the original six-origin rig (28/28) and the three-candidate rig (30/30), the
latter also serving the console with per-source figures and novelty. The pace ledger (per-request
wait rows) is still the next audit improvement: pacing is enforced and measured in memory, and its
effect is visible in run duration, but individual waits are not yet persisted.
