"""Expected promise dates and amounts from the spec's calendar data (T-010, from NOW-CASES).

Deliberately independent of ``offer_check.py``: it reads the spec (holidays, non-business
weekdays, earliest and latest rules, amount floors), not the generated code, so the
self-check compares the code with the spec's own rules.
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from .spec import OFFER_ADJUST, OFFER_NEXT_WEEKDAY, OFFER_UNITS

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december")
BUSINESS, CALENDAR = OFFER_UNITS
PREVIOUS, NEXT, KEEP = OFFER_ADJUST
FOLLOWING_WEEK = OFFER_NEXT_WEEKDAY[0]


def matches(when: Any, product: dict[str, Any]) -> bool:
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


def first_rule(rules: Any, product: dict[str, Any]) -> dict[str, Any] | None:
    rules = rules if isinstance(rules, list) else [rules]
    return next((rule for rule in rules if rule and matches(rule.get("when"), product)), None)


def _offer(spec: Any) -> dict[str, Any]:
    """The offer data of a spec dict or of a parsed spec."""
    offer = getattr(spec, "offer", None)
    if offer is not None and hasattr(offer, "data"):
        return offer.data
    return spec["offer"]


class SpecCalendar:
    """The spec's date and amount rules for one ``now`` (ISO date and time)."""

    def __init__(self, spec: Any, now: str) -> None:
        offer = _offer(spec)
        self.offer = offer
        self.today = datetime.date.fromisoformat(now[:10])
        self.holidays = {datetime.date.fromisoformat(day) for day in offer.get("holidays", [])}
        # ISO weekday numbers (Monday 1 ... Sunday 7), as the spec gives them.
        self.weekend = set(offer.get("non_business_weekdays", []))

    def is_business(self, day: datetime.date) -> bool:
        return day.isoweekday() not in self.weekend and day not in self.holidays

    def next_business(self, day: datetime.date) -> datetime.date:
        while not self.is_business(day):
            day += datetime.timedelta(days=1)
        return day

    def add(self, start: datetime.date, days: int, unit: str) -> datetime.date:
        """``days`` calendar or business days after ``start`` (``start`` itself not counted)."""
        if unit == CALENDAR:
            return start + datetime.timedelta(days=days)
        day, counted = start, 0
        while counted < days:
            day += datetime.timedelta(days=1)
            if self.is_business(day):
                counted += 1
        return day

    def earliest(self) -> datetime.date:
        rule = self.offer.get("earliest") or {"days": 0, "unit": CALENDAR}
        return self.add(self.today, rule["days"], rule["unit"])

    def deadline(self, product: dict[str, Any]) -> datetime.date:
        rule = first_rule(self.offer.get("latest"), product)
        day = self.add(self.today, rule["days"], rule["unit"])
        # A calendar-day deadline on a non-business day moves back (previous), forward (next)
        # or stays (keep); a business-day count already ends on a business day.
        step = {PREVIOUS: -1, NEXT: 1}.get(self.offer.get("latest_on_non_business_day"), 0)
        while step and not self.is_business(day):
            day += datetime.timedelta(days=step)
        return day

    @staticmethod
    def _amount(rule: dict[str, Any], product: dict[str, Any]) -> float:
        """An amount rule: a fixed ``value`` or a product ``field``, times ``share`` if given."""
        base = float(rule["value"]) if "value" in rule else float(product[rule["field"]])
        return round(base * float(rule.get("share", 1)), 2)

    def floor(self, product: dict[str, Any]) -> float:
        return self._amount(first_rule(self.offer.get("min_amount"), product), product)

    def full(self, product: dict[str, Any]) -> float:
        return self._amount(first_rule(self.offer.get("max_amount"), product), product)

    def first_allowed(self, product: dict[str, Any]) -> datetime.date | None:
        """The first day the rules accept for ``product``, or None when there is none."""
        day, deadline = self.earliest(), self.deadline(product)
        if self.offer.get("promise_date_must_be_business_day"):
            day = self.next_business(day)
        return day if day <= deadline else None

    def resolve(self, phrase: str) -> datetime.date:
        """What a customer's day words mean (the spec's reading of "next <weekday>")."""
        text = phrase.lower().strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return datetime.date.fromisoformat(text)
        if text == "today":
            return self.today
        if text == "tomorrow":
            return self.today + datetime.timedelta(days=1)
        monday = self.today - datetime.timedelta(days=self.today.weekday())
        for index, name in enumerate(WEEKDAYS):
            if text == "this " + name:
                return monday + datetime.timedelta(days=index)
            if text == "next " + name:
                assert self.offer.get("next_weekday") == FOLLOWING_WEEK, "only the following-week reading"
                return monday + datetime.timedelta(days=7 + index)
        match = re.fullmatch(r"(\d{1,2}) (\w+)", text)
        if match and match.group(2) in MONTHS:
            day = datetime.date(self.today.year, MONTHS.index(match.group(2)) + 1, int(match.group(1)))
            return day if day >= self.today else day.replace(year=day.year + 1)
        raise ValueError(f"no reading for {phrase!r}")

    def outcome(self, phrase: str, product: dict[str, Any]) -> tuple[datetime.date, str]:
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
