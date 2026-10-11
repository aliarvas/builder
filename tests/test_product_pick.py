"""T-025: with several products, the product an offer is for comes from the customer's words or
is the product under discussion (Fix 1); a pending offer survives product_unknown and missing
(Fix 2); a loop without progress ends (Fix 4); the product fields are reset (Fix 5)."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from builder.offer_check import OFFER_PRODUCT, OFFER_PRODUCT_NAME, multi_product
from builder.workflow import build_spec_workflow
from tests.test_multi_ready import AB_SPECS, CASES, Session
from tests.test_selfcheck import SPECS, load

V2 = AB_SPECS["v2"]


def accepted(session):
    return json.loads(session.vars["offers_accepted"])


class PickTests(unittest.TestCase):
    def test_no_product_named_is_the_product_under_discussion(self):
        session = Session(V2, CASES["PUB-11"]).say(offer_date="this Friday")
        self.assertEqual(["1"], list(accepted(session)))
        session.say(offer_date="this Friday")
        self.assertEqual(["1", "2"], sorted(accepted(session)))

    def test_a_named_product_by_kind_or_by_label(self):
        session = Session(V2, CASES["PUB-11"]).say(offer_date="this Friday", offer_product_name="the car loan")
        self.assertEqual(["3"], list(accepted(session)))
        session.say(offer_date="this Friday", offer_product_name="the card ending 2288")
        self.assertEqual(["1", "3"], sorted(accepted(session)))

    def test_both_applies_the_same_date_to_each_product(self):
        # PUB-13: "both on 30 October"; the loan's latest date is 23 October.
        session = Session(V2, CASES["PUB-13"]).say(offer_date="30 October", offer_product_name="both")
        self.assertEqual(["1"], list(accepted(session)))
        self.assertEqual("date_too_late", session.vars["offer_verdict"])
        self.assertIn("Friday, 23 October", session.vars["offer_message"])
        session.say(offer_accepts_proposal="yes")
        self.assertEqual("confirm_record", session.step)
        self.assertEqual({"1": "2026-10-30", "2": "2026-10-23"},
                         {key: value["date"] for key, value in accepted(session).items()})

    def test_words_that_fit_two_open_products_are_asked_once_and_the_offer_waits(self):
        session = Session(V2, CASES["PUB-11"]).say(offer_date="this Friday")    # the card
        session.say(offer_date="next Monday", offer_product_name="the loan")    # personal or car loan?
        self.assertEqual("product_unknown", session.vars["offer_verdict"])
        self.assertEqual("next Monday", session.vars["offer_date"])              # Fix 2: kept
        self.assertEqual("offer_say", session.step)
        session.say(offer_product_name="the personal loan")                       # the date waits
        self.assertEqual({"1", "2"}, set(accepted(session)))
        self.assertEqual("2026-10-19", accepted(session)["2"]["date"])
        # Asked once per product: the same words again take the product under discussion.
        session.say(offer_date="next Monday", offer_product_name="the loan")
        self.assertEqual({"1", "2", "3"}, set(accepted(session)))

    def test_the_product_fields_are_reset_after_every_check(self):
        session = Session(V2, CASES["PUB-11"]).say(offer_date="this Friday", offer_product_name="the card",
                                                   offer_product_number=1)
        self.assertEqual((0, ""), (session.vars[OFFER_PRODUCT], session.vars[OFFER_PRODUCT_NAME]))

    def test_a_missing_date_keeps_the_amount(self):
        session = Session(V2, CASES["PUB-11"]).say(offer_date="when I can", offer_amount=100.0,
                                                   offer_amount_kind="other")
        self.assertEqual("missing", session.vars["offer_verdict"])
        self.assertEqual(100.0, session.vars["offer_amount"])
        self.assertEqual("", session.vars["offer_date"])


class LoopGuardTests(unittest.TestCase):
    def test_no_progress_ends_with_the_offers_there_are(self):
        session = Session(V2, CASES["PUB-11"]).say(offer_date="this Friday")
        session.vars["offer_no_progress"] = 4
        session.say(offer_date="when I can")
        self.assertEqual("ready", session.vars["offer_progress"])
        self.assertEqual("confirm_record", session.step)

    def test_no_progress_without_an_offer_is_the_limit(self):
        session = Session(V2, CASES["PUB-11"])
        session.vars["offer_no_progress"] = 4
        session.say(offer_date="when I can")
        self.assertEqual("limit", session.vars["offer_progress"])
        self.assertEqual("closing", session.step)

    def test_progress_resets_the_counter(self):
        session = Session(V2, CASES["PUB-11"]).say(offer_date="when I can")
        self.assertEqual(1, session.vars["offer_no_progress"])
        session.say(offer_date="this Friday")
        self.assertEqual(0, session.vars["offer_no_progress"])


class SingleProductRenderTests(unittest.TestCase):
    def test_specs_without_per_product_handling_render_identically(self):
        seen = 0
        for name, (path, tools) in SPECS.items():
            spec = load(path)
            if multi_product(spec):
                continue
            seen += 1
            with self.subTest(spec=name):
                now = build_spec_workflow(spec, tools)
                with mock.patch("builder.offer_check.multi_product", lambda spec: False), \
                        mock.patch("builder.product_notes.multi_product", lambda spec: False):
                    before = build_spec_workflow(spec, tools)
                self.assertEqual(json.dumps(before, sort_keys=True), json.dumps(now, sort_keys=True))
                self.assertNotIn(OFFER_PRODUCT_NAME, json.dumps(now))
        self.assertGreaterEqual(seen, 5)

    def test_specs_with_per_product_handling_get_the_name_field(self):
        spec = load(SPECS["spec-brief-b.json"][0])
        nodes = build_spec_workflow(spec, SPECS["spec-brief-b.json"][1])["nodes"]
        for key in ("negotiate", "offer_say", "revise_ask"):
            names = [field["name"] for field in nodes[key]["extraction_schema"]]
            self.assertEqual(names.index(OFFER_PRODUCT) + 1, names.index(OFFER_PRODUCT_NAME), key)


if __name__ == "__main__":
    unittest.main()
