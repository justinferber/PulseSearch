"""M12 dynamic discovery, cited answers, conflict handling and feedback tests."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from pulse_search_broad_r3a3g.api import Consumer, build_server
from pulse_search_broad_r3a3g.client import PulseSearchClient
from pulse_search_broad_r3a3g.m12_feedback import FeedbackStore, query_shape
from pulse_search_broad_r3a3g.m12_research import (
    Candidate, QueryPlan, ResearchEngine, ResearchSession, SourcePolicy, SourceRule,
    _merge_candidates,
)
from pulse_search_crawler_r3a3f.safe_fetch import FetchResult


class StubConfig:
    user_agent = "PulseSearch-M12-Test/1.0"


class StubFetcher:
    def __init__(self, pages: dict[str, str]):
        self.pages = pages
        self.config = StubConfig()

    def fetch(self, url, max_bytes=None):
        body = self.pages[url].encode("utf-8")
        return FetchResult(url, url, status=200, body=body,
                           headers={"content-type": "text/html; charset=utf-8"})


class StubRobots:
    def path_allowed(self, url, user_agent):
        return True, None


class StubProvider:
    def __init__(self, results: list[dict]):
        self.results = results
        self.calls = []

    def search(self, query, limit=10, language="all"):
        self.calls.append((query, language))
        return {"status": "provider_results_unverified", "results": self.results[:limit]}


def rule(url: str, publisher: str = "Fixture Publisher", *,
         kind: str = "detail", city: str = "", authority: str = "official") -> SourceRule:
    return SourceRule(
        source_id=url.rstrip("/").rsplit("/", 1)[-1],
        url=url, publisher=publisher, authority=authority, jurisdiction="GB",
        language="en", city=city, rights="public_metadata_and_short_snippet",
        approval_ref="TEST-M12", answer_kind=kind, topics=(), priority=1,
    )


def policy(*rules: SourceRule) -> SourcePolicy:
    return SourcePolicy(list(rules), "TEST-M12")


def html(title: str, text: str) -> str:
    return ("<html><head><title>" + title + "</title>"
            "<meta name=\"description\" content=\"Fixture description for tests.\">"
            "</head><body><main>" + text + "</main></body></html>")


def list_html() -> str:
    rows = [
        ("Newcastle Christmas Market", "19th - 23rd December 2026",
         "Expect a friendly market with local traders.", "Newcastle upon Tyne, England"),
        ("Frankfurt Christmas Market, Birmingham", "5th November - 24th December 2026",
         "A long-running market with craft stalls and food.", "Birmingham, England"),
        ("Edinburgh Christmas Markets", "14th November 2026 - 3rd January 2027",
         "Festive stalls and events across the city.", "Edinburgh, Scotland"),
        ("Manchester Christmas Markets", "6th November - 22nd December 2026",
         "A large market with food, gifts and seasonal drinks.", "Manchester, England"),
        ("Cardiff Christmas Market", "12th November - 23rd December 2026",
         "Hand-made products and festive food.", "Cardiff, Wales"),
        ("York Christmas Market", "12th November - 21st December 2026",
         "Wooden chalets and gifts in the city centre.", "York, England"),
        ("Bath Christmas Market", "26th November - 13th December 2026",
         "An open-air market in the heart of Bath.", "Bath, England"),
        ("Bristol Christmas Market", "November - December 2026",
         "A city-centre market with entertainment.", "Bristol, England"),
        ("Glasgow Christmas Market", "November - December 2026",
         "A festive market with entertainment and rides.", "Glasgow, Scotland"),
        ("Hyde Park Winter Wonderland", "19th November 2026 - 3rd January 2027",
         "A large festive attraction in Hyde Park.", "London, England"),
    ]
    parts = ["<h1>Top Christmas markets in Britain</h1>"]
    for name, dates, description, place in rows:
        parts.append(f"<h2>{name}</h2><p>View on map {dates} {description} "
                     f"Location: {place}</p>")
    return html("Top Christmas markets in Britain", "".join(parts))


class QueryPlanTests(unittest.TestCase):
    def test_query_shapes_are_general_and_language_aware(self):
        expected = {
            "What are the top ten Christmas markets in the UK for 2026?": "list",
            "When does Bath Christmas Market open in 2026?": "factual",
            "How do I renew my British passport?": "how_to",
            "Which Christmas markets are easiest to reach by train?": "comparison",
            "Which museums in London have wheelchair access?": "local",
            "What is the capital of France?": "general",
            "Wann öffnet der Bath Christmas Market 2026?": "factual",
        }
        for question, kind in expected.items():
            with self.subTest(question=question):
                plan = QueryPlan.from_question(question)
                self.assertEqual(plan.answer_type, kind)
        self.assertEqual(QueryPlan.from_question(
            "What are the top ten Christmas markets in the UK for 2026?").count, 10)
        self.assertEqual(QueryPlan.from_question(
            "Wann öffnet der Bath Christmas Market 2026?").language, "de")
        self.assertTrue(QueryPlan.from_question(
            "Wann öffnet der Bath Christmas Market 2026?").queries[1].startswith(
                "bath christmas market"))

    def test_source_policy_is_exact_and_rejects_unapproved_or_http(self):
        approved = rule("https://fixture.example/one")
        source_policy = policy(approved)
        self.assertIs(source_policy.match("https://fixture.example/one"), approved)
        self.assertIsNone(source_policy.match("https://fixture.example/two"))
        raw = {"sources": [{"id": "bad", "url": "http://fixture.example/one",
                            "approved": True, "rights": "public_metadata_and_short_snippet"}]}
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "sources.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                SourcePolicy.from_file(path)


class EngineTests(unittest.TestCase):
    def test_ten_item_list_is_entity_deduplicated_and_cited(self):
        url = "https://fixture.example/list"
        source_policy = policy(rule(url, "Fixture list", kind="list"))
        engine = ResearchEngine(
            StubProvider([{"url": url, "title": "List", "snippet": "fixture"}]),
            source_policy, StubFetcher({url: list_html()}), StubRobots(), max_pages=1)
        answer = engine.answer("What are the top ten Christmas markets in the UK for 2026?")
        self.assertEqual(answer.status, "ANSWERED")
        self.assertEqual(answer.response_mode, "CITED_LIST")
        self.assertEqual(len(answer.candidates), 10)
        self.assertEqual(answer.shortfall, 0)
        self.assertEqual(len({c["name"] for c in answer.candidates}), 10)
        self.assertTrue(all(c["sources"] for c in answer.candidates))
        self.assertIn("Newcastle Christmas Market", answer.answer)
        self.assertIn("Hyde Park Winter Wonderland", answer.answer)
        self.assertIn("not an independent ranking", answer.answer)

    def test_detail_question_uses_the_date_evidence_and_marks_uncertainty(self):
        url = "https://fixture.example/bath"
        text = ("Bath Christmas Market runs from 26 November 2026 to 13 December 2026. "
                "The open-air market is free to enter.")
        source_policy = policy(rule(url, "Bath official", city="Bath"))
        engine = ResearchEngine(
            StubProvider([{"url": url, "title": "Bath Christmas Market", "snippet": ""}]),
            source_policy, StubFetcher({url: html("Bath Christmas Market", text)}),
            StubRobots(), max_pages=1)
        answer = engine.answer("When does Bath Christmas Market open in 2026?")
        self.assertEqual(answer.status, "ANSWERED")
        self.assertIn("26 November 2026", answer.answer)
        self.assertIn("13 December 2026", answer.answer)
        self.assertTrue(answer.claims[0]["evidence"])
        self.assertEqual(answer.candidates[0]["evidence_status"], "confirmed_2026")

    def test_conflicting_dates_are_not_silently_merged(self):
        one = "https://fixture.example/bath-one"
        two = "https://fixture.example/bath-two"
        source_policy = policy(
            rule(one, "Publisher A", city="Bath"),
            rule(two, "Publisher B", city="Bath"))
        pages = {
            one: html("Bath Christmas Market | A",
                      "Bath Christmas Market runs from 26 November 2026 to 13 December 2026."),
            two: html("Bath Christmas Market | B",
                      "Bath Christmas Market runs from 27 November 2026 to 14 December 2026."),
        }
        engine = ResearchEngine(
            StubProvider([{"url": one, "title": "A", "snippet": ""},
                          {"url": two, "title": "B", "snippet": ""}]),
            source_policy, StubFetcher(pages), StubRobots(), max_pages=2)
        answer = engine.answer("When does Bath Christmas Market open in 2026?")
        self.assertEqual(answer.status, "CONFLICTING_EVIDENCE")
        self.assertEqual(answer.response_mode, "UNCERTAIN")
        self.assertIn("Sources disagree", answer.answer)
        self.assertEqual(answer.candidates[0]["evidence_status"], "conflicting_evidence")
        self.assertEqual(len(answer.candidates[0]["date_variants"]), 2)

    def test_no_evidence_is_explicit(self):
        engine = ResearchEngine(
            StubProvider([]), policy(),
            StubFetcher({}), StubRobots(), max_pages=1)
        answer = engine.answer("What is the population of the fictional town of Nowhere?")
        self.assertEqual(answer.status, "NO_EVIDENCE")
        self.assertEqual(answer.response_mode, "NO_EVIDENCE")
        self.assertFalse(answer.candidates)
        self.assertTrue(answer.limitations)

    def test_comparison_uses_multiple_sources(self):
        one = "https://fixture.example/one"
        two = "https://fixture.example/two"
        source_policy = policy(rule(one, "A", city="Bath"),
                               rule(two, "B", city="York"))
        pages = {
            one: html("Bath Christmas Market", "Bath Christmas Market is easy to reach by train from London."),
            two: html("York Christmas Market", "York Christmas Market is easy to reach by train from London."),
        }
        engine = ResearchEngine(
            StubProvider([{"url": one, "title": "Bath", "snippet": ""},
                          {"url": two, "title": "York", "snippet": ""}]),
            source_policy, StubFetcher(pages), StubRobots(), max_pages=2)
        answer = engine.answer("Which Christmas markets are easiest to reach by train?")
        self.assertEqual(answer.status, "ANSWERED")
        self.assertIn("Bath", answer.answer)
        self.assertGreaterEqual(len(answer.claims), 2)

    def test_follow_up_reuses_retained_verified_list(self):
        url = "https://fixture.example/list"
        engine = ResearchEngine(
            StubProvider([{"url": url, "title": "List", "snippet": ""}]),
            policy(rule(url, kind="list")), StubFetcher({url: list_html()}),
            StubRobots(), max_pages=1)
        session = ResearchSession(engine)
        session.ask("What are the top ten Christmas markets in the UK for 2026?")
        answer = session.follow_up("Which one starts earliest?")
        self.assertEqual(answer.status, "ANSWERED")
        self.assertIn("Frankfurt Christmas Market, Birmingham", answer.answer)
        self.assertTrue(answer.citations)


class FeedbackTests(unittest.TestCase):
    def test_feedback_is_hashed_reviewed_and_turns_into_a_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FeedbackStore(Path(tmp) / "feedback.sqlite")
            question = "What are the best Christmas markets in the UK?"
            store.record(question, "visitbritain.com", "helpful", "reviewer-a")
            store.record(question, "bad.example", "irrelevant", "reviewer-a")
            rows = store.export()
            self.assertEqual(len(rows), 2)
            self.assertNotIn("best christmas markets", json.dumps(rows).lower())
            self.assertEqual(rows[0]["query_key"], hashlib.sha256(
                "what are the best christmas markets in the uk".encode()).hexdigest()[:24])
            self.assertEqual(store.score("visitbritain.com"), 2)
            proposal = store.proposal()
            self.assertFalse(proposal["automatic_apply"])
            self.assertEqual(proposal["sources"][0]["source_domain"], "visitbritain.com")
            store.close()

    def test_feedback_changes_a_reviewed_ranking_but_not_an_unreviewed_click(self):
        good = Candidate("A Market", "Bath", "2026 dates", "fixture",
                         "https://good.example/a", "A", "a", "official")
        bad = Candidate("B Market", "York", "2026 dates", "fixture",
                        "https://bad.example/b", "B", "b", "official")
        with tempfile.TemporaryDirectory() as tmp:
            store = FeedbackStore(Path(tmp) / "feedback.sqlite")
            try:
                store.record("Christmas markets", "good.example", "helpful", "reviewer-a")
                store.record("Christmas markets", "bad.example", "irrelevant", "reviewer-a")
                ranked = _merge_candidates([bad, good], store)
                self.assertEqual(ranked[0].name, "A Market")
                self.assertEqual(ranked[0].score - ranked[1].score, 4.0)
            finally:
                store.close()


class ApiResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="m12-api-"))
        (cls.tmp / "staging.sqlite").write_bytes(b"")
        url = "https://fixture.example/list"
        cls.url = url
        engine = ResearchEngine(
            StubProvider([{"url": url, "title": "List", "snippet": ""}]),
            policy(rule(url, kind="list")), StubFetcher({url: list_html()}),
            StubRobots(), max_pages=1)
        cls.token = "m12-api-token"
        cls.server = build_server(
            str(cls.tmp / "staging.sqlite"),
            {"puke": Consumer("puke", cls.token,
                              frozenset({"health:read", "research:read"}))},
            port=0, research=engine)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def request(self, path, payload):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            self.base + path, data=data, method="POST",
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json", "Connection": "close"})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_research_endpoint_preserves_claims_and_source_labels(self):
        status, body = self.request(
            "/v1/research",
            {"question": "What are the top ten Christmas markets in the UK for 2026?"})
        self.assertEqual(status, 200)
        self.assertEqual(body["response_mode"], "CITED_LIST")
        self.assertEqual(len(body["candidates"]), 10)
        self.assertTrue(body["claims"])
        self.assertTrue(body["citations"])
        self.assertEqual(body["citations"][0]["kind"], "approved_source")
        self.assertTrue(all("evidence_id" in c for c in body["citations"]))

    def test_client_can_request_dynamic_research(self):
        client = PulseSearchClient(self.base, self.token)
        result = client.research(
            "What are the top ten Christmas markets in the UK for 2026?")
        self.assertEqual(result.status, "ANSWERED")
        self.assertEqual(result.response_mode, "CITED_LIST")
        self.assertEqual(len(result.links), 10)
        self.assertTrue(result.claim_evidence)

    def test_research_is_scope_protected(self):
        server = build_server(
            str(self.tmp / "staging.sqlite"),
            {"read-only": Consumer("read-only", "other-token",
                                   frozenset({"health:read"}))},
            port=0, research=self.server.research)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_address[1]}/v1/research",
                data=json.dumps({"question": "x"}).encode(), method="POST",
                headers={"Authorization": "Bearer other-token",
                         "Content-Type": "application/json", "Connection": "close"})
            with self.assertRaises(urllib.error.HTTPError) as context:
                urllib.request.urlopen(req, timeout=10)
            self.assertEqual(context.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
