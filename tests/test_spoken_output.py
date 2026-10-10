"""F-043 (wait line on the account lookup) and F-044 (human read-back), offline."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from builder.prompts import ACCOUNT_WAIT_LINE, CONFIRM_TASK_TEMPLATE
from builder.spec import SpecError, parse_spec
from builder.tools_from_openapi import tools_from_openapi
from builder.workflow import build_spec_workflow

ROOT = Path(__file__).resolve().parents[1]
TOOLS = tools_from_openapi(json.loads((ROOT / "build-the-builder-v2/tools/openapi.json").read_text(encoding="utf-8")))
FIXTURE_A = json.loads((ROOT / "tests/fixtures/spec-brief-a.json").read_text(encoding="utf-8"))
CARD = {"product_id": "p-card", "type": "credit_card", "card_last4": "0377", "past_due": 95.5,
        "days_late": 4, "minimum_payment": 28.5}
LOAN = {"product_id": "p-loan", "type": "personal_loan", "past_due": 300.0, "days_late": 20,
        "instalment_amount": 150.0}


def code_of(node):
    return node["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]


def nodes_for(data):
    return build_spec_workflow(parse_spec(copy.deepcopy(data)), TOOLS)["nodes"]


def read_back(data, products, offers, now="2026-10-14T11:00"):
    """Run offer_setup, then check_offer for each (number, date, amount); return the summary."""
    nodes = nodes_for(data)
    spec = parse_spec(copy.deepcopy(data))
    variables = {spec.account.data["products_variable"]: json.dumps(products), "now": now}
    exec(code_of(nodes["offer_setup"]), {"vars": variables})
    for number, date, amount in offers:
        variables.update({"offer_date": date, "offer_amount": amount, "offer_product_number": number})
        exec(code_of(nodes["check_offer"]), {"vars": variables})
        assert variables["offer_verdict"] == "ok", variables["offer_message"]
    return variables


class WaitLineTests(unittest.TestCase):
    def test_account_lookup_speaks_a_fixed_line(self):
        account = nodes_for(FIXTURE_A)["account"]
        self.assertEqual({"type": "tts", "text": ACCOUNT_WAIT_LINE.text}, account["on_enter"])
        self.assertTrue(account["passthrough"])
        self.assertNotIn("{{", ACCOUNT_WAIT_LINE.text)
        self.assertLessEqual(len(ACCOUNT_WAIT_LINE.text.split()), 12)

    def test_spec_wait_line_in_the_call_language_wins(self):
        data = copy.deepcopy(FIXTURE_A)
        data["agent"]["wait_line"] = "  Einen Moment bitte.  "
        self.assertEqual("Einen Moment bitte.", nodes_for(data)["account"]["on_enter"]["text"])
        data["agent"]["wait_line"] = 5
        with self.assertRaises(SpecError):
            parse_spec(data)

    def test_only_the_account_step_gets_the_line(self):
        nodes = nodes_for(FIXTURE_A)
        spoken = [key for key, node in nodes.items()
                  if node.get("node_type") in ("api_request", "code") and node.get("on_enter", {}).get("type") == "tts"]
        self.assertIn("account", spoken)
        self.assertNotIn("offer_setup", spoken)
        self.assertNotIn("check_offer", spoken)


class ReadBackTests(unittest.TestCase):
    def test_read_back_uses_names_spoken_dates_and_plain_amounts(self):
        variables = read_back(FIXTURE_A, [CARD], [(1, "2026-10-16", 95.5)])
        self.assertEqual("credit card ending 0377: 95.50 on Friday, 16 October [product number 1]",
                         variables["offers_summary"])
        self.assertNotIn("Product 1", variables["offers_summary"])
        self.assertNotIn("2026-10-16", variables["offers_summary"])

    def test_whole_amounts_have_no_decimals_and_other_years_are_said(self):
        data = copy.deepcopy(FIXTURE_A)
        data["offer"]["latest"] = []  # no deadline, so a date next year is allowed
        variables = read_back(data, [LOAN], [(1, "2027-01-04", 150)], now="2026-12-28T10:00")
        self.assertEqual("personal loan: 150 on Monday, 4 January 2027 [product number 1]", variables["offers_summary"])

    def test_without_naming_fields_products_are_ordinal(self):
        data = copy.deepcopy(FIXTURE_A)
        del data["account"]["product_kind_field"], data["account"]["product_label_field"]
        variables = read_back(data, [CARD, LOAN], [(1, "2026-10-16", 95.5), (2, "2026-10-20", 150)])
        self.assertEqual(
            "the first product: 95.50 on Friday, 16 October [product number 1]; "
            "the second product: 150 on Tuesday, 20 October [product number 2]",
            variables["offers_summary"],
        )

    def test_facts_tell_the_agent_how_to_name_each_product(self):
        variables = read_back(FIXTURE_A, [CARD, LOAN], [])
        facts = variables["products_facts"]
        self.assertIn("Name it to the customer as: credit card ending 0377.", facts)
        self.assertIn("Name it to the customer as: personal loan.", facts)
        self.assertEqual(2, facts.count("Product "))
        self.assertNotIn("p-card", facts)

    def test_confirm_prompt_keeps_the_number_for_the_tool_only(self):
        self.assertIn("never say it to the customer", CONFIRM_TASK_TEMPLATE.text)
        self.assertIn("{{offers_summary}}", nodes_for(FIXTURE_A)["confirm_record"]["task_message"])

    def test_naming_fields_are_optional_strings(self):
        data = copy.deepcopy(FIXTURE_A)
        data["account"]["product_label_field"] = ["card_last4"]
        with self.assertRaises(SpecError):
            parse_spec(data)


if __name__ == "__main__":
    unittest.main()
