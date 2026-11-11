"""P0 Wiki publication integrity, evidence admission and concurrency."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pulse_search_broad_r3a3g.evidence import EvidenceRegistry  # noqa: E402
from pulse_search_broad_r3a3g.wiki import (  # noqa: E402
    LocalPublisher, PublisherNotConfigured, WikiError, WikiPolicy, WikiService, WikiStore,
)

ARTICLES = json.loads((ROOT / "config/wiki_articles.json").read_text(encoding="utf-8"))["articles"]
POLICY = WikiPolicy(auto_publish_enabled=True, authorised_by="test-owner",
                    allowed_categories=("general",), min_independent_publishers=2)


class CapturingPublisher(LocalPublisher):
    def __init__(self, fail_once: bool = False):
        super().__init__()
        self.revisions = []
        self.fail_once = fail_once
        self.calls = 0

    def publish(self, revision):
        self.calls += 1
        self.revisions.append(revision)
        if self.fail_once and self.calls == 1:
            raise TimeoutError("simulated adapter timeout")
        return super().publish(revision)


class P0WikiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="r3a3g-p0-"))
        self.store = WikiStore(self.tmp / "wiki.sqlite")
        self.publisher = CapturingPublisher()
        self.service = WikiService(self.store, self.publisher)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def create(self, article=None):
        article = article or ARTICLES[0]
        self.service.propose(article)
        return article

    def publish(self, article, service=None):
        service = service or self.service
        service.approve(article["topic_id"], "editor")
        return service.publish(article["topic_id"], POLICY, reviewer="editor")

    def test_default_publisher_fails_closed_even_with_policy(self):
        service = WikiService(self.store)
        article = self.create()
        info = service.approve(article["topic_id"], "editor")
        self.assertEqual(info["status"], "approved")
        with self.assertRaises(PublisherNotConfigured):
            service.publish(article["topic_id"], POLICY, reviewer="editor")
        self.assertEqual(self.store.get(article["topic_id"])["status"], "approved")

    def test_pending_revision_is_the_published_revision(self):
        article = self.create()
        self.publish(article)
        updated = dict(article)
        updated["claims"] = article["claims"] + [{
            "text": "Confirm accessibility arrangements on the venue's own page before booking.",
            "evidence": ["ev-mercedes-arena", "ev-huxleys"],
        }]
        result = self.service.propose(updated)
        self.assertEqual(result["result"], "update_draft")
        self.assertEqual(self.store.get(article["topic_id"])["status"], "published")
        self.service.approve(article["topic_id"], "editor")
        self.assertEqual(self.store.get(article["topic_id"])["status"], "approved_update")
        receipt = self.service.publish(article["topic_id"], POLICY, reviewer="editor")
        published = self.store.get(article["topic_id"])
        sent = self.publisher.revisions[-1]
        self.assertEqual(receipt["version"], 2)
        self.assertEqual(sent.version, 2)
        self.assertEqual(sent.base_version, 1)
        self.assertEqual(published["body"], sent.body)
        self.assertIn("accessibility arrangements", published["body"])
        self.assertEqual(published["claims"], list(sent.claims))
        self.assertEqual(published["sources"], list(sent.sources))
        self.assertEqual(published["version"], 2)
        self.assertFalse(published["has_pending"])
        self.assertEqual(published["external_id"], receipt["publisher"]["external_id"])

    def test_adapter_timeout_leaves_state_unchanged_and_retry_is_idempotent(self):
        publisher = CapturingPublisher(fail_once=True)
        service = WikiService(self.store, publisher)
        article = self.create()
        service.approve(article["topic_id"], "editor")
        before = self.store.get(article["topic_id"])
        with self.assertRaises(WikiError):
            service.publish(article["topic_id"], POLICY, reviewer="editor")
        after = self.store.get(article["topic_id"])
        self.assertEqual(before["body"], after["body"])
        self.assertEqual(after["status"], "approved")
        result = service.publish(article["topic_id"], POLICY, reviewer="editor")
        self.assertEqual(result["result"], "published")
        key = publisher.revisions[-1].idempotency_key
        again = publisher.publish(publisher.revisions[-1])
        self.assertTrue(again["idempotent"])
        self.assertEqual(again["external_id"], result["publisher"]["external_id"])
        self.assertEqual(len({r.idempotency_key for r in publisher.revisions}), 1)

    def test_fake_evidence_same_domain_and_cross_topic_are_rejected(self):
        fake = json.loads(json.dumps(ARTICLES[0]))
        fake["topic_id"] = "fake-topic"
        fake["claims"] = [{"text": "A fabricated claim about Berlin tickets.",
                           "sources": ["https://example.invalid/fake"]}]
        with self.assertRaises(WikiError):
            self.service.propose(fake)

        same_domain = dict(ARTICLES[0], topic_id="same-domain-topic")
        same_domain["claims"] = [{
            "text": "Use the Berlin events calendar for concert tickets.",
            "sources": ["https://www.berlin.de/events/", "https://www.berlin.de/en/"],
        }]
        with self.assertRaises(WikiError):
            self.service.propose(same_domain)

        cross_topic = dict(ARTICLES[0], topic_id="cross-topic")
        cross_topic["claims"] = [{
            "text": "The DWD publishes the national weather forecast.",
            "sources": ["https://www.dwd.de/"],
        }]
        with self.assertRaises(WikiError):
            self.service.propose(cross_topic)

    def test_category_policy_is_enforced_before_external_write(self):
        article = self.create()
        self.service.approve(article["topic_id"], "editor")
        calls = self.publisher.calls
        with self.assertRaises(WikiError):
            self.service.publish(
                article["topic_id"],
                WikiPolicy(auto_publish_enabled=True, authorised_by="test",
                           allowed_categories=("events",)),
                reviewer="editor")
        self.assertEqual(self.publisher.calls, calls)

    def test_revocation_considers_pending_revision_and_preserves_audit(self):
        article = self.create()
        self.publish(article)
        updated = dict(article)
        updated["claims"] = article["claims"] + [{
            "text": "Check the venue accessibility page before booking.",
            "evidence": ["ev-mercedes-arena"],
        }]
        self.service.propose(updated)
        self.assertEqual(self.store.get(article["topic_id"])["has_pending"], 1)
        result = self.service.flag_source("https://www.mercedes-benz-arena.de/",
                                          "rights withdrawn")
        self.assertIn(article["topic_id"], result["topics"])
        page = self.store.get(article["topic_id"])
        self.assertEqual(page["status"], "flagged")
        self.assertEqual(page["has_pending"], 0)
        notes = [r["note"] for r in self.store.revisions(article["topic_id"])]
        self.assertTrue(any("source revoked" in str(n) for n in notes))

    def test_concurrent_proposals_are_serialised(self):
        article = ARTICLES[0]
        results, errors = [], []

        def run():
            try:
                results.append(self.service.propose(article)["result"])
            except Exception as exc:  # pragma: no cover - assertion reports it
                errors.append(repr(exc))

        threads = [threading.Thread(target=run) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 12)
        self.assertEqual(len(self.store.list()), 1)
        self.assertTrue(all(r in ("draft_created", "duplicate", "update_draft")
                            for r in results))

    def test_registry_rejects_unknown_or_revoked_source(self):
        registry = EvidenceRegistry.from_file(ROOT / "config/wiki_evidence.json")
        with self.assertRaises(ValueError):
            registry.get("ev-does-not-exist", topic_id="guide-berlin-concert-tickets",
                         claim="venue tickets")
        self.store.mark_evidence_revoked("https://www.mercedes-benz-arena.de/", "test")
        service = WikiService(self.store, self.publisher,
                              evidence=registry)
        with self.assertRaises(WikiError):
            service.propose(ARTICLES[0])


if __name__ == "__main__":
    unittest.main()
