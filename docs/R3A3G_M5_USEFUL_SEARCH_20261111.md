# R3-A3G M5: Useful official handoffs

Date: 2026-11-11  
Status: **local evidence only**; production and public Wiki publication remain on HOLD.

## Outcome

The first practical usefulness benchmark now passes all eight named cases with
zero unrelated top results. When captured pages do not cover the specific
question, the API returns a reviewed official service instead of forcing an
irrelevant admission:

| Case | Response | Top result |
| --- | --- | --- |
| Berlin concert tickets | `official_links` | Eventim Berlin, `/city/berlin-8/` |
| Berlin venue accessibility and bag rules | `official_links` | Official venue page (Huxley's Neue Welt at last run) |
| Berlin Christmas-market transport | `official_links` | BVG Berlin |
| London New Year's Eve fireworks tickets | `official_links` | Mayor of London |
| Berlin CSD 2027 dates | `official_links` | CSD Berlin |
| Berlin Pride route and accessibility | `official_links` | CSD Berlin |
| Glastonbury Festival 2027 dates | `staging_results` | BBC News, "First Glastonbury 2027 tickets sell out…" |
| Berlin music festivals | `official_links` | Berlin.de events calendar |

Evidence: `docs/evidence/r3a3g_usefulness_benchmark.json`.

The benchmark uses the same captured real-source snapshot as the 15-query
evaluator. It checks the **top handoff** against the reviewed domain, not merely
whether an expected domain appears somewhere in the result set. It is a
navigation benchmark, not proof that a date, price or ticket is currently
available.

## Search behavior

- `_sufficient` requires the admitted set to cover at least 75% of the query's
  specific terms (city and stop words excluded). A single incidental phrase is
  not enough.
- A weak admitted set is withheld in favour of reviewed official navigation.
- An accessibility query prioritises venue pages rather than a ticket seller.
- Berlin ticket queries prefer the Berlin Eventim entry; other German cities do
  not inherit it.
- Berlin music/festival queries prefer the Berlin.de calendar.
- Arbitrary phrases without a known topic, city or booking intent do not get a
  generic calendar handoff; they remain `NO_EVIDENCE`.
- The standalone API, answer service, CLI and dashboard pass
  `enforce_support=True`. Legacy synthetic pattern tests keep their original
  fixtures by opting out explicitly, so the change is covered rather than
  hidden by weakened assertions.

## Standalone API / PUKE

PUKE remains a separate loopback HTTP client. It uses the standalone Pulse
Search API, never imports the search implementation, and sends no member
context.

Latest demo statuses:

| Question | Status |
| --- | --- |
| London weather tomorrow | `OFFICIAL_LINKS` |
| CSD Berlin 2027 | `OFFICIAL_LINKS` |
| Glastonbury Festival 2027 | `ANSWERED` |
| London fireworks tickets | `OFFICIAL_LINKS` |
| Berlin Christmas-market transport | `OFFICIAL_LINKS` |
| Moon Parade (unknown) | `NO_EVIDENCE` |

The API demo passes 9/9 checks (401 unauthenticated, health, capabilities,
search, event answer, weather answer, no-evidence answer, Wiki candidate,
Wiki scope denial). Evidence: `docs/evidence/r3a3g_api_demo.json` and
`docs/evidence/r3a3g_puke_client_demo.json`.

## UNA Wiki adapter, independently exercised

The adapter was run against the real mounted UNA application and the isolated
`una_pre_verify` database, not an in-memory substitute:

- Real `BxDolWiki`, `BxDolWikiQuery` and `BxDolDb` objects loaded.
- Real `wiki-home` page and block `342` were found.
- Real ACL allowed profile 3 to edit and denied profile 99.
- A draft revision was written, read back through UNA, and incremented the
  revision by one.
- A denied write added no revision.
- Retraction deactivated the real block.
- The test restored the original activation state, text, and revision history
  in `una_pre_verify` afterwards.

Result: **10/10 staging checks passed**. The test files are in the Pulse UNITY
adapter repository, not Pulse Search. No live `una` database write and no
public Wiki publication occurred.

Remaining UNA limit: page creation still needs the UNA operator UI because
`addPage()` has language-catalogue and page-builder side effects; the adapter
continues to fail closed for that path.

## Limits

- Official links are reviewed navigation entries, not crawled admissions or
  live values (`verified_live` is false).
- The eight-case benchmark is deliberately narrow and owner-directed.
- The legacy 15-query evaluator now separates admitted recall from official
  handoff availability. Its old human labels refer to admitted-page answers and
  are not a score for the new handoff behavior.
- Source coverage remains incomplete; missing sources are not filled by
  invented facts.
- No production deployment, public Wiki publication, or real-source crawling
  beyond the previously reviewed captures was performed.

## Reproduction

```sh
python tools/r3a3g_usefulness_benchmark.py
python tools/r3a3g_api_demo.py
python tools/puke_client_demo.py
python tools/r3a3g_real_source_eval.py
python -m unittest discover -s tests
```

UNA staging test (inside `una-php-1`, against `una_pre_verify`):

```sh
php /opt/una/adapters/pulse_search_wiki/tests/una_staging_test.php
```
