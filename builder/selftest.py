"""Short post-publish chat checks generated from a phone-agent spec."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from .spec import PhoneAgentSpec


DEFAULT_BUDGET_SECONDS = 6 * 60
MAX_RETRIES_PER_TURN = 2
MAX_NODE_TURNS = 6


@dataclass(frozen=True)
class SelfTestCase:
    id: str
    messages: tuple[str, ...]
    customer_variables: dict[str, Any]
    expected_nodes: tuple[str, ...]
    expected_tools: tuple[str, ...]
    require_close: bool = False


@dataclass(frozen=True)
class SelfTestResult:
    case_id: str
    result: str
    reason: str
    call_id: str
    seconds: float


def _variables(spec: PhoneAgentSpec, case_id: str) -> dict[str, Any]:
    values: dict[str, Any] = {
        "customer_id": "self-test-" + case_id,
        "first_name": "Test",
        "last_name": "Customer",
        "title": "Mx",
        "now": "2030-01-07T12:00:00Z",
    }
    for name in spec.opening.data["address_with"]:
        values.setdefault(name, "Test")
    return values


def generate_cases(spec: PhoneAgentSpec, openapi: dict[str, Any]) -> tuple[SelfTestCase, ...]:
    """Create three bounded cases from spec values; never read practice-case files."""
    if not isinstance(openapi.get("paths"), dict):
        raise ValueError("OpenAPI paths are required for self-test generation")
    identity_value = str(spec.opening.data["identity_values"][0])
    third_party_value = str(spec.opening.data["third_party_values"][0])
    third_party_close = str(spec.third_party.data["close_values"][0])
    answers = tuple(
        f"My answer to '{question.ask.text}' is self-test-answer-{index}."
        for index, question in enumerate(spec.identity_questions, start=1)
    )
    wrong_answers = tuple(
        f"My answer to '{spec.identity_questions[0].ask.text}' is intentionally incorrect {index}."
        for index in range(1, 5)
    )
    return (
        SelfTestCase(
            "identity_to_account",
            ("Hello.", f"I am the named customer; classify this as {identity_value}.", *answers),
            _variables(spec, "identity-to-account"),
            ("opening", "identity", "account"),
            ("verify_identity", "get_account"),
        ),
        SelfTestCase(
            "identity_exhausted",
            ("Hello.", f"I am the named customer; classify this as {identity_value}.", *wrong_answers),
            _variables(spec, "identity-exhausted"),
            ("opening", "identity", "end_call"),
            ("verify_identity",),
            require_close=True,
        ),
        SelfTestCase(
            "third_party_close",
            (
                "Hello.",
                f"I am someone else; classify this as {third_party_value}.",
                f"My answer is {third_party_close}.",
            ),
            _variables(spec, "third-party-close"),
            ("opening", "third_party", "end_call"),
            (),
            require_close=True,
        ),
    )


def _system_events(call: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in call.get("messages", []) if isinstance(call, dict) else []:
        if not isinstance(item, dict) or item.get("role") != "system":
            continue
        value = item.get("message")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                continue
        if isinstance(value, dict):
            events.append(value)
    return events


def _ended(call: dict[str, Any]) -> bool:
    if call.get("endedReason"):
        return True
    for event in _system_events(call):
        if event.get("event") == "node_enter" and event.get("node") == "end_call":
            return True
        if event.get("event") == "function_call_start" and event.get("function") == "end_call":
            return True
    return False


def _message_ids(call: dict[str, Any]) -> set[str]:
    return {
        str(item.get("messageId"))
        for item in call.get("messages", [])
        if isinstance(item, dict) and item.get("messageId") is not None
    }


def _turn_was_processed(call: dict[str, Any], before_ids: set[str], message: str) -> bool:
    for item in call.get("messages", []) if isinstance(call, dict) else []:
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        identifier = item.get("messageId")
        if identifier is not None and str(identifier) in before_ids:
            continue
        if str(item.get("message", "")).strip() == message.strip():
            return True
    return False


def _is_5xx(exc: BaseException) -> bool:
    return re.search(r"(?:->|status(?:_code)?[=: ]+)\s*5\d\d\b", str(exc), re.IGNORECASE) is not None


def _validate(case: SelfTestCase, call: dict[str, Any]) -> tuple[str, str]:
    events = _system_events(call)
    nodes = {
        str(event.get("node")) for event in events
        if event.get("event") == "node_enter" and event.get("node")
    }
    functions = [
        str(event.get("function")) for event in events
        if event.get("event") == "function_call_start" and event.get("function")
    ]
    missing_nodes = [name for name in case.expected_nodes if name not in nodes]
    if missing_nodes:
        return "fail", "missing node(s): " + ",".join(missing_nodes)
    missing_tools = [name for name in case.expected_tools if name not in functions]
    if missing_tools:
        return "fail", "missing tool(s): " + ",".join(missing_tools)
    if any(event.get("event") == "error" for event in events):
        return "fail", "call record contains a tool or engine error"
    close_count = sum(name in {"close_call", "close_call_on_hangup"} for name in functions)
    if case.require_close and close_count != 1:
        return "fail", f"close tool count was {close_count}, expected 1"
    for item in call.get("messages", []) if isinstance(call, dict) else []:
        if not isinstance(item, dict):
            continue
        snapshot = item.get("workflowSnapshot")
        if isinstance(snapshot, dict):
            try:
                if int(snapshot.get("nodeTurnCount") or 0) > MAX_NODE_TURNS:
                    return "fail", "a node exceeded the turn limit"
            except (TypeError, ValueError):
                pass
    return "pass", "all expected nodes and tools observed"


def _run_case(
    client: Any,
    workflow_id: str,
    case: SelfTestCase,
    deadline: float,
    clock: Callable[[], float],
) -> SelfTestResult:
    started = clock()
    call_id = ""
    call: dict[str, Any] = {}
    result: tuple[str, str] | None = None

    def remaining_timeout() -> float:
        return max(0.1, min(120.0, deadline - clock()))

    try:
        for message in case.messages:
            if clock() >= deadline:
                result = ("platform_error", "self-test budget exhausted")
                break
            before_ids = _message_ids(call)
            for retry in range(MAX_RETRIES_PER_TURN + 1):
                try:
                    response = client.chat_message(
                        workflow_id, message, case.customer_variables, call_id or None,
                        timeout_seconds=remaining_timeout(),
                    )
                    if isinstance(response, dict) and response.get("callId"):
                        call_id = str(response["callId"])
                    if not call_id:
                        result = ("platform_error", "chat response had no callId")
                        break
                    call = client.get_call(call_id, timeout_seconds=remaining_timeout())
                    break
                except Exception as exc:
                    if not _is_5xx(exc):
                        result = ("platform_error", "chat request failed: " + str(exc)[:120])
                        break
                    # F-023: a gateway error can arrive after Freya processed the turn.
                    if call_id:
                        try:
                            observed = client.get_call(call_id, timeout_seconds=remaining_timeout())
                        except Exception:
                            observed = {}
                        if _turn_was_processed(observed, before_ids, message):
                            call = observed
                            break
                    if retry >= MAX_RETRIES_PER_TURN:
                        result = ("platform_error", "chat turn still returned 5xx after 2 retries")
                        break
                    if clock() >= deadline:
                        result = ("platform_error", "self-test budget exhausted")
                        break
            if result is not None or _ended(call):
                break
        if result is None:
            if call_id:
                try:
                    call = client.get_call(call_id, timeout_seconds=remaining_timeout())
                except Exception as exc:
                    result = ("platform_error", "call record unavailable: " + str(exc)[:120])
            if result is None:
                result = _validate(case, call)
    finally:
        # End only unfinished calls, after validation, so cleanup cannot mask a missing close.
        if call_id and not _ended(call):
            try:
                if clock() < deadline:
                    client.end_chat(call_id, timeout_seconds=remaining_timeout())
            except Exception:
                pass
    return SelfTestResult(case.id, result[0], result[1], call_id or "none", clock() - started)


def run_self_tests(
    client: Any,
    workflow_id: str,
    spec: PhoneAgentSpec,
    openapi: dict[str, Any],
    *,
    budget_seconds: float = DEFAULT_BUDGET_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[SelfTestResult, ...]:
    """Run generated cases sequentially within one hard wall-clock budget."""
    deadline = clock() + max(0.0, budget_seconds)
    results: list[SelfTestResult] = []
    for case in generate_cases(spec, openapi):
        if clock() >= deadline:
            results.append(SelfTestResult(case.id, "platform_error", "self-test budget exhausted", "none", 0.0))
            continue
        started = clock()
        try:
            results.append(_run_case(client, workflow_id, case, deadline, clock))
        except Exception as exc:
            results.append(SelfTestResult(
                case.id, "platform_error", "unexpected self-test error: " + str(exc)[:120],
                "none", clock() - started,
            ))
    return tuple(results)

