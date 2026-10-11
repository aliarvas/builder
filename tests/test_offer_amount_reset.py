"""F-060: check_offer must reset the float offer_amount with a value the platform accepts.

The platform rejects a write whose value does not fit the extraction field's type and keeps
the old value (F-052, live). ``PlatformCall`` applies that rule after every code step.
"""

from __future__ import annotations

import copy
import json
import unittest

from builder.offer_check import AMOUNT_NONE_VALUE, OFFER_AMOUNT, OFFER_PROPOSED_KIND
from builder.selfcheck import fits as selfcheck_fits
from builder.spec import parse_spec
from builder.workflow import build_spec_workflow
from tests.test_offer_date_only import CARD, FIXTURE_A, LOAN, NOW, TOOLS, code_of


# The platform rule for typed writes lives in the builder's simulator (T-010).
fits = selfcheck_fits


class PlatformCall:
    """Runs the offer code like the platform: invalid typed writes are rejected and logged."""

    def __init__(self, products=(CARD,)):
        spec = parse_spec(copy.deepcopy(FIXTURE_A))
        self.nodes = build_spec_workflow(spec, TOOLS)["nodes"]
        self.fields = {field["name"]: field for node in self.nodes.values()
                       for field in node.get("extraction_schema") or []}
        self.vars = {spec.account.data["products_variable"]: json.dumps(list(products)), "now": NOW}
        self.rejected = []
        self.run("offer_setup")

    def run(self, key):
        before = dict(self.vars)
        exec(code_of(self.nodes[key]), {"vars": self.vars})
        for name, field in self.fields.items():
            if name in self.vars and self.vars.get(name) != before.get(name) and not fits(self.vars[name], field):
                self.rejected.append((key, name, self.vars[name]))
                if name in before:
                    self.vars[name] = before[name]
                else:
                    del self.vars[name]

    def turn(self, **extracted):
        # Extraction writes only the fields it found in the customer's last message.
        self.vars.update(extracted)
        self.run("check_offer")
        return self.vars


class StaleAmountTests(unittest.TestCase):
    def test_no_typed_write_is_rejected(self):
        call = PlatformCall(products=(CARD, LOAN))
        call.turn(offer_date="2026-10-16", offer_amount=10.0, offer_product_number=1)
        call.turn(offer_date="2026-10-16", offer_product_number=1)
        call.turn(offer_date="2026-10-20", offer_amount=300.0, offer_product_number=2)
        self.assertEqual([], call.rejected)

    def test_date_only_after_a_refused_amount_takes_the_proposed_amount(self):
        # The customer offers 10 (below the 28.50 floor); the check proposes the floor. The
        # customer then names only a date: the floor applies, not the stale 10.
        call = PlatformCall()
        first = call.turn(offer_date="2026-10-16", offer_amount=10.0, offer_product_number=1)
        self.assertEqual("amount_too_low", first["offer_verdict"])
        self.assertEqual("minimum", first[OFFER_PROPOSED_KIND])
        second = call.turn(offer_date="2026-10-19", offer_product_number=1)
        self.assertEqual("ok", second["offer_verdict"], second["offer_message"])
        self.assertIn("28.50 on Monday, 19 October", second["offers_summary"])

    def test_a_new_amount_still_counts(self):
        call = PlatformCall()
        call.turn(offer_date="2026-10-16", offer_amount=10.0, offer_product_number=1)
        result = call.turn(offer_date="2026-10-19", offer_amount=120.0, offer_product_number=1)
        self.assertEqual("amount_too_high", result["offer_verdict"])

    def test_reset_value_reads_as_no_amount(self):
        call = PlatformCall()
        call.turn(offer_date="2026-10-16", offer_amount=10.0, offer_product_number=1)
        self.assertEqual(AMOUNT_NONE_VALUE, call.vars[OFFER_AMOUNT])
        for stored in (AMOUNT_NONE_VALUE, "-1.0", "-1"):
            with self.subTest(stored=stored):
                fresh = PlatformCall()
                result = fresh.turn(offer_date="2026-10-16", offer_amount=stored, offer_product_number=1)
                self.assertEqual("ok", result["offer_verdict"])  # the proposed full amount, 95
                self.assertIn("95 on Friday, 16 October", result["offers_summary"])


if __name__ == "__main__":
    unittest.main()


class PeriodAnswerTests(unittest.TestCase):
    def test_a_named_period_is_asked_for_the_exact_day(self):
        # F-060 LOW: the customer named a period, so the line does not say it was not heard.
        from tests.test_offer_date_only import Call
        from builder.spoken import agent_directed

        for phrase in ("the week after next", "sometime next month", "mmh"):
            with self.subTest(phrase=phrase):
                result = Call().turn(offer_date=phrase, offer_product_number=1)
                self.assertEqual("missing", result["offer_verdict"])
                message = result["offer_message"]
                self.assertEqual("Could you tell me the exact day you would like to pay?", message)
                self.assertNotIn("did not catch", message)
                self.assertEqual("", agent_directed(message))


class RejectionSignatureTests(unittest.TestCase):
    """F-060 fix (review finding 1): a repeated invalid offer is not a new rejection."""

    def test_two_identical_date_only_invalid_offers_count_once(self):
        call = PlatformCall()
        first = call.turn(offer_date="2026-11-30", offer_product_number=1)
        self.assertEqual("date_too_late", first["offer_verdict"])
        self.assertEqual(AMOUNT_NONE_VALUE, call.vars[OFFER_AMOUNT])  # the reset really happened
        second = call.turn(offer_date="2026-11-30", offer_product_number=1)
        self.assertEqual("date_too_late", second["offer_verdict"])
        self.assertEqual(1, second["offer_rejections"])
        self.assertNotEqual("more", second["offer_progress"])
        self.assertEqual("[]", second["offers_noted"].replace(" ", ""))

    def test_same_offer_in_other_words_counts_once_and_a_new_offer_counts(self):
        call = PlatformCall()
        call.turn(offer_date="2026-11-30", offer_amount=95.0, offer_product_number=1)
        # The same day and the same (full) amount, said as a date alone.
        self.assertEqual(1, call.turn(offer_date="2026-11-30", offer_product_number=1)["offer_rejections"])
        # A different day is a new offer.
        self.assertEqual(2, call.turn(offer_date="2026-12-01", offer_product_number=1)["offer_rejections"])
