"""T-032: review fixes (tasks/T-029-030-review.md MEDIUM 3, LOW 2). The identity hook (MEDIUM 4)
is tested in tests/test_global_exit_identity.py, the recording notice (LOW 1) in
tests/test_recording_notice.py."""

from __future__ import annotations

import unittest

from builder.goodbye import CUSTOMER_ENDS_CALL, goodbye_exit_gaps
from builder.prompts import CUSTOMER_ENDS_CALL_INTENT, GOODBYE_CHOICE_DESCRIPTION, READBACK_RESUME_LINE
from builder.readback_resume import CONFIRM_RESUME
from builder.selfcheck import holds
from builder.workflow import SPECIAL_TOPIC_VALUE
from tests.test_selfcheck import SPECS
from tests.test_selfcheck_families import AB, render

PREVIOUS = "__previous__"


def first_route(node, variables):
    return next(t["target_node"] for t in node["transitions"] if holds(t["condition"], variables))


class GoodbyeWordingTests(unittest.TestCase):
    def test_thanks_or_a_no_is_not_a_goodbye(self):
        # Review MEDIUM 3: "Okay, thank you" mid-call and "No thanks, goodbye" to a question.
        intent = CUSTOMER_ENDS_CALL_INTENT.text
        self.assertNotIn("goodbye or thanks", intent)
        self.assertIn('"Thanks", "okay" or "yes" alone is not a goodbye', intent)
        choice = GOODBYE_CHOICE_DESCRIPTION.text
        self.assertIn('"thanks", "okay" or "yes" alone is not {value}', choice)
        self.assertIn('a "no" (also "no thanks, goodbye") answers the question', choice)

    def test_the_rendered_steps_carry_the_new_wording(self):
        spec, workflow = render(AB)
        self.assertEqual(CUSTOMER_ENDS_CALL_INTENT.text,
                         workflow["global_nodes"][CUSTOMER_ENDS_CALL]["condition"]["description"])
        asks = [node for node in workflow["global_nodes"].values()
                if node.get("node_type") == "conversation" and not node.get("passthrough")]
        for node in asks:
            self.assertIn('answers the question', node["extraction_schema"][0]["description"])


class ReadbackResumeTests(unittest.TestCase):
    def test_a_side_question_at_the_read_back_returns_without_the_read_back(self):
        spec, workflow = render(AB)
        nodes, globals_ = workflow["nodes"], workflow["global_nodes"]
        choice = spec.confirmation.data["intent_variable"]
        resume, confirm = nodes[CONFIRM_RESUME], nodes["confirm_record"]
        self.assertEqual({"type": "tts", "text": READBACK_RESUME_LINE.text}, resume["on_enter"])
        self.assertNotIn("readback_text", resume["on_enter"]["text"])
        self.assertEqual(confirm["transitions"], resume["transitions"])
        self.assertEqual(confirm["extraction_schema"], resume["extraction_schema"])
        returning = [key for key, node in globals_.items()
                     if any(t["target_node"] == CONFIRM_RESUME for t in node.get("transitions") or [])]
        self.assertTrue(returning)
        for key in returning:
            node = globals_[key]
            with self.subTest(step=key):
                self.assertNotIn("confirm_record", node["excluded_nodes"])
                self.assertNotIn(CONFIRM_RESUME, node["excluded_nodes"])
                # Find the variables of the plain return (__previous__), then add the read-back value.
                stay = next(t for t in node["transitions"] if t["target_node"] == PREVIOUS)
                variables = {"now": "2026-10-14T11:00"}
                for item in stay["condition"].get("conditions", []):
                    if item.get("operator") == "equals":
                        variables[item["variable"]] = item["operand"]
                self.assertEqual(PREVIOUS, first_route(node, {**variables, choice: "confirms"}))
                self.assertEqual(PREVIOUS, first_route(node, variables))
                self.assertEqual(CONFIRM_RESUME, first_route(node, {**variables, choice: SPECIAL_TOPIC_VALUE}))

    def test_fresh_entries_still_say_the_read_back(self):
        spec, workflow = render(AB)
        every = {**workflow["nodes"], **workflow["global_nodes"]}
        into_resume = {key for key, node in every.items()
                       for t in node.get("transitions") or [] if t["target_node"] == CONFIRM_RESUME}
        # Only global side steps (and a special path started at the copy, returning to it) go there.
        for key in into_resume:
            self.assertTrue(key in workflow["global_nodes"] or key.endswith("_done"), key)
        self.assertEqual("{{readback_text}}", workflow["nodes"]["confirm_record"]["on_enter"]["text"])

    def test_a_goodbye_leaves_the_copy_and_unused_copies_are_dropped(self):
        for name in SPECS:
            spec, workflow = render(name)
            with self.subTest(spec=name):
                self.assertEqual([], goodbye_exit_gaps(workflow))
                if CONFIRM_RESUME in workflow["nodes"]:
                    self.assertTrue(any(t["target_node"] == CONFIRM_RESUME
                                        for node in workflow["global_nodes"].values()
                                        for t in node.get("transitions") or []))
                else:
                    self.assertFalse([key for key in workflow["global_nodes"] if key.endswith(CONFIRM_RESUME)])


if __name__ == "__main__":
    unittest.main()
