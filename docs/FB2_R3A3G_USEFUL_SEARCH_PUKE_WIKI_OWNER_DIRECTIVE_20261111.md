# FB2 — R3-A3G owner directive: Useful Search, Clean Answers, PUKE API and Wiki Knowledge Pipeline
**Date:** 11 November 2026  
**Owner-approved direction:** R3-A3G working development, mostly FREE/self-hosted components, standalone Pulse Search.  
**Branch:** fb2/r3-a3g-broad-search-query-intents-20261111 · **PR:** #11 draft.  
**R3-A3F crawler safety PR #10:** separate, unchanged and still draft. No production release or third-party crawler activation by this directive.

## 1. Owner correction: stop building a costly question-answering demonstrator

Pulse Search must **find genuinely useful pages for arbitrary user queries**. It is independent of the Pulse UNITY Knowledge Engine (PUKE), but PUKE must be able to ask Pulse Search *any question*. Search may return links, contextual snippets, verified structured answers and a clear no-answer state. Do not require a language model or paid API for routine navigational queries.

Example: "What is the weather in London?" A good FREE answer is: "For the latest London forecast, see BBC Weather and the UK Met Office," with authentic source URLs. **Do not give an invented temperature, call a paid weather API, or refuse when useful official forecast webpages can be linked.** "Weather tomorrow" links to forecast services, never labels *current observations* as tomorrow's forecast. Optional live weather remains a plugin/capability with separate licensing and validity checks, not a default dependency.

Weather links for the initial UK source catalogue: https://www.bbc.co.uk/weather (BBC Weather) and https://weather.metoffice.gov.uk/forecast/uk (Met Office UK forecast). For Germany include https://www.dwd.de/ as a **national weather source**, without inventing a direct local forecast URL. These are trusted navigation **leads**, not permission to scrape weather datasets. Verify maintained URLs in the integration environment; handle link or country changes.

Other examples:
- "How do I buy concert tickets in Berlin?" → official concert/venue/organiser ticket instructions + current source link; if absent, honest official-ticket search/navigation, not an empty refusal or fake ticket stock.
- "Pride festivals Germany" / "Fireworks London" / "Music festivals Europe" → diverse source-backed links and event editions, not only London Parade or one website.
- "ChatGPT" / "Gmail" / "Canva" / "Wordle" → exact official navigation, not SEO clones.
- "FIFA World Cup" → official information and sources; scores require a live provider.
- "Translate English to German" → route to an authorised translator/service; do not claim a translation was performed if none was.
- General wiki questions → relevant official/reference pages, sourced extractive summary if evidence exists, otherwise useful links.

**No monthly keyword-volume analytics or another narrow event pilot in this workstream.** The 15 popular queries are a minimum **behavioural regression set**, not a list to hardcode or overfit.

## 2. Improve the search algorithm itself, in code

Implement a reproducible multi-stage pipeline, not a large growing curated fact list:

**(a) Understand the question.** Unicode/language-aware normalisation, entity/place detection, location and time, spelling/aliases (Chat GPT↔ChatGPT; Konzert↔concert; CSD↔Pride), negation ("Berlin events excluding Christmas markets"), and intent: OFFICIAL_NAVIGATION, WEATHER/FORECAST_NAVIGATION, EVENT_DISCOVERY, HOW_TO/TICKETS, CURRENT_INFORMATION, TRANSLATE, FACTUAL, GENERAL_SEARCH. Event date is NOT a requirement for general informational pages.

**(b) Gather real candidates from the right channel.** Sources: already licensed staging index FTS5/BM25; reviewed official-source directory; optional explicitly configured local SearXNG for ephemeral web discovery; approved feeds/provider APIs only where configured. Never imply that SearXNG results were crawled, verified, licensed for permanent indexing, or are live facts. Merge/normalise source URLs carefully, deduplicate redirects/canonical URLs and near-duplicates, retain original citations and publisher; no arbitrary off-domain crawling. Clear fallback when a provider is unconfigured.

**(c) Rerank for usefulness.** Use an explainable blend of BM25 relevance, entity and language match, location/date/edition fit, document type, official/primary-source quality, rights/source eligibility, freshness where time-sensitive, and domain/source diversity. A relevant official Berlin venue guide must outrank a London ticket page for a Berlin booking query. Avoid repetitive ten-results-from-one-domain and SEO/thin pages. Show ranking features and rejection reasons in owner JSON. Research pinned offline BGE or other free semantic reranking ONLY if separately measured against unseen human-graded queries; do not promote unvalidated model outputs. Calibrate thresholds to avoid irrelevant one-word matches.

**(d) Clean up the presentation.** For each query choose the best response format:
1. OFFICIAL LINK — title, verified publisher, short description and clickable URL.
2. SEARCH RESULTS — 3–8 ranked, deduplicated, diverse source cards, optional location/date chips.
3. EXTRACTIVE ANSWER — 1–3 concise sentences/steps actually grounded in licensed source evidence, links and verification time.
4. CURRENT SERVICE HANDOFF — official weather/translation/sports/ticket provider page with explicit "see current information there" and no fabricated live value.
5. UNKNOWN — say evidence is insufficient; show useful verified navigation if available.

Never take instructions from page snippets. Do not transform a page snippet into an asserted answer merely because its host is in a trusted list. Distinguish *official website*, *source admissible for indexing*, *fact independently supported*, and *fresh current observation*. Use source-linked claim spans or a supported fact record; otherwise keep text as attributed excerpts and links. Strip repetitive boilerplate; cap excerpts according to each source's licence; escape HTML; remove obvious malicious/instruction-like content without accidentally rewriting factual sentences.

**(e) Guard freshness/accuracy.** Historical events vs announced editions; no future dates invented; source-as-of timestamp; reviews for changed booking rules, expired events or removed pages. A weather navigation result is always legitimate regardless of whether a live weather adapter is present. If a live adapter is later used, distinguish current conditions from tomorrow's forecast, reject future/invalid timestamps and check commercial provider terms.

### Minimum acceptance dataset
Build an owner-reviewable independent set of **60+ distinct English/German real-world question patterns** with labelled expected intent, source types and relevance, including:
- the 15 owner-supplied popular query *behaviours* (no volume data);
- London/Manchester/Berlin weather now and tomorrow, with navigation-only provider-off mode;
- Berlin concert booking, flight booking, transport to venue, accessibility, refund guidance;
- multi-city Fireworks, Pride/CSD, music festival, Christmas markets, cultural and general information;
- exclusion/negation, misspellings, ambiguous cities, prior-year dates, cancellations;
- phishing/fake official sites, irrelevant-but-trusted snippets, expired pricing/stock and revoked sources.
Measure Recall@3, MRR/NDCG@5, helpful official-link rate, wrong-city rate, unsupported-answer rate, citation accuracy, source diversity, latency and number of no-evidence cases. Keep raw failures visible in browser and JSON. No 100% synthetic fixture score accepted as proof of open-web quality.

## 3. PUKE ↔ Pulse Search: independent, versioned server API

**Critical architecture**: Pulse Search is a standalone search product, own repo, own index, own service and deploy lifecycle. **PUKE is a client**, never the search index owner. Other services/ARIES/clients may later use the same contract with separate permissions.

Implement and test a stable versioned **read-only query surface**, e.g.:
- POST /v1/search: {query, lang?, country?, city?, time_range?, limit?, consumer_context?}; response {status, intent, result_cards[], source_ids[], retrieved_at, notices[], request_id}.
- POST /v1/answer: {question, language?, context?, max_sources?}; response {status, response_mode, answer?, claim_evidence[], citations[], freshness, confidence_calibration, limits[], request_id}.
- GET /v1/health and a capability endpoint telling callers what is available (local index, ephemeral provider, live weather if licensed, languages).
- POST /v1/wiki-candidates (separate service-to-service and restricted): propose **public-evidence-only, source-cited article candidates** to the Wiki workflow; never publish user conversations or private member content.

Use existing Pulse UNITY identity/service authentication (OIDC/OAuth where appropriate) for the **PUKE client** and an authenticated gateway. Scope by consumer, rate-limit, cap payload size and latency, redact query logs where needed, emit request IDs and enforce timeouts/retries/circuit breakers. No raw SQLite connection or direct library file access from PUKE; no requirement for a Pulse UNITY account just to run standalone Pulse Search. The current unauthenticated localhost console MUST remain loopback-only. No public server bind before an independent security/abuse review.

PUKE can ask arbitrary questions and must get one of ANSWERED / RESULTS / OFFICIAL_LINKS / CURRENT_SERVICE_HANDOFF / NO_EVIDENCE / NOT_AVAILABLE; absence of event date/categories may never cause arbitrary general questions to be rejected. Allow PUKE to attach its *own permissioned context* without forwarding member secrets into third-party search providers, and never leak caller private data into the public Wiki.

## 4. Wiki: actually turn evidence into lasting pages, not raw search dumps

The Wiki is a **separate authorised publisher** owned by Pulse UNITY. Pulse Search only returns source-linked public evidence and/or proposes a topic/article record. **No SQL or direct unauthorised API writes into UNA/Pulse UNITY Wiki.** Inspect the actual installed Wiki module, page/ACL/version and editorial interfaces first. If the supported Wiki API does not exist, implement an explicit adapter under PUKE/UNA with tests, rather than assuming a URL endpoint.

Build the following pipeline:

Search result / verified factual answer
→ candidate article/topic (canonical entity or subject)
→ source provenance and publication rights check
→ deduplicate existing Wiki page/aliases/edition
→ generate short neutral draft with source-by-claim citations and last verified date
→ Wiki draft/review queue with preview/diff/change history
→ owner/editor approval or a **separately owner-authorised ruleset** for limited automatic publication
→ publish/update existing page, never duplicate or overwrite user edits blindly
→ scheduled re-verification and correction/retraction when sources change or are revoked.

**Publication rules:**
- Aggregate reusable, public-interest knowledge (e.g. "How to book concert tickets in Berlin", "UK weather forecast sources", "Pride festivals in Germany") instead of creating a page every time a user asks "weather London today". Do not persist transient temperatures, live prices, private queries, individual member questions or provider-derived copyrighted text without publishing rights.
- Article is not publishable from a single generic search snippet; require sufficient claim-level evidence, provenance, rights and non-duplicate topic identity. Distinguish unverified web discovery leads from licensed indexed evidence. Images only where use rights allow, with source credit.
- Every Wiki page keeps stable topic ID, canonical slug, locale, source URLs, verified_at, author/reviewer, source rights class, publication status, reference to original evidence and version/revision. Public links remain clickable.
- Start by generating **5–10 real-looking offline Wiki draft previews** covering evergreen booking and practical guides, venue directions, Pride/fireworks guides and official weather-service navigation. Demonstrate one draft update, duplicate merging, citation integrity, source revocation → article flag/unpublish, owner review approval and no PII leakage.
- The owner wants published Wiki pages: **implement a real publish/update adapter and approval capability**, not simply a static report. Before any real public Wiki writes, verify the existing Wiki module's permissions and obtain a separate deployment/publication authorisation. Once a signed source/publish policy is in place, routine pages in defined categories may publish automatically; ambiguous/time-sensitive items remain reviewed. Draft creation and local workflow tests may proceed immediately.

This is a **consumer integration**. Pulse Search is NOT renamed to Pulse UNITY KE, and does not become part of the UNA Events Engine. Event pages proposed to the Wiki remain independent from event-edition publishing/approval workflows.

## 5. Work order — code and demonstration, not architecture theatre

**M1 — Search relevance and result UX:** implement query router, source service handoff, stronger FTS ranking/cleaning, 60+ adversarial acceptance set, and show browser results for 10 user questions. Fix the existing "weather tomorrow" bug in R3-A3G, never confuse a source link with a current observation. Preserve existing crawler safety and historical hashes.

**M2 — Search service API:** working authenticated/localhost versioned API and standalone sample client. Simulate arbitrary PUKE queries; prove no private-context leakage, strict provenance, read-only index access, error/freshness states, honest no-answer and per-consumer limits. Capture request/response fixtures.

**M3 — Wiki draft + publisher integration:** inspect real UNA Wiki API and ACLs, implement consumer-side queue/publisher adapter with source/rights and editorial controls; demonstrate drafts, update of an existing page, rejection and revocation in tests. DO NOT claim real wiki pages are published until confirmed by Wiki responses and owner deployment authority.

**M4 — Source expansion and independent quality:** add genuinely diverse source candidates and permissioned feeds across countries/languages/event + non-event information; real publisher discovery via configured SearXNG but not automatic indexing; human-grade 60+ cases, compare with R3-A3G baseline. Track useful **answer coverage**, not monthly keyword volumes or only raw fetches.

### Concrete delivery receipts FB2 must provide
- Exact branch, commit, draft PR #11 updates and remaining PR #10 separation; no silent main merge.
- Test logs with pass/fail counts; old 129 crawler + historical 419 regression verified; frozen original 120-page index SHA and 54-case replay unchanged.
- One browser console demonstrating weather → **official links** without API; Berlin concert ticket how-to → credible webpages; fireworks/Pride/music → diverse relevant results; general navigation queries.
- Example structured POST /v1/search and /v1/answer outputs with citations, provenance, truthfully labelled sources and timing.
- 5–10 Wiki draft previews and real publish-adapter integration evidence (test environment only until authorised).
- Owner acceptance report: examples that work, unsupported answers/why, source diversity, rights, how cost stays near zero and what requires future paid/licensed integration.

**Do not report "done" merely for a plan or curated fact pack. Implement, execute tests and demonstrate useful search results in the browser.**

## 6. Release boundary

- No default commercial paid APIs; use free/local and existing approved resources first; source licences and API terms still apply.
- No new live crawler admissions from this instruction; no bypass of robots/rights, no permanent re-use of unauthorised SearXNG snippets.
- No public unauthenticated member API; no live public Wiki publishing before owner-approved editorial and integration gates.
- No public claims that Pulse Search has indexed the whole web or that synthetic fixtures prove a thousand real useful pages/day.
- Keep codebases and PRs separate: PulseSearch R3-A3G for algorithm/API; Pulse UNITY/UNA for the KE client and Wiki publisher, using a shared versioned contract.

**Owner's product principle:** "If a user wants today's weather, help them find BBC Weather or the Met Office. If they want to book a Berlin concert, help them find the official booking information. If PUKE asks anything, return the best sourced result. Build lasting Wiki knowledge only when evidence supports it."
