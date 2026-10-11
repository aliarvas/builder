"""T-035: loops of silent steps end even when the code sandbox fails.

Live v20 (A+B, PUB-12): after one note every code run failed, ``note_state`` kept "note" and
``note_next`` -> ``note_record`` sent about 40 notes. The note step now leaves on the engine's
call counters (as F-067 does for the record and close loops); a static check finds every
loop of code and api steps and needs such an exit; a sandbox-down walk proves the chain from
the closing and from the record loop reaches end_call after a bounded number of calls."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from builder.code_cycles import code_cycle_gaps, sandbox_down_chain, sandbox_down_walk, silent_cycles
from builder.offer_check import ESTIMATED_PRODUCTS
from builder.product_notes import NOTE_LOOP_CAP, NOTE_NEXT, NOTE_RECORD, NOTE_SUCCESS_CAP
from builder.selfcheck import run_selfcheck, sandbox_down_gaps
from builder.spec import parse_spec
from builder.workflow import build_spec_workflow
from tests.test_selfcheck import KIT_TOOLS, NOW, SPECS, load

ROOT = Path(__file__).resolve().parents[1]


def renders():
    """The 10 fixtures and the live Brief A and A+B specs."""
    result = [(name, load(path), tools) for name, (path, tools) in SPECS.items()]
    for name, path in (("live-a", "tests/fixtures/replay/brief-a-live-spec.json"),
                       ("live-ab", "traces/brief-a+brief-b.spec.json")):
        file = ROOT / path
        if file.exists():
            data = json.loads(file.read_text(encoding="utf-8"))
            result.append((name, parse_spec(data.get("spec", data)), KIT_TOOLS))
    return result


def with_notes():
    return next(build_spec_workflow(spec, tools) for _, spec, tools in renders()
                if NOTE_NEXT in build_spec_workflow(spec, tools)["nodes"])


def without_counter_exit(workflow, step):
    workflow = copy.deepcopy(workflow)
    node = workflow["nodes"][step]
    node["transitions"] = [item for item in node["transitions"] if "_count" not in json.dumps(item["condition"])
                           or item["condition"].get("operator") == "always"]
    return workflow


class CodeCycleTests(unittest.TestCase):
    def test_no_unguarded_loop_on_any_render(self):
        for name, spec, tools in renders():
            with self.subTest(spec=name):
                workflow = build_spec_workflow(spec, tools)
                self.assertTrue(silent_cycles(workflow))
                self.assertEqual([], code_cycle_gaps(workflow))
                self.assertEqual([], sandbox_down_gaps(workflow))
                failed = {item.scenario for item in run_selfcheck(spec, workflow, NOW).results
                          if item.scenario.startswith("code_cycle[")}
                self.assertEqual(set(), failed)

    def test_the_note_loop_ends_on_the_engine_counters(self):
        workflow = with_notes()
        group = [NOTE_NEXT, NOTE_RECORD]
        self.assertIn(group, silent_cycles(workflow))
        # Every call fails: two tries per product for twice the assumed products, then out.
        self.assertEqual(NOTE_LOOP_CAP + 1, sandbox_down_walk(workflow, group)[1])
        # Every call succeeds (v20: the repeated notes were written): fewer.
        self.assertEqual(NOTE_SUCCESS_CAP + 1, sandbox_down_walk(workflow, group, result="success")[1])
        for result in ("failure", "success"):
            reached, calls = sandbox_down_chain(workflow, "closing", result=result)
            self.assertEqual("end_call", reached)
            self.assertLessEqual(calls[NOTE_RECORD], NOTE_LOOP_CAP + 1)
            self.assertLessEqual(calls["close_record"], 2)

    def test_v20_without_the_guard_the_check_names_the_loop(self):
        workflow = without_counter_exit(with_notes(), NOTE_RECORD)
        gaps = dict(code_cycle_gaps(workflow))
        self.assertIn("note_next+note_record", gaps)
        self.assertIn("call counters", gaps["note_next+note_record"])
        self.assertEqual("", sandbox_down_chain(workflow, "closing")[0])
        self.assertTrue(any(key.startswith("closing:") for key, _ in sandbox_down_gaps(workflow)))

    def test_the_check_names_the_close_and_record_loops_without_their_guards(self):
        workflow = with_notes()
        self.assertIn("close_attempt+close_record", dict(code_cycle_gaps(without_counter_exit(workflow, "close_record"))))
        self.assertIn("confirmation_progress+record_next+record_promise",
                      dict(code_cycle_gaps(without_counter_exit(workflow, "record_next"))))

    def test_a_loop_of_code_steps_alone_cannot_be_guarded(self):
        def code(key, target):
            return {"name": key, "node_type": "code", "transitions": [
                {"target_node": "end_call", "description": "done", "condition": {"logic": "or", "conditions": [
                    {"variable": "state", "operator": "equals", "operand": "done"}]}},
                {"target_node": target, "description": "again", "condition": {"operator": "always"}}]}
        workflow = {"nodes": {"a": code("a", "b"), "b": code("b", "a"),
                              "end_call": {"name": "end_call", "node_type": "end_call", "transitions": []}}}
        self.assertEqual([["a", "b"]], silent_cycles(workflow))
        self.assertIn("no api step", dict(code_cycle_gaps(workflow))["a+b"])

    def test_the_caps_never_cut_a_working_loop(self):
        # The largest kit case has three products; each needs at most one written note and two tries.
        cases = json.loads((ROOT / "build-the-builder-v2/public-test-set.json").read_text(encoding="utf-8"))
        most = max(len(case.get("products") or (case.get("account") or {}).get("products") or [])
                   for case in (cases.get("cases") if isinstance(cases, dict) else cases))
        self.assertLessEqual(most, ESTIMATED_PRODUCTS)
        self.assertLess(most, NOTE_SUCCESS_CAP)
        self.assertLess(2 * most, NOTE_LOOP_CAP)


if __name__ == "__main__":
    unittest.main()
