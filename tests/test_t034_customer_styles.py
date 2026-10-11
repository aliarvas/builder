"""T-034: the kit's customer styles (build-the-builder-v2/tools/run_cases.py STYLES) as self-check
calls: a self-corrected date, a date in two pieces, an unrelated day in a talkative answer, a
year said digit by digit, and a question back before each answer."""

from __future__ import annotations

import json
import unittest

from builder.prompts import WHO_ANSWERED_DESCRIPTION
from builder.selfcheck import play, run_selfcheck, scenarios
from tests.test_selfcheck import SPECS
from tests.test_selfcheck_families import AB, BRIEF_A, render

NOW = "2026-10-14T11:00"
STYLE_IDS = {"style_corrects_digit", "style_corrects_month_first", "style_corrects_words",
             "style_pieces_day_then_month", "style_pieces_month_then_day", "style_talkative_chatter",
             "style_talkative_other_day", "style_talkative_other_day_no_pay_word", "style_in_words_year_digits",
             "style_asks_back"}
# The T-033 code before T-034: the first date of a phrase, no pieces.
OLD_READING = (
    ("corrections = list(re.finditer(CORRECTION_PATTERN, text.lower()))", "corrections = []"),
    ("if len(said_day_numbers(text)) > 1:", "if False:"),
    ("if day is None and piece and kept_piece:", "if False:"),
)


def style_failures(spec, workflow):
    found = {}
    for scenario in scenarios(spec, NOW):
        if scenario.id.startswith("style_"):
            found[scenario.id] = play(workflow, spec, scenario, NOW)[1]
    return found


def old_reading(workflow):
    text = json.dumps(workflow)
    for new, old in OLD_READING:
        assert json.dumps(new)[1:-1] in text, new
        text = text.replace(json.dumps(new)[1:-1], json.dumps(old)[1:-1])
    return json.loads(text)


class StyleFamilyTests(unittest.TestCase):
    def test_every_fixture_passes_the_style_calls(self):
        for name in SPECS:
            spec, workflow = render(name)
            with self.subTest(spec=name):
                found = style_failures(spec, workflow)
                self.assertTrue(STYLE_IDS <= set(found), STYLE_IDS - set(found))
                self.assertEqual({}, {key: value for key, value in found.items() if value})

    def test_the_old_date_reading_fails_them(self):
        for name in (BRIEF_A, AB):
            spec, workflow = render(name)
            with self.subTest(spec=name):
                found = style_failures(spec, old_reading(workflow))
                failed = {key for key, value in found.items() if value}
                self.assertTrue({"style_corrects_digit", "style_corrects_month_first", "style_talkative_other_day",
                                 "style_pieces_day_then_month", "style_pieces_month_then_day"} <= failed, failed)
                # The wedding day (the first day said) was booked.
                self.assertTrue(any("promises" in item for item in found["style_talkative_other_day"]))

    def test_the_family_is_part_of_the_self_check(self):
        spec, workflow = render(BRIEF_A)
        report = run_selfcheck(spec, workflow, NOW)
        names = {result.scenario for result in report.results}
        self.assertTrue(STYLE_IDS <= names, STYLE_IDS - names)
        self.assertEqual([], [r.scenario for r in report.results if r.scenario.startswith("style_") and not r.passed])


class AskBackTests(unittest.TestCase):
    def test_a_question_back_at_the_opening_is_not_counted_as_unclear(self):
        text = WHO_ANSWERED_DESCRIPTION.text
        stay = text.split("{stay}:")[1].split("\n")[0]
        greeting = text.split("{greeting}:")[1]
        self.assertNotIn("question back", stay)
        self.assertIn("asks a question back", greeting)
        spec, workflow = render(BRIEF_A)
        field = workflow["nodes"]["opening"]["extraction_schema"][0]
        self.assertIn("asks a question back", field["description"])
        self.assertIn("ask a question back", workflow["nodes"]["opening"]["task_message"])

    def test_a_turn_that_answers_nothing_must_keep_the_step(self):
        spec, workflow = render(BRIEF_A)
        scenario = next(s for s in scenarios(spec, NOW) if s.id == "style_asks_back")
        sim, failures = play(workflow, spec, scenario, NOW)
        self.assertEqual([], failures)
        # A step that moves on a turn without an answer is flagged.
        broken = json.loads(json.dumps(workflow))
        broken["nodes"]["confirm_record"]["transitions"].append(
            {"target_node": "closing", "description": "x", "condition": {"operator": "always"}})
        failures = play(broken, spec, scenario, NOW)[1]
        self.assertTrue(any("ask_back turn at confirm_record moved the call" in item for item in failures), failures)


if __name__ == "__main__":
    unittest.main()
