"""F-061/F-062: per-product refusal and a code-owned note for every product without a promise.

Both are driven by optional spec data, so a spec without it renders as before:

- ``negotiation.product_end_values`` / ``attempt_values`` (and ``offer.persuasion_attempts``):
  a refusal goes from negotiate to ``product_refusal`` (code). It counts persuasion attempts
  per product when the spec gives them, notes the product as refused, and moves on: the next
  product's line (``offer_say``), the read-back when offers were accepted, or the closing.
- ``closing.product_notes``: ``closing`` -> ``note_next`` (code) -> ``note_record`` (silent
  passthrough api step with the note tool; F-050: no tts on an api step) -> ``note_next`` ...
  -> ``closing_say``. No notes when the call's outcome is in ``skip_outcomes`` (a transfer).
"""

from __future__ import annotations

import copy
from typing import Any, Callable

from .offer_check import (
    NOTE_PRODUCT_ID, NOTE_REASON, NOTE_RESULT, NOTE_STATE, PERSUASION_ATTEMPT, PRODUCT_REFUSAL_STATE,
    note_next_code, product_refusal_code,
)
from .prompts import PERSUASION_STATE_LINE, PRODUCT_INTENT_DESCRIPTION
from .record_loop import RECORDED_NUMBERS
from .spec import FRAMEWORK_NONE_VALUE, PhoneAgentSpec, SpecError
from .tools_from_openapi import CALL_VARIABLES

PRODUCT_REFUSAL = "product_refusal"
NOTE_NEXT = "note_next"
NOTE_RECORD = "note_record"
# Trace warning prefix when the note rule cannot be rendered and is left out.
NOTES_DROPPED = "closing.product_notes dropped (F-061 not applied)"


def _condition(variable: str, operator: str, operand: Any) -> dict[str, Any]:
    return {"variable": variable, "operator": operator, "operand": operand}


def _transition(target: str, description: str, conditions: list[dict[str, Any]]) -> dict[str, Any]:
    condition = conditions[0] if len(conditions) == 1 else {"logic": "or", "conditions": conditions}
    return {"target_node": target, "description": description, "condition": condition}


def refusal_values(spec: PhoneAgentSpec) -> list[str]:
    """Negotiation intents that go to the per-product refusal step."""
    negotiation = spec.negotiation.data
    attempts = list(negotiation.get("attempt_values") or []) if spec.offer.data.get("persuasion_attempts") else []
    return [*negotiation.get("product_end_values", []), *attempts]


def note_tool(spec: PhoneAgentSpec, by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The note tool for the loop: product id and reason come from code (call variables)."""
    notes = spec.closing.data["product_notes"]
    if notes["tool"] not in by_name:
        raise SpecError(f"closing.product_notes.tool {notes['tool']!r} is not an OpenAPI tool")
    tool = copy.deepcopy(by_name[notes["tool"]])
    body = tool["function"]["parameters"]["properties"].get("body", {})
    properties = body.get("properties", {})
    for key, variable in ((notes["product_field"], NOTE_PRODUCT_ID), (notes["reason_field"], NOTE_REASON)):
        if key not in properties:
            raise SpecError(f"closing.product_notes field {key!r} is not a {notes['tool']} body field")
        properties[key] = {**properties[key], "default": "{{" + variable + "}}"}
    # No model runs this step: an optional field the model would fill is left out.
    for key in [name for name, prop in properties.items()
                if name not in (notes["product_field"], notes["reason_field"])
                and str(prop.get("default", "")).startswith("{{")
                and str(prop.get("default", "")).strip("{}") not in CALL_VARIABLES]:
        if key in body.get("required", []):
            raise SpecError(f"{notes['tool']} needs {key!r}, which no code value fills")
        properties.pop(key)
    allowed = properties[notes["reason_field"]].get("enum")
    if allowed:
        unknown = sorted(set(notes["reasons"]) - set(allowed))
        if unknown:
            raise SpecError(f"closing.product_notes.reasons not in the {notes['tool']} enum: {unknown}")
    body["required"] = [name for name in body.get("required", [])
                        if name not in (notes["product_field"], notes["reason_field"])]
    if not body["required"]:
        body.pop("required")
    tool.pop("response_mapping", None)
    tool.setdefault("config", {})["maxRetries"] = 0
    return tool


def add_product_steps(
    spec: PhoneAgentSpec,
    nodes: dict[str, Any],
    by_name: dict[str, dict[str, Any]],
    code_node: Callable[[str, str, list[dict[str, Any]]], dict[str, Any]],
    special_results: list[str],
    offer_say: str,
    warnings: list[str] | None = None,
) -> None:
    """Add the refusal step and the note loop when the spec asks for them (before the
    negotiate copies are made, so they share the refusal route)."""
    negotiation = spec.negotiation.data
    values = refusal_values(spec)
    if values:
        intent = negotiation["intent_variable"]
        nodes[PRODUCT_REFUSAL] = code_node(PRODUCT_REFUSAL, product_refusal_code(spec), [
            _transition(offer_say, "Next product", [_condition(PRODUCT_REFUSAL_STATE, "equals", "more")]),
            _transition("confirm_record", "Every product is handled and offers were accepted",
                        [_condition(PRODUCT_REFUSAL_STATE, "equals", "ready")]),
            _transition("closing", "No product is left and nothing was accepted",
                        [_condition(PRODUCT_REFUSAL_STATE, "equals", "closing")]),
            {"target_node": "negotiate", "description": "Persuasion attempt left", "condition": {"operator": "always"}},
        ])
        negotiate = nodes["negotiate"]
        # First after the offer check: these values never reach the read-back or closing routes.
        negotiate["transitions"].insert(1, _transition(
            PRODUCT_REFUSAL, "The customer refuses the product being discussed",
            [_condition(intent, "equals", value) for value in values]))
        for field in negotiate.get("extraction_schema", []):
            if field["name"] == intent:
                field["description"] += " " + PRODUCT_INTENT_DESCRIPTION.text.replace(
                    "{product_end}", ", ".join(negotiation.get("product_end_values", []))
                ).replace("{attempt}", ", ".join(negotiation.get("attempt_values", [])) or FRAMEWORK_NONE_VALUE)
        if spec.offer.data.get("persuasion_attempts"):
            negotiate["task_message"] += "\n" + PERSUASION_STATE_LINE.text.replace(
                "{attempt}", "{{" + PERSUASION_ATTEMPT + "}}")

    if spec.closing.data.get("product_notes"):
        try:
            tool = note_tool(spec, by_name)
        except SpecError as exc:
            # Optional block (review finding 2): a note rule the tools cannot carry is dropped
            # with a warning and the build goes on, as for the callback fields (F-055).
            if warnings is not None:
                warnings.append(f"{NOTES_DROPPED}: {exc}")
            return
        nodes[NOTE_NEXT] = code_node(NOTE_NEXT, note_next_code(spec, RECORDED_NUMBERS, special_results), [
            _transition(NOTE_RECORD, "A product without a promise has no note yet",
                        [_condition(NOTE_STATE, "equals", "note")]),
            {"target_node": "closing_say", "description": "Every note is written", "condition": {"operator": "always"}},
        ])
        nodes[NOTE_RECORD] = {
            "name": NOTE_RECORD, "node_type": "api_request", "on_enter": {"type": "silent"},
            "passthrough": True, "passthrough_default_transition": NOTE_NEXT,
            "pre_actions": [tool],
            "response_mapping": [{"path": "data.ok", "variable": NOTE_RESULT}],
            "transitions": [{"target_node": NOTE_NEXT, "description": "Note tool returned", "condition": {"operator": "always"}}],
        }
        closing = nodes["closing"]
        for transition in closing["transitions"]:
            if transition["target_node"] == "closing_say":
                transition["target_node"] = NOTE_NEXT
                transition["description"] = "Outcome computed; write the product notes"

