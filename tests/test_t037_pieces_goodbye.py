"""T-037: an identity turn bound, the read-back revised by an amount alone, and the goodbye after
the read-back that records nothing (CTO)."""

from __future__ import annotations

import json
import unittest

from builder import goodbye
from builder.offer_check import NOTE_SKIP_NUMBERS, PRODUCT_NOTE_REASONS
from builder.prompts import IDENTITY_TASK_TEMPLATE, REVISE_ASK_LINE
from builder.workflow import IDENTITY_TURN_LIMIT, IDENTITY_TURNS_PER_QUESTION
from tests.test_selfcheck import SPECS, load
from tests.test_selfcheck_families import AB, BRIEF_A, render


class IdentityTests(unittest.TestCase):
    def test_parts_are_put_together_and_the_step_is_bounded(self):
        self.assertIn("never ask for the whole answer again", IDENTITY_TASK_TEMPLATE.text)
        for name in (BRIEF_A, AB):
            spec, workflow = render(name)
            node = workflow["nodes"]["identity"]
            self.assertEqual(IDENTITY_TURNS_PER_QUESTION * len(spec.identity_questions), node["max_node_turns"])
            self.assertEqual(IDENTITY_TURN_LIMIT, node["max_turn_transition"])
            code = workflow["nodes"][IDENTITY_TURN_LIMIT]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
            self.assertIn(json.dumps(goodbye.goodbye_states(spec)[1]), code)


class ReviseTests(unittest.TestCase):
    def test_the_revise_line_asks_no_amount_and_an_amount_alone_is_checked(self):
        self.assertNotIn("amount", REVISE_ASK_LINE.text)
        spec, workflow = render(BRIEF_A)
        kinds = json.dumps([t for t in workflow["nodes"]["revise_ask"]["transitions"] if t["target_node"] == "check_offer"])
        self.assertIn("offer_amount_kind", kinds)
        kinds = json.dumps([t for t in workflow["nodes"]["confirm_record"]["transitions"] if t["target_node"] == "check_offer"])
        self.assertIn("offer_amount_kind", kinds)


class UnconfirmedGoodbyeTests(unittest.TestCase):
    def run_close(self, spec):
        variables = {"offers_accepted_count": 1, "readback_text": "x", goodbye.GOODBYE_READBACK: "x",
                     "identity_verified": "true", "offers_accepted": json.dumps({"1": {"date": "d"}})}
        exec(goodbye.goodbye_code(spec), {"vars": variables})
        return variables

    def test_no_neutral_reason_means_no_note(self):
        spec = load(SPECS["brief-ab-extracted-v2.json"][0])
        self.assertEqual("", goodbye.unconfirmed_note_reason(spec))
        variables = self.run_close(spec)
        self.assertEqual("close", variables[goodbye.GOODBYE_ROUTE])
        self.assertEqual([1], json.loads(variables[NOTE_SKIP_NUMBERS]))

    def test_a_neutral_reason_is_used(self):
        data = json.loads(SPECS["brief-ab-extracted-v2.json"][0].read_text(encoding="utf-8"))
        data = data.get("spec", data)
        data["closing"]["product_notes"]["reasons"].append("not_confirmed")
        from builder.spec import parse_spec
        spec = parse_spec(data)
        self.assertEqual("not_confirmed", goodbye.unconfirmed_note_reason(spec))
        variables = self.run_close(spec)
        self.assertEqual({"1": "not_confirmed"}, json.loads(variables[PRODUCT_NOTE_REASONS]))


if __name__ == "__main__":
    unittest.main()
