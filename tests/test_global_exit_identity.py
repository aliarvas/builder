"""T-028: v19 live run of Brief A (asks_back). PUB-08: two global special steps handed the call
back and forth without a word; PUB-05: a verify result without the overall field kept the call in
the identity step, and the sympathy line came only after the support question."""

from __future__ import annotations

import copy
import json
import unittest

from builder.extract import merge_groups
from builder.selfcheck import BUILDER, _sandbox, _compiled, global_always_exits, play, run_selfcheck, scenarios
from builder.spec import SpecError, parse_spec
from builder.workflow import GLOBAL_EXIT_CONDITION, IDENTITY_PASSED_VARIABLE, build_spec_workflow, _closing_code
from tests.test_selfcheck import SPECS
from tests.test_selfcheck_families import AB, BRIEF_A, failed, render
from tests.test_special_topic import ab_data, with_decline

NOW = "2026-10-14T11:00"


def identity_hook(workflow):
    tool = workflow["nodes"]["identity"]["tools"][0]
    return tool, tool["post_process_code"]


def run_hook(code, data, variables):
    result = {"status": "success", "status_code": 200, "data": dict(data)}
    exec(_compiled(code), _sandbox([], "test", result=result, vars=variables))
    return result["data"]


def say_first_spec():
    """The A+B spec with the brief's order: sympathy, then the support offer; a no closes."""
    data = with_decline(ab_data())
    for path in data["special_paths"]:
        if path["id"] == "hardship_support":
            path["say_first"] = True
    return data


class GlobalExitTests(unittest.TestCase):
    def test_no_global_step_leaves_by_always(self):
        for name in SPECS:
            spec, workflow = render(name)
            with self.subTest(spec=name):
                self.assertEqual([], global_always_exits(workflow))
                for key, node in workflow["global_nodes"].items():
                    for transition in node.get("transitions") or []:
                        self.assertNotEqual("always", transition["condition"].get("operator"), key)

    def test_the_v19_render_is_caught(self):
        # PUB-08: special_already_paid -> special_dispute -> special_already_paid ... for 50 s.
        spec, workflow = render(BRIEF_A)
        for node in workflow["global_nodes"].values():
            for transition in node.get("transitions") or []:
                if transition["condition"] == GLOBAL_EXIT_CONDITION:
                    transition["condition"] = {"operator": "always"}
        steps = {step for step, _ in global_always_exits(workflow)}
        self.assertIn("special_already_paid", steps)
        self.assertIn("special_dispute", steps)
        report = run_selfcheck(spec, workflow, NOW)
        flagged = {r.scenario for r in report.results if not r.passed and r.kind == BUILDER}
        self.assertIn("global_exit[special_already_paid]", flagged)

    def test_the_exit_holds_on_every_call(self):
        # `now` is a call variable, always set; the condition is deterministic, no intent call.
        spec, workflow = render(BRIEF_A)
        scenario = next(s for s in scenarios(spec, NOW) if s.id == "special_already_paid_over_choice_at_negotiate")
        sim, failures = play(workflow, spec, scenario, NOW)
        self.assertEqual([], failures)
        self.assertIn("special_already_paid", sim.path)
        self.assertNotIn("special_dispute", sim.path)


class IdentityKnownEarlierTests(unittest.TestCase):
    def test_two_right_answers_verify_when_the_overall_field_is_missing(self):
        spec, workflow = render(BRIEF_A)
        _, code = identity_hook(workflow)
        verified, answer = spec.identity.data["verified_field"], spec.identity.data["answer_verified_field"]
        variables = {}
        first = run_hook(code, {"ok": True, answer: True, "wrong_answers_left": 3}, variables)
        self.assertNotIn(verified, first)  # one question only
        second = run_hook(code, {"ok": True, answer: True, "wrong_answers_left": 3}, variables)
        self.assertIs(True, second[verified])
        self.assertEqual(2, variables[IDENTITY_PASSED_VARIABLE])

    def test_the_bank_overall_field_always_wins(self):
        spec, workflow = render(BRIEF_A)
        _, code = identity_hook(workflow)
        verified, answer = spec.identity.data["verified_field"], spec.identity.data["answer_verified_field"]
        variables = {IDENTITY_PASSED_VARIABLE: 5}
        data = run_hook(code, {"ok": True, answer: True, verified: False}, variables)
        self.assertIs(False, data[verified])
        wrong = run_hook(code, {"ok": True, answer: False}, {})
        self.assertNotIn(verified, wrong)

    def test_the_scenario_passes_and_the_v19_render_is_caught(self):
        for name in (BRIEF_A, AB):
            spec, workflow = render(name)
            with self.subTest(spec=name):
                self.assertEqual({}, failed(spec, workflow, {"identity_known_earlier"}, NOW))
                tool, code = identity_hook(workflow)
                tool["post_process_code"] = code.split("try:\n    data = result.get('data')")[0]
                result = failed(spec, workflow, {"identity_known_earlier"}, NOW)
                self.assertIn("the call does not reach end_call; it waits at identity",
                              result["identity_known_earlier"])


class SayFirstTests(unittest.TestCase):
    def test_the_sympathy_line_comes_before_the_offer(self):
        spec = parse_spec(say_first_spec())
        workflow = build_spec_workflow(spec, SPECS[AB][1])
        path = next(p for p in spec.special_paths if p.id == "hardship_support")
        node = workflow["global_nodes"]["special_hardship_support"]
        self.assertEqual(path.say.text.strip() + " " + path.ask.text.strip(), node["on_enter"]["text"])
        # Said once: the closing does not repeat it after the transfer.
        self.assertNotIn(json.dumps(path.say.text), _closing_code(spec).split("FIRST_LINES = [")[1].split("]")[0])
        report = run_selfcheck(spec, workflow, NOW)
        self.assertEqual([], [r.scenario for r in report.results if not r.passed and "hardship" in r.scenario])

    def test_without_say_first_nothing_changes(self):
        spec, workflow = render(AB)
        path = next(p for p in spec.special_paths if p.id == "hardship_support")
        self.assertEqual(path.ask.text, workflow["global_nodes"]["special_hardship_support"]["on_enter"]["text"])

    def test_a_question_without_the_line_is_caught(self):
        spec = parse_spec(say_first_spec())
        workflow = build_spec_workflow(spec, SPECS[AB][1])
        path = next(p for p in spec.special_paths if p.id == "hardship_support")
        node = workflow["global_nodes"]["special_hardship_support"]
        node["on_enter"]["text"] = path.ask.text  # the v19 render
        node["task_message"] = node["task_message"].replace(path.say.text.strip() + " ", "")
        result = failed(spec, workflow, {"special_hardship_support_declined"}, NOW)
        self.assertTrue(any("asks before saying" in f for f in result["special_hardship_support_declined"]))

    def test_say_first_needs_ask(self):
        data = ab_data()
        for path in data["special_paths"]:
            if path["id"] == "dispute":
                path["say_first"] = True
        with self.assertRaisesRegex(SpecError, "say_first"):
            parse_spec(data)
        data = say_first_spec()
        for path in data["special_paths"]:
            if path["id"] == "hardship_support":
                path["say_first"] = "yes"
        with self.assertRaisesRegex(SpecError, "say_first"):
            parse_spec(data)

    def test_extraction_drops_a_say_first_it_cannot_use(self):
        from tests.test_callback import groups_from_spec

        data = say_first_spec()
        for path in data["special_paths"]:
            if path["id"] == "dispute":
                path["say_first"] = True  # no ask: dropped
        merged = merge_groups(groups_from_spec(copy.deepcopy(data)))
        by_id = {path["id"]: path for path in merged["special_paths"]}
        self.assertIs(True, by_id["hardship_support"]["say_first"])
        self.assertNotIn("say_first", by_id["dispute"])
        parse_spec(merged)


if __name__ == "__main__":
    unittest.main()
