"""T-011: the call's outcome derived from the product notes (closing.product_notes.outcome_from_notes)."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from builder.offer_check import NOTES_OUTCOME_BODY
from builder.product_notes import NOTES_OUTCOME
from builder.selfcheck import Scenario, _Plan, play, run_selfcheck, synthetic_products
from builder.spec import SpecError, parse_spec
from builder.prompts import CLOSING_FALLBACK_SAY
from builder.workflow import build_spec_workflow, special_result_variable, speakable_spec
from tests import test_extract
from tests.test_extract import BRIEF_AB, FIXTURE_B, groups_from_spec, run
from tests.test_multi_step import kit_tools
from tests.test_selfcheck import KIT_TOOLS, NOW

ROOT = Path(__file__).resolve().parents[1]
RULE = FIXTURE_B["closing"]["product_notes"]["outcome_from_notes"]


def with_rule(name):
    """A recorded A+B extraction with the block added (it was extracted without one)."""
    data = json.loads((ROOT / "tests/fixtures/extract" / name).read_text(encoding="utf-8"))
    data = data.get("spec", data)
    data["closing"]["product_notes"]["outcome_from_notes"] = copy.deepcopy(RULE)
    return parse_spec(data)


# (spec, tools) for every A+B fixture with a note rule (brief-ab-extracted.json, the oldest
# recording, has none).
def a_plus_b():
    yield "spec-brief-b.json", parse_spec(copy.deepcopy(FIXTURE_B)), kit_tools(0)
    for name in ("brief-ab-extracted-tagged.json", "brief-ab-extracted-v2.json"):
        yield name, with_rule(name), KIT_TOOLS


def path_with_reason(spec, reason):
    notes = spec.closing.data["product_notes"]
    return next(path for path in spec.special_paths if path.then != "close" and path.tool == notes["tool"]
                and path.tool_args.get(notes["reason_field"]) == reason)


def noted_call(spec, reasons):
    """One product per reason; each is noted by the returning special path with its reason, then the
    customer refuses and the call closes. Returns the scenario."""
    plan = _Plan(spec, NOW)
    products = synthetic_products(spec, len(reasons))
    actions = [*plan.reach_negotiation()]
    for number, reason in enumerate(reasons, start=1):
        path = path_with_reason(spec, reason)
        actions.append({"kind": "special", "label": "special", "node": "special_" + path.id, "number": number,
                        "choice_variable": special_result_variable(path) + "_choice"})
    actions.append(plan.refuse())
    notes = [(f"p{number}", reason) for number, reason in enumerate(reasons, start=1)]
    return Scenario("noted_" + "_".join(reasons), actions, "negotiation:" + plan.refusal_value(), products,
                    notes=notes, step="negotiate")


def close_body(spec, sim):
    closing = spec.closing.data
    call = sim.bank.calls[-1]
    return call.body.get(closing["outcome_field"]), call.body.get(closing["reason_field"]) or ""


class DerivedOutcomeTests(unittest.TestCase):
    def play_reasons(self, reasons):
        for name, spec, tools in a_plus_b():
            with self.subTest(spec=name, reasons=reasons):
                workflow = build_spec_workflow(spec, tools)
                self.assertIn(NOTES_OUTCOME, workflow["nodes"])
                sim, failures = play(workflow, spec, noted_call(spec, reasons), NOW)
                self.assertEqual([], failures)
                yield name, spec, sim

    def test_every_product_already_paid_closes_as_paid(self):
        for _, spec, sim in self.play_reasons(["paid", "paid", "paid"]):
            self.assertEqual((RULE["all_outcome"], RULE["all_outcome_reason"]), close_body(spec, sim))
            self.assertEqual("notes:" + RULE["all_outcome"], sim.vars["close_resolved_state"])
            # The row's own sentence, as the renderer makes it speakable (F-047).
            spoken, _ = speakable_spec(spec)
            paid_row = next(item for item in spoken.outcomes
                            if (item.outcome, item.reason) == (RULE["all_outcome"], RULE["all_outcome_reason"]))
            self.assertEqual(paid_row.say.text or CLOSING_FALLBACK_SAY.text, sim.vars["closing_sentence"])
            # The special path wrote every note; the note loop adds none.
            notes = spec.closing.data["product_notes"]
            self.assertEqual(3, sum(call.tool == notes["tool"] for call in sim.bank.calls))

    def test_one_dispute_and_the_others_paid_closes_with_the_dispute(self):
        for _, spec, sim in self.play_reasons(["paid", "dispute", "paid"]):
            self.assertEqual((RULE["otherwise_outcome"], "dispute"), close_body(spec, sim))

    def test_the_first_other_note_in_account_order_wins(self):
        # p1 refused by the customer (code writes the note), p2 dispute, p3 paid: refused first.
        name, spec, tools = next(a_plus_b())
        plan = _Plan(spec, NOW)
        scenario = noted_call(spec, ["paid", "dispute", "paid"])
        refused = spec.closing.data["product_notes"]["refused_reason"]
        # Replace product 1's paid note by a refusal of product 1 first.
        scenario.actions = [*plan.reach_negotiation(), {**plan.refuse(), "repeat": False},
                            *[action for action in scenario.actions if action.get("number") in (2, 3)],
                            plan.refuse()]
        scenario.notes = [("p1", refused), ("p2", "dispute"), ("p3", "paid")]
        sim, failures = play(build_spec_workflow(spec, tools), spec, scenario, NOW)
        self.assertEqual([], failures)
        self.assertEqual((RULE["otherwise_outcome"], refused), close_body(spec, sim))

    def test_a_recorded_promise_keeps_the_promise_row(self):
        name, spec, tools = next(a_plus_b())
        report = run_selfcheck(spec, build_spec_workflow(spec, tools), NOW)
        promise = next(item for item in report.results if item.scenario == "multi_refuse_one")
        self.assertTrue(promise.passed, promise.reason)

    def test_the_risk_5_rows_are_reached(self):
        for name, spec, tools in a_plus_b():
            with self.subTest(spec=name):
                report = run_selfcheck(spec, build_spec_workflow(spec, tools), NOW)
                self.assertEqual([], [item.scenario for item in report.results if not item.passed])


class WrongBlockTests(unittest.TestCase):
    """Review T-011 #1: a valid but wrong block must not rewrite an ordinary refusal."""

    def wrong_spec(self):
        data = copy.deepcopy(FIXTURE_B)
        data["closing"]["product_notes"]["outcome_from_notes"]["all_reason"] = "refused"
        return parse_spec(data)

    def test_a_plain_refusal_still_closes_as_the_refusal_row(self):
        spec = self.wrong_spec()
        workflow = build_spec_workflow(spec, kit_tools(0))
        refusal_row = next(item for item in spec.outcomes if "negotiation:no_arrangement" in item.on)
        for count in (1, 3):
            with self.subTest(products=count):
                plan = _Plan(spec, NOW)
                products = synthetic_products(spec, count)
                actions = [*plan.reach_negotiation(), *[{**plan.refuse(), "repeat": False} for _ in range(count)]]
                notes = [(f"p{number}", "refused") for number in range(1, count + 1)]
                scenario = Scenario("wrong_all_reason", actions, "negotiation:no_arrangement", products, notes=notes)
                sim, failures = play(workflow, spec, scenario, NOW)
                self.assertEqual([], failures)
                self.assertEqual((refusal_row.outcome, refusal_row.reason), close_body(spec, sim))
                self.assertNotIn("notes:", str(sim.vars.get("close_resolved_state")))

    def test_the_self_check_expects_the_refusal_row_too(self):
        spec = self.wrong_spec()
        report = run_selfcheck(spec, build_spec_workflow(spec, kit_tools(0)), NOW)
        refusal = next(item for item in report.results if item.scenario == "refusal_no_arrangement")
        self.assertTrue(refusal.passed, refusal.reason)

    def test_a_special_note_still_derives_with_the_right_block(self):
        # The guard keeps the risk-5 case: a paid note from the special path says more.
        spec = parse_spec(copy.deepcopy(FIXTURE_B))
        sim, failures = play(build_spec_workflow(spec, kit_tools(0)), spec, noted_call(spec, ["paid"]), NOW)
        self.assertEqual([], failures)
        self.assertEqual(("paid", ""), close_body(spec, sim))


class GapWarningTests(unittest.TestCase):
    def test_a_reason_without_a_row_is_warned_at_render(self):
        # spec-brief-b has a hardship note reason but no no_promise/hardship row.
        warnings = []
        build_spec_workflow(parse_spec(copy.deepcopy(FIXTURE_B)), kit_tools(0), warnings)
        gaps = [warning for warning in warnings if warning.startswith(NOTES_OUTCOME + ":")]
        self.assertEqual(1, len(gaps), warnings)
        self.assertIn("reason hardship has no row no_promise/hardship", gaps[0])
        data = copy.deepcopy(FIXTURE_B)
        del data["closing"]["product_notes"]["outcome_from_notes"]
        warnings = []
        build_spec_workflow(parse_spec(data), kit_tools(0), warnings)
        self.assertFalse(any(warning.startswith(NOTES_OUTCOME) for warning in warnings))


class RenderTests(unittest.TestCase):
    def test_without_the_block_nothing_changes(self):
        spec = parse_spec(copy.deepcopy(FIXTURE_B))
        data = copy.deepcopy(FIXTURE_B)
        del data["closing"]["product_notes"]["outcome_from_notes"]
        # T-017: without the block, the returning paths' notes still choose the row; the T-011
        # body and its sent-reason state are not rendered. With no such path, nothing at all.
        plain = build_spec_workflow(parse_spec(data), kit_tools(0))
        self.assertIn("special_pairs", json.dumps(plain["nodes"][NOTES_OUTCOME]))
        self.assertNotIn("note_reasons_sent", json.dumps(plain))
        data["special_paths"] = [path for path in data["special_paths"] if path["then"] == "close"]
        data["outcomes"] = [row for row in data["outcomes"] if row["on"] or row["outcome"] == "transferred"]
        bare = build_spec_workflow(parse_spec(data), kit_tools(0))
        self.assertNotIn(NOTES_OUTCOME, bare["nodes"])
        text = json.dumps(bare)
        for marker in ("note_reasons_sent", "note_reasons_special", "NOTES_TABLE"):
            self.assertNotIn(marker, text)
        derived = build_spec_workflow(spec, kit_tools(0))
        self.assertIn("note_reasons_special", json.dumps(derived["nodes"]))
        self.assertIn(NOTES_OUTCOME_BODY.splitlines()[0], json.dumps(derived["nodes"][NOTES_OUTCOME]))

    def test_brief_a_renders_byte_identically(self):
        # T-011 added nothing to Brief A (no block): its render was pinned at 74eb27a. Re-pinned at
        # T-015, which changes Brief A on purpose (fixed lines, opening descriptions, customer return)
        # together with T-014's callback code; re-pinned again for the T-014 review fix (compound
        # durations in the callback code only); re-pinned at T-023 (special_topic in the choice fields,
        # the ask-first choice wording) on a tree that also holds T-022's work in progress, which moves
        # it too. A change here must be a deliberate one.
        import hashlib
        data = json.loads((ROOT / "tests/fixtures/spec-brief-a.json").read_text(encoding="utf-8"))
        workflow = build_spec_workflow(parse_spec(data), kit_tools(0))
        digest = hashlib.sha256(json.dumps(workflow, indent=1, sort_keys=True).encode("utf-8")).hexdigest()
        self.assertEqual(BRIEF_A_RENDER_SHA256, digest)

    def test_an_invalid_block_is_refused_by_the_spec(self):
        for change, text in (({"all_reason": "lost"}, "all_reason"), ({"all_outcome_reason": "lost"}, "not a row"),
                             ({"otherwise_outcome": "moved"}, "otherwise_outcome"), ({"extra": 1}, "unknown keys")):
            with self.subTest(change=change):
                data = copy.deepcopy(FIXTURE_B)
                data["closing"]["product_notes"]["outcome_from_notes"].update(change)
                with self.assertRaisesRegex(SpecError, text):
                    parse_spec(data)


# T-028/T-026: global exits, identity hook, honesty line, present-tense recording notice. T-027 on top: a
# weekday with a day in words, the code-built read-back said by confirm_record, the global goodbye step.
# T-029: the goodbye exit at every conversation step (special-topic value at the opening and third party,
# the goodbye value at the global ask steps, the customer_goodbye step). T-030 does not move it.
BRIEF_A_RENDER_SHA256 = "dde9db86b247aea886abac6b682add375219535c3863485078fd07452298432c"


class ExtractionTests(unittest.TestCase):
    def test_the_block_survives_the_round_trip(self):
        result, _, _ = run(groups_from_spec(FIXTURE_B), BRIEF_AB)
        self.assertEqual(RULE, result.spec_data["closing"]["product_notes"]["outcome_from_notes"])
        self.assertFalse(any("can never end this way" in warning for warning in result.warnings), result.warnings)

    def test_block_errors_drop_only_the_block(self):
        groups = groups_from_spec(FIXTURE_B)
        helper = test_extract.ExtractionPipelineTests()
        for change, text in (({"all_reason": "lost"}, "outcome_from_notes.all_reason"),
                             ({"all_outcome": "promise", "all_outcome_reason": "x"}, "outcome_from_notes.all_outcome"),
                             ({"otherwise_outcome": "moved"}, "outcome_from_notes.otherwise_outcome"),
                             ({"source": ""}, "outcome_from_notes.source")):
            with self.subTest(change=change):
                broken = copy.deepcopy(groups)
                rule = broken["outcomes"]["closing"]["product_notes"]["outcome_from_notes"]
                rule.update(change)
                result = helper.assertOptionalDropped(broken, "notes_outcome", text)
                notes = result.spec_data["closing"]["product_notes"]
                self.assertNotIn("outcome_from_notes", notes)  # the note rule itself stays
                self.assertEqual(FIXTURE_B["closing"]["product_notes"]["tool"], notes["tool"])


if __name__ == "__main__":
    unittest.main()
