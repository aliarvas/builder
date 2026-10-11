"""T-026: the recording notice is said in the present tense; "recorded" only after a tool returned ok."""

from __future__ import annotations

import re
import unittest

from builder.spoken import RECORDING_NOTICE_WORDS, present_recording_notice
from tests.test_selfcheck import SPECS
from tests.test_selfcheck_families import render


def opening_line(workflow):
    """The introduction as the opening prompt gives it (its first words, said once)."""
    return workflow["nodes"]["opening"]["task_message"].split("only once: ", 1)[1].split("\n", 1)[0]


class RecordingNoticeTests(unittest.TestCase):
    def test_every_fixture_opening_discloses_without_recorded(self):
        for name in SPECS:
            spec, workflow = render(name)
            line = opening_line(workflow)
            with self.subTest(spec=name):
                self.assertNotRegex(line, re.compile(r"\brecorded\b", re.IGNORECASE))
                if re.search(r"\brecord", spec.agent.introduction.text, re.IGNORECASE):
                    self.assertIn("recording", line.lower())  # still discloses it
                self.assertNotIn("introduction", workflow["nodes"]["opening_reask"]["task_message"].split("\n")[1])
                self.assertIn('Use the word "recorded" only for an action whose tool returned ok true',
                              workflow["system_prompt"])

    def test_the_brief_a_live_line(self):
        # The v17 PUB-10 judge read this as "recorded" said before any tool ran.
        line, note = present_recording_notice(
            "I am a digital assistant calling from Freya Bank, and this call is recorded.")
        self.assertEqual("I am a digital assistant calling from Freya Bank, and we are recording this call.", line)
        self.assertIn("present", note)

    def test_grammar(self):
        cases = {
            "This call is recorded.": "We are recording this call.",
            "Hello. This call is being recorded for quality and security.":
                "Hello. We are recording this call for quality and security.",
            "This is a digital assistant calling from the bank; your call is recorded.":
                "This is a digital assistant calling from the bank; we are recording this call.",
            "Calls are recorded for training, and this is the bank.":
                "We are recording this call for training, and this is the bank.",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(expected, present_recording_notice(text)[0])
                self.assertNotIn("call is recording", present_recording_notice(text)[0])

    def test_other_lines_are_left_with_a_warning(self):
        self.assertEqual(("Hello, I am calling from the bank.", ""),
                         present_recording_notice("Hello, I am calling from the bank."))
        text = "Your details are recorded in our system."
        line, note = present_recording_notice(text)
        self.assertEqual(text, line)  # not clearly the call-recording notice
        self.assertIn("left in the line", note)
        self.assertNotIn(RECORDING_NOTICE_WORDS, present_recording_notice("This call may be recorded.")[0])


if __name__ == "__main__":
    unittest.main()
