"""Render the T-001 minimal Freya workflow."""

from __future__ import annotations

import copy
import json
import math
import re
from typing import Any

from .prompts import (
    CLOSING_FALLBACK_SAY,
    CONFIRM_TASK_TEMPLATE,
    IDENTITY_TASK_TEMPLATE,
    MULTI_STEP_SYSTEM_PROMPT_TEMPLATE,
    NEGOTIATION_TASK_TEMPLATE,
    OPENING_TASK_TEMPLATE,
    SPECIAL_PATH_TASK_TEMPLATE,
    THIRD_PARTY_TASK_TEMPLATE,
    render_phone_agent_system_prompt,
    render_phone_agent_task_message,
    render_prompt,
)
from .spec import PhoneAgentSpec, Rule, SpecError, required_close_states


FIXED_TOOL_NAMES = frozenset(
    {"verify_identity", "get_account", "create_promise", "add_note", "schedule_callback", "transfer_to_agent", "close_call"}
)


def _closing_transition() -> dict[str, Any]:
    return {
        "target_node": "hang_up",
        "description": "close_call succeeded",
        "condition": {
            "logic": "or",
            "conditions": [
                {
                    "variable": "close_call_response.data.ok",
                    "operator": "equals",
                    "operand": value,
                }
                for value in ("true", "True")
            ],
        },
    }


def build_workflow(brief_text: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a generic one-conversation-node workflow from runtime inputs."""
    tool_names = {tool.get("function", {}).get("name") for tool in tools}
    if "close_call" not in tool_names:
        raise ValueError("OpenAPI document must define the fixed close_call POST tool")

    task_message = render_phone_agent_task_message(brief_text)
    return {
        "initial_node": "call",
        "system_prompt": render_phone_agent_system_prompt(),
        "nodes": {
            "call": {
                "name": "call",
                "node_type": "conversation",
                "task_message": task_message,
                "tools": tools,
                "max_node_turns": 60,
                "max_turn_transition": "hang_up",
                "transitions": [
                    _closing_transition(),
                    {
                        "target_node": "call",
                        "description": "Keep going",
                        "condition": {"operator": "always"},
                    },
                ],
            },
            "hang_up": {
                "name": "hang_up",
                "node_type": "end_call",
                "on_enter": {"type": "silent"},
                "disable_inactivity_monitor": True,
                "transitions": [],
                "terminal": {
                    "type": "function",
                    "function": {
                        "name": "hang_up",
                        "handler": "__function__:end_call",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "message_mode": {"type": "string", "default": "none"}
                            },
                        },
                    },
                },
            },
        },
        "global_nodes": {},
        "test_variables": {
            "customer_id": "placeholder_customer",
            "first_name": "Test",
            "last_name": "Customer",
            "title": "Mx",
            "now": "2000-01-03T12:00",
        },
    }


def _rule_lines(rules: tuple[Rule, ...]) -> str:
    return "\n".join(f"- {rule.text}" for rule in rules) or "- Follow the step objective."


def _condition(variable: str, operator: str, operand: Any) -> dict[str, Any]:
    return {"variable": variable, "operator": operator, "operand": operand}


def _transition(target: str, description: str, conditions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "target_node": target,
        "description": description,
        "condition": {"logic": "or", "conditions": conditions},
    }


def _conversation(
    name: str, task: str, tools: list[dict[str, Any]], transitions: list[dict[str, Any]],
    *, max_turn_transition: str = "close_turn_limit",
) -> dict[str, Any]:
    return {
        "name": name,
        "node_type": "conversation",
        "task_message": task,
        "tools": tools,
        "max_node_turns": 30,
        "max_turn_transition": max_turn_transition,
        "transitions": transitions,
    }


def _tool_name(tool: dict[str, Any]) -> str:
    return str(tool.get("function", {}).get("name", ""))


def _tool_index(tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {_tool_name(tool): copy.deepcopy(tool) for tool in tools}
    missing = FIXED_TOOL_NAMES - result.keys()
    if missing:
        raise SpecError("OpenAPI is missing fixed tools: " + ", ".join(sorted(missing)))
    return result


def _response_mapping(tool: dict[str, Any], mappings: dict[str, str]) -> dict[str, Any]:
    mapped = copy.deepcopy(tool)
    mapped["response_mapping"] = [
        {"path": path, "variable": variable} for path, variable in mappings.items()
    ]
    return mapped


def product_id_pre_process_code(
    products_variable: str, products_field: str, product_number_field: str, product_id_field: str
) -> str:
    """Build a defensive hook that replaces a 1-based selection with a stored API id."""
    return f"""import json
try:
    body = config.get('body')
    products = vars.get({products_variable!r})
    if isinstance(products, str):
        try:
            products = json.loads(products)
        except Exception:
            products = []
    if not isinstance(products, list):
        products = vars.get({'get_account_response.data.' + products_field!r})
    if isinstance(products, str):
        try:
            products = json.loads(products)
        except Exception:
            products = []
    choice = body.get({product_number_field!r}) if isinstance(body, dict) else None
    try:
        index = int(str(choice).strip()) - 1
    except Exception:
        index = -1
    if isinstance(body, dict) and isinstance(products, list) and 0 <= index < len(products):
        selected = products[index]
        if isinstance(selected, dict) and {product_id_field!r} in selected:
            body.pop({product_number_field!r}, None)
            body[{product_id_field!r}] = selected[{product_id_field!r}]
except Exception:
    pass
"""


def _promise_tool(spec: PhoneAgentSpec, tool: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(tool)
    body = result["function"]["parameters"]["properties"]["body"]
    properties = body.setdefault("properties", {})
    number_field = spec.confirmation.data["product_number_field"]
    id_field = spec.confirmation.data["promise_product_id_field"]
    properties.pop(id_field, None)
    properties[number_field] = {
        "type": "integer",
        "description": "The 1-based product number from the account list shown in this call.",
        "default": "{{" + number_field + "}}",
    }
    required = [name for name in body.get("required", []) if name != id_field]
    if number_field not in required:
        required.append(number_field)
    body["required"] = required
    result["pre_process_code"] = product_id_pre_process_code(
        spec.account.data["products_variable"], spec.account.data["products_field"],
        number_field, id_field
    )
    result["response_mapping"] = [{"path": "data.ok", "variable": "promise_result_ok"}]
    return result


def _code_node(name: str, code: str, transitions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": name,
        "node_type": "code",
        "on_enter": {"type": "silent"},
        "passthrough": True,
        "passthrough_default_transition": transitions[-1]["target_node"],
        "pre_actions": [{
            "type": "function",
            "function": {
                "name": "code_exec",
                "handler": "__function__:code_exec",
                "parameters": {"type": "object", "properties": {
                    "code": {"type": "string", "default": code},
                    "timeout_ms": {"type": "number", "default": 10000},
                }},
            },
        }],
        "transitions": transitions,
    }


def _increment_code(variable: str, clear_variable: str) -> str:
    return (
        "try:\n"
        f"    vars[{variable!r}] = int(vars.get({variable!r}) or 0) + 1\n"
        "except Exception:\n"
        f"    vars[{variable!r}] = 1\n"
        f"vars[{clear_variable!r}] = ''\n"
    )


def _confirmation_progress_code(spec: PhoneAgentSpec) -> str:
    confirmation = spec.confirmation.data
    expected = confirmation["expected_count_variable"]
    number = "create_promise_args." + confirmation["product_number_field"]
    maximum = confirmation["max_attempts_per_product"]
    return f"""try:
    expected_count = max(1, int(vars.get({expected!r}) or 1))
except Exception:
    expected_count = 1
try:
    recorded_count = int(vars.get('promise_recorded_count') or 0)
except Exception:
    recorded_count = 0
product_number = str(vars.get({number!r}) or '')
attempt_key = 'promise_attempts_' + product_number
try:
    attempts = int(vars.get(attempt_key) or 0)
except Exception:
    attempts = 0
ok_value = vars.get('promise_result_ok')
ok = ok_value is True or str(ok_value).lower() == 'true'
if ok:
    recorded_count += 1
    vars['promise_recorded_count'] = recorded_count
    vars[attempt_key] = 0
    vars['promise_progress_state'] = 'complete' if recorded_count >= expected_count else 'continue'
else:
    attempts += 1
    vars[attempt_key] = attempts
    vars['promise_progress_state'] = 'exhausted' if attempts >= {maximum!r} else 'retry'
vars['promise_result_ok'] = 'consumed'
"""


def _tool_with_baked_args(tool: dict[str, Any], args: dict[str, Any], path_id: str) -> dict[str, Any]:
    result = copy.deepcopy(tool)
    body = result["function"]["parameters"]["properties"]["body"]
    properties = body.setdefault("properties", {})
    required = list(body.get("required", []))
    for name, value in args.items():
        if name not in properties:
            raise SpecError(f"special path {path_id!r} tool has no argument {name!r}")
        properties[name]["default"] = copy.deepcopy(value)
        required = [field for field in required if field != name]
    if required:
        body["required"] = required
    else:
        body.pop("required", None)
    return result


def _special_key(raw: str, used: set[str]) -> str:
    base = "special_" + re.sub(r"[^A-Za-z0-9_]+", "_", raw).strip("_")
    if base == "special_":
        raise SpecError("special path id must contain a letter or number")
    key = base
    suffix = 2
    while key in used:
        key = f"{base}_{suffix}"
        suffix += 1
    used.add(key)
    return key


def _py_str(value: str) -> str:
    """Python string literal for generated code that never contains a brace."""
    return json.dumps(value).replace("{", "\\u007b").replace("}", "\\u007d")


def _close_state_code(state: str) -> str:
    return f"vars['close_state'] = {_py_str(state)}\n"


def close_table(spec: PhoneAgentSpec) -> list[tuple[str, str, str, str, bool]]:
    """(state, outcome, reason, closing sentence, wins over a recorded promise) rows.

    The ``default`` row comes last.
    """
    by_pair = {(item.outcome, item.reason): item for item in spec.outcomes}
    rows = [
        (state, item.outcome, item.reason, item.say.text, item.wins_over_promise)
        for item in spec.outcomes for state in item.on if state != "default"
    ]
    for path in spec.special_paths:
        if path.then == "close":
            item = by_pair[(path.outcome, path.reason)]
            rows.append(("special:" + path.id, path.outcome, path.reason, item.say.text, item.wins_over_promise))
    default = next(item for item in spec.outcomes if "default" in item.on)
    rows.append(("default", default.outcome, default.reason, default.say.text, default.wins_over_promise))
    return rows


def _closing_code(spec: PhoneAgentSpec) -> str:
    """Pick outcome, reason and the closing sentence from call state; never raises."""
    rows = ",\n".join(
        "    (" + ", ".join(_py_str(value) for value in row[:4]) + f", {row[4]!r})"
        for row in close_table(spec)
    )
    return f"""TABLE = [
{rows},
]
chosen = TABLE[-1]
try:
    state = str(vars.get('close_state') or '')
    try:
        recorded = int(vars.get('promise_recorded_count') or 0)
    except Exception:
        recorded = 0
    for row in TABLE:
        if row[0] == state:
            chosen = row
            break
    if recorded > 0 and not chosen[4]:
        for row in TABLE:
            if row[0] == 'promise_recorded':
                chosen = row
                break
except Exception:
    pass
vars['close_resolved_state'] = chosen[0]
vars['close_outcome'] = chosen[1]
if chosen[2]:
    vars['close_reason'] = chosen[2]
vars['closing_sentence'] = chosen[3] or {_py_str(CLOSING_FALLBACK_SAY.text)}
"""


def _close_tool(spec: PhoneAgentSpec, tool: dict[str, Any]) -> dict[str, Any]:
    closing = spec.closing.data
    result = _tool_with_baked_args(tool, {
        closing["outcome_field"]: "{{close_outcome}}",
        closing["reason_field"]: "{{close_reason}}",
    }, "closing")
    # Write tool: no tool-level retries; the flow retries once (close_attempt).
    result.setdefault("config", {})["maxRetries"] = 0
    return result


def build_spec_workflow(spec: PhoneAgentSpec, tools: list[dict[str, Any]]) -> dict[str, Any]:
    """Render the T-004 deterministic skeleton from a validated spec and OpenAPI tools."""
    by_name = _tool_index(tools)
    identity_body = by_name["verify_identity"]["function"]["parameters"]["properties"]["body"]
    field_schema = identity_body.get("properties", {}).get("field", {})
    allowed_identity_fields = field_schema.get("enum", [])
    unknown_identity_fields = [
        question.field for question in spec.identity_questions
        if question.field not in allowed_identity_fields
    ]
    if unknown_identity_fields:
        raise SpecError(
            "identity question fields are not in the OpenAPI enum: "
            + ", ".join(unknown_identity_fields)
        )
    close_body = by_name["close_call"]["function"]["parameters"]["properties"]["body"].get("properties", {})
    for field in (spec.closing.data["outcome_field"], spec.closing.data["reason_field"]):
        if field not in close_body:
            raise SpecError(f"closing field {field!r} is not a close_call body field")
    outcome_enum = close_body[spec.closing.data["outcome_field"]].get("enum")
    if outcome_enum:
        unknown_outcomes = sorted({item.outcome for item in spec.outcomes} - set(outcome_enum))
        if unknown_outcomes:
            raise SpecError("outcomes are not in the close_call enum: " + ", ".join(unknown_outcomes))
    reserved_special_tools = {"verify_identity", "get_account", "create_promise", "close_call"}
    for path in spec.special_paths:
        if path.tool in reserved_special_tools:
            raise SpecError(
                f"special path {path.id!r} cannot use step-scoped tool {path.tool!r}"
            )
    opening = spec.opening.data
    third = spec.third_party.data
    identity = spec.identity.data
    negotiation = spec.negotiation.data
    confirmation = spec.confirmation.data

    used = {
        "opening", "opening_unclear", "third_party", "identity", "account", "negotiate",
        "confirm_record", "confirmation_progress", "closing", "closing_say", "close_attempt",
        "close_record", "end_call",
    }
    close_nodes: dict[str, str] = {}

    def close_via(state: str) -> str:
        """Node that records why the call ends, then runs the shared closing path."""
        if state not in close_nodes:
            key = "close_" + re.sub(r"[^A-Za-z0-9_]+", "_", state).strip("_")
            base, suffix = key, 2
            while key in used:
                key = f"{base}_{suffix}"
                suffix += 1
            used.add(key)
            close_nodes[state] = key
        return close_nodes[state]

    close_via("turn_limit")
    special_keys = [
        (path, source, _special_key(path.id + "_from_" + source, used))
        for path in spec.special_paths for source in path.available_in
    ]

    def special_transitions(step: str) -> list[dict[str, Any]]:
        return [
            {
                "target_node": key,
                "description": path.when.text,
                "condition": {"operator": "matches_intent", "description": path.when.text},
            }
            for path, source, key in special_keys if source == step
        ]

    opening_transitions = [
        *(
            _transition(close_via("opening:" + value), "Opening path must close", [
                _condition(opening["who_answered_variable"], "equals", value)
            ])
            for value in opening["close_values"]
        ),
        _transition("identity", "Customer answered", [
            _condition(opening["who_answered_variable"], "equals", value)
            for value in opening["identity_values"]
        ]),
        _transition("third_party", "Someone else answered", [
            _condition(opening["who_answered_variable"], "equals", value)
            for value in opening["third_party_values"]
        ]),
        _transition("opening_unclear", "Opening remains unclear", [
            _condition(opening["who_answered_variable"], "equals", value)
            for value in opening["stay_values"]
        ]),
        *special_transitions("opening"),
    ]

    identity_tool = _response_mapping(by_name["verify_identity"], {
        "data." + identity["verified_field"]: "identity_verified",
        "data." + identity["attempts_left_field"]: "identity_attempts_left",
    })
    account_tool = copy.deepcopy(by_name["get_account"])
    account_tool.setdefault("config", {})["maxRetries"] = 1
    promise_tool = _promise_tool(spec, by_name["create_promise"])

    questions = "\n".join(
        f"{index}. {question.ask.text} (field: {question.field}; tool format, convert it yourself: {question.answer_format.text})"
        for index, question in enumerate(spec.identity_questions, start=1)
    )
    callback_tool = _response_mapping(by_name["schedule_callback"], {"data.ok": "callback_ok"})
    nodes: dict[str, Any] = {
        "opening": _conversation("opening", render_prompt(
            OPENING_TASK_TEMPLATE,
            introduction=spec.agent.introduction.text,
            address=" ".join("{{" + name + "}}" for name in opening["address_with"]),
            question=opening["confirmation_question"]["text"],
            unclear=opening["unclear_instruction"]["text"],
            forbidden=", ".join(opening["forbidden_before_verification"]),
            rules=_rule_lines(spec.opening.rules),
        ), [], opening_transitions),
        "opening_unclear": _code_node("opening_unclear", _increment_code(
            opening["unclear_count_variable"], opening["who_answered_variable"]
        ), [
            _transition(close_via("opening_unclear"), "Opening uncertainty limit reached", [
                _condition(
                    opening["unclear_count_variable"], "greater_than",
                    opening["max_unclear_asks"] - 1,
                )
            ]),
            {"target_node": "opening", "description": "Ask once more", "condition": {"operator": "always"}},
        ]),
        "third_party": _conversation("third_party", render_prompt(
            THIRD_PARTY_TASK_TEMPLATE, rules=_rule_lines(spec.third_party.rules)
        ), [callback_tool], [
            _transition(close_via("callback_scheduled"), "Callback was scheduled", [
                _condition(variable, "equals", value)
                for variable in ("callback_ok", "schedule_callback_response.data.ok")
                for value in ("true", "True")
            ]),
            _transition(close_via("callback_failed"), "Callback could not be scheduled", [
                *(
                    _condition(variable, "equals", value)
                    for variable in ("callback_ok", "schedule_callback_response.data.ok")
                    for value in ("false", "False")
                ),
                _condition("schedule_callback_failure_count", "greater_than", 0),
            ]),
            *(
                _transition(close_via("third_party:" + value), "Third-party path is complete", [
                    _condition(third["intent_variable"], "equals", value)
                ])
                for value in third["close_values"]
            ),
            *special_transitions("third_party"),
        ]),
        "identity": _conversation("identity", render_prompt(
            IDENTITY_TASK_TEMPLATE, questions=questions,
            answer_verified=identity["answer_verified_field"],
            failed_answer=identity["failed_answer_instruction"]["text"],
            attempts_left=identity["attempts_left_field"],
            exhausted_say=identity["exhausted_say"]["text"],
            rules=_rule_lines(spec.identity.rules),
        ), [identity_tool], [
            _transition("account", "Identity verified", [
                _condition("identity_verified", "equals", value) for value in ("true", "True")
            ]),
            _transition(close_via("identity_failed"), "No identity attempts remain", [
                _condition("identity_attempts_left", "less_than", 1)
            ]),
            *special_transitions("identity"),
        ]),
        "account": {
            "name": "account", "node_type": "api_request", "on_enter": {"type": "silent"},
            "passthrough": True, "passthrough_default_transition": "negotiate",
            "pre_actions": [account_tool],
            "response_mapping": [{
                "path": "data." + spec.account.data["products_field"],
                "variable": spec.account.data["products_variable"],
            }],
            "transitions": [
                _transition(close_via("account_failed"), "Account retrieval failed after retry", [
                    _condition("account_failure_count", "greater_than", 0)
                ]),
                {"target_node": "negotiate", "description": "Account loaded", "condition": {"operator": "always"}},
            ],
        },
        "negotiate": _conversation("negotiate", render_prompt(
            NEGOTIATION_TASK_TEMPLATE, rules=_rule_lines(spec.account.rules + spec.negotiation.rules)
        ), [], [
            _transition("confirm_record", "Customer proposes an arrangement", [
                _condition(negotiation["intent_variable"], "equals", value) for value in negotiation["confirm_values"]
            ]),
            *(
                _transition(close_via("negotiation:" + value), "Negotiation ends without a proposal", [
                    _condition(negotiation["intent_variable"], "equals", value)
                ])
                for value in negotiation["close_values"]
            ),
            *special_transitions("negotiate"),
        ]),
        "confirm_record": _conversation("confirm_record", render_prompt(
            CONFIRM_TASK_TEMPLATE, rules=_rule_lines(spec.confirmation.rules)
        ), [promise_tool], [
            _transition("negotiate", "Customer revised or rejected the read-back", [
                _condition(confirmation["intent_variable"], "equals", value)
                for value in confirmation["revise_values"]
            ]),
            _transition("confirmation_progress", "Promise tool returned a result", [
                _condition("promise_result_ok", "equals", value)
                for value in ("true", "True", "false", "False")
            ]),
            *special_transitions("confirm_record"),
        ]),
        "confirmation_progress": _code_node(
            "confirmation_progress", _confirmation_progress_code(spec), [
                _transition(close_via("promise_recorded"), "All agreed products were recorded", [
                    _condition("promise_progress_state", "equals", "complete")
                ]),
                _transition(close_via("promise_failed"), "A product exhausted its recording attempts", [
                    _condition("promise_progress_state", "equals", "exhausted")
                ]),
                {"target_node": "confirm_record", "description": "Record the next product or retry once", "condition": {"operator": "always"}},
            ],
        ),
        "closing": _code_node("closing", _closing_code(spec), [
            {"target_node": "closing_say", "description": "Outcome computed", "condition": {"operator": "always"}},
        ]),
        "closing_say": {
            **_code_node("closing_say", "vars['closing_said'] = 'yes'\n", [
                {"target_node": "close_attempt", "description": "Goodbye said", "condition": {"operator": "always"}},
            ]),
            "on_enter": {"type": "tts", "text": "{{closing_sentence}}"},
        },
        "close_attempt": _code_node("close_attempt", _increment_code("close_attempts", "close_call_ok"), [
            {"target_node": "close_record", "description": "Record the outcome", "condition": {"operator": "always"}},
        ]),
        "close_record": {
            "name": "close_record", "node_type": "api_request", "on_enter": {"type": "silent"},
            "passthrough": True, "passthrough_default_transition": "close_attempt",
            "pre_actions": [_close_tool(spec, by_name["close_call"])],
            "response_mapping": [{"path": "data.ok", "variable": "close_call_ok"}],
            "transitions": [
                _transition("end_call", "Closing tool succeeded", [
                    _condition("close_call_ok", "equals", value) for value in ("true", "True")
                ]),
                _transition("end_call", "Closing tool failed twice; end without claiming success", [
                    _condition("close_attempts", "greater_than", 1)
                ]),
                {"target_node": "close_attempt", "description": "Retry the closing tool once", "condition": {"operator": "always"}},
            ],
        },
        "end_call": {
            "name": "end_call", "node_type": "end_call", "on_enter": {"type": "silent"},
            "disable_inactivity_monitor": True, "transitions": [],
            "terminal": {"type": "function", "function": {"name": "end_call", "handler": "__function__:end_call", "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}}}},
        },
    }

    for path, source, key in special_keys:
        if path.tool and path.tool not in by_name:
            raise SpecError(f"special path {path.id!r} references unavailable tool {path.tool!r}")
        scoped = [_tool_with_baked_args(by_name[path.tool], path.tool_args, path.id)] if path.tool else []
        conditions = (
            [_condition(path.tool + "_success_count", "greater_than", 0), _condition(path.tool + "_failure_count", "greater_than", 0)]
            if path.tool else []
        )
        target = close_via("special:" + path.id) if path.then == "close" else source
        transitions = (
            [_transition(target, "Special-path tool completed", conditions)]
            if conditions else [{
                "target_node": target, "description": "Special path handled", "is_tool_call": True,
                "condition": {"operator": "matches_intent", "description": "The required special-path response has been given."},
            }]
        )
        nodes[key] = _conversation(key, render_prompt(
            SPECIAL_PATH_TASK_TEMPLATE, when=path.when.text, say=path.say.text
        ), scoped, transitions)

    for state, key in close_nodes.items():
        nodes[key] = _code_node(key, _close_state_code(state), [
            {"target_node": "closing", "description": "Compute the closing outcome", "condition": {"operator": "always"}},
        ])

    # Extraction is restricted to categorical routing signals supplied by the spec.
    nodes["opening"]["extraction_schema"] = [{
        "name": opening["who_answered_variable"], "type": "string",
        "description": "Who answered the call", "enum_values": opening["who_answered_options"],
        "min_confidence": 0.8,
    }]
    nodes["third_party"]["extraction_schema"] = [{
        "name": third["intent_variable"], "type": "string",
        "description": "The third party's current intent", "enum_values": third["intent_values"],
        "min_confidence": 0.8,
    }]
    nodes["negotiate"]["extraction_schema"] = [{
        "name": negotiation["intent_variable"], "type": "string",
        "description": "The customer's negotiation intent", "enum_values": negotiation["intent_values"],
        "min_confidence": 0.8,
    }, {
        "name": confirmation["expected_count_variable"], "type": "integer",
        "description": "Number of products in the customer's confirmed proposal",
        "min_confidence": 0.8,
    }]
    nodes["confirm_record"]["extraction_schema"] = [{
        "name": confirmation["intent_variable"], "type": "string",
        "description": "Whether the customer confirms or revises the read-back",
        "enum_values": confirmation["intent_values"], "min_confidence": 0.8,
    }]

    return {
        "initial_node": "opening",
        "system_prompt": render_prompt(
            MULTI_STEP_SYSTEM_PROMPT_TEMPLATE,
            agent_name=spec.agent.name,
            language=spec.agent.language,
            rules=_rule_lines(spec.global_rules),
        ),
        "nodes": nodes,
        "global_nodes": {},
        "test_variables": {
            "customer_id": "placeholder_customer", "first_name": "Test", "last_name": "Customer",
            "title": "Mx", "now": "2000-01-03T12:00",
        },
    }


def workflow_prompt_estimates(workflow: dict[str, Any]) -> dict[str, int]:
    """Return conservative character/4 estimates for each conversation node."""
    system = str(workflow.get("system_prompt", ""))
    return {
        key: math.ceil((
            len(system)
            + len(str(node.get("task_message", "")))
            + sum(len(str(tool.get("function", {}).get("description", ""))) for tool in node.get("tools", []))
        ) / 4)
        for key, node in workflow.get("nodes", {}).items()
        if node.get("node_type") == "conversation"
    }


def workflow_tools_by_step(workflow: dict[str, Any]) -> dict[str, list[str]]:
    return {
        key: [_tool_name(tool) for tool in node.get("tools", [])] + [
            _tool_name(tool) + " (engine)" for tool in node.get("pre_actions", [])
            if _tool_name(tool) != "code_exec"
        ]
        for key, node in workflow.get("nodes", {}).items()
    }
