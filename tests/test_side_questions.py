"""T-019 (F-074): a side question asked in the same turn as a business answer is not lost. The
steps where a spoken-only returning special path may fire, or that speak right after a turn in
one, list each such path's answer."""

from __future__ import annotations

import copy
import json
import unittest

from builder.prompts import NO_GOODBYE_LINE, SIDE_QUESTION_ITEM, SIDE_QUESTION_LINE
from builder.spec import parse_spec
from builder.workflow import (
    build_spec_workflow, next_speakers, side_question_paths, source_steps,
)
from tests.test_selfcheck import SPECS, load


def item(path):
    return SIDE_QUESTION_ITEM.text.replace("{when}", path.when.text.strip()).replace("{say}", path.say.text.strip())


def conversations(nodes):
    return {key: node for key, node in nodes.items() if node.get("node_type") == "conversation"}


def expected_steps(spec, nodes, path):
    """The steps the path's answer belongs to, computed from the render: its own steps, and the
    conversation steps reached right after a turn in one of them."""
    own = set(source_steps(path)) & set(conversations(nodes))
    return own | {target for step in own for target in next_speakers(nodes, step)}


class SideQuestionLintTests(unittest.TestCase):
    def test_every_answer_is_listed_exactly_where_it_belongs(self):
        seen = 0
        for name, (path_file, tools) in SPECS.items():
            spec = load(path_file)
            workflow = build_spec_workflow(spec, tools)
            nodes = workflow["nodes"]
            paths = side_question_paths(spec)
            seen += bool(paths)
            for key, node in {**conversations(nodes), **conversations(workflow.get("global_nodes", {}))}.items():
                with self.subTest(spec=name, step=key):
                    here = [path for path in paths
                            if key in nodes and key in expected_steps(spec, nodes, path)]
                    for field in ("task_message", "loop_prompt"):
                        if field not in node:
                            continue
                        text = node[field]
                        self.assertEqual(bool(here), SIDE_QUESTION_LINE.text in text, field)
                        for path in paths:
                            self.assertEqual(path in here, item(path) in text, (field, path.id))
                        if here:
                            # After the goodbye line, before the tool rule, in path order.
                            start = text.index(SIDE_QUESTION_LINE.text)
                            self.assertLess(text.index(NO_GOODBYE_LINE.text), start)
                            positions = [text.index(item(path)) for path in here]
                            self.assertEqual(sorted(positions), positions)
                            if "Tool-use rule for this turn" in text:
                                self.assertLess(positions[-1], text.index("Tool-use rule for this turn"))
        self.assertGreater(seen, 2)  # recorded extractions with robot and scam questions

    def test_only_spoken_returning_paths_without_a_tool(self):
        for name, (path_file, _) in SPECS.items():
            spec = load(path_file)
            for path in side_question_paths(spec):
                with self.subTest(spec=name, path=path.id):
                    self.assertNotEqual("close", path.then)
                    self.assertFalse(path.tool)
                    self.assertFalse(path.ask)
                    self.assertTrue(path.say.text.strip())

    def test_the_pub_04_turn(self):
        # "I can pay on <date>. Are you a robot?" in negotiate: the date goes to the offer check;
        # the steps that speak next (and negotiate itself) carry the answer.
        path_file, tools = SPECS["brief-ab-extracted-v2.json"]
        spec = load(path_file)
        robot = next(path for path in side_question_paths(spec) if "robot" in path.when.text)
        nodes = build_spec_workflow(spec, tools)["nodes"]
        for key in ("negotiate", "offer_say", "revise_ask", "confirm_record", "identity", "opening"):
            self.assertIn(item(robot), nodes[key]["task_message"], key)
        # Written out by hand: the robot path is available at opening, third_party, identity,
        # negotiate and confirm_record; opening_reask follows opening (unclear answer),
        # third_party_ask follows third_party (callback re-ask), offer_say and revise_ask follow
        # negotiate and confirm_record. No other conversation step lists it.
        listed = {key for key, node in conversations(nodes).items() if item(robot) in node["task_message"]}
        self.assertEqual({"opening", "opening_reask", "third_party", "third_party_ask", "identity", "negotiate",
                          "offer_say", "revise_ask", "confirm_record"}, listed)
        # A step neither listed nor reached right after one gets nothing.
        self.assertNotIn(SIDE_QUESTION_LINE.text, json.dumps(build_spec_workflow(spec, tools).get("global_nodes")))

    def test_a_path_with_a_tool_or_a_closing_path_is_not_listed(self):
        path_file, tools = SPECS["brief-ab-extracted-v2.json"]
        data = json.loads(path_file.read_text(encoding="utf-8"))
        data = copy.deepcopy(data.get("spec", data))
        for path in data["special_paths"]:
            if path["then"] != "close" and not path["tool"]:
                path["then"] = "close"
        spec = parse_spec(data)
        self.assertEqual([], side_question_paths(spec))
        self.assertNotIn(SIDE_QUESTION_LINE.text, json.dumps(build_spec_workflow(spec, tools)))

    def test_a_spec_without_such_paths_renders_no_line(self):
        for name in ("spec-brief-a.json", "spec-brief-b.json"):
            path_file, tools = SPECS[name]
            self.assertNotIn(SIDE_QUESTION_LINE.text, json.dumps(build_spec_workflow(load(path_file), tools)))


if __name__ == "__main__":
    unittest.main()
