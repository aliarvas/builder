"""T-029: a goodbye leaves every conversation step. Normal steps through the global goodbye
step, global conversation steps through a choice value of their own; the goodbye closes with
the state the end-of-call hook would write before identity, the third party's close without a
callback, or a hang-up after identity (accepted offers: the read-back once)."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest import mock

from builder.goodbye import CUSTOMER_ENDS_CALL, CUSTOMER_GOODBYE, GOODBYE_VALUE, goodbye_exit_gaps, goodbye_states
from builder.selfcheck import run_selfcheck
from builder.spec import parse_spec
from builder.workflow import build_spec_workflow
from tests.test_selfcheck import KIT_TOOLS, NOW, SPECS, load

ROOT = Path(__file__).resolve().parents[1]
LIVE = ("tests/fixtures/replay/brief-a-live-spec.json", "tests/fixtures/replay/brief-ab-live-spec.json")


def live(path):
    data = json.loads((ROOT / path).read_text(encoding="utf-8"))
    return parse_spec(data.get("spec", data))


def renders():
    for name, (path, tools) in SPECS.items():
        spec = load(path)
        yield name, spec, build_spec_workflow(spec, tools)
    for path in LIVE:
        spec = live(path)
        yield Path(path).name, spec, build_spec_workflow(spec, KIT_TOOLS)


class StaticCheckTests(unittest.TestCase):
    def test_every_step_that_waits_has_a_goodbye_exit(self):
        seen = 0
        for name, spec, workflow in renders():
            seen += 1
            with self.subTest(spec=name):
                self.assertEqual([], goodbye_exit_gaps(workflow))
        self.assertEqual(12, seen)

    def test_a_step_without_the_exit_is_named(self):
        spec = live(LIVE[1])
        workflow = build_spec_workflow(spec, KIT_TOOLS)
        broken = copy.deepcopy(workflow)
        broken["global_nodes"][CUSTOMER_ENDS_CALL]["excluded_nodes"].append("identity")
        ask = next(key for key, node in broken["global_nodes"].items()
                   if any(t["target_node"] == CUSTOMER_GOODBYE for t in node.get("transitions", [])))
        broken["global_nodes"][ask]["transitions"] = [
            t for t in broken["global_nodes"][ask]["transitions"] if t["target_node"] != CUSTOMER_GOODBYE]
        self.assertEqual({"identity", ask}, {step for step, _ in goodbye_exit_gaps(broken)})
        failed = {item.scenario for item in run_selfcheck(spec, broken, NOW).results if not item.passed}
        self.assertTrue({"goodbye_exit[identity]", f"goodbye_exit[{ask}]"} <= failed, failed)

    def test_global_ask_steps_get_the_goodbye_value(self):
        workflow = build_spec_workflow(live(LIVE[1]), KIT_TOOLS)
        asks = [node for node in workflow["global_nodes"].values()
                if node.get("node_type") == "conversation" and not node.get("passthrough")]
        self.assertTrue(asks)
        for node in asks:
            field = node["extraction_schema"][0]
            self.assertIn(GOODBYE_VALUE, field["enum_values"])
            self.assertIn(GOODBYE_VALUE + ": the customer only says goodbye", field["description"])
            self.assertEqual(CUSTOMER_GOODBYE, node["transitions"][0]["target_node"])


class StateTests(unittest.TestCase):
    def test_the_states_follow_the_end_of_call_hook(self):
        spec = live(LIVE[0])
        self.assertEqual(("hangup", "hangup_unverified", "third_party:no_callback"), goodbye_states(spec))
        data = json.loads((ROOT / LIVE[0]).read_text(encoding="utf-8"))
        data = data.get("spec", data)
        for row in data["outcomes"]:
            row["on"] = [state for state in row["on"] if state not in ("hangup_unverified", "hangup")]
        data["third_party"].pop("callback_window", None)
        after, before, third = goodbye_states(parse_spec(data))
        self.assertEqual(("default", "default"), (after, before))
        self.assertEqual("third_party:" + data["third_party"]["close_values"][0], third)


class PlayTests(unittest.TestCase):
    STEPS = ("goodbye_opening", "goodbye_identity", "goodbye_third_party", "goodbye_negotiate")

    def results(self, spec, workflow):
        return {item.scenario: item for item in run_selfcheck(spec, workflow, NOW).results}

    def test_a_goodbye_at_each_kind_of_step_ends_the_call(self):
        for path in LIVE:
            spec = live(path)
            results = self.results(spec, build_spec_workflow(spec, KIT_TOOLS))
            special = [name for name in results if name.startswith("goodbye_special_")]
            with self.subTest(spec=path):
                self.assertTrue(special)
                for name in (*self.STEPS, *special):
                    self.assertTrue(results[name].passed, (name, results[name].reason))

    def test_without_the_goodbye_step_the_plays_fail(self):
        spec = live(LIVE[1])
        with mock.patch("builder.workflow.add_goodbye_exit", lambda *args: None):
            workflow = build_spec_workflow(spec, KIT_TOOLS)
        results = self.results(spec, workflow)
        for name in self.STEPS:
            self.assertFalse(results[name].passed, name)


if __name__ == "__main__":
    unittest.main()
