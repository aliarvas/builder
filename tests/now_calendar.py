"""NOW-CASES: expected promise dates for a call variable ``now``, worked out from the spec's
calendar data (holidays, non-business weekdays, earliest and latest rules, amount floors).

This is test code and deliberately independent of ``builder/offer_check.py``: it reads the
spec, not the generated code, so a case checks the code against the spec's own rules.
"""

from __future__ import annotations

import datetime
import re

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december")


def _matches(when, product):
    for item in when or ():
        value = product.get(item["field"])
        if "equals" in item and value != item["equals"]:
            return False
        if "in" in item and value not in item["in"]:
            return False
        if "min" in item and (value is None or value < item["min"]):
            return False
        if "max" in item and (value is None or value > item["max"]):
            return False
    return True


def _first(rules, product):
    rules = rules if isinstance(rules, list) else [rules]
    return next((rule for rule in rules if rule and _matches(rule.get("when"), product)), None)


class SpecCalendar:
    """The spec's date and amount rules for one ``now`` (ISO date and time)."""

    def __init__(self, spec, now):
        offer = spec["offer"]
        self.offer = offer
        self.today = datetime.date.fromisoformat(now[:10])
        self.holidays = {datetime.date.fromisoformat(day) for day in offer.get("holidays", [])}
        # ISO weekday numbers (Monday 1 ... Sunday 7), as the spec gives them.
        self.weekend = set(offer.get("non_business_weekdays", []))

    def is_business(self, day):
        return day.isoweekday() not in self.weekend and day not in self.holidays

    def next_business(self, day):
        while not self.is_business(day):
            day += datetime.timedelta(days=1)
        return day

    def add(self, start, days, unit):
        """``days`` calendar or business days after ``start`` (``start`` itself not counted)."""
        if unit == "calendar":
            return start + datetime.timedelta(days=days)
        day, counted = start, 0
        while counted < days:
            day += datetime.timedelta(days=1)
            if self.is_business(day):
                counted += 1
        return day

    def earliest(self):
        rule = self.offer.get("earliest") or {"days": 0, "unit": "calendar"}
        return self.add(self.today, rule["days"], rule["unit"])

    def deadline(self, product):
        rule = _first(self.offer.get("latest"), product)
        day = self.add(self.today, rule["days"], rule["unit"])
        if not self.is_business(day) and self.offer.get("latest_on_non_business_day") == "previous":
            while not self.is_business(day):
                day -= datetime.timedelta(days=1)
        return day

    def floor(self, product):
        return float(product[_first(self.offer.get("min_amount"), product)["field"]])

    def full(self, product):
        return float(product[_first(self.offer.get("max_amount"), product)["field"]])

    def resolve(self, phrase):
        """What a customer's day words mean (the spec's reading of "next <weekday>")."""
        text = phrase.lower().strip()
        if text == "today":
            return self.today
        if text == "tomorrow":
            return self.today + datetime.timedelta(days=1)
        monday = self.today - datetime.timedelta(days=self.today.weekday())
        for index, name in enumerate(WEEKDAYS):
            if text == "this " + name:
                return monday + datetime.timedelta(days=index)
            if text == "next " + name:
                assert self.offer.get("next_weekday") == "following_week", "only the following-week reading"
                return monday + datetime.timedelta(days=7 + index)
        match = re.fullmatch(r"(\d{1,2}) (\w+)", text)
        if match and match.group(2) in MONTHS:
            day = datetime.date(self.today.year, MONTHS.index(match.group(2)) + 1, int(match.group(1)))
            return day if day >= self.today else day.replace(year=day.year + 1)
        raise ValueError(f"no reading for {phrase!r}")

    def outcome(self, phrase, product):
        """(date the customer ends up with, why): the named day, or the day the rules offer
        instead when the customer accepts it (a non-business day moves to the next business
        day; a day after the deadline becomes the deadline)."""
        day = self.resolve(phrase)
        deadline = self.deadline(product)
        if day < self.earliest():
            return self.earliest(), "before the earliest date"
        if day > deadline:
            return deadline, "after the deadline"
        if self.offer.get("promise_date_must_be_business_day") and not self.is_business(day):
            moved = self.next_business(day)
            if moved > deadline:
                return deadline, "not a business day; the next one is after the deadline"
            return moved, "not a business day"
        return day, "allowed"


def expected_ledger(case, spec):
    """The promises a case should record on ``spec``: one per accepted offer, from its turns."""
    calendar = SpecCalendar(spec, case["variables"]["now"])
    products = case["products"]
    promises, notes = {}, []
    for turn in case["turns"]:
        number = turn["product"]
        product = products[number - 1]
        if turn["kind"] == "offer":
            day, _ = calendar.outcome(turn["date"], product)
            amount = calendar.floor(product) if turn.get("amount_kind") == "minimum" else calendar.full(product)
            promises[number] = {"product_id": f"p{number}", "amount": amount, "date": day.isoformat()}
        elif turn["kind"] == "refuse":
            notes.append({"product_id": f"p{number}", "reason": spec["closing"]["product_notes"]["refused_reason"]})
    return {"promises": [promises[number] for number in sorted(promises)], "notes": notes}
