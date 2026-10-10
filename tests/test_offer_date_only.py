"""F-051: a customer who names only a date is checked against the amount the agent proposed."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from builder.offer_check import AMOUNT_KIND_NONE, OFFER_AMOUNT_KIND, OFFER_PROPOSED_KIND
from builder.prompts import NEGOTIATION_TASK_TEMPLATE
from builder.spec import parse_spec
from builder.tools_from_openapi import tools_from_openapi
from builder.workflow import build_spec_workflow

ROOT = Path(__file__).resolve().parents[1]
TOOLS = tools_from_openapi(json.loads((ROOT / "build-the-builder-v2/tools/openapi.json").read_text(encoding="utf-8")))
FIXTURE_A = json.loads((ROOT / "tests/fixtures/spec-brief-a.json").read_text(encoding="utf-8"))
CARD = {"product_id": "p-card", "type": "credit_card", "card_last4": "0377", "past_due": 95.0,
        "days_late": 4, "minimum_payment": 28.5}
NOW = "2026-10-14T11:00"  # Wednesday


def code_of(node):
    return node["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]


class Call:
    """Runs offer_setup once, then check_offer for each customer turn, keeping the call variables."""

    def __init__(self, products=(CARD,)):
        spec = parse_spec(copy.deepcopy(FIXTURE_A))
        self.nodes = build_spec_workflow(spec, TOOLS)["nodes"]
        self.vars = {spec.account.data["products_variable"]: json.dumps(list(products)), "now": NOW}
        exec(code_of(self.nodes["offer_setup"]), {"vars": self.vars})

    def turn(self, **extracted):
        self.vars.update(extracted)
        exec(code_of(self.nodes["check_offer"]), {"vars": self.vars})
        return self.vars

    def accepted(self):
        return json.loads(self.vars["offers_accepted"])


def routes_to_check(negotiate, variables):
    condition = negotiate["transitions"][0]["condition"]["conditions"][0]["conditions"]
    for item in condition:
        value = variables.get(item["variable"])
        if item["operator"] == "is_set" and value is None:
            return False
        if item["operator"] == "not_equals" and value == item["operand"]:
            return False
    return True


class DateOnlyTests(unittest.TestCase):
    def test_a_date_alone_routes_to_the_check(self):
        negotiate = Call().nodes["negotiate"]
        self.assertEqual("check_offer", negotiate["transitions"][0]["target_node"])
        self.assertTrue(routes_to_check(negotiate, {"offer_date": "Friday"}))
        self.assertFalse(routes_to_check(negotiate, {"offer_date": ""}))
        self.assertFalse(routes_to_check(negotiate, {}))

    def test_date_only_takes_the_full_amount_by_default(self):
        call = Call()
        result = call.turn(offer_date="2026-10-16")
        self.assertEqual("ok", result["offer_verdict"], result["offer_message"])
        self.assertEqual(95.0, call.accepted()["1"]["amount"])

    def test_date_only_after_a_floor_offer_takes_the_floor(self):
        call = Call()
        # The customer offers too little; the check offers the floor and remembers it.
        first = call.turn(offer_date="2026-10-16", offer_amount=10)
        self.assertEqual("amount_too_low", first["offer_verdict"])
        self.assertEqual("minimum", first[OFFER_PROPOSED_KIND])
        # The customer then only names a date: the floor is used.
        second = call.turn(offer_date="2026-10-19")
        self.assertEqual("ok", second["offer_verdict"], second["offer_message"])
        self.assertEqual(28.5, call.accepted()["1"]["amount"])

    def test_date_only_after_the_agent_proposed_the_floor(self):
        # Extraction reads the agent's last proposal (minimum) from the conversation.
        call = Call()
        result = call.turn(offer_date="2026-10-16", **{OFFER_PROPOSED_KIND: "minimum"})
        self.assertEqual("ok", result["offer_verdict"])
        self.assertEqual(28.5, call.accepted()["1"]["amount"])

    def test_customer_amount_wins_over_the_proposal(self):
        call = Call()
        call.turn(offer_date="2026-10-16", offer_amount=50, **{OFFER_PROPOSED_KIND: "minimum"})
        self.assertEqual(50.0, call.accepted()["1"]["amount"])
        call = Call()
        call.turn(offer_date="2026-10-16", **{OFFER_AMOUNT_KIND: "full", OFFER_PROPOSED_KIND: "minimum"})
        self.assertEqual(95.0, call.accepted()["1"]["amount"])

    def test_other_amount_without_a_number_is_missing(self):
        result = Call().turn(offer_date="2026-10-16", **{OFFER_AMOUNT_KIND: "other"})
        self.assertEqual("missing", result["offer_verdict"])

    def test_a_late_date_alone_is_checked_not_invented(self):
        result = Call().turn(offer_date="2026-11-03")  # after the early-band deadline
        self.assertEqual("date_too_late", result["offer_verdict"])
        self.assertEqual("2026-11-02", result["offer_suggested_date"])


class EnumResetTests(unittest.TestCase):
    def test_amount_kind_is_reset_to_an_allowed_value(self):
        call = Call()
        schema = {item["name"]: item for item in call.nodes["negotiate"]["extraction_schema"]}
        allowed = schema[OFFER_AMOUNT_KIND]["enum_values"]
        self.assertIn(AMOUNT_KIND_NONE, allowed)
        self.assertIn(call.vars[OFFER_AMOUNT_KIND], allowed)  # after offer_setup
        call.turn(offer_date="2026-10-16", **{OFFER_AMOUNT_KIND: "full"})
        self.assertIn(call.vars[OFFER_AMOUNT_KIND], allowed)  # after check_offer
        self.assertIn(call.vars[OFFER_PROPOSED_KIND], schema[OFFER_PROPOSED_KIND]["enum_values"])

    def test_no_offer_code_writes_an_empty_amount_kind(self):
        nodes = Call().nodes
        for key in ("offer_setup", "check_offer"):
            self.assertNotIn("vars[CONFIG['amount_kind_var']] = ''", code_of(nodes[key]), key)


class NegotiationPromptTests(unittest.TestCase):
    def test_prompt_forbids_own_limits_and_internal_names(self):
        text = NEGOTIATION_TASK_TEMPLATE.text
        self.assertIn("Never state a limit yourself", text)
        self.assertIn("Never mention internal step, tool or variable names", text)
        self.assertIn("Verdict none: propose or ask, but never say whether a date or an amount is allowed", text)
        self.assertIn("If the customer names only a date, the amount you last proposed applies", text)


if __name__ == "__main__":
    unittest.main()
