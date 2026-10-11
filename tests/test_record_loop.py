"""F-063: one read-back and one confirmation, then code records every accepted offer."""

from __future__ import annotations

import copy
import json
import unittest

from builder.prompts import CLOSING_FALLBACK_SAY, PROMISE_NOT_ALL_RECORDED_SAY, SPECIAL_TOOL_FAILED_SAY
from builder.spec import SpecError, parse_spec
from builder.record_loop import RECORD_NEXT, RECORD_PROMISE
from builder.workflow import RECORD_LOOP_PRODUCT_CAP, build_spec_workflow
from tests.test_multi_ready import AB_SPECS, CASES, ROOT, Session, expected_promises, holds
from tests.test_multi_step import FIXTURES, code_of, kit_tools, load_spec

LOOP = (RECORD_NEXT, RECORD_PROMISE, "confirmation_progress")


def pub11(session):
    """PUB-11 up to the read-back: all three products this Friday, one per check turn."""
    for number in (1, 2, 3):
        session.say(offer_date="this Friday", offer_product_number=number)
    return session


class RecordLoopTests(unittest.TestCase):
    def test_pub11_one_read_back_three_promises(self):
        case = CASES["PUB-11"]
        for name, path in AB_SPECS.items():
            with self.subTest(spec=name):
                session = pub11(Session(path, case))
                self.assertEqual("confirm_record", session.step)
                start = len(session.path)
                session.record_all()
                after_yes = session.path[start:]
                # One yes: confirm_record routes once, then only the code loop runs.
                self.assertEqual("confirm_record", after_yes[0])
                self.assertEqual(set(LOOP), set(after_yes[1:]))
                self.assertEqual(3, after_yes.count(RECORD_PROMISE))
                self.assertEqual(3, len(session.calls))
                self.assertEqual(expected_promises(case), session.ledger_promises())
                self.assertEqual("promise", session.close()[0])
                self.assertNotIn(PROMISE_NOT_ALL_RECORDED_SAY.text, session.vars["closing_sentence"])

    def test_a_failed_call_is_retried_once_for_that_product(self):
        session = pub11(Session(AB_SPECS["fixture-b"], CASES["PUB-11"]))
        session.record_all([True, False, True, True])
        self.assertEqual(4, len(session.calls))
        numbers = [call for call in session.calls]
        self.assertEqual(numbers[1], numbers[2])  # the retry is for the same product
        self.assertEqual(expected_promises(CASES["PUB-11"]), session.ledger_promises())
        self.assertEqual("promise", session.close()[0])

    def test_exhausted_product_is_set_aside_and_the_others_are_recorded(self):
        # F-061/F-062 review finding 1 (replaces the F-063 stop rule): p2 fails twice, the loop
        # goes on with p3; p2 gets the failed reason, no product is noted refused.
        for name in ("fixture-b", "tagged", "v2"):
            with self.subTest(spec=name):
                session = pub11(Session(AB_SPECS[name], CASES["PUB-11"]))
                session.record_all([True, False, False, True])
                self.assertEqual(["p1", "p2", "p2", "p3"], [call["product_id"] for call in session.calls])
                self.assertEqual(["p1", "p3"], sorted(promise["product_id"] for promise in session.promises))
                self.assertEqual("promise_failed", session.vars["close_state"])
                outcome, _ = session.close()
                self.assertEqual("promise", outcome)  # a recorded promise wins the outcome row
                self.assertTrue(session.vars["closing_sentence"].startswith(PROMISE_NOT_ALL_RECORDED_SAY.text))
                self.assertEqual([("p2", "service_error")], session.ledger_notes())

    def test_last_product_failing_still_ends_the_loop(self):
        session = pub11(Session(AB_SPECS["fixture-b"], CASES["PUB-11"]))
        session.record_all([True, True, False, False])
        self.assertEqual(4, len(session.calls))
        self.assertEqual("exhausted", session.vars["promise_progress_state"])
        self.assertEqual("closing", session.step)

    def test_single_promise_that_fails_twice_closes_as_the_spec_says(self):
        session = Session(ROOT / "tests/fixtures/spec-brief-a.json", CASES["PUB-01"])
        session.say(offer_date="today", offer_product_number=1)
        self.assertEqual("confirm_record", session.step)
        session.record_all([False, False])
        self.assertEqual([], session.promises)
        self.assertEqual(2, len(session.calls))
        outcome, reason = session.close()
        self.assertEqual(("no_promise", "service_error"), (outcome, reason))
        sentence = session.vars["closing_sentence"]
        self.assertNotIn(PROMISE_NOT_ALL_RECORDED_SAY.text, sentence)  # the spec's own line only
        self.assertNotIn("confirming", sentence)

    def test_revise_still_goes_to_revise_ask_and_records_the_new_date(self):
        session = pub11(Session(AB_SPECS["fixture-b"], CASES["PUB-11"]))
        confirmation = session.spec.confirmation.data
        session.say(**{confirmation["intent_variable"]: confirmation["revise_values"][0]})
        self.assertEqual("revise_ask", session.step)
        session.say(offer_date="15 October", offer_product_number=1)
        self.assertEqual("confirm_record", session.step)
        session.record_all()
        dates = {promise[0]: promise[2] for promise in session.ledger_promises()}
        self.assertEqual("2026-10-15", dates["p1"])
        self.assertEqual(3, len(session.promises))

    def test_graph_shape(self):
        for index, fixture in enumerate(FIXTURES):
            spec = load_spec(fixture)
            nodes = build_spec_workflow(spec, kit_tools(index))["nodes"]
            with self.subTest(fixture=fixture.name):
                self.assertEqual([], nodes["confirm_record"]["tools"])
                record = nodes[RECORD_PROMISE]
                self.assertEqual("api_request", record["node_type"])
                self.assertEqual({"type": "silent"}, record["on_enter"])  # F-050
                self.assertEqual(0, record["pre_actions"][0]["config"]["maxRetries"])
                for key in LOOP:
                    self.assertTrue(nodes[key]["passthrough"], key)
                    self.assertNotEqual("tts", nodes[key]["on_enter"]["type"], key)
                # The loop never returns to the read-back.
                for key in LOOP:
                    targets = {t["target_node"] for t in nodes[key]["transitions"]}
                    self.assertNotIn("confirm_record", targets, key)
                confirmation = spec.confirmation.data
                into_loop = next(t for t in nodes["confirm_record"]["transitions"] if t["target_node"] == RECORD_NEXT)
                operands = {c["operand"] for c in into_loop["condition"]["conditions"]}
                self.assertFalse(operands & set(confirmation["revise_values"]))


class ReviewFixTests(unittest.TestCase):
    def test_hook_reads_the_number_from_the_variable_not_the_template(self):
        # Review fix 1: the body field may hold the literal template text (or nothing);
        # the hook takes the product from promise_record_number itself.
        spec = load_spec(FIXTURES[1])
        nodes = build_spec_workflow(spec, kit_tools(1))["nodes"]
        tool = nodes[RECORD_PROMISE]["pre_actions"][0]
        confirmation = spec.confirmation.data
        number_field = confirmation["product_number_field"]
        accepted = {"1": {"product_id": "id-a", "date": "2026-10-16", "amount": 95.0},
                    "2": {"product_id": "id-b", "date": "2026-10-20", "amount": 150.0}}
        variables = {"offers_accepted": json.dumps(accepted), "promise_record_number": 2}
        for body_value in ("{{promise_record_number}}", None, 1):
            body = {"customer_id": "c"}
            if body_value is not None:
                body[number_field] = body_value
            config = {"body": body}
            exec(tool["pre_process_code"], {"vars": dict(variables), "config": config})
            with self.subTest(body_value=body_value):
                self.assertEqual("id-b", config["body"][confirmation["promise_product_id_field"]])
                self.assertEqual(150.0, config["body"][confirmation["promise_amount_field"]])
        # Without the variable, the body value is the fallback.
        config = {"body": {"customer_id": "c", number_field: 1}}
        exec(tool["pre_process_code"], {"vars": {"offers_accepted": json.dumps(accepted)}, "config": config})
        self.assertEqual("id-a", config["body"][confirmation["promise_product_id_field"]])

    def closing(self, data, variables):
        workflow = build_spec_workflow(parse_spec(data), kit_tools(0))
        variables = dict(variables)
        exec(code_of(workflow["nodes"]["closing"]), {"vars": variables})
        return variables

    def test_instruction_style_failure_row_still_says_the_failure(self):
        # Review fix 2: the row's sentence is an instruction, so the spoken-text fallback
        # replaced it with the generic goodbye; the builder's failure line is added.
        data = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        row = next(item for item in data["outcomes"] if item.get("reason") == "service_error")
        row["say"]["text"] = "Say you could not record the promise. Then thank the customer and say goodbye."
        row["on"] = [*row["on"], "special_tool_failed"]
        for state, line in (("promise_failed", PROMISE_NOT_ALL_RECORDED_SAY.text),
                            ("special_tool_failed", SPECIAL_TOOL_FAILED_SAY.text)):
            with self.subTest(state=state):
                result = self.closing(copy.deepcopy(data), {"close_state": state})
                self.assertEqual((row["outcome"], row["reason"]), (result["close_outcome"], result["close_reason"]))
                self.assertEqual(line + " " + CLOSING_FALLBACK_SAY.text, result["closing_sentence"])

    def test_spoken_failure_row_is_said_alone(self):
        data = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        row = next(item for item in data["outcomes"] if item.get("reason") == "service_error")
        result = self.closing(data, {"close_state": "promise_failed"})
        self.assertEqual(row["say"]["text"], result["closing_sentence"])

    def test_extracted_ab_spec_with_an_instruction_row(self):
        data = json.loads((ROOT / "tests/fixtures/extract/brief-ab-extracted.json").read_text(encoding="utf-8"))
        data = data.get("spec", data)
        result = self.closing(data, {"close_state": "promise_failed"})
        self.assertTrue(result["closing_sentence"].startswith(PROMISE_NOT_ALL_RECORDED_SAY.text))

    def test_confirm_step_says_once_that_the_program_records(self):
        # Review fix 3: spec rules may still speak of calling the promise tool.
        nodes = build_spec_workflow(load_spec(FIXTURES[0]), kit_tools(0))["nodes"]
        task = nodes["confirm_record"]["task_message"]
        self.assertEqual(1, task.count("the program does that after the yes"))
        self.assertEqual([], nodes["confirm_record"]["tools"])

    def test_spec_needs_a_record_value(self):
        # Review fix 4: a confirmation with only revise values cannot start the record loop.
        data = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        data["confirmation"]["revise_values"] = list(data["confirmation"]["intent_values"])
        with self.assertRaisesRegex(SpecError, "not in revise_values"):
            parse_spec(data)


def run_without_sandbox(nodes, start, stops, limit=200):
    """F-067: walk silent steps from ``start`` while the code sandbox is down. Code steps
    change nothing; each api step counts as a failed call on the engine's own counters and
    the bank answers not ok. Returns the step reached and the number of api calls."""
    variables, target, calls = {}, start, 0
    for _ in range(limit):
        if target in stops:
            return target, calls
        node = nodes[target]
        if node["node_type"] == "api_request":
            calls += 1
            key = target + "_failure_count"
            variables[key] = variables.get(key, 0) + 1
            for mapping in node.get("response_mapping") or []:
                variables[mapping["variable"]] = "false"
        target = next(t["target_node"] for t in node["transitions"] if holds(t["condition"], variables))
    return target, calls


class SandboxDownTests(unittest.TestCase):
    def test_record_and_close_loops_end_on_engine_counters(self):
        for index, fixture in enumerate(FIXTURES):
            spec = load_spec(fixture)
            nodes = build_spec_workflow(spec, kit_tools(index))["nodes"]
            maximum = spec.confirmation.data["max_attempts_per_product"]
            with self.subTest(fixture=fixture.name):
                step, calls = run_without_sandbox(nodes, RECORD_NEXT, {"closing"})
                self.assertEqual("closing", step)
                self.assertEqual(maximum * RECORD_LOOP_PRODUCT_CAP + 1, calls)
                step, calls = run_without_sandbox(nodes, "close_attempt", {"end_call"})
                self.assertEqual("end_call", step)
                self.assertEqual(2, calls)

    def test_the_cap_never_cuts_a_working_loop(self):
        # Every product of the largest kit case fails every attempt: the code ends the loop
        # before the engine cap does.
        session = pub11(Session(AB_SPECS[next(iter(AB_SPECS))], CASES["PUB-11"]))
        maximum = session.spec.confirmation.data["max_attempts_per_product"]
        session.record_all(answers=[False] * (3 * maximum))
        self.assertEqual("closing", session.step)
        self.assertEqual(3 * maximum, len(session.calls))
        self.assertLess(3 * maximum, maximum * RECORD_LOOP_PRODUCT_CAP)


if __name__ == "__main__":
    unittest.main()
