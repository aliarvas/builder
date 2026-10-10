"""F-051: a customer who names only a date is checked against the amount the agent proposed."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from builder.offer_check import AMOUNT_KIND_NONE, OFFER_ACCEPTS, OFFER_AMOUNT_KIND, OFFER_PROPOSED_KIND
from builder.prompts import NEGOTIATION_TASK_TEMPLATE
from builder.spec import SpecError, parse_spec
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
        self.assertEqual("amount_missing", result["offer_verdict"])
        self.assertIn("Propose the amount again yourself", result["offer_message"])

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


LOAN = {"product_id": "p-loan", "type": "personal_loan", "past_due": 300.0, "days_late": 20,
        "instalment_amount": 150.0}


class FollowUpTests(unittest.TestCase):
    """F-052: proposal per product, date-less acceptance, date-only missing message, enum resets."""

    def test_next_product_starts_from_the_full_amount(self):
        call = Call(products=(CARD, LOAN))
        call.turn(offer_date="2026-10-16", offer_amount=10, offer_product_number=1)   # below the floor
        call.turn(offer_date="2026-10-16", offer_product_number=1)                    # floor accepted
        self.assertEqual(28.5, call.accepted()["1"]["amount"])
        self.assertEqual("full", call.vars[OFFER_PROPOSED_KIND])
        call.turn(offer_date="2026-10-20", offer_product_number=2)                    # only a date
        self.assertEqual(300.0, call.accepted()["2"]["amount"])

    def test_yes_to_the_proposed_date_is_checked_with_that_date(self):
        call = Call()
        first = call.turn(offer_date="2026-11-03")          # after the deadline: the check proposes 2026-11-02
        self.assertEqual("2026-11-02", first["offer_suggested_date"])
        negotiate = call.nodes["negotiate"]
        self.assertTrue(any(c.get("variable") == OFFER_ACCEPTS and c.get("operand") == "yes"
                            for c in negotiate["transitions"][0]["condition"]["conditions"]))
        second = call.turn(**{OFFER_ACCEPTS: "yes"})
        self.assertEqual("ok", second["offer_verdict"], second["offer_message"])
        self.assertEqual("2026-11-02", call.accepted()["1"]["date"])
        self.assertEqual("none", call.vars[OFFER_ACCEPTS])

    def test_yes_without_a_proposed_date_asks_for_the_date(self):
        result = Call().turn(**{OFFER_ACCEPTS: "yes"})
        self.assertEqual("missing", result["offer_verdict"])
        self.assertEqual("The date was not clear. Ask the customer for the exact date.", result["offer_message"])
        self.assertNotIn("amount", result["offer_message"])

    def test_ok_message_names_the_product(self):
        result = Call().turn(offer_date="2026-10-16")
        self.assertIn("credit card ending 0377", result["offer_message"])
        self.assertNotIn("product 1", result["offer_message"])

    def test_old_intent_cannot_skip_the_second_product(self):
        spec = parse_spec(copy.deepcopy(FIXTURE_A))
        intent = spec.negotiation.data["intent_variable"]
        proposal = spec.negotiation.data["confirm_values"][0]
        call = Call(products=(CARD, LOAN))
        result = call.turn(offer_date="2026-10-16", offer_product_number=1, **{intent: proposal})
        self.assertEqual("more", result["offer_progress"])
        schema = {item["name"]: item for item in call.nodes["negotiate"]["extraction_schema"]}
        self.assertEqual("none", call.vars[intent])
        self.assertIn("none", schema[intent]["enum_values"])
        to_confirm = [t for t in call.nodes["negotiate"]["transitions"] if t["target_node"] == "confirm_record"]
        for transition in to_confirm:
            for group in transition["condition"]["conditions"]:
                self.assertFalse(all(call.vars.get(c["variable"]) == c["operand"] if c["operator"] == "equals"
                                     else float(call.vars.get(c["variable"]) or 0) > c["operand"]
                                     for c in group["conditions"]))

    def test_every_enum_reset_writes_an_allowed_value(self):
        spec = parse_spec(copy.deepcopy(FIXTURE_A))
        call = Call()
        call.turn(offer_date="2026-10-16")
        schemas = {item["name"]: item for node in call.nodes.values() for item in node.get("extraction_schema", [])}
        for name in (spec.negotiation.data["intent_variable"], spec.confirmation.data["intent_variable"],
                     OFFER_AMOUNT_KIND, OFFER_ACCEPTS, OFFER_PROPOSED_KIND):
            self.assertIn(call.vars[name], schemas[name]["enum_values"], name)

    def test_none_is_reserved_in_spec_value_lists(self):
        for stage, key in (("opening", "who_answered_options"), ("third_party", "intent_values"),
                           ("negotiation", "intent_values"), ("confirmation", "intent_values")):
            data = copy.deepcopy(FIXTURE_A)
            data[stage][key] = [*data[stage][key], "none"]
            with self.assertRaises(SpecError, msg=f"{stage}.{key}"):
                parse_spec(data)
