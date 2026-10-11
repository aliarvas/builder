"""T-027 (PUB-12): the offer talk cannot stall.

- ``confirm_record`` says the read-back itself on entry (``readback_text``, built by the offer
  check from the checked offers) instead of leaving it to the model, which in PUB-12 never read
  it back after an earlier goodbye and waited for a confirmation until the call timed out.
- A global step ``customer_ends_call`` catches a goodbye in the offer steps and the read-back,
  where no route matched it ("Thank you, goodbye" was ``none``) and the step repeated "Thank
  you for your time" for minutes. A global step fires only when the step's own routes found no
  match. With accepted offers it goes to the read-back once; otherwise, or the second time,
  it closes as a hang-up (the closing chain then writes the notes and the outcome).
"""

from __future__ import annotations

from typing import Any, Callable

from .offer_check import OFFERS_ACCEPTED_COUNT
from .prompts import CONFIRM_READBACK_SAID_LINE, CUSTOMER_ENDS_CALL_INTENT

CUSTOMER_ENDS_CALL = "customer_ends_call"
GOODBYE_COUNT = "customer_goodbye_count"
GOODBYE_ROUTE = "customer_goodbye_route"
READBACK_TEXT = "readback_text"
# The steps of the offer talk where a goodbye has no route of its own.
GOODBYE_STEPS = ("negotiate", "offer_say", "revise_ask", "confirm_record")

GOODBYE_CODE = f"""try:
    count = int(vars.get({GOODBYE_COUNT!r}) or 0) + 1
except Exception:
    count = 1
vars[{GOODBYE_COUNT!r}] = count
try:
    accepted = int(vars.get({OFFERS_ACCEPTED_COUNT!r}) or 0)
except Exception:
    accepted = 0
if accepted > 0 and count == 1:
    vars[{GOODBYE_ROUTE!r}] = 'readback'
else:
    vars[{GOODBYE_ROUTE!r}] = 'close'
    vars['close_state'] = 'hangup'
"""


def speak_readback(nodes: dict[str, Any]) -> None:
    """confirm_record says the code-built read-back on entry; the model only answers."""
    node = nodes["confirm_record"]
    node["on_enter"] = dict(type="tts", text="{{" + READBACK_TEXT + "}}")
    node["task_message"] = CONFIRM_READBACK_SAID_LINE.text + "\n" + node["task_message"]


def add_goodbye_exit(
    nodes: dict[str, Any],
    global_nodes: dict[str, Any],
    global_sources: dict[str, tuple[str, ...]],
    code_node: Callable[[str, str, list[dict[str, Any]]], dict[str, Any]],
) -> None:
    """The global goodbye step, active in the offer steps and the read-back."""
    sources = tuple(key for key in GOODBYE_STEPS if key in nodes)
    if not sources or CUSTOMER_ENDS_CALL in nodes or CUSTOMER_ENDS_CALL in global_nodes:
        return
    node = code_node(CUSTOMER_ENDS_CALL, GOODBYE_CODE, [
        {"target_node": "confirm_record", "description": "Offers were accepted: read them back once",
         "condition": {"variable": GOODBYE_ROUTE, "operator": "equals", "operand": "readback"}},
        {"target_node": "closing", "description": "The customer ends the call", "condition": {"operator": "always"}},
    ])
    # The description is the situation the steps' special-topic value names (T-023 shadow rule).
    node["description"] = CUSTOMER_ENDS_CALL_INTENT.text
    node["condition"] = {"operator": "matches_intent", "description": CUSTOMER_ENDS_CALL_INTENT.text}
    global_nodes[CUSTOMER_ENDS_CALL] = node
    global_sources[CUSTOMER_ENDS_CALL] = sources
