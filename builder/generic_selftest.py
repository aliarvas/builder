"""T-047: self-test and repair loop for the generic mode (builder/generic.py).

The case folder's own test material (test customers, example conversations) becomes test
scenarios with one model call. Each scenario is played against the saved agent through Freya
chat by a model acting as the caller; one model call judges each call against the scenario and
the documents. Failures go back to the workflow repair, the repaired workflow is saved, and only
the failed scenarios run again. The version with the most passes is kept (and is the live one).

The test material is used only here, at build time; nothing of it goes into the workflow (the
repair line says so). Every scenario, call id, verdict and reason is written to the trace.
"""

from __future__ import annotations

import inspect
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .prompts import PromptDefinition
from .selftest import _ended, _is_5xx, _system_events

MAX_SCENARIOS = 8
MAX_CALLER_TURNS = 14
# Chat calls may run in parallel (simulations may not): every scenario of a round at once.
MAX_PARALLEL = 8
REPAIR_ROUNDS = 2
# Time kept free for one repair (model) plus one save (Freya) before another round starts.
REPAIR_RESERVE_SECONDS = 5 * 60
TOOL_RESULT_CHARS = 600
# The longest document text one self-test call carries (about 10k tokens).
DOCUMENT_CHAR_LIMIT = 40_000
CHAT_TIMEOUT_SECONDS = 120

# The self-test prompts (kept here while generic.py adds its own to prompts.py). One shared system text, so the
# cached documents prefix is reused by the scenario, player and judge calls; each task follows it.
SELFTEST_SYSTEM = PromptDefinition(
    "SELFTEST_SYSTEM", "The shared system text of every self-test call, so the cached documents are reused "
    "(T-047).", "builder model", "builder/generic_selftest.py — every self-test model call",
    "You test a phone agent that a builder made from the documents in this request. The documents are the "
    "only source of rules and values. Follow the task after the documents exactly and reply with the JSON "
    "object it asks for, nothing else.",
)
SELFTEST_SCENARIOS_TASK = PromptDefinition(
    "SELFTEST_SCENARIOS_TASK", "Turns the folder's test customers and example conversations into test "
    "scenarios (T-047).", "builder model", "builder/generic_selftest.py — derive_scenarios",
    "Task: write at most {max} test scenarios for the phone agent. Cover every example conversation in the "
    "documents, then every kind of test customer and service answer the test material lists (errors, empty "
    "results and edge cases included), then the documents' rules most likely to be broken. Each scenario is "
    "an object with:\n"
    "- id: short snake_case name;\n"
    "- persona: who calls and how they speak (style, mood, what they know);\n"
    "- goal: what the caller wants, in order, including changes of mind;\n"
    "- language: the language of the call as the documents give it;\n"
    "- variables: an object with every call variable the documents say each call receives, filled for this "
    "test customer; a date-time variable gets a value that makes the scenario's date rules testable, in the "
    "format the documents give;\n"
    "- opening: the caller's first words;\n"
    "- expected: list of what the agent must do or say, with the values the test material gives;\n"
    "- expected_tools: list of the service paths the agent must call;\n"
    "- forbidden: list of what the agent must not do;\n"
    "- max_turns: the caller's turns needed, at most {turns}.\n"
    "Reply {\"scenarios\": [ ... ]}.",
    ("{max}", "{turns}"),
)
SELFTEST_CUSTOMER_TASK = PromptDefinition(
    "SELFTEST_CUSTOMER_TASK", "Plays the caller of one scenario, one turn at a time (T-047).", "builder model",
    "builder/generic_selftest.py — run_scenario",
    "Task: you are the caller in this scenario:\n{scenario}\n\nThe call so far:\n{transcript}\n\nWrite the "
    "caller's next turn: one or two short spoken sentences in the scenario's language, in the persona's style, "
    "moving towards the goal. Answer what the agent asked with the persona's data. Never mention a test, a "
    "scenario or a workflow. When the goal is done, the agent has ended the call, or the call is stuck in a "
    "loop, say goodbye and set hang_up to true. Reply {\"message\": \"...\", \"hang_up\": false}.",
    ("{scenario}", "{transcript}"),
)
SELFTEST_JUDGE_TASK = PromptDefinition(
    "SELFTEST_JUDGE_TASK", "Judges one self-test call against its scenario and the documents (T-047).",
    "builder model", "builder/generic_selftest.py — judge",
    "Task: judge this test call.\nScenario:\n{scenario}\n\nThe call (caller, agent, and each tool call with "
    "its result):\n{transcript}\n\nFail it when: an expected step, value or tool call is missing; a forbidden "
    "thing happened; the agent said a value that is in no tool result and no document, or said an action was "
    "done without a successful tool result; it broke a rule of the documents (language, what it may say, "
    "transfers, dates decided from the call variables); or it got stuck, repeated itself, or ended the call "
    "wrongly. Do not fail for wording or politeness alone. Reply {\"pass\": true or false, \"reasons\": "
    "[\"...\"], \"fix\": \"what in the workflow should change, in one or two sentences, with no value of this "
    "test customer\"}.",
    ("{scenario}", "{transcript}"),
)
SELFTEST_REPAIR_LINE = PromptDefinition(
    "SELFTEST_REPAIR_LINE", "One failed self-test scenario, as a problem line for the workflow repair (T-047).",
    "builder model", "builder/generic_selftest.py — problem_lines (sent through generic.repair)",
    "Self-test scenario {id} failed ({goal}): {reasons}. Suggested fix: {fix}. Fix the workflow so every "
    "caller of this kind is handled; never copy a test customer's value into it.",
    ("{id}", "{goal}", "{reasons}", "{fix}"),
)


PASS, FAIL, ERROR = "pass", "fail", "error"


@dataclass
class Scenario:
    id: str
    persona: str
    goal: str
    language: str
    variables: dict[str, Any]
    opening: str
    expected: list[str]
    expected_tools: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    max_turns: int = MAX_CALLER_TURNS

    def brief(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=1)


@dataclass
class ScenarioResult:
    id: str
    verdict: str                    # pass | fail | error (platform or model problem, not the agent's)
    reasons: list[str]
    fix: str = ""
    call_id: str = ""
    turns: int = 0
    seconds: float = 0.0
    transcript: str = ""


# ---------------------------------------------------------------------------
# Model calls
# ---------------------------------------------------------------------------

def _documents_blocks(case: Any) -> list[dict[str, Any]]:
    """The case documents (PDFs attached), cached: every self-test call shares this prefix."""
    from .llm import text_block

    texts = "\n\n".join(f"=== {label} ===\n{_capped(label, text)}" for label, text in case.text_documents())
    return [*case.attachments(), text_block(texts, cache=True)]


def _capped(label: str, text: str) -> str:
    """A very large document (for example a full data dump of the test environment) is cut: every
    self-test call carries the documents, and the tool results in the transcript show the real data."""
    if len(text) <= DOCUMENT_CHAR_LIMIT:
        return text
    return (text[:DOCUMENT_CHAR_LIMIT] + f"\n[... {label}: cut here for the self-test, {len(text) - DOCUMENT_CHAR_LIMIT} "
            "more characters; an overview document or the tool results give the rest]")


def _ask(model: Any, case: Any, task: str, purpose: str, blocks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """One model call: shared system + cached documents + the task; returns its JSON object."""
    from .llm import text_block

    content = [*(blocks if blocks is not None else _documents_blocks(case)), text_block(task)]
    reply = model.complete(SELFTEST_SYSTEM.text, [{"role": "user", "content": content}], purpose)
    return parse_json_object(getattr(reply, "text", reply))


def parse_json_object(text: str) -> dict[str, Any]:
    """The first JSON object in a reply (fences and prose around it are ignored)."""
    text = str(text or "")
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in the reply")
    value, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(value, dict):
        raise ValueError("the reply is not a JSON object")
    return value


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(item) for item in value or [] if str(item).strip()] if isinstance(value, list) else []


def parse_scenarios(answer: dict[str, Any]) -> tuple[list[Scenario], list[str]]:
    """Scenarios from the model's JSON; a malformed one is skipped with a note."""
    scenarios: list[Scenario] = []
    notes: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(answer.get("scenarios") or []):
        if not isinstance(item, dict):
            notes.append(f"scenario {index}: not an object; skipped")
            continue
        sid = re.sub(r"[^a-z0-9_]+", "_", str(item.get("id") or f"scenario_{index + 1}").lower()).strip("_")
        sid = sid or f"scenario_{index + 1}"
        while sid in seen:
            sid += "_x"
        missing = [key for key in ("goal", "opening") if not str(item.get(key) or "").strip()]
        if missing or not _strings(item.get("expected")):
            notes.append(f"scenario {sid}: no {', '.join(missing or ['expected'])}; skipped")
            continue
        variables = item.get("variables") if isinstance(item.get("variables"), dict) else {}
        try:
            turns = max(1, min(MAX_CALLER_TURNS, int(item.get("max_turns") or MAX_CALLER_TURNS)))
        except (TypeError, ValueError):
            turns = MAX_CALLER_TURNS
        seen.add(sid)
        scenarios.append(Scenario(
            sid, str(item.get("persona") or ""), str(item["goal"]), str(item.get("language") or ""),
            {str(key): value for key, value in variables.items()}, str(item["opening"]),
            _strings(item.get("expected")), _strings(item.get("expected_tools")), _strings(item.get("forbidden")),
            turns))
    scenarios = scenarios[:MAX_SCENARIOS]
    # A call variable one scenario left out (for example the call time) is taken from another one.
    for item in scenarios:
        for other in scenarios:
            for key, value in other.variables.items():
                if key not in item.variables:
                    item.variables[key] = value
                    notes.append(f"scenario {item.id}: call variable {key} taken from scenario {other.id}")
    return scenarios, notes


def derive_scenarios(case: Any, model: Any, blocks: list[dict[str, Any]] | None = None) -> tuple[list[Scenario], list[str]]:
    task = SELFTEST_SCENARIOS_TASK.text.replace("{max}", str(MAX_SCENARIOS)).replace("{turns}", str(MAX_CALLER_TURNS))
    return parse_scenarios(_ask(model, case, task, "selftest_scenarios", blocks))


def parse_verdict(answer: dict[str, Any]) -> tuple[str, list[str], str]:
    value = answer.get("pass")
    if isinstance(value, str):
        value = value.strip().lower() in ("true", "yes", "pass")
    if not isinstance(value, bool):
        raise ValueError("the judge gave no pass value")
    return (PASS if value else FAIL), _strings(answer.get("reasons")), str(answer.get("fix") or "")


# ---------------------------------------------------------------------------
# The call record
# ---------------------------------------------------------------------------

def _short(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= TOOL_RESULT_CHARS else text[:TOOL_RESULT_CHARS] + " …"


def transcript_of(call: dict[str, Any]) -> str:
    """Caller and agent lines with each tool call and its result, in order."""
    lines: list[str] = []
    for item in call.get("messages", []) if isinstance(call, dict) else []:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role == "user":
            lines.append("Caller: " + str(item.get("message", "")))
        elif role in ("assistant", "bot"):
            lines.append("Agent: " + str(item.get("message", "")))
        elif role == "system":
            for event in _system_events({"messages": [item]}):
                kind, name = event.get("event"), event.get("function")
                if kind == "function_call_start" and name:
                    lines.append(f"[tool {name} called with {_short(event.get('args'))}]")
                elif kind == "function_call_complete" and name:
                    outcome = event.get("result") if event.get("result") is not None else event.get("error")
                    lines.append(f"[tool {name} returned {_short(outcome)}]")
                elif kind == "node_enter" and event.get("node"):
                    lines.append(f"[step {event['node']}]")
                elif kind == "error":
                    lines.append(f"[engine error {_short(event.get('message') or event)}]")
    return "\n".join(lines)


def _reply_text(response: Any) -> str:
    if isinstance(response, dict):
        return str(response.get("response") or response.get("message") or "")
    return str(response or "")


# ---------------------------------------------------------------------------
# One scenario
# ---------------------------------------------------------------------------

def run_scenario(scenario: Scenario, workflow_id: str, *, model: Any, chat: Any, case: Any,
                 blocks: list[dict[str, Any]], deadline: float,
                 clock: Callable[[], float] = time.monotonic) -> ScenarioResult:
    """Play the scenario through chat, read the call record, judge it."""
    started = clock()
    call_id = ""
    call: dict[str, Any] = {}
    local: list[str] = []          # what the chat replies said, used until the record is read
    message = scenario.opening
    turns = 0

    def timeout() -> float:
        return max(1.0, min(CHAT_TIMEOUT_SECONDS, deadline - clock()))

    def result(verdict: str, reasons: list[str], fix: str = "", transcript: str = "") -> ScenarioResult:
        return ScenarioResult(scenario.id, verdict, reasons, fix, call_id, turns, round(clock() - started, 1),
                              transcript or "\n".join(local))

    try:
        while turns < scenario.max_turns:
            if clock() >= deadline:
                return result(ERROR, ["self-test time is up"])
            turns += 1
            local.append("Caller: " + message)
            response = None
            for attempt in range(2):
                try:
                    response = chat.chat_message(workflow_id, message, scenario.variables, call_id or None,
                                                 timeout_seconds=timeout())
                    break
                except Exception as exc:  # one retry on a gateway error; the record shows if it ran
                    if attempt or not _is_5xx(exc):
                        return result(ERROR, ["chat turn failed: " + str(exc)[:200]])
            if isinstance(response, dict) and response.get("callId"):
                call_id = str(response["callId"])
            if not call_id:
                return result(ERROR, ["chat reply had no callId"])
            local.append("Agent: " + _reply_text(response))
            try:
                call = chat.get_call(call_id, timeout_seconds=timeout())
            except Exception:
                call = {}
            if call and _ended(call):
                break
            transcript = transcript_of(call) if call else "\n".join(local)
            task = (SELFTEST_CUSTOMER_TASK.text.replace("{scenario}", scenario.brief())
                    .replace("{transcript}", transcript))
            try:
                answer = _ask(model, case, task, "selftest_caller", blocks)
            except Exception as exc:
                return result(ERROR, ["caller model failed: " + str(exc)[:200]])
            message = str(answer.get("message") or "").strip()
            if not message:
                break
            if answer.get("hang_up") is True:
                turns += 1
                local.append("Caller: " + message)
                try:
                    chat.chat_message(workflow_id, message, scenario.variables, call_id, timeout_seconds=timeout())
                except Exception:
                    pass
                break
        try:
            call = chat.get_call(call_id, timeout_seconds=timeout())
        except Exception:
            pass
        transcript = transcript_of(call) if call else "\n".join(local)
        task = SELFTEST_JUDGE_TASK.text.replace("{scenario}", scenario.brief()).replace("{transcript}", transcript)
        try:
            verdict, reasons, fix = parse_verdict(_ask(model, case, task, "selftest_judge", blocks))
        except Exception as exc:
            return result(ERROR, ["judge failed: " + str(exc)[:200]], transcript=transcript)
        return result(verdict, reasons, fix, transcript)
    except Exception as exc:  # never let one scenario stop the build
        return result(ERROR, ["unexpected: " + str(exc)[:200]])
    finally:
        if call_id and not (call and _ended(call)):
            try:
                chat.end_chat(call_id, timeout_seconds=timeout())
            except Exception:
                pass


def run_scenarios(scenarios: list[Scenario], workflow_id: str, **kwargs: Any) -> list[ScenarioResult]:
    if not scenarios:
        return []
    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL, len(scenarios))) as pool:
        return list(pool.map(lambda item: run_scenario(item, workflow_id, **kwargs), scenarios))


def problem_lines(results: list[ScenarioResult], scenarios: dict[str, Scenario]) -> list[str]:
    """The judge's failures as repair problems (platform errors are not the workflow's fault)."""
    lines = []
    for item in results:
        if item.verdict != FAIL:
            continue
        goal = scenarios[item.id].goal if item.id in scenarios else ""
        lines.append(SELFTEST_REPAIR_LINE.text.replace("{id}", item.id).replace("{goal}", goal)
                     .replace("{reasons}", "; ".join(item.reasons) or "no reason given").replace("{fix}", item.fix or "-"))
    return lines


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

def _call_repair(repair: Callable[..., Any], problems: list[str], workflow: dict[str, Any]) -> dict[str, Any]:
    """repair(problems, workflow) when it takes two arguments, else repair(problems)."""
    try:
        parameters = inspect.signature(repair).parameters.values()
        two = sum(1 for p in parameters if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)) >= 2 or any(
            p.kind == p.VAR_POSITIONAL for p in parameters)
    except (TypeError, ValueError):
        two = False
    return repair(problems, workflow) if two else repair(problems)


def _trace(trace: Any, key: str, value: Any) -> None:
    if trace is not None:
        trace.add(key, value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str))


def _saved(result: Any, workflow: dict[str, Any], fallback_id: str = "") -> tuple[str, dict[str, Any]]:
    """save() returns the workflow id, or (id, the workflow it really saved) when it changed it
    (for example a Freya validation repair): the export must be the live version."""
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
        return str(result[0] or fallback_id), result[1]
    return str(result or fallback_id), workflow


def self_test_loop(case: Any, workflow: dict[str, Any], save: Callable[[dict[str, Any]], Any],
                   repair: Callable[..., dict[str, Any]], trace: Any, *, model: Any, chat: Any,
                   deadline: float, workflow_id: str | None = None, rounds: int = REPAIR_ROUNDS,
                   clock: Callable[[], float] = time.monotonic) -> tuple[dict[str, Any], list[ScenarioResult]]:
    """Test the saved workflow, repair failures, keep the version with the most passes.

    Returns (best workflow, its results per scenario). The best workflow is the live one."""
    if model is None or chat is None:
        _trace(trace, "self_test", "skipped: no model or chat client")
        return workflow, []
    blocks = _documents_blocks(case)
    try:
        scenarios, notes = derive_scenarios(case, model, blocks)
    except Exception as exc:
        _trace(trace, "self_test", f"skipped: scenarios could not be made ({str(exc)[:200]})")
        return workflow, []
    for note in notes:
        _trace(trace, "warning", "self-test " + note)
    _trace(trace, "self_test_scenarios", [asdict(item) for item in scenarios])
    if not scenarios:
        _trace(trace, "self_test", "skipped: the documents gave no scenario")
        return workflow, []
    by_id = {item.id: item for item in scenarios}
    try:
        live_id, workflow = (workflow_id, workflow) if workflow_id else _saved(save(workflow), workflow)
    except Exception as exc:
        _trace(trace, "self_test", f"skipped: save failed ({str(exc)[:200]})")
        return workflow, []
    kwargs = dict(model=model, chat=chat, case=case, blocks=blocks, deadline=deadline, clock=clock)

    def record(round_number: int, results: list[ScenarioResult]) -> None:
        for item in results:
            _trace(trace, "self_test_result", {"round": round_number, **asdict(item)})

    round_started = clock()
    current = {item.id: item for item in run_scenarios(scenarios, live_id, **kwargs)}
    record(0, list(current.values()))
    round_seconds = clock() - round_started
    best_workflow, best = workflow, dict(current)
    live_workflow = workflow

    def passes(results: dict[str, ScenarioResult]) -> int:
        return sum(1 for item in results.values() if item.verdict == PASS)

    _trace(trace, "self_test_round", {"round": 0, "passed": passes(current), "of": len(scenarios),
                                      "seconds": round(round_seconds, 1)})
    for round_number in range(1, rounds + 1):
        problems = problem_lines(list(current.values()), by_id)
        if not problems:
            break
        if deadline - clock() < round_seconds + REPAIR_RESERVE_SECONDS:
            _trace(trace, "self_test", f"round {round_number} not started: not enough time left")
            break
        try:
            repaired = _call_repair(repair, problems, live_workflow)
            live_id, repaired = _saved(save(repaired), repaired, live_id)
        except Exception as exc:
            _trace(trace, "self_test", f"round {round_number}: repair or save failed ({str(exc)[:200]})")
            break
        live_workflow = repaired
        failed = [by_id[item.id] for item in current.values() if item.verdict != PASS]
        round_started = clock()
        rerun = run_scenarios(failed, live_id, **kwargs)
        round_seconds = clock() - round_started
        record(round_number, rerun)
        current = {**current, **{item.id: item for item in rerun}}
        _trace(trace, "self_test_round", {"round": round_number, "passed": passes(current), "of": len(scenarios),
                                          "seconds": round(round_seconds, 1)})
        if passes(current) > passes(best):
            best_workflow, best = live_workflow, dict(current)
    if live_workflow is not best_workflow:
        try:
            _, best_workflow = _saved(save(best_workflow), best_workflow)
            _trace(trace, "self_test", f"kept the earlier version with {passes(best)} passes")
        except Exception as exc:
            _trace(trace, "warning", f"self-test could not re-save the best version ({str(exc)[:200]}); "
                                     "the last repaired version stays live")
            best_workflow, best = live_workflow, current
    _trace(trace, "self_test", f"{passes(best)} of {len(scenarios)} scenarios passed")
    return best_workflow, list(best.values())
