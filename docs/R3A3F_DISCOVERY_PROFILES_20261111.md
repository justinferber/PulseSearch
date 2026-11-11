# R3-A3F — intent-aware discovery for outdoor festivals, music, parades and seasonal markets

**Date:** 11 November 2026. **Scope:** discovery quality only. No new crawl rights, no topic filtering, no live crawling.

## The problem this fixes

Depth 3 is a small budget. A crawler that spreads it evenly over whatever a homepage links will spend it on navigation pages and miss the content the owner actually wants first: Christmas markets, Pride/CSD programmes, carnivals and processions, and open-air music festivals. Those pages are typically two or three hops away, are reached by anchor text (`Christmas markets 2026`, `Weihnachtsmarkt`, `Umzug`), and sit on listing hubs (`/whats-on`, `/events`, `/calendar`) rather than on the front page.

The old behaviour treated every same-origin link identically: discovery was breadth-first over `min_depth`, with no notion of what a link promised or what season it was.

## What was added

### 1. Intent profiles (`pulse_search_crawler_r3a3f/topics.py`)

Seven discovery intents, each mapping to the 18-category coverage facets:

| Intent | Examples of the terms matched | Feeds |
| --- | --- | --- |
| `christmas_markets` | Christmas market, Xmas market, **Weihnachtsmarkt**, **Christkindlmarkt**, **Adventsmarkt**, Glühwein | Market, Festival |
| `pride` | Pride, **CSD**, Christopher Street Day, queer festival, LGBTQ | Pride & Community, Festival, Parades |
| `music_festivals` | Open air, openair, lineup, live music, concert series, **Konzert** | Music & Performance, Festival |
| `parades` | Parade, procession, **Umzug**, **Karneval**, Fasching | Parades & Processions, Festival |
| `outdoor_festivals` | Street festival, **Straßenfest**, **Stadtfest**, **Sommerfest**, Volksfest, street party | Festival, Arts & Culture |
| `diwali` | Diwali, Deepavali, festival of lights | Festival |
| `new_year` | New Year, **Silvester**, fireworks, winter festival | Festival, Music & Performance |

Terms are matched on word boundaries so `pride` does not fire inside `prideful`, and multi-word phrases match as phrases. Local-language forms are first-class, because a Berlin Christmas market page says `Weihnachtsmarkt`, not "Christmas market".

### 2. Anchor text, not just URLs

`extract.py` now captures anchor text per link (`link_texts`). Discovery scores `anchor + URL`, so a link labelled `Christmas markets 2026` is prioritised over a link labelled `read more`, even when both point at listing pages.

### 3. Priority instead of breadth-first

Frontier priority is now `100 − 10·depth + intent boost` (boost capped at 2.0, scaled by seasonality), and `claim_next` orders by priority first. The effect is that the 3-hop budget is spent on plausible event content before generic navigation, while everything else still gets crawled.

### 4. Listing-section probes

Each approved source gets up to a dozen same-origin probes for paths that usually host listings (`/events`, `/whats-on`, `/calendar`, `/listings`, `/markets`, `/christmas`, `/pride`, `/festivals`, `/music`, `/veranstaltungen`). A probe:

* must fall inside the source's already-approved `allowed_paths`;
* is admitted at depth 1, so two further hops remain;
* still passes robots, scope, dedup and rights checks;
* is recorded with the hint `discovery_probe` so the dashboard can show what was probed.

This is the single largest gain: a homepage that never links its own Christmas section is now reached anyway, without inventing a seed or bypassing the 3-hop rule.

### 5. Seasonality

Intents carry months (Christmas November–December, Pride June–July, music May–August, parades February/November). In-season intents receive the full boost, out-of-season intents 0.6×, so the same crawl budget favours what is actually happening now. `focus_month` can pin the month for reproducible tests.

### 6. Hub detection

Pages that look like listings ("what's on", calendar, programme, many links) are labelled `hub` and their links inherit intent-derived priority. This is how a city guide becomes a productive node instead of a dead end.

### 7. Document labels and reporting

Accepted documents now carry the best-matching intent (score ≥ 0.4). The run report and dashboard show documents per intent, which intents are in season, how many probes completed, and the top priority-raised URLs. `discovery.semantics` is explicitly `priority_hint_only_no_topic_blocking`.

## What this deliberately does not do

* **No topic blocking.** Pride, CSD, Diwali and Stadtfest stay fully discoverable; the intent layer only decides what to look at first. Christmas season does not demote them — 0.6× still boosts.
* **No scope expansion.** Probes cannot leave approved paths, and off-domain links remain candidates requiring admission.
* **No robots bypass.** A probe is an ordinary GET that robots and politeness gate like any other.
* **No fabricated labels.** A page with no intent signal carries none; category classification remains independent and keeps its `uncertain` flag.
* **No live crawl.** All of this was demonstrated on loopback only.

## Evidence

Fixture additions: a `/whats-on` listing hub with intent anchors, a German `Weihnachtsmarkt` page, an open-air music festival page, and a `Karneval Umzug` page. In the offline run:

* listing probe completed and its seasonal children indexed;
* intent documents found for Christmas markets, music festivals, parades and Pride;
* depth still capped at 3 with zero depth-4 fetches;
* Diwali, CSD, Pride Berlin and Stadtfest still present in the same run;
* new `tests/test_r3a3f_discovery.py` suite, including the "intent never blocks a topic" assertion.

These are synthetic pages. Whether real Berlin/London listing sections respond this way is exactly what a capped pilot must measure.
