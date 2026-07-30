from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs" / "FEEDBACK-template.md"


class FeedbackProtocolTests(unittest.TestCase):
    def test_template_has_required_sections_and_lifecycle_values(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        for section in (
            "## Control Fields",
            "## Original Feedback",
            "## Interpretation",
            "## Work Items",
            "## Validation And Outcome",
            "## Closeout Checklist",
            "## Promotion Decision",
            "## Handoff And References",
        ):
            self.assertIn(section, text)

        self.assertEqual(re.search(r"^processing_state: (\w+)$", text, re.MULTILINE).group(1), "received")
        self.assertEqual(re.search(r"^validation_state: (\w+)$", text, re.MULTILINE).group(1), "none")
        self.assertEqual(re.search(r"^promotion_decision: (\w+)$", text, re.MULTILINE).group(1), "not_promoted")
        normalized = " ".join(text.split())
        self.assertIn(
            "Allowed `processing_state` values are `received`, `in_progress`, `blocked`, `deferred`, and `rejected`.",
            normalized,
        )
        self.assertIn(
            "Allowed `validation_state` values are `none`, `local_passed`, `user_pending`, and `production_passed`.",
            normalized,
        )

    def test_template_preserves_boundaries_and_closeout_rules(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertLess(text.index("## Original Feedback"), text.index("## Interpretation"))
        self.assertLess(text.index("## Interpretation"), text.index("## Work Items"))
        self.assertLess(text.index("## Work Items"), text.index("## Validation And Outcome"))
        self.assertLess(text.index("## Validation And Outcome"), text.index("## Closeout Checklist"))
        self.assertLess(text.index("## Closeout Checklist"), text.index("## Promotion Decision"))
        self.assertIn("Copy this file before any work starts", text)
        self.assertIn("preserve it verbatim", text)
        self.assertIn("local check passed", text)
        self.assertIn("does not close work", text)
        self.assertIn("Do not automatically convert feedback into a Claim", text)
        for checklist_item in (
            "Every work item has a status",
            "Remaining work is `none` only when no further action",
            "`local_passed` is not treated as user or production validation",
            "Deferred, blocked, and rejected work has a reason",
            "Completed evidence and artifact links are recorded",
            "`promotion_decision` remains `not_promoted`",
            "No Claim, Authority Ref, Memory, Bundle, projection, or Git state was changed",
        ):
            self.assertIn(checklist_item, text)
        self.assertIn("Do not mark the feedback complete", text)
        self.assertIsNotNone(re.search(r"deferred.*require a reason", text, re.IGNORECASE | re.DOTALL))
        self.assertIsNotNone(re.search(r"rejected.*require a reason", text, re.IGNORECASE | re.DOTALL))


if __name__ == "__main__":
    unittest.main()
