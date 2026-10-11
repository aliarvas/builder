"""T-027: v19 live runs.

PUB-07 (Brief A): "Monday the twenty sixth" was read as the next Monday (19 October): a day in
words was turned into digits only next to a month name. PUB-12 (A+B): the refusal of the car
loan was counted against the personal loan, the persuasion turn did not know its product, a
goodbye had no route, and the read-back step waited for a read-back the model never said.
The replays feed the live extractor's recorded fields to the simulator."""

from __future__ import annotations

import datetime
import json
import unittest
from pathlib import Path
from unittest import mock

from builder import goodbye, offer_check
from builder.offer_check import PRELUDE
from builder.selfcheck import (
    END_CALL, Bank, Simulator, _Plan, _play_goodbye, _promise_tool, recorded_claim_gaps, run_selfcheck,
)
from builder.spec import parse_spec
from builder.tools_from_openapi import CALL_VARIABLES
from builder.workflow import build_spec_workflow
from tests.test_selfcheck import KIT_TOOLS, NOW, SPECS, load

ROOT = Path(__file__).resolve().parents[1]
REPLAYS = ROOT / "tests/fixtures/replay"
OFFER_STEPS = ("negotiate", "offer_say", "revise_ask")


def fixture(name):
    return json.loads((REPLAYS / name).read_text(encoding="utf-8"))


def live_spec(name):
    data = fixture(name)
    return parse_spec(data.get("spec", data))


def start(spec, replay, workflow=None):
    """A simulator at the first negotiation turn of the recorded call."""
    workflow = workflow or build_spec_workflow(spec, KIT_TOOLS)
    variables = {"now": replay["now"], spec.offer.data.get("today_variable") or "now": replay["now"]}
    for name in CALL_VARIABLES:
        variables.setdefault(name, "sim-" + name)
    sim = Simulator(workflow, spec, Bank(spec, replay["products"], {}, []), variables)
    sim.rendered = workflow
    for action in _Plan(spec, replay["now"]).reach_negotiation():
        if action["kind"] == "say":
            sim.turn(dict(action["vars"]))
        else:
            sim.tool_turn(dict(action["args"]))
    return sim


def feed(sim, turn):
    """One recorded customer turn, with only the fields the waiting step extracts."""
    waiting = sim.advance()
    fields = {field["name"] for field in sim.nodes[waiting].get("extraction_schema") or []}
    sim.turn({name: value for name, value in turn["extracted"].items() if name in fields})
    sim.advance()  # the routes and code steps after the turn
    return waiting


def negotiation_turns(replay):
    first = next(index for index, turn in enumerate(replay["turns"]) if turn["node"] == "negotiate")
    return replay["turns"][first:]


def reader(today=datetime.date(2026, 10, 14), weekday_words=True):
    names = {"vars": {}}
    code = PRELUDE.replace("__CONFIG__", "{'offer': {}}").replace("__PRODUCT_READER__", "")
    if not weekday_words:
        # v19: day words only next to a month name.
        code = code.replace("WEEKDAY_NAME_PATTERN = '|'.join(name.lower() for name in WEEKDAYS)",
                            "WEEKDAY_NAME_PATTERN = 'no weekday'", 1)
    exec(code, names)
    names["today"] = lambda: today
    return names["resolve_offer_day"]


def promises(sim, spec):
    confirmation = spec.confirmation.data
    record = _promise_tool(sim.rendered, spec)
    return sorted([str(call.body.get(confirmation["promise_product_id_field"])),
                   float(call.body.get(confirmation["promise_amount_field"])),
                   str(call.body.get(confirmation["promise_date_field"]))]
                  for call in sim.bank.calls if call.tool == record and call.ok)


class Pub07Tests(unittest.TestCase):
    def test_a_weekday_with_a_day_in_words_is_that_day(self):
        read = reader()
        for phrase, day in {"Monday the twenty sixth.": "2026-10-26", "monday twenty six": "2026-10-26",
                            "Friday the twenty third of October": "2026-10-23", "Monday the 26": "2026-10-26",
                            "Monday": "2026-10-19"}.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(day, str(read(phrase)))
        # Not a day: a tens word before a unit past 31, or words with neither weekday nor month.
        self.assertEqual("2026-10-16", str(read("Friday the thirty second")))
        self.assertIsNone(read("twenty sixth"))

    def test_the_v19_reader_took_the_next_monday(self):
        self.assertTrue(PRELUDE.count("WEEKDAY_NAME_PATTERN") >= 2)
        self.assertEqual("2026-10-19", str(reader(weekday_words=False)("Monday the twenty sixth.")))

    def test_replay_the_holiday_moves_to_the_next_business_day(self):
        spec = live_spec("brief-a-live-spec.json")
        replay = fixture("pub-07-extractions.json")
        sim = start(spec, replay)
        turns = negotiation_turns(replay)
        feed(sim, turns[0])        # "the week after next": no day, the latest date is proposed
        self.assertEqual("missing", sim.vars["offer_verdict"])
        feed(sim, turns[1])        # "Monday the twenty sixth." (26 October is a holiday)
        self.assertEqual("offer_say", sim.advance())
        self.assertEqual("date_not_business_day", sim.vars["offer_verdict"])
        self.assertEqual("2026-10-27", sim.vars["offer_suggested_date"])
        # Not recorded (the live call went on differently): the customer takes the proposal.
        sim.turn({"offer_accepts_proposal": "yes"})
        self.assertEqual("confirm_record", sim.advance())
        sim.turn(turns[2]["extracted"])                     # "Yes, I confirm."
        self.assertEqual(END_CALL, sim.advance())
        self.assertEqual(replay["expected"]["promises"], promises(sim, spec))


class Pub07SelfCheckTests(unittest.TestCase):
    def test_the_spoken_date_family_has_the_weekday_form_and_catches_the_v19_reader(self):
        spec = load(SPECS["spec-brief-a.json"][0])
        tools = SPECS["spec-brief-a.json"][1]
        now = {item.scenario for item in run_selfcheck(spec, build_spec_workflow(spec, tools), NOW).results
               if not item.passed}
        self.assertNotIn("spoken_date_weekday_the_word", now)
        prelude = PRELUDE.replace("WEEKDAY_NAME_PATTERN = '|'.join(name.lower() for name in WEEKDAYS)",
                                  "WEEKDAY_NAME_PATTERN = 'no weekday'", 1)
        with mock.patch("builder.offer_check.PRELUDE", prelude):
            workflow = build_spec_workflow(spec, tools)
        failed = {item.scenario for item in run_selfcheck(spec, workflow, NOW).results if not item.passed}
        self.assertIn("spoken_date_weekday_the_word", failed)


class Pub12ReplayTests(unittest.TestCase):
    def setUp(self):
        self.spec = live_spec("brief-ab-live-spec.json")
        self.replay = fixture("pub-12-extractions.json")
        self.turns = negotiation_turns(self.replay)

    def test_a_refusal_counts_for_the_product_it_names(self):
        sim = start(self.spec, self.replay)
        for turn in self.turns[:3]:   # card tomorrow; "not the personal loan"; "not the car loan"
            feed(sim, turn)
        # v19 counted both refusals against the personal loan: {"2": 2}.
        self.assertEqual({"2": 1, "3": 1}, json.loads(sim.vars["persuasion_used_by_product"]))
        self.assertEqual({"1"}, set(json.loads(sim.vars["offers_accepted"])))
        self.assertEqual("car loan", sim.vars["offer_discussed_product"])

    def test_the_v19_refusal_step_counted_the_car_loan_for_the_personal_loan(self):
        v19 = _v19_refusal(self.spec)
        with mock.patch("builder.product_notes.product_refusal_code", lambda spec: v19):
            workflow = build_spec_workflow(self.spec, KIT_TOOLS)
        sim = start(self.spec, self.replay, workflow)
        for turn in self.turns[:3]:
            feed(sim, turn)
        self.assertEqual({"2": 2}, json.loads(sim.vars["persuasion_used_by_product"]))

    def test_the_recorded_refusals_reach_the_read_back_and_a_goodbye_ends_the_call(self):
        sim = start(self.spec, self.replay)
        steps = []
        for turn in self.turns[:6]:   # up to the last "No, I am not paying the car loan."
            steps.append(feed(sim, turn))
        # The car loan's one attempt is used up; the personal loan has had both of its attempts.
        self.assertEqual([3], json.loads(sim.vars["offers_noted"]))
        self.assertEqual({"2": 2, "3": 1}, json.loads(sim.vars["persuasion_used_by_product"]))
        # The recorded goodbye ("Thank you, goodbye." extracted as none): the global step.
        for _ in range(2):
            if sim.advance() == END_CALL:
                break
            self.assertTrue(_play_goodbye(sim, {"kind": "goodbye"}), sim.problems)
        self.assertEqual(END_CALL, sim.advance())
        self.assertEqual([], sim.problems)

    def test_same_turn_refusals_count_before_the_check(self):
        sim = start(self.spec, self.replay)
        first = dict(self.turns[0]["extracted"], offer_refused_product_name="the personal loan or the car loan")
        feed(sim, {"extracted": first})
        self.assertEqual({"2": 1, "3": 1}, json.loads(sim.vars["persuasion_used_by_product"]))
        self.assertEqual({"1"}, set(json.loads(sim.vars["offers_accepted"])))


class ReadbackTests(unittest.TestCase):
    def test_the_read_back_step_says_the_checked_offers(self):
        spec = live_spec("brief-ab-live-spec.json")
        workflow = build_spec_workflow(spec, KIT_TOOLS)
        node = workflow["nodes"]["confirm_record"]
        self.assertEqual({"type": "tts", "text": "{{readback_text}}"}, node["on_enter"])
        sim = start(spec, fixture("pub-11-extractions.json"))
        sim.turn({"offer_date": "this Friday", "offer_product_name": "all three"})
        self.assertEqual("confirm_record", sim.advance())
        self.assertEqual(
            "I can record a payment of 220 for the credit card ending 2288 on Friday, 16 October, a payment of "
            "640 for the personal loan on Friday, 16 October and a payment of 75 for the car loan on Friday, "
            "16 October. Do you confirm?", sim.vars["readback_text"])

    def test_no_step_that_sees_the_offers_may_claim_a_record(self):
        for name, (path, tools) in SPECS.items():
            with self.subTest(spec=name):
                self.assertEqual([], recorded_claim_gaps(build_spec_workflow(load(path), tools)))
        workflow = build_spec_workflow(load(SPECS["spec-brief-a.json"][0]), SPECS["spec-brief-a.json"][1])
        workflow["nodes"]["negotiate"]["task_message"] = workflow["nodes"]["negotiate"]["task_message"].replace(
            "never say a payment or promise was recorded", "")
        self.assertEqual(["negotiate"], [step for step, _ in recorded_claim_gaps(workflow)])


class SelfCheckFamilyTests(unittest.TestCase):
    def failed(self, spec, workflow):
        return {item.scenario for item in run_selfcheck(spec, workflow, NOW).results if not item.passed}

    def test_the_families_pass_on_the_multi_product_fixtures(self):
        for name in ("spec-brief-b.json", "brief-ab-extracted-v2.json"):
            spec = load(SPECS[name][0])
            failed = self.failed(spec, build_spec_workflow(spec, SPECS[name][1]))
            with self.subTest(spec=name):
                self.assertFalse({item for item in failed if item.startswith(("goodbye_", "multi_pay", "multi_refuse_named"))})

    def test_without_the_goodbye_step_the_goodbye_family_fails(self):
        spec = load(SPECS["spec-brief-b.json"][0])
        with mock.patch.object(goodbye, "add_goodbye_exit", lambda *args: None), \
                mock.patch("builder.workflow.add_goodbye_exit", lambda *args: None):
            workflow = build_spec_workflow(spec, SPECS["spec-brief-b.json"][1])
        failed = self.failed(spec, workflow)
        self.assertTrue({"goodbye_negotiate", "goodbye_at_readback"} <= failed, failed)

    def test_with_the_v19_refusal_step_the_named_refusal_fails(self):
        spec = load(SPECS["spec-brief-b.json"][0])
        v19 = _v19_refusal(spec)
        with mock.patch("builder.product_notes.product_refusal_code", lambda spec: v19):
            workflow = build_spec_workflow(spec, SPECS["spec-brief-b.json"][1])
        self.assertIn("multi_refuse_named", self.failed(spec, workflow))


def _v19_refusal(spec):
    """The refusal step before T-027: the product under discussion, whatever the words name."""
    with mock.patch("builder.offer_check.multi_product", lambda spec: False):
        return offer_check.product_refusal_code(spec)


if __name__ == "__main__":
    unittest.main()
