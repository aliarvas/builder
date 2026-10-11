"""T-030: one persuasion move per turn; the persuasion turn never reads back, claims a record,
thanks the customer or talks about another product (PUB-12)."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from builder.selfcheck import recorded_claim_gaps
from builder.spec import parse_spec
from builder.workflow import build_spec_workflow, workflow_prompt_estimates
from tests.test_selfcheck import SPECS


class PersuasionPromptTests(unittest.TestCase):
    def render(self, name, side_questions=True):
        path, tools = SPECS[name]
        data = json.loads(path.read_text(encoding="utf-8"))
        spec = parse_spec(data.get("spec", data))
        if side_questions:
            return spec, build_spec_workflow(spec, tools)
        with mock.patch("builder.workflow.side_question_steps", lambda spec, nodes: {}):
            return spec, build_spec_workflow(spec, tools)

    def test_the_persuasion_turn_rules(self):
        spec, workflow = self.render("brief-ab-extracted-v2.json")
        task = workflow["nodes"]["negotiate"]["task_message"]
        self.assertIn("Each turn: one reason the documents allow, then ask if and when they can pay", task)
        self.assertIn('never read back or sum up offers, say "record" or "confirm", or thank them', task)
        self.assertIn("Talk only about the {{", task)
        self.assertIn("Never say goodbye", task)  # the existing goodbye line covers the goodbye

    def test_budget_and_honesty_on_every_fixture(self):
        for name in SPECS:
            spec, workflow = self.render(name, side_questions=False)
            with self.subTest(spec=name):
                if spec.offer.data.get("persuasion_attempts") and name != "brief-ab-extracted.json":
                    self.assertLess(workflow_prompt_estimates(workflow)["negotiate"], 1700)
                self.assertEqual([], recorded_claim_gaps(self.render(name)[1]))


if __name__ == "__main__":
    unittest.main()
