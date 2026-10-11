"""T-032 (review LOW 2): a return to the read-back does not say the whole read-back again.

``confirm_record`` says the read-back on every entry (T-027). The routes into it (an accepted
offer, a revised offer, a goodbye, the end of a special path) all need it. A side question
asked at the read-back (a fixed line, a declined offer of help) returns with ``__previous__``,
and the step said the full read-back a second time. Those returns now go to a copy of the step,
``confirm_record_resume`` (same prompt, extraction and routes), whose fixed line only asks for
the confirmation. A return is known by the read-back's choice field: the step that sent the
call to the side question set it to the special-topic value.
"""

from __future__ import annotations

import copy
from typing import Any

from .prompts import READBACK_RESUME_LINE

CONFIRM_RECORD = "confirm_record"
CONFIRM_RESUME = "confirm_record_resume"
PREVIOUS = "__previous__"


def add_readback_resume(nodes: dict[str, Any]) -> None:
    """The copy of the read-back step that a side question returns to."""
    if CONFIRM_RECORD not in nodes or CONFIRM_RESUME in nodes:
        return
    resume = copy.deepcopy(nodes[CONFIRM_RECORD])
    resume["name"] = CONFIRM_RESUME
    resume["on_enter"] = dict(type="tts", text=READBACK_RESUME_LINE.text)
    nodes[CONFIRM_RESUME] = resume


def _with(condition: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any] | None:
    """``condition`` and ``extra`` (top level "or", "and" nested); None for an intent."""
    if condition.get("operator") == "always":
        return {"logic": "or", "conditions": [extra]}
    if condition.get("logic") != "or" or any("operator" in item and item["operator"] == "matches_intent"
                                             for item in condition.get("conditions", [])):
        return None
    return {"logic": "or", "conditions": [
        {"logic": "and", "conditions": [extra, item]} for item in condition["conditions"]]}


def resume_returns(nodes: dict[str, Any], global_nodes: dict[str, Any], global_sources: dict[str, tuple[str, ...]],
                   choice_variable: str, special_value: str) -> None:
    """Each global step that may start at the read-back and returns with ``__previous__``
    returns to the copy when the read-back's choice field holds the special-topic value. With
    no such step, the copy is removed again."""
    at_readback = {"variable": choice_variable, "operator": "equals", "operand": special_value}
    for key, node in global_nodes.items():
        if CONFIRM_RECORD not in global_sources.get(key, ()):
            continue
        transitions = []
        for transition in node.get("transitions") or []:
            condition = _with(transition["condition"], at_readback) if transition["target_node"] == PREVIOUS else None
            if condition is not None:
                transitions.append({"target_node": CONFIRM_RESUME, "description": "Back to the read-back",
                                    "condition": condition})
            transitions.append(transition)
        node["transitions"] = transitions
    if any(transition["target_node"] == CONFIRM_RESUME
           for node in global_nodes.values() for transition in node.get("transitions") or []):
        return
    # No side question returns to the read-back: the copy and the steps that start only there go.
    nodes.pop(CONFIRM_RESUME, None)
    for key, sources in list(global_sources.items()):
        if CONFIRM_RESUME in sources:
            global_sources[key] = tuple(source for source in sources if source != CONFIRM_RESUME)
            if not global_sources[key]:
                del global_sources[key]
                global_nodes.pop(key, None)
