"""Render the T-001 minimal Freya workflow."""

from __future__ import annotations

import copy
import dataclasses
import json
import math
import re
from typing import Any

from .prompts import (
    ACCOUNT_WAIT_LINE,
    SPECIAL_ASK_PHRASED_TEMPLATE,
    SPECIAL_SAY_FALLBACK,
    CLOSING_FALLBACK_SAY,
    CONVERSATION_NO_TOOL_RULE,
    CONVERSATION_TOOL_RULE_TEMPLATE,
    CONFIRM_TASK_TEMPLATE,
    IDENTITY_TASK_TEMPLATE,
    MULTI_STEP_SYSTEM_PROMPT_TEMPLATE,
    NEGOTIATION_TASK_TEMPLATE,
    OPENING_REASK_TASK_TEMPLATE,
    OPENING_TASK_TEMPLATE,
    SPECIAL_ASK_TASK_TEMPLATE,
    SPECIAL_PATH_TASK_TEMPLATE,
    THIRD_PARTY_TASK_TEMPLATE,
    WHO_ANSWERED_DESCRIPTION,
    render_phone_agent_system_prompt,
    render_phone_agent_task_message,
    render_prompt,
)
from .offer_check import (
    OFFER_AMOUNT, OFFER_DATE, OFFER_PRODUCT, OFFER_PROGRESS, OFFERS_ACCEPTED_COUNT,
    OFFER_AMOUNT_KIND, OFFER_PROPOSED_KIND, AMOUNT_KINDS, AMOUNT_KIND_NONE, OFFER_ACCEPTS, ACCEPTS_YES, _py_literal, check_offer_code, offer_setup_code, product_reader_code,
    promise_values_hook, special_noted_code,
)
from .spec import ENFORCEMENT_CHECKS, FRAMEWORK_NONE_VALUE, OPENING_GREETING_VALUE, PhoneAgentSpec, Rule, SpecError, SpecialPath
from .spoken import agent_directed, spoken_words
from .tools_from_openapi import CALL_VARIABLES


IDENTITY_CHECK = "identity_check"
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
    workflow = {
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
    _apply_conversation_tool_rules(workflow["nodes"]["call"])
    return workflow


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


def _apply_conversation_tool_rules(node: dict[str, Any]) -> None:
    """Put the kit's two-way tool rule in every prompt the node may show."""
    if node.get("node_type") != "conversation":
        return
    names = [_tool_name(tool) for tool in node.get("tools", [])]
    if any(not name for name in names):
        raise ValueError("conversation tool has no function.name")
    if names:
        rule = "\n".join(
            render_prompt(CONVERSATION_TOOL_RULE_TEMPLATE, tool_name=name) for name in names
        )
    else:
        rule = CONVERSATION_NO_TOOL_RULE.text
    for field in ("task_message", "loop_prompt"):
        if field in node:
            node[field] = str(node[field]).rstrip() + "\n\n" + rule


def _tool_index(tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {_tool_name(tool): copy.deepcopy(tool) for tool in tools}
    missing = FIXED_TOOL_NAMES - result.keys()
    if missing:
        raise SpecError(
            "the tool file does not define the bank tools this builder needs: "
            + ", ".join(sorted(missing))
            + ". Tools found: " + (", ".join(sorted(name for name in result if name)) or "none")
            + ". Each tool name is taken from the last part of its OpenAPI path."
        )
    return result


def group_transitions_by_target(transitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Write each target once: OR the conditions of transitions that share a target.

    Freya merges same-target transitions at load time, and an unconditional one makes the
    merged transition unconditional. Merging here keeps the rendered order explicit. A
    target reached both unconditionally (or by intent) and by another transition is a
    builder bug and raises.
    """
    order: list[str] = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for transition in transitions:
        target = transition["target_node"]
        if target not in groups:
            groups[target] = []
            order.append(target)
        groups[target].append(transition)
    result = []
    for target in order:
        items = groups[target]
        if len(items) == 1:
            result.append(items[0])
            continue
        if any(item.get("is_tool_call") or item["condition"].get("logic") != "or" for item in items):
            raise ValueError(
                f"internal: target {target!r} has an unconditional or intent transition and another one"
            )
        descriptions = list(dict.fromkeys(item["description"] for item in items))
        result.append({
            "target_node": target,
            "description": "; ".join(descriptions),
            "condition": {"logic": "or", "conditions": [
                condition for item in items for condition in item["condition"]["conditions"]
            ]},
        })
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
    reader = product_reader_code(products_variable, products_field)
    return f"""import json
import re
{reader}
try:
    body = config.get('body')
    products = load_products()
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


def _with_product_number(spec: PhoneAgentSpec, tool: dict[str, Any]) -> dict[str, Any]:
    """Let the model choose a product by its list number; a pre-hook sends the stored id."""
    result = copy.deepcopy(tool)
    body = result["function"]["parameters"]["properties"]["body"]
    properties = body.setdefault("properties", {})
    number_field = spec.confirmation.data["product_number_field"]
    id_field = spec.account.data["product_id_field"]
    if id_field not in properties or not _model_filled(properties[id_field]):
        return result
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
    return result


def _promise_tool(spec: PhoneAgentSpec, tool: dict[str, Any]) -> dict[str, Any]:
    """The model names only the product number; date, amount and id come from checked offers."""
    result = _with_product_number(spec, tool)
    body = result["function"]["parameters"]["properties"]["body"]
    properties = body.setdefault("properties", {})
    checked = (spec.confirmation.data["promise_date_field"], spec.confirmation.data["promise_amount_field"])
    for field in checked:
        if field not in properties:
            raise SpecError(f"confirmation field {field!r} is not a create_promise body field")
        properties.pop(field)
    body["required"] = [name for name in body.get("required", []) if name not in checked]
    result["pre_process_code"] = promise_values_hook(spec)
    result["response_mapping"] = [{"path": "data.ok", "variable": "promise_result_ok"}]
    return result


def _model_filled(prop: dict[str, Any]) -> bool:
    """True when the model must supply this body field (not baked by the workflow)."""
    default = prop.get("default")
    if not isinstance(default, str):
        return default is None
    match = re.fullmatch(r"\{\{([A-Za-z0-9_.]+)\}\}", default)
    return bool(match) and match.group(1) not in CALL_VARIABLES


def _model_fields(tool: dict[str, Any]) -> list[str]:
    body = tool["function"]["parameters"]["properties"]["body"]
    properties = body.get("properties", {})
    return [name for name in body.get("required", []) if _model_filled(properties.get(name, {}))]


SPECIAL_RESULT_PREFIX = "special_result_"

# Steps that stand for one spec step name. ``opening_reask`` asks the opening question
# again, so whatever is available in ``opening`` is available there too.
STEP_ALIASES = {"opening": ("opening", "opening_reask")}


def source_steps(path: SpecialPath) -> tuple[str, ...]:
    """The rendered steps a special path may fire in (its spec ``available_in``, expanded)."""
    return tuple(dict.fromkeys(
        step for name in path.available_in for step in STEP_ALIASES.get(name, (name,))
    ))


def _special_nodes(
    spec: PhoneAgentSpec, path: SpecialPath, key: str, by_name: dict[str, dict[str, Any]],
    tag_close: Any,
) -> tuple[dict[str, tuple[dict[str, Any], tuple[str, ...]]], dict[str, Any]]:
    """Return ({global key: (node, steps it may fire in)}, extra regular nodes) for one path.

    The path never asks the model whether it is finished: it speaks a fixed line, the
    engine (or, if a value is needed from the conversation, the model) runs the tool,
    and the exit routes on the tool result. A closing path goes straight to ``closing``,
    which derives ``special:<id>`` from the tool result (see close_rules); a path without
    a tool writes its state itself.
    """
    success = "closing" if path.then == "close" else "__previous__"
    failure = tag_close("special_tool_failed") if path.then == "close" else "__previous__"
    tool = None
    if path.tool:
        if path.tool not in by_name:
            raise SpecError(f"special path {path.id!r} references unavailable tool {path.tool!r}")
        tool = _with_product_number(spec, _tool_with_baked_args(by_name[path.tool], path.tool_args, path.id))
        # Write tools are not retried by the engine; the result decides the route.
        tool.setdefault("config", {})["maxRetries"] = 0
    result_variable = special_result_variable(path)

    def ok_transitions() -> list[dict[str, Any]]:
        return [
            _transition(success, "Special-path tool succeeded", [
                _condition(result_variable, "equals", value) for value in ("true", "True")
            ]),
            _transition(failure, "Special-path tool failed", [
                _condition(result_variable, "equals", value) for value in ("false", "False")
            ]),
        ]

    extra: dict[str, Any] = {}

    def action(node_key: str) -> dict[str, Any]:
        if tool is None and path.then == "close":
            node = _code_node(node_key, _write_close_state([("True", "special:" + path.id)]), [
                {"target_node": success, "description": "Line spoken", "condition": {"operator": "always"}},
            ])
            node["on_enter"] = {"type": "tts", "text": path.say.text}
            return node
        if tool is None:
            return {
                "name": node_key, "node_type": "conversation", "task_message": path.say.text,
                "on_enter": {"type": "tts", "text": path.say.text},
                "passthrough": True, "passthrough_default_transition": success,
                "transitions": [{"target_node": success, "description": "Line spoken", "condition": {"operator": "always"}}],
            }
        if not _model_fields(tool):
            # F-050: a tts entry on a passthrough api_request step breaks the turn on the platform
            # (HTTP 502, state rolled back). The line is spoken by a code step; the api step is silent.
            call_key = node_key + "_call"
            extra[call_key] = {
                "name": call_key, "node_type": "api_request",
                "on_enter": {"type": "silent"},
                "passthrough": True, "passthrough_default_transition": failure,
                "pre_actions": [tool],
                "response_mapping": [{"path": "data.ok", "variable": result_variable}],
                "transitions": [
                    ok_transitions()[0],
                    {"target_node": failure, "description": "Special-path tool did not succeed", "condition": {"operator": "always"}},
                ],
            }
            node = _code_node(node_key, f"vars[{(result_variable + '_said')!r}] = 'yes'\n", [
                {"target_node": call_key, "description": "Line spoken; run the tool", "condition": {"operator": "always"}},
            ])
            node["on_enter"] = {"type": "tts", "text": path.say.text}
            return node
        scoped = _response_mapping(tool, {"data.ok": result_variable})
        return _conversation(node_key, render_prompt(
            SPECIAL_PATH_TASK_TEMPLATE, when=path.when.text, say=path.say.text
        ), [scoped], ok_transitions())

    if tool is not None and _model_fields(tool) and path.ask is None:
        return _model_tool_special(spec, path, key, tool, result_variable, success, failure)
    if path.ask is None:
        node = action(key)
    else:
        go_key = key + "_go"
        extra[go_key] = action(go_key)
        choice = result_variable + "_choice"
        # F-047: an ask written as an instruction is phrased by the agent, never read aloud.
        phrased = bool(agent_directed(path.ask.text))
        ask_prompt = SPECIAL_ASK_PHRASED_TEMPLATE if phrased else SPECIAL_ASK_TASK_TEMPLATE
        node = _conversation(key, render_prompt(ask_prompt, ask=path.ask.text), [], [
            _transition(go_key, "The customer still wants this", [_condition(choice, "equals", "proceed")]),
            _transition("__previous__", "The customer accepts help instead", [_condition(choice, "equals", "stay")]),
        ])
        node["on_enter"] = {"type": "llm"} if phrased else {"type": "tts", "text": path.ask.text}
        node["extraction_schema"] = [{
            "name": choice, "type": "string", "enum_values": ["proceed", "stay"],
            "description": "proceed: the customer still insists on this request; stay: they accept help or drop it",
            "min_confidence": 0.8,
        }]
    node["description"] = path.when.text
    node["condition"] = {"operator": "matches_intent", "description": path.when.text}
    return {key: (node, source_steps(path))}, extra


def _done_transitions(source_variable: str, sources: tuple[str, ...]) -> list[dict[str, Any]]:
    """Return to the source step, or go to the read-back when every product is handled.

    No target appears twice (see group_transitions_by_target).
    """
    ready = _condition(OFFER_PROGRESS, "equals", "ready")
    not_ready = _condition(OFFER_PROGRESS, "not_equals", "ready")
    if "confirm_record" in sources:
        return [
            *(
                {
                    "target_node": source, "description": "Return to the step the request came from",
                    "condition": {"logic": "or", "conditions": [{"logic": "and", "conditions": [
                        _condition(source_variable, "equals", source), not_ready,
                    ]}]},
                }
                for source in sources if source != "confirm_record"
            ),
            {"target_node": "confirm_record", "description": "Read back the offers", "condition": {"operator": "always"}},
        ]
    return [
        _transition("confirm_record", "Every product now has an offer or a note", [ready]),
        *(
            _transition(source, "Return to the step the request came from", [
                _condition(source_variable, "equals", source)
            ])
            for source in sources[:-1]
        ),
        {"target_node": sources[-1], "description": "Return", "condition": {"operator": "always"}},
    ]


def _model_tool_special(
    spec: PhoneAgentSpec, path: SpecialPath, key: str, tool: dict[str, Any],
    result_variable: str, success: str, failure: str,
) -> tuple[dict[str, tuple[dict[str, Any], tuple[str, ...]]], dict[str, Any]]:
    """A special path whose tool needs a value from the conversation (e.g. which product).

    One small global code step per source step clears the previous result and remembers
    where to return, so a second use of the path never exits on a stale result and the
    return target is explicit. The conversation step then exits on the tool result.
    """
    source_variable = result_variable + "_from"
    done_key = key + "_done"
    returns = path.then == "return"
    globals_: dict[str, tuple[dict[str, Any], tuple[str, ...]]] = {}
    for source in source_steps(path):
        entry_key = f"{key}_at_{source}"
        entry = _code_node(entry_key, (
            f"vars[{result_variable!r}] = ''\n"
            f"vars[{source_variable!r}] = {source!r}\n"
        ), [{"target_node": key, "description": "Handle the special request", "condition": {"operator": "always"}}])
        entry["description"] = path.when.text
        entry["condition"] = {"operator": "matches_intent", "description": path.when.text}
        globals_[entry_key] = (entry, (source,))

    scoped = _response_mapping(tool, {"data.ok": result_variable})
    after_success = done_key if returns else success
    after_failure = done_key if returns else failure
    extra: dict[str, Any] = {key: _conversation(key, render_prompt(
        SPECIAL_PATH_TASK_TEMPLATE, when=path.when.text, say=path.say.text
    ), [scoped], [
        _transition(after_success, "Special-path tool succeeded", [
            _condition(result_variable, "equals", value) for value in ("true", "True")
        ]),
        _transition(after_failure, "Special-path tool failed", [
            _condition(result_variable, "equals", value) for value in ("false", "False")
        ]),
    ])}
    if returns:
        number_field = spec.confirmation.data["product_number_field"]
        body = scoped["function"]["parameters"]["properties"]["body"].get("properties", {})
        extra[done_key] = _code_node(done_key, special_noted_code(
            spec, result_variable, path.tool, number_field in body
        ), [
            *_done_transitions(source_variable, source_steps(path)),
        ])
    return globals_, extra


def special_result_variable(path: SpecialPath) -> str:
    return SPECIAL_RESULT_PREFIX + re.sub(r"[^A-Za-z0-9_]+", "_", path.id)


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


def _increment_code(variable: str, clear_variable: str, clear_value: str = "") -> str:
    return (
        "try:\n"
        f"    vars[{variable!r}] = int(vars.get({variable!r}) or 0) + 1\n"
        "except Exception:\n"
        f"    vars[{variable!r}] = 1\n"
        f"vars[{clear_variable!r}] = {clear_value!r}\n"
    )


def _confirmation_progress_code(spec: PhoneAgentSpec) -> str:
    confirmation = spec.confirmation.data
    expected = confirmation["expected_count_variable"]
    number = "create_promise_args." + confirmation["product_number_field"]
    maximum = confirmation["max_attempts_per_product"]
    return f"""import json
try:
    expected_count = max(1, int(vars.get({OFFERS_ACCEPTED_COUNT!r}) or vars.get({expected!r}) or 1))
except Exception:
    expected_count = 1
try:
    recorded_count = int(vars.get('promise_recorded_count') or 0)
except Exception:
    recorded_count = 0
raw_number = vars.get({number!r})
if raw_number is None:
    raw_args = vars.get('create_promise_args')
    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args)
        except Exception:
            raw_args = None
    if isinstance(raw_args, dict):
        raw_number = raw_args.get({confirmation["product_number_field"]!r})
product_number = str(raw_number or '')
attempt_key = 'promise_attempts_' + product_number
try:
    attempts = int(vars.get(attempt_key) or 0)
except Exception:
    attempts = 0
ok_value = vars.get('promise_result_ok')
if ok_value is None:
    ok_value = vars.get('create_promise_response.data.ok')
if ok_value is None:
    response = vars.get('create_promise_response')
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except Exception:
            response = None
    if isinstance(response, dict):
        data = response.get('data')
        if isinstance(data, dict):
            ok_value = data.get('ok')
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


# Call-end states that no existing variable identifies; each keeps a one-line tagging step.
# turn_limit: the engine's max_turn_transition sets no variable. special_tool_failed: the
# "no usable result" fallback of an engine tool step (HTTP error, or no ok field) sets no
# variable that is reliable in every failure mode.
TAGGED_CLOSE_STATES = ("turn_limit", "special_tool_failed")


def _is_true(variable: str) -> list[dict[str, Any]]:
    return [_condition(variable, "equals", value) for value in ("true", "True")]


def _is_false(variable: str) -> list[dict[str, Any]]:
    return [_condition(variable, "equals", value) for value in ("false", "False")]


def _all(*conditions: dict[str, Any]) -> dict[str, Any]:
    return {"logic": "and", "conditions": list(conditions)}


def close_rules(spec: PhoneAgentSpec) -> list[tuple[str, list[dict[str, Any]]]]:
    """The one priority order for call-end states derived from existing variables.

    Each entry is (state, OR-conditions). The same conditions route the source step to
    ``closing``, and ``closing`` (and the end-of-call close) re-evaluates them in this
    order; the first that holds names the state. Later call stages come first, so a
    variable left over from an earlier stage never wins. A ``close_state`` written by a
    code step (opening_unclear, offer_limit, promise_recorded, promise_failed, a special
    path without a tool, the tagged states) wins over every rule.
    """
    opening = spec.opening.data
    third = spec.third_party.data
    negotiation = spec.negotiation.data
    callback_results = ("callback_ok", "schedule_callback_response.data.ok")
    return [
        *(
            ("special:" + path.id, _is_true(special_result_variable(path)))
            for path in spec.special_paths if path.then == "close" and path.tool
        ),
        *(
            ("negotiation:" + value, [_all(
                _condition(negotiation["intent_variable"], "equals", value),
                _condition(OFFERS_ACCEPTED_COUNT, "less_than", 1),
            )])
            for value in negotiation["close_values"]
        ),
        ("account_failed", [_condition("account_failure_count", "greater_than", 0)]),
        ("identity_failed", [
            _all(_condition("identity_attempts_left", "less_than", 1), _condition("identity_verified", "equals", value))
            for value in ("false", "False")
        ]),
        ("callback_scheduled", [item for variable in callback_results for item in _is_true(variable)]),
        ("callback_failed", [
            *(item for variable in callback_results for item in _is_false(variable)),
            _condition("schedule_callback_failure_count", "greater_than", 0),
        ]),
        *(
            ("third_party:" + value, [_condition(third["intent_variable"], "equals", value)])
            for value in third["close_values"]
        ),
        *(
            ("opening:" + value, [_condition(opening["who_answered_variable"], "equals", value)])
            for value in opening["close_values"]
        ),
    ]


def _write_close_state(cases: list[tuple[str, str]]) -> str:
    """Code that writes ``close_state`` on the branch that routes to ``closing``.

    ``cases`` are (Python test, state) pairs, checked in order.
    """
    body = "".join(
        f"    {'if' if index == 0 else 'elif'} {test}:\n        vars['close_state'] = {_py_str(state)}\n"
        for index, (test, state) in enumerate(cases)
    )
    return "try:\n" + body + "except Exception:\n    pass\n"


def _close_state_derivation_code(spec: PhoneAgentSpec) -> str:
    """Shared snippet: ``derive_close_state()`` evaluates close_rules like the router does."""
    rules = [[state, {"logic": "or", "conditions": conditions}] for state, conditions in close_rules(spec)]
    return f"""import json
RULES = {_py_literal(rules)}


def holds(condition):
    try:
        if 'conditions' in condition:
            results = [holds(item) for item in condition['conditions']]
            return all(results) if condition.get('logic') == 'and' else any(results)
        name = condition.get('variable')
        operator = condition.get('operator')
        value = vars.get(name)
        present = value is not None and value != ''
        if operator == 'is_set':
            return present
        if operator == 'equals':
            return present and str(value) == str(condition.get('operand'))
        if operator == 'not_equals':
            return not (present and str(value) == str(condition.get('operand')))
        if operator in ('greater_than', 'less_than') and present:
            number = float(value)
            limit = float(condition.get('operand'))
            return number > limit if operator == 'greater_than' else number < limit
    except Exception:
        return False
    return False


def derive_close_state():
    try:
        written = vars.get('close_state')
        if written:
            return str(written)
        for state, condition in RULES:
            if holds(condition):
                return state
    except Exception:
        pass
    return ''
"""


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


def _outcome_choice_code(spec: PhoneAgentSpec) -> str:
    """Shared snippet: the outcome table and ``choose(candidates)``; never raises."""
    rows = ",\n".join(
        "    (" + ", ".join(_py_str(value) for value in row[:4]) + f", {row[4]!r})"
        for row in close_table(spec)
    )
    return f"""TABLE = [
{rows},
]


def choose(candidates):
    chosen = TABLE[-1]
    try:
        found = None
        for candidate in candidates:
            for row in TABLE:
                if row[0] == candidate:
                    found = row
                    break
            if found is not None:
                break
        if found is not None:
            chosen = found
        try:
            recorded = int(vars.get('promise_recorded_count') or 0)
        except Exception:
            recorded = 0
        if recorded > 0 and not chosen[4]:
            for row in TABLE:
                if row[0] == 'promise_recorded':
                    chosen = row
                    break
    except Exception:
        pass
    return chosen
"""


def _closing_code(spec: PhoneAgentSpec) -> str:
    """Pick outcome, reason and the closing sentence from call state; never raises."""
    return _close_state_derivation_code(spec) + _outcome_choice_code(spec) + f"""
chosen = choose([derive_close_state()])
vars['close_resolved_state'] = chosen[0]
vars['close_outcome'] = chosen[1]
if chosen[2]:
    vars['close_reason'] = chosen[2]
vars['closing_sentence'] = chosen[3] or {_py_str(CLOSING_FALLBACK_SAY.text)}
"""


def _hangup_hook_code(spec: PhoneAgentSpec, url: str) -> str:
    """Pre-hook of the end-of-call close. Fail-closed: the tool's URL is empty, and only the
    send branch writes the real ``url`` (as its last step). Skip if the closing chain
    already ran, else fill outcome and reason from call state. Never raises."""
    closing = spec.closing.data
    return _close_state_derivation_code(spec) + _outcome_choice_code(spec) + f"""
try:
    ok_value = str(vars.get('close_call_ok') or '').lower()
    try:
        attempts = int(vars.get('close_attempts') or 0)
    except Exception:
        attempts = 0
    if ok_value == 'true' or attempts > 0:
        # The closing chain already sent close_call: never send a second one.
        config['url'] = ''
        config['body'] = dict()
        vars['hangup_close'] = 'skipped'
    else:
        verified = str(vars.get('identity_verified') or '').lower() == 'true'
        candidates = [derive_close_state()]
        if not verified:
            candidates.append('hangup_unverified')
        candidates.append('hangup')
        chosen = choose(candidates)
        body = config.get('body')
        if isinstance(body, dict):
            body[{closing["outcome_field"]!r}] = chosen[1]
            if chosen[2]:
                body[{closing["reason_field"]!r}] = chosen[2]
            else:
                body.pop({closing["reason_field"]!r}, None)
            vars['hangup_close'] = 'sent:' + chosen[0]
            config['url'] = {_py_str(url)}
        else:
            vars['hangup_close'] = 'skipped:no_body'
except Exception:
    pass
"""


def _hangup_close_tool(spec: PhoneAgentSpec, tool: dict[str, Any]) -> dict[str, Any]:
    """Top-level end-of-call lifecycle tool that records an outcome if the call ended early.

    Every field resolves without the model (literal or call-variable defaults); the
    pre-hook computes the real outcome or neutralizes the request.
    """
    closing = spec.closing.data
    default = close_table(spec)[-1]
    result = copy.deepcopy(tool)
    result["function"]["name"] = "close_call_on_hangup"
    body = result["function"]["parameters"]["properties"]["body"]
    properties = body.setdefault("properties", {})
    kept = {}
    for name, prop in properties.items():
        if name == closing["outcome_field"]:
            kept[name] = {**prop, "default": default[1]}
        elif name == closing["reason_field"]:
            if default[2]:
                kept[name] = {**prop, "default": default[2]}
        elif not _model_filled(prop):
            kept[name] = prop
    body["properties"] = kept
    body.pop("required", None)
    # Fail-closed (review T-005c #1): no URL unless the pre-hook decides to send.
    url_property = result["function"]["parameters"]["properties"]["url"]
    real_url = str(url_property.get("default") or "")
    if not real_url or "{{" in real_url:
        raise SpecError("close_call has no fixed URL for the end-of-call close")
    url_property["default"] = ""
    result["config"] = {**result.get("config", {}), "alwaysRunsAt": ["end_of_call"], "maxRetries": 0}
    result["pre_process_code"] = _hangup_hook_code(spec, real_url)
    result.pop("response_mapping", None)
    return result


def _close_tool(spec: PhoneAgentSpec, tool: dict[str, Any]) -> dict[str, Any]:
    closing = spec.closing.data
    result = _tool_with_baked_args(tool, {
        closing["outcome_field"]: "{{close_outcome}}",
        closing["reason_field"]: "{{close_reason}}",
    }, "closing")
    # Write tool: no tool-level retries; the flow retries once (close_attempt).
    result.setdefault("config", {})["maxRetries"] = 0
    return result


def _check_identity_fields(
    spec: PhoneAgentSpec, tool: dict[str, Any], warnings: list[str] | None
) -> None:
    """Check the spec's identity questions against the tool's selector enum, whatever it is named."""
    properties = tool["function"]["parameters"]["properties"]["body"].get("properties", {})
    wanted = {question.field for question in spec.identity_questions}
    enums = {name: set(map(str, prop["enum"])) for name, prop in properties.items() if prop.get("enum")}
    if any(wanted <= values for values in enums.values()):
        return
    message = (
        "identity question fields " + ", ".join(sorted(wanted))
        + " are not all in one enum of the identity tool; not validated"
    )
    if warnings is not None:
        warnings.append(message)


def _render_spec_workflow(
    spec: PhoneAgentSpec, tools: list[dict[str, Any]], warnings: list[str] | None, plan: "RulePlan",
) -> dict[str, Any]:
    """Render the skeleton with the step and global rules chosen by ``plan``."""
    by_name = _tool_index(tools)
    _check_identity_fields(spec, by_name["verify_identity"], warnings)
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

    # (variable, reset value). Enum variables get the framework value "none": the platform
    # rejects "" for an enum and would keep the old intent (F-052).
    reset_variables = [
        (special_result_variable(path), "") for path in spec.special_paths
    ] + [(negotiation["intent_variable"], FRAMEWORK_NONE_VALUE), (confirmation["intent_variable"], FRAMEWORK_NONE_VALUE)]
    used = {
        "opening", "opening_reask", "opening_unclear", "third_party", IDENTITY_CHECK, "identity", "account", "negotiate",
        "confirm_record", "confirmation_progress", "closing", "closing_say", "close_attempt",
        "offer_setup", "check_offer",
        "close_record", "end_call",
    }
    close_nodes: dict[str, str] = {}
    rules = dict(close_rules(spec))

    def to_closing(state: str, description: str) -> dict[str, Any]:
        """Route to ``closing`` on the rule that also derives ``state`` there."""
        return _transition("closing", description, rules[state])

    def tag_close(state: str) -> str:
        """Tagging step for a state no variable identifies (TAGGED_CLOSE_STATES)."""
        if state not in TAGGED_CLOSE_STATES:
            raise ValueError(f"internal: {state!r} is derived, not tagged")
        if state not in close_nodes:
            key = "close_" + re.sub(r"[^A-Za-z0-9_]+", "_", state).strip("_")
            base, suffix = key, 2
            while key in used:
                key = f"{base}_{suffix}"
                suffix += 1
            used.add(key)
            close_nodes[state] = key
        return close_nodes[state]

    tag_close("turn_limit")
    special_keys = [(path, _special_key(path.id, used)) for path in spec.special_paths]

    opening_transitions = [
        *(to_closing("opening:" + value, "Opening path must close") for value in opening["close_values"]),
        _transition(IDENTITY_CHECK, "Customer answered", [
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
    opening_values = dict(
        address=" ".join("{{" + name + "}}" for name in opening["address_with"]),
        question=opening["confirmation_question"]["text"],
        unclear=opening["unclear_instruction"]["text"],
        forbidden=", ".join(opening["forbidden_before_verification"]),
        rules=_rule_lines(plan.rules("opening")),
    )
    unclear_limit = opening["max_unclear_asks"] - 1
    nodes: dict[str, Any] = {
        "opening": {
            **_conversation("opening", render_prompt(
                OPENING_TASK_TEMPLATE, introduction=spec.agent.introduction.text, **opening_values
            ), [], opening_transitions),
            # The introduction is spoken once; asking again happens in opening_reask.
            "on_enter_first_entry_only": True,
        },
        "opening_reask": _conversation("opening_reask", render_prompt(
            OPENING_REASK_TASK_TEMPLATE, **opening_values
        ), [], copy.deepcopy(opening_transitions)),
        "opening_unclear": _code_node("opening_unclear", _increment_code(
            opening["unclear_count_variable"], opening["who_answered_variable"], FRAMEWORK_NONE_VALUE
        ) + _write_close_state([
            (f"int(vars.get({opening['unclear_count_variable']!r}) or 0) > {unclear_limit!r}", "opening_unclear"),
        ]), [
            _transition("closing", "Opening uncertainty limit reached", [
                _condition(opening["unclear_count_variable"], "greater_than", unclear_limit)
            ]),
            {"target_node": "opening_reask", "description": "Ask once more", "condition": {"operator": "always"}},
        ]),
        "third_party": _conversation("third_party", render_prompt(
            THIRD_PARTY_TASK_TEMPLATE, rules=_rule_lines(plan.rules("third_party"))
        ), [callback_tool], [
            to_closing("callback_scheduled", "Callback was scheduled"),
            to_closing("callback_failed", "Callback could not be scheduled"),
            *(to_closing("third_party:" + value, "Third-party path is complete") for value in third["close_values"]),
        ]),
        # F-049: a replayed or re-entered identity step must not ask again once verified.
        IDENTITY_CHECK: _code_node(IDENTITY_CHECK, "vars['identity_checked'] = 'yes'\n", [
            _transition("account", "Identity already verified", [
                _condition("identity_verified", "equals", value) for value in ("true", "True")
            ]),
            {"target_node": "identity", "description": "Ask the security questions", "condition": {"operator": "always"}},
        ]),
        "identity": _conversation("identity", render_prompt(
            IDENTITY_TASK_TEMPLATE, questions=questions,
            answer_verified=identity["answer_verified_field"],
            failed_answer=identity["failed_answer_instruction"]["text"],
            attempts_left=identity["attempts_left_field"],
            exhausted_say=identity["exhausted_say"]["text"],
            wait_line=spec.agent.wait_line or ACCOUNT_WAIT_LINE.text,
            rules=_rule_lines(plan.rules("identity")),
        ), [identity_tool], [
            _transition("account", "Identity verified", [
                _condition("identity_verified", "equals", value) for value in ("true", "True")
            ]),
            to_closing("identity_failed", "No identity attempts remain"),
        ]),
        "account": {
            # F-050: silent. A tts entry here broke the turn on the platform (502 and rollback);
            # the wait line is said by the identity step after the last answer passed.
            "name": "account", "node_type": "api_request", "on_enter": {"type": "silent"},
            "passthrough": True, "passthrough_default_transition": "offer_setup",
            "pre_actions": [account_tool],
            "response_mapping": [{
                "path": "data." + spec.account.data["products_field"],
                "variable": spec.account.data["products_variable"],
            }],
            "transitions": [
                to_closing("account_failed", "Account retrieval failed after retry"),
                {"target_node": "offer_setup", "description": "Account loaded", "condition": {"operator": "always"}},
            ],
        },
        "offer_setup": _code_node("offer_setup", offer_setup_code(spec), [
            {"target_node": "negotiate", "description": "Product facts computed", "condition": {"operator": "always"}},
        ]),
        "check_offer": _code_node("check_offer", check_offer_code(spec, reset_variables) + _write_close_state([
            (f"vars.get({OFFER_PROGRESS!r}) == 'limit'", "offer_limit"),
        ]), [
            _transition("confirm_record", "Every agreed offer passed the check", [
                _condition(OFFER_PROGRESS, "equals", "ready")
            ]),
            _transition("closing", "Too many rejected offers", [
                _condition(OFFER_PROGRESS, "equals", "limit")
            ]),
            {"target_node": "negotiate", "description": "Discuss the check result", "condition": {"operator": "always"}},
        ]),
        "negotiate": _conversation("negotiate", render_prompt(
            NEGOTIATION_TASK_TEMPLATE,
            rules=_rule_lines(plan.rules("negotiate")),
        ), [], [
            {
                # F-051: a date is enough. Without an amount the check uses the amount the
                # agent last proposed, so a customer who only names a date is checked too.
                "target_node": "check_offer", "description": "The customer named or accepted a date",
                "condition": {"logic": "or", "conditions": [
                    {"logic": "and", "conditions": [
                        {"variable": OFFER_DATE, "operator": "is_set"},
                        _condition(OFFER_DATE, "not_equals", ""),
                    ]},
                    # F-052: "yes, that works" to the date the agent just proposed.
                    _condition(OFFER_ACCEPTS, "equals", ACCEPTS_YES),
                ]},
            },
            *(
                {
                    "target_node": "confirm_record",
                    "description": "The customer is done and some offers were accepted",
                    "condition": {"logic": "or", "conditions": [{"logic": "and", "conditions": [
                        _condition(negotiation["intent_variable"], "equals", value),
                        _condition(OFFERS_ACCEPTED_COUNT, "greater_than", 0),
                    ]}]},
                }
                for value in [*negotiation["confirm_values"], *negotiation["close_values"]]
            ),
            *(
                to_closing("negotiation:" + value, "Negotiation ends without an accepted offer")
                for value in negotiation["close_values"]
            ),
        ]),
        "confirm_record": _conversation("confirm_record", render_prompt(
            CONFIRM_TASK_TEMPLATE, rules=_rule_lines(plan.rules("confirm_record"))
        ), [promise_tool], [
            _transition("negotiate", "Customer revised or rejected the read-back", [
                _condition(confirmation["intent_variable"], "equals", value)
                for value in confirmation["revise_values"]
            ]),
            _transition("confirmation_progress", "Promise tool returned a result", [
                _condition("promise_result_ok", "equals", value)
                for value in ("true", "True", "false", "False")
            ]),
        ]),
        "confirmation_progress": _code_node(
            "confirmation_progress", _confirmation_progress_code(spec) + _write_close_state([
                ("vars.get('promise_progress_state') == 'complete'", "promise_recorded"),
                ("vars.get('promise_progress_state') == 'exhausted'", "promise_failed"),
            ]), [
                _transition("closing", "All agreed products were recorded", [
                    _condition("promise_progress_state", "equals", "complete")
                ]),
                _transition("closing", "A product exhausted its recording attempts", [
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
                _transition("end_call", "The closing result was already recorded", [
                    _condition("close_call_ok", "equals", value) for value in ("true", "True")
                ]),
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

    global_nodes: dict[str, Any] = {}
    global_sources: dict[str, tuple[str, ...]] = {}
    for path, key in special_keys:
        made, extra = _special_nodes(spec, path, key, by_name, tag_close)
        for global_key, (node, sources) in made.items():
            if global_key in nodes or global_key in global_nodes:
                raise SpecError(f"special path step name collision: {global_key!r}")
            global_nodes[global_key] = node
            global_sources[global_key] = sources
        nodes.update(extra)

    for state, key in close_nodes.items():
        nodes[key] = _code_node(key, _write_close_state([("True", state)]), [
            {"target_node": "closing", "description": "Compute the closing outcome", "condition": {"operator": "always"}},
        ])

    # Extraction is restricted to categorical routing signals supplied by the spec.
    # A bare greeting gets its own value: it routes nowhere, so the step stays and asks
    # again, and it never counts toward the unclear limit.
    for key in ("opening", "opening_reask"):
        nodes[key]["extraction_schema"] = [{
            "name": opening["who_answered_variable"], "type": "string",
            "description": render_prompt(WHO_ANSWERED_DESCRIPTION, greeting=OPENING_GREETING_VALUE),
            "enum_values": [*opening["who_answered_options"], OPENING_GREETING_VALUE, FRAMEWORK_NONE_VALUE],
            "min_confidence": 0.8,
        }]
    nodes["third_party"]["extraction_schema"] = [{
        "name": third["intent_variable"], "type": "string",
        "description": "The third party's current intent", "enum_values": [*third["intent_values"], FRAMEWORK_NONE_VALUE],
        "min_confidence": 0.8,
    }]
    nodes["negotiate"]["extraction_schema"] = [{
        "name": OFFER_DATE, "type": "string",
        "description": "Copy the payment date phrase from the customer's last message unchanged. If the customer accepts a date the agent just proposed without naming it (for example \"yes, that works\"), copy the date as the agent said it. Do not resolve relative dates with the system clock. Empty if none.",
        "min_confidence": 0.7,
    }, {
        "name": OFFER_AMOUNT, "type": "float",
        "description": "The payment amount the customer proposes or accepts in their last message. Empty if none.",
        "min_confidence": 0.7,
    }, {
        "name": OFFER_AMOUNT_KIND, "type": "string",
        "description": "Meaning of the amount in the customer's last message: full for the full or entire amount; minimum for the minimum, required instalment, or instalment amount; other for a numeric or different amount; none if the customer names no amount.",
        "enum_values": [*AMOUNT_KINDS, AMOUNT_KIND_NONE],
        "min_confidence": 0.7,
    }, {
        "name": OFFER_PROPOSED_KIND, "type": "string",
        "description": "Which amount the agent proposed most recently for the product being discussed now: full for the full amount due; minimum for the minimum or floor amount. When the talk moves to another product, full unless the agent proposed that product's minimum. Keep the previous value if the agent proposed no new amount.",
        "enum_values": ["full", "minimum"],
        "min_confidence": 0.7,
    }, {
        "name": OFFER_ACCEPTS, "type": "string",
        "description": "yes if the customer's last message accepts the date and amount the agent just proposed without naming a date (for example \"yes, that works\" or \"fine\"); none otherwise.",
        "enum_values": [ACCEPTS_YES, FRAMEWORK_NONE_VALUE],
        "min_confidence": 0.8,
    }, {
        "name": OFFER_PRODUCT, "type": "integer",
        "description": "The number of the product in the account facts list that the offer is for. Empty if unclear.",
        "min_confidence": 0.7,
    }, {
        "name": negotiation["intent_variable"], "type": "string",
        "description": (
            "The customer's negotiation intent. Values " + ", ".join(negotiation["close_values"])
            + " mean the customer refuses any payment or arrangement after being asked for alternatives. "
            + "Not today, not now, uncertainty about a date, or inability to pay on one proposed date are not refusal; keep negotiating."
        ) + " none: only the system writes it; choose a value above.",
        "enum_values": [*negotiation["intent_values"], FRAMEWORK_NONE_VALUE],
        "min_confidence": 0.8,
    }, {
        "name": confirmation["expected_count_variable"], "type": "integer",
        "description": "Number of products in the customer's confirmed proposal",
        "min_confidence": 0.8,
    }]
    nodes["confirm_record"]["extraction_schema"] = [{
        "name": confirmation["intent_variable"], "type": "string",
        "description": "Whether the customer confirms or revises the read-back",
        "enum_values": [*confirmation["intent_values"], FRAMEWORK_NONE_VALUE], "min_confidence": 0.8,
    }]

    for node in [*nodes.values(), *global_nodes.values()]:
        _apply_conversation_tool_rules(node)
        if node.get("transitions"):
            node["transitions"] = group_transitions_by_target(node["transitions"])

    for global_key, sources in global_sources.items():
        global_nodes[global_key]["excluded_nodes"] = sorted(
            [name for name in nodes if name not in sources] + list(global_nodes)
        )

    return {
        "initial_node": "opening",
        "system_prompt": render_prompt(
            MULTI_STEP_SYSTEM_PROMPT_TEMPLATE,
            agent_name=spec.agent.name,
            language=spec.agent.language,
            rules=_rule_lines(plan.rules(GLOBAL)),
        ),
        "nodes": nodes,
        "global_nodes": global_nodes,
        # F-012: records an outcome when the call ends before the closing chain ran.
        "tools": [_hangup_close_tool(spec, by_name["close_call"])],
        "test_variables": {
            "customer_id": "placeholder_customer", "first_name": "Test", "last_name": "Customer",
            "title": "Mx", "now": "2000-01-03T12:00",
        },
    }


# ---------------------------------------------------------------------------
# Prompt budget (T-009): every spec rule ends up somewhere, and the trace says where.
# ---------------------------------------------------------------------------

PROMPT_TARGET_TOKENS = 1200
PROMPT_HARD_LIMIT_TOKENS = 1500
BUDGET_EXCEEDED = "budget_exceeded_but_shipped"
GLOBAL = "global"
# Step prompt -> spec sections whose rules it shows. Closing rules have no step prompt:
# a rule not guaranteed by the closing code goes to the global prompt.
RULE_STEPS = {
    "opening": ("opening",),
    "third_party": ("third_party",),
    "identity": ("identity",),
    "negotiate": ("account", "negotiation", "offer"),
    "confirm_record": ("confirmation",),
    GLOBAL: ("global", "closing"),
}
# Nodes rendered from a plan step's rules (opening_reask repeats the opening rules).
STEP_NODES = {
    "opening": ("opening", "opening_reask"), "third_party": ("third_party",), "identity": ("identity",),
    "negotiate": ("negotiate",), "confirm_record": ("confirm_record",),
}
_FILLER = re.compile(r"\b(?:the|a|an|that)\b")


def enforcement_available(spec: PhoneAgentSpec, check: str) -> bool:
    """True when the generated code really performs ``check`` for this spec."""
    offer = spec.offer.data
    limit = offer.get("max_rejected_offers")
    return {
        # Dates: a latest-date rule must exist (earliest alone does not cover deadline rules).
        "offer_dates": bool(offer.get("latest")),
        "business_days": bool(offer.get("promise_date_must_be_business_day")),
        "offer_amounts": bool(offer.get("min_amount") or offer.get("max_amount")),
        "weekday_reading": offer.get("next_weekday", "ask") != "ask",
        "invalid_offer_limit": isinstance(limit, int) and not isinstance(limit, bool) and limit >= 1,
        "identity_attempts": bool(spec.identity.data.get("attempts_left_field") and spec.identity_questions),
        "closing_outcome": bool(spec.outcomes and spec.closing.data.get("outcome_field")),
    }.get(check, False)


def _sentences(text: str) -> frozenset[str]:
    return frozenset(filter(None, (_norm_rule(part) for part in re.split(r"(?<=[.!?;])\s+", text))))


def _norm_rule(text: str) -> str:
    text = re.sub(r"[^a-z0-9<> ]+", " ", text.lower())
    return re.sub(r"\s+", " ", _FILLER.sub(" ", text)).strip()


class RulePlan:
    """Where each spec rule goes: a step prompt, the global prompt, or code only."""

    def __init__(self, spec: PhoneAgentSpec) -> None:
        self.spec = spec
        sections = {
            "opening": spec.opening.rules, "third_party": spec.third_party.rules, "identity": spec.identity.rules,
            "account": spec.account.rules, "negotiation": spec.negotiation.rules,
            "confirmation": spec.confirmation.rules, "offer": spec.offer.rules,
            "global": spec.global_rules, "closing": spec.closing.rules,
        }
        # (rule id, rule, step it is rendered in, or None when it is not in any prompt)
        self.entries: list[list[Any]] = []
        self.notes: dict[str, str] = {}
        for step, names in RULE_STEPS.items():
            for name in names:
                for index, rule in enumerate(sections[name]):
                    key = f"global_rules[{index}]" if name == "global" else f"{name}.rules[{index}]"
                    self.entries.append([key, rule, step])
                    self.notes[key] = "closing rule, no step prompt" if name == "closing" else "its section"
        # Closing rules have no step prompt: all start in the global prompt. A rule tagged
        # closing_outcome leaves it only under budget pressure, like every other tag (T-009b).

    def _code_ok(self, rule: Rule) -> bool:
        return bool(rule.enforced_by) and enforcement_available(self.spec, rule.enforced_by)

    def _to_code(self, entry: list[Any]) -> None:
        entry[2] = None
        self.notes[entry[0]] = f"code: {entry[1].enforced_by}"

    def rules(self, step: str) -> tuple[Rule, ...]:
        return tuple(rule for _, rule, where in self.entries if where == step)

    def drop_code_enforced(self, steps: set[str]) -> int:
        moved = 0
        for entry in self.entries:
            if entry[2] in steps and self._code_ok(entry[1]):
                self._to_code(entry)
                moved += 1
        return moved

    def drop_duplicates(self, steps: set[str]) -> int:
        """Remove a step rule whose every sentence appears word for word (ignoring case,
        punctuation and articles) in another rule of the same step or in a global rule, which
        every step prompt includes. Whole sentences only: a part of a sentence can change its
        meaning ("offer the floor" inside "do not offer the floor")."""
        moved = 0
        for entry in self.entries:
            key, rule, where = entry
            if where not in steps:
                continue
            mine = _sentences(rule.text)
            for other_key, other, other_where in self.entries:
                if other_key == key or other_where not in (where, GLOBAL) or not mine:
                    continue
                if where == GLOBAL and other_where != GLOBAL:
                    continue
                theirs = _sentences(other.text)
                if mine <= theirs and (mine != theirs or other_where != where or self._before(other_key, key)):
                    entry[2] = None
                    place = "global prompt" if other_where == GLOBAL else f"step {other_where}"
                    self.notes[key] = f"duplicate of {other_key} ({place})"
                    moved += 1
                    break
        return moved

    def _before(self, first: str, second: str) -> bool:
        keys = [entry[0] for entry in self.entries]
        return keys.index(first) < keys.index(second)

    def move_shared_to_global(self) -> int:
        """A rule whose wording appears in two or more step prompts is said once, globally."""
        by_text: dict[str, list[list[Any]]] = {}
        for entry in self.entries:
            if entry[2] not in (None, GLOBAL):
                by_text.setdefault(_norm_rule(entry[1].text), []).append(entry)
        moved = 0
        for entries in by_text.values():
            if len({entry[2] for entry in entries}) < 2:
                continue
            steps = sorted({entry[2] for entry in entries})
            entries[0][2] = GLOBAL
            self.notes[entries[0][0]] = f"moved: was in {', '.join(steps)}"
            for entry in entries[1:]:
                entry[2] = None
                self.notes[entry[0]] = f"duplicate of {entries[0][0]} (global prompt)"
            moved += len(entries)
        return moved

    def placements(self) -> list[str]:
        lines = []
        for key, rule, where in self.entries:
            place = "global prompt" if where == GLOBAL else f"step {where}" if where else "not in a prompt"
            note = self.notes[key]
            if where and rule.enforced_by:
                note += (f"; code also enforces {rule.enforced_by}, kept: within budget" if self._code_ok(rule)
                         else f"; tagged {rule.enforced_by} but this spec has no data for that check, kept")
            lines.append(f"{key} -> {place} ({note}): {rule.text[:80]}")
        return lines


def speakable_spec(spec: PhoneAgentSpec) -> tuple[PhoneAgentSpec, list[str]]:
    """Make every field spoken word for word safe to say (F-047).

    ``Say: "..."`` wrappers are unwrapped. Text that still addresses the agent is replaced:
    an outcome line by a polite goodbye, a special path line by a short thank-you, a wait
    line by the builder default; a special path question is phrased by the agent instead.
    Every replacement is returned as a ``spoken_fallback`` warning.
    """
    notes: list[str] = []

    def clean(text: str, fallback: str, where: str) -> str:
        words = spoken_words(text)
        reason = agent_directed(words)
        if not reason:
            return words
        notes.append(f"spoken_fallback {where}: {reason}; spoken instead: {fallback!r}")
        return fallback

    outcomes = tuple(
        dataclasses.replace(item, say=dataclasses.replace(
            item.say, text=clean(item.say.text, CLOSING_FALLBACK_SAY.text, f"outcomes[{index}].say")))
        for index, item in enumerate(spec.outcomes)
    )
    paths = []
    for index, path in enumerate(spec.special_paths):
        say = dataclasses.replace(path.say, text=clean(path.say.text, SPECIAL_SAY_FALLBACK.text,
                                                       f"special_paths[{index}].say"))
        ask = path.ask
        if ask is not None:
            ask = dataclasses.replace(ask, text=spoken_words(ask.text))
            reason = agent_directed(ask.text)
            if reason:
                notes.append(f"spoken_fallback special_paths[{index}].ask: {reason}; the agent phrases the question")
        paths.append(dataclasses.replace(path, say=say, ask=ask))
    wait_line = clean(spec.agent.wait_line, ACCOUNT_WAIT_LINE.text, "agent.wait_line") if spec.agent.wait_line else ""
    agent = dataclasses.replace(spec.agent, wait_line=wait_line)
    return dataclasses.replace(spec, outcomes=outcomes, special_paths=tuple(paths), agent=agent), notes


def build_spec_workflow(
    spec: PhoneAgentSpec, tools: list[dict[str, Any]], warnings: list[str] | None = None,
    placements: list[str] | None = None, *,
    target_tokens: int = PROMPT_TARGET_TOKENS, hard_limit_tokens: int = PROMPT_HARD_LIMIT_TOKENS,
) -> dict[str, Any]:
    """Render the deterministic skeleton from a validated spec and OpenAPI tools.

    Prompt budget: a step over ``target_tokens`` first loses rules the generated code
    guarantees, then duplicate wording, then rules shared by several steps move to the
    global prompt. A step still over ``hard_limit_tokens`` is shipped with every rule and a
    ``budget_exceeded_but_shipped`` placement line; the build never stops on the budget. Non-fatal problems go to ``warnings``; ``placements`` receives one line per rule
    (where it ended up) and the per-step budget summary.
    """
    spec, spoken_notes = speakable_spec(spec)
    plan = RulePlan(spec)

    def render() -> tuple[dict[str, Any], list[str], dict[str, int]]:
        found: list[str] = []
        workflow = _render_spec_workflow(spec, tools, found, plan)
        return workflow, found, workflow_prompt_estimates(workflow)

    workflow, found, estimates = render()
    before = dict(estimates)
    stages: list[str] = []

    def over_steps(limit: int) -> set[str]:
        over_nodes = {key for key, value in estimates.items() if value > limit}
        steps = {step for step, keys in STEP_NODES.items() if over_nodes & set(keys)}
        # Every prompt includes the global rules: any step over the limit can shrink them too.
        return steps | ({GLOBAL} if over_nodes else set())

    for name, stage in (
        ("code-enforced rules left out", plan.drop_code_enforced),
        ("duplicate wording removed", plan.drop_duplicates),
    ):
        steps = over_steps(target_tokens)
        if not steps:
            break
        if stage(steps):
            stages.append(name)
            workflow, found, estimates = render()
    if over_steps(target_tokens) and plan.move_shared_to_global():
        stages.append("shared rules moved to the global prompt")
        workflow, found, estimates = render()

    if warnings is not None:
        warnings.extend(found)
        warnings.extend(spoken_notes)
    if placements is not None:
        placements.extend(plan.placements())
        for key in sorted(estimates):
            if before[key] != estimates[key] or estimates[key] > target_tokens:
                placements.append(f"budget {key}: ~{before[key]} -> ~{estimates[key]} tokens "
                                  f"(target {target_tokens}, limit {hard_limit_tokens})")
        if stages:
            placements.append("budget stages: " + "; ".join(stages))
    # CTO decision (T-009b): an over-long prompt never stops the build. Losing a whole brief
    # is worse than a long prompt; the step ships with every rule and a clear warning.
    over_limit = {key: value for key, value in estimates.items() if value > hard_limit_tokens}
    if placements is not None:
        for key, value in sorted(over_limit.items()):
            placements.append(f"{BUDGET_EXCEEDED} {key}: ~{value} tokens > limit {hard_limit_tokens} "
                              "after all budget stages; shipped with every rule")
    if warnings is not None:
        for key, value in sorted(estimates.items()):
            if value > hard_limit_tokens:
                warnings.append(f"{key}: prompt ~{value} tokens is over the hard limit {hard_limit_tokens}; "
                                "shipped anyway, no rule cut")
            elif value > target_tokens:
                warnings.append(f"{key}: prompt ~{value} tokens is over the target {target_tokens} "
                                f"(limit {hard_limit_tokens})")
    return workflow


def workflow_prompt_estimates(workflow: dict[str, Any]) -> dict[str, int]:
    """Return conservative character/4 estimates for each conversation node."""
    system = str(workflow.get("system_prompt", ""))
    return {
        key: math.ceil((
            len(system)
            + len(str(node.get("task_message", "")))
            + sum(len(str(tool.get("function", {}).get("description", ""))) for tool in node.get("tools", []))
        ) / 4)
        for key, node in {**workflow.get("nodes", {}), **workflow.get("global_nodes", {})}.items()
        if node.get("node_type") == "conversation"
    }


def workflow_tools_by_step(workflow: dict[str, Any]) -> dict[str, list[str]]:
    return {
        key: [_tool_name(tool) for tool in node.get("tools", [])] + [
            _tool_name(tool) + " (engine)" for tool in node.get("pre_actions", [])
            if _tool_name(tool) != "code_exec"
        ]
        for key, node in {**workflow.get("nodes", {}), **workflow.get("global_nodes", {})}.items()
    }
