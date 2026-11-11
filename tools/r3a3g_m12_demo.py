"""M12 demonstration: live retrieval, cited answers, diverse cases and feedback.

SearXNG upstream search engines became rate-limited during this run, so the
demonstration separates discovery from retrieval explicitly:

* discovery leads are the exact URLs previously returned by the local SearXNG
  instance (recorded, not re-queried);
* every accepted page is fetched live through the existing SSRF-safe fetcher and
  robots cache;
* conflict and no-evidence cases use in-memory fixtures and are labelled as such.

This is evidence of the retrieval/answer pipeline, not a claim that upstream
provider search was healthy at the moment the file was generated.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_broad_r3a3g.m12_feedback import FeedbackStore  # noqa: E402
from pulse_search_broad_r3a3g.m12_research import (  # noqa: E402
    Candidate, ResearchEngine, ResearchSession, SourcePolicy, SourceRule,
    _merge_candidates,
)
from pulse_search_crawler_r3a3f.config import CrawlConfig  # noqa: E402
from pulse_search_crawler_r3a3f.robots import RobotsCache  # noqa: E402
from pulse_search_crawler_r3a3f.safe_fetch import Fetcher, FetchResult  # noqa: E402


class RecordedProvider:
    def __init__(self, urls: list[str], note: str = ""):
        self.urls = urls
        self.note = note

    def search(self, query, limit=10, language="all"):
        return {
            "status": "provider_results_unverified",
            "results": [{"url": u, "title": "", "snippet": ""} for u in self.urls[:limit]],
            "note": self.note,
        }


class FixtureFetcher:
    class Config:
        user_agent = "pulse-search-m12-fixture/1.0"

    def __init__(self, pages):
        self.pages = pages
        self.config = self.Config()

    def fetch(self, url, max_bytes=None):
        body = self.pages[url].encode("utf-8")
        return FetchResult(url, url, status=200, body=body,
                           headers={"content-type": "text/html; charset=utf-8"})


class FixtureRobots:
    def path_allowed(self, url, user_agent):
        return True, None


def fixture_html(title, text):
    return ("<html><head><title>" + title + "</title></head><body>"
            + text + "</body></html>")


def fixture_rule(url, publisher, city=""):
    return SourceRule(
        source_id=url.rsplit("/", 1)[-1], url=url, publisher=publisher,
        authority="official", jurisdiction="GB", language="en", city=city,
        rights="public_metadata_and_short_snippet", approval_ref="M12-DEMO-FIXTURE",
        answer_kind="detail", topics=(), priority=1)


def policy(*rules):
    return SourcePolicy(list(rules), "M12-DEMO")


def answer_dict(answer):
    data = answer.as_dict()
    data["discovery"]["mode"] = "recorded_local_searxng_lead"
    return data


def run_live() -> dict:
    source_policy = SourcePolicy.from_file(ROOT / "config/m12_sources.json")
    fetcher = Fetcher(CrawlConfig(min_interval_s=0.8, timeout_s=20.0,
                                  max_bytes=1_500_000))
    robots = RobotsCache(fetcher)
    leads = {
        "list": ["https://www.visitbritain.com/en/things-to-do/christmas-markets-britain"],
        "bath": ["https://www.bathchristmasmarket.co.uk/event-information",
                 "https://www.visitbath.co.uk/whats-on/bath-christmas-market-p2988783"],
        "passport": ["https://www.gov.uk/apply-renew-passport"],
        "local": ["https://www.tate.org.uk/visit/accessibility"],
        "general": ["https://en.wikipedia.org/wiki/Paris"],
        "comparison": ["https://www.eurostar.com/us-en/destinations/christmas-markets",
                       "https://www.visitbath.co.uk/whats-on/bath-christmas-market-p2988783"],
        "german": ["https://www.bathchristmasmarket.co.uk/event-information",
                   "https://www.visitbath.co.uk/whats-on/bath-christmas-market-p2988783"],
    }
    questions = {
        "list": "What are the top ten Christmas markets in the UK for 2026?",
        "bath": "When does Bath Christmas Market open in 2026?",
        "passport": "How do I renew my British passport?",
        "local": "Which museums in London have wheelchair access?",
        "general": "What is the capital of France?",
        "comparison": "Which Christmas markets are easiest to reach by train?",
        "german": "Wann öffnet der Bath Christmas Market 2026?",
    }
    output = {"source_policy": "config/m12_sources.json",
              "discovery_note": "Recorded live local-SearXNG leads; upstream engines were rate-limited at evidence time.",
              "cases": {}}
    first = None
    for key, question in questions.items():
        engine = ResearchEngine(
            RecordedProvider(leads[key], "Recorded from local SearXNG before upstream throttling."),
            source_policy, fetcher, robots, max_pages=3)
        answer = engine.answer(question)
        output["cases"][key] = answer_dict(answer)
        if key == "list":
            first = engine
    if first is not None:
        session = ResearchSession(first)
        session.ask(questions["list"])
        follow = session.follow_up("Which one starts earliest?")
        output["follow_up"] = answer_dict(follow)

    # These are deterministic fixtures, not live claims. They exercise the same
    # engine's uncertainty and conflict paths without inventing web evidence.
    conflict_policy = policy(
        fixture_rule("https://fixture.example/bath-a", "Publisher A", "Bath"),
        fixture_rule("https://fixture.example/bath-b", "Publisher B", "Bath"))
    conflict_pages = {
        "https://fixture.example/bath-a": fixture_html(
            "Bath Christmas Market | A",
            "Bath Christmas Market runs from 26 November 2026 to 13 December 2026."),
        "https://fixture.example/bath-b": fixture_html(
            "Bath Christmas Market | B",
            "Bath Christmas Market runs from 27 November 2026 to 14 December 2026."),
    }
    conflict = ResearchEngine(
        RecordedProvider(list(conflict_pages)), conflict_policy,
        FixtureFetcher(conflict_pages), FixtureRobots(), max_pages=2).answer(
            "When does Bath Christmas Market open in 2026?")
    output["conflict_fixture"] = answer_dict(conflict)

    empty = ResearchEngine(
        RecordedProvider([]), source_policy, FixtureFetcher({}), FixtureRobots(),
        max_pages=1).answer("What is the population of the fictional town of Nowhere?")
    output["no_evidence"] = answer_dict(empty)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store = FeedbackStore(Path(tmp) / "feedback.sqlite")
        try:
            store.record("Christmas markets in the UK", "visitbritain.com",
                         "helpful", "m12-reviewer", "publisher list was useful")
            store.record("Christmas markets in the UK", "spam.example",
                         "irrelevant", "m12-reviewer", "off-topic lead")
            before = _merge_candidates([
                Candidate("Spam result", "London", "", "fixture",
                          "https://spam.example/x", "Spam", "spam", "reference"),
                Candidate("VisitBritain list", "UK", "2026", "fixture",
                          "https://visitbritain.com/x", "VisitBritain", "vb", "official"),
            ])
            after = _merge_candidates([
                Candidate("Spam result", "London", "", "fixture",
                          "https://spam.example/x", "Spam", "spam", "reference"),
                Candidate("VisitBritain list", "UK", "2026", "fixture",
                          "https://visitbritain.com/x", "VisitBritain", "vb", "official"),
            ], store)
            output["feedback"] = {
                "before": [{"name": c.name, "score": c.score} for c in before],
                "after": [{"name": c.name, "score": c.score} for c in after],
                "proposal": store.proposal(),
                "raw_question_stored": False,
            }
        finally:
            store.close()
    return output


def main() -> int:
    result = run_live()
    out = ROOT / "docs/evidence/r3a3g_m12_demo.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    for key, case in result["cases"].items():
        print(key, case["status"], case["response_mode"],
              "candidates=", len(case.get("candidates") or []),
              "citations=", len(case.get("citations") or []))
    print("conflict", result["conflict_fixture"]["status"])
    print("no_evidence", result["no_evidence"]["status"])
    print("feedback", result["feedback"]["after"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
