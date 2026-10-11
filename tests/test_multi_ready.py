"""MULTI-READY: the multi-product practice cases (PUB-11/12/13) walked through the A+B render offline.

The model's part is given as an ideal extraction per customer turn (what a correct extraction
model would write). Everything else runs the generated code and the rendered transitions:
offer_setup, check_offer, the routes out of check_offer and negotiate, the create_promise
pre-hook (product id, date, amount), confirmation_progress and the closing outcome. The
ledger built here is what the bank would see from the tool bodies.

The platform rule that an invalid typed write is rejected (F-052, F-060) is applied too.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from builder.spec import parse_spec
from builder.workflow import build_spec_workflow
from builder.selfcheck import Bank, Simulator, holds as selfcheck_holds
from tests.test_offer_date_only import TOOLS, code_of

ROOT = Path(__file__).resolve().parents[1]
CASES = {case["id"]: case for case in json.loads(
    (ROOT / "build-the-builder-v2/public-test-set.json").read_text(encoding="utf-8"))}
# The tagged fixture (F-061/F-062 fields added by hand), the two A+B specs extracted live
# (T-006, F-040; the older shape) and fixture B.
AB_SPECS = {
    "tagged": ROOT / "tests/fixtures/extract/brief-ab-extracted-tagged.json",
    # Fresh live A+B extraction with the F-061/F-062 fields (AB-FRESH).
    "v2": ROOT / "tests/fixtures/extract/brief-ab-extracted-v2.json",
    "f040-b": ROOT / "traces/f040-b.spec.json",
    "t006-brief-b": ROOT / "traces/t006-brief-b.spec.json",
    # Hand-written Brief B fixture in the current spec shape (product kind and label, F-044).
    "fixture-b": ROOT / "tests/fixtures/spec-brief-b.json",
}


def load(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("spec", data)


# The simulator lives in the builder (T-010); the test session drives it from the account result.
holds = selfcheck_holds


class Session:
    """One call on the rendered A+B workflow, from the account result to the close."""

    def __init__(self, spec_path, case):
        spec = parse_spec(copy.deepcopy(load(spec_path)))
        self.spec = spec
        workflow = build_spec_workflow(spec, TOOLS)
        self.nodes = workflow["nodes"]
        self.has_kind = bool(spec.account.data.get("product_kind_field"))
        self.body_fields = {key: spec.confirmation.data[key] for key in (
            "product_number_field", "promise_product_id_field", "promise_date_field", "promise_amount_field")}
        products = [dict(product, product_id="p" + str(index))
                    for index, product in enumerate(case["products"], start=1)]
        variables = dict(case["variables"], customer_id="c-1")
        variables[spec.account.data["products_variable"]] = json.dumps(products)
        self.bank = Bank(spec, products)
        self.sim = Simulator(workflow, spec, self.bank, variables)
        self.vars, self.rejected, self.fields = self.sim.vars, self.sim.rejected, self.sim.fields
        self.promises, self.path, self.calls = [], [], []
        self.notes, self.note_calls = [], []
        self.run_code("offer_setup")
        self.step = self.route("offer_setup")

    def run_code(self, key):
        """A code step, with the platform rule for typed writes (``Simulator.run_code``)."""
        self.sim.run_code(key)
        assert not self.sim.problems, self.sim.problems

    def route(self, key):
        self.path.append(key)
        for transition in self.nodes[key]["transitions"]:
            if holds(transition["condition"], self.vars):
                return transition["target_node"]
        return key

    def say(self, **extracted):
        """A customer turn on a conversation step: the extraction writes, the step routes."""
        assert self.nodes[self.step]["node_type"] == "conversation", self.step
        self.vars.update(extracted)
        target = self.route(self.step)
        while target in self.nodes and self.nodes[target]["node_type"] == "code" and target not in (
                "closing",):
            self.run_code(target)
            target = self.route(target)
        self.step = target
        return self

    def record_all(self, answers=()):
        """confirm_record: one clear yes to the one read-back; then code records (F-063). The
        record loop runs code steps and the silent create_promise api step until closing;
        ``answers`` are the bank's ok values in call order (ok once they run out)."""
        assert self.step == "confirm_record", self.step
        confirmation = self.spec.confirmation.data
        record = next(v for v in confirmation["intent_values"] if v not in confirmation["revise_values"])
        self.vars[confirmation["intent_variable"]] = record
        target = self.route("confirm_record")
        self.read_backs = 1
        answers = list(answers)
        for _ in range(50):
            if target == "closing":
                break
            node = self.nodes[target]
            if node["node_type"] == "code":
                self.run_code(target)
            else:
                ok = answers.pop(0) if answers else True
                body = self.run_api(target, ok)
                if ok:
                    self.promises.append(body)
                self.calls.append(body)
            target = self.route(target)
        self.step = target
        return self

    def run_api(self, key, ok):
        """A silent passthrough api step: the body from its defaults and pre-hook; ``ok`` is
        the bank's answer, written where the step maps data.ok (``Simulator.run_api``)."""
        node = self.nodes[key]
        assert node["node_type"] == "api_request" and node["on_enter"] == {"type": "silent"}, key
        assert node.get("passthrough"), key
        self.bank.answers[node["pre_actions"][0]["function"]["name"]] = [ok]
        self.sim.run_api(key)
        return dict(self.bank.calls[-1].body)

    def close(self, note_answers=()):
        """The closing outcome, then the note loop (F-061) until the goodbye step."""
        assert self.step == "closing", self.step
        self.run_code("closing")
        target = self.route("closing")
        answers = list(note_answers)
        for _ in range(50):
            if target == "closing_say":
                break
            if self.nodes[target]["node_type"] == "code":
                self.run_code(target)
            else:
                ok = answers.pop(0) if answers else True
                body = self.run_api(target, ok)
                self.note_calls.append(body)
                if ok:
                    self.notes.append(body)
            target = self.route(target)
        self.step = target
        return self.vars.get("close_outcome"), self.vars.get("close_reason")

    def ledger_notes(self):
        return sorted((note["product_id"], note["reason"]) for note in self.notes)

    def refusal(self):
        """The spec's "refusal, attempts used up" intent as {variable: value}: the first
        intent that closes the call when no offer was accepted."""
        closing = next(t for t in self.nodes["negotiate"]["transitions"] if t["target_node"] == "closing")
        intent = closing["condition"]["conditions"][0]["conditions"][0]
        return {intent["variable"]: intent["operand"]}

    def end_product(self, refusal=None, limit=5):
        """Refuse the product being discussed until code ends it: with persuasion attempts in
        the spec, each refusal uses one attempt while attempts are left (AB-FRESH risk 1)."""
        refusal = refusal or self.refusal()
        for _ in range(limit):
            self.say(**refusal)
            if self.step != "negotiate":
                break
        return self

    def named(self, kind_words, ordinal):
        """How the bank line names a product: by kind when the spec has the kind field (F-044)."""
        return kind_words if self.has_kind else "the " + ordinal + " product"

    def ledger_promises(self):
        fields = self.body_fields
        return sorted((p[fields["promise_product_id_field"]], float(p[fields["promise_amount_field"]]),
                       p[fields["promise_date_field"]]) for p in self.promises)


def expected_promises(case):
    return sorted((p["product_id"], float(p["amount"]), p["date"]) for p in case["expected"]["promises"])


class MultiProductCaseTests(unittest.TestCase):
    def assertLedger(self, session, case):
        self.assertEqual(expected_promises(case), session.ledger_promises())
        outcome, reason = session.close()
        self.assertEqual(case["expected"]["outcome"], outcome)
        self.assertEqual([], session.rejected)

    def test_pub11_three_products_one_date(self):
        # "Cannot pay today. Agrees to pay all three this Friday. Confirms once."
        case = CASES["PUB-11"]
        for name, path in AB_SPECS.items():
            with self.subTest(spec=name):
                session = Session(path, case)
                self.assertEqual("negotiate", session.step)
                # The check takes one product per turn; "all three this Friday" is checked as
                # product 1 first, then the bank line asks for the next product each time.
                session.say(offer_date="this Friday", offer_product_number=1)
                self.assertEqual("offer_say", session.step)
                self.assertIn(session.named("personal loan", "second"), session.vars["offer_message"])
                session.say(offer_date="this Friday", offer_product_number=2)
                self.assertIn(session.named("car loan", "third"), session.vars["offer_message"])
                session.say(offer_date="this Friday", offer_product_number=3)
                self.assertEqual("confirm_record", session.step)
                # One read-back for all three, then one promise per product.
                self.assertEqual(3, session.vars["offers_summary"].count("[product number"))
                session.record_all()
                self.assertLedger(session, case)

    def test_pub11_one_turn_for_all_three(self):
        # T-025 (was a risk record): an empty product number is the product under discussion,
        # and "all three" names every product, so one turn checks all three.
        session = Session(AB_SPECS["tagged"], CASES["PUB-11"])
        session.say(offer_date="this Friday")
        self.assertEqual("ok", session.vars["offer_verdict"])
        self.assertEqual(1, session.vars["offers_accepted_count"])
        self.assertEqual("offer_say", session.step)
        whole = Session(AB_SPECS["tagged"], CASES["PUB-11"])
        whole.say(offer_date="this Friday", offer_product_name="all three")
        self.assertEqual(3, whole.vars["offers_accepted_count"])
        self.assertEqual("confirm_record", whole.step)

    def test_pub13_one_date_after_the_loan_deadline(self):
        # "Wants to pay both on 30 October. Accepts when told the loan has an earlier latest date."
        case = CASES["PUB-13"]
        for name, path in AB_SPECS.items():
            with self.subTest(spec=name):
                session = Session(path, case)
                session.say(offer_date="30 October", offer_product_number=1)
                self.assertEqual("ok", session.vars["offer_verdict"])
                session.say(offer_date="30 October", offer_product_number=2)
                self.assertEqual("date_too_late", session.vars["offer_verdict"])
                self.assertIn("Friday, 23 October", session.vars["offer_message"])
                self.assertEqual("offer_say", session.step)
                # "Yes, that works": the date the check proposed, without naming it.
                session.say(offer_date="", offer_accepts_proposal="yes", offer_product_number=2)
                self.assertEqual("confirm_record", session.step)
                summary = session.vars["offers_summary"]
                self.assertIn("Friday, 30 October", summary)  # the read-back names both dates
                self.assertIn("Friday, 23 October", summary)
                session.record_all()
                self.assertLedger(session, case)

    def test_pub12_promise_then_refusals_reach_the_promise_and_outcome(self):
        # The card tomorrow; the loan and the car loan are refused flatly. On every spec the
        # promise and the outcome are reached (the refusals route differently, see below).
        case = CASES["PUB-12"]
        for name, path in AB_SPECS.items():
            with self.subTest(spec=name):
                session = Session(path, case)
                session.say(offer_date="tomorrow", offer_product_number=1)
                self.assertEqual("ok", session.vars["offer_verdict"])
                self.assertEqual("offer_say", session.step)
                for _ in range(6):  # refusals until the read-back
                    if session.step == "confirm_record":
                        break
                    session.say(**session.refusal())
                self.assertEqual("confirm_record", session.step)
                session.record_all()
                self.assertEqual(expected_promises(case), session.ledger_promises())
                self.assertEqual("promise", session.close()[0])

    def test_pub12_refused_products_are_noted(self):
        # F-061/F-062 (was the MULTI-READY gap): each refused product is closed in code and
        # gets add_note(refused) before the goodbye; the ledger matches the case.
        case = CASES["PUB-12"]
        for name in ("tagged", "v2", "fixture-b"):
            with self.subTest(spec=name):
                session = Session(AB_SPECS[name], case)
                session.say(offer_date="tomorrow", offer_product_number=1)
                session.end_product()  # the loan: refused until its attempts are used up
                self.assertEqual("offer_say", session.step)
                self.assertIn(session.named("car loan", "third"), session.vars["offer_message"])
                session.end_product()  # the car loan
                self.assertEqual("confirm_record", session.step)
                session.record_all()
                self.assertEqual("promise", session.close()[0])
                self.assertEqual(expected_promises(case), session.ledger_promises())
                expected_notes = sorted((note["product_id"], note["reason"]) for note in case["expected"]["notes"])
                self.assertEqual(expected_notes, session.ledger_notes())
                self.assertEqual("closing_say", session.step)
                self.assertEqual([], session.rejected)

    def test_pub12_persuasion_attempts_are_counted_per_product_band(self):
        # Check "two attempts on the personal loan (late band), one on the car loan (early band)":
        # the tagged and the fresh spec give the attempts per band; code counts the refusals.
        for name in ("tagged", "v2"):
            with self.subTest(spec=name):
                session = Session(AB_SPECS[name], CASES["PUB-12"])
                negotiation = session.spec.negotiation.data
                attempt = {negotiation["intent_variable"]: negotiation["attempt_values"][0]}
                session.say(offer_date="tomorrow", offer_product_number=1)
                steps = []
                for _ in range(5):
                    session.say(**attempt)
                    steps.append((session.step, session.vars["persuasion_attempt"]))
                    if session.step == "confirm_record":
                        break
                self.assertEqual([
                    ("negotiate", 1), ("negotiate", 2),   # the loan: two persuasion attempts
                    ("offer_say", 0),                     # used up: the car loan starts at attempt 0
                    ("negotiate", 1),                     # the car loan: one attempt
                    ("confirm_record", 1),                # used up; the card's offer is read back
                ], steps)
                self.assertEqual("none", session.vars[negotiation["intent_variable"]])
                self.assertEqual({"2": "refused", "3": "refused"}, json.loads(session.vars["product_note_reasons"]))

    def test_an_end_value_with_attempts_left_uses_an_attempt(self):
        # AB-FRESH risk 1: the model writes the "product ends" value on the first no; code
        # still makes the persuasion attempts of the band (the loan: 2, the car loan: 1).
        for name in ("tagged", "v2"):
            with self.subTest(spec=name):
                session = Session(AB_SPECS[name], CASES["PUB-12"])
                negotiation = session.spec.negotiation.data
                end = {negotiation["intent_variable"]: negotiation["product_end_values"][0]}
                session.say(offer_date="tomorrow", offer_product_number=1)
                steps = []
                for _ in range(5):
                    session.say(**end)
                    steps.append((session.step, session.vars["persuasion_attempt"]))
                    if session.step == "confirm_record":
                        break
                self.assertEqual([("negotiate", 1), ("negotiate", 2), ("offer_say", 0),
                                  ("negotiate", 1), ("confirm_record", 1)], steps)
                self.assertEqual({"2": "refused", "3": "refused"}, json.loads(session.vars["product_note_reasons"]))

    def test_without_persuasion_attempts_an_end_value_ends_the_product_at_once(self):
        session = Session(AB_SPECS["fixture-b"], CASES["PUB-12"])
        session.say(offer_date="tomorrow", offer_product_number=1)
        session.say(**session.refusal())
        self.assertEqual("offer_say", session.step)
        self.assertEqual({"2": "refused"}, json.loads(session.vars["product_note_reasons"]))

    def test_old_specs_without_the_new_fields_keep_the_old_routes(self):
        # Live A+B specs extracted before F-061/F-062: the refusal still goes to the read-back
        # and no note step exists. A fresh extraction is needed for the new behaviour.
        for name in ("f040-b", "t006-brief-b"):
            with self.subTest(spec=name):
                session = Session(AB_SPECS[name], CASES["PUB-12"])
                self.assertNotIn("note_next", session.nodes)
                self.assertNotIn("product_refusal", session.nodes)
                session.say(offer_date="tomorrow", offer_product_number=1)
                session.say(**session.refusal())
                self.assertEqual("confirm_record", session.step)

    def test_promise_hook_with_a_number_that_was_not_accepted(self):
        # Risk record (MULTI-READY finding 4): with several accepted offers, a product number the
        # model invents is not filled from the checked offers; the body has no id, date or amount,
        # so the bank refuses it and confirmation_progress retries. Nothing wrong is recorded.
        session = Session(AB_SPECS["fixture-b"], CASES["PUB-13"])
        session.say(offer_date="30 October", offer_product_number=1)
        session.say(offer_date="23 October", offer_product_number=2)
        self.assertEqual("confirm_record", session.step)
        tool = session.nodes["record_promise"]["pre_actions"][0]
        number_field = session.body_fields["product_number_field"]
        config = {"body": {"customer_id": "c-1", number_field: 7}}
        exec(tool["pre_process_code"], {"vars": session.vars, "config": config})
        self.assertNotIn(session.body_fields["promise_product_id_field"], config["body"])
        self.assertNotIn(session.body_fields["promise_amount_field"], config["body"])


if __name__ == "__main__":
    unittest.main()
