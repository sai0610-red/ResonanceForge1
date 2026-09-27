"""Unit tests for grounded ACCESS / ADAPT / ADOPT checklist scoring."""

from __future__ import annotations

import unittest

from app.rubric.checklist import (
    CHECKLIST,
    get_checklist_payload,
    is_checklist_complete,
    score_checklist,
)


class ChecklistScoringTests(unittest.TestCase):
    def test_checklist_has_15_items(self):
        self.assertEqual(len(CHECKLIST), 15)
        dims = {item["dimension"] for item in CHECKLIST}
        self.assertEqual(dims, {"access", "adapt", "adopt"})
        for dim in ("access", "adapt", "adopt"):
            self.assertEqual(sum(1 for i in CHECKLIST if i["dimension"] == dim), 5)

    def test_payload_shape(self):
        payload = get_checklist_payload()
        self.assertEqual(len(payload), 15)
        q = payload[0]
        self.assertIn("id", q)
        self.assertIn("dimension", q)
        self.assertIn("prompt", q)
        self.assertEqual(len(q["options"]), 5)
        self.assertEqual(q["options"][0]["value"], 1)
        self.assertEqual(q["options"][-1]["value"], 5)

    def test_all_ones_is_low(self):
        answers = {item["id"]: 1 for item in CHECKLIST}
        self.assertTrue(is_checklist_complete(answers))
        result = score_checklist(answers)
        self.assertEqual(result.access.score, 2)
        self.assertEqual(result.adapt.score, 2)
        self.assertEqual(result.adopt.score, 2)
        self.assertEqual(result.overall_readiness, "Low")
        self.assertGreaterEqual(len(result.top_gaps), 3)
        self.assertLessEqual(len(result.top_gaps), 5)
        self.assertIn("Checklist", result.access.reason)

    def test_all_fives_is_high(self):
        answers = {item["id"]: 5 for item in CHECKLIST}
        result = score_checklist(answers)
        self.assertEqual(result.access.score, 10)
        self.assertEqual(result.adapt.score, 10)
        self.assertEqual(result.adopt.score, 10)
        self.assertEqual(result.overall_readiness, "High")

    def test_mixed_medium(self):
        answers = {item["id"]: 3 for item in CHECKLIST}
        result = score_checklist(answers)
        self.assertEqual(result.access.score, 6)
        self.assertEqual(result.overall_readiness, "Medium")

    def test_incomplete_raises(self):
        with self.assertRaises(ValueError):
            score_checklist({"access_data_quality": 3})

    def test_scores_clamped_1_to_10(self):
        answers = {item["id"]: 2 for item in CHECKLIST}
        result = score_checklist(answers)
        for score in (result.access.score, result.adapt.score, result.adopt.score):
            self.assertGreaterEqual(score, 1)
            self.assertLessEqual(score, 10)


if __name__ == "__main__":
    unittest.main()
