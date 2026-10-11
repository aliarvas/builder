"""T-031 (review of T-026..T-030): product words and the goodbye after an accepted offer.

HIGH 1: words that name a product other than by its full kind ("the car", "the loans", "both
loans") were booked on the product under discussion or on every product. HIGH 2: a second
goodbye after the read-back dropped the accepted offer and wrote a refused note on it.
MEDIUM 5: refusals by plural or short words were not counted, and a copied refusal counted
again. The words below are the public PUB-11/PUB-12 products' kinds; the builder matches
them only through the product data."""

from __future__ import annotations

import json
import re
import unittest
from unittest import mock

from builder import goodbye, offer_check
from builder.offer_check import (
    MULTI_CHECK_BODY, MULTI_REFUSAL_BODY, PRELUDE, PRODUCT_PICK_BODY, _full_config, _multi_config, _py_literal,
)
from builder.selfcheck import run_selfcheck
from builder.workflow import build_spec_workflow
from tests.test_live_v19 import fixture
from tests.test_selfcheck import KIT_TOOLS, NOW

PRODUCTS = fixture("pub-12-extractions.json")["products"]

# Customer's words -> (products an offer is for, ask first), products a refusal counts.
WORDS = {
    "the car": ([3], False, [3]),
    "my car payment": ([3], False, [3]),
    "the cars": ([3], False, [3]),
    "the loans": ([2, 3], False, [2, 3]),
    "both loans": ([2, 3], False, [2, 3]),
    "my vehicle": ([], True, []),
    "the car loan": ([3], False, [3]),
    "the personal one": ([2], False, [2]),
    "the second one": ([2], False, [2]),
    "the card": ([1], False, [1]),
    "credit cards": ([1], False, [1]),
    "the credit card ending 9015": ([1], False, [1]),
    "the card and the car loan": ([1, 3], False, [1, 3]),
    "all of them": ([1, 2, 3], False, [1, 2, 3]),
    "this one": ([1], False, []),
    "it": ([1], False, []),
    "friday": ([1], False, []),
    # "both" with three open products: one question; a refusal is the product under discussion.
    "both": ([], True, [1]),
    # One shared kind word in the singular: one question; a refusal counts both products of it.
    "the loan": ([], True, [2, 3]),
    "the others": ([], True, [1, 2, 3]),
}


def picker(spec, body=PRODUCT_PICK_BODY):
    config = _full_config(spec, [])
    config.update(_multi_config(spec))
    names = {"vars": {}, "json": json}
    exec(PRELUDE.replace("__CONFIG__", _py_literal(config)).replace("__PRODUCT_READER__", "") + body, names)
    names["accepted_offers"] = lambda: {}
    return names, config


class ProductWordTests(unittest.TestCase):
    """HIGH 1 and MEDIUM 5: the words -> products table of the review."""

    def multi_spec(self):
        # The public A+B extraction with per-product refusals (the PUB-12 spec shape).
        from tests.test_selfcheck import SPECS, load
        return load(SPECS["brief-ab-extracted-v2.json"][0])

    def test_words_name_the_products_they_say(self):
        spec = self.multi_spec()
        self.assertTrue(_multi_config(spec)["refused_name_var"])
        for words, (offer, ask, refused) in WORDS.items():
            with self.subTest(words=words):
                names, config = picker(spec)
                names["vars"][config["product_name_var"]] = words
                names["vars"][config["refused_name_var"]] = words
                self.assertEqual((offer, ask), names["pick_products"](PRODUCTS))
                self.assertEqual(refused, names["refused_numbers"](PRODUCTS, []))

    def test_both_means_the_two_open_products(self):
        names, config = picker(self.multi_spec())
        names["accepted_offers"] = lambda: {"1": {"date": "2026-10-16"}}
        names["vars"][config["product_name_var"]] = "both"
        self.assertEqual(([2, 3], False), names["pick_products"](PRODUCTS))

    def test_unknown_words_ask_once_then_the_product_under_discussion(self):
        names, config = picker(self.multi_spec())
        for expected in (([], True), ([1], False)):
            names["vars"][config["product_name_var"]] = "my vehicle"
            self.assertEqual(expected, names["pick_products"](PRODUCTS))

    def test_a_copied_refusal_counts_once(self):
        names, config = picker(self.multi_spec())
        refused = config["refused_name_var"]
        said = []
        for words in ("the car loan", "the car loan", "", "the car loan"):
            names["vars"][refused] = words
            said.append(names["refusal_repeated"]())
        self.assertEqual([False, True, False, False], said)

    def test_the_v19_matcher_booked_the_wrong_products(self):
        old = PRODUCT_PICK_BODY.replace("singular(word) for word in raw", "word for word in raw").replace(
            "not plausible and names_a_product(words)", "False")
        names, config = picker(self.multi_spec(), old)
        for words, wrong in (("the loans", ([1], False)), ("my vehicle", ([1], False))):
            names["vars"][config["product_name_var"]] = words
            self.assertEqual(wrong, names["pick_products"](PRODUCTS))


class GoodbyeAfterAcceptTests(unittest.TestCase):
    """HIGH 2 and LOW 3."""

    def run_goodbye(self, accepted, text, said="", rejected=False):
        from tests.test_selfcheck import SPECS, load
        spec = load(SPECS["brief-ab-extracted-v2.json"][0])
        variables = {"offers_accepted_count": accepted, "readback_text": text,
                     goodbye.GOODBYE_READBACK: said, "identity_verified": "true"}
        if rejected:
            confirmation = spec.confirmation.data
            variables[confirmation["intent_variable"]] = confirmation["revise_values"][0]
        exec(goodbye.goodbye_code(spec), {"vars": variables})
        return variables[goodbye.GOODBYE_ROUTE]

    def test_read_back_once_per_text_then_close(self):
        # T-037 (CTO): the goodbye after the read-back closes and records nothing.
        self.assertEqual("readback", self.run_goodbye(1, "I can record A. Do you confirm?"))
        self.assertEqual("close", self.run_goodbye(1, "I can record A. Do you confirm?",
                                                   said="I can record A. Do you confirm?"))
        # A new accepted offer gives a new read-back: it is said again.
        self.assertEqual("readback", self.run_goodbye(2, "I can record A and B. Do you confirm?",
                                                      said="I can record A. Do you confirm?"))

    def test_a_rejected_read_back_is_never_recorded_on_a_goodbye(self):
        text = "I can record A. Do you confirm?"
        self.assertEqual("close", self.run_goodbye(1, text, said=text, rejected=True))
        self.assertEqual("close", self.run_goodbye(1, text, rejected=True))

    def test_no_read_back_text_closes(self):
        self.assertEqual("close", self.run_goodbye(1, ""))
        self.assertEqual("close", self.run_goodbye(0, ""))

    def test_there_is_no_record_route(self):
        # T-037 (CTO): no promise is recorded without an explicit yes to the read-back.
        from tests.test_selfcheck import SPECS, load
        spec = load(SPECS["brief-ab-extracted-v2.json"][0])
        workflow = build_spec_workflow(spec, KIT_TOOLS)
        targets = {transition["condition"].get("operand"): transition["target_node"]
                   for transition in workflow["nodes"][goodbye.CUSTOMER_GOODBYE]["transitions"]}
        self.assertEqual("confirm_record", targets["readback"])
        self.assertNotIn("record", targets)
        self.assertNotIn("record_next", targets.values())


class SelfCheckTests(unittest.TestCase):
    """The scenario families the review asked for, and that they catch the v19 behaviour."""

    def failed(self, spec, workflow=None):
        workflow = workflow or build_spec_workflow(spec, KIT_TOOLS)
        return {item.scenario: item.reason for item in run_selfcheck(spec, workflow, NOW).results if not item.passed}

    def spec(self):
        from tests.test_selfcheck import SPECS, load
        return load(SPECS["brief-ab-extracted-v2.json"][0])

    def test_the_families_run_and_pass(self):
        spec = self.spec()
        names = {item.scenario for item in run_selfcheck(spec, build_spec_workflow(spec, KIT_TOOLS), NOW).results}
        for name in ("product_words_kind_word", "product_words_plural", "product_words_both_kind",
                     "product_words_refused_plural", "product_words_unknown_name", "goodbye_readback_then_goodbye"):
            self.assertIn(name, names)
        self.assertFalse({name for name in self.failed(spec) if name.startswith(("product_words", "goodbye"))})

    def test_the_v19_matcher_fails_the_family(self):
        spec = self.spec()
        old = PRODUCT_PICK_BODY.replace("singular(word) for word in raw", "word for word in raw").replace(
            "not plausible and names_a_product(words)", "False")
        with mock.patch.object(offer_check, "PRODUCT_PICK_BODY", old):
            failed = self.failed(spec)
        self.assertIn("product_words_plural", failed)
        self.assertIn("product_words_unknown_name", failed)

    def test_the_v19_goodbye_fails_and_names_the_false_note(self):
        # v19: the goodbye closed and the note loop wrote the refused reason on the accepted product.
        spec = self.spec()
        code = goodbye.goodbye_code

        def v19(spec):
            return code(spec).replace("        for number in offers:", "        for number in []:")

        with mock.patch.object(goodbye, "goodbye_code", v19):
            failed = self.failed(spec)
        self.assertIn("goodbye_readback_then_goodbye", failed)
        self.assertRegex(failed["goodbye_readback_then_goodbye"], "which the customer accepted")


class NeutralCodeTests(unittest.TestCase):
    def test_no_product_kind_words_in_generated_code(self):
        # LOW 4: the generated code's comments use neutral examples.
        kinds = {word for product in PRODUCTS for word in re.split(r"[^a-z]+", str(product["type"]))
                 if len(word) >= 3}
        for name in ("PRELUDE", "PRODUCT_PICK_BODY", "MULTI_CHECK_BODY", "MULTI_REFUSAL_BODY", "CHECK_BODY"):
            text = getattr(offer_check, name).lower()
            with self.subTest(body=name):
                self.assertFalse({word for word in kinds if re.search(r"\b" + word + r"s?\b", text)})
        self.assertTrue(MULTI_CHECK_BODY and MULTI_REFUSAL_BODY)


if __name__ == "__main__":
    unittest.main()
