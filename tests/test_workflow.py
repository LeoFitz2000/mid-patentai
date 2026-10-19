from __future__ import annotations

import unittest
from unittest.mock import Mock

import requests

from modules.eval_ranker import evaluate
from modules.invention_improver import suggest_improvements
from modules.llm_client import LLMClient
from modules.models import PatentRecord, ScoredRecord
from modules.patent_drafter import generate_draft
from modules.patent_extract import extract_records
from modules.similarity_engine import analyze
from modules.workflow import require_confirmation


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = [
            PatentRecord("optical glucose patch", "near infrared wearable sensor", "https://patents.google.com/patent/A", "patents.google.com"),
            PatentRecord("battery charger", "wireless power control", "https://patents.google.com/patent/B", "patents.google.com"),
        ]

    def test_empty_search_is_insufficient_evidence(self) -> None:
        result = analyze("optical glucose patch", [])
        self.assertIsNone(result.max_similarity)
        self.assertEqual(result.matches, ())

    def test_reference_filter_deduplicates_and_rejects_untrusted_host(self) -> None:
        raw = [
            {"title": "A", "content": "Sensor", "url": "https://patents.google.com/patent/A#anchor"},
            {"title": "A again", "url": "https://patents.google.com/patent/A"},
            {"title": "Fake", "url": "https://patents.google.com.evil.test/fake"},
        ]
        cleaned = extract_records(raw)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0].url, "https://patents.google.com/patent/A")

    def test_confirmation_guard_prevents_external_stage(self) -> None:
        selected = [("P1", ScoredRecord(self.records[0], 0.8))]
        with self.assertRaises(PermissionError):
            require_confirmation(False, selected)
        require_confirmation(True, selected)

    def test_external_response_is_validated_without_fake_fallback(self) -> None:
        selected = [("P1", ScoredRecord(self.records[0], 0.8))]
        client = Mock()
        client.complete.return_value = "not JSON"
        with self.assertRaises(ValueError):
            suggest_improvements("a new sensor", selected, client)
        with self.assertRaises(ValueError):
            generate_draft("a new sensor", selected, client)

    def test_llm_http_failure_never_exposes_key(self) -> None:
        response = Mock()
        response.status_code = 401
        response.raise_for_status.side_effect = requests.HTTPError("secret-key")
        client = LLMClient("secret-key", "https://example.test/v1", "model", post=lambda *a, **k: response)
        with self.assertRaises(RuntimeError) as context:
            client.complete("system", "user")
        self.assertNotIn("secret-key", str(context.exception))

    def test_ranker_eval_uses_labeled_urls(self) -> None:
        case = {
            "query": "optical glucose patch",
            "records": [item.__dict__ for item in self.records],
            "relevant_urls": [self.records[0].url],
        }
        metrics = evaluate([case], k=1)
        self.assertEqual(metrics["recall@1"], 1.0)
        self.assertEqual(metrics["mrr"], 1.0)


if __name__ == "__main__":
    unittest.main()
