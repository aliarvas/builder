"""NOW-CASES (SELF-TEST "different now"): public cases replayed on other ``now`` values.

``tests/fixtures/now-cases.json`` holds the cases: the public case's products and customer
turns, a new ``now`` and the expected ledger. The expected dates come from the spec calendar
(``tests/now_calendar.py``, independent of the builder code), and some are checked by hand
below. Each case is then walked offline through the rendered Brief A and A+B (v2) workflows
with the ``Session`` simulator of ``test_multi_ready``.
"""

from __future__ import annotations

import datetime
import json
import unittest

from builder.offer_check import ACCEPTS_YES, OFFER_ACCEPTS, OFFER_AMOUNT_KIND
from tests.now_calendar import SpecCalendar, expected_ledger
from tests.test_multi_ready import AB_SPECS, CASES, ROOT, Session, load

NOW_CASES = json.loads((ROOT / "tests/fixtures/now-cases.json").read_text(encoding="utf-8"))["cases"]
SPECS = {"A": ROOT / "tests/fixtures/spec-brief-a.json", "AB-v2": AB_SPECS["v2"]}
# Brief A cases run on both specs; Brief B (multi-product) cases need the A+B spec.
RUNS_ON = {"A": ("A", "AB-v2"), "B": ("AB-v2",)}


def walk(spec_path, case):
    """Play the customer turns, confirm once, record (with the case's bank answers), close."""
    session = Session(spec_path, case)
    verdicts = []
    for turn in case["turns"]:
        number = turn["product"]
        if turn["kind"] == "offer":
            extra = {OFFER_AMOUNT_KIND: turn["amount_kind"]} if turn.get("amount_kind") else {}
            session.say(offer_date=turn["date"], offer_product_number=number, **extra)
        elif turn["kind"] == "accept":
            session.say(offer_date="", offer_product_number=number, **{OFFER_ACCEPTS: ACCEPTS_YES})
        else:
            session.end_product()
        verdicts.append((session.vars.get("offer_verdict"), session.vars.get("offer_suggested_date")))
    return session, verdicts


class NowCaseFileTests(unittest.TestCase):
    def test_cases_cover_several_nows_and_keep_the_public_products(self):
        nows = {case["variables"]["now"] for case in NOW_CASES}
        self.assertGreaterEqual(len(nows), 3)
        for case in NOW_CASES:
            base = CASES[case["base"]]
            with self.subTest(case=case["id"]):
                self.assertEqual(base["products"], case["products"])
                self.assertEqual(base["brief"], case["brief"])
                self.assertNotEqual(base["variables"]["now"], case["variables"]["now"])
                self.assertTrue(case["description"])

    def test_expected_ledger_is_the_spec_calendar(self):
        # The file's dates are not typed by hand: they are what the spec's rules give.
        for case in NOW_CASES:
            for name in RUNS_ON[case["brief"]]:
                spec = load(SPECS[name])
                with self.subTest(case=case["id"], spec=name):
                    expected = expected_ledger(case, spec)
                    self.assertEqual(expected["promises"], case["expected"]["promises"])
                    self.assertEqual(expected["notes"], case["expected"]["notes"])

    def test_some_dates_checked_by_hand(self):
        spec = load(SPECS["AB-v2"])
        date = datetime.date.fromisoformat
        friday = SpecCalendar(spec, "2026-10-16T11:00")
        self.assertEqual(date("2026-10-19"), friday.outcome("tomorrow", {"days_late": 6})[0])  # Saturday -> Monday
        # 7 business days from Friday 16 October: 19-23, 26 October is a holiday, 27, 28.
        self.assertEqual(date("2026-10-28"), friday.deadline({"days_late": 14}))
        holiday_week = SpecCalendar(spec, "2026-11-09T11:00")
        self.assertEqual(date("2026-11-12"), holiday_week.outcome("this wednesday", {"days_late": 5})[0])
        # 12 business days from Monday 9 November: 11 and 26 November are holidays.
        self.assertEqual(date("2026-11-27"), holiday_week.deadline({"days_late": 4}))
        self.assertEqual(date("2026-11-19"), holiday_week.deadline({"days_late": 20}))
        year_end = SpecCalendar(spec, "2026-12-30T11:00")
        self.assertEqual(date("2027-01-01"), year_end.resolve("this friday"))
        self.assertEqual(date("2027-01-04"), year_end.outcome("this friday", {"days_late": 8})[0])
        # 31 December, (1 January holiday), 4-8 January, 11 January.
        self.assertEqual(date("2027-01-11"), year_end.deadline({"days_late": 14}))
        self.assertEqual(date("2027-01-20"), year_end.resolve("20 january"))  # rolls into next year


class NowCaseLedgerTests(unittest.TestCase):
    def test_each_case_reaches_the_expected_ledger(self):
        for case in NOW_CASES:
            for name in RUNS_ON[case["brief"]]:
                with self.subTest(case=case["id"], spec=name):
                    session, verdicts = walk(SPECS[name], case)
                    self.assertEqual("confirm_record", session.step, verdicts)
                    session.record_all(case["record_answers"])
                    expected = case["expected"]
                    want = sorted((p["product_id"], float(p["amount"]), p["date"]) for p in expected["promises"])
                    self.assertEqual(want, session.ledger_promises())
                    # One call per promise, plus one retry per failed answer.
                    self.assertEqual(len(want) + case["record_answers"].count(False), len(session.calls))
                    outcome, reason = session.close()
                    self.assertEqual((expected["outcome"], expected["reason"]), (outcome, reason or None))
                    want_notes = sorted((n["product_id"], n["reason"]) for n in expected["notes"])
                    self.assertEqual(want_notes, session.ledger_notes())
                    self.assertEqual([], session.rejected)

    def test_the_check_names_the_date_the_calendar_gives(self):
        # A non-business day and a day after the deadline: the check rejects it and proposes
        # exactly the day the spec calendar gives (the customer then accepts it).
        verdict_for = {"not a business day": "date_not_business_day", "after the deadline": "date_too_late",
                       "allowed": "ok"}
        for case in NOW_CASES:
            for name in RUNS_ON[case["brief"]]:
                spec = load(SPECS[name])
                calendar = SpecCalendar(spec, case["variables"]["now"])
                _, verdicts = walk(SPECS[name], case)
                for turn, (verdict, suggested) in zip(case["turns"], verdicts):
                    if turn["kind"] != "offer":
                        continue
                    day, why = calendar.outcome(turn["date"], case["products"][turn["product"] - 1])
                    with self.subTest(case=case["id"], spec=name, turn=turn["date"]):
                        if why == "allowed":
                            self.assertEqual("ok", verdict)
                        else:
                            self.assertEqual(verdict_for[why], verdict)
                            self.assertEqual(day.isoformat(), suggested)


if __name__ == "__main__":
    unittest.main()
