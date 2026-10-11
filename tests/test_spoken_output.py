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
    """F-043 wait line, moved by F-050: the identity step says it after the last answer passed;
    no passthrough api step speaks (a tts entry there broke the turn on the platform)."""

    def test_identity_step_says_the_default_wait_line(self):
        nodes = nodes_for(FIXTURE_A)
        self.assertIn("then say: " + ACCOUNT_WAIT_LINE.text, nodes["identity"]["task_message"])
        self.assertEqual({"type": "silent"}, nodes["account"]["on_enter"])
        self.assertNotIn("{{", ACCOUNT_WAIT_LINE.text)
        self.assertLessEqual(len(ACCOUNT_WAIT_LINE.text.split()), 12)

    def test_spec_wait_line_in_the_call_language_wins(self):
        data = copy.deepcopy(FIXTURE_A)
        data["agent"]["wait_line"] = "  Einen Moment bitte.  "
        self.assertIn("then say: Einen Moment bitte.", nodes_for(data)["identity"]["task_message"])
        data["agent"]["wait_line"] = 5
        with self.assertRaises(SpecError):
            parse_spec(data)

    def test_no_passthrough_api_step_speaks(self):
        for path in sorted((ROOT / "tests/fixtures").glob("spec-*.json")) + sorted(
                (ROOT / "tests/fixtures/extract").glob("*extracted*.json")):
            tools = TOOLS
            if path.name == "spec-synthetic.json":
                tools = tools_from_openapi(json.loads(
                    (ROOT / "tests/fixtures/openapi-synthetic.json").read_text(encoding="utf-8")))
            workflow = build_spec_workflow(parse_spec(json.loads(path.read_text(encoding="utf-8"))), tools)
            for key, node in {**workflow["nodes"], **workflow["global_nodes"]}.items():
                if node.get("node_type") == "api_request":
                    self.assertTrue(node.get("passthrough"), (path.name, key))
                    self.assertEqual({"type": "silent"}, node.get("on_enter"), (path.name, key))


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
        self.assertIn("Product 1, credit card ending 0377 (", facts)
        self.assertIn("Product 2, personal loan (", facts)
        self.assertEqual(2, facts.count("Product "))
        self.assertNotIn("p-card", facts)

    def test_confirm_prompt_keeps_the_number_for_the_tool_only(self):
        self.assertIn("Never say the product number in square brackets", CONFIRM_TASK_TEMPLATE.text)
        self.assertIn("{{offers_summary}}", nodes_for(FIXTURE_A)["confirm_record"]["task_message"])

    def test_naming_fields_are_optional_strings(self):
        data = copy.deepcopy(FIXTURE_A)
        data["account"]["product_label_field"] = ["card_last4"]
        with self.assertRaises(SpecError):
            parse_spec(data)


if __name__ == "__main__":
    unittest.main()
