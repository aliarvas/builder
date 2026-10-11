"""T-017: without closing.product_notes.outcome_from_notes, a call without a promise whose every
product a returning special path noted, all naming the same outcome row, closes on that row."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from builder.product_notes import NOTES_OUTCOME
from builder.selfcheck import _Plan, play, run_selfcheck
from builder.spec import parse_spec, special_note_pairs
from builder.workflow import build_spec_workflow
from tests.test_notes_outcome import close_body, noted_call, path_with_reason
from tests.test_selfcheck import KIT_TOOLS, NOW

ROOT = Path(__file__).resolve().parents[1]


def recorded():
    """A recorded A+B extraction: returning note paths, no outcome_from_notes block."""
    data = json.loads((ROOT / "tests/fixtures/extract/brief-ab-extracted-v2.json").read_text(encoding="utf-8"))
    spec = parse_spec(data.get("spec", data))
    assert not spec.closing.data["product_notes"].get("outcome_from_notes")
    return spec


def row_of(spec, reason):
    path = path_with_reason(spec, reason)
    return path.outcome, path.reason


def default_row(spec):
    row = next(item for item in spec.outcomes if "default" in item.on)
    return row.outcome, row.reason


class SpecialNotesOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.spec = recorded()
        self.workflow = build_spec_workflow(self.spec, KIT_TOOLS)

    def play(self, scenario):
        sim, failures = play(self.workflow, self.spec, scenario, NOW)
        self.assertEqual([], failures)
        return close_body(self.spec, sim)

    def test_the_step_is_rendered(self):
        self.assertIn(NOTES_OUTCOME, self.workflow["nodes"])
        self.assertEqual({"paid", "dispute"}, set(special_note_pairs(self.spec)))

    def test_one_product_disputed_closes_with_the_dispute_row(self):
        self.assertEqual(row_of(self.spec, "dispute"), self.play(noted_call(self.spec, ["dispute"])))

    def test_two_products_both_paid_close_with_the_paid_row(self):
        self.assertEqual(row_of(self.spec, "paid"), self.play(noted_call(self.spec, ["paid", "paid"])))

    def test_mixed_rows_keep_the_close_the_call_state_gives(self):
        self.assertEqual(default_row(self.spec), self.play(noted_call(self.spec, ["paid", "dispute"])))

    def test_a_product_without_a_special_note_keeps_the_close(self):
        # p1 refused by the customer (the note loop writes it), p2 disputed by the special path.
        plan = _Plan(self.spec, NOW)
        scenario = noted_call(self.spec, ["dispute", "dispute"])
        scenario.actions = [*plan.reach_negotiation(), {**plan.refuse(), "repeat": False},
                            *[action for action in scenario.actions if action.get("number") == 2], plan.refuse()]
        refused = self.spec.closing.data["product_notes"]["refused_reason"]
        scenario.notes = [("p1", refused), ("p2", "dispute")]
        self.assertEqual(default_row(self.spec), self.play(scenario))

    def test_the_self_check_reaches_the_rows(self):
        report = run_selfcheck(self.spec, self.workflow, NOW)
        failed = [item.scenario for item in report.results if not item.passed]
        self.assertEqual([], failed)


if __name__ == "__main__":
    unittest.main()
