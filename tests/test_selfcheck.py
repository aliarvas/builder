"""T-010: the builder's offline self-check (``builder/selfcheck.py``) and its repair loop."""

from __future__ import annotations

import copy
import datetime
import io
import json
import os
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from builder import build
from builder.extract import extract_spec
from builder.selfcheck import BUILDER, SPEC, check_nows, play, run_selfcheck, scenarios
from builder.selfcheck_calendar import SpecCalendar
from builder.spec import parse_spec
from builder.tools_from_openapi import tools_from_openapi
from builder.workflow import build_spec_workflow
from tests.extract_helpers import FakeClient, as_text
from tests.test_extract import BRIEF_A, OPENAPI, OutcomeReachTests, all_covered
from tests.test_multi_step import kit_tools
from tests.test_submission_check import SubmissionCheckTests
from tools.submission_check import check_submission

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-10-14T11:00"
KIT_TOOLS = tools_from_openapi(OPENAPI)
# Every fixture spec and recorded extraction, with the tools it is rendered with.
SPECS = {
    "spec-brief-a.json": (ROOT / "tests/fixtures/spec-brief-a.json", kit_tools(0)),
    "spec-brief-b.json": (ROOT / "tests/fixtures/spec-brief-b.json", kit_tools(0)),
    "spec-synthetic.json": (ROOT / "tests/fixtures/spec-synthetic.json", kit_tools(2)),
    **{path.name: (path, KIT_TOOLS) for path in sorted((ROOT / "tests/fixtures/extract").glob("*.json"))
       if path.name != "brief-a-replies.json"},
}
A_PLUS_B = ("spec-brief-b.json", "brief-ab-extracted.json", "brief-ab-extracted-tagged.json", "brief-ab-extracted-v2.json")
# Known gaps (listed in tasks/T-010-report.md):
# - Brief B "paid" and "dispute" rows are named only by a returning per-product path; the closing
#   does not derive the call's outcome from the notes (AB-FRESH risk 5, open).
# - The REPRO 13:00 extraction has no path for a declined hardship offer (F-065).
KNOWN = {
    **{name: {f"reach_outcomes[{index}]" for index in indexes} for name, indexes in (
        ("spec-brief-b.json", (1, 3)), ("brief-ab-extracted.json", (1, 7)),
        ("brief-ab-extracted-tagged.json", (1, 7)), ("brief-ab-extracted-v2.json", (1, 7)))},
    "brief-a-repro-1300.json": {"reach_outcomes[6]"},
}


def load(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return parse_spec(copy.deepcopy(data.get("spec", data)))


def check(name):
    path, tools = SPECS[name]
    spec = load(path)
    workflow = build_spec_workflow(spec, tools)
    return spec, workflow, run_selfcheck(spec, workflow, NOW)


class FixtureTests(unittest.TestCase):
    def test_every_fixture_passes_except_the_known_gaps(self):
        for name in SPECS:
            with self.subTest(spec=name):
                _, _, report = check(name)
                failed = {item.scenario: item.reason for item in report.results if not item.passed}
                self.assertEqual(KNOWN.get(name, set()), set(failed), failed)
                self.assertGreaterEqual(len(report.results), 14)

    def test_known_gaps_are_classified(self):
        _, _, report = check("brief-a-repro-1300.json")
        [problem] = report.spec_problems
        self.assertEqual("outcomes[6]", problem.path)
        self.assertIn("no_promise/hardship", problem.reason)
        _, _, report = check("brief-ab-extracted-v2.json")
        self.assertEqual([], report.spec_problems)  # risk 5 is not sent to repair
        self.assertTrue(all(item.kind == BUILDER for item in report.builder_problems))

    def test_scenarios_cover_the_required_families(self):
        ids = {scenario.id for scenario in scenarios(load(SPECS["brief-ab-extracted-v2.json"][0]), NOW)}
        for wanted in ("identity_failed", "promise", "record_failed", "offer_not_business_day", "offer_after_deadline",
                       "offer_below_floor", "offer_over_full", "offer_limit", "callback_booked", "callback_outside",
                       "special_hardship_support", "special_hardship_support_tool_failed", "special_dispute",
                       "multi_accept_all", "multi_refuse_one", "multi_record_failure"):
            self.assertIn(wanted, ids)
        self.assertTrue(any(name.startswith("third_party_") for name in ids))
        self.assertTrue(any(name.startswith("refusal_") for name in ids))

    def test_persuasion_attempts_are_checked_per_band(self):
        spec = load(SPECS["brief-ab-extracted-v2.json"][0])
        refusal = next(item for item in scenarios(spec, NOW) if item.id == "refusal_refuses_after_attempts")
        # The first synthetic product is in the early band: one attempt, then the product ends.
        self.assertEqual({"refuse": 2}, refusal.repeats)

    def test_a_b_runs_in_under_ten_seconds(self):
        started = time.monotonic()
        for name in A_PLUS_B:
            check(name)
        self.assertLess(time.monotonic() - started, 10)


class MutationTests(unittest.TestCase):
    """A broken workflow is caught (builder problems, no repair)."""

    def run_mutated(self, change):
        spec = load(SPECS["spec-brief-a.json"][0])
        workflow = build_spec_workflow(spec, kit_tools(0))
        change(workflow)
        return run_selfcheck(spec, workflow, NOW)

    def test_a_broken_route_is_caught(self):
        def break_route(workflow):
            for transition in workflow["nodes"]["check_offer"]["transitions"]:
                if transition["target_node"] == "confirm_record":
                    transition["target_node"] = "offer_say"
        report = self.run_mutated(break_route)
        failed = {item.scenario for item in report.builder_problems}
        self.assertIn("promise", failed)
        self.assertEqual([], report.spec_problems)

    def test_a_missing_tool_is_caught(self):
        report = self.run_mutated(lambda workflow: workflow["nodes"]["identity"].update(tools=[]))
        reasons = " ".join(item.reason for item in report.builder_problems)
        self.assertIn("identity has no tool for the model to call", reasons)

    def test_a_missing_close_call_is_caught(self):
        def drop_close(workflow):
            workflow["nodes"]["close_record"]["pre_actions"] = []
        report = self.run_mutated(drop_close)
        self.assertTrue(all("api step close_record has no tool" in item.reason for item in report.builder_problems))
        self.assertEqual(len(report.results), len(report.builder_problems))

    def test_a_code_step_that_raises_is_caught(self):
        def break_code(workflow):
            properties = workflow["nodes"]["closing"]["pre_actions"][0]["function"]["parameters"]["properties"]
            properties["code"]["default"] = "raise ValueError('broken')\n"
        report = self.run_mutated(break_code)
        self.assertTrue(any("code step closing raised ValueError" in item.reason for item in report.builder_problems))

    def test_two_spoken_messages_in_the_closing_turn_are_caught(self):
        def speak_twice(workflow):
            workflow["nodes"]["close_attempt"]["on_enter"] = {"type": "tts", "text": "Bye."}
        report = self.run_mutated(speak_twice)
        self.assertTrue(any("2 spoken messages in the closing turn" in item.reason for item in report.builder_problems))

    def test_a_field_the_step_cannot_extract_is_caught(self):
        # Review T-010 #1: ideal extraction writes only fields the waiting step declares.
        spec = load(SPECS["spec-brief-a.json"][0])
        variable = spec.negotiation.data["intent_variable"]

        def drop_field(workflow):
            for node in workflow["nodes"].values():
                if node.get("extraction_schema"):
                    node["extraction_schema"] = [f for f in node["extraction_schema"] if f["name"] != variable]
        report = self.run_mutated(drop_field)
        refusals = [item for item in report.builder_problems if item.scenario.startswith("refusal_")]
        self.assertTrue(refusals)
        self.assertIn(f"negotiate cannot extract {variable}=", refusals[0].reason)

    def test_a_value_outside_the_step_enum_is_caught(self):
        spec = load(SPECS["spec-brief-a.json"][0])
        variable = spec.opening.data["who_answered_variable"]
        value = spec.opening.data["close_values"][0]

        def shrink(workflow):
            for field in workflow["nodes"]["opening"]["extraction_schema"]:
                if field["name"] == variable:
                    field["enum_values"] = [v for v in field["enum_values"] if v != value]
        report = self.run_mutated(shrink)
        failed = {item.scenario: item for item in report.results if not item.passed}
        self.assertEqual(BUILDER, failed[f"opening_{value}"].kind)  # the step, not the spec, is wrong
        self.assertIn(f"opening cannot extract {variable}={value!r}", failed[f"opening_{value}"].reason)

    def test_a_routed_spec_value_without_a_route_is_a_spec_problem(self):
        # Review T-010 #4: the step takes the spec's value but no transition handles it.
        spec = load(SPECS["spec-brief-a.json"][0])
        value = spec.opening.data["close_values"][0]

        def drop_route(workflow):
            transitions = workflow["nodes"]["opening"]["transitions"]
            workflow["nodes"]["opening"]["transitions"] = [
                t for t in transitions if value not in json.dumps(t["condition"])]
        report = self.run_mutated(drop_route)
        [problem] = [item for item in report.spec_problems if item.scenario == f"opening_{value}"]
        self.assertEqual("opening.close_values[0]", problem.path)
        self.assertIn("dead end at opening", problem.reason)
        self.assertEqual("opening.close_values[0]", report.repair_messages()[0][0])

    def test_an_import_the_platform_does_not_allow_is_caught(self):
        def import_os(workflow):
            properties = workflow["nodes"]["closing"]["pre_actions"][0]["function"]["parameters"]["properties"]
            properties["code"]["default"] = "import os\nimport json, re, datetime\n" + properties["code"]["default"]
        report = self.run_mutated(import_os)
        reasons = " ".join(item.reason for item in report.builder_problems)
        self.assertIn("code step closing imports os", reasons)
        self.assertNotIn("imports json", reasons)

    def test_two_transitions_to_one_target_are_caught(self):
        def duplicate(workflow):
            transitions = workflow["nodes"]["check_offer"]["transitions"]
            transitions.append({**transitions[0], "condition": {"operator": "always"}})
        report = self.run_mutated(duplicate)
        reasons = " ".join(item.reason for item in report.builder_problems)
        self.assertIn("step check_offer has more than one transition to", reasons)

    def test_a_wrong_ledger_is_caught(self):
        spec = load(SPECS["spec-brief-a.json"][0])
        workflow = build_spec_workflow(spec, kit_tools(0))
        promise = next(item for item in scenarios(spec, NOW) if item.id == "promise")
        promise.promises = [(promise.promises[0][0], 1.0, promise.promises[0][2])]
        _, failures = play(workflow, spec, promise, NOW)
        self.assertTrue(any(failure.startswith("promises ") for failure in failures), failures)


def calendar_spec(mode, holidays=()):
    return {"offer": {"holidays": list(holidays), "non_business_weekdays": [6, 7],
                      "latest": [{"days": 3, "unit": "calendar"}], "latest_on_non_business_day": mode}}


class CalendarTests(unittest.TestCase):
    """Review T-010 #2: a calendar-day deadline on a non-business day, for each mode."""

    def test_deadline_on_a_weekend(self):
        # Wednesday 14 October + 3 calendar days = Saturday 17 October.
        for mode, day in (("previous", "2026-10-16"), ("next", "2026-10-19"), ("keep", "2026-10-17")):
            with self.subTest(mode=mode):
                self.assertEqual(day, SpecCalendar(calendar_spec(mode), NOW).deadline({}).isoformat())

    def test_deadline_on_a_holiday(self):
        # Monday 12 October + 3 = Thursday 15 October, a holiday; the 16th is a Friday.
        for mode, day in (("previous", "2026-10-14"), ("next", "2026-10-16"), ("keep", "2026-10-15")):
            with self.subTest(mode=mode):
                calendar = SpecCalendar(calendar_spec(mode, ["2026-10-15"]), "2026-10-12T11:00")
                self.assertEqual(day, calendar.deadline({}).isoformat())

    def test_next_mode_spec_passes_when_the_deadline_is_a_sunday(self):
        # The reviewer's probe: spec-synthetic (20 calendar days, next) on 26 October.
        path, tools = SPECS["spec-synthetic.json"]
        spec = load(path)
        report = run_selfcheck(spec, build_spec_workflow(spec, tools), "2026-10-26T11:00")
        self.assertEqual([], [item.scenario for item in report.results if not item.passed])

    def test_the_build_also_plays_a_friday_and_a_holiday_eve(self):
        spec = load(SPECS["spec-brief-a.json"][0])
        nows = check_nows(spec, NOW)
        calendar = SpecCalendar(spec, NOW)
        self.assertEqual(NOW, nows[0])
        self.assertEqual(3, len(nows))
        friday = SpecCalendar(spec, nows[1]).today
        self.assertTrue(calendar.is_business(friday))
        self.assertFalse(calendar.is_business(friday + datetime.timedelta(days=1)))
        eve = SpecCalendar(spec, nows[2]).today
        self.assertTrue(any(day > eve and (day - eve).days <= 4 for day in calendar.holidays))
        report = run_selfcheck(spec, build_spec_workflow(spec, kit_tools(0)))
        summary = dict(report.trace_lines())["self_check_summary"]
        self.assertIn(" now=", summary)
        self.assertIn(" extra_nows=", summary)
        self.assertEqual([], [item.scenario for item in report.results if not item.passed])


class RepairLoopTests(unittest.TestCase):
    """A spec problem goes back to extraction; the build never stops for it."""

    def groups(self):
        return OutcomeReachTests().groups_1300()

    def run_extraction(self, outcomes, deadline=None):
        groups = self.groups()
        replies = {name: [as_text(value)] for name, value in groups.items()}
        replies["coverage"] = [as_text(all_covered(BRIEF_A))]
        replies["outcomes"] = outcomes
        client = FakeClient(replies)
        logs = []
        result = extract_spec(BRIEF_A, OPENAPI, client, log=lambda key, value: logs.append((key, str(value))),
                              self_check=lambda spec: build._self_check_problems(spec, OPENAPI), deadline=deadline)
        return result, client, logs

    def repaired_outcomes(self):
        outcomes = copy.deepcopy(self.groups()["outcomes"])
        outcomes["special_paths"].append({
            "id": "hardship_declined",
            "when": {"text": "The customer who mentioned hardship declines the connection to the customer support team.",
                     "source": "If they decline, close as `no_promise` / `hardship`."},
            "say": {"text": "Thank you for your time. Goodbye.",
                    "source": "Thank the customer and say goodbye before `close_call`."},
            "tool": "", "tool_args": {}, "outcome": "no_promise", "reason": "hardship",
            "available_in": ["negotiate", "confirm_record"], "then": "close",
        })
        return outcomes

    def test_the_1300_spec_goes_to_a_self_check_repair_that_fixes_it(self):
        # The extraction check sends it back twice and lets it through in the last round (a
        # warning); the self-check then finds the unreachable row and repairs it.
        broken = as_text(self.groups()["outcomes"])
        result, client, logs = self.run_extraction([broken, broken, broken, as_text(self.repaired_outcomes())])
        self.assertIn("selfcheck1:outcomes", client.purposes())
        repair = next(messages for purpose, messages in client.calls if purpose == "selfcheck1:outcomes")
        self.assertIn("self-check scenario 'reach_outcomes[6]' (step closing)", repair[-1]["content"])
        self.assertIn(("self_check_repair", "round=1 groups=outcomes problems=1"), logs)
        self.assertIn(("self_check_repair", "round=1 accepted warnings=1->0 problems=1->0"), logs)
        self.assertIn("hardship_declined", [path.id for path in result.spec.special_paths])
        self.assertNotIn("selfcheck2:outcomes", client.purposes())

    def test_still_failing_after_two_rounds_ships_with_the_problem(self):
        broken = as_text(self.groups()["outcomes"])
        result, client, logs = self.run_extraction([broken])
        self.assertIn("selfcheck2:outcomes", client.purposes())
        self.assertNotIn("selfcheck3:outcomes", client.purposes())
        self.assertNotIn("hardship_declined", [path.id for path in result.spec.special_paths])

    def test_a_repair_that_breaks_other_checks_is_dropped(self):
        broken = self.groups()["outcomes"]
        worse = copy.deepcopy(broken)
        worse["special_paths"][0]["tool_args"] = {"queue": "nobody"}
        worse["special_paths"][0]["tool"] = "transfer_to_agent"
        result, client, logs = self.run_extraction([as_text(broken)] * 3 + [as_text(worse)])
        self.assertTrue(any(key == "self_check_repair" and "rejected" in value for key, value in logs), logs)
        self.assertEqual("", result.spec.special_paths[0].tool)  # the previous spec is kept

    def test_a_repair_that_adds_a_warning_is_dropped(self):
        # Review T-010 #3: the last round's checks are soft; a new unreachable row would only be
        # a warning there, so the repair is compared with the spec it replaces.
        # It fixes the row but its goodbye is an instruction (soft in the last round): the
        # warning count stays 1, yet the warning is new.
        worse = self.repaired_outcomes()
        worse["special_paths"][-1]["say"]["text"] = "Thank the customer and say goodbye before `close_call`."
        broken = as_text(self.groups()["outcomes"])
        result, client, logs = self.run_extraction([broken, broken, broken, as_text(worse)])
        rejected = [value for key, value in logs if key == "self_check_repair" and "rejected" in value]
        self.assertTrue(rejected, logs)
        self.assertIn("adds a warning at special_paths[8].say", rejected[0])
        self.assertIn("warnings=1->1 problems=1->0", rejected[0])
        self.assertNotIn("hardship_declined", [path.id for path in result.spec.special_paths])

    def test_a_repair_that_adds_a_self_check_problem_is_dropped(self):
        groups = self.groups()
        replies = {name: [as_text(value)] for name, value in groups.items()}
        replies["coverage"] = [as_text(all_covered(BRIEF_A))]
        replies["outcomes"] = [as_text(groups["outcomes"])] * 3 + [as_text(self.repaired_outcomes())]
        answers = [[("outcomes[6]", "row")], [("outcomes[6]", "row"), ("negotiation.close_values[0]", "dead end")]]
        logs = []
        result = extract_spec(BRIEF_A, OPENAPI, FakeClient(replies), log=lambda key, value: logs.append((key, str(value))),
                              self_check=lambda spec: answers.pop(0) if answers else [])
        rejected = [value for key, value in logs if key == "self_check_repair" and "rejected" in value]
        self.assertEqual(1, len(rejected), logs)
        self.assertIn("adds self-check problem(s) at negotiation.close_values[0]", rejected[0])
        self.assertIn("problems=1->2", rejected[0])
        self.assertNotIn("hardship_declined", [path.id for path in result.spec.special_paths])

    def test_the_time_guard_skips_the_repair(self):
        broken = as_text(self.groups()["outcomes"])
        _, client, logs = self.run_extraction([broken], deadline=time.monotonic() - 1)
        self.assertNotIn("selfcheck1:outcomes", client.purposes())
        self.assertTrue(any(key == "self_check_repair" and "time guard" in value for key, value in logs))


    def test_the_time_guard_counts_the_slowest_round(self):
        # Review T-010 #6: a fake clock where every reading is one minute later, so each normal
        # repair round "takes" 60 s; at the guard (240 s) a round would end at 300 s > 270 s.
        import builder.extract as extract_module

        class Clock:
            value = -60

            def monotonic(self):
                self.value += 60
                return self.value
        broken = as_text(self.groups()["outcomes"])
        real = extract_module.time
        extract_module.time = Clock()
        try:
            _, client, logs = self.run_extraction([broken], deadline=270)
        finally:
            extract_module.time = real
        self.assertNotIn("selfcheck1:outcomes", client.purposes())
        self.assertTrue(any(key == "self_check_repair" and "time guard" in value for key, value in logs), logs)


class TraceTests(unittest.TestCase):
    def test_print_with_spec_writes_self_check_lines(self):
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            try:
                with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
                    code = build.main([str(ROOT / "build-the-builder-v2/briefs/brief-a.md"),
                                       str(ROOT / "build-the-builder-v2/tools/openapi.json"), "--print",
                                       "--spec", str(ROOT / "tests/fixtures/extract/brief-a-repro-1300.json"),
                                       "--slot", "check"])
                trace = Path("traces/check.print.log").read_text(encoding="utf-8")
            finally:
                os.chdir(previous)
        self.assertEqual(0, code)
        json.loads(out.getvalue())  # stdout stays the workflow JSON
        lines = [line for line in trace.splitlines() if line.startswith("self_check")]
        self.assertTrue(any("scenario=reach_outcomes[6] result=fail kind=spec" in line for line in lines))
        summary = [line for line in lines if line.startswith("self_check_summary:")]
        self.assertEqual(1, len(summary))
        self.assertIn("spec=1 builder=0", summary[0])
        self.assertIn("warning: self_check: 1 spec problem(s) left; shipped anyway", trace)

    def test_submission_check_accepts_the_new_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            helper = SubmissionCheckTests()
            trace, export, spec = helper.make_artifacts(directory)
            text = trace.read_text(encoding="utf-8").replace("status: ok", "\n".join([
                "self_check: scenario=promise result=pass",
                "self_check: scenario=reach_outcomes[6] result=fail kind=spec reason=no call reaches the row",
                "self_check_summary: scenarios=2 pass=1 fail=1 spec=1 builder=0 seconds=0.3",
                "self_check_repair: round=1 groups=outcomes problems=1",
                "status: ok"]))
            trace.write_text(text, encoding="utf-8")
            self.assertEqual(set(), helper.failures(check_submission(trace, export, spec)))


if __name__ == "__main__":
    unittest.main()
