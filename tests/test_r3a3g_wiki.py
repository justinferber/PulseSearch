"""Wiki draft workflow: dedup, update, approval, publication gate, revocation."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_broad_r3a3g.wiki import (  # noqa: E402
    LocalPublisher, WikiError, WikiPolicy, WikiService, WikiStore,
)

ARTICLES = json.loads((ROOT / "config/wiki_articles.json").read_text(encoding="utf-8"))["articles"]


class WikiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="r3a3g-wiki-"))
        self.store = WikiStore(self.tmp / "wiki.sqlite")
        self.service = WikiService(self.store)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ten_plus_drafts_have_two_sources_each(self):
        for article in ARTICLES:
            result = self.service.propose(article)
            self.assertEqual(result["result"], "draft_created", article["slug"])
        pages = self.store.list()
        self.assertGreaterEqual(len(pages), 10)
        for page in pages:
            sources = json.loads(page["sources"])
            self.assertGreaterEqual(len({s["url"] for s in sources}), 2)
            self.assertIn("## Sources", page["body"])

    def test_duplicate_topic_is_recognised_not_duplicated(self):
        article = ARTICLES[0]
        self.service.propose(article)
        before = len(self.store.list())
        result = self.service.propose(article)
        self.assertEqual(result["result"], "duplicate")
        self.assertEqual(len(self.store.list()), before)
        self.assertEqual(result["topic_id"], article["topic_id"])

    def test_existing_topic_gets_an_update_diff_not_an_overwrite(self):
        article = dict(ARTICLES[0])
        self.service.propose(article)
        original = self.store.get(article["topic_id"])["body"]
        changed = dict(article)
        changed["claims"] = article["claims"] + [{
            "text": "Check the venue's own site for current accessibility arrangements.",
            "sources": ["https://www.mercedes-benz-arena.de/"],
        }]
        result = self.service.propose(changed)
        self.assertEqual(result["result"], "update_draft")
        self.assertIn("+", result["diff"])
        self.assertEqual(self.store.get(article["topic_id"])["body"], original)
        self.assertEqual(self.store.get(article["topic_id"])["status"], "draft_update")

    def test_publication_requires_authorised_policy_and_approval(self):
        article = ARTICLES[0]
        self.service.propose(article)
        with self.assertRaises(WikiError):
            self.service.publish(article["topic_id"], WikiPolicy())
        self.service.approve(article["topic_id"], "editor@example.test")
        with self.assertRaises(WikiError):
            self.service.publish(article["topic_id"], WikiPolicy(auto_publish_enabled=True))
        policy = WikiPolicy(auto_publish_enabled=True, authorised_by="local-test-policy")
        result = self.service.publish(article["topic_id"], policy, reviewer="editor")
        self.assertEqual(result["result"], "published")
        self.assertEqual(self.store.get(article["topic_id"])["status"], "published")

    def test_revoked_source_flags_and_unpublishes(self):
        article = ARTICLES[0]
        self.service.propose(article)
        self.service.approve(article["topic_id"], "editor")
        self.service.publish(article["topic_id"],
                             WikiPolicy(auto_publish_enabled=True, authorised_by="test"),
                             reviewer="editor")
        source = article["claims"][0]["sources"][0]
        result = self.service.flag_source(source, "rights withdrawn")
        self.assertIn(article["topic_id"], result["topics"])
        page = self.store.get(article["topic_id"])
        self.assertEqual(page["status"], "flagged")
        self.assertEqual(page["flag_reason"], "rights withdrawn")

    def test_personal_data_and_transient_values_are_rejected(self):
        bad = dict(ARTICLES[0], topic_id="bad-pii")
        bad["claims"] = [{"text": "Contact member@example.test", "sources": [
            "https://www.berlin.de/events/", "https://www.eventim.de/"]}]
        with self.assertRaises(WikiError):
            self.service.propose(bad)
        price = dict(ARTICLES[0], topic_id="bad-price")
        price["claims"] = [{"text": "Tickets cost £45 today", "sources": [
            "https://www.berlin.de/events/", "https://www.eventim.de/"]}]
        with self.assertRaises(WikiError):
            self.service.propose(price)

    def test_publisher_adapter_is_explicit(self):
        class Unconfigured(LocalPublisher):
            def publish(self, page):
                raise WikiError("UNA Wiki adapter not configured")

        service = WikiService(self.store, Unconfigured())
        article = ARTICLES[1]
        service.propose(article)
        service.approve(article["topic_id"], "editor")
        with self.assertRaises(WikiError):
            service.publish(article["topic_id"],
                            WikiPolicy(auto_publish_enabled=True, authorised_by="test"),
                            reviewer="editor")


if __name__ == "__main__":
    unittest.main()
