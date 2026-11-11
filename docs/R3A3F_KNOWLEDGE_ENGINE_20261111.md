# Pulse UNITY knowledge engine — safe answer layer

**Date:** 11 November 2026 · **Status:** local, offline-tested · **Production HOLD** unchanged.

The crawler finds and stores pages. This layer turns that index plus a small, owner-curated fact
pack into **answers with citations** for Pulse UNITY's Knowledge engine, Wiki and member questions.
It is deliberately not a chatbot: there is no language-model generation in the answer path and no
invented fact, price or date.

## The three example questions

| Question | Behaviour |
| --- | --- |
| *When is Glastonbury on next year?* | Answered from the curated event fact: **Wednesday 23 to Sunday 27 June 2027**, citing the organiser's own announcement. “Next year” is checked against the fact's year; a 2028 question is refused rather than having the date moved. |
| *What is the weather in London or Berlin today?* | With the live adapter enabled, current observations for both cities with an observation time, source and a 30-minute freshness limit. With it disabled, `LIVE_SOURCE_REQUIRED` — the build says it cannot answer and does not guess. |
| *Can you name place to buy flight tickets?* | Lists official airline/airport/regulator channels. It does **not** quote, rank or invent fares; it says so, and there are no affiliate links. |

## Safe-build guarantees

1. **Evidence or refusal.** `ANSWERED` requires either a structured fact with a trusted source or an
   accepted staging page. Otherwise the status is `NO_EVIDENCE` / `LIVE_SOURCE_REQUIRED` /
   `NEEDS_CLARIFICATION` / `REFUSED`.
2. **Host allowlist.** Citations are accepted only from `policy.trusted_hosts` (and its subdomains).
   An untrusted hit is counted in `gates.untrusted_hits_blocked` and never cited.
3. **Page text is evidence, not instruction.** Snippets are shortened to 320 characters and
   instruction-like text (`ignore previous instructions`, `SYSTEM:`) is replaced. The answer is
   assembled by templates; a page cannot change the answer's status or add a claim.
4. **Facts are versioned.** Every event carries `source`, `retrieved_at` and `verified_at`; facts
   older than 180 days are marked for recheck, and a finished edition is labelled as finished.
5. **Live data is explicit.** Weather is fetched only when `--live-weather` is passed (keyless
   Open-Meteo adapter). It sends coordinates only, caches nothing in the index, and refuses stale
   observations. No live fares are fetched at all.
6. **Sensitive questions are refused.** Medical, legal, financial-advice and account-security
   questions get a handoff message.
7. **Read-only index use.** The answer layer reads the staging index; it never writes documents,
   never crawls, and the existing staging search still logs the query only.

## API contract for pulseunity.co

Server-side call (keep the crawler local or behind your own network; do not expose the SQLite
console directly to the internet):

```
GET /api/ask?q=When%20is%20Glastonbury%20on%20next%20year%3F
```

```json
{
  "status": "ANSWERED",
  "intent": "event_date",
  "question": "When is Glastonbury on next year?",
  "answer": "Glastonbury Festival is scheduled for Wednesday 23 June 2027 to Sunday 27 June 2027 (5 days) at Worthy Farm, Pilton, Somerset, England.",
  "citations": [{"title": "Glastonbury 2027 ticket information confirmed",
                  "url": "https://www.glastonburyfestivals.co.uk/news/...",
                  "publisher": "Glastonbury Festivals", "kind": "source"}],
  "confidence": 0.95,
  "freshness": "2026-11-11T00:00:00+00:00",
  "limits": [],
  "gates": {"trusted_hosts_only": true, "live_fares": false, "generated_text": false}
}
```

Integration rules for the Pulse UNITY server:

- Call it server-side from your member API; add your own authentication, per-member rate limit and
  query logging policy. This layer has no accounts and processes no personal data.
- Treat `NO_EVIDENCE` / `LIVE_SOURCE_REQUIRED` as a normal UI state: show the reason and the
  suggested official source, not a guess.
- Cache `ANSWERED` event answers for a day and weather for its stated freshness window; do not cache
  refusals as facts.
- Render `citations` as visible links. Do not strip them: the citation is the trust signal.

## Adding a fact

Edit `config/knowledge_pack.json`:

- **Event:** `name`, `aliases`, `start`, `end`, `venue`, `status`, `date_note`, `ticket_note`,
  `source` (title/url/publisher/retrieved_at) and `verified_at`. Only add dates announced by the
  organiser.
- **Weather place:** `name`, `country`, `latitude`, `longitude`, `aliases`.
- **Buying channels:** name + official URL; no affiliate or tracking links.
- **Trusted host:** add the publisher's registrable domain only, not a URL path.

Re-run `python -m unittest discover -s tests -p "test_r3a3f_answers.py"` and
`python tools/r3a3f_knowledge_demo.py`.

## Local console

```
python -m pulse_search_crawler_r3a3f.dashboard --db data/r3a3f_three_source/crawl.sqlite \
  --staging data/r3a3f_three_source/staging.sqlite --port 8787 \
  --registry docs/evidence/r3a3f_three_source_admission.json --live-weather
```

Ask at `http://127.0.0.1:8787/` or fetch `/api/ask?q=...`. The console remains read-only and local.

## Limits

- The pack is small on purpose: one verified event, two weather places, flight channels. It is a
  demonstration of the safe path, not a full Wiki.
- The staging index is synthetic in this repository; general “who/what” answers quote only what is
  already accepted and trusted.
- Weather is a live third-party dependency; if Open-Meteo is unreachable the answer is
  `LIVE_SOURCE_REQUIRED`, never a cached temperature passed off as current.
- No language model is used. Multi-hop synthesis, personalisation and open-ended chat are out of
  scope until there is a separately reviewed retrieval-and-attribution design.
