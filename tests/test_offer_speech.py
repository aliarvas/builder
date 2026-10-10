"""F-053 (the check result is spoken by a fixed line) and F-054 (a computed spoken calendar)."""

from __future__ import annotations

import unittest

from builder.prompts import NEGOTIATION_TASK_TEMPLATE, OFFER_VERDICT_MESSAGES, REVISE_ASK_LINE
from builder.spoken import agent_directed
from builder.offer_check import OFFER_PROPOSED_KIND
from tests.test_offer_date_only import CARD, LOAN, Call


class CheckResultSpeechTests(unittest.TestCase):
    def test_check_result_goes_through_a_spoken_step(self):
        nodes = Call().nodes
        say = nodes["offer_say"]
        # A waiting copy of negotiate that speaks the result on entry, then waits for the customer.
        self.assertEqual("conversation", say["node_type"])
        self.assertFalse(say.get("passthrough"))
        self.assertEqual({"type": "tts", "text": "{{offer_message}}"}, say["on_enter"])
        for key in ("transitions", "extraction_schema", "task_message"):
            self.assertEqual(nodes["negotiate"][key], say[key], key)
        self.assertEqual("offer_say", nodes["check_offer"]["transitions"][-1]["target_node"])
        self.assertEqual({"type": "tts", "text": REVISE_ASK_LINE.text}, nodes["revise_ask"]["on_enter"])
        self.assertFalse(nodes["negotiate"].get("on_enter_first_entry_only"))

    def test_every_message_is_said_to_the_customer(self):
        for line in OFFER_VERDICT_MESSAGES.text.splitlines():
            key, _, sentence = line.partition(": ")
            sample = (sentence.replace("the [product]", "the credit card").replace("the [next]", "the loan")
                      .replace("[date]", "Friday, 16 October").replace("[amount]", "95").replace("[next_amount]", "300"))
            self.assertEqual("", agent_directed(sample), key)
            self.assertNotIn("[", sample, key)
        self.assertEqual("", agent_directed(REVISE_ASK_LINE.text))

    def test_holiday_date_is_answered_with_the_next_business_day(self):
        # PUB-07: Wednesday 14 October; the customer names Monday 26 October (a holiday).
        result = Call().turn(offer_date="2026-10-26")
        self.assertEqual("date_not_business_day", result["offer_verdict"])
        self.assertEqual("That day is not a business day. The next possible day is Tuesday, 27 October. "
                         "Would that work for you?", result["offer_message"])

    def test_spoken_values_and_product_names(self):
        late = Call().turn(offer_date="2026-11-03")
        self.assertEqual("The latest date I can record for the credit card ending 0377 is Monday, 2 November. "
                         "Would Monday, 2 November work for you?", late["offer_message"])
        low = Call().turn(offer_date="2026-10-16", offer_amount=10)
        self.assertEqual("The lowest amount I can record for the credit card ending 0377 is 28.50. "
                         "Could you pay 28.50?", low["offer_message"])

    def test_next_product_is_named(self):
        result = Call(products=(CARD, LOAN)).turn(offer_date="2026-10-16", offer_product_number=1)
        self.assertEqual("more", result["offer_progress"])
        self.assertEqual("Thank you, that works for the credit card ending 0377. Now let us look at the personal loan. "
                         "The amount due is 300. Could you pay 300?", result["offer_message"])
        self.assertTrue(result["offer_message"].endswith("?"))


class CalendarTests(unittest.TestCase):
    def test_calendar_lists_this_and_next_week(self):
        calendar = Call().vars["calendar_text"]  # now: Wednesday 14 October 2026
        self.assertEqual(
            "Today is Wednesday, 14 October. "
            "Business days this week: Wednesday 14, Thursday 15 and Friday 16 October. "
            "Business days next week: Monday 19, Tuesday 20, Wednesday 21, Thursday 22 and Friday 23 October. "
            "Last business day: this week Friday, 16 October; next week Friday, 23 October.",
            calendar,
        )
        self.assertNotIn("Saturday", calendar)

    def test_calendar_skips_holidays(self):
        call = Call.__new__(Call)
        Call.__init__(call)
        call.vars["now"] = "2026-10-22T10:00"  # Thursday; Monday 26 October is a holiday
        exec(__import__("tests.test_offer_date_only", fromlist=["code_of"]).code_of(call.nodes["offer_setup"]),
             {"vars": call.vars})
        calendar = call.vars["calendar_text"]
        self.assertIn("Business days next week: Tuesday 27, Wednesday 28", calendar)
        self.assertNotIn("26 October", calendar)

    def test_facts_use_spoken_dates_and_amounts(self):
        facts = Call(products=(CARD, LOAN)).vars["products_facts"]
        self.assertIn("deadline Monday, 2 November; minimum amount 28.50; full amount 95.", facts)
        self.assertNotIn("2026-", facts)

    def test_prompt_uses_only_the_computed_calendar(self):
        text = NEGOTIATION_TASK_TEMPLATE.text
        self.assertIn("{{calendar_text}}", text)
        self.assertNotIn("{{today_text}}", text)
        self.assertIn("never work out a date or an amount yourself", text)
        self.assertIn("do not repeat it", text)


if __name__ == "__main__":
    unittest.main()


class NoDeadAirTests(unittest.TestCase):
    """F-053 fix (review finding 1): every step a side question can return to speaks on entry."""

    def test_every_return_target_speaks(self):
        import json
        from pathlib import Path

        from builder.spec import parse_spec
        from builder.tools_from_openapi import tools_from_openapi
        from builder.workflow import build_spec_workflow

        root = Path(__file__).resolve().parents[1]
        kit = tools_from_openapi(json.loads((root / "build-the-builder-v2/tools/openapi.json").read_text()))
        synthetic = tools_from_openapi(json.loads((root / "tests/fixtures/openapi-synthetic.json").read_text()))
        paths = sorted((root / "tests/fixtures").glob("spec-*.json")) + sorted(
            (root / "tests/fixtures/extract").glob("*extracted*.json"))
        for path in paths:
            tools = synthetic if path.name == "spec-synthetic.json" else kit
            workflow = build_spec_workflow(parse_spec(json.loads(path.read_text())), tools)
            nodes = workflow["nodes"]

            def speaks(key):
                node = nodes[key]
                entry = node.get("on_enter", {"type": "llm"})
                return entry.get("type") != "silent" and not node.get("on_enter_first_entry_only")

            for key, node in workflow["global_nodes"].items():
                for source in sorted(set(nodes) - set(node["excluded_nodes"])):
                    if nodes[source].get("node_type") == "conversation":
                        self.assertTrue(speaks(source), (path.name, key, source))
            for key, node in nodes.items():
                if key.endswith("_done"):
                    for transition in node["transitions"]:
                        self.assertTrue(speaks(transition["target_node"]), (path.name, key, transition["target_node"]))


def setup_vars(products, now, data=None):
    """Runs offer_setup alone for ``products`` at ``now``; ``data`` overrides the fixture spec."""
    import copy
    import json

    from builder.spec import parse_spec
    from builder.workflow import build_spec_workflow
    from tests.test_offer_date_only import FIXTURE_A, TOOLS, code_of

    spec = parse_spec(copy.deepcopy(data or FIXTURE_A))
    nodes = build_spec_workflow(spec, TOOLS)["nodes"]
    variables = {spec.account.data["products_variable"]: json.dumps(list(products)), "now": now}
    exec(code_of(nodes["offer_setup"]), {"vars": variables})
    return variables, nodes


class ShortRuntimeTextTests(unittest.TestCase):
    """T-009c: shorter calendar and product facts, with no policy fact and no check lost."""

    def test_facts_have_no_raw_field_prefix_but_keep_unsaid_fields(self):
        facts = Call(products=(CARD, LOAN)).vars["products_facts"]
        for raw in ("type credit_card", "card_last4", "past_due", "minimum_payment", "instalment_amount", "p-card"):
            self.assertNotIn(raw, facts)
        # The name and the limits say type, label and amounts; days late is said nowhere else.
        self.assertIn("Product 1, credit card ending 0377 (days late 4): deadline Monday, 2 November; "
                      "minimum amount 28.50; full amount 95.", facts)
        self.assertIn("Product 2, personal loan (days late 20): deadline Friday, 23 October;", facts)

    def test_calendar_stops_at_the_latest_deadline(self):
        # Monday 12 October; the loan's deadline is Wednesday 21 October, the only product.
        variables, nodes = setup_vars((LOAN,), "2026-10-12T10:00")
        calendar = variables["calendar_text"]
        self.assertIn("Business days next week: Monday 19, Tuesday 20 and Wednesday 21 October.", calendar)
        self.assertNotIn("22", calendar)
        self.assertNotIn("23 October", calendar)
        self.assertIn("Last business day: this week Friday, 16 October.", calendar)  # policy line kept
        self.assertIn("No day after Wednesday, 21 October can be recorded.", calendar)
        # The checks do not change: a later day is still refused with the deadline.
        variables.update(offer_date="2026-10-23", offer_product_number=1)
        exec(__import__("tests.test_offer_date_only", fromlist=["code_of"]).code_of(nodes["check_offer"]),
             {"vars": variables})
        self.assertEqual("date_too_late", variables["offer_verdict"])
        self.assertIn("Wednesday, 21 October", variables["offer_message"])

    def test_calendar_is_not_cut_by_the_longest_deadline(self):
        # Two products: the card's later deadline keeps the loan's earlier one from cutting.
        calendar = Call(products=(CARD, LOAN)).vars["calendar_text"]
        self.assertIn("Thursday 22 and Friday 23 October.", calendar)
        self.assertNotIn("No day after", calendar)

    def test_calendar_starts_at_the_earliest_date(self):
        import copy

        from tests.test_offer_date_only import FIXTURE_A

        data = copy.deepcopy(FIXTURE_A)
        data["offer"]["earliest"] = {"days": 2, "unit": "calendar"}
        calendar = setup_vars((CARD,), "2026-10-14T10:00", data)[0]["calendar_text"]
        self.assertIn("Earliest date: Friday, 16 October.", calendar)
        self.assertIn("Business days this week: Friday 16 October.", calendar)


class RuntimeTextShareTests(unittest.TestCase):
    """T-009c: the budget shares in RUNTIME_TEXT_CHARACTERS cover the longest texts the code writes."""

    PRODUCTS = (
        CARD, LOAN,
        {"product_id": "p-car", "type": "car_loan", "past_due": 12345.67, "days_late": 44, "instalment_amount": 1234.56},
    )

    def test_calendar_and_facts_fit_their_shares(self):
        import datetime

        from builder.offer_check import RUNTIME_TEXT_CHARACTERS

        calendar_share = RUNTIME_TEXT_CHARACTERS["{{calendar_text}}"][0]
        facts_share = RUNTIME_TEXT_CHARACTERS["{{products_facts}}"][1]
        variables, nodes = setup_vars(self.PRODUCTS, "2026-01-01T10:00")
        key = next(name for name in variables if name != "now" and name.endswith("products"))
        setup = __import__("tests.test_offer_date_only", fromlist=["code_of"]).code_of(nodes["offer_setup"])
        start = datetime.date(2026, 1, 1)
        for offset in range(0, 731, 1):
            day = (start + datetime.timedelta(days=offset)).isoformat()
            for products in (self.PRODUCTS, (LOAN,)):
                values = {key: variables[key] if products is self.PRODUCTS else '[' + __import__("json").dumps(LOAN) + ']',
                          "now": day + "T10:00"}
                exec(setup, {"vars": values})
                self.assertLessEqual(len(values["calendar_text"]), calendar_share, day)
                lines = values["products_facts"].split(" Product ")
                self.assertEqual(len(products), len(lines))
                for line in lines:
                    self.assertLessEqual(len(line) + 1, facts_share, line)

    def test_messages_and_summary_fit_their_shares(self):
        from builder.offer_check import RUNTIME_TEXT_CHARACTERS

        for date, amount in (("2026-11-30", ""), ("2026-10-16", 1), ("2026-10-16", 99999), ("2026-10-26", ""),
                             ("2026-10-16", "")):
            result = Call(products=self.PRODUCTS).turn(offer_date=date, offer_amount=amount, offer_product_number=1)
            self.assertLessEqual(len(result["offer_message"]), RUNTIME_TEXT_CHARACTERS["{{offer_message}}"][0],
                                 result["offer_message"])
        call = Call(products=self.PRODUCTS)
        call.turn(offer_date="2026-10-30", offer_amount="", offer_product_number=1)
        summary = call.turn(offer_date="2026-10-21", offer_amount="", offer_product_number=2)["offers_summary"]
        entries = summary.split("; ")
        self.assertEqual(2, len(entries), summary)
        for entry in entries:
            self.assertLessEqual(len(entry) + 2, RUNTIME_TEXT_CHARACTERS["{{offers_summary}}"][1], entry)

    def test_estimate_grows_per_product(self):
        import copy

        from builder.offer_check import RUNTIME_TEXT_CHARACTERS
        from builder.spec import parse_spec
        from builder.workflow import build_spec_workflow, workflow_prompt_estimates
        from tests.test_offer_date_only import FIXTURE_A, TOOLS

        workflow = build_spec_workflow(parse_spec(copy.deepcopy(FIXTURE_A)), TOOLS)
        one, three = workflow_prompt_estimates(workflow, 1)["negotiate"], workflow_prompt_estimates(workflow, 3)["negotiate"]
        per_product = RUNTIME_TEXT_CHARACTERS["{{products_facts}}"][1] + RUNTIME_TEXT_CHARACTERS["{{offers_summary}}"][1]
        self.assertAlmostEqual(2 * per_product / 4, three - one, delta=1)
        self.assertEqual(workflow_prompt_estimates(workflow), workflow_prompt_estimates(workflow, 3))


class ExhaustedProductMessageTests(unittest.TestCase):
    def test_limit_moves_on_without_offering_the_closed_product_again(self):
        # T-009c: the invalid-offer limit (2) closes the card; the line does not offer it again.
        call = Call(products=(CARD, LOAN))
        call.turn(offer_date="2026-11-30", offer_product_number=1)
        result = call.turn(offer_date="2026-10-16", offer_amount=1, offer_product_number=1)
        self.assertEqual("more", result["offer_progress"])
        self.assertEqual("Now let us look at the personal loan. The amount due is 300. Could you pay 300?",
                         result["offer_message"])
        self.assertEqual("", result["offer_suggested_date"])
        self.assertEqual("", result["offer_suggested_amount"])


class T009cFixTests(unittest.TestCase):
    def test_date_only_after_a_limit_closed_product_records_the_full_amount(self):
        # Review finding 1: the card closes on the limit, the agent asks for 300, a date alone records 300.
        call = Call(products=(CARD, LOAN))
        call.turn(offer_date="2026-11-30", offer_product_number=1)
        result = call.turn(offer_date="2026-10-16", offer_amount=1, offer_product_number=1)
        self.assertEqual("more", result["offer_progress"])
        self.assertEqual("full", result[OFFER_PROPOSED_KIND])
        result = call.turn(offer_date="2026-10-20", offer_amount="", offer_product_number=2)
        self.assertEqual("ok", result["offer_verdict"])
        self.assertEqual(300.0, call.accepted()["2"]["amount"])
        self.assertIn("personal loan: 300 on Tuesday, 20 October", result["offers_summary"])

    def test_boolean_fields_are_said_in_words(self):
        # Review finding 2: a flag is not dropped silently.
        facts = Call(products=(dict(LOAN, secured=True, disputed=False),)).vars["products_facts"]
        self.assertIn("(days late 20, secured yes, disputed no)", facts)
