"""F-056/F-059: one spoken message in the closing turn, and the path's line only after its tool."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from builder.prompts import SPECIAL_CLOSE_TOOL_TASK_TEMPLATE, SPECIAL_TOOL_FAILED_SAY
from builder.selfcheck import SILENT_TOOL_RULE
from builder.selfcheck import spoken_per_turn as selfcheck_spoken_per_turn
from builder.spec import parse_spec
from builder.tools_from_openapi import tools_from_openapi
from builder.workflow import build_spec_workflow, speakable_spec, special_result_variable
from tests.test_multi_step import FIXTURES, code_of, kit_tools, load_spec, walk

VERIFIED = {"who_answered": "customer", "identity_verified": "true", "identity_attempts_left": 2}
ROOT = Path(__file__).resolve().parents[1]
KIT_TOOLS = tools_from_openapi(json.loads((ROOT / "build-the-builder-v2/tools/openapi.json").read_text(encoding="utf-8")))
EXTRACTED = tuple(ROOT / "tests/fixtures/extract" / name for name in (
    "brief-a-v11-extracted.json", "brief-ab-extracted.json", "brief-ab-extracted-tagged.json",
))
# Steps of a special path and of the closing chain; the walk stops anywhere else.
CHAIN = ("special_", "close_", "closing", "end_call")


def speaks(node):
    return node.get("on_enter", {}).get("type") in ("tts", "llm")


def all_workflows():
    for index, fixture in enumerate(FIXTURES):
        yield fixture.name, build_spec_workflow(load_spec(fixture), kit_tools(index))
    for fixture in EXTRACTED:
        data = json.loads(fixture.read_text(encoding="utf-8"))
        yield fixture.name, build_spec_workflow(parse_spec(data), KIT_TOOLS)


def spoken_per_turn(workflow, start):
    """T-012: the builder's self-check walker (``builder.selfcheck.spoken_per_turn``)."""
    return selfcheck_spoken_per_turn(workflow, start, CHAIN)


def closing_sentence(workflow, variables):
    variables = dict(variables)
    exec(code_of(workflow["nodes"]["closing"]), {"vars": variables})
    return variables


class ClosingTurnTests(unittest.TestCase):
    def test_at_most_one_spoken_step_per_customer_turn_from_a_closing_entry(self):
        """Review fix: walk from every special-path entry to end_call, conversation entries
        included; a closing path whose tool the model fills must not speak in the tool turn."""
        for name, workflow in all_workflows():
            closing_entries = 0
            for key in workflow["global_nodes"]:
                worst, reached = spoken_per_turn(workflow, key)
                closing_entries += reached
                with self.subTest(fixture=name, entry=key):
                    self.assertLessEqual(worst, 1)
            with self.subTest(fixture=name):
                self.assertGreater(closing_entries, 0)

    def test_model_filled_closing_tool_step_says_nothing_with_the_tool(self):
        data = json.loads(EXTRACTED[2].read_text(encoding="utf-8"))
        spec, _ = speakable_spec(parse_spec(data))  # the lines the workflow really says
        workflow = build_spec_workflow(parse_spec(data), KIT_TOOLS)
        shaped = [path for path in spec.special_paths if path.then == "close" and path.tool
                  and workflow["nodes"].get("special_" + path.id, {}).get("node_type") == "conversation"]
        self.assertTrue(shaped)
        self.assertIn(SILENT_TOOL_RULE, SPECIAL_CLOSE_TOOL_TASK_TEMPLATE.text)  # the walker's silent rule
        for path in shaped:
            task = workflow["nodes"]["special_" + path.id]["task_message"]
            self.assertIn(SILENT_TOOL_RULE, task)
            self.assertNotIn(path.say.text, task)
            result = closing_sentence(workflow, {**VERIFIED, special_result_variable(path): "true"})
            self.assertEqual(1, result["closing_sentence"].count(path.say.text))

    def test_no_spoken_step_reaches_closing_without_waiting(self):
        """A spoken step followed by passthrough steps into ``closing`` makes the closing
        turn speak twice (closing_say speaks too), and the platform ends the turn at the
        first line (F-056)."""
        for index, fixture in enumerate(FIXTURES):
            workflow = build_spec_workflow(load_spec(fixture), kit_tools(index))
            every = {**workflow["nodes"], **workflow["global_nodes"]}
            for key, node in every.items():
                if key == "closing_say" or not speaks(node) or not node.get("passthrough"):
                    continue
                seen, todo = set(), [key]
                while todo:
                    current = todo.pop()
                    if current in seen or current not in every:
                        continue
                    seen.add(current)
                    step = every[current]
                    if current != key and not step.get("passthrough"):
                        continue
                    targets = [t["target_node"] for t in step.get("transitions", [])]
                    targets.append(step.get("passthrough_default_transition"))
                    with self.subTest(fixture=fixture.name, start=key, via=current):
                        self.assertNotIn("closing", targets)
                    todo.extend(target for target in targets if target)

    def test_closing_special_steps_are_silent(self):
        for index, fixture in enumerate(FIXTURES):
            spec = load_spec(fixture)
            workflow = build_spec_workflow(spec, kit_tools(index))
            every = {**workflow["nodes"], **workflow["global_nodes"]}
            for path in spec.special_paths:
                if path.then != "close":
                    continue
                key = "special_" + path.id
                action = key + "_go" if path.ask else key
                with self.subTest(fixture=fixture.name, path=path.id):
                    self.assertEqual({"type": "silent"}, every[action]["on_enter"])
                    if path.tool:
                        self.assertEqual({"type": "silent"}, every[action + "_call"]["on_enter"])

    def test_tool_path_line_is_said_once_after_the_tool_succeeded(self):
        for index, fixture in enumerate(FIXTURES):
            spec = load_spec(fixture)
            workflow = build_spec_workflow(spec, kit_tools(index))
            for path in spec.special_paths:
                if path.then != "close" or not path.tool:
                    continue
                with self.subTest(fixture=fixture.name, path=path.id):
                    key = "special_" + path.id
                    start = {special_result_variable(path) + "_choice": "proceed"} if path.ask else {}
                    variables = {**VERIFIED, **start, special_result_variable(path): "true"}
                    self.assertEqual("closing", walk(workflow, key, variables))
                    result = closing_sentence(workflow, variables)
                    self.assertEqual("special:" + path.id, result["close_resolved_state"])
                    self.assertEqual(1, result["closing_sentence"].count(path.say.text))
                    self.assertTrue(result["closing_sentence"].startswith(path.say.text))

    def test_failed_tool_never_says_the_line_and_says_plainly_it_failed(self):
        for index, fixture in enumerate(FIXTURES):
            spec = load_spec(fixture)
            workflow = build_spec_workflow(spec, kit_tools(index))
            for path in spec.special_paths:
                if path.then != "close" or not path.tool:
                    continue
                with self.subTest(fixture=fixture.name, path=path.id):
                    key = "special_" + path.id
                    start = {special_result_variable(path) + "_choice": "proceed"} if path.ask else {}
                    variables = {**VERIFIED, **start, special_result_variable(path): "false"}
                    self.assertEqual("closing", walk(workflow, key, variables))
                    result = closing_sentence(workflow, variables)
                    self.assertEqual("special_tool_failed", variables.get("close_state"))
                    self.assertNotIn(path.say.text, result["closing_sentence"])
                    self.assertTrue(result["closing_sentence"].startswith(SPECIAL_TOOL_FAILED_SAY.text))

    def test_a_spec_line_for_the_failed_state_replaces_the_builder_line(self):
        data = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        row = next(item for item in data["outcomes"] if item.get("reason") == "service_error")
        row["on"] = [*row["on"], "special_tool_failed"]
        workflow = build_spec_workflow(parse_spec(data), kit_tools(0))
        result = closing_sentence(workflow, {"close_state": "special_tool_failed"})
        self.assertEqual(row["say"]["text"], result["closing_sentence"])

    def test_identical_line_and_closing_sentence_are_said_once(self):
        # The PUB-09 shape: the path's line is also its outcome's closing sentence.
        data = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        path = next(item for item in data["special_paths"] if item.get("tool"))
        row = next(item for item in data["outcomes"]
                   if (item["outcome"], item.get("reason")) == (path["outcome"], path.get("reason")))
        line = "I will connect you with a colleague. Thank you for your time. Goodbye."
        path["say"]["text"] = row["say"]["text"] = line
        spec = parse_spec(data)
        workflow = build_spec_workflow(spec, kit_tools(0))
        variables = {**VERIFIED, special_result_variable(spec.special_paths[data["special_paths"].index(path)]): "true"}
        self.assertEqual(line, closing_sentence(workflow, variables)["closing_sentence"])
        # A line already contained in the closing sentence is not repeated either.
        path["say"]["text"] = "I will connect you with a colleague."
        workflow = build_spec_workflow(parse_spec(copy.deepcopy(data)), kit_tools(0))
        self.assertEqual(line, closing_sentence(workflow, variables)["closing_sentence"])

    def test_line_without_tool_is_kept_when_a_recorded_promise_wins(self):
        spec = load_spec(FIXTURES[0])
        workflow = build_spec_workflow(spec, kit_tools(0))
        path = next(item for item in spec.special_paths if item.then == "close" and not item.tool)
        result = closing_sentence(workflow, {"close_state": "special:" + path.id, "promise_recorded_count": 1})
        self.assertEqual("promise", result["close_outcome"])
        self.assertTrue(result["closing_sentence"].startswith(path.say.text))
        self.assertEqual(1, result["closing_sentence"].count(path.say.text))

    def test_other_states_get_no_special_line(self):
        spec = load_spec(FIXTURES[0])
        workflow = build_spec_workflow(spec, kit_tools(0))
        sentence = closing_sentence(workflow, {"close_state": "promise_recorded"})["closing_sentence"]
        for path in spec.special_paths:
            self.assertNotIn(path.say.text, sentence)
        self.assertNotIn(SPECIAL_TOOL_FAILED_SAY.text, sentence)


if __name__ == "__main__":
    unittest.main()
