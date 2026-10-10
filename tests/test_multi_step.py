from __future__ import annotations

import ast
import re
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from builder import build
from builder.spec import (
    CLOSE_STATE_NAMES, HANGUP_CLOSE_STATES, OFFER_ADJUST, OFFER_UNITS, OPTIONAL_CLOSE_STATES, SpecError, load_spec, parse_spec, required_close_states,
)
from builder.tools_from_openapi import CALL_VARIABLES, tools_from_openapi
from builder.workflow import build_spec_workflow, close_table, source_steps, workflow_prompt_estimates


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = (
    ROOT / "tests/fixtures/spec-brief-a.json",
    ROOT / "tests/fixtures/spec-brief-b.json",
    ROOT / "tests/fixtures/spec-synthetic.json",
)


def kit_tools(spec=None):
    document = json.loads((ROOT / "build-the-builder-v2/tools/openapi.json").read_text(encoding="utf-8"))
    if spec is not None:
        # The synthetic bank uses its own outcome codes; give its OpenAPI a matching enum.
        schema = document["paths"]["/close_call"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        enum = schema["properties"]["outcome"]["enum"]
        enum.extend(item.outcome for item in spec.outcomes if item.outcome not in enum)
    return tools_from_openapi(document)


def code_of(node):
    return node["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]


def edges(node):
    targets = [item["target_node"] for item in node.get("transitions", [])]
    if node.get("max_turn_transition"):
        targets.append(node["max_turn_transition"])
    return targets


def graph(workflow):
    """Successors of every step, including the global nodes a step can trigger."""
    nodes, globals_ = workflow["nodes"], workflow["global_nodes"]
    every = {**nodes, **globals_}
    result = {}
    for key, node in every.items():
        targets = [target for target in edges(node) if target != "__previous__"]
        targets += [name for name, item in globals_.items() if key not in item["excluded_nodes"]]
        result[key] = targets
    return result


def tool_names(node):
    return [tool["function"]["name"] for tool in node.get("tools", [])]


def engine_holds(condition, variables):
    """Test-side reading of a transition condition (written independently of the builder)."""
    operator = condition.get("operator")
    if operator == "always":
        return True
    if "conditions" in condition:
        results = [engine_holds(item, variables) for item in condition["conditions"]]
        return all(results) if condition.get("logic") == "and" else any(results)
    value = variables.get(condition.get("variable"))
    present = value not in (None, "")
    if operator == "is_set":
        return present
    if operator == "equals":
        return present and str(value) == str(condition["operand"])
    if operator == "not_equals":
        return not (present and str(value) == str(condition["operand"]))
    if operator in ("greater_than", "less_than") and present:
        return float(value) > condition["operand"] if operator == "greater_than" else float(value) < condition["operand"]
    return False


def walk(workflow, key, variables, limit=20):
    """Follow deterministic routing from ``key``: run code steps, take the first matching
    transition, stop at ``closing`` or where a step waits (no match)."""
    every = {**workflow["nodes"], **workflow["global_nodes"]}
    for _ in range(limit):
        if key == "closing":
            return key
        node = every[key]
        if node["node_type"] == "code":
            exec(code_of(node), {"vars": variables})
        for transition in node.get("transitions", []):
            if not transition.get("is_tool_call") and engine_holds(transition["condition"], variables):
                key = transition["target_node"]
                break
        else:
            return key
    raise AssertionError("routing loop")


class SpecTests(unittest.TestCase):
    def test_all_fixtures_load(self):
        for path in FIXTURES:
            with self.subTest(path=path.name):
                self.assertEqual(1, load_spec(path).spec_version)

    def test_missing_section_is_clear(self):
        value = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        value.pop("identity")
        with self.assertRaisesRegex(SpecError, "missing required.*identity"):
            parse_spec(value)

    def test_unknown_special_path_outcome_is_clear(self):
        value = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        value["special_paths"][0]["outcome"] = "not_in_table"
        with self.assertRaisesRegex(SpecError, "unknown outcome/reason"):
            parse_spec(value)

    def test_every_call_end_state_must_map_to_an_outcome(self):
        value = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        for item in value["outcomes"]:
            if "identity_failed" in item["on"]:
                item["on"].remove("identity_failed")
        with self.assertRaisesRegex(SpecError, "does not map.*identity_failed"):
            parse_spec(value)
        value = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        value["outcomes"][0]["on"].append("made_up_state")
        with self.assertRaisesRegex(SpecError, "unknown state"):
            parse_spec(value)

    def test_address_variables_are_required_names(self):
        value = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        value["opening"]["address_with"] = ["Mr Park"]
        with self.assertRaisesRegex(SpecError, "address_with"):
            parse_spec(value)

    def test_unclear_limit_must_be_positive(self):
        value = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        value["opening"]["max_unclear_asks"] = 0
        with self.assertRaisesRegex(SpecError, "max_unclear_asks.*positive integer"):
            parse_spec(value)


CARD = {"product_id": "p-card", "type": "credit_card", "card_last4": "0377", "past_due": 95.0,
        "days_late": 4, "minimum_payment": 28.5}
LOAN = {"product_id": "p-loan", "type": "personal_loan", "past_due": 300.0, "days_late": 20,
        "instalment_amount": 150.0}


class OfferCheckTests(unittest.TestCase):
    """Expected values computed by hand from each fixture's offer rules."""

    def run_offer(self, index, products, now, date, amount, number=None, state=None):
        spec = load_spec(FIXTURES[index])
        nodes = build_spec_workflow(spec, kit_tools(spec if index == 2 else None))["nodes"]
        variables = {spec.account.data["products_variable"]: json.dumps(products), "now": now}
        exec(code_of(nodes["offer_setup"]), {"vars": variables})
        variables.update(state or {})
        variables.update({"offer_date": date, "offer_amount": amount})
        if number is not None:
            variables["offer_product_number"] = number
        exec(code_of(nodes["check_offer"]), {"vars": variables})
        return variables

    def assertVerdict(self, variables, verdict, date="", amount=""):
        self.assertEqual(verdict, variables["offer_verdict"], variables["offer_message"])
        self.assertEqual(date, variables["offer_suggested_date"])
        self.assertEqual(amount, variables["offer_suggested_amount"])
        self.assertEqual("", variables["offer_date"])
        self.assertEqual("", variables["offer_amount"])

    def test_code_shape(self):
        for index in range(len(FIXTURES)):
            spec = load_spec(FIXTURES[index])
            nodes = build_spec_workflow(spec, kit_tools(spec if index == 2 else None))["nodes"]
            for key in ("offer_setup", "check_offer"):
                code = code_of(nodes[key])
                compile(code, key, "exec")
                self.assertNotIn("{{", code)
                self.assertNotIn("}}", code)

    def test_brief_a_rules(self):
        now = "2026-10-14T11:00"  # Wednesday
        cases = [
            # (product, date, amount, verdict, suggested date, suggested amount)
            (CARD, "2026-10-16", 95, "ok", "", ""),
            (CARD, "2026-11-02", 28.5, "ok", "", ""),                      # early band: 12th business day, holiday skipped
            (CARD, "2026-11-03", 95, "date_too_late", "2026-11-02", ""),
            (CARD, "2026-10-26", 95, "date_not_business_day", "2026-10-27", ""),  # holiday -> next business day
            (CARD, "2026-10-17", 95, "date_not_business_day", "2026-10-19", ""),  # Saturday
            (CARD, "2026-10-13", 95, "date_too_early", "2026-10-14", ""),         # before today
            (CARD, "2026-10-16", 20, "amount_too_low", "", 28.5),
            (CARD, "2026-10-16", 100, "amount_too_high", "", 95.0),
            (LOAN, "2026-10-23", 150, "ok", "", ""),                       # late band: 7th business day
            (LOAN, "2026-10-26", 150, "date_too_late", "2026-10-23", ""),
            (LOAN, "2026-10-20", 100, "amount_too_low", "", 150.0),
            (CARD, "next week", 95, "missing", "", ""),
            (CARD, "2026-10-16", "", "missing", "", ""),
        ]
        for product, date, amount, verdict, day, money in cases:
            with self.subTest(product=product["type"], date=date, amount=amount):
                self.assertVerdict(self.run_offer(0, [product], now, date, amount), verdict, day, money)

    def test_brief_a_late_deadline_on_holiday_week_and_setup_facts(self):
        variables = self.run_offer(0, [CARD, LOAN], "2026-10-14T11:00", "2026-10-16", 95, number=1)
        facts = variables["products_facts"]
        self.assertIn("Product 1: type credit_card", facts)
        self.assertIn("latest date Monday 2026-11-02", facts)
        self.assertIn("latest date Friday 2026-10-23", facts)
        self.assertIn("minimum amount 28.50", facts)
        self.assertIn("minimum amount 150.00", facts)
        self.assertNotIn("p-card", facts)
        self.assertEqual("Wednesday 2026-10-14", variables["today_text"])

    def test_brief_b_products_and_progress(self):
        now = "2026-10-14T11:00"
        unknown = self.run_offer(1, [CARD, LOAN], now, "2026-10-16", 95)
        self.assertVerdict(unknown, "product_unknown")
        first = self.run_offer(1, [CARD, LOAN], now, "2026-10-16", 95, number=1)
        self.assertVerdict(first, "ok")
        self.assertEqual("more", first["offer_progress"])
        self.assertEqual(1, first["offers_accepted_count"])
        second = self.run_offer(1, [CARD, LOAN], now, "2026-10-20", 150, number=2, state={
            "offers_accepted": first["offers_accepted"],
        })
        self.assertEqual("ready", second["offer_progress"])
        self.assertEqual(2, second["offers_accepted_count"])
        self.assertEqual(
            "Product 1: 95.00 on Friday 2026-10-16; Product 2: 150.00 on Tuesday 2026-10-20",
            second["offers_summary"],
        )
        accepted = json.loads(second["offers_accepted"])
        self.assertEqual({"product_id": "p-loan", "date": "2026-10-20", "amount": 150.0}, accepted["2"])

    def test_flattened_account_products_work_for_one_two_and_three_products(self):
        spec = load_spec(FIXTURES[1])
        nodes = build_spec_workflow(spec, kit_tools())["nodes"]
        products = [CARD, LOAN, dict(CARD, product_id="p-other", card_last4="9981")]
        for prefix in ("account_response", "get_account_response"):
            for count in (1, 2, 3):
                with self.subTest(prefix=prefix, count=count):
                    variables = {"now": "2026-10-14T11:00"}
                    for index, product in enumerate(products[:count]):
                        for field, value in product.items():
                            variables[f"{prefix}.data.products.{index}.{field}"] = value
                    exec(code_of(nodes["offer_setup"]), {"vars": variables})
                    self.assertEqual(count, variables["products_facts"].count("Product "))
                    self.assertNotIn("p-card", variables["products_facts"])
                    variables.update({"offer_date": "today", "offer_amount_kind": "full"})
                    if count > 1:
                        variables["offer_product_number"] = count
                    exec(code_of(nodes["check_offer"]), {"vars": variables})
                    accepted = json.loads(variables["offers_accepted"])
                    self.assertEqual(products[count - 1]["product_id"], accepted[str(count)]["product_id"])

    def test_relative_date_phrases_resolve_from_call_now(self):
        cases = {
            "today": ("ok", "2026-10-14"),
            "tomorrow": ("ok", "2026-10-15"),
            "this Friday": ("ok", "2026-10-16"),
            "next Monday": ("ok", "2026-10-19"),
            "Friday next week": ("ok", "2026-10-23"),
            "next week Friday": ("ok", "2026-10-23"),
            "Monday the week after next": ("date_not_business_day", "2026-10-27"),
            "Monday the 26th": ("date_not_business_day", "2026-10-27"),
            "October 20, 2026": ("ok", "2026-10-20"),
            "Oct 20": ("ok", "2026-10-20"),
            "the 20th": ("ok", "2026-10-20"),
            "the day after tomorrow": ("ok", "2026-10-16"),
            "2026-10-26": ("date_not_business_day", "2026-10-27"),
        }
        for phrase, (verdict, resolved) in cases.items():
            with self.subTest(phrase=phrase):
                result = self.run_offer(0, [CARD], "2026-10-14T11:00", phrase, 95)
                self.assertEqual(verdict, result["offer_verdict"])
                if verdict == "ok":
                    self.assertEqual(resolved, json.loads(result["offers_accepted"])["1"]["date"])
                else:
                    self.assertEqual(resolved, result["offer_suggested_date"])

        ambiguous = self.run_offer(0, [CARD], "2026-10-14T11:00", "next Friday", 95)
        self.assertEqual("date_ambiguous", ambiguous["offer_verdict"])
        self.assertEqual("Do you mean Friday 16 October?", ambiguous["offer_message"])
        self.assertEqual({}, json.loads(ambiguous["offers_accepted"]))
        self.assertVerdict(
            self.run_offer(0, [CARD], "2026-10-14T11:00", "next week", 95), "missing"
        )

    def test_amount_kinds_use_spec_derived_limits(self):
        cases = ((CARD, "full", 95.0), (CARD, "minimum", 28.5), (LOAN, "minimum", 150.0))
        for product, kind, expected in cases:
            with self.subTest(product=product["type"], kind=kind):
                result = self.run_offer(
                    0, [product], "2026-10-14T11:00", "tomorrow", "",
                    state={"offer_amount_kind": kind},
                )
                self.assertEqual(expected, json.loads(result["offers_accepted"])["1"]["amount"])

    def test_ready_needs_every_product_handled_not_an_extracted_count(self):
        now = "2026-10-14T11:00"
        # The extractor said 1, but the customer has two products: not ready after one.
        first = self.run_offer(1, [CARD, LOAN], now, "2026-10-16", 95, number=1, state={"agreed_item_count": 1})
        self.assertEqual("more", first["offer_progress"])
        # Product 2 was noted (for example disputed): product 1's offer makes it ready.
        noted = self.run_offer(1, [CARD, LOAN], now, "2026-10-16", 95, number=1, state={"offers_noted": "[2]"})
        self.assertEqual("ready", noted["offer_progress"])

    def test_amount_text_with_separators(self):
        now = "2026-10-14T11:00"
        big = dict(CARD, past_due=2000.0, minimum_payment=50.0)
        cases = {"1,200": 1200.0, "1.200,50": 1200.5, "1,200.50": 1200.5, "12,50": 12.5, "1.200.000": 1200000.0,
                 "95": 95.0, "$1,500": 1500.0}
        for text, value in cases.items():
            with self.subTest(text=text):
                variables = self.run_offer(0, [big], now, "2026-10-16", text)
                accepted = json.loads(variables["offers_accepted"]).get("1", {})
                if value <= 2000.0 and value >= 50.0:
                    self.assertEqual(value, accepted.get("amount"), variables["offer_message"])
                else:
                    self.assertNotEqual("ok", variables["offer_verdict"])

    def test_today_not_a_business_day_is_not_called_too_early(self):
        # 2026-10-26 is a Brief A holiday (Monday): an offer for today is moved, not "too early".
        variables = self.run_offer(0, [CARD], "2026-10-26T10:00", "2026-10-26", 95)
        self.assertVerdict(variables, "date_not_business_day", "2026-10-27")
        variables = self.run_offer(0, [CARD], "2026-10-26T10:00", "2026-10-23", 95)
        self.assertVerdict(variables, "date_too_early", "2026-10-27")

    def test_rejections_count_distinct_offers_up_to_the_spec_limit(self):
        now = "2026-10-14T11:00"
        state = {}
        progress = []
        for date in ("2026-11-03", "2026-11-03", "2026-11-04", "2026-11-05"):
            variables = self.run_offer(0, [CARD], now, date, 95, state=state)
            state = {key: variables[key] for key in ("offer_rejections", "offer_last_signature")}
            progress.append((variables["offer_rejections"], variables["offer_progress"]))
        self.assertEqual([(1, "rejected"), (1, "rejected"), (2, "rejected"), (3, "limit")], progress)

    def test_synthetic_rules_differ_from_the_practice_briefs(self):
        now = "2030-12-30T09:00"  # Monday; only Sunday is non-business, 2031-01-01 is a holiday
        item = {"product_id": "n-1", "type": "car_loan", "past_due": 100.0, "days_late": 3}
        cases = [
            ("2030-12-30", 60, "date_too_early", "2030-12-31", ""),  # earliest: 1 business day after today
            ("2031-01-20", 60, "ok", "", ""),                         # 20 calendar days lands on Sunday -> next
            ("2031-01-21", 60, "date_too_late", "2031-01-20", ""),
            ("2031-01-05", 60, "ok", "", ""),                         # Sunday allowed: no business-day rule
            ("2031-01-06", 40, "amount_too_low", "", 50.0),           # half of past_due
        ]
        for date, amount, verdict, day, money in cases:
            with self.subTest(date=date, amount=amount):
                self.assertVerdict(self.run_offer(2, [item], now, date, amount), verdict, day, money)

    def test_never_raises_on_missing_or_broken_inputs(self):
        spec = load_spec(FIXTURES[0])
        nodes = build_spec_workflow(spec, kit_tools())["nodes"]
        for variables in ({}, {"account_products": "not json", "now": "garbage"},
                          {"account_products": [None, 3], "offer_date": None, "offer_amount": "abc"}):
            setup, check = dict(variables), dict(variables)
            exec(code_of(nodes["offer_setup"]), {"vars": setup})
            exec(code_of(nodes["check_offer"]), {"vars": check})
            self.assertIn(check["offer_verdict"], {"missing", "product_unknown"})
            self.assertTrue(check["offer_message"])
            for key in ("products_facts", "today_text", "offers_summary", "offer_message", "offers_accepted"):
                self.assertIn(key, setup)

    def test_offer_routing(self):
        nodes = build_spec_workflow(load_spec(FIXTURES[0]), kit_tools())["nodes"]
        self.assertEqual("offer_setup", nodes["account"]["passthrough_default_transition"])
        self.assertEqual(["negotiate"], edges(nodes["offer_setup"]))
        self.assertEqual(["confirm_record", "closing", "negotiate"], edges(nodes["check_offer"]))
        first = nodes["negotiate"]["transitions"][0]
        self.assertEqual("check_offer", first["target_node"])
        rendered = json.dumps(first)
        self.assertIn('"variable": "offer_date", "operator": "is_set"', rendered)
        self.assertIn('"variable": "offer_amount", "operator": "not_equals", "operand": ""', rendered)
        self.assertIn('"variable": "offer_amount_kind", "operator": "equals", "operand": "full"', rendered)
        types = {item["name"]: item["type"] for item in nodes["negotiate"]["extraction_schema"]}
        self.assertEqual("string", types["offer_date"])
        self.assertEqual("float", types["offer_amount"])
        self.assertEqual("string", types["offer_amount_kind"])
        date_field = next(item for item in nodes["negotiate"]["extraction_schema"] if item["name"] == "offer_date")
        self.assertNotIn("{{today_text}}", date_field["description"])
        self.assertIn("{{products_facts}}", nodes["negotiate"]["task_message"])
        self.assertIn("{{offer_message}}", nodes["negotiate"]["task_message"])
        self.assertIn("{{offers_summary}}", nodes["confirm_record"]["task_message"])

    def test_offer_spec_validation(self):
        base = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        broken = [
            (("holidays",), ["26/10/2026"], "ISO date"),
            (("non_business_weekdays",), [0], "at least 1"),
            (("latest", 0, "unit"), "weeks", "unit must be one of"),
            (("min_amount", 0), {"field": "x", "value": 1}, "exactly one of field or value"),
            (("max_rejected_offers",), 0, "max_rejected_offers"),
            (("latest", 0, "when", 0), {"field": "x"}, "needs one of"),
        ]
        for path, value, message in broken:
            data = json.loads(json.dumps(base))
            target = data["offer"]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path):
                with self.assertRaisesRegex(SpecError, message):
                    parse_spec(data)


class MultiStepWorkflowTests(unittest.TestCase):
    def render(self, index=0):
        spec = load_spec(FIXTURES[index])
        return build_spec_workflow(spec, kit_tools(spec if index == 2 else None))

    def test_outcome_outside_close_call_enum_is_rejected(self):
        spec = load_spec(FIXTURES[2])
        with self.assertRaisesRegex(SpecError, "close_call enum"):
            build_spec_workflow(spec, kit_tools())

    def test_all_fixtures_render_without_null_or_agent_config(self):
        for index, path in enumerate(FIXTURES):
            with self.subTest(path=path.name):
                workflow = self.render(index)
                serialized = json.dumps(workflow)
                self.assertNotIn("null", serialized)
                self.assertNotIn("agent_config", workflow)
                for key, node in workflow["nodes"].items():
                    self.assertEqual(key, node["name"])
                    if "tools" in node:
                        self.assertEqual("conversation", node["node_type"])

    def test_reachability_and_terminal_shape(self):
        for index in range(len(FIXTURES)):
            with self.subTest(fixture=FIXTURES[index].name):
                workflow = self.render(index)
                nodes = workflow["nodes"]
                successors = graph(workflow)
                reached = {workflow["initial_node"]}
                pending = list(reached)
                while pending:
                    for target in successors[pending.pop()]:
                        if target not in reached:
                            reached.add(target)
                            pending.append(target)
                self.assertEqual(set(nodes) | set(workflow["global_nodes"]), reached)
                terminals = [key for key, node in nodes.items() if node["node_type"] == "end_call"]
                self.assertEqual(["end_call"], terminals)
                incoming_end = [source for source, targets in successors.items() if "end_call" in targets]
                self.assertEqual(["closing_say", "close_record"], incoming_end)
                for node in [*nodes.values(), *workflow["global_nodes"].values()]:
                    if node["node_type"] in {"api_request", "code"} or node.get("passthrough"):
                        self.assertEqual("always", node["transitions"][-1]["condition"]["operator"])

    def test_every_path_to_end_call_runs_the_close_path(self):
        for index in range(len(FIXTURES)):
            with self.subTest(fixture=FIXTURES[index].name):
                workflow = self.render(index)
                nodes = workflow["nodes"]
                successors = graph(workflow)
                # Remove the close path; then end_call must be unreachable from everywhere else.
                close_path = {"closing", "closing_say", "close_attempt", "close_record"}
                reached = {"opening"}
                pending = ["opening"]
                while pending:
                    for target in successors[pending.pop()]:
                        if target not in reached and target not in close_path:
                            reached.add(target)
                            pending.append(target)
                self.assertNotIn("end_call", reached)
                self.assertEqual(["closing_say"], edges(nodes["closing"]))
                self.assertEqual(["end_call", "close_attempt"], edges(nodes["closing_say"]))
                self.assertEqual(["close_record"], edges(nodes["close_attempt"]))
                # Tagging steps (states no variable identifies) only write their state.
                for key, targets in successors.items():
                    if "closing" in targets and key.startswith("close_"):
                        self.assertEqual("code", nodes[key]["node_type"])
                        self.assertIn("vars['close_state'] = ", code_of(nodes[key]))

    def test_conversation_steps_have_no_unconditional_self_loop(self):
        for index in range(len(FIXTURES)):
            nodes = self.render(index)["nodes"]
            for key, node in nodes.items():
                if node["node_type"] != "conversation":
                    continue
                for transition in node.get("transitions", []):
                    self.assertFalse(
                        transition["target_node"] == key
                        and transition["condition"].get("operator") == "always",
                        key,
                    )

    def terminal_scenarios(self, index):
        """(expected state, [(start step, variables to add before walking)]) for every
        call-end path, built from the spec only. Verified-stage scenarios carry leftovers of
        earlier stages (who answered, identity attempts at 0) that must not win."""
        spec = load_spec(FIXTURES[index])
        opening, third = spec.opening.data, spec.third_party.data
        negotiation, confirmation = spec.negotiation.data, spec.confirmation.data
        who = opening["who_answered_variable"]
        verified = {who: opening["identity_values"][0], "identity_verified": "true", "identity_attempts_left": 0}
        caller = {who: opening["third_party_values"][0]}
        scenarios = [
            *((f"opening:{value}", [("opening", {who: value})]) for value in opening["close_values"]),
            ("opening_unclear", [("opening", {
                who: opening["stay_values"][0], opening["unclear_count_variable"]: opening["max_unclear_asks"] - 1,
            })]),
            ("opening_unclear", [("opening_reask", {
                who: opening["stay_values"][0], opening["unclear_count_variable"]: opening["max_unclear_asks"] - 1,
            })]),
            ("callback_scheduled", [("third_party", {**caller, "callback_ok": "True"})]),
            ("callback_failed", [("third_party", {**caller, "schedule_callback_response.data.ok": "false"})]),
            ("callback_failed", [("third_party", {**caller, "schedule_callback_failure_count": 1})]),
            *((f"third_party:{value}", [("third_party", {**caller, third["intent_variable"]: value})])
              for value in third["close_values"]),
            ("identity_failed", [("identity", {who: opening["identity_values"][0],
                                               "identity_verified": "false", "identity_attempts_left": 0})]),
            ("account_failed", [("account", {**verified, "account_failure_count": 1})]),
            *((f"negotiation:{value}", [("negotiate", {**verified, negotiation["intent_variable"]: value,
                                                        "offers_accepted_count": 0})])
              for value in negotiation["close_values"]),
            ("promise_recorded", [("confirmation_progress", {**verified, "promise_result_ok": "true",
                                                             "offers_accepted_count": 1})]),
            ("promise_failed", [("confirmation_progress", {
                **verified, "promise_result_ok": "false", "offers_accepted_count": 1,
                "create_promise_args." + confirmation["product_number_field"]: 1,
                "promise_attempts_1": confirmation["max_attempts_per_product"] - 1,
            })]),
            ("turn_limit", [(self.render(index)["nodes"]["negotiate"]["max_turn_transition"], dict(verified))]),
        ]
        # Too many rejected offers: distinct invalid offers until check_offer gives up.
        products = {spec.account.data["products_variable"]: json.dumps([CARD]), "now": "2026-10-14T11:00"}
        offers = [("check_offer", {"offer_date": "2000-01-01", "offer_amount": amount}) for amount in range(1, 10)]
        scenarios.append(("offer_limit", [("offer_setup", {**verified, **products}), *offers]))
        for path in spec.special_paths:
            if path.then != "close":
                continue
            key = "special_" + path.id
            result = "special_result_" + path.id
            start = [(key, {result + "_choice": "proceed"})] if path.ask else [(key, {})]
            if path.tool:
                scenarios.append(("special:" + path.id, [(start[0][0], {**verified, **start[0][1], result: "True"})]))
                scenarios.append(("special_tool_failed", [(start[0][0], {**verified, **start[0][1], result: "false"})]))
            else:
                scenarios.append(("special:" + path.id, [(start[0][0], {**verified, **start[0][1]})]))
        return spec, scenarios

    def run_scenario(self, workflow, steps):
        """Start at the first step; later entries add what the customer says where the
        call is waiting."""
        variables, key = {}, steps[0][0]
        for _, added in steps:
            variables.update(added)
            key = walk(workflow, key, variables)
            if key == "closing":
                break
        return key, variables

    def test_every_call_end_path_derives_its_state_and_outcome(self):
        for index in range(len(FIXTURES)):
            spec, scenarios = self.terminal_scenarios(index)
            workflow = self.render(index)
            code = code_of(workflow["nodes"]["closing"])
            compile(code, "<closing>", "exec")
            self.assertNotIn("{{", code)
            self.assertNotIn("}}", code)
            states = set(required_close_states(spec)) - {"default"}
            states |= set(OPTIONAL_CLOSE_STATES) - set(HANGUP_CLOSE_STATES)
            states -= {"special_tool_failed"} if not any(p.tool and p.then == "close" for p in spec.special_paths) else set()
            states |= {"special:" + path.id for path in spec.special_paths if path.then == "close"}
            self.assertEqual(states, {state for state, _ in scenarios})
            table = {row[0]: row for row in close_table(spec)}
            for state, steps in scenarios:
                with self.subTest(fixture=FIXTURES[index].name, state=state, start=steps[0][0]):
                    key, variables = self.run_scenario(workflow, steps)
                    self.assertEqual("closing", key)
                    before = dict(variables)
                    exec(code, {"vars": variables})
                    expected = table.get(state, table["default"])
                    self.assertEqual(expected[0], variables["close_resolved_state"])
                    self.assertEqual(expected[1], variables["close_outcome"])
                    self.assertEqual(expected[2], variables.get("close_reason", ""))
                    self.assertTrue(variables["closing_sentence"])
                    # The end-of-call close derives the same row from the same variables.
                    if not before.get("promise_recorded_count"):
                        config = self.run_hangup(before, index)
                        self.assertEqual(expected[1], config["body"]["outcome"])
            for bad in ({}, {"close_state": None, "promise_recorded_count": "x"}, {"close_state": "nope"},
                        {"identity_attempts_left": "x", "account_failure_count": None}):
                variables = dict(bad)
                exec(code, {"vars": variables})
                self.assertEqual(table["default"][1], variables["close_outcome"])

    def test_close_state_tagging_steps_are_only_for_underivable_states(self):
        from builder.workflow import TAGGED_CLOSE_STATES
        for index in range(len(FIXTURES)):
            nodes = self.render(index)["nodes"]
            tags = {key for key in nodes if key.startswith("close_") and key not in {"close_attempt", "close_record"}}
            self.assertTrue(tags <= {"close_" + state for state in TAGGED_CLOSE_STATES}, tags)
            self.assertIn("close_turn_limit", tags)

    def test_explicit_state_wins_and_stale_variables_do_not(self):
        workflow = self.render()
        code = code_of(workflow["nodes"]["closing"])
        # Verified customer with leftover zero attempts and an earlier refusal that was
        # followed by an accepted offer: the transfer result decides.
        variables = {"who_answered": "customer", "identity_verified": "True", "identity_attempts_left": 0,
                     "negotiation_intent": "refusal", "offers_accepted_count": 1, "special_result_human": "true"}
        exec(code, {"vars": variables})
        self.assertEqual("special:human", variables["close_resolved_state"])
        variables = {"close_state": "promise_failed", "identity_attempts_left": 0, "identity_verified": "false"}
        exec(code, {"vars": variables})
        self.assertEqual("promise_failed", variables["close_resolved_state"])

    def test_brief_a_closing_states_match_its_outcome_table(self):
        spec = load_spec(FIXTURES[0])
        code = code_of(self.render()["nodes"]["closing"])
        cases = {
            "identity_failed": ("not_verified", "failed", "mobile app"),
            "promise_failed": ("no_promise", "service_error", "could not record"),
            "special:human": ("transferred", "human", "Goodbye"),
        }
        for state, (outcome, reason, phrase) in cases.items():
            variables = {"close_state": state}
            exec(code, {"vars": variables})
            self.assertEqual((outcome, reason), (variables["close_outcome"], variables["close_reason"]))
            self.assertIn(phrase, variables["closing_sentence"])
        variables = {"close_state": "promise_recorded"}
        exec(code, {"vars": variables})
        self.assertEqual("promise", variables["close_outcome"])
        self.assertNotIn("close_reason", variables)
        # A recorded promise wins over a state the table does not map.
        variables = {"close_state": "unmapped", "promise_recorded_count": 1}
        exec(code, {"vars": variables})
        self.assertEqual("promise", variables["close_outcome"])
        # A transfer after a recorded promise still closes as transferred.
        variables = {"close_state": "special:human", "promise_recorded_count": 1}
        exec(code, {"vars": variables})
        self.assertEqual(("transferred", "human"), (variables["close_outcome"], variables["close_reason"]))
        # Hitting the turn limit is not a service error; it uses the default row.
        default = next(item for item in spec.outcomes if "default" in item.on)
        variables = {"close_state": "turn_limit"}
        exec(code, {"vars": variables})
        self.assertEqual((default.outcome, default.reason), (variables["close_outcome"], variables["close_reason"]))

    def test_recorded_promise_wins_unless_the_row_says_otherwise(self):
        for index in range(len(FIXTURES)):
            spec = load_spec(FIXTURES[index])
            code = code_of(self.render(index)["nodes"]["closing"])
            table = {row[0]: row for row in close_table(spec)}
            for state, row in table.items():
                variables = {"close_state": state, "promise_recorded_count": 1}
                exec(code, {"vars": variables})
                expected = row if row[4] else table["promise_recorded"]
                with self.subTest(fixture=FIXTURES[index].name, state=state):
                    self.assertEqual(expected[1], variables["close_outcome"])
        # Brief B: one product recorded, another failed twice -> promise.
        code = code_of(self.render(1)["nodes"]["closing"])
        variables = {"close_state": "promise_failed", "promise_recorded_count": 1}
        exec(code, {"vars": variables})
        self.assertEqual("promise", variables["close_outcome"])
        self.assertNotIn("close_reason", variables)

    def test_wins_over_promise_must_be_boolean(self):
        value = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        value["outcomes"][0]["wins_over_promise"] = "yes"
        with self.assertRaisesRegex(SpecError, "wins_over_promise must be true or false"):
            parse_spec(value)

    def test_close_call_runs_engine_side_with_baked_values_and_bounded_retry(self):
        nodes = self.render()["nodes"]
        record = nodes["close_record"]
        self.assertEqual("api_request", record["node_type"])
        tool = record["pre_actions"][0]
        self.assertEqual("close_call", tool["function"]["name"])
        body = tool["function"]["parameters"]["properties"]["body"]
        self.assertEqual("{{close_outcome}}", body["properties"]["outcome"]["default"])
        self.assertEqual("{{close_reason}}", body["properties"]["reason"]["default"])
        self.assertNotIn("outcome", body.get("required", []))
        self.assertIn("post_process_code", tool)
        self.assertEqual([{"path": "data.ok", "variable": "close_call_ok"}], record["response_mapping"])
        self.assertEqual(["end_call", "close_attempt"], edges(record))
        self.assertEqual(["end_call", "close_attempt"], edges(nodes["closing_say"]))
        self.assertTrue(engine_holds(nodes["closing_say"]["transitions"][0]["condition"], {"close_call_ok": "true"}))
        success_or_given_up = json.dumps(record["transitions"][0])
        self.assertIn('"variable": "close_call_ok"', success_or_given_up)
        self.assertIn('"variable": "close_attempts", "operator": "greater_than", "operand": 1', success_or_given_up)
        attempt = {"close_call_ok": "False"}
        exec(code_of(nodes["close_attempt"]), {"vars": attempt})
        exec(code_of(nodes["close_attempt"]), {"vars": attempt})
        self.assertEqual(2, attempt["close_attempts"])
        self.assertEqual("", attempt["close_call_ok"])
        self.assertEqual({"type": "tts", "text": "{{closing_sentence}}"}, nodes["closing_say"]["on_enter"])
        self.assertEqual(0, tool["config"]["maxRetries"])
        for key, node in nodes.items():
            self.assertNotIn("close_call", tool_names(node), key)

    def test_negotiation_prompt_and_extraction_enforce_honesty_and_refusal_meaning(self):
        workflow = self.render()
        task = workflow["nodes"]["negotiate"]["task_message"]
        self.assertIn("say the last offer check message", task)
        self.assertIn("never say a payment or promise was recorded", task)
        self.assertIn("Never read an internal id", task)
        self.assertIn("cannot pay on one date", task)
        self.assertIn("create_promise returned ok true", workflow["system_prompt"])
        intent = next(
            item for item in workflow["nodes"]["negotiate"]["extraction_schema"]
            if item["name"] == load_spec(FIXTURES[0]).negotiation.data["intent_variable"]
        )
        self.assertIn("refuses any payment or arrangement after being asked for alternatives", intent["description"])
        self.assertIn("Not today, not now", intent["description"])

    def test_opening_addresses_customer_with_spec_call_variables(self):
        for index in range(len(FIXTURES)):
            spec = load_spec(FIXTURES[index])
            task = self.render(index)["nodes"]["opening"]["task_message"]
            address = " ".join("{{" + name + "}}" for name in spec.opening.data["address_with"])
            self.assertIn(address, task)

    def test_identity_prompt_handles_failed_and_exhausted_answers(self):
        for index in range(len(FIXTURES)):
            spec = load_spec(FIXTURES[index])
            task = self.render(index)["nodes"]["identity"]["task_message"]
            identity = spec.identity.data
            self.assertIn(identity["answer_verified_field"] + " is false: say the answer did not match", task)
            self.assertIn("Ask the same question again", task)
            self.assertIn("After the last question, ask nothing more", task)
            self.assertIn("Do not thank them as if it passed", task)
            self.assertIn(identity["failed_answer_instruction"]["text"], task)
            self.assertIn(identity["attempts_left_field"] + " is 0: " + identity["exhausted_say"]["text"], task)
            self.assertIn("Ask nothing more", task)
            self.assertIn("Never ask the customer to say a technical format", task)
            self.assertNotIn("Answer format:", task)

    def test_tools_are_scoped(self):
        nodes = self.render()["nodes"]
        self.assertEqual(["verify_identity"], tool_names(nodes["identity"]))
        self.assertEqual(["create_promise"], tool_names(nodes["confirm_record"]))
        for key, node in nodes.items():
            if key != "identity":
                self.assertNotIn("verify_identity", tool_names(node))
            if key != "confirm_record":
                self.assertNotIn("create_promise", tool_names(node))
            self.assertNotIn("close_call", tool_names(node))

    def test_freya_extraction_and_passthrough_wire_shapes(self):
        workflow = self.render()
        nodes = workflow["nodes"]
        for key in ("opening", "third_party", "negotiate"):
            schema = nodes[key]["extraction_schema"]
            self.assertIsInstance(schema, list)
            self.assertIn("name", schema[0])
            self.assertIn("min_confidence", schema[0])
        account = nodes["account"]
        self.assertTrue(account["passthrough"])
        self.assertIn("response_mapping", account)
        self.assertNotIn("response_mapping", account["pre_actions"][0])
        for node in [*nodes.values(), *workflow["global_nodes"].values()]:
            for transition in node.get("transitions", []):
                self.assertNotIn("is_tool_call", transition)

    def test_special_tool_args_are_baked(self):
        nodes = self.render()["nodes"]
        tool = nodes["special_human_go"]["pre_actions"][0]
        body = tool["function"]["parameters"]["properties"]["body"]
        self.assertEqual("general", body["properties"]["queue"]["default"])
        self.assertNotIn("queue", body.get("required", []))
        self.assertEqual(0, tool["config"]["maxRetries"])

    def test_identity_routes_on_both_true_spellings_and_attempt_count(self):
        transitions = self.render()["nodes"]["identity"]["transitions"]
        rendered = json.dumps(transitions)
        self.assertIn('"operand": "true"', rendered)
        self.assertIn('"operand": "True"', rendered)
        self.assertIn('"operator": "less_than", "operand": 1', rendered)

    def test_product_hook_maps_any_index_from_three_supported_variable_shapes(self):
        tool = self.render(1)["nodes"]["special_product_dispute"]["tools"][0]
        code = tool["pre_process_code"]
        compile(code, "<product-hook>", "exec")
        self.assertNotIn("{{", code)
        products = [
            {"product_id": "id-a"}, {"product_id": "id-b"},
            {"product_id": "id-c"}, {"product_id": "id-d"},
        ]
        account_flattened = {
            f"account_response.data.products.{index}.product_id": product["product_id"]
            for index, product in enumerate(products)
        }
        tool_flattened = {
            key.replace("account_response", "get_account_response"): value
            for key, value in account_flattened.items()
        }
        sources = (
            {"late_products": products},
            {"late_products": json.dumps(products)},
            {"get_account_response.data.products": products},
            account_flattened,
            tool_flattened,
        )
        for source in sources:
            config = {"body": {"selected_product_number": 4}}
            exec(code, {"config": config, "vars": source, "json": json})
            self.assertEqual("id-d", config["body"]["product_id"])
            self.assertNotIn("selected_product_number", config["body"])
        for bad in (None, "", "x", 0, 5, {}, []):
            config = {"body": {"selected_product_number": bad}}
            exec(code, {"config": config, "vars": {"late_products": products}, "json": json})

    def test_promise_values_come_from_checked_offers(self):
        tool = self.render(1)["nodes"]["confirm_record"]["tools"][0]
        body = tool["function"]["parameters"]["properties"]["body"]
        self.assertEqual({"customer_id", "selected_product_number"}, set(body["properties"]))
        hook = tool["pre_process_code"]
        compile(hook, "<promise-hook>", "exec")
        self.assertNotIn("{{", hook)
        self.assertNotIn("}}", hook)
        accepted = {"1": {"product_id": "id-a", "date": "2026-10-16", "amount": 95.0},
                    "2": {"product_id": "id-b", "date": "2026-10-20", "amount": 150.0}}
        config = {"body": {"customer_id": "c", "selected_product_number": 2, "date": "1999-01-01"}}
        exec(hook, {"config": config, "vars": {"offers_accepted": json.dumps(accepted)}})
        self.assertEqual(
            {"customer_id": "c", "product_id": "id-b", "date": "2026-10-20", "amount": 150.0}, config["body"]
        )
        # A single accepted offer is used even if the model names no valid number.
        config = {"body": {"customer_id": "c", "selected_product_number": "x"}}
        exec(hook, {"config": config, "vars": {"offers_accepted": json.dumps({"1": accepted["1"]})}})
        self.assertEqual("id-a", config["body"]["product_id"])
        for bad in ({}, {"offers_accepted": "x"}, {"offers_accepted": None}):
            config = {"body": {"selected_product_number": 1}}
            exec(hook, {"config": config, "vars": dict(bad)})
            self.assertNotIn("product_id", config["body"])

    def test_confirmation_progress_supports_multiple_products_and_one_retry(self):
        node = self.render(1)["nodes"]["confirmation_progress"]
        code = node["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        variables = {"agreed_item_count": 2, "create_promise_args.selected_product_number": 1, "promise_result_ok": True}
        exec(code, {"vars": variables})
        self.assertEqual("continue", variables["promise_progress_state"])
        self.assertEqual("consumed", variables["promise_result_ok"])
        variables.update({"create_promise_args.selected_product_number": 2, "promise_result_ok": True})
        exec(code, {"vars": variables})
        self.assertEqual("complete", variables["promise_progress_state"])

        variables = {"agreed_item_count": 1, "create_promise_args.selected_product_number": 1, "promise_result_ok": False}
        exec(code, {"vars": variables})
        self.assertEqual("retry", variables["promise_progress_state"])
        variables["promise_result_ok"] = False
        exec(code, {"vars": variables})
        self.assertEqual("exhausted", variables["promise_progress_state"])

        variables = {
            "offers_accepted_count": 1,
            "create_promise_args": json.dumps({"selected_product_number": 1}),
            "create_promise_response.data.ok": "true",
        }
        exec(code, {"vars": variables})
        self.assertEqual("complete", variables["promise_progress_state"])

    def test_opening_unclear_counter_close_and_stay_routes(self):
        nodes = self.render()["nodes"]
        opening = json.dumps(nodes["opening"]["transitions"])
        self.assertIn('"target_node": "opening_unclear"', opening)
        self.assertIn('"target_node": "closing"', opening)
        self.assertEqual(["closing", "opening_reask"], edges(nodes["opening_unclear"]))
        code = nodes["opening_unclear"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        variables = {"who_answered": "unclear"}
        exec(code, {"vars": variables})
        self.assertEqual(1, variables["opening_unclear_count"])
        self.assertEqual("", variables["who_answered"])
        self.assertNotIn("close_state", variables)
        exec(code, {"vars": variables})
        self.assertEqual(2, variables["opening_unclear_count"])
        self.assertEqual("opening_unclear", variables["close_state"])
        synthetic_transitions = self.render(2)["nodes"]["opening_unclear"]["transitions"]
        self.assertIn('"operand": 2', json.dumps(synthetic_transitions))

    def test_greeting_is_its_own_value_and_never_counts_as_unclear(self):
        from builder.spec import OPENING_GREETING_VALUE
        for index in range(len(FIXTURES)):
            spec = load_spec(FIXTURES[index])
            opening = spec.opening.data
            workflow = self.render(index)
            for key in ("opening", "opening_reask"):
                node = workflow["nodes"][key]
                field = node["extraction_schema"][0]
                with self.subTest(fixture=FIXTURES[index].name, step=key):
                    self.assertEqual(opening["who_answered_variable"], field["name"])
                    self.assertEqual([*opening["who_answered_options"], OPENING_GREETING_VALUE], field["enum_values"])
                    self.assertIn(OPENING_GREETING_VALUE + ":", field["description"])
                    self.assertNotIn(f'"operand": "{OPENING_GREETING_VALUE}"', json.dumps(node["transitions"]))
                    variables = {opening["who_answered_variable"]: OPENING_GREETING_VALUE}
                    self.assertEqual(key, walk(workflow, key, variables))
                    self.assertNotIn(opening["unclear_count_variable"], variables)
        value = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        value["opening"]["who_answered_options"].append(OPENING_GREETING_VALUE)
        with self.assertRaisesRegex(SpecError, "must not contain 'greeting'"):
            parse_spec(value)

    def test_introduction_is_spoken_once_and_disclosure_comes_first(self):
        for index in range(len(FIXTURES)):
            spec = load_spec(FIXTURES[index])
            workflow = self.render(index)
            nodes = workflow["nodes"]
            introduction = spec.agent.introduction.text
            with self.subTest(fixture=FIXTURES[index].name):
                self.assertTrue(nodes["opening"]["on_enter_first_entry_only"])
                self.assertIn(introduction, nodes["opening"]["task_message"])
                # Asking again happens in its own step, which never repeats the introduction
                # and still speaks on entry (default llm entry, not silent).
                reask = nodes["opening_reask"]
                self.assertNotIn(introduction, reask["task_message"])
                self.assertNotIn("on_enter", reask)
                self.assertNotIn("on_enter_first_entry_only", reask)
                self.assertEqual(nodes["opening"]["transitions"], reask["transitions"])
                self.assertEqual(["closing", "opening_reask"], edges(nodes["opening_unclear"]))
                into_opening = [
                    key for key, node in {**nodes, **workflow["global_nodes"]}.items()
                    if "opening" in edges(node)
                ]
                self.assertEqual([], into_opening)
                # Disclosure first, from any step the call can reach first.
                self.assertIn("give it first in your next message, whatever the customer said: " + introduction,
                              workflow["system_prompt"])

    def test_model_product_field_is_never_written_as_a_workflow_variable(self):
        workflow = self.render(1)
        tool = workflow["nodes"]["confirm_record"]["tools"][0]
        hook = tool["pre_process_code"]
        progress = workflow["nodes"]["confirmation_progress"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        self.assertNotIn("vars['selected_product_number'] =", hook)
        self.assertIn("create_promise_args.selected_product_number", progress)
        self.assertNotIn("vars.pop('promise_result_ok'", progress)
        transitions = workflow["nodes"]["confirm_record"]["transitions"]
        result_transition = next(item for item in transitions if item["target_node"] == "confirmation_progress")
        self.assertEqual(
            ["true", "True", "false", "False"],
            [condition["operand"] for condition in result_transition["condition"]["conditions"]],
        )

    def test_special_paths_are_global_nodes_with_scoped_exclusions(self):
        def exits(item):
            return [transition["target_node"] for transition in item["transitions"]]

        for index in range(len(FIXTURES)):
            spec = load_spec(FIXTURES[index])
            workflow = self.render(index)
            nodes, globals_ = workflow["nodes"], workflow["global_nodes"]
            self.assertFalse([key for key in nodes if "_from_" in key])
            close_chain = {"closing", "closing_say", "close_attempt", "close_record", "end_call"}
            for path in spec.special_paths:
                key = "special_" + path.id
                per_source = key not in globals_
                entries = (
                    {f"{key}_at_{source}": {source} for source in source_steps(path)}
                    if per_source else {key: set(source_steps(path))}
                )
                with self.subTest(fixture=FIXTURES[index].name, path=path.id):
                    for entry_key, sources in entries.items():
                        node = globals_[entry_key]
                        self.assertEqual(entry_key, node["name"])
                        self.assertEqual("matches_intent", node["condition"]["operator"])
                        fires_in = {name for name in nodes if name not in node["excluded_nodes"]}
                        self.assertEqual(sources, fires_in)
                        self.assertTrue(close_chain <= set(node["excluded_nodes"]))
                        self.assertTrue(set(globals_) <= set(node["excluded_nodes"]))
                        if "identity" not in path.available_in:
                            self.assertIn("identity", node["excluded_nodes"])
                            self.assertIn("opening", node["excluded_nodes"])
                    if per_source:
                        # Model-filled tool: explicit return targets, no __previous__.
                        targets = exits(nodes[key]) + exits(nodes.get(key + "_done", {"transitions": []}))
                        self.assertNotIn("__previous__", targets)
                        if path.then == "return":
                            self.assertTrue(set(path.available_in) <= set(targets))
                        continue
                    node = globals_[key]
                    targets = exits(node) + (exits(nodes[key + "_go"]) if path.ask else [])
                    if path.then == "return":
                        self.assertEqual({"__previous__"}, set(targets))
                    else:
                        self.assertIn("closing", targets)
                        if path.ask:
                            self.assertIn("__previous__", edges(node))

    def test_special_path_available_in_opening_also_fires_in_opening_reask(self):
        for index, path_id in ((0, "human"), (0, "already_paid"), (1, "product_dispute")):
            value = json.loads(FIXTURES[index].read_text(encoding="utf-8"))
            item = next(entry for entry in value["special_paths"] if entry["id"] == path_id)
            item["available_in"] = ["opening", *item["available_in"]]
            spec = parse_spec(value)
            path = next(entry for entry in spec.special_paths if entry.id == path_id)
            self.assertEqual(("opening", "opening_reask"), source_steps(path)[:2])
            workflow = build_spec_workflow(spec, kit_tools())
            nodes, globals_ = workflow["nodes"], workflow["global_nodes"]
            key = "special_" + path_id
            entries = [name for name in globals_ if name == key or name.startswith(key + "_at_")]
            with self.subTest(path=path_id):
                fires_in = {
                    step for name in entries for step in nodes if step not in globals_[name]["excluded_nodes"]
                }
                self.assertEqual(set(source_steps(path)), fires_in)
                if path.then == "return" and key + "_done" in nodes:
                    self.assertIn(key + "_at_opening_reask", globals_)
                    self.assertIn("opening_reask", edges(nodes[key + "_done"]))
        # Without opening in available_in, neither opening step is a source.
        for path in load_spec(FIXTURES[0]).special_paths:
            self.assertNotIn("opening_reask", source_steps(path))

    def test_identity_failed_needs_an_explicit_unverified_result(self):
        workflow = self.render()
        code = code_of(workflow["nodes"]["closing"])
        for verified, expected in (("false", "identity_failed"), ("False", "identity_failed"),
                                   (None, "default"), ("true", "default"), ("True", "default")):
            variables = {"identity_attempts_left": 0}
            if verified is not None:
                variables["identity_verified"] = verified
            with self.subTest(verified=verified):
                self.assertEqual(expected == "identity_failed",
                                 walk(workflow, "identity", dict(variables)) == "closing")
                exec(code, {"vars": variables})
                self.assertEqual(expected, variables["close_resolved_state"])

    def test_model_tool_special_path_clears_stale_result_and_returns_to_its_source(self):
        workflow = self.render(1)
        nodes, globals_ = workflow["nodes"], workflow["global_nodes"]
        for source in ("negotiate", "confirm_record"):
            entry = globals_["special_product_dispute_at_" + source]
            variables = {"special_result_product_dispute": "True"}
            exec(code_of(entry), {"vars": variables})
            self.assertEqual("", variables["special_result_product_dispute"])
            self.assertEqual(source, variables["special_result_product_dispute_from"])
            self.assertEqual(["special_product_dispute"], edges(entry))
        done = nodes["special_product_dispute_done"]
        self.assertEqual(["negotiate", "confirm_record"], edges(done))
        self.assertEqual("always", done["transitions"][-1]["condition"]["operator"])
        back = json.dumps(done["transitions"][0])
        self.assertIn('"variable": "special_result_product_dispute_from", "operator": "equals", "operand": "negotiate"', back)
        self.assertIn('"variable": "offer_progress", "operator": "not_equals", "operand": "ready"', back)

    def test_done_step_without_confirm_source_keeps_ready_shortcut(self):
        from builder.workflow import _done_transitions
        transitions = _done_transitions("from_var", ("negotiate", "identity"))
        self.assertEqual(["confirm_record", "negotiate", "identity"], [item["target_node"] for item in transitions])
        self.assertEqual("always", transitions[-1]["condition"]["operator"])

    def test_no_step_names_a_target_twice(self):
        for index in range(len(FIXTURES)):
            workflow = self.render(index)
            for key, node in {**workflow["nodes"], **workflow["global_nodes"]}.items():
                targets = [item["target_node"] for item in node.get("transitions", [])]
                with self.subTest(fixture=FIXTURES[index].name, step=key):
                    self.assertEqual(len(targets), len(set(targets)), targets)

    def test_grouping_merges_conditions_and_rejects_mixed_unconditional(self):
        from builder.workflow import group_transitions_by_target
        a = {"target_node": "x", "description": "a", "condition": {"logic": "or", "conditions": [{"variable": "v", "operator": "equals", "operand": 1}]}}
        b = {"target_node": "y", "description": "b", "condition": {"logic": "or", "conditions": [{"variable": "w", "operator": "equals", "operand": 2}]}}
        c = {"target_node": "x", "description": "c", "condition": {"logic": "or", "conditions": [{"variable": "u", "operator": "is_set"}]}}
        merged = group_transitions_by_target([a, b, c])
        self.assertEqual(["x", "y"], [item["target_node"] for item in merged])
        self.assertEqual(2, len(merged[0]["condition"]["conditions"]))
        always = {"target_node": "x", "description": "d", "condition": {"operator": "always"}}
        with self.assertRaisesRegex(ValueError, "internal: target 'x'"):
            group_transitions_by_target([a, b, always])

    def hangup_tool(self, index=0):
        tools = self.render(index)["tools"]
        self.assertEqual(1, len(tools))
        return tools[0]

    def test_hangup_close_is_an_end_of_call_tool_that_needs_no_model(self):
        for index in range(len(FIXTURES)):
            tool = self.hangup_tool(index)
            with self.subTest(fixture=FIXTURES[index].name):
                self.assertEqual(["end_of_call"], tool["config"]["alwaysRunsAt"])
                self.assertEqual(0, tool["config"]["maxRetries"])
                self.assertEqual("close_call_on_hangup", tool["function"]["name"])
                body = tool["function"]["parameters"]["properties"]["body"]
                self.assertNotIn("required", body)
                for name, prop in body["properties"].items():
                    default = prop.get("default")
                    self.assertIsNotNone(default, name)
                    placeholder = re.fullmatch(r"\{\{(\w+)\}\}", str(default))
                    if placeholder:
                        self.assertIn(placeholder.group(1), CALL_VARIABLES, name)
                code = tool["pre_process_code"]
                compile(code, "<hangup>", "exec")
                self.assertNotIn("{{", code)
                self.assertNotIn("}}", code)

    def run_hangup(self, variables, index=0, hook=True):
        tool = self.hangup_tool(index)
        properties = tool["function"]["parameters"]["properties"]
        body = {name: prop["default"] for name, prop in properties["body"]["properties"].items()}
        config = {"url": properties["url"]["default"], "body": body}
        if hook:
            exec(tool["pre_process_code"], {"vars": variables, "config": config})
        return config

    def test_hangup_close_is_fail_closed(self):
        tool = self.hangup_tool()
        self.assertEqual("", tool["function"]["parameters"]["properties"]["url"]["default"])
        real = self.render()["nodes"]["close_record"]["pre_actions"][0]["function"]["parameters"]["properties"]["url"]["default"]
        self.assertTrue(real.endswith("/close_call"))
        self.assertIn(repr(real)[1:-1], tool["pre_process_code"])
        # If the hook never runs, nothing can be sent.
        self.assertEqual("", self.run_hangup({}, hook=False)["url"])
        # The send branch writes the real URL; a hook error before that leaves it empty.
        self.assertEqual(real, self.run_hangup({})["url"])
        config = {"url": "", "body": None}
        exec(tool["pre_process_code"], {"vars": {}, "config": config})
        self.assertEqual("", config["url"])

    def test_hangup_close_never_double_records(self):
        for variables in ({"close_call_ok": "True"}, {"close_call_ok": "false", "close_attempts": 2}, {"close_attempts": 1}):
            config = self.run_hangup(dict(variables))
            self.assertEqual("", config["url"])
            self.assertEqual({}, config["body"])

    def test_hangup_close_outcome_from_call_state(self):
        cases = [
            ({}, ("not_verified", "declined")),                                    # hung up before verification
            ({"identity_verified": "True"}, ("no_promise", "refused")),           # verified, no promise: default row
            ({"identity_verified": "true", "promise_recorded_count": 1}, ("promise", None)),
            ({"identity_verified": "true", "close_state": "special:human"}, ("transferred", "human")),
            ({"close_state": "identity_failed"}, ("not_verified", "failed")),
        ]
        for variables, (outcome, reason) in cases:
            with self.subTest(variables=variables):
                config = self.run_hangup(dict(variables))
                self.assertTrue(config["url"].endswith("/close_call"))
                self.assertEqual(outcome, config["body"]["outcome"])
                self.assertEqual(reason, config["body"].get("reason"))
                self.assertEqual("{{customer_id}}", config["body"]["customer_id"])
        for broken in ({"promise_recorded_count": "x", "close_attempts": "y"}, {"close_state": None}):
            self.run_hangup(dict(broken))
        # Without a hang-up row the default row is used.
        config = self.run_hangup({}, index=1)
        self.assertEqual("no_promise", config["body"]["outcome"])

    def test_missing_bank_tool_stops_with_a_clear_error(self):
        document = json.loads((ROOT / "build-the-builder-v2/tools/openapi.json").read_text(encoding="utf-8"))
        document["paths"]["/close_up"] = document["paths"].pop("/close_call")
        with self.assertRaisesRegex(SpecError, "does not define the bank tools.*close_call.*Tools found:.*close_up"):
            build_spec_workflow(load_spec(FIXTURES[0]), tools_from_openapi(document))

    def test_noted_product_counts_as_handled(self):
        spec = load_spec(FIXTURES[1])
        nodes = self.render(1)["nodes"]
        products = json.dumps([CARD, LOAN])
        accepted = json.dumps({"1": {"product_id": "p-card", "date": "2026-10-16", "amount": 95.0}})
        variables = {
            "late_products": products, "offers_accepted": accepted, "offers_noted": "[]",
            "special_result_product_dispute": "True", "add_note_args.selected_product_number": 2,
        }
        exec(code_of(nodes["special_product_dispute_done"]), {"vars": variables})
        self.assertEqual([2], json.loads(variables["offers_noted"]))
        self.assertEqual("ready", variables["offer_progress"])
        for prefix in ("account_response", "get_account_response"):
            flattened = {
                "offers_accepted": accepted, "offers_noted": "[]",
                "special_result_product_dispute": "True", "add_note_args.selected_product_number": 2,
            }
            for index, product in enumerate((CARD, LOAN)):
                for field, value in product.items():
                    flattened[f"{prefix}.data.products.{index}.{field}"] = value
            exec(code_of(nodes["special_product_dispute_done"]), {"vars": flattened})
            self.assertEqual("ready", flattened["offer_progress"])
        # A failed note does not count; nothing accepted yet is never ready.
        variables = {"late_products": products, "offers_accepted": "{}", "offers_noted": "[]",
                     "special_result_product_dispute": "False", "add_note_args.selected_product_number": 2}
        exec(code_of(nodes["special_product_dispute_done"]), {"vars": variables})
        self.assertEqual([], json.loads(variables["offers_noted"]))
        self.assertEqual("open", variables["offer_progress"])
        for broken in ({}, {"special_result_product_dispute": "true", "add_note_args": "x"}):
            exec(code_of(nodes["special_product_dispute_done"]), {"vars": dict(broken)})
        self.assertTrue(spec.special_paths)

    def test_identity_selector_field_is_found_by_enum_not_by_name(self):
        spec = load_spec(FIXTURES[0])
        document = json.loads((ROOT / "build-the-builder-v2/tools/openapi.json").read_text(encoding="utf-8"))
        schema = document["paths"]["/verify_identity"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        schema["properties"]["question"] = schema["properties"].pop("field")
        schema["required"] = ["customer_id", "question", "answer"]
        warnings = []
        build_spec_workflow(spec, tools_from_openapi(document), warnings)
        self.assertEqual([], warnings)
        schema["properties"]["question"]["enum"] = ["something_else"]
        warnings = []
        build_spec_workflow(spec, tools_from_openapi(document), warnings)
        self.assertEqual(1, len(warnings))
        self.assertIn("not validated", warnings[0])

    def test_no_special_path_exit_depends_on_the_model(self):
        for index in range(len(FIXTURES)):
            workflow = self.render(index)
            special = {
                key: node for key, node in {**workflow["nodes"], **workflow["global_nodes"]}.items()
                if key.startswith("special_")
            }
            self.assertTrue(special)
            for key, node in special.items():
                for transition in node["transitions"]:
                    self.assertNotEqual("matches_intent", transition["condition"].get("operator"), key)
                    self.assertNotIn("is_tool_call", transition)
            for key, node in workflow["nodes"].items():
                for transition in node.get("transitions", []):
                    self.assertNotEqual("matches_intent", transition["condition"].get("operator"), key)

    def test_special_path_shapes_follow_the_tool(self):
        a = self.render(0)
        paid = a["global_nodes"]["special_already_paid"]
        self.assertTrue(paid["passthrough"])
        self.assertEqual("tts", paid["on_enter"]["type"])
        human = a["global_nodes"]["special_human"]
        self.assertEqual("tts", human["on_enter"]["type"])
        self.assertEqual("api_request", a["nodes"]["special_human_go"]["node_type"])
        b = self.render(1)
        self.assertEqual("code", b["global_nodes"]["special_product_dispute_at_negotiate"]["node_type"])
        dispute = b["nodes"]["special_product_dispute"]
        self.assertEqual(["add_note"], tool_names(dispute))
        tool = dispute["tools"][0]
        body = tool["function"]["parameters"]["properties"]["body"]
        self.assertNotIn("product_id", body["properties"])
        self.assertIn("selected_product_number", body["properties"])
        self.assertIn("pre_process_code", tool)
        self.assertEqual(0, tool["config"]["maxRetries"])
        self.assertEqual(
            [{"path": "data.ok", "variable": "special_result_product_dispute"}], tool["response_mapping"]
        )

    def test_ask_requires_close(self):
        value = json.loads(FIXTURES[1].read_text(encoding="utf-8"))
        dispute = next(item for item in value["special_paths"] if item["then"] == "return")
        dispute["ask"] = {"text": "Are you sure?", "source": "test"}
        with self.assertRaisesRegex(SpecError, "ask is supported only"):
            parse_spec(value)

    def test_account_and_closing_have_bounded_retries_and_confirm_can_revise(self):
        nodes = self.render()["nodes"]
        self.assertEqual(1, nodes["account"]["pre_actions"][0]["config"]["maxRetries"])
        self.assertEqual("closing", nodes["account"]["transitions"][0]["target_node"])
        self.assertEqual("negotiate", nodes["confirm_record"]["transitions"][0]["target_node"])
        for key, node in nodes.items():
            if node["node_type"] == "conversation":
                self.assertEqual("close_turn_limit", node["max_turn_transition"], key)

    def test_fixture_a_prompts_are_under_budget(self):
        for index in range(len(FIXTURES)):
            estimates = workflow_prompt_estimates(self.render(index))
            self.assertTrue(estimates)
            self.assertTrue(all(value <= 1500 for value in estimates.values()), estimates)
        workflow = self.render()
        estimates = workflow_prompt_estimates(workflow)
        without_identity_tool = json.loads(json.dumps(workflow))
        without_identity_tool["nodes"]["identity"]["tools"] = []
        self.assertGreater(
            estimates["identity"], workflow_prompt_estimates(without_identity_tool)["identity"]
        )

    def test_cli_print_with_spec_is_offline_and_traced(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_root = Path(directory)
            previous = Path.cwd()
            try:
                import os
                os.chdir(trace_root)
                stdout, stderr = StringIO(), StringIO()
                captured = {}
                def generate_tools(document, **kwargs):
                    captured.update(kwargs)
                    return tools_from_openapi(document, **kwargs)
                with patch("builder.build.tools_from_openapi", side_effect=generate_tools), \
                        redirect_stdout(stdout), redirect_stderr(stderr):
                    result = build.main([
                            str(ROOT / "build-the-builder-v2/briefs/brief-a.md"),
                            str(ROOT / "build-the-builder-v2/tools/openapi.json"),
                            "--spec", str(FIXTURES[0]), "--print", "--slot", "multi-step",
                        ])
                self.assertEqual(0, result)
                self.assertIn("negotiation_intent", captured["known_entry_variables"])
                self.assertIn("agreed_product_count", captured["known_entry_variables"])
                self.assertEqual("opening", json.loads(stdout.getvalue())["initial_node"])
                trace = (trace_root / "traces/multi-step.print.log").read_text(encoding="utf-8")
                self.assertIn("renderer: multi-step spec_version=1", trace)
                self.assertIn("prompt_estimate:", trace)
                self.assertIn("freya: not contacted", trace)
            finally:
                os.chdir(previous)

    def test_builder_string_literals_do_not_embed_fixture_values(self):
        def strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for child in value.values():
                    yield from strings(child)
            elif isinstance(value, list):
                for child in value:
                    yield from strings(child)

        openapi = json.loads((ROOT / "build-the-builder-v2/tools/openapi.json").read_text(encoding="utf-8"))
        # OpenAPI values (enums, required lists) are the tool contract. Field names are NOT
        # allowed wholesale: a tool field name hardcoded in builder/ would hide a build break.
        openapi_values = set(strings(openapi))
        fixture_values = set()
        for path in FIXTURES:
            fixture_values.update(strings(json.loads(path.read_text(encoding="utf-8"))))
        literal_files = {}
        for path in (ROOT / "builder").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    literal_files.setdefault(node.value, set()).add(path.name)
        allowed_fixed_tools = {
            "verify_identity", "get_account", "create_promise", "add_note",
            "schedule_callback", "transfer_to_agent", "close_call",
        }
        # Skeleton vocabulary, derived from the code that defines it.
        required_framework_terms = {
            "third_party", "identity", "negotiate", "confirm_record",
        } | set(CLOSE_STATE_NAMES) | set(OFFER_UNITS) | set(OFFER_ADJUST)
        # Call variable names are a kit contract (STARTER-KIT-FACTS), not brief data.
        allowed_fixed_tools = allowed_fixed_tools | CALL_VARIABLES
        # Common words allowed only in the files that use them for their own meaning.
        file_scoped = {
            "type": {"tools_from_openapi.py", "workflow.py"},       # JSON schema / Freya node keyword
            "default": {"spec.py", "tools_from_openapi.py", "workflow.py"},  # schema default, default row
            "close": {"spec.py", "workflow.py"},                     # special path then=close
            "return": {"spec.py", "workflow.py"},                    # special path then=return
            "failed": {"build.py", "freya.py"},                      # trace / API status words
        }
        leaked = {
            value for value in fixture_values
            if len(value) >= 4
            and value in literal_files
            and value not in openapi_values
            and value not in allowed_fixed_tools
            and value not in required_framework_terms
            and not literal_files[value] <= file_scoped.get(value, set())
        }
        self.assertEqual(set(), leaked)
        # The identity tool's selector field name must not be hardcoded (review T-005b #2).
        self.assertNotIn("workflow.py", literal_files.get("field", set()))
        workflow_source = (ROOT / "builder/workflow.py").read_text(encoding="utf-8")
        self.assertNotIn("min(len(products), 3)", workflow_source)
        workflow_tree = ast.parse(workflow_source)
        self.assertFalse(any(
            isinstance(node, ast.Constant) and type(node.value) is int and node.value == 3
            for node in ast.walk(workflow_tree)
        ))
        lowered = workflow_source.lower()
        for phrase in ("up to three", "one to three", "at most three"):
            self.assertNotIn(phrase, lowered)


if __name__ == "__main__":
    unittest.main()
