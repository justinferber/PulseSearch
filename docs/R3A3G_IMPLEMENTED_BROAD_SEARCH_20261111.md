# Pulse Search R3-A3G — Implemented broad-search increment
**11 Nov 2026 · development branch, offline by default · no production or crawler admission.**

## Owner goal

Find pages **people care about**, not Google volume statistics and not only event pages. Deliver navigation, relevant webpages and actionable information for:

- Global fireworks, Pride/CSD, music festivals, concerts, Christmas markets, Diwali, parades and 18 existing event-category facets.
- Practical questions: "How do I book tickets for a concert in Berlin?", ticketing policies, venue guides, transit/accessibility, opening times.
- Common everyday searches: ChatGPT, Amazon, YouTube, Gmail, Wordle, weather, translation, Canva, shopping, sports and general questions.
- Broad general reference and how-to pages that have no event edition/date.

## Implemented in code (first increment)

1. \`pulse_search_broad_r3a3g/search.py\`: query intent classification, alias/official navigation, weather freshness guard, bilingual synonym support, FTS5-indexed candidate generation followed by lexical relevance ranking across staged title/snippet/URL, separate booking/how-to and general-document types, source citations/URLs, no invented answers or live prices.
2. \`pulse_search_broad_r3a3g/cli.py\`: read-only \`mode=ro\` search over the existing staging database; optional separately invoked SearXNG discovery. No implicit crawler activation.
3. \`pulse_search_broad_r3a3g/providers.py\`: an *opt-in* adapter to an explicitly configured SearXNG JSON API. Local/loopback service by default; remote HTTPS requires a deliberate operator flag. Results are sanitised links and transient snippets, marked **unverified, not indexed, not crawled, no rights assumed**. SearXNG JSON must have been enabled by the operator; its absence returns a provider error. No search requests occur merely by importing this module or viewing the owner dashboard.
4. \`pulse_search_broad_r3a3g/source_discovery.py\`: aggregates outbound hosts *already observed by the permissioned crawler*, ranks likely new event/venue/guide/transport sources for review without contacting them, rejects unsafe IP and URL schemes and keeps each candidate **NOT ADMITTED**.
5. R3-A3G additions to the R3-A3F link-priority \`topics.py\`: fireworks, ticket-booking/venue guidance and visitor/transport guides. These change **priority hints only**, never source permission, rights or max depth.
6. Owner dashboard: visible broad query intent, ranked staged results or official navigation, honest provider-freshness status, plus likely new source candidates in both the HTML view and JSON report. Original event dashboard sections remain intact.
7. \`tests/test_r3a3g_broad_search.py\`, \`test_r3a3g_source_discovery.py\`, \`test_r3a3g_provider_and_priority.py\`: regression fixtures for the 15 commonly requested intents **without using volumes**, multi-city festival queries, Berlin concert ticket guide, wrong-city ranking, general reference, provider-unavailable scenarios, false phishing/private URLs and optional local SearXNG. They were committed by this development increment (plus `tests/test_r3a3g_fts_retrieval.py` to test late-document FTS recall and revocation) but **must still be executed by FB2**; no passing result is claimed here.

## Run after pulling this branch

Offline search of **already accepted** staging pages:

\`\`\`bash
python -m pulse_search_broad_r3a3g.cli \
  --staging data/r3a3f_three_source/staging.sqlite \
  "How do I book tickets for a concert in Berlin?"
\`\`\`

The old three-source staging fixture cannot answer a Berlin ticketing guide reliably if no such guide was ingested. This absence should be reported as **no evidence**, not a fake answer. The new R3-A3G tests provide labelled synthetic guide fixtures for evaluation.

Once the owner already runs a SearXNG instance with JSON enabled, *explicitly opt in* to retrieval of external webpages:

\`\`\`bash
python -m pulse_search_broad_r3a3g.cli \
  --searxng http://127.0.0.1:8080 \
  "How do I book tickets for a concert in Berlin?"
\`\`\`

To compare both sources without permanently indexing provider snippets:

\`\`\`bash
python -m pulse_search_broad_r3a3g.cli \
  --staging data/r3a3f_three_source/staging.sqlite \
  --searxng http://127.0.0.1:8080 \
  "Pride festivals Germany"
\`\`\`

**No SearXNG endpoint has been confirmed connected in this session.** Example commands are not claims of executed live searches, working deployment or trusted search output.

Tests to run and report independently:

\`\`\`bash
python -m unittest discover -s tests -p 'test_r3a3g_*.py' -v
python -m unittest discover -s tests -p 'test_r3a3f_*.py'
\`\`\`

Re-run historical archived 419 checks, integrity hashes, frozen 54 replay, and compare search behaviour. Send both failing cases and successes.

## Honest limitations / immediate FB2 development tasks

- **Actual page discovery** now has two bounded routes: link candidates from already crawled, admitted sources; and opt-in query-time SearXNG **if a provider is configured**. Neither silently creates new crawler rights. Scaling coverage requires approved source onboarding, official/public service APIs and verified provider integration.
- Broad retrieval now uses the existing SQLite FTS5 index for OR/synonym candidate generation (up to 1,000 candidates) followed by intent-aware ranking; SQLite databases without FTS fall back to a labelled bounded 5,000-document scan. Benchmark FTS recall, prefix-token behaviour and multilingual accuracy against larger real permissioned corpora before production. The original index is not modified.
- Current weather and scores **need trusted live data providers**. The first increment returns a clear unavailable/current-provider-needed state rather than making data up. Translation needs a real translator and specified languages; a service-navigation link is not a translation result. Merchant prices and ticket availability are not live without verified provider evidence.
- The result pipeline returns evidence-backed **links** and snippets; it does **not** yet generate a full multi-step answer from verified official documents or perform purchases.
- Curated site navigation is a separate **link registry**, not a website crawler allowlist, and should be revalidated periodically. Do not conflate internal staging with provider search results.
- Broaden the source portfolio across multiple cities, genres and informational verticals. The event taxonomy is *facets*, not a restriction on what can be indexed. Preserve owner consent, indexing rights, robots, SSRF protections and revocation.
- Keep standalone Pulse Search independent of the UNA Events publication engine, PulseChat, ARIES and all other codebases.
- R3-A3F PR #10 remains draft; no first live crawler GET has been authorised. London Parade remains just one possible bounded safety pilot, not a product focus. City Hall and Lord Mayor's Show still have separate rights states.

**Immediate FB2 follow-through:** pull the R3-A3G branch; run/repair tests; show owner real broad query results from a correctly configured approved search source and evidence-labelled local fixtures; add source/ranking quality evaluations; build scalable retrieval; return exact hashes, failures and independent report before any production proposal.
