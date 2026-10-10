#!/usr/bin/env python3
"""Compare an extracted spec with a reference spec, ignoring wording.

Usage: python3 tools/compare_spec.py <extracted.json> <reference.json>

Reports only values that change the agent's behavior: identity fields and order, routing
(by route and closing pair, not by value name), the outcome table, offer rules and calendar,
special paths, tool fields, limits, and required sentences missing from goodbye/special lines.
Variable names chosen by the builder (``*_variable``, ``product_number_field``) are ignored.
Exit code 0 when nothing differs, 1 otherwise.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [_norm(part) for part in parts if part.strip()]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def _pair(row: dict[str, Any]) -> str:
    return f"{row.get('outcome')}/{row.get('reason') or '-'}"


def _rows(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {_pair(row): row for row in spec.get("outcomes", [])}


def _state_pairs(spec: dict[str, Any]) -> dict[str, str]:
    """Call-end state -> outcome pair, with routed states renamed by route (value names ignored)."""
    result: dict[str, str] = {}
    for row in spec.get("outcomes", []):
        for state in row.get("on", []):
            stage, routed, _ = state.partition(":")
            result[f"{stage} closes with {_pair(row)}" if routed else state] = _pair(row)
    return result


def _routes(spec: dict[str, Any]) -> dict[str, int]:
    opening = spec.get("opening", {})
    return {
        "opening.identity_values": len(opening.get("identity_values", [])),
        "opening.third_party_values": len(opening.get("third_party_values", [])),
        "opening.stay_values": len(opening.get("stay_values", [])),
        "negotiation.confirm_values": len(spec.get("negotiation", {}).get("confirm_values", [])),
        "confirmation.revise_values": len(spec.get("confirmation", {}).get("revise_values", [])),
    }


def _special_key(path: dict[str, Any]) -> str:
    args = ",".join(f"{key}={value}" for key, value in sorted((path.get("tool_args") or {}).items()))
    return f"{path.get('tool') or '-'}({args}) -> {path.get('then')} {_pair(path)}"


def compare_specs(extracted: dict[str, Any], reference: dict[str, Any]) -> list[str]:
    diffs: list[str] = []

    def same(area: str, got: Any, want: Any) -> None:
        if got != want:
            diffs.append(f"{area}: extracted={json.dumps(got, sort_keys=True)} reference={json.dumps(want, sort_keys=True)}")

    def get(spec: dict[str, Any], *keys: str) -> Any:
        value: Any = spec
        for key in keys:
            value = value.get(key) if isinstance(value, dict) else None
        return value

    # Identity.
    same("identity.question_fields", [q.get("field") for q in get(extracted, "identity", "questions") or []],
         [q.get("field") for q in get(reference, "identity", "questions") or []])
    for key in ("verified_field", "attempts_left_field", "answer_verified_field"):
        same(f"identity.{key}", get(extracted, "identity", key), get(reference, "identity", key))

    # Opening and routing.
    for key in ("max_unclear_asks", "address_with"):
        same(f"opening.{key}", get(extracted, "opening", key), get(reference, "opening", key))
    same("opening.forbidden_before_verification",
         sorted(_norm(item) for item in get(extracted, "opening", "forbidden_before_verification") or []),
         sorted(_norm(item) for item in get(reference, "opening", "forbidden_before_verification") or []))
    got_routes, want_routes = _routes(extracted), _routes(reference)
    for key in want_routes:
        same(f"{key} (count)", got_routes[key], want_routes[key])

    # Tool fields and limits.
    for section, key in (
        ("account", "products_field"), ("account", "product_id_field"),
        ("confirmation", "promise_product_id_field"), ("confirmation", "promise_date_field"),
        ("confirmation", "promise_amount_field"), ("confirmation", "max_attempts_per_product"),
        ("closing", "outcome_field"), ("closing", "reason_field"),
    ):
        same(f"{section}.{key}", get(extracted, section, key), get(reference, section, key))

    # Offer rules and calendar: every data value.
    got_offer = {k: v for k, v in (get(extracted, "offer") or {}).items() if k != "rules"}
    want_offer = {k: v for k, v in (get(reference, "offer") or {}).items() if k != "rules"}
    for key in sorted(set(got_offer) | set(want_offer)):
        got, want = got_offer.get(key), want_offer.get(key)
        if key == "holidays":
            got, want = sorted(got or []), sorted(want or [])
        same(f"offer.{key}", got, want)

    # Outcome table: rows, states, precedence, required sentences.
    got_rows, want_rows = _rows(extracted), _rows(reference)
    same("outcomes.rows", sorted(got_rows), sorted(want_rows))
    got_states, want_states = _state_pairs(extracted), _state_pairs(reference)
    for state in sorted(set(got_states) | set(want_states)):
        same(f"outcomes.state {state}", got_states.get(state), want_states.get(state))
    for pair in sorted(set(got_rows) & set(want_rows)):
        same(f"outcomes[{pair}].wins_over_promise", bool(got_rows[pair].get("wins_over_promise")),
             bool(want_rows[pair].get("wins_over_promise")))
        said = _norm(got_rows[pair].get("say", {}).get("text", ""))
        missing = [s for s in _sentences(want_rows[pair].get("say", {}).get("text", "")) if s and s not in said]
        if missing:
            diffs.append(f"outcomes[{pair}].say: missing sentences {missing}")

    # Special paths, matched by tool, fixed arguments, then and pair.
    got_paths = {_special_key(path): path for path in extracted.get("special_paths", [])}
    want_paths = {_special_key(path): path for path in reference.get("special_paths", [])}
    same("special_paths", sorted(got_paths), sorted(want_paths))
    for key in sorted(set(got_paths) & set(want_paths)):
        same(f"special_paths[{key}].available_in", sorted(got_paths[key].get("available_in", [])),
             sorted(want_paths[key].get("available_in", [])))
        same(f"special_paths[{key}].ask", "ask" in got_paths[key], "ask" in want_paths[key])
        said = _norm(got_paths[key].get("say", {}).get("text", ""))
        missing = [s for s in _sentences(want_paths[key].get("say", {}).get("text", "")) if s and s not in said]
        if missing:
            diffs.append(f"special_paths[{key}].say: missing sentences {missing}")
    return diffs


def rule_counts(spec: dict[str, Any]) -> dict[str, int]:
    counts = {
        section: len((spec.get(section) or {}).get("rules") or [])
        for section in ("opening", "third_party", "identity", "account", "negotiation", "confirmation", "offer", "closing")
    }
    counts["global_rules"] = len(spec.get("global_rules") or [])
    return counts


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    extracted, reference = (json.loads(Path(path).read_text(encoding="utf-8")) for path in args)
    diffs = compare_specs(extracted, reference)
    for line in diffs:
        print("DIFF " + line)
    got, want = rule_counts(extracted), rule_counts(reference)
    print("rules per section (extracted/reference): " + ", ".join(f"{k}={got[k]}/{want[k]}" for k in want))
    unmapped = (extracted.get("coverage") or {}).get("unmapped") or []
    print(f"coverage unmapped items: {len(unmapped)}")
    for line in unmapped:
        print("  UNMAPPED " + line)
    print(f"{len(diffs)} difference(s)")
    return 1 if diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
