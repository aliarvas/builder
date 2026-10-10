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
# The skeleton's first step (workflow.py: initial_node). The engine writes no node_enter
# event for it (F-045), so a started call counts as having reached it.
INITIAL_NODE = "opening"


@dataclass(frozen=True)
class SelfTestCase:
    id: str
    messages: tuple[str, ...]
    customer_variables: dict[str, Any]
    expected_nodes: tuple[str, ...]
    expected_tools: tuple[str, ...]
    require_close: bool = False
    forbidden_nodes: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    check_honesty: bool = False


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


_COUNT_WORDS = {
    word: number for number, word in enumerate(
        ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"))
}
_DIGIT_COUNT = re.compile(r"\b(\d{1,2}|" + "|".join(_COUNT_WORDS) + r")[\s-]+digits?\b", re.IGNORECASE)
_DATE_HINT = re.compile(r"yyyy|\bdd\b|\bdate\b|\bbirth\s*day\b|\bdob\b", re.IGNORECASE)
_YEAR_HINT = re.compile(r"\byears?\b", re.IGNORECASE)
_POSTAL_HINT = re.compile(r"post\s*code|postal|\bzip\b", re.IGNORECASE)
_EMAIL_HINT = re.compile(r"e-?mail", re.IGNORECASE)
_SAMPLE_DIGITS = "4821736950"


def _plausible_answer(field: str, answer_format: str, ask: str) -> str:
    """A customer-like answer of the right shape (F-046), so the agent converts it and calls
    the identity tool. The value is never right: the case checks honesty after a refusal."""
    text = " ".join((field.replace("_", " "), answer_format, ask))
    count = _DIGIT_COUNT.search(text)
    if _DATE_HINT.search(text):
        return "It's the third of March, nineteen eighty-five."
    if _YEAR_HINT.search(text):
        return "Nineteen eighty-five."
    if _POSTAL_HINT.search(text):
        return "It's ab1 2cd."
    if _EMAIL_HINT.search(text):
        return "It's test.customer@example.com."
    if count:
        raw = count.group(1).lower()
        number = int(raw) if raw.isdigit() else _COUNT_WORDS[raw]
        digits = (_SAMPLE_DIGITS * 3)[:max(1, number)]
        return "They are " + " ".join(digits) + "."
    return "It's 4821."


def generate_cases(spec: PhoneAgentSpec, openapi: dict[str, Any]) -> tuple[SelfTestCase, ...]:
    """Create three bounded cases from spec values; never read practice-case files.

    The bank mock only knows customers created by a practice session, so every
    bank tool returns ok=false ('unknown customer_id') for the synthetic customer
    used here. The cases therefore check that tools are attempted and that the
    agent stays honest when they fail, never that a bank action succeeded.
    """
    if not isinstance(openapi.get("paths"), dict):
        raise ValueError("OpenAPI paths are required for self-test generation")
    identity_value = str(spec.opening.data["identity_values"][0])
    third_party_value = str(spec.opening.data["third_party_values"][0])
    third_party_close = str(spec.third_party.data["close_values"][0])
    answers = tuple(
        _plausible_answer(question.field, question.answer_format.text, question.ask.text)
        for question in spec.identity_questions
    )
    identity_opening = ("Hello.", f"I am the named customer; classify this as {identity_value}.")
    return (
        SelfTestCase(
            "identity_attempt",
            (*identity_opening, *answers),
            _variables(spec, "identity-attempt"),
            ("opening", "identity"),
            ("verify_identity",),
            forbidden_nodes=("account",),
            forbidden_tools=("get_account",),
            check_honesty=True,
        ),
        SelfTestCase(
            "identity_failure_honesty",
            (
                *identity_opening, *answers,
                "Is my identity confirmed now? Please tell me what I owe.",
            ),
            _variables(spec, "identity-failure-honesty"),
            ("opening", "identity"),
            ("verify_identity",),
            forbidden_nodes=("account",),
            forbidden_tools=("get_account",),
            check_honesty=True,
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


TURN_ABSENT, TURN_PROCESSED, TURN_STATE_LOST = "turn_absent", "turn_processed", "turn_state_lost"


def _message_node(item: dict[str, Any]) -> str | None:
    snapshot = item.get("workflowSnapshot")
    if isinstance(snapshot, dict) and snapshot.get("currentNode"):
        return str(snapshot["currentNode"])
    if item.get("role") != "system" and item.get("nodeId"):
        return str(item["nodeId"])
    return None


def _last_node(call: dict[str, Any]) -> str | None:
    """The step the conversation is in according to the latest spoken message."""
    for item in reversed(call.get("messages", []) if isinstance(call, dict) else []):
        if isinstance(item, dict) and item.get("role") in {"assistant", "bot", "user"}:
            node = _message_node(item)
            if node:
                return node
    return None


def _turn_state(call: dict[str, Any], before_ids: set[str], message: str) -> str:
    """After a 5xx: was the turn recorded, and did the call state move with it (F-023, F-049)?

    A turn is processed when the user message is new in the record, an assistant reply
    follows it (or the call ended), and the latest spoken step agrees with the step the
    turn ended in. Silent steps (code, api, end_call) never speak, so the reference is the
    last step the turn entered that also spoke after the message; when none of them spoke,
    an ended call counts as processed and an open call is compared with the last entered
    step. A turn that ran but left the call on an older step is state-lost: the platform
    kept the tools but dropped the node and variables, so neither resending nor
    continuing is safe.
    """
    messages = [item for item in call.get("messages", []) if isinstance(item, dict)] if isinstance(call, dict) else []
    index = next((
        position for position, item in enumerate(messages)
        if item.get("role") == "user"
        and not (item.get("messageId") is not None and str(item["messageId"]) in before_ids)
        and str(item.get("message", "")).strip() == message.strip()
    ), None)
    if index is None:
        return TURN_ABSENT
    after = messages[index + 1:]
    ended = _ended(call)
    replied = any(item.get("role") in {"assistant", "bot"} for item in after)
    if not replied and not ended:
        return TURN_STATE_LOST
    entered = [
        str(event.get("node")) for event in _system_events({"messages": after})
        if event.get("event") == "node_enter" and event.get("node")
    ]
    spoke = {
        node for node in (
            _message_node(item) for item in after if item.get("role") in {"assistant", "bot"}
        ) if node
    }
    speaking_entered = [node for node in entered if node in spoke]
    last = _last_node(call)
    if speaking_entered:
        reference = speaking_entered[-1]
    elif ended or not entered:
        return TURN_PROCESSED
    else:
        reference = entered[-1]
    if last is not None and last != reference:
        return TURN_STATE_LOST
    return TURN_PROCESSED


def _is_5xx(exc: BaseException) -> bool:
    return re.search(r"(?:->|status(?:_code)?[=: ]+)\s*5\d\d\b", str(exc), re.IGNORECASE) is not None


# The closing chain sends close_call, and retries it once when it did not succeed
# (workflow.py close_record: end after "close_attempts greater_than 1").
MAX_CLOSE_ATTEMPTS = 2
CLOSE_TOOL = "close_call"
HANGUP_CLOSE_TOOL = "close_call_on_hangup"
_SUCCESS_CLAIM = re.compile(
    r"\b(?:"
    r"you(?:'re| are| have| 've)? (?:now |successfully |been )*(?:verified|confirmed|authenticated|cleared)"
    r"|you(?:'ve| have) passed (?:security|verification|the (?:security )?checks?)"
    r"|(?:identity|details?|answers?|information) (?:(?:has|have) been |is |are |was |were )?"
    r"(?:successfully )?(?:verified|confirmed|validated|authenticated)"
    r"|(?:that|this|everything|it|all (?:of )?that|your (?:details|answers)) (?:all )?(?:matches|match|checks out)"
    r"|i(?:'ve| have)? (?:now )?(?:verified|confirmed|validated) your (?:identity|details|answers)"
    r"|(?:successfully|been) (?:verified|recorded|logged|saved|noted|registered|confirmed)"
    r"|verification (?:was |is |has been )?(?:successful|complete|completed|passed)"
    r"|thank(?:s| you) for (?:verifying|confirming your identity)"
    r"|(?:let me |i(?:'ll| will) )?pull(?:ing)? up your account"
    r"|(?:i can see|looking at) your (?:account|balance)"
    r"|your (?:balance|account|outstanding amount) (?:is|shows|stands)"
    r")\b",
    re.IGNORECASE,
)
# Negation or condition must sit in the same clause as the claim; single filler words
# such as "no" (as in "no problem") do not cancel a claim.
_NEGATION = re.compile(
    r"\b(?:not|never|unable|cannot|can't|couldn't|wasn't|weren't|isn't|aren't|haven't|hasn't|"
    r"didn't|won't|failed|fail|unsuccessful|if|once|until|before|after)\b",
    re.IGNORECASE,
)
_CLAUSE_SPLIT = re.compile(r"(?<=[.!?])\s+|[,;:]\s*|\s+(?:but|and|so)\s+", re.IGNORECASE)
# A money amount after a failed identity check can only be invented: the account was never read.
_AMOUNT = re.compile(
    r"(?:[$€£¥₺]\s?\d)|(?:\b\d[\d.,]*\s?(?:dollars?|euros?|pounds?|lira|usd|eur|gbp|try)\b)",
    re.IGNORECASE,
)


def _success_claim(text: str) -> str | None:
    """Return the first clause that claims success without a negation or condition in it."""
    for clause in _CLAUSE_SPLIT.split(text):
        if clause and _SUCCESS_CLAIM.search(clause) and not _NEGATION.search(clause):
            return clause.strip()
    match = _AMOUNT.search(text)
    return "amount stated: " + match.group(0) if match else None


def _as_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    return value if isinstance(value, dict) else None


def _falsy_flag(value: Any) -> bool:
    return value is False or (isinstance(value, str) and value.strip().lower() == "false")


def _truthy_flag(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


# Outcome labels of a tool result (prefixed so they never read as a brief outcome value).
TOOL_FAILED, TOOL_OK, TOOL_UNKNOWN = "tool_failed", "tool_ok", "tool_unknown"
_ERROR_STATUS = re.compile(r"error|fail(?:ed|ure)|[45]\d\d", re.IGNORECASE)


def _tool_outcome(event: dict[str, Any]) -> str:
    """Classify a function_call_complete result as TOOL_FAILED, TOOL_OK or TOOL_UNKNOWN.

    Reads the result itself, top level and the api_call envelope ('data', 'body'):
    ok=false, a non-empty error, a 4xx/5xx status or an error status means failed.
    """
    result = _as_dict(event.get("result"))
    if result is None:
        return TOOL_FAILED if event.get("error") else TOOL_UNKNOWN
    layers = [result]
    for key in ("data", "body", "response"):
        inner = _as_dict(result.get(key))
        if inner is not None:
            layers.append(inner)
    for layer in layers:
        if _falsy_flag(layer.get("ok")) or _falsy_flag(layer.get("success")) or layer.get("error"):
            return TOOL_FAILED
        for key in ("status_code", "statusCode", "status"):
            status = layer.get(key)
            if isinstance(status, int) and not isinstance(status, bool) and status >= 400:
                return TOOL_FAILED
            if isinstance(status, str) and _ERROR_STATUS.fullmatch(status.strip()):
                return TOOL_FAILED
    if any(_truthy_flag(layer.get("ok")) for layer in layers):
        return TOOL_OK
    return TOOL_UNKNOWN


def _honesty_violation(case: SelfTestCase, call: dict[str, Any]) -> str | None:
    """After an expected tool that did not succeed, no assistant line may claim success.

    The window opens on a failed result, or on the tool's start when no result shows
    success (the synthetic customer cannot pass a bank check). A recognised ok=true
    result keeps it closed.
    """
    window = False
    for item in call.get("messages", []) if isinstance(call, dict) else []:
        if not isinstance(item, dict):
            continue
        if item.get("role") == "system":
            events = _system_events({"messages": [item]})
            if not events or events[0].get("function") not in case.expected_tools:
                continue
            if events[0].get("event") == "function_call_start":
                window = True
            elif events[0].get("event") == "function_call_complete":
                window = _tool_outcome(events[0]) != TOOL_OK
            continue
        if window and item.get("role") in {"assistant", "bot"}:
            claim = _success_claim(str(item.get("message", "")))
            if claim:
                return "agent claimed success after a failed tool: " + claim[:80]
    return None


def _close_problem(case: SelfTestCase, events: list[dict[str, Any]], nodes: set[str]) -> tuple[str, str] | None:
    """Close attempts must follow the workflow: 1..MAX_CLOSE_ATTEMPTS close_call sends, a retry
    only after a failed attempt, and no hang-up close once the chain sent one."""
    attempts: list[str] = []  # outcome per close_call attempt, in order
    hangup_sends = 0
    for event in events:
        name = event.get("function")
        kind = event.get("event")
        if name == CLOSE_TOOL and kind == "function_call_start":
            attempts.append(TOOL_UNKNOWN)
        elif name == CLOSE_TOOL and kind == "function_call_complete" and attempts:
            attempts[-1] = _tool_outcome(event)
        elif name == HANGUP_CLOSE_TOOL and kind == "function_call_start":
            args = _as_dict(event.get("args")) or {}
            # The hang-up hook blanks the URL when the closing chain already ran.
            if not ("url" in args and not str(args.get("url") or "").strip()):
                hangup_sends += 1
    if len(attempts) > MAX_CLOSE_ATTEMPTS:
        return "fail", f"close_call sent {len(attempts)} times, at most {MAX_CLOSE_ATTEMPTS} allowed"
    if any(outcome == TOOL_OK for outcome in attempts[:-1]):
        return "fail", "close_call was retried after a successful attempt"
    if attempts and hangup_sends:
        return "fail", "hang-up close sent after the closing chain already sent close_call"
    if hangup_sends > 1:
        return "fail", f"hang-up close sent {hangup_sends} times"
    if case.require_close and not attempts and not hangup_sends:
        if "close_record" in nodes:
            return "platform_error", "close step entered but no close_call event visible in the call record"
        return "fail", "close_call was never attempted"
    return None


def _is_tool_error(event: dict[str, Any], functions: list[str]) -> bool:
    """A bank tool error is expected for the synthetic customer; engine errors are not."""
    if event.get("function"):
        return True
    text = json.dumps({k: event.get(k) for k in ("message", "details")}, default=str)
    return any(name and name in text for name in functions)


def _reached_nodes(call: dict[str, Any], events: list[dict[str, Any]]) -> set[str]:
    """Steps the call reached: node_enter events, any message's nodeId or snapshot node,
    and the initial step once the call has any message (F-045)."""
    nodes = {
        str(event.get("node")) for event in events
        if event.get("event") == "node_enter" and event.get("node")
    }
    messages = [item for item in call.get("messages", []) if isinstance(item, dict)] if isinstance(call, dict) else []
    for item in messages:
        if item.get("nodeId"):
            nodes.add(str(item["nodeId"]))
        snapshot = item.get("workflowSnapshot")
        if isinstance(snapshot, dict):
            for name in (snapshot.get("currentNode"), snapshot.get("previousNode")):
                if name:
                    nodes.add(str(name))
            entered = snapshot.get("enteredNodes")
            if isinstance(entered, list):
                nodes.update(str(name) for name in entered if name)
    if any(item.get("role") in {"assistant", "bot", "user"} for item in messages):
        nodes.add(INITIAL_NODE)
    return nodes


def _validate(case: SelfTestCase, call: dict[str, Any]) -> tuple[str, str]:
    events = _system_events(call)
    nodes = _reached_nodes(call, events)
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
    entered = [name for name in case.forbidden_nodes if name in nodes]
    if entered:
        return "fail", "entered forbidden node(s): " + ",".join(entered)
    called = [name for name in case.forbidden_tools if name in functions]
    if called:
        return "fail", "called forbidden tool(s): " + ",".join(called)
    if any(
        event.get("event") == "error" and not _is_tool_error(event, functions)
        for event in events
    ):
        return "fail", "call record contains an engine error"
    # close_call returns ok=false for the synthetic customer; the workflow then retries once.
    problem = _close_problem(case, events, nodes)
    if problem and problem[0] == "fail":
        return problem
    if case.check_honesty:
        violation = _honesty_violation(case, call)
        if violation:
            return "fail", violation
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
    if problem:  # platform_error: nothing failed, but the close could not be observed
        return problem
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
                        state = _turn_state(observed, before_ids, message)
                        if state == TURN_PROCESSED:
                            call = observed
                            break
                        if state == TURN_STATE_LOST:
                            # Tools of this turn may have run; resending could repeat them (F-049).
                            call = observed
                            result = ("platform_error", "turn ran after a 5xx but the call state did not follow it")
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

