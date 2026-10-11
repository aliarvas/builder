"""T-012: more self-check scenario families, each caught by a mutation, and the walkers."""

from __future__ import annotations

import copy
import dataclasses
import sys
import time
import unittest

from builder.selfcheck import (
    BUILDER, SILENT_TOOL_RULE, _sandbox, follow, play, run_selfcheck, scenarios, spoken_per_turn, unreached_rows,
)
from builder.workflow import build_spec_workflow
from tests.test_selfcheck import A_PLUS_B, NOW, SPECS, load

FAMILIES = {
    "hang-up": ("hangup_opening", "hangup_identity", "hangup_negotiate", "hangup_after_promise"),
    "turn limit": ("turn_limit_opening", "turn_limit_negotiate"),
    "account read fails": ("account_failed",),
    "callback answers": ("callback_unclear_then_booked", "callback_need_time_then_booked", "callback_book_failed"),
    "revise at the read-back": ("revise_at_readback",),
}
# Brief A (no callback window) and the A+B extraction (a window, returning paths, notes).
BRIEF_A, AB = "spec-brief-a.json", "brief-ab-extracted-v2.json"


def render(name):
    path, tools = SPECS[name]
    spec = load(path)
    return spec, build_spec_workflow(spec, tools)


def failed(spec, workflow, ids, now=NOW):
    """{scenario id: failures} for the scenarios ``ids`` that fail on ``workflow``."""
    result = {}
    for scenario in scenarios(spec, now):
        if scenario.id in ids:
            sim, failures = play(workflow, spec, scenario, now)
            if failures or sim.spec_failures:
                result[scenario.id] = failures + [problem for _, problem in sim.spec_failures]
    return result


class FamilyTests(unittest.TestCase):
    def test_every_family_is_generated_from_the_spec(self):
        for name in (BRIEF_A, AB):
            spec, _ = render(name)
            ids = {scenario.id for scenario in scenarios(spec, NOW)}
            with self.subTest(spec=name):
                for family, wanted in FAMILIES.items():
                    self.assertLessEqual(set(wanted), ids, family)
                # Two special paths in one call, and a path at another of its steps.
                self.assertTrue(any("_then_" in item for item in ids), ids)
                self.assertTrue(any(item.startswith("special_") and "_at_" in item for item in ids), ids)
        _, workflow = render(AB)
        spec, _ = render(AB)
        ids = {scenario.id for scenario in scenarios(spec, NOW)}
        # With a callback window, unclear or day-only answers end in giving up.
        self.assertLessEqual({"callback_unclear_give_up", "callback_need_time_give_up"}, ids)
        spec, _ = render(BRIEF_A)
        self.assertFalse({"callback_unclear_give_up"} & {s.id for s in scenarios(spec, NOW)})

    def test_expected_ledgers_come_from_the_spec_rows(self):
        spec, _ = render(BRIEF_A)
        plays = {scenario.id: scenario for scenario in scenarios(spec, NOW)}
        rows = {state: (item.outcome, item.reason) for item in spec.outcomes for state in item.on}
        # Before identity passed, a hang-up takes the unverified hang-up row.
        self.assertEqual(rows["hangup_unverified"], plays["hangup_opening"].pair)
        self.assertEqual(rows["hangup_unverified"], plays["hangup_identity"].pair)
        # Brief A maps no "hangup" state: after verification the default row.
        self.assertEqual(rows["default"], plays["hangup_negotiate"].pair)
        self.assertEqual("promise_recorded", plays["hangup_after_promise"].expect_state)
        self.assertEqual("account_failed", plays["account_failed"].expect_state)
        self.assertEqual("callback_failed", plays["callback_book_failed"].expect_state)
        self.assertEqual((), plays["callback_book_failed"].callback)
        day, _ = plays["callback_need_time_then_booked"].callback
        self.assertEqual("2026-10-15", day)  # the day named in the first answer is kept
        revise = plays["revise_at_readback"]
        first = next(action for action in revise.actions if action["label"] == "offer")["vars"]["offer_date"]
        self.assertNotEqual(first, revise.promises[0][2])  # only the new offer is recorded

    def test_every_fixture_plays_the_families_on_several_nows(self):
        for name in SPECS:
            spec, workflow = render(name)
            ids = {item for wanted in FAMILIES.values() for item in wanted}
            for now in ("2026-10-16T18:45", "2026-11-25T09:00", "2026-12-31T11:00"):
                with self.subTest(spec=name, now=now):
                    self.assertEqual({}, failed(spec, workflow, ids, now))

    def test_a_row_mapped_only_by_a_played_state_must_be_reached(self):
        data_spec, _ = render(BRIEF_A)
        spec = copy.deepcopy(data_spec)
        plays = scenarios(spec, NOW)
        # Move "account_failed" to a new row that nothing else names.
        outcomes = list(spec.outcomes)
        source = next(index for index, item in enumerate(outcomes) if "account_failed" in item.on)
        target = next(index for index, item in enumerate(outcomes) if not item.on and item.outcome == "paid")
        outcomes[source] = dataclasses.replace(outcomes[source], on=tuple(s for s in outcomes[source].on
                                                                           if s != "account_failed"))
        outcomes.append(dataclasses.replace(outcomes[target], reason="account_read", on=("account_failed",)))
        target = len(outcomes) - 1
        spec = dataclasses.replace(spec, outcomes=tuple(outcomes))
        self.assertNotIn(target, [index for index, _ in unreached_rows(spec, plays)])
        # Without the played call, the row is not counted as reached any more (a builder note).
        rows = dict(unreached_rows(spec, [item for item in plays if item.id != "account_failed"]))
        self.assertIn("state not played", rows[target])

    def test_the_a_b_self_check_stays_under_ten_seconds_in_build_mode(self):
        for name in A_PLUS_B:
            spec, workflow = render(name)
            started = time.monotonic()
            report = run_selfcheck(spec, workflow)  # build mode: three moments
            with self.subTest(spec=name):
                self.assertEqual(3, len(report.nows))
                self.assertLess(time.monotonic() - started, 10)


class MutationTests(unittest.TestCase):
    """One mutation of the rendered workflow per new family; the family catches it."""

    def assertCaught(self, name, mutate, ids, text=""):
        spec, workflow = render(name)
        self.assertEqual({}, failed(spec, workflow, ids))
        mutate(workflow)
        result = failed(spec, workflow, ids)
        self.assertTrue(result, f"{ids} not caught")
        if text:
            self.assertIn(text, " ".join(" ".join(items) for items in result.values()))
        return result

    def test_hangup_without_the_end_of_call_close_is_caught(self):
        def drop(workflow):
            workflow["tools"] = [tool for tool in workflow["tools"]
                                 if "end_of_call" not in tool.get("config", {}).get("alwaysRunsAt", [])]
        result = self.assertCaught(BRIEF_A, drop, FAMILIES["hang-up"], "0 close calls")
        self.assertEqual(set(FAMILIES["hang-up"]), set(result))

    def test_an_end_of_call_close_after_the_closing_chain_is_caught(self):
        def always(workflow):
            hook = workflow["tools"][0]
            hook["pre_process_code"] = hook["pre_process_code"].replace(
                "if ok_value == 'true' or attempts > 0:", "if False:")
        self.assertCaught(BRIEF_A, always, ("promise", "turn_limit_negotiate"), "2 close calls")

    def test_a_lost_turn_limit_transition_is_caught(self):
        def drop(workflow):
            workflow["nodes"]["negotiate"].pop("max_turn_transition")
        self.assertCaught(BRIEF_A, drop, FAMILIES["turn limit"], "no turn-limit transition")

    def test_an_account_failure_that_does_not_close_is_caught(self):
        def drop(workflow):
            account = workflow["nodes"]["account"]
            account["transitions"] = [t for t in account["transitions"] if t["target_node"] != "closing"]
        self.assertCaught(BRIEF_A, drop, FAMILIES["account read fails"], "does not reach end_call")

    def test_a_callback_check_that_forgets_the_named_day_is_caught(self):
        def forget(workflow):
            node = workflow["nodes"]["callback_check"]
            code = node["pre_actions"][0]["function"]["parameters"]["properties"]["code"]
            kept = "vars[CALLBACK['day_kept']] = fresh.isoformat()"
            self.assertIn(kept, code["default"])
            code["default"] = code["default"].replace(kept, "pass")
        result = self.assertCaught(BRIEF_A, forget, ("callback_need_time_then_booked",), "callbacks booked")
        self.assertIn("2026-10-15 12:00", " ".join(result["callback_need_time_then_booked"]))

    def test_a_callback_check_that_gives_up_at_once_on_unclear_is_caught(self):
        def hasty(workflow):
            code = workflow["nodes"]["callback_check"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]
            self.assertIn("max(1, WINDOW['max_outside_asks'])", code["default"])
            code["default"] = code["default"].replace("max(1, WINDOW['max_outside_asks'])", "0")
        self.assertCaught(AB, hasty, ("callback_unclear_then_booked",), "closes as not_reached/no_callback")

    def test_a_revise_that_records_the_old_offer_is_caught(self):
        def record(workflow):
            for transition in workflow["nodes"]["confirm_record"]["transitions"]:
                if transition["target_node"] == "revise_ask":
                    transition["target_node"] = "record_next"
        self.assertCaught(BRIEF_A, record, FAMILIES["revise at the read-back"], "promises")

    def test_a_declined_path_that_does_not_return_is_caught(self):
        spec, _ = render(BRIEF_A)
        [two] = [s.id for s in scenarios(spec, NOW) if s.id.startswith("special_") and "_then_" in s.id]
        first = two[len("special_"):two.index("_then_")]

        def no_way_back(workflow):
            node = workflow["global_nodes"]["special_" + first]
            node["transitions"] = [t for t in node["transitions"] if t["target_node"] != "__previous__"]
        self.assertCaught(BRIEF_A, no_way_back, (two,), "no way back")

    def test_a_path_that_cannot_start_at_its_other_step_is_caught(self):
        spec, _ = render(BRIEF_A)
        elsewhere = [s for s in scenarios(spec, NOW) if s.id.startswith("special_") and "_at_" in s.id]
        self.assertTrue(elsewhere)
        scenario = elsewhere[0]
        path_id = scenario.id[len("special_"):scenario.id.rindex("_at_")]

        def exclude(workflow):
            workflow["global_nodes"]["special_" + path_id]["excluded_nodes"].append(scenario.step)
        self.assertCaught(BRIEF_A, exclude, (scenario.id,), "cannot start at")


class WalkerTests(unittest.TestCase):
    def test_follow_routes_in_the_platform_sandbox(self):
        _, workflow = render(BRIEF_A)
        variables = {"identity_attempts_left": 0, "identity_verified": "false"}
        self.assertEqual("closing", follow(workflow, "identity", variables))
        self.assertEqual("identity", follow(workflow, "identity", {"identity_attempts_left": 2}))
        workflow["nodes"]["opening_unclear"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"][
            "default"] = "import os\n"
        with self.assertRaisesRegex(RuntimeError, "imports os"):
            follow(workflow, "opening_unclear", {})

    def test_an_allowed_modules_own_import_is_not_the_steps(self):
        # datetime.strptime loads _strptime lazily, through the step's import hook.
        sys.modules.pop("_strptime", None)
        problems = []
        exec("import datetime\ndatetime.datetime.strptime('2026-10-14', '%Y-%m-%d')\n",
             _sandbox(problems, "step", vars={}))
        exec("import time\nfrom os import path\n", _sandbox(problems, "other", vars={}))
        self.assertEqual(["other imports time", "other imports os"], [item.split(" (")[0] for item in problems])

    def test_spoken_per_turn_counts_a_tool_turn_unless_it_is_silent(self):
        _, workflow = render("brief-ab-extracted-tagged.json")  # a closing path the model fills
        within = ("special_", "close_", "closing", "end_call")
        every = {**workflow["nodes"], **workflow["global_nodes"]}
        silent = [key for key, node in every.items() if key.startswith("special_") and node.get("tools")
                  and SILENT_TOOL_RULE in node.get("task_message", "")]
        self.assertTrue(silent)
        for key in silent:
            self.assertLessEqual(spoken_per_turn(workflow, key, within)[0], 1)
            loud = copy.deepcopy(workflow)
            group = "nodes" if key in loud["nodes"] else "global_nodes"
            loud[group][key]["task_message"] = "Call the tool."
            with self.subTest(step=key):
                self.assertGreater(spoken_per_turn(loud, key, within)[0], 1)

if __name__ == "__main__":
    unittest.main()


class RelativeCallbackTests(unittest.TestCase):
    """T-014 (F-073): relative callback times are counted from now and checked on the window."""

    def relative(self, name, now):
        spec, workflow = render(name)
        plays = [s for s in scenarios(spec, now) if s.id.startswith("callback_relative_")]
        return spec, workflow, plays

    def test_the_family_passes_at_eleven_and_half_past_three(self):
        for name in (BRIEF_A, AB):
            for now in ("2026-10-14T11:00", "2026-10-14T15:30"):
                spec, workflow, plays = self.relative(name, now)
                self.assertGreaterEqual(len(plays), 6)
                with self.subTest(spec=name, now=now):
                    self.assertEqual({}, failed(spec, workflow, {s.id for s in plays}, now))

    def test_expected_times_by_hand(self):
        want = {
            ("2026-10-14T11:00", "callback_relative_two_hours_later"): ("2026-10-14", "13:00"),
            ("2026-10-14T15:30", "callback_relative_two_hours_later"): ("2026-10-14", "17:30"),
            ("2026-10-14T15:30", "callback_relative_half_an_hour_later"): ("2026-10-14", "16:00"),
            ("2026-10-14T11:00", "callback_relative_in_forty_five_minutes"): ("2026-10-14", "11:45"),
            # Not exact: asked again, then the next business day at the window's start (A+B: 10:00).
            ("2026-10-14T15:30", "callback_relative_in_a_couple_of_hours"): ("2026-10-15", "10:00"),
            # 18:30 + 2 h is after the window (19:00): asked again; Friday -> Monday 10:00.
            ("2026-10-16T18:30", "callback_relative_two_hours_later"): ("2026-10-19", "10:00"),
            # Review T-014: compound durations add every span; a bare number after a unit is asked again.
            ("2026-10-14T11:00", "callback_relative_two_hours_thirty_minutes_later"): ("2026-10-14", "13:30"),
            ("2026-10-14T15:30", "callback_relative_in_2_hours_30_minutes"): ("2026-10-14", "18:00"),
            ("2026-10-14T11:00", "callback_relative_in_one_hour_fifteen"): ("2026-10-15", "10:00"),
            # The window's edge (19:00): the last minute is booked, one minute later is asked again.
            ("2026-10-14T11:00", "callback_relative_window_last_minute"): ("2026-10-14", "19:00"),
            ("2026-10-14T15:30", "callback_relative_window_last_minute"): ("2026-10-14", "19:00"),
            ("2026-10-14T15:30", "callback_relative_window_one_minute_past"): ("2026-10-15", "10:00"),
        }
        for (now, scenario_id), callback in want.items():
            _, _, plays = self.relative(AB, now)
            with self.subTest(now=now, scenario=scenario_id):
                self.assertEqual(callback, next(s for s in plays if s.id == scenario_id).callback)

    def test_build_mode_plays_the_family_on_every_moment(self):
        for name in (BRIEF_A, AB):
            spec, workflow = render(name)
            report = run_selfcheck(spec, workflow)  # the build's now plus check_nows
            with self.subTest(spec=name):
                self.assertEqual(3, len(report.nows))
                self.assertFalse([r for r in report.results if "relative" in r.scenario and not r.passed])

    def test_reading_only_the_first_span_of_a_compound_duration_is_caught(self):
        # Review T-014 finding 1: the T-014 code read "two hours thirty minutes later" as 30 minutes.
        def first_span_only(workflow):
            code = workflow["nodes"]["callback_check"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]
            for text in ("(?: (?:and )?(\\d+) (?:minutes?|mins?))?", "if not found or BARE.search(text):",
                         "    if len(SPANS.findall(text)) != len(SPANS.findall(found.group(0))):\n        return -1\n"):
                self.assertIn(text, code["default"])
            code["default"] = (code["default"]
                               .replace("(?: (?:and )?(\\d+) (?:minutes?|mins?))?", "(?: and (\\d+) (?:minutes?|mins?))?")
                               .replace("if not found or BARE.search(text):", "if not found:")
                               .replace("    if len(SPANS.findall(text)) != len(SPANS.findall(found.group(0))):\n"
                                        "        return -1\n", ""))
        compound = {"callback_relative_in_2_hours_30_minutes", "callback_relative_two_hours_thirty_minutes_later",
                    "callback_relative_in_one_hour_fifteen"}
        for name in (BRIEF_A, AB):
            spec, workflow, _ = self.relative(name, "2026-10-14T11:00")
            first_span_only(workflow)
            with self.subTest(spec=name):
                self.assertEqual(compound, set(failed(spec, workflow, compound, "2026-10-14T11:00")))

    def test_reading_two_hours_later_as_a_clock_time_is_caught(self):
        # The F-073 code: no duration reading, so "two hours later" became the clock time 14:00.
        def old(workflow):
            code = workflow["nodes"]["callback_check"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]
            for text in ("    offset = duration_minutes(time_text)\n", "        offset = duration_minutes(day_text)\n"):
                self.assertIn(text, code["default"])
                code["default"] = code["default"].replace(text, text.split("=")[0] + "= None\n")
            code["default"] = code["default"].replace("    if DURATION.search(text):\n        return []\n", "")
        for name in (BRIEF_A, AB):
            for now in ("2026-10-14T11:00", "2026-10-14T15:30"):
                spec, workflow, _ = self.relative(name, now)
                old(workflow)
                result = failed(spec, workflow, {"callback_relative_two_hours_later"}, now)
                with self.subTest(spec=name, now=now):
                    # Brief A (no window) books 02:00, the A+B window 14:00 (or "outside" at 15:30).
                    self.assertTrue(result)
