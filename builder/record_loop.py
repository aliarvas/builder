"""F-063: after one read-back and one clear yes, code records every accepted offer.

``confirm_record`` reads back once and has no tool. Its "record" answer routes to
``record_next`` (code: the next accepted product not yet recorded), then ``record_promise``
(a silent api step, F-050: no tts on an api step) runs the promise tool for that product,
and ``confirmation_progress`` applies the per-product retry rule and loops back here. The
model never calls the promise tool and never says what was recorded; the closing does.

Decision (F-061/F-062 review finding 1, replaces the F-063 stop rule): a product whose
attempts are used up is set aside (``promises_failed_numbers``) and the loop goes on with the
next accepted product, as Brief-style rules keep the promises that can be recorded. When no
accepted product is left, the state is ``complete`` (all recorded) or ``exhausted`` (at least
one failed); the closing then says that not every promise was recorded, and the note loop
gives each failed product the spec's failed reason.
"""

from __future__ import annotations

import copy
from typing import Any

from .offer_check import OFFERS_ACCEPTED
from .spec import PhoneAgentSpec
from .tools_from_openapi import write_tool_config

RECORD_NEXT = "record_next"
RECORD_PROMISE = "record_promise"
# The product number the record step sends; a name of its own, so no model-filled tool
# default (``{{<product number field>}}``) ever picks it up.
RECORD_NUMBER = "promise_record_number"
RECORDED_NUMBERS = "promises_recorded_numbers"
FAILED_NUMBERS = "promises_failed_numbers"
RECORD_STATE = "record_state"
RESULT_VARIABLE = "promise_result_ok"


def record_values(spec: PhoneAgentSpec) -> list[str]:
    """Confirmation intents that mean "record": every value that is not a revise value
    (the extraction gives each intent the route record or change)."""
    confirmation = spec.confirmation.data
    return [value for value in confirmation["intent_values"] if value not in confirmation["revise_values"]]


def record_next_code() -> str:
    """Pick the lowest accepted product number not yet recorded or set aside; never raises."""
    return f"""import json
state = 'done'
try:
    accepted = vars.get({OFFERS_ACCEPTED!r})
    if isinstance(accepted, str):
        accepted = json.loads(accepted) if accepted.strip() else dict()
    if not isinstance(accepted, dict):
        accepted = dict()
    recorded = vars.get({RECORDED_NUMBERS!r})
    if isinstance(recorded, str):
        recorded = json.loads(recorded or '[]')
    recorded = [int(item) for item in (recorded or [])]
    failed = vars.get({FAILED_NUMBERS!r})
    if isinstance(failed, str):
        failed = json.loads(failed or '[]')
    recorded += [int(item) for item in (failed or [])]
    numbers = sorted(int(str(key).strip()) for key in accepted if str(key).strip().isdigit())
    pending = [number for number in numbers if number not in recorded]
    if pending:
        vars[{RECORD_NUMBER!r}] = pending[0]
        state = 'record'
except Exception:
    state = 'done'
vars[{RESULT_VARIABLE!r}] = ''
vars[{RECORD_STATE!r}] = state
"""


def record_number_hook(number_field: str) -> str:
    """Pre-hook prefix: write ``promise_record_number`` into the body's number field."""
    return f"""try:
    record_number = vars.get({RECORD_NUMBER!r})
    if record_number is not None and str(record_number).strip() != '' and isinstance(config.get('body'), dict):
        config['body'][{number_field!r}] = record_number
except Exception:
    pass
"""


def record_promise_node(spec: PhoneAgentSpec, promise_tool: dict[str, Any], after: str) -> dict[str, Any]:
    """Silent api step: the promise tool for ``{{promise_record_number}}``; its pre-hook fills
    id, date and amount from the checked offer. Write tool: no engine retry (the retry rule
    is ``confirmation_progress``)."""
    number_field = spec.confirmation.data["product_number_field"]
    tool = copy.deepcopy(promise_tool)
    body = tool["function"]["parameters"]["properties"]["body"]
    body["properties"][number_field] = {
        **body["properties"][number_field], "default": "{{" + RECORD_NUMBER + "}}",
    }
    body["required"] = [name for name in body.get("required", []) if name != number_field]
    if not body["required"]:
        body.pop("required")
    tool.pop("response_mapping", None)
    write_tool_config(tool)
    # Review fix 1: the product number comes from the variable itself, not only from the
    # engine's template substitution into an integer field; the body value is the fallback.
    tool["pre_process_code"] = record_number_hook(number_field) + tool.get("pre_process_code", "")
    return {
        "name": RECORD_PROMISE, "node_type": "api_request", "on_enter": dict(type="silent"),
        "passthrough": True, "passthrough_default_transition": after,
        "pre_actions": [tool],
        "response_mapping": [{"path": "data.ok", "variable": RESULT_VARIABLE}],
        "transitions": [{"target_node": after, "description": "Promise tool returned", "condition": {"operator": "always"}}],
    }
