"""Test helpers: turn a written spec into the four extraction replies, and a fake model client."""

from __future__ import annotations

import copy
import json
import threading
from typing import Any

from builder.extract import DERIVED_REQUIRED_STATES
from builder.llm import LLMResult


def groups_from_spec(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The replies a perfect extraction would return for ``spec`` (intermediate shape)."""
    s = copy.deepcopy(spec)
    pairs = {state: (row["outcome"], row["reason"]) for row in s["outcomes"] for state in row["on"]}

    def entries(values, route_of, prefix, with_pairs=True):
        result = []
        for value in values:
            entry = {"value": value, "meaning": value.replace("_", " "), "route": route_of(value), "source": "recorded"}
            if with_pairs and entry["route"] == "end":
                entry["outcome"], entry["reason"] = pairs[prefix + value]
            result.append(entry)
        return result

    o, t, n, c = s["opening"], s["third_party"], s["negotiation"], s["confirmation"]
    opening = {key: o[key] for key in (
        "rules", "confirmation_question", "unclear_instruction", "forbidden_before_verification",
        "address_with", "max_unclear_asks",
    )}
    opening["answers"] = entries(o["who_answered_options"], lambda v: (
        "verify" if v in o["identity_values"] else "other_person" if v in o["third_party_values"]
        else "ask_again" if v in o["stay_values"] else "end"
    ), "opening:")
    return {
        "opening_identity": {
            "agent": s["agent"],
            "opening": opening,
            "third_party": {"rules": t["rules"], "intents": entries(
                t["intent_values"], lambda v: "end" if v in t["close_values"] else "stay", "third_party:")},
            "identity": {key: value for key, value in s["identity"].items()},
            "global_rules": s["global_rules"],
            "sources": {"opening.max_unclear_asks": "recorded"},
            "overrides": [],
        },
        "flow": {
            "account": {key: s["account"][key] for key in ("rules", "products_field", "product_id_field")},
            "negotiation": {"rules": n["rules"], "intents": entries(n["intent_values"], lambda v: (
                "readback" if v in n["confirm_values"] else "end" if v in n["close_values"] else "stay"
            ), "negotiation:")},
            "confirmation": {
                **{key: c[key] for key in (
                    "rules", "promise_product_id_field", "promise_date_field", "promise_amount_field",
                    "max_attempts_per_product",
                )},
                "intents": entries(c["intent_values"], lambda v: "change" if v in c["revise_values"] else "record",
                                   "", with_pairs=False),
            },
            "sources": {}, "overrides": [],
        },
        "offer": {"offer": s["offer"], "sources": {"offer.holidays": "recorded"}, "overrides": []},
        "outcomes": _with_derived_states({
            "closing": s["closing"],
            "outcomes": [
                {**{k: v for k, v in row.items() if k != "on"}, "states": [x for x in row["on"] if ":" not in x]}
                for row in s["outcomes"]
            ],
            "special_paths": s["special_paths"],
            "sources": {}, "overrides": [],
        }),
    }


def _with_derived_states(reply: dict[str, Any]) -> dict[str, Any]:
    """Map framework states a written spec leaves to the default row explicitly, as the model
    must (F-040). Same behavior: an unmapped optional state uses the default row at run time."""
    mapped = {state for row in reply["outcomes"] for state in row["states"]}
    default_row = next(row for row in reply["outcomes"] if "default" in row["states"])
    reply["derived_states"] = {}
    for state in DERIVED_REQUIRED_STATES:
        if state not in mapped:
            default_row["states"].append(state)
            reply["derived_states"][state] = "not named in the spec; the default row applies"
    return reply


class FakeClient:
    """Returns queued replies by group (``extract:<g>`` / ``repairN:<g>``) or by purpose.

    The last reply of a queue is repeated. ``barrier`` makes the four first extraction
    calls wait for each other, which only succeeds when they run in parallel.
    """

    def __init__(self, replies: dict[str, list[str]], *, barrier: threading.Barrier | None = None, log=None):
        self.replies = {key: list(value) for key, value in replies.items()}
        self.calls: list[tuple[str, list[dict[str, Any]]]] = []
        self.barrier = barrier
        self.log = log
        self._lock = threading.Lock()

    def complete(self, system, messages, purpose):
        with self._lock:
            self.calls.append((purpose, copy.deepcopy(messages)))
            key = purpose.split(":", 1)[1] if ":" in purpose else purpose
            queue = self.replies[key]
            text = queue.pop(0) if len(queue) > 1 else queue[0]
        if self.barrier is not None and purpose.startswith("extract:"):
            self.barrier.wait()
        result = LLMResult(text, "fake-model", 1000, 200, 0, 0.01, "end_turn")
        if self.log is not None:
            self.log(purpose, result)
        return result

    def settings(self) -> str:
        return "model=fake-model temperature=not sent"

    def purposes(self) -> list[str]:
        return [purpose for purpose, _ in self.calls]


def as_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1)
