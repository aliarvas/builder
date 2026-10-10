"""Typed, versioned input specification for multi-step phone agents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SpecError(ValueError):
    """Raised when a phone-agent spec is invalid."""


@dataclass(frozen=True)
class Rule:
    text: str
    source: str


@dataclass(frozen=True)
class AgentSpec:
    name: str
    language: str
    introduction: Rule


@dataclass(frozen=True)
class StageSpec:
    rules: tuple[Rule, ...]
    data: dict[str, Any]


@dataclass(frozen=True)
class IdentityQuestion:
    field: str
    ask: Rule
    answer_format: Rule


@dataclass(frozen=True)
class SpecialPath:
    id: str
    when: Rule
    say: Rule
    tool: str
    tool_args: dict[str, Any]
    outcome: str
    reason: str
    available_in: tuple[str, ...]
    then: str


@dataclass(frozen=True)
class Outcome:
    outcome: str
    reason: str
    when: Rule


@dataclass(frozen=True)
class PhoneAgentSpec:
    spec_version: int
    agent: AgentSpec
    opening: StageSpec
    third_party: StageSpec
    identity: StageSpec
    identity_questions: tuple[IdentityQuestion, ...]
    account: StageSpec
    negotiation: StageSpec
    confirmation: StageSpec
    special_paths: tuple[SpecialPath, ...]
    outcomes: tuple[Outcome, ...]
    global_rules: tuple[Rule, ...]


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SpecError(f"{path} must be an object")
    return value


def _string(value: Any, path: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise SpecError(f"{path} must be a non-empty string")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise SpecError(f"{path} must be an array")
    return value


def _required(obj: dict[str, Any], key: str, path: str) -> Any:
    if key not in obj:
        raise SpecError(f"missing required section or field: {path}.{key}")
    return obj[key]


def _rule(value: Any, path: str) -> Rule:
    obj = _object(value, path)
    return Rule(
        _string(_required(obj, "text", path), f"{path}.text"),
        _string(_required(obj, "source", path), f"{path}.source", empty=True),
    )


def _rules(value: Any, path: str) -> tuple[Rule, ...]:
    return tuple(_rule(item, f"{path}[{index}]") for index, item in enumerate(_list(value, path)))


def _stage(root: dict[str, Any], name: str) -> StageSpec:
    obj = _object(_required(root, name, "$"), name)
    rules = _rules(_required(obj, "rules", name), f"{name}.rules")
    return StageSpec(rules, {key: value for key, value in obj.items() if key != "rules"})


def _string_list(data: dict[str, Any], key: str, path: str) -> tuple[str, ...]:
    return tuple(
        _string(item, f"{path}.{key}[{index}]")
        for index, item in enumerate(_list(_required(data, key, path), f"{path}.{key}"))
    )


def parse_spec(value: Any) -> PhoneAgentSpec:
    root = _object(value, "$" )
    version = _required(root, "spec_version", "$")
    if version != 1:
        raise SpecError(f"unsupported spec_version {version!r}; expected 1")

    agent_data = _object(_required(root, "agent", "$"), "agent")
    agent = AgentSpec(
        _string(_required(agent_data, "name", "agent"), "agent.name"),
        _string(_required(agent_data, "language", "agent"), "agent.language"),
        _rule(_required(agent_data, "introduction", "agent"), "agent.introduction"),
    )
    stages = {name: _stage(root, name) for name in (
        "opening", "third_party", "identity", "account", "negotiation", "confirmation"
    )}

    questions = tuple(
        IdentityQuestion(
            _string(_required(obj := _object(item, f"identity.questions[{index}]"), "field", f"identity.questions[{index}]"), f"identity.questions[{index}].field"),
            _rule(_required(obj, "ask", f"identity.questions[{index}]"), f"identity.questions[{index}].ask"),
            _rule(_required(obj, "answer_format", f"identity.questions[{index}]"), f"identity.questions[{index}].answer_format"),
        )
        for index, item in enumerate(_list(_required(stages["identity"].data, "questions", "identity"), "identity.questions"))
    )
    if not questions:
        raise SpecError("identity.questions must contain at least one question")

    outcomes = tuple(
        Outcome(
            _string(_required(obj := _object(item, f"outcomes[{index}]"), "outcome", f"outcomes[{index}]"), f"outcomes[{index}].outcome"),
            _string(_required(obj, "reason", f"outcomes[{index}]"), f"outcomes[{index}].reason", empty=True),
            _rule(_required(obj, "when", f"outcomes[{index}]"), f"outcomes[{index}].when"),
        )
        for index, item in enumerate(_list(_required(root, "outcomes", "$"), "outcomes"))
    )
    if not outcomes:
        raise SpecError("outcomes must contain at least one entry")
    known_outcomes = {(item.outcome, item.reason) for item in outcomes}

    special_paths: list[SpecialPath] = []
    for index, item in enumerate(_list(_required(root, "special_paths", "$"), "special_paths")):
        path = f"special_paths[{index}]"
        obj = _object(item, path)
        tool_args = _object(_required(obj, "tool_args", path), f"{path}.tool_args")
        if any(value is None or isinstance(value, (dict, list)) for value in tool_args.values()):
            raise SpecError(f"{path}.tool_args values must be non-null scalars")
        special = SpecialPath(
            _string(_required(obj, "id", path), f"{path}.id"),
            _rule(_required(obj, "when", path), f"{path}.when"),
            _rule(_required(obj, "say", path), f"{path}.say"),
            _string(_required(obj, "tool", path), f"{path}.tool", empty=True),
            tool_args,
            _string(_required(obj, "outcome", path), f"{path}.outcome"),
            _string(_required(obj, "reason", path), f"{path}.reason", empty=True),
            _string_list(obj, "available_in", path),
            _string(_required(obj, "then", path), f"{path}.then"),
        )
        allowed_steps = {"opening", "third_party", "identity", "negotiate", "confirm_record"}
        unknown_steps = set(special.available_in) - allowed_steps
        if not special.available_in or unknown_steps:
            raise SpecError(f"{path}.available_in contains unsupported steps: {sorted(unknown_steps)}")
        if special.then not in {"close", "return"}:
            raise SpecError(f"{path}.then must be 'close' or 'return'")
        if special.then == "close" and (special.outcome, special.reason) not in known_outcomes:
            raise SpecError(
                f"{path} references unknown outcome/reason: {special.outcome!r}/{special.reason!r}"
            )
        special_paths.append(special)

    global_rules = _rules(_required(root, "global_rules", "$"), "global_rules")
    # Validate renderer-required routing/configuration fields here for early, clear errors.
    _string_list(stages["opening"].data, "who_answered_options", "opening")
    _string_list(stages["opening"].data, "identity_values", "opening")
    _string_list(stages["opening"].data, "third_party_values", "opening")
    _string_list(stages["opening"].data, "close_values", "opening")
    _string_list(stages["opening"].data, "stay_values", "opening")
    _string_list(stages["opening"].data, "forbidden_before_verification", "opening")
    _string_list(stages["third_party"].data, "intent_values", "third_party")
    _string_list(stages["third_party"].data, "close_values", "third_party")
    _string_list(stages["negotiation"].data, "intent_values", "negotiation")
    _string_list(stages["negotiation"].data, "confirm_values", "negotiation")
    _string_list(stages["negotiation"].data, "close_values", "negotiation")
    _string_list(stages["confirmation"].data, "intent_values", "confirmation")
    _string_list(stages["confirmation"].data, "revise_values", "confirmation")
    for stage_name, keys in {
        "opening": ("who_answered_variable", "unclear_count_variable", "confirmation_question", "unclear_instruction"),
        "third_party": ("intent_variable",),
        "identity": ("verified_field", "attempts_left_field"),
        "account": ("products_field", "products_variable", "product_id_field"),
        "negotiation": ("intent_variable",),
        "confirmation": (
            "product_number_field", "promise_product_id_field", "expected_count_variable",
            "intent_variable",
        ),
    }.items():
        for key in keys:
            raw = _required(stages[stage_name].data, key, stage_name)
            if key in {"confirmation_question", "unclear_instruction"}:
                _rule(raw, f"{stage_name}.{key}")
            else:
                _string(raw, f"{stage_name}.{key}")
    max_attempts = _required(stages["confirmation"].data, "max_attempts_per_product", "confirmation")
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
        raise SpecError("confirmation.max_attempts_per_product must be a positive integer")
    max_unclear = _required(stages["opening"].data, "max_unclear_asks", "opening")
    if not isinstance(max_unclear, int) or isinstance(max_unclear, bool) or max_unclear < 1:
        raise SpecError("opening.max_unclear_asks must be a positive integer")

    return PhoneAgentSpec(
        1, agent, stages["opening"], stages["third_party"], stages["identity"], questions,
        stages["account"], stages["negotiation"], stages["confirmation"],
        tuple(special_paths), outcomes, global_rules,
    )


def load_spec(path: str | Path) -> PhoneAgentSpec:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecError(f"could not load spec {path}: {exc}") from exc
    return parse_spec(value)


def spec_entry_variables(spec: PhoneAgentSpec) -> frozenset[str]:
    """Variables populated before or between steps that must not be reused as model inputs."""
    return frozenset(
        {
            spec.opening.data["who_answered_variable"],
            spec.opening.data["unclear_count_variable"],
            spec.third_party.data["intent_variable"],
            spec.account.data["products_variable"],
            spec.negotiation.data["intent_variable"],
            spec.confirmation.data["expected_count_variable"],
            spec.confirmation.data["intent_variable"],
            "identity_verified",
            "identity_attempts_left",
        }
    )
