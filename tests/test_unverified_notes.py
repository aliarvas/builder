"""T-016: a special path that closes the call before identity writes no product note. The
account is read only after identity, so the call has no product to note yet (the kit's
not_verified practice case expects ``notes: []``)."""

from __future__ import annotations

import copy
import json
import unittest

from builder.selfcheck import run_selfcheck, scenarios
from builder.spec import parse_spec
from builder.workflow import build_spec_workflow
from tests.test_selfcheck import NOW, SPECS

PATH, TOOLS = SPECS["spec-brief-b.json"]


def spec_with_path(available_in):
    data = json.loads(PATH.read_text(encoding="utf-8"))
    data = copy.deepcopy(data.get("spec", data))
    data["special_paths"].append({
        "id": "stops_talking",
        "when": {"text": "The person says twice that they do not want to talk.", "source": "test"},
        "say": {"text": "Thank you for your time. Goodbye.", "source": "test"},
        "tool": "", "tool_args": {}, "outcome": "not_verified", "reason": "declined",
        "available_in": available_in, "then": "close"})
    return parse_spec(data)


def played(spec, name):
    report = run_selfcheck(spec, build_spec_workflow(spec, TOOLS), NOW)
    return next(item for item in report.results if item.scenario == name)


class UnverifiedCloseTests(unittest.TestCase):
    def test_a_close_before_identity_expects_no_notes(self):
        spec = spec_with_path(["opening", "identity"])
        expected = next(item for item in scenarios(spec, NOW) if item.id == "special_stops_talking")
        self.assertEqual("identity", expected.step)
        self.assertEqual([], expected.notes)
        result = played(spec, "special_stops_talking")
        self.assertTrue(result.passed, result.reason)

    def test_a_close_after_the_account_still_expects_a_note_per_product(self):
        spec = spec_with_path(["negotiate"])
        expected = next(item for item in scenarios(spec, NOW) if item.id == "special_stops_talking")
        self.assertEqual([("p1", spec.closing.data["product_notes"]["refused_reason"])], list(expected.notes))
        result = played(spec, "special_stops_talking")
        self.assertTrue(result.passed, result.reason)


if __name__ == "__main__":
    unittest.main()
