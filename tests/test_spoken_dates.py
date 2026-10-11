"""T-022 (F-075, F-076): dates said in words, a turn without a readable date, and the longer
timeout of the tools that write."""

from __future__ import annotations

import datetime
import json
import unittest

from builder.offer_check import PRELUDE
from builder.selfcheck import BUILDER, run_selfcheck, spoken_date_forms, spoken_ordinal
from builder.tools_from_openapi import WRITE_TIMEOUT_MS
from builder.workflow import build_spec_workflow
from tests.test_offer_date_only import Call
from tests.test_selfcheck import NOW, SPECS, load


def reader():
    """The generated date reader, run at the test's now (a Wednesday)."""
    names = {"vars": {"now": NOW}}
    exec(PRELUDE.replace("__CONFIG__", "{'offer': {}}").replace("__PRODUCT_READER__", ""), names)
    names["today"] = lambda: datetime.date(2026, 10, 14)
    return names["resolve_offer_day"]


class SpokenDayTests(unittest.TestCase):
    def test_day_numbers_in_words_next_to_a_month(self):
        read = reader()
        for phrase, day in {
            "Twenty-third of October": "2026-10-23", "the twenty third of October": "2026-10-23",
            "the sixth of November": "2026-11-06", "November the sixth": "2026-11-06",
            "October twenty-first": "2026-10-21", "twenty three October": "2026-10-23",
            "the thirty-first of October": "2026-10-31", "on the twentieth of November": "2026-11-20",
            "first of December": "2026-12-01", "6th of November": "2026-11-06", "October 23rd": "2026-10-23",
            "Friday the twenty third of October": "2026-10-23",
        }.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(day, str(read(phrase)))

    def test_words_without_a_month_or_past_31_are_not_a_day(self):
        read = reader()
        for phrase in ("twenty", "I can pay twenty pounds", "the first", "thirty second of October",
                       "October thirty second", "forty first of May"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(read(phrase))

    def test_the_spoken_forms(self):
        self.assertEqual(["first", "twentieth", "twenty-third", "thirtieth", "thirty-first"],
                         [spoken_ordinal(n) for n in (1, 20, 23, 30, 31)])
        forms = spoken_date_forms(datetime.date(2026, 10, 23))
        self.assertEqual("the twenty-third of October", forms["word_ordinal"])
        self.assertEqual("October 23rd", forms["month_first"])


class MissingDateTests(unittest.TestCase):
    # spec-brief-a: one card, latest allowed date 2026-11-02, max_rejected_offers 2.
    UNREADABLE = "when my salary comes in"

    def test_the_code_proposes_the_latest_date_and_a_yes_takes_it(self):
        call = Call()
        first = call.turn(offer_date=self.UNREADABLE)
        self.assertEqual("missing", first["offer_verdict"])
        self.assertIn("Monday, 2 November", first["offer_message"])
        self.assertEqual("2026-11-02", first["offer_suggested_date"])
        second = call.turn(offer_accepts_proposal="yes")
        self.assertEqual("ok", second["offer_verdict"], second["offer_message"])
        self.assertEqual("2026-11-02", call.accepted()["1"]["date"])

    def test_the_second_asks_for_day_and_month_and_the_third_counts_as_a_rejection(self):
        call = Call()
        messages, rejections = [], []
        for _ in range(4):
            result = call.turn(offer_date=self.UNREADABLE)
            self.assertEqual("missing", result["offer_verdict"])
            messages.append(result["offer_message"])
            rejections.append(int(result["offer_rejections"]))
        self.assertTrue(messages[0].startswith("Could you tell me the exact day"))
        self.assertEqual("Please tell me the day and the month, for example Monday, 2 November.", messages[1])
        self.assertEqual(messages[1], messages[2])
        self.assertEqual([0, 0, 1, 2], rejections)
        # The spec's offer limit (2) is reached: the product is closed as refused, no more asking.
        self.assertIn("1", [str(number) for number in json.loads(call.vars["offers_noted"])])

    def test_a_readable_date_resets_the_streak(self):
        call = Call()
        call.turn(offer_date=self.UNREADABLE)
        call.turn(offer_date="2026-11-03")  # read, after the deadline
        again = call.turn(offer_date=self.UNREADABLE)
        self.assertTrue(again["offer_message"].startswith("Could you tell me the exact day"), again["offer_message"])


class SelfCheckTests(unittest.TestCase):
    def test_the_family_passes_and_catches_the_old_reader(self):
        spec = load(SPECS["spec-brief-a.json"][0])
        workflow = build_spec_workflow(spec, SPECS["spec-brief-a.json"][1])
        played = [item for item in run_selfcheck(spec, workflow, NOW).results if item.scenario.startswith("spoken_date")]
        self.assertEqual(7, len(played))  # T-027: the weekday form
        self.assertTrue(all(item.passed for item in played), [item.reason for item in played if not item.passed])
        # The v18 reader: no words for day numbers.
        text = json.dumps(workflow)
        old = text.replace("text = spoken_day_numbers(normalized_date_text(value))", "text = normalized_date_text(value)")
        self.assertNotEqual(text, old)
        report = run_selfcheck(spec, json.loads(old), NOW)
        failed = {item.scenario for item in report.results if item.scenario.startswith("spoken_date") and not item.passed}
        self.assertEqual({"spoken_date_word_ordinal", "spoken_date_word_ordinal_capital", "spoken_date_month_the_word",
                          "spoken_date_weekday_the_word"}, failed)
        self.assertTrue(all(item.kind == BUILDER for item in report.results
                            if item.scenario in failed))


class WriteTimeoutTests(unittest.TestCase):
    def test_every_write_tool_waits_longer_and_is_never_retried(self):
        for name, (path, tools) in SPECS.items():
            workflow = build_spec_workflow(load(path), tools)
            with self.subTest(spec=name):
                seen = set()
                for node in [*workflow["nodes"].values(), *workflow.get("global_nodes", {}).values()]:
                    for tool in node.get("pre_actions", []):
                        if tool.get("function", {}).get("handler") != "__function__:api_call":
                            continue
                        config = tool.get("config", {})
                        name_ = tool["function"]["name"]
                        if config.get("maxRetries") == 0:
                            seen.add(name_)
                            self.assertEqual(WRITE_TIMEOUT_MS, config.get("timeoutMs"), name_)
                for tool in workflow.get("tools", []):
                    self.assertEqual(WRITE_TIMEOUT_MS, tool["config"]["timeoutMs"])
                self.assertTrue({"create_promise", "close_call"} <= seen, seen)
                # The reads keep the short timeout and their retries.
                for node in workflow["nodes"].values():
                    for tool in node.get("pre_actions", []):
                        if tool.get("function", {}).get("name") in ("get_account",):
                            self.assertEqual(10000, tool["config"]["timeoutMs"])


if __name__ == "__main__":
    unittest.main()
