# Owner correction — Pulse Search is a broad search and knowledge engine, not a London Parade crawler
**Date:** 11 November 2026
**Project:** Standalone `justinferber/PulseSearch`; **not** Pulse UNITY Events or the UNA event publisher.
**Owner direction:** "Why is it concentrating on just London Parade? That is just One event. We should be cataloguing the Fireworks, Pride festivals, Music festivals etc +++ All the other information such as How to book tickets to a concert on Berlin or something like that."

## 0. Correct the fundamental scope error

London Parade was only intended to be **one source in a tiny live-crawler safety pilot**. It is not a thematic limit, not the main index and not the intended user experience. City Hall and the Lord Mayor's Show are likewise *test source candidates*, not the source universe.

The existing `docs/R3A3F_DEPTH3_CRAWLER_ARCHITECTURE_20261111.md` already targets up to ~1,000 **new relevant searchable** pages/day, 18 event categories as facets rather than a filter, and explicitly permits content that is not a named event edition. The latest engineering and signoff thread became overly concentrated on three sites. Restore the broader product charter now.

**Product charter:** General-purpose, AI-assisted discovery, indexing, search and citation-grounded answers, with **events and practical city/ticketing information as initial high-value verticals**. Not event-only and not restricted to Mine Media clients. Mine Media's extensive client relationships are a valuable *source acquisition* route, not the definition of what Pulse Search can index.

## 1. Content and question types Pulse Search must support

These axes are **independent**: `document_type`, `topic`, `event_category`, `location`, `time/edition`, `source_rights`, `answer_intent`. A page need not be classified as an event to be searchable.

**A. Event discovery, globally:** fireworks (New Year's Eve and local displays), Pride/CSD/LGBTQ+ events, music festivals, gigs, concerts, Christmas markets, cultural and religious festivals (Diwali, etc.), street festivals/Stadtfest, parades/processions, sport, exhibitions, conferences, performances, local family events, charity/community events, markets and everything else across the 18 existing primary *event* category facets. No hardcoded preference for three named events. Introduce cross-facets `Fireworks`, `Open Air`, `Free`, `Family`, `Accessibility`, `Seasonal`, `Ticketed` as appropriate rather than inventing new exclusive primary categories.

**B. Practical how-to / guidance:** "How do I book tickets to a concert in Berlin?", "Where can I buy official tickets?", "How do I get to the venue?", "Is it accessible?", "What are the refund rules?", "How do I find fireworks near me?" Use verified official booking instructions and links, venue guidance, promoter or authorised ticketing pages, public transport links and source-specific warnings. Do not claim a ticket, price, stock, checkout path or current availability unless verified from appropriate current evidence. No live purchase actions.

**C. General web knowledge:** venue and destination guides, museums, attractions, event organisers/artists, local travel/logistics, service FAQs, official instructions, explanatory articles and other information relevant to natural-language questions. Architecture must not require `event_date`, `venue` or 18-category eligibility for useful non-event material. Search outside these verticals should remain feasible via source-policy-approved indexes or a separately permissioned metasearch/retrieval channel.

**D. Sources:** event/venue/organiser websites, official schedules/calendars, tourism/city authority guides, public transport, official ticketing help pages, newspapers/blogs where permitted, structured data `schema.org`, authorised feeds, and selected Mine Media partner sources. A discovered external host is a *candidate*, not automatically fetchable. Commercial client permission is recorded per client and actual source rights; do not auto-admit hundreds of client sites from the London Parade attestation.

## 2. Architecture: separate retrieval, understanding and answering

Design and implement in bounded stages:

1. **Source discovery and permissioned admission**: broaden a proposed source catalogue across event categories, cities, languages, `document_type` and rights status. Candidate discovery may come from approved search-provider APIs, reviewed seed submissions, links from approved hosts, client-provided feeds, or human research. No unapproved third-party crawler GETs. The source register holds origin/path rights, source reliability and takedown obligations.
2. **Multi-document ingestion**: distinguish `event_detail`, `event_listing`, `venue`, `official_booking_guide`, `transport_guide`, `FAQ/how_to`, `programme`, `news`, `general_reference`. Apply dedup, provenance, locale, last verified, extraction confidence and expiry. Use date/edition structure only for event items; preserve evergreen how-to documents independently.
3. **Understanding and normalization**: identify official source, exact evidence for date/time/timezone, place/city/country, organiser, venue, price *when verifiable*, event status (announced/cancelled/postponed), booking process and official booking link. Do not confuse `when published` with `when event occurs`. Do not fabricate a booking link or infer next year's date.
4. **Retrieval and ranking**: retain FTS, frozen original 120-page index/BGE research and 54 human review baseline untouched; develop isolated broader staging and a query planner for `find events`, `how-to`, `navigate to official page`, `compare`, `factual question`, `location/time` and `general information`. Hybrid lexical/semantic ranking can be researched offline only; source quality, freshness, intent fit, category diversity and dedup must be scored separately.
5. **Cited answer layer**: results should answer "How do I book tickets to a concert in Berlin?" with actionable steps, official site or organiser links where supported, date of verification, ticketing caveats and optional source links. If sources are missing/ambiguous/outdated, clearly say so and give safe navigation rather than invented facts. Search results and generative answers are different output types; answers must cite and be permissioned, with transparent uncertainty.
6. **UI owner console**: show source catalogue and approval status, topic/category/source mix, event vs guide vs venue document type, query intent coverage, geographical breadth (incl. Berlin, London and worldwide), novel relevant indexed documents and actual tested answer quality. A three-event dashboard is not sufficient.

Review whether the previously researched SearXNG/search-provider approach can provide *source discovery and live query retrieval* without improperly treating search snippets as a permanent content-reuse licence; keep its role distinct from permissioned crawling and the user-facing grounded-answer layer.

## 3. Example acceptance tests — synthetic / no live crawling

Create a new independently gradeable set (do **not** reuse the owner's frozen 54) with representative German and English queries. For each, assert query intent, selected document types, freshness/location constraints and appropriate evidence/citations.

- "Fireworks displays in London this New Year's Eve" — distinguish announced dates from historical displays; official source, venue, restrictions.
- "Pride festivals in Germany next summer" — CSD/Christopher Street Day / Pride wording, city/date and multiple editions, not just Berlin.
- "Open-air music festivals in Europe" — multi-source coverage, seasonal events and venue links.
- "Christmas markets in Berlin" — `Weihnachtsmarkt`, opening/closing dates and year.
- "How do I book tickets for a concert in Berlin?" — identify official organiser/venue/ticket page; step-by-step how-to, source link, no made-up price or availability, no unauthorised checkout.
- "Where can I get tickets for a festival?" — official source versus uncertain reseller, explanatory fallback.
- "How do I get to a concert venue by public transport?" — recognise guidance, not an event edition.
- "When is London Parade 2027?" and "What happened to the 2021 edition?" — edition accuracy.
- "What is the Lord Mayor's Show?" — general explanation from permissible evidence, not forced into a single future event.
- "Events in Berlin excluding Christmas markets" — query-local negation, no global exclusion of market documents.
- "What is a public transport day ticket?" — valid non-event general informational query with citations.
- Ambiguous or missing-data examples must refuse unsupported dates, locations, ticket stock or opening times.

Minimum offline evaluation dimensions: how-to top-3 recall and evidence accuracy; multi-source/multi-city event recall; current vs historical separation; link accuracy; source-policy compliance; protected/community topics present; general informative page retrieval even without an event record. Publish failure cases, not just all-PASS synthetic fixtures.

## 4. Development and release sequencing

- **R3-A3F safety pilot**: retain its audited branch/PR #10, completed robots and admission gates, City Hall/London Parade/Show source records, frozen corpus and separate live pilot approval. London Parade remains a possible *technical first-live source*, not the crawler's product focus. No new live request is authorised by this directive.
- **New bounded R3-A3G broad-search track**: create a **new distinct branch and draft PR**, based on the current verified R3-A3F head (or exact reviewed merge base if directed by repo maintainers). Do not add unrelated broad search architecture work to PR #10. Begin with an explicit source discovery and query taxonomy design, then functional offline implementation + tests for multi-category events and actionable how-to query retrieval.
- **Stage A**: source inventory across multiple countries/cities, six+ distinct source families, proposed rights, event facets and non-event document types, no live GETs by crawler.
- **Stage B**: multi-document extraction + normalization + hybrid/relevance retrieval in a new staged corpus; Berlin ticketing how-to fixture must work alongside seasonal festival searches.
- **Stage C**: evidence-grounded answer UI and honest links with source timestamps; measure error rates using independent owner-reviewable queries.
- **Stage D**: source-by-source live admission and staged ramp from a tiny trial toward the aspirational 1,000 *useful new indexed* pages/day, preserving per-host fairness, no rate-limit evasion. Not a 1,000/day promise.
- **Operational**: maintain source/copyright control, privacy minimization and easy revocation, per-source provenance, robots and full redirect pacing, no external unapproved host fetches, no automatic publication into Pulse UNITY Events, no launch or production scheduler until specifically approved.

## 5. Deliverables from FB2

1. A corrected **Pulse Search product charter**, distinguishing global event discovery, practical how-to guidance, general knowledge retrieval, and the narrowly bounded live-crawler *pilot*.
2. Proposed source families and source registry data (including at least several independent event types/locations and official ticketing/how-to sources; all unapproved until their own rights and robots review).
3. Functional offline tests/results for Berlin concert ticket how-to, Fireworks, Pride, music festivals, Christmas markets, London Parade and broader general-information questions.
4. Query planner / document-type data model, relevance failures and an owner browser demonstration of **both** event results and sourced how-to answers.
5. New draft PR (R3-A3G) link, commit, test receipts and unchanged original 120-page index/model/54 review hashes.
6. A written multi-source live-pilot expansion plan that stays separate from the London Parade P1 authorisation and labels what is merely synthetic.

**Acceptance:** An independent user must be able to see that Pulse Search answers a practical Berlin booking question using supplied licensed synthetic sources and finds diverse festival/event categories across geographies. London Parade cannot dominate the demo or be the only usable named subject. No permission is inferred for other clients, and no live crawler fetch is started from this scope correction.

**Owner principle:** *Index broad useful information, retrieve the most relevant evidence, and answer real questions accurately. The crawler is only one input; London Parade is only one example.*
