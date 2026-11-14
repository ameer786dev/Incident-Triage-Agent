from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

from triage_lab.scoring import score_case


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.case = {
            "id": "case-1", "snapshot": {
                "logs": [{"id": "log-1", "service": "checkout", "message": "statement timeout"}],
                "metrics": {"checkout": {"db_latency_p95_ms": 3000}}, "deploys": []},
            "expected": {"root_cause": "db_timeout", "affected_service": "checkout", "runbook_id": "checkout-db_timeout", "required_evidence_sources": ["logs", "metrics"], "should_abstain": False},
        }
        self.prediction = {
            "root_cause": "db_timeout", "affected_service": "checkout",
            "runbooks": [{"id": "checkout-db_timeout"}], "needs_human_review": False,
            "evidence": [{"id": "log-1", "source": "search_logs", "service": "checkout", "detail": "statement timeout"}, {"id": "metric:checkout:db_latency_p95_ms", "source": "get_metrics", "service": "checkout", "detail": "3000"}],
        }

    def test_valid_sources_are_grounded(self):
        score = score_case(self.case, self.prediction)
        self.assertTrue(score["root_cause_correct"])
        self.assertEqual(score["evidence_precision"], 1)
        self.assertTrue(score["required_sources_covered"])
        self.assertTrue(score["retrieval_hit_at_3"])

    def test_fabricated_citation_reduces_grounding(self):
        self.prediction["evidence"][0]["id"] = "made-up-log"
        score = score_case(self.case, self.prediction)
        self.assertFalse(score["evidence_grounded"])
        self.assertFalse(score["required_sources_covered"])
        self.assertEqual(score["evidence_precision"], 0.5)

    def test_existing_id_cannot_be_claimed_by_wrong_service_or_tool(self):
        self.prediction["evidence"][0]["service"] = "payments"
        self.prediction["evidence"][1]["source"] = "search_logs"
        self.assertEqual(score_case(self.case, self.prediction)["evidence_precision"], 0)

    def test_unknown_metric_field_is_not_an_observation(self):
        self.prediction["evidence"][1]["id"] = "metric:checkout:invented_metric"
        self.assertEqual(score_case(self.case, self.prediction)["evidence_precision"], 0.5)

    def test_empty_evidence_does_not_pass_known_diagnosis(self):
        self.prediction["evidence"] = []
        score = score_case(self.case, self.prediction)
        self.assertIsNone(score["evidence_precision"])
        self.assertFalse(score["evidence_grounded"])
        self.assertFalse(score["required_sources_covered"])

    def test_unknown_abstention_has_no_retrieval_target(self):
        self.case["expected"].update(root_cause="unknown", runbook_id=None, should_abstain=True, required_evidence_sources=[])
        self.prediction.update(root_cause="unknown", needs_human_review=True, evidence=[])
        score = score_case(self.case, self.prediction)
        self.assertTrue(score["abstention_correct"])
        self.assertTrue(score["evidence_grounded"])
        self.assertIsNone(score["retrieval_hit_at_3"])

    def test_runbook_rank_four_does_not_count(self):
        self.prediction["runbooks"] = ["other-1", "other-2", "other-3", "checkout-db_timeout"]
        self.assertFalse(score_case(self.case, self.prediction)["retrieval_hit_at_3"])

    def test_duplicate_citations_do_not_inflate_counts(self):
        self.prediction["evidence"].append(self.prediction["evidence"][0].copy())
        self.assertEqual(score_case(self.case, self.prediction)["evidence_count"], 2)

    def test_dataset_shape_and_reproducibility(self):
        path = Path(__file__).resolve().parents[1] / "evals" / "generate.py"
        spec = importlib.util.spec_from_file_location("eval_generate", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cases = module.generate("test", 731942)
        self.assertEqual(len(cases), 180)
        self.assertEqual(cases, module.generate("test", 731942))
        self.assertEqual(sum(c["expected"]["should_abstain"] for c in cases), 20)
        self.assertEqual(len({c["id"] for c in cases}), 180)
        self.assertTrue(all("root_cause" not in c["snapshot"] for c in cases))
        self.assertTrue(all("expected" not in c["snapshot"] for c in cases))
        self.assertEqual(len(module.generate("development", 184903)), 40)


if __name__ == "__main__":
    unittest.main()
