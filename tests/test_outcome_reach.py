"""F-065 (REPRO): unreachable outcome rows, quoted speech in instruction lines, and the row a
failed special-path tool closes with. Offline; the two specs are live Brief A extractions."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from builder.prompts import CLOSING_FALLBACK_SAY, SPECIAL_TOOL_FAILED_SAY
from builder.spec import parse_spec
from builder.spoken import agent_directed, quoted_speech, spoken_words
from builder.workflow import build_spec_workflow, close_table, speakable_spec, unreachable_outcomes
from tests.test_multi_step import FIXTURES, kit_tools
from tests.test_offer_date_only import code_of

ROOT = Path(__file__).resolve().parents[1]
# The 13:00 run (no special path for a declined hardship offer) and rep2 (every closing line
# written as an instruction), both from REPRO.
SPEC_1300 = json.loads((ROOT / "tests/fixtures/extract/brief-a-repro-1300.json").read_text(encoding="utf-8"))
SPEC_REP2 = json.loads((ROOT / "tests/fixtures/extract/brief-a-repro-rep2.json").read_text(encoding="utf-8"))


def says(data):
    spec, notes = speakable_spec(parse_spec(copy.deepcopy(data)))
    return {(item.outcome, item.reason): item.say.text for item in spec.outcomes}, notes


class UnreachableOutcomeTests(unittest.TestCase):
    def test_the_1300_spec_renders_with_a_trace_warning(self):
        warnings = []
        build_spec_workflow(parse_spec(copy.deepcopy(SPEC_1300)), kit_tools(0), warnings)
        found = [warning for warning in warnings if warning.startswith("unreachable_outcome")]
        self.assertEqual(1, len(found), found)
        self.assertIn("no_promise/hardship", found[0])

    def test_fixtures_and_live_specs_with_every_path_have_no_warning(self):
        for path in [*FIXTURES, ROOT / "tests/fixtures/extract/brief-a-repro-rep2.json"]:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("closing", {}).get("product_notes"):
                continue  # Brief B: see the next test
            with self.subTest(spec=path.name):
                self.assertEqual([], unreachable_outcomes(parse_spec(data.get("spec", data))))

    def test_a_returning_path_without_a_tool_reaches_nothing(self):
        # Review LOW 1: a question path returns with some pair but writes nothing; a row with
        # only that pair is still unreachable (render and extraction).
        data = copy.deepcopy(SPEC_1300)
        question = next(path for path in data["special_paths"] if path["then"] == "return" and not path["tool"])
        question["outcome"], question["reason"] = "no_promise", "hardship"
        found = unreachable_outcomes(parse_spec(data))
        self.assertEqual(1, len(found), found)
        self.assertIn("the call can never end this way", found[0])

    def test_rows_named_only_by_a_returning_path_get_their_own_warning(self):
        # Brief B: paid and dispute are per-product notes (then return); the closing does not yet
        # derive the call's outcome from the notes (AB-FRESH risk 5, open).
        for name in ("spec-brief-b.json", "extract/brief-ab-extracted-v2.json"):
            with self.subTest(spec=name):
                data = json.loads((ROOT / "tests/fixtures" / name).read_text(encoding="utf-8"))
                found = unreachable_outcomes(parse_spec(data))
                self.assertEqual(2, len(found), found)
                self.assertTrue(all("only a special path that returns names it" in line for line in found))


class QuotedSpeechTests(unittest.TestCase):
    def test_quoted_words_are_kept(self):
        self.assertEqual("You will receive a text message confirming this promise.", quoted_speech(
            'Say: "You will receive a text message confirming this promise." Then thank the customer and say goodbye.'))
        self.assertEqual("We can help.", quoted_speech("Tell them “We can help”"))
        self.assertEqual("", quoted_speech("Thank the customer and say goodbye."))
        self.assertEqual("", quoted_speech('Say "call close_call now".'))  # quoted, but not speech

    # F-065 review: quoted words that are not speech the agent should say.
    NOT_SPEECH = (
        'Say that payments can take one business day to appear; close as "paid".',
        'If the customer says "I already paid", say that payments can take one business day.',
        'Tell the customer to use the mobile app, then close as no_promise / "refused".',
        'Close with outcome "promise" and thank the customer.',
        'Do not say "payment" or "debt" before verification; thank the customer and say goodbye.',
        'Never say "debt". Say goodbye.',
        'Thank the customer for "their time" and say goodbye.',
        'Say "Is this a scam?" is answered by phoning the bank.',
    )

    def test_quotes_that_are_not_speech_give_the_plain_goodbye(self):
        for line in self.NOT_SPEECH:
            with self.subTest(line=line):
                self.assertEqual("", quoted_speech(line))
                data = copy.deepcopy(SPEC_REP2)
                next(item for item in data["outcomes"] if item["outcome"] == "promise")["say"]["text"] = line
                lines, _ = says(data)
                self.assertEqual(CLOSING_FALLBACK_SAY.text, lines[("promise", "")])

    def test_negated_or_mixed_quotes_give_nothing(self):
        self.assertEqual("", quoted_speech('Do not say "you owe us a lot of money." Then say goodbye.'))
        self.assertEqual("", quoted_speech('Say: "We can help you today." Say "close_call now please".'))
        self.assertEqual("", quoted_speech('Say "the promise is done."', {"the promise is done"}))

    def test_quoted_lines_of_the_live_specs_are_kept(self):
        # Every quoted instruction line in the fixtures is a real sentence and is kept.
        kept = []
        for path in sorted((ROOT / "tests/fixtures").rglob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            data = data.get("spec", data) if isinstance(data, dict) else None
            if not isinstance(data, dict) or not isinstance(data.get("outcomes"), list):
                continue
            for item in [*data["outcomes"], *data.get("special_paths", [])]:
                text = (item.get("say") or {}).get("text", "") if isinstance(item, dict) else ""
                if ('"' in text or "“" in text) and agent_directed(spoken_words(text)):
                    kept.append(quoted_speech(text))
        self.assertEqual(6, len(kept))
        self.assertEqual({"You will receive a text message confirming this promise.", "I am sorry for your loss."},
                         set(kept))

    def test_rep2_lines_keep_their_quoted_sentence(self):
        lines, notes = says(SPEC_REP2)
        goodbye = CLOSING_FALLBACK_SAY.text
        self.assertEqual("You will receive a text message confirming this promise. " + goodbye, lines[("promise", "")])
        self.assertEqual("I am sorry for your loss. " + goodbye, lines[("not_reached", "deceased")])
        # Nothing quoted: the goodbye alone, as before.
        self.assertEqual(goodbye, lines[("no_promise", "refused")])
        self.assertTrue(any("spoken instead: 'You will receive" in note for note in notes))

    def test_quoted_goodbye_is_not_said_twice(self):
        data = copy.deepcopy(SPEC_REP2)
        row = next(item for item in data["outcomes"] if item["outcome"] == "promise")
        row["say"]["text"] = 'Say: "Thank you, goodbye." Then thank the customer.'
        lines, _ = says(data)
        self.assertEqual("Thank you, goodbye.", lines[("promise", "")])

    def test_spoken_lines_are_unchanged(self):
        lines, notes = says(SPEC_1300)
        self.assertEqual(
            "You will receive a text message confirming this promise. Thank you for your time. Goodbye.",
            lines[("promise", "")])
        self.assertEqual([], [note for note in notes if note.startswith("spoken_fallback outcomes")])


class SpecialToolFailedTests(unittest.TestCase):
    def closing(self, data, variables):
        workflow = build_spec_workflow(parse_spec(copy.deepcopy(data)), kit_tools(0))
        variables = dict(variables)
        exec(code_of(workflow["nodes"]["closing"]), {"vars": variables})
        return variables

    def test_an_unmapped_tool_failure_takes_the_promise_failure_row(self):
        # rep2 maps no row to special_tool_failed; it used to fall to the default row (refused).
        self.assertFalse(any("special_tool_failed" in row["on"] for row in SPEC_REP2["outcomes"]))
        rows = {row[0]: row[1:3] for row in close_table(parse_spec(copy.deepcopy(SPEC_REP2)))}
        self.assertEqual(rows["promise_failed"][:2], rows["special_tool_failed"][:2])
        result = self.closing(SPEC_REP2, {"close_state": "special_tool_failed"})
        self.assertEqual(("no_promise", "service_error"), (result["close_outcome"], result["close_reason"]))
        # The builder's failure line and the goodbye, not the promise-failure sentence.
        self.assertEqual(SPECIAL_TOOL_FAILED_SAY.text + " " + CLOSING_FALLBACK_SAY.text, result["closing_sentence"])

    def test_a_mapped_tool_failure_keeps_its_row(self):
        data = copy.deepcopy(SPEC_REP2)
        refused = next(row for row in data["outcomes"] if row.get("reason") == "refused")
        refused["on"].append("special_tool_failed")
        result = self.closing(data, {"close_state": "special_tool_failed"})
        self.assertEqual(("no_promise", "refused"), (result["close_outcome"], result["close_reason"]))


if __name__ == "__main__":
    unittest.main()
