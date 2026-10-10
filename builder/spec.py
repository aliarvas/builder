"""Typed, versioned input specification for multi-step phone agents."""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SpecError(ValueError):
    """Raised when a phone-agent spec is invalid."""


# Checks that generated code performs. A rule tagged with one of them (``enforced_by``)
# may be left out of a step prompt when the budget requires it (T-009); it stays in the spec
# and in the trace. Each check is available only when the spec carries its data
# (``enforcement_available`` in builder/workflow.py).
ENFORCEMENT_CHECKS = (
    "offer_dates", "business_days", "offer_amounts", "weekday_reading", "invalid_offer_limit",
    "identity_attempts", "closing_outcome",
)


@dataclass(frozen=True)
class Rule:
    text: str
    source: str
    enforced_by: str = ""


@dataclass(frozen=True)
class AgentSpec:
    name: str
    language: str
    introduction: Rule
    # Short fixed line spoken while the account is fetched (F-043); empty: the builder's
    # English default. Written in the call's language.
    wait_line: str = ""


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
    """``say`` is spoken word for word; ``ask`` (optional) is a question asked first."""

    id: str
    when: Rule
    say: Rule
    tool: str
    tool_args: dict[str, Any]
    outcome: str
    reason: str
    available_in: tuple[str, ...]
    then: str
    ask: Rule | None = None


@dataclass(frozen=True)
class Outcome:
    outcome: str
    reason: str
    when: Rule
    say: Rule
    on: tuple[str, ...]
    wins_over_promise: bool = False


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
    closing: StageSpec
    offer: StageSpec


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


def _flag(obj: dict[str, Any], key: str, path: str) -> bool:
    value = obj.get(key, False)
    if not isinstance(value, bool):
        raise SpecError(f"{path}.{key} must be true or false")
    return value


def _rule(value: Any, path: str) -> Rule:
    obj = _object(value, path)
    enforced_by = obj.get("enforced_by") or ""
    if enforced_by not in ("", *ENFORCEMENT_CHECKS):
        raise SpecError(f"{path}.enforced_by must be one of {list(ENFORCEMENT_CHECKS)} or absent")
    return Rule(
        _string(_required(obj, "text", path), f"{path}.text"),
        _string(_required(obj, "source", path), f"{path}.source", empty=True),
        enforced_by,
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
        _string(agent_data.get("wait_line", ""), "agent.wait_line", empty=True).strip(),
    )
    stages = {name: _stage(root, name) for name in (
        "opening", "third_party", "identity", "account", "negotiation", "confirmation", "closing",
        "offer",
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
            _rule(_required(obj, "say", f"outcomes[{index}]"), f"outcomes[{index}].say"),
            _string_list(obj, "on", f"outcomes[{index}]"),
            _flag(obj, "wins_over_promise", f"outcomes[{index}]"),
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
            _rule(obj["ask"], f"{path}.ask") if "ask" in obj else None,
        )
        allowed_steps = {"opening", "third_party", "identity", "negotiate", "confirm_record"}
        unknown_steps = set(special.available_in) - allowed_steps
        if not special.available_in or unknown_steps:
            raise SpecError(f"{path}.available_in contains unsupported steps: {sorted(unknown_steps)}")
        if special.then not in {"close", "return"}:
            raise SpecError(f"{path}.then must be 'close' or 'return'")
        if special.ask is not None and special.then != "close":
            raise SpecError(f"{path}.ask is supported only with then='close'")
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
    if OPENING_GREETING_VALUE in stages["opening"].data["who_answered_options"]:
        raise SpecError(
            f"opening.who_answered_options must not contain {OPENING_GREETING_VALUE!r}; "
            "the builder adds it for a bare greeting"
        )
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
        "identity": (
            "verified_field", "attempts_left_field", "answer_verified_field",
            "failed_answer_instruction", "exhausted_say",
        ),
        "account": ("products_field", "products_variable", "product_id_field"),
        "negotiation": ("intent_variable",),
        "confirmation": (
            "product_number_field", "promise_product_id_field", "expected_count_variable",
            "intent_variable", "promise_date_field", "promise_amount_field",
        ),
        "closing": ("outcome_field", "reason_field"),
    }.items():
        for key in keys:
            raw = _required(stages[stage_name].data, key, stage_name)
            if key in {"confirmation_question", "unclear_instruction", "failed_answer_instruction", "exhausted_say"}:
                _rule(raw, f"{stage_name}.{key}")
            else:
                _string(raw, f"{stage_name}.{key}")
    # Optional (F-044): product fields that name a product to the customer.
    for key in ("product_kind_field", "product_label_field"):
        if key in stages["account"].data:
            _string(stages["account"].data[key], f"account.{key}", empty=True)
    max_attempts = _required(stages["confirmation"].data, "max_attempts_per_product", "confirmation")
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
        raise SpecError("confirmation.max_attempts_per_product must be a positive integer")
    max_unclear = _required(stages["opening"].data, "max_unclear_asks", "opening")
    if not isinstance(max_unclear, int) or isinstance(max_unclear, bool) or max_unclear < 1:
        raise SpecError("opening.max_unclear_asks must be a positive integer")
    address_with = _string_list(stages["opening"].data, "address_with", "opening")
    if not address_with or any(not _IDENTIFIER.fullmatch(name) for name in address_with):
        raise SpecError("opening.address_with must list call variable names (letters, digits, _)")

    spec = PhoneAgentSpec(
        1, agent, stages["opening"], stages["third_party"], stages["identity"], questions,
        stages["account"], stages["negotiation"], stages["confirmation"],
        tuple(special_paths), outcomes, global_rules, stages["closing"], stages["offer"],
    )
    _validate_close_states(spec)
    _validate_offer(stages["offer"].data)
    return spec


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Who-answered value the builder adds for a bare greeting or a line check ("Hello?").
# It routes nowhere: the opening step stays and asks again, and it never counts as unclear.
OPENING_GREETING_VALUE = "greeting"

# Terminal call states the skeleton can produce. Brief-independent; the spec maps each
# to an outcome-table row through ``outcomes[].on``.
# Used only when the call ends before the closing chain ran (end-of-call close).
HANGUP_CLOSE_STATES = ("hangup", "hangup_unverified")
OPTIONAL_CLOSE_STATES = (
    "callback_failed", "account_failed", "turn_limit", "special_tool_failed", "offer_limit",
    *HANGUP_CLOSE_STATES,
)
# Fixed call-end state names of the skeleton (state names built from spec values,
# such as "opening:<value>", are not listed). The leakage test allows exactly these.
CLOSE_STATE_NAMES = (
    "opening_unclear", "callback_scheduled", "identity_failed",
    "promise_recorded", "promise_failed", "default", *OPTIONAL_CLOSE_STATES,
)


def required_close_states(spec: PhoneAgentSpec) -> tuple[str, ...]:
    """States that every spec must map to an outcome row (``default`` is the fallback)."""
    return (
        *("opening:" + value for value in spec.opening.data["close_values"]),
        "opening_unclear",
        *("third_party:" + value for value in spec.third_party.data["close_values"]),
        "callback_scheduled",
        "identity_failed",
        *("negotiation:" + value for value in spec.negotiation.data["close_values"]),
        "promise_recorded",
        "promise_failed",
        "default",
    )


def _validate_close_states(spec: PhoneAgentSpec) -> None:
    allowed = set(required_close_states(spec)) | set(OPTIONAL_CLOSE_STATES)
    seen: dict[str, int] = {}
    for index, outcome in enumerate(spec.outcomes):
        for state in outcome.on:
            if state not in allowed:
                raise SpecError(f"outcomes[{index}].on has unknown state {state!r}; allowed: {sorted(allowed)}")
            if state in seen:
                raise SpecError(f"outcomes[{index}].on repeats state {state!r} (also in outcomes[{seen[state]}])")
            seen[state] = index
    missing = [state for state in required_close_states(spec) if state not in seen]
    if missing:
        raise SpecError("outcomes[].on does not map these call-end states: " + ", ".join(missing))


# Offer rule vocabulary (brief-independent). See docs in _validate_offer.
OFFER_UNITS = ("business", "calendar")
OFFER_ADJUST = ("previous", "next", "keep")
OFFER_NEXT_WEEKDAY = ("following_week", "upcoming", "ask")
OFFER_WHEN_KEYS = ("field", "min", "max", "equals", "in")


def _number(value: Any, path: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpecError(f"{path} must be a number")
    if minimum is not None and value < minimum:
        raise SpecError(f"{path} must be at least {minimum}")
    return float(value)


def _int(value: Any, path: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SpecError(f"{path} must be an integer of at least {minimum}")
    return value


def _validate_when(value: Any, path: str) -> None:
    for index, item in enumerate(_list(value, path)):
        where = f"{path}[{index}]"
        obj = _object(item, where)
        unknown = set(obj) - set(OFFER_WHEN_KEYS)
        if unknown:
            raise SpecError(f"{where} has unknown keys: {sorted(unknown)}")
        _string(_required(obj, "field", where), f"{where}.field")
        if not set(obj) & {"min", "max", "equals", "in"}:
            raise SpecError(f"{where} needs one of min, max, equals, in")
        for key in ("min", "max"):
            if key in obj:
                _number(obj[key], f"{where}.{key}")
        if "in" in obj:
            _list(obj["in"], f"{where}.in")


def _validate_day_rule(obj: dict[str, Any], path: str) -> None:
    _int(_required(obj, "days", path), f"{path}.days", minimum=0)
    if _required(obj, "unit", path) not in OFFER_UNITS:
        raise SpecError(f"{path}.unit must be one of {list(OFFER_UNITS)}")


def _validate_offer(data: dict[str, Any]) -> None:
    """Validate the offer rule format.

    - today_variable: call variable holding the current date-time (ISO); system date if unset.
    - non_business_weekdays: ISO weekday numbers (1 = Monday ... 7 = Sunday).
    - holidays: ISO dates that are not business days.
    - promise_date_must_be_business_day: true or false.
    - earliest: {days, unit}; the first allowed date counted from today.
    - latest: ordered rules {when?, days, unit}; the first rule whose ``when`` matches the
      product decides the latest allowed date. No match: no latest date.
    - latest_on_non_business_day: previous | next | keep (for calendar-day rules).
    - next_weekday: following_week | upcoming | ask; optional, defaults to ask.
    - min_amount / max_amount: ordered rules {when?, field | value, share?}; first match wins.
    - max_rejected_offers: distinct customer offers that fail deterministic date or amount
      rules before that product is exhausted. It is not the number of persuasion attempts
      after a flat refusal. The value is at least 2 so the agent can state one counter-offer
      and the customer can reject it before the product is exhausted.
    - max_rejected_offers_by_product: optional ordered rules {when?, value}; first match
      overrides max_rejected_offers for that product, with the same invalid-offer meaning.
    ``when`` is a list of conditions on product fields: {field, min?, max?, equals?, in?}; all must hold.
    """
    _string(_required(data, "today_variable", "offer"), "offer.today_variable")
    for index, day in enumerate(_list(_required(data, "non_business_weekdays", "offer"), "offer.non_business_weekdays")):
        if _int(day, f"offer.non_business_weekdays[{index}]", minimum=1) > 7:
            raise SpecError(f"offer.non_business_weekdays[{index}] must be 1..7")
    for index, day in enumerate(_list(_required(data, "holidays", "offer"), "offer.holidays")):
        try:
            datetime.date.fromisoformat(_string(day, f"offer.holidays[{index}]"))
        except ValueError as exc:
            raise SpecError(f"offer.holidays[{index}] must be an ISO date (YYYY-MM-DD)") from exc
    if not isinstance(_required(data, "promise_date_must_be_business_day", "offer"), bool):
        raise SpecError("offer.promise_date_must_be_business_day must be true or false")
    _validate_day_rule(_object(_required(data, "earliest", "offer"), "offer.earliest"), "offer.earliest")
    for index, item in enumerate(_list(_required(data, "latest", "offer"), "offer.latest")):
        where = f"offer.latest[{index}]"
        obj = _object(item, where)
        _validate_day_rule(obj, where)
        _validate_when(obj.get("when", []), f"{where}.when")
    if _required(data, "latest_on_non_business_day", "offer") not in OFFER_ADJUST:
        raise SpecError(f"offer.latest_on_non_business_day must be one of {list(OFFER_ADJUST)}")
    next_weekday = data.setdefault("next_weekday", "ask")
    if next_weekday not in OFFER_NEXT_WEEKDAY:
        raise SpecError(f"offer.next_weekday must be one of {list(OFFER_NEXT_WEEKDAY)}")
    for key in ("min_amount", "max_amount"):
        for index, item in enumerate(_list(_required(data, key, "offer"), f"offer.{key}")):
            where = f"offer.{key}[{index}]"
            obj = _object(item, where)
            if ("field" in obj) == ("value" in obj):
                raise SpecError(f"{where} needs exactly one of field or value")
            if "field" in obj:
                _string(obj["field"], f"{where}.field")
            else:
                _number(obj["value"], f"{where}.value", minimum=0)
            if "share" in obj:
                _number(obj["share"], f"{where}.share", minimum=0)
            _validate_when(obj.get("when", []), f"{where}.when")
    _int(_required(data, "max_rejected_offers", "offer"), "offer.max_rejected_offers", minimum=2)
    limits = data.setdefault("max_rejected_offers_by_product", [])
    for index, item in enumerate(_list(limits, "offer.max_rejected_offers_by_product")):
        where = f"offer.max_rejected_offers_by_product[{index}]"
        obj = _object(item, where)
        unknown = set(obj) - {"when", "value"}
        if unknown:
            raise SpecError(f"{where} has unknown keys: {sorted(unknown)}")
        _int(_required(obj, "value", where), f"{where}.value", minimum=2)
        _validate_when(obj.get("when", []), f"{where}.when")


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
