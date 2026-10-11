"""T-044: product names in the call's language, the Turkish recording notice and honesty line,
Turkish callback times, and the documents' currency after spoken amounts. English is unchanged."""

from __future__ import annotations

import datetime
import json
import unittest

from builder import language
from builder.selfcheck import _compiled, _sandbox
from builder.spec import parse_spec
from builder.spoken import present_recording_notice
from builder.workflow import build_spec_workflow
from tests.test_selfcheck import SPECS
from tests.test_t041_turkish import NOW, check_namespace

AB = "brief-ab-extracted-v2.json"
WORDS = {
    "WORD_NAME_WITH_LABEL": "{label} ile biten {kind}", "WORD_PRODUCT": "ürün", "WORD_AND": "ve",
    "WORD_NTH": "\n".join(f"{n}. ürün" for n in range(1, 11)),
    "WORD_KIND_credit_card": "kredi kartı", "WORD_KIND_personal_loan": "ihtiyaç kredisi",
}


def spec_of(name, **agent):
    path, tools = SPECS[name]
    data = json.loads(path.read_text(encoding="utf-8"))
    data = data.get("spec", data)
    data["agent"].update(agent)
    return parse_spec(data), tools


def code_of(workflow, key):
    return workflow["nodes"][key]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]


class ProductWordTests(unittest.TestCase):
    def test_the_kinds_come_from_the_spec_and_go_in_the_one_call(self):
        spec, _ = spec_of(AB)
        entries = language.product_word_entries(spec)
        self.assertEqual("credit card", entries["WORD_KIND_credit_card"])
        self.assertIn("WORD_NAME_WITH_LABEL", entries)
        sent = {}

        def complete(system, user):
            sent.update(json.loads(user))
            return json.dumps({**sent, **WORDS})
        table, notes = language.translate_table("tr", complete, entries)
        self.assertIn("WORD_KIND_credit_card", sent)
        self.assertEqual("kredi kartı", table["WORD_KIND_credit_card"])
        self.assertEqual("{label} ile biten {kind}", table["WORD_NAME_WITH_LABEL"])

    def test_turkish_names_and_read_back(self):
        spec, tools = spec_of(AB, language="Turkish")
        with language.localized(WORDS):
            workflow = build_spec_workflow(spec, tools)
        names = check_namespace(workflow)
        card = {spec.account.data["product_kind_field"]: "credit_card", spec.account.data["product_label_field"]: "1903"}
        name = names["product_name"](1, card, 2)
        self.assertEqual("1903 ile biten kredi kartı", name)
        self.assertTrue(name.startswith("the "))   # the English code adds no "the "
        self.assertEqual("2. ürün", names["product_name"](2, {}, 2))
        # An unknown kind falls back to its own words.
        self.assertEqual("gold card", names["product_name"](1, {spec.account.data["product_kind_field"]: "gold_card"}, 1))

    def test_offer_messages_keep_the_name_slot(self):
        english = {item.name: item.text for item in language.spoken_definitions()}
        turkish = english["OFFER_VERDICT_MESSAGES"].replace("the [product]", "[product] için").replace("the [next]", "[next]")
        table, _ = language.translate_table("tr", lambda system, user: json.dumps({"OFFER_VERDICT_MESSAGES": turkish}))
        self.assertNotIn("[product] için", table["OFFER_VERDICT_MESSAGES"].replace("the [product] için", ""))
        self.assertIn("the [product] için", table["OFFER_VERDICT_MESSAGES"])


class NoticeTests(unittest.TestCase):
    def test_turkish_notice_in_the_present(self):
        cases = {
            "Freya Bank'tan arıyorum ve görüşmemiz kaydedilmiştir.":
                "Freya Bank'tan arıyorum ve görüşmemiz kayıt altına alınıyor.",
            "Bu görüşme kayıt altına alınmıştır.": "Görüşmemiz kayıt altına alınıyor.",
            "Aramanız kaydedilir, iyi günler.": "Görüşmemiz kayıt altına alınıyor, iyi günler.",
        }
        for text, expected in cases.items():
            self.assertEqual(expected, present_recording_notice(text, "tr")[0])
        line, note = present_recording_notice("Aramanız kaydedilebilir.", "tr")
        self.assertEqual("Aramanız kaydedilebilir.", line)
        self.assertIn("left in the line", note)
        self.assertEqual(("Bu görüşme kaydediliyor.", ""), present_recording_notice("Bu görüşme kaydediliyor.", "tr"))

    def test_system_prompt_honesty_line_in_turkish(self):
        spec, tools = spec_of(AB, language="Turkish")
        system = build_spec_workflow(spec, tools)["system_prompt"]
        self.assertIn('"görüşmemiz kayıt altına alınıyor"', system)
        self.assertIn('"kaydedildi"', system)
        self.assertNotIn("we are recording this call", system)


class CallbackTests(unittest.TestCase):
    def test_turkish_times(self):
        spec, tools = spec_of("brief-a-reference.json", language="Turkish")
        code = code_of(build_spec_workflow(spec, tools), "callback_check")
        cases = [("yarın", "saat on birde", "11:00"), ("", "yarın saat on birde", "11:00"),
                 ("yarın", "öğleden sonra üçte", "15:00"), ("yarın", "14:30", "14:30"),
                 ("yarın", "sabah dokuz buçukta", "09:30"), ("yarın", "öğlen", "12:00")]
        for day, time, want in cases:
            variables = {"now": NOW, "callback_day_text": day, "callback_time_text": time}
            exec(_compiled(code), _sandbox([], "test", vars=variables))
            with self.subTest(time=time):
                self.assertEqual("2026-10-15", variables.get("callback_date"))
                self.assertEqual(want, variables.get("callback_time"))


class CurrencyTests(unittest.TestCase):
    def test_the_currency_word_follows_amounts(self):
        spec, tools = spec_of("brief-a-reference.json", language="Turkish", currency="TL")
        names = check_namespace(build_spec_workflow(spec, tools))
        self.assertEqual("637,50 TL", names["say_spoken_amount"](637.5))
        self.assertEqual("none", names["say_spoken_amount"](None))

    def test_english_without_currency_is_unchanged(self):
        spec, tools = spec_of("brief-a-reference.json")
        text = json.dumps(build_spec_workflow(spec, tools))
        for marker in ("CURRENCY", "SpokenName", "PRODUCT_WORDS", "turkish_clock_text"):
            self.assertNotIn(marker, text)



class SelfCheckTests(unittest.TestCase):
    def test_a_turkish_multi_product_spec_plays_every_scenario(self):
        from builder.selfcheck import play, scenarios
        spec, tools = spec_of(AB, language="Turkish", currency="TL")
        workflow = build_spec_workflow(spec, tools)
        self.assertEqual([], [s.id for s in scenarios(spec, NOW) if play(workflow, spec, s, NOW)[1]])
        # The several-product check reads Turkish dates too (T-041 had it only in the one-product check).
        self.assertIn("turkish_date_text", code_of(workflow, "check_offer"))

if __name__ == "__main__":
    unittest.main()
