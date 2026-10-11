"""NOW-CASES: expected promise dates for a call variable ``now``, worked out from the spec's
calendar data (holidays, non-business weekdays, earliest and latest rules, amount floors).

This is test code and deliberately independent of ``builder/offer_check.py``: it reads the
spec, not the generated code, so a case checks the code against the spec's own rules.
"""

from __future__ import annotations


from builder.selfcheck_calendar import MONTHS, WEEKDAYS, SpecCalendar, first_rule as _first, matches as _matches  # noqa: F401


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
