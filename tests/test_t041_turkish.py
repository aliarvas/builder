"""T-041: a call in Turkish. The system prompt and extraction say the language, the generated code
reads Turkish dates and says them in Turkish, the builder's fixed lines are translated with their
placeholders kept, and English renders are unchanged."""

from __future__ import annotations

import dataclasses
import datetime
import json
import unittest

from builder import language
from builder.prompts import OFFER_VERDICT_MESSAGES, READBACK_LINE
from builder.selfcheck import _compiled, _sandbox, play, scenarios
from builder.spec import parse_spec
from builder.workflow import build_spec_workflow
from tests.test_selfcheck import SPECS

NOW = "2026-10-14T11:00"   # a Wednesday
FIXTURE = "brief-a-reference.json"


def turkish_spec(name=FIXTURE):
    path, tools = SPECS[name]
    data = json.loads(path.read_text(encoding="utf-8"))
    data = data.get("spec", data)
    data["agent"]["language"] = "Turkish"
    return parse_spec(data), tools


def check_namespace(workflow):
    code = workflow["nodes"]["check_offer"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    names = _sandbox([], "test", vars={"now": NOW})
    exec(_compiled(code), names)
    return names


# Phrase -> the day it names (NOW is Wednesday 14 October 2026).
TURKISH_DAYS = {
    "16 Ekim": "2026-10-16",
    "16 Ekim'de": "2026-10-16",
    "on altı Ekim": "2026-10-16",
    "Ekim'in on altısı": "2026-10-16",
    "yirmi yedi Ekim Salı": "2026-10-27",
    "27 Ekim'de ödeyebilirim": "2026-10-27",
    "16.10.2026": "2026-10-16",
    "bugün": "2026-10-14",
    "yarın": "2026-10-15",
    "öbür gün": "2026-10-16",
    "Cuma": "2026-10-16",
    "bu cuma": "2026-10-16",
    "haftaya cuma": "2026-10-23",
    "17 Ekim, pardon, 16 Ekim": "2026-10-16",
    "kuzenimin düğünü 30 Ekim'de ama 16 Ekim'de ödeyebilirim": "2026-10-16",
    "İKİ KASIM": "2026-11-02",
}


class LanguageCodeTests(unittest.TestCase):
    def test_codes(self):
        for text, code in (("Turkish", "tr"), ("tr", "tr"), ("Türkçe", "tr"), ("tr-TR", "tr"), ("English", "en"),
                           ("", "en"), (None, "en")):
            self.assertEqual(code, language.language_code(text), text)


class TurkishRenderTests(unittest.TestCase):
    def test_system_prompt_and_extraction_say_the_language(self):
        spec, tools = turkish_spec()
        workflow = build_spec_workflow(spec, tools)
        self.assertTrue(workflow["system_prompt"].startswith("Speak only Turkish"))
        for node in workflow["nodes"].values():
            for field in node.get("extraction_schema") or []:
                self.assertTrue(field["description"].endswith("The customer may speak Turkish."), field["name"])

    def test_the_english_render_is_unchanged(self):
        path, tools = SPECS[FIXTURE]
        data = json.loads(path.read_text(encoding="utf-8"))
        spec = parse_spec(data.get("spec", data))
        workflow = json.dumps(build_spec_workflow(spec, tools))
        self.assertNotIn("Speak only", workflow)
        self.assertNotIn("TR_MONTHS", workflow)

    def test_the_turkish_date_reader(self):
        spec, tools = turkish_spec()
        names = check_namespace(build_spec_workflow(spec, tools))
        for phrase, day in TURKISH_DAYS.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(day, str(names["resolve_offer_day"](phrase)))
        self.assertIsNone(names["resolve_offer_day"]("maaşım yatınca"))

    def test_dates_and_amounts_are_said_in_turkish(self):
        spec, tools = turkish_spec()
        names = check_namespace(build_spec_workflow(spec, tools))
        self.assertEqual("16 Ekim Cuma", names["say_spoken_day"](datetime.date(2026, 10, 16)))
        self.assertEqual("637,50", names["say_spoken_amount"](637.5))
        self.assertEqual("1250", names["say_spoken_amount"](1250.0))
        self.assertEqual(1250.5, names["parse_amount"]("1.250,50"))

    def test_the_self_check_plays_turkish_dates(self):
        spec, tools = turkish_spec()
        workflow = build_spec_workflow(spec, tools)
        found = {s.id: s for s in scenarios(spec, NOW)}
        self.assertEqual([], [key for key, s in found.items() if play(workflow, spec, s, NOW)[1]])
        self.assertTrue({"spoken_date_tr_digits", "spoken_date_tr_suffix", "spoken_date_tr_words"} <= set(found))
        base = found["spoken_date_digit_ordinal"]
        day = datetime.date.fromisoformat(base.promises[0][2])
        at = next(i for i, action in enumerate(base.actions) if action.get("label") == "offer")
        names = check_namespace(workflow)
        for phrase in (f"{day.day} Ekim", f"{day.day} Ekim'de", names["say_spoken_day"](day)):
            actions = [dict(action) for action in base.actions]
            actions[at] = {**actions[at], "vars": {**actions[at]["vars"], "offer_date": phrase}}
            with self.subTest(phrase=phrase):
                self.assertEqual([], play(workflow, spec, dataclasses.replace(base, actions=actions), NOW)[1])


class TranslationTableTests(unittest.TestCase):
    def test_placeholders_are_kept_or_the_line_stays_english(self):
        english = {item.name: item.text for item in language.spoken_definitions()}
        self.assertIn("READBACK_LINE", english)
        self.assertIn("OFFER_VERDICT_MESSAGES", english)
        answer = {name: "TR " + text for name, text in english.items()}
        answer["READBACK_LINE"] = "{payments} kaydedebilirim. Onaylıyor musunuz?"
        answer["READBACK_ITEM"] = "{product} için ödeme"   # lost {amount} and {date}
        answer["OFFER_VERDICT_MESSAGES"] = "\n".join(
            "x" + line for line in OFFER_VERDICT_MESSAGES.text.splitlines())  # keys changed
        table, notes = language.translate_table("tr", lambda system, user: json.dumps(answer))
        self.assertEqual("{payments} kaydedebilirim. Onaylıyor musunuz?", table["READBACK_LINE"])
        self.assertNotIn("READBACK_ITEM", table)
        self.assertNotIn("OFFER_VERDICT_MESSAGES", table)
        self.assertTrue(any("READBACK_ITEM" in note for note in notes))

    def test_a_failed_call_keeps_english(self):
        def broken(system, user):
            raise RuntimeError("down")
        table, notes = language.translate_table("tr", broken)
        self.assertEqual({}, table)
        self.assertTrue(notes)

    def test_localized_swaps_and_restores(self):
        original = READBACK_LINE.text
        with language.localized({"READBACK_LINE": "{payments} kaydedebilirim. Onaylıyor musunuz?"}):
            self.assertEqual("{payments} kaydedebilirim. Onaylıyor musunuz?", READBACK_LINE.text)
            spec, tools = turkish_spec()
            code = json.dumps(build_spec_workflow(spec, tools))
            self.assertIn("kaydedebilirim", code)
        self.assertEqual(original, READBACK_LINE.text)

    def test_english_needs_no_model_call(self):
        class Trace:
            def add(self, *args):
                raise AssertionError("no trace entry for English")
        path, tools = SPECS[FIXTURE]
        data = json.loads(path.read_text(encoding="utf-8"))
        spec = parse_spec(data.get("spec", data))
        with language.spoken_language(spec, Trace(), client=object()):
            pass


if __name__ == "__main__":
    unittest.main()
