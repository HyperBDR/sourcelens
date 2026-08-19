from django.test import SimpleTestCase

from lens.citations import sanitize_planned_evidence


class SanitizePlannedEvidenceTest(SimpleTestCase):
    """Bound the public planned-evidence summary surface."""

    def test_keeps_sufficient_and_gap_categories(self):
        output = sanitize_planned_evidence(
            {
                "sufficient": True,
                "gap_categories": ["source", "unexpected"],
                "internal_secret": "x",
            }
        )

        self.assertEqual(output["sufficient"], True)
        self.assertEqual(output["gap_categories"], ["source"])
        self.assertNotIn("internal_secret", output)

    def test_keeps_planner_status_and_bounded_rejection_reason(self):
        output = sanitize_planned_evidence(
            {
                "planner_status": "fallback",
                "planner_rejection_reason": (
                    "unsupported CodeGraph operation: symbol_search | "
                    "codegraph query must be an object"
                ),
            }
        )

        self.assertEqual(output["planner_status"], "fallback")
        self.assertIn(
            "unsupported CodeGraph operation: symbol_search",
            output["planner_rejection_reason"],
        )

    def test_rejects_unknown_planner_status_and_non_string_reason(self):
        output = sanitize_planned_evidence(
            {
                "planner_status": "exploded",
                "planner_rejection_reason": {"nested": "secret"},
            }
        )

        self.assertNotIn("planner_status", output)
        self.assertNotIn("planner_rejection_reason", output)

    def test_non_dict_input_returns_empty(self):
        self.assertEqual(sanitize_planned_evidence("oops"), {})
