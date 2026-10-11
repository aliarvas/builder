"""T-027 (PUB-12) and T-029: no conversation step can stall on a goodbye.

- ``confirm_record`` says the read-back itself on entry (``readback_text``, built by the offer
  check from the checked offers) instead of leaving it to the model, which in PUB-12 never read
  it back after an earlier goodbye and waited for a confirmation until the call timed out.
- A goodbye that no route of the step takes ("Thank you, goodbye" was ``none`` in PUB-12, and
  the step repeated "Thank you for your time" for minutes) goes to ``customer_goodbye`` (code):
  with accepted offers the read-back once; a goodbye after it closes and records nothing (T-037,
  CTO: no promise without an explicit yes to the read-back); before identity passed, the state the end-of-call hook would write (a third party: the close
  of its path without a callback); otherwise a hang-up. A second goodbye always ends the call.
  The closing chain then writes notes and the outcome.
- T-029: every conversation step reaches it. Normal steps through the global step
  ``customer_ends_call`` (it fires only when the step's own routes found no match); global
  conversation steps, which no global step can start from, through a choice value of their own.
"""

from __future__ import annotations

from typing import Any, Callable

from .offer_check import NOTE_SKIP_NUMBERS, OFFERS_ACCEPTED, OFFERS_ACCEPTED_COUNT, PRODUCT_NOTE_REASONS
from .prompts import CONFIRM_READBACK_SAID_LINE, CUSTOMER_ENDS_CALL_INTENT, GOODBYE_CHOICE_DESCRIPTION
from .spec import HANGUP_CLOSE_STATES, PhoneAgentSpec

CUSTOMER_ENDS_CALL = "customer_ends_call"
CUSTOMER_GOODBYE = "customer_goodbye"
GOODBYE_COUNT = "customer_goodbye_count"
GOODBYE_ROUTE = "customer_goodbye_route"
# The choice value a global conversation step gets for a goodbye.
GOODBYE_VALUE = "ends_call"
READBACK_TEXT = "readback_text"
# The read-back text a goodbye already had said (T-031).
GOODBYE_READBACK = "customer_goodbye_readback"
VERIFIED_STATE, UNVERIFIED_STATE = HANGUP_CLOSE_STATES


def goodbye_states(spec: PhoneAgentSpec) -> tuple[str, str, str]:
    """(after identity, before identity, a third party): the close states a goodbye writes, as
    the end-of-call hook would choose them (the unverified hang-up row, then the hang-up row,
    then the default row); a third party gets the close its path uses without a callback."""
    mapped = {state for item in spec.outcomes for state in item.on}
    unverified = next((state for state in (UNVERIFIED_STATE, VERIFIED_STATE) if state in mapped), "default")
    verified = VERIFIED_STATE if VERIFIED_STATE in mapped else "default"
    third = spec.third_party.data
    value = (third.get("callback_window") or {}).get("outside_close_value") or next(iter(third.get("close_values") or []), "")
    third_state = "third_party:" + value if value and "third_party:" + value in mapped else unverified
    return verified, unverified, third_state


def unconfirmed_note_reason(spec: PhoneAgentSpec) -> str:
    """T-037: the note reason for a product whose offer was agreed but never confirmed (the
    customer left after the read-back). The spec's neutral reason: a note reason that is not the
    refused or failed reason and that no outcome row or special path writes. Otherwise the reason
    the end-of-call hook gives (the hang-up row's reason). Never the refused reason: "" then,
    and the product gets no note."""
    notes = spec.closing.data.get("product_notes") or {}
    reasons = [str(reason) for reason in notes.get("reasons") or []]
    if not reasons:
        return ""
    reason_field = notes.get("reason_field", "")
    used = {notes.get("refused_reason"), notes.get("failed_reason"), *(item.reason for item in spec.outcomes),
            *(str((path.tool_args or {}).get(reason_field, "")) for path in spec.special_paths)}
    neutral = next((reason for reason in reasons if reason not in used), "")
    if neutral:
        return neutral
    after = goodbye_states(spec)[0]
    row = next((item for item in spec.outcomes if after in item.on), None) or next(
        (item for item in spec.outcomes if "default" in item.on), None)
    hook = row.reason if row else ""
    return hook if hook in reasons and hook not in (notes.get("refused_reason"), notes.get("failed_reason")) else ""


def goodbye_code(spec: PhoneAgentSpec) -> str:
    """T-031: with accepted offers, the read-back is said once for each read-back text (a new
    accepted offer gives a new text, so an early goodbye never uses it up). T-037 (CTO): a
    goodbye after the read-back is not a yes. The call closes by stage and records nothing; the
    products with an unconfirmed offer get the neutral note reason (``unconfirmed_note_reason``)
    or no note, never a refusal. A read-back the customer rejected (a revise value, which the offer
    check clears when it accepts new terms) is never read again on a goodbye."""
    after, before, third_state = goodbye_states(spec)
    confirmation = spec.confirmation.data
    rejected = list(confirmation.get("revise_values") or [])
    who = spec.opening.data.get("who_answered_variable") or ""
    third_values = list(spec.opening.data.get("third_party_values") or [])
    reason = unconfirmed_note_reason(spec)
    return f"""import json
try:
    count = int(vars.get({GOODBYE_COUNT!r}) or 0) + 1
except Exception:
    count = 1
vars[{GOODBYE_COUNT!r}] = count
try:
    accepted = int(vars.get({OFFERS_ACCEPTED_COUNT!r}) or 0)
except Exception:
    accepted = 0
text = str(vars.get({READBACK_TEXT!r}) or '').strip()
verified = str(vars.get('identity_verified') or '').lower() == 'true'
if str(vars.get({confirmation.get("intent_variable") or ""!r}) or '') in {rejected!r}:
    accepted = 0
if accepted > 0 and text and text != str(vars.get({GOODBYE_READBACK!r}) or ''):
    vars[{GOODBYE_ROUTE!r}] = 'readback'
    vars[{GOODBYE_READBACK!r}] = text
else:
    vars[{GOODBYE_ROUTE!r}] = 'close'
    if verified:
        vars['close_state'] = {after!r}
    elif str(vars.get({who!r}) or '') in {third_values!r}:
        vars['close_state'] = {third_state!r}
    else:
        vars['close_state'] = {before!r}
    try:
        offers = vars.get({OFFERS_ACCEPTED!r})
        offers = json.loads(offers) if isinstance(offers, str) and offers.strip() else (offers or dict())
        reasons = vars.get({PRODUCT_NOTE_REASONS!r})
        reasons = json.loads(reasons) if isinstance(reasons, str) and reasons.strip() else (reasons or dict())
        skipped = [int(number) for number in json.loads(str(vars.get({NOTE_SKIP_NUMBERS!r}) or '[]'))]
        for number in offers:
            if {reason!r}:
                reasons[str(number)] = {reason!r}
            elif int(number) not in skipped:
                skipped.append(int(number))
        vars[{PRODUCT_NOTE_REASONS!r}] = json.dumps(reasons)
        vars[{NOTE_SKIP_NUMBERS!r}] = json.dumps(skipped)
    except Exception:
        pass
"""


def speak_readback(nodes: dict[str, Any]) -> None:
    """confirm_record says the code-built read-back on entry; the model only answers."""
    node = nodes["confirm_record"]
    node["on_enter"] = dict(type="tts", text="{{" + READBACK_TEXT + "}}")
    node["task_message"] = CONFIRM_READBACK_SAID_LINE.text + "\n" + node["task_message"]


def waits_for_customer(node: dict[str, Any]) -> bool:
    """A conversation step that waits for a customer turn (not a passthrough line)."""
    return node.get("node_type") == "conversation" and not node.get("passthrough")


def add_goodbye_exit(
    spec: PhoneAgentSpec,
    nodes: dict[str, Any],
    global_nodes: dict[str, Any],
    global_sources: dict[str, tuple[str, ...]],
    code_node: Callable[[str, str, list[dict[str, Any]]], dict[str, Any]],
) -> None:
    """The goodbye step, and a way to it from every conversation step."""
    if CUSTOMER_ENDS_CALL in nodes or CUSTOMER_ENDS_CALL in global_nodes or CUSTOMER_GOODBYE in nodes:
        return
    exits = [{"target_node": "closing", "description": "The customer ends the call", "condition": {"operator": "always"}}]
    if "confirm_record" in nodes:
        exits.insert(0, {"target_node": "confirm_record", "description": "Offers were accepted: read them back once",
                         "condition": {"variable": GOODBYE_ROUTE, "operator": "equals", "operand": "readback"}})
    nodes[CUSTOMER_GOODBYE] = code_node(CUSTOMER_GOODBYE, goodbye_code(spec), exits)
    sources = tuple(key for key, node in nodes.items() if waits_for_customer(node))
    entry = code_node(CUSTOMER_ENDS_CALL, "vars['customer_goodbye_heard'] = 'yes'\n", [
        {"target_node": CUSTOMER_GOODBYE, "description": "Decide where the goodbye goes", "condition": {"operator": "always"}},
    ])
    # The description is the situation the steps' special-topic value names (T-023 shadow rule).
    entry["description"] = CUSTOMER_ENDS_CALL_INTENT.text
    entry["condition"] = {"operator": "matches_intent", "description": CUSTOMER_ENDS_CALL_INTENT.text}
    for key, node in global_nodes.items():
        if waits_for_customer(node):
            add_goodbye_choice(node)
    global_nodes[CUSTOMER_ENDS_CALL] = entry
    global_sources[CUSTOMER_ENDS_CALL] = sources


def add_goodbye_choice(node: dict[str, Any]) -> None:
    """A global conversation step: its choice field gets the goodbye value and a route to it."""
    for field in node.get("extraction_schema") or []:
        if field.get("enum_values") and GOODBYE_VALUE not in field["enum_values"]:
            field["enum_values"] = [*field["enum_values"], GOODBYE_VALUE]
            field["description"] = field["description"].rstrip() + GOODBYE_CHOICE_DESCRIPTION.text.replace(
                "{value}", GOODBYE_VALUE)
            node["transitions"] = [{
                "target_node": CUSTOMER_GOODBYE, "description": "The customer ends the call",
                "condition": {"logic": "or", "conditions": [
                    {"variable": field["name"], "operator": "equals", "operand": GOODBYE_VALUE}]},
            }, *node.get("transitions", [])]
            return


def goodbye_exit_gaps(workflow: dict[str, Any]) -> list[tuple[str, str]]:
    """(step, problem) for each conversation step that waits for the customer but has no way to
    the goodbye step: neither the global goodbye step nor a route of its own (T-029)."""
    globals_ = workflow.get("global_nodes", {})
    entry = globals_.get(CUSTOMER_ENDS_CALL) or {}
    excluded = set(entry.get("excluded_nodes") or []) if entry else None
    problems = []
    for key, node in [*workflow.get("nodes", {}).items(), *globals_.items()]:
        if not waits_for_customer(node):
            continue
        own = any(transition.get("target_node") == CUSTOMER_GOODBYE for transition in node.get("transitions") or [])
        by_global = excluded is not None and key in workflow.get("nodes", {}) and key not in excluded
        if not own and not by_global:
            problems.append((key, "the step waits for the customer but a goodbye has no route out of it; the "
                                  "step would answer it again and again until the turn limit"))
    return problems
