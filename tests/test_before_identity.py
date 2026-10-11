"""T-015: a third party who is the customer (F-069), no security questions before identity
(F-070), every opening value described (F-071), and no goodbye outside the closing (F-072)."""

from __future__ import annotations

import copy
import json
import unittest

from builder.prompts import NO_GOODBYE_LINE, NO_SECURITY_QUESTIONS_LINE
from builder.selfcheck import BUILDER, run_selfcheck
from builder.spec import FRAMEWORK_NONE_VALUE, OPENING_GREETING_VALUE, THIRD_PARTY_CUSTOMER_VALUE, parse_spec
from builder.workflow import (
    BEFORE_IDENTITY_STEPS, CALL_END_STEPS, THIRD_PARTY_CUSTOMER, build_spec_workflow, who_answered_description,
)
from tests.test_selfcheck import NOW, SPECS, load


def rendered():
    for name, (path, tools) in SPECS.items():
        spec = load(path)
        yield name, spec, build_spec_workflow(spec, tools)


def conversations(workflow):
    return {key: node for key, node in {**workflow["nodes"], **workflow.get("global_nodes", {})}.items()
            if node.get("node_type") == "conversation"}


class PromptLintTests(unittest.TestCase):
    def test_no_conversation_step_may_say_goodbye_unless_it_ends_the_call(self):
        for name, _, workflow in rendered():
            for key, node in conversations(workflow).items():
                with self.subTest(spec=name, step=key):
                    ends = any(t["target_node"] in CALL_END_STEPS for t in node.get("transitions", []))
                    for field in ("task_message", "loop_prompt"):
                        if field in node:
                            self.assertEqual(not ends, NO_GOODBYE_LINE.text in node[field], field)

    def test_steps_before_identity_never_ask_security_questions(self):
        for name, _, workflow in rendered():
            for key, node in conversations(workflow).items():
                with self.subTest(spec=name, step=key):
                    self.assertEqual(key in BEFORE_IDENTITY_STEPS, NO_SECURITY_QUESTIONS_LINE.text in node["task_message"])
            self.assertTrue(set(BEFORE_IDENTITY_STEPS) <= set(conversations(workflow)), name)

    def test_the_fixed_lines_come_before_the_tool_rule(self):
        _, _, workflow = next(rendered())
        task = workflow["nodes"]["third_party"]["task_message"]
        self.assertLess(task.index(NO_GOODBYE_LINE.text), task.index("Tool-use rule for this turn"))


class OpeningDescriptionTests(unittest.TestCase):
    def test_every_opening_value_is_described(self):
        for name, spec, workflow in rendered():
            opening = spec.opening.data
            field = workflow["nodes"]["opening"]["extraction_schema"][0]
            with self.subTest(spec=name):
                self.assertEqual(field, workflow["nodes"]["opening_reask"]["extraction_schema"][0])
                for value in field["enum_values"]:
                    if value != FRAMEWORK_NONE_VALUE:
                        self.assertIn(f"{value}:", field["description"])
                for value in opening["third_party_values"]:
                    self.assertIn(f"{value}: only when the person clearly says they are not the customer",
                                  field["description"])
                for value in opening["stay_values"]:
                    self.assertIn(f"{value}: anything else that does not confirm", field["description"])
                self.assertIn(opening["unclear_instruction"]["text"], field["description"])
                self.assertNotIn("{", field["description"])

    def test_a_route_without_values_has_no_line(self):
        spec = load(SPECS["spec-brief-a.json"][0])
        spec.opening.data["stay_values"] = []
        text = who_answered_description(spec)
        self.assertNotIn("anything else that does not confirm", text)
        self.assertIn(f"{OPENING_GREETING_VALUE}:", text)


class CustomerReturnTests(unittest.TestCase):
    def test_the_third_party_step_routes_the_customer_back_to_the_confirmation(self):
        for name, spec, workflow in rendered():
            nodes = workflow["nodes"]
            intent = spec.third_party.data["intent_variable"]
            with self.subTest(spec=name):
                field = next(f for f in nodes["third_party"]["extraction_schema"] if f["name"] == intent)
                self.assertIn(THIRD_PARTY_CUSTOMER_VALUE, field["enum_values"])
                self.assertIn(f"{THIRD_PARTY_CUSTOMER_VALUE}: the person says they are the customer", field["description"])
                for key in ("third_party", "third_party_ask"):
                    targets = [t["target_node"] for t in nodes[key]["transitions"]]
                    self.assertIn(THIRD_PARTY_CUSTOMER, targets, key)
                step = nodes[THIRD_PARTY_CUSTOMER]
                self.assertEqual("code", step["node_type"])
                self.assertEqual(["opening_reask"], [t["target_node"] for t in step["transitions"]])
                code = step["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
                variables = {intent: THIRD_PARTY_CUSTOMER_VALUE, spec.opening.data["who_answered_variable"]: "x"}
                exec(code, {"vars": variables})
                self.assertEqual({FRAMEWORK_NONE_VALUE}, set(variables.values()))

    def test_the_self_check_plays_it_and_catches_a_lost_route(self):
        spec = load(SPECS["spec-brief-a.json"][0])
        workflow = build_spec_workflow(spec, SPECS["spec-brief-a.json"][1])
        report = run_selfcheck(spec, workflow, NOW)
        played = next(item for item in report.results if item.scenario == "third_party_is_customer")
        self.assertTrue(played.passed, played.reason)
        for key in ("third_party", "third_party_ask"):
            workflow["nodes"][key]["transitions"] = [
                t for t in workflow["nodes"][key]["transitions"] if t["target_node"] != THIRD_PARTY_CUSTOMER]
        report = run_selfcheck(spec, workflow, NOW)
        lost = next(item for item in report.results if item.scenario == "third_party_is_customer")
        self.assertFalse(lost.passed)
        self.assertEqual(BUILDER, lost.kind)
        self.assertIn("dead end at third_party", lost.reason)

    def test_a_spec_that_already_uses_the_value_keeps_its_own_routes(self):
        data = json.loads(SPECS["spec-brief-a.json"][0].read_text(encoding="utf-8"))
        data = copy.deepcopy(data.get("spec", data))
        data["third_party"]["intent_values"].append(THIRD_PARTY_CUSTOMER_VALUE)
        workflow = build_spec_workflow(parse_spec(data), SPECS["spec-brief-a.json"][1])
        self.assertNotIn(THIRD_PARTY_CUSTOMER, workflow["nodes"])


if __name__ == "__main__":
    unittest.main()
