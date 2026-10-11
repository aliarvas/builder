"""T-010: offline self-check of the rendered workflow against what the spec requires.

Layer 1 of "tests and improves it": no Freya, no model, no practice file. Scenarios are made
from the spec only and played on the rendered workflow:

- ``Simulator`` walks one call from the initial step. It runs the generated code steps,
  evaluates the rendered transition conditions, applies the platform rule for typed writes
  (F-052/F-060: a value that does not fit the extraction field is rejected, the old value
  kept), runs api steps and the model's tool calls through ``Bank``, and enters global
  special-path steps when a scenario says so.
- ``Bank`` answers the tools from the OpenAPI response shapes and the spec's field names, with
  scripted answers per scenario, and keeps the ledger (every tool call in order).
- ``scenarios`` builds the calls; the expected ledger comes from the spec (outcome rows,
  ``selfcheck_calendar`` for dates and amounts, the note rule).
- ``run_selfcheck`` plays them and sorts the failures: a *spec* problem (an ending no scenario
  can reach) goes back to extraction as a repair; anything else is a *builder* problem, a
  trace warning.

The model's part is "ideal extraction": the values a correct extraction would write.
"""

from __future__ import annotations

import builtins
import copy
import dataclasses
import datetime
import json
import time
from typing import Any, Callable

from .callback import (
    DAY_TEXT, THIRD_PARTY_CLOSE_EXPLICIT, THIRD_PARTY_CLOSE_KIND, TIME_TEXT, callback_window,
)
from .offer_check import ACCEPTS_YES, OFFER_ACCEPTS, OFFER_AMOUNT, OFFER_DATE, OFFER_PRODUCT
from .selfcheck_calendar import SpecCalendar, first_rule
from .record_loop import RECORD_PROMISE
from .spec import FRAMEWORK_NONE_VALUE, SPECIAL_THEN_CLOSE, PhoneAgentSpec
from .tools_from_openapi import CALL_VARIABLES

END_CALL = "end_call"
PREVIOUS = "__previous__"
SPEAKING = ("tts", "llm")
# A simulator parameter, not policy: the kit's mock verify_identity allows this many wrong
# answers in total. The workflow routes on the ``attempts_left`` value the bank returns, so a
# bank with another limit only changes how many wrong answers a scenario plays.
BANK_WRONG_ANSWERS = 3
# Modules a code step or hook may import on the platform (kit docs: tools-and-code).
ALLOWED_IMPORTS = ("json", "re", "datetime")
# Loop guards: steps walked without a customer turn, and repeats of one customer turn.
MAX_PASSTHROUGH = 200
MAX_REPEATS = 8
SPEC, BUILDER = "spec", "builder"


# ---------------------------------------------------------------------------
# Rendered conditions and typed writes (the platform's reading)
# ---------------------------------------------------------------------------

def holds(condition: dict[str, Any], variables: dict[str, Any]) -> bool:
    """A rendered transition condition, evaluated the way the platform compares values."""
    if "conditions" in condition:
        parts = [holds(item, variables) for item in condition["conditions"]]
        return all(parts) if condition.get("logic") == "and" else any(parts)
    operator = condition.get("operator")
    if operator == "always":
        return True
    value = variables.get(condition.get("variable"))
    present = value not in (None, "")
    operand = condition.get("operand")
    if operator == "is_set":
        return present
    if operator == "equals":
        return present and str(value) == str(operand)
    if operator == "not_equals":
        return not (present and str(value) == str(operand))
    if operator in ("greater_than", "less_than") and present:
        try:
            number, limit = float(value), float(operand)
        except (TypeError, ValueError):
            return False
        return number > limit if operator == "greater_than" else number < limit
    return False


def fits(value: Any, field: dict[str, Any]) -> bool:
    """Whether the platform accepts ``value`` for an extraction field (F-052/F-060)."""
    if "enum_values" in field:
        return value in field["enum_values"]
    kind = field.get("type")
    if kind == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    return isinstance(value, str)


def code_of(node: dict[str, Any]) -> str:
    return node["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]


def _sandbox(problems: list[str], where: str, **names: Any) -> dict[str, Any]:
    """Globals for one code step or hook: only ``names`` and the platform's importable modules."""
    def guarded(name, *args, **kwargs):
        if name.split(".")[0] not in ALLOWED_IMPORTS:
            problems.append(f"{where} imports {name} (the platform allows {', '.join(ALLOWED_IMPORTS)})")
        return builtins.__import__(name, *args, **kwargs)
    return {**names, "__builtins__": {**vars(builtins), "__import__": guarded}}


def _get_path(data: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(data, dict):
            return None
        data = data.get(part)
    return data


# ---------------------------------------------------------------------------
# Bank
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ToolCall:
    tool: str
    body: dict[str, Any]
    ok: bool
    step: str


class Bank:
    """Plays the bank's tools. ``answers`` maps a tool name to its ok values in call order
    (ok once they run out); ``identity`` lists whether each security answer is right."""

    def __init__(self, spec: PhoneAgentSpec, products: list[dict[str, Any]],
                 answers: dict[str, list[bool]] | None = None, identity: list[bool] | None = None) -> None:
        self.spec = spec
        self.products = products
        self.answers = {name: list(values) for name, values in (answers or {}).items()}
        self.identity = list(identity or [])
        self.wrong_left = BANK_WRONG_ANSWERS
        self.passed: set[str] = set()
        self.calls: list[ToolCall] = []

    def answer(self, tool: str, body: dict[str, Any], step: str) -> dict[str, Any]:
        identity = self.spec.identity.data
        account = self.spec.account.data
        queue = self.answers.get(tool)
        ok = queue.pop(0) if queue else True
        data: dict[str, Any] = {"ok": ok}
        if tool == self.identity_tool:
            right = self.identity.pop(0) if self.identity else True
            field = next((str(value) for value in body.values() if str(value) in self.question_fields), "")
            if right:
                self.passed.add(field)
            else:
                self.wrong_left = max(0, self.wrong_left - 1)
            data.update({
                identity["answer_verified_field"]: right,
                identity["verified_field"]: self.passed >= set(self.question_fields),
                identity["attempts_left_field"]: self.wrong_left,
            })
        elif tool == self.account_tool:
            data[account["products_field"]] = copy.deepcopy(self.products) if ok else []
        self.calls.append(ToolCall(tool, dict(body), ok, step))
        return {"status_code": 200 if ok else 500, "data": data}

    identity_tool = ""
    account_tool = ""
    question_fields: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

class Simulator:
    """One call on a rendered workflow, from the first step to ``end_call``."""

    def __init__(self, workflow: dict[str, Any], spec: PhoneAgentSpec, bank: Bank,
                 variables: dict[str, Any]) -> None:
        self.spec = spec
        self.nodes = {**workflow["nodes"], **workflow.get("global_nodes", {})}
        self.globals = workflow.get("global_nodes", {})
        self.bank = bank
        self.vars = dict(variables)
        self.fields = {field["name"]: field for node in self.nodes.values()
                       for field in node.get("extraction_schema") or []}
        self.rejected: list[tuple[str, str, Any]] = []
        self.path: list[str] = []
        self.problems: list[str] = []
        self.spoken_after_turn: list[str] = []
        self.previous = ""
        self.merged: set[str] = set()
        self.extract_failed = False   # the last turn's extraction wrote less than it was given
        self.spec_failures: list[tuple[str, str]] = []   # (spec path, problem): for repair
        self.step = workflow["initial_node"]
        bank.identity_tool = self._identity_tool()
        bank.account_tool = self._account_tool()
        bank.question_fields = tuple(str(q.get("field")) for q in spec.identity.data.get("questions", []))

    # -- tools of the rendered workflow ------------------------------------
    def _identity_tool(self) -> str:
        for node in self.nodes.values():
            for tool in node.get("tools") or []:
                names = {item.get("variable") for item in tool.get("response_mapping") or []}
                if self.spec.identity.data.get("verified_field") and any(
                        item.get("path", "").endswith("." + self.spec.identity.data["verified_field"])
                        for item in tool.get("response_mapping") or []) and names:
                    return tool["function"]["name"]
        return ""

    def _account_tool(self) -> str:
        variable = self.spec.account.data["products_variable"]
        for node in self.nodes.values():
            for item in node.get("response_mapping") or []:
                if item.get("variable") == variable:
                    return node["pre_actions"][0]["function"]["name"]
        return ""

    # -- running steps -----------------------------------------------------
    def run_code(self, key: str) -> None:
        before = dict(self.vars)
        try:
            exec(code_of(self.nodes[key]), _sandbox(self.problems, f"code step {key}", vars=self.vars))
        except Exception as exc:  # generated code must never raise
            self.problems.append(f"code step {key} raised {type(exc).__name__}: {exc}")
        for name, field in self.fields.items():
            if name in self.vars and self.vars[name] != before.get(name) and not fits(self.vars[name], field):
                self.rejected.append((key, name, self.vars[name]))
                if name in before:
                    self.vars[name] = before[name]
                else:
                    del self.vars[name]

    def call_tool(self, tool: dict[str, Any], step: str, args: dict[str, Any] | None = None) -> bool:
        """A tool call (an api step's pre-action, or the model's call with ``args``)."""
        properties = tool["function"]["parameters"]["properties"].get("body", {}).get("properties", {})
        body: dict[str, Any] = {}
        for name, prop in properties.items():
            default = str(prop.get("default", ""))
            if default.startswith("{{") and default.endswith("}}"):
                variable = default[2:-2]
                if variable in self.vars:
                    body[name] = self.vars[variable]
                elif variable in CALL_VARIABLES:
                    body[name] = "sim-" + variable
            elif "default" in prop:
                body[name] = prop["default"]
        body.update(args or {})
        config = {"body": body}
        if tool.get("pre_process_code"):
            try:
                exec(tool["pre_process_code"], _sandbox(self.problems, f"pre-hook of {tool['function']['name']}",
                                                        vars=self.vars, config=config))
            except Exception as exc:
                self.problems.append(f"pre-hook of {tool['function']['name']} raised {type(exc).__name__}")
        name = tool["function"]["name"]
        result = self.bank.answer(name, config["body"], step)
        if tool.get("post_process_code"):
            try:
                exec(tool["post_process_code"], _sandbox(self.problems, f"post-hook of {name}",
                                                         result=result, vars=self.vars))
            except Exception as exc:
                self.problems.append(f"post-hook of {name} raised {type(exc).__name__}")
        for item in tool.get("response_mapping") or []:
            value = _get_path(result, item["path"])
            if value is not None:
                self.vars[item["variable"]] = value
        return bool(_get_path(result, "data.ok"))

    def run_api(self, key: str) -> None:
        node = self.nodes[key]
        if not node.get("pre_actions"):
            self.problems.append(f"api step {key} has no tool")
            return
        tool = node["pre_actions"][0]
        if not tool.get("response_mapping") and node.get("response_mapping"):
            tool = {**tool, "response_mapping": node["response_mapping"]}
        ok = self.call_tool(tool, key)
        counter = f"{key}_{'success' if ok else 'failure'}_count"
        self.vars[counter] = int(self.vars.get(counter) or 0) + 1

    def route(self, key: str) -> str | None:
        node = self.nodes[key]
        targets = [t["target_node"] for t in node.get("transitions", []) if not t.get("is_tool_call")]
        if len(targets) != len(set(targets)) and key not in self.merged:
            # The platform merges same-target transitions (OR), so the rendered order is lost.
            self.merged.add(key)
            self.problems.append(f"step {key} has more than one transition to "
                                 f"{sorted({t for t in targets if targets.count(t) > 1})}")
        for transition in node.get("transitions", []):
            if not transition.get("is_tool_call") and holds(transition["condition"], self.vars):
                return transition["target_node"]
        if node.get("passthrough"):
            return node.get("passthrough_default_transition")
        return None

    def _target(self, target: str) -> str:
        if target == PREVIOUS:
            return self.previous
        return target

    def advance(self) -> str:
        """Walk the passthrough steps until a conversation step waits or the call ends."""
        for _ in range(MAX_PASSTHROUGH):
            key = self.step
            if key == END_CALL or key not in self.nodes:
                return key
            node = self.nodes[key]
            if node.get("on_enter", {}).get("type") in SPEAKING:
                self.spoken_after_turn.append(key)
            if node["node_type"] == "conversation":
                return key
            if node["node_type"] == "end_call":
                self.step = END_CALL
                return END_CALL
            if node["node_type"] == "code":
                self.run_code(key)
            elif node["node_type"] == "api_request":
                self.run_api(key)
            target = self.route(key)
            if target is None:
                self.problems.append(f"dead end at {key}: no transition holds")
                return key
            self.path.append(key)
            self.step = self._target(target)
        self.problems.append(f"routing loop after {self.step}")
        return self.step

    # -- customer turns -----------------------------------------------------
    def turn(self, extracted: dict[str, Any]) -> bool:
        """The customer speaks at the waiting step; the extraction writes; the step routes.
        False when no transition takes the turn (the step keeps waiting)."""
        key = self.advance()
        if key == END_CALL or key not in self.nodes:
            return False
        self.spoken_after_turn = []
        self.extract(key, extracted)
        target = self.route(key)
        if target is None:
            return False
        self.path.append(key)
        self.step = self._target(target)
        return True

    def extract(self, key: str, extracted: dict[str, Any]) -> None:
        """The model's extraction at step ``key``: only the step's own fields, with values that
        fit them, are written (ideal extraction cannot write what the step does not declare)."""
        schema = {field["name"]: field for field in self.nodes[key].get("extraction_schema") or []}
        self.extract_failed = False
        for name, value in extracted.items():
            field = schema.get(name)
            if field is None or not fits(value, field):
                self.extract_failed = True
                self.problems.append(f"{key} cannot extract {name}={value!r}")
                continue
            self.vars[name] = value

    def tool_turn(self, args: dict[str, Any]) -> bool:
        """The model calls the waiting step's tool with ``args`` (an identity answer), then
        the step routes on the result."""
        key = self.advance()
        node = self.nodes.get(key, {})
        tools = node.get("tools") or []
        if not tools:
            self.problems.append(f"{key} has no tool for the model to call")
            return False
        self.spoken_after_turn = []
        tool = tools[0]
        properties = tool["function"]["parameters"]["properties"].get("body", {}).get("properties", {})
        filled = {}
        for name, prop in properties.items():
            default = str(prop.get("default", ""))
            model_filled = default.startswith("{{") and default[2:-2] not in CALL_VARIABLES
            if not model_filled:
                continue
            enum = [str(value) for value in prop.get("enum", [])]
            choice = args.get("choice")
            if enum and choice not in enum and name not in args:
                self.problems.append(f"{key} cannot extract {name}={choice!r}")
            filled[name] = choice if choice in enum else args.get(name, "sim-answer")
        for name in args:
            if name != "choice" and name not in filled:
                self.problems.append(f"{key} cannot extract {name}={args[name]!r}")
        # The platform stores the model's arguments as ``<tool>_args.<field>`` (kit docs).
        for name, value in filled.items():
            self.vars[f"{tool['function']['name']}_args.{name}"] = value
        self.call_tool(tool, key, filled)
        target = self.route(key)
        if target is None:
            return True  # the step waits for the next answer
        self.path.append(key)
        self.step = self._target(target)
        return True

    def enter_special(self, node_key: str) -> bool:
        """A global special-path step triggered at the waiting step (its intent matched)."""
        key = self.advance()
        node = self.globals.get(node_key)
        if node is None:
            self.problems.append(f"special step {node_key} is missing")
            return False
        if key in node.get("excluded_nodes", []):
            self.problems.append(f"special step {node_key} cannot start at {key}")
            return False
        self.spoken_after_turn = []
        self.previous = key
        self.step = node_key
        return True


# ---------------------------------------------------------------------------
# Scenarios (from the spec only)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class Scenario:
    id: str
    actions: list[dict[str, Any]]
    expect_state: str                       # the call-end state the spec maps to a row
    products: list[dict[str, Any]]
    answers: dict[str, list[bool]] = dataclasses.field(default_factory=dict)
    identity: list[bool] = dataclasses.field(default_factory=list)
    promises: list[tuple[str, float, str]] = dataclasses.field(default_factory=list)
    notes: list[tuple[str, str]] | None = None   # None: not checked
    pair: tuple[str, str] | None = None     # an outcome pair given directly (a special path)
    repeats: dict[str, int] = dataclasses.field(default_factory=dict)  # action label -> turns
    step: str = ""                          # the step the scenario is about


def synthetic_products(spec: PhoneAgentSpec, count: int) -> list[dict[str, Any]]:
    """Products that match the spec's offer rules: one per deadline band and floor rule."""
    offer = spec.offer.data
    account = spec.account.data
    bands = [rule.get("when") or [] for rule in offer.get("latest") or []] or [[]]
    kinds = [rule for rule in offer.get("min_amount") or []] or [{}]
    full_rule = first_rule(offer.get("max_amount"), {}) or (offer.get("max_amount") or [{}])[0]
    combos = [(band, kind) for kind in kinds for band in bands]
    products = []
    for index in range(count):
        band, kind = combos[index % len(combos)]
        product: dict[str, Any] = {account["product_id_field"]: f"p{index + 1}"}
        for item in [*band, *(kind.get("when") or [])]:
            if "equals" in item:
                product[item["field"]] = item["equals"]
            elif "in" in item:
                product[item["field"]] = item["in"][0]
            elif "min" in item or "max" in item:
                low = item.get("min", item.get("max", 0))
                high = item.get("max", low)
                product[item["field"]] = (low + high) // 2 if isinstance(low, int) and isinstance(high, int) else low
        full = 400.0 + 100.0 * index
        if full_rule.get("field"):
            product[full_rule["field"]] = full
        if kind.get("field") and kind.get("field") != full_rule.get("field"):
            product[kind["field"]] = round(full / 4, 2)
        label = account.get("product_label_field")
        if label:
            product[label] = f"{index + 1:04d}"
        products.append(product)
    return products


class _Plan:
    """Shared values for the scenario builders."""

    def __init__(self, spec: PhoneAgentSpec, now: str) -> None:
        self.spec = spec
        self.now = now
        self.calendar = SpecCalendar(spec, now)
        self.opening = spec.opening.data
        self.third = spec.third_party.data
        self.negotiation = spec.negotiation.data
        self.confirmation = spec.confirmation.data
        self.notes = spec.closing.data.get("product_notes")
        self.questions = [str(q.get("field")) for q in spec.identity.data.get("questions", [])]
        self.promise_tool = ""

    def answer_who(self, values_key: str) -> dict[str, Any]:
        return {"kind": "say", "label": "opening", "spec_path": f"opening.{values_key}[0]",
                "vars": {self.opening["who_answered_variable"]: self.opening[values_key][0]}}

    def verify(self, right: bool = True) -> list[dict[str, Any]]:
        return [{"kind": "tool", "label": "identity", "args": {"choice": field}} for field in self.questions]

    def reach_negotiation(self) -> list[dict[str, Any]]:
        return [self.answer_who("identity_values"), *self.verify()]

    def offer(self, number: int, day: str, amount: float | None = None) -> dict[str, Any]:
        values: dict[str, Any] = {OFFER_DATE: day, OFFER_PRODUCT: number}
        if amount is not None:
            values[OFFER_AMOUNT] = amount
        return {"kind": "say", "label": "offer", "vars": values}

    def accept(self, number: int) -> dict[str, Any]:
        return {"kind": "say", "label": "accept", "vars": {OFFER_DATE: "", OFFER_ACCEPTS: ACCEPTS_YES, OFFER_PRODUCT: number}}

    def confirm(self) -> dict[str, Any]:
        values = self.confirmation["intent_values"]
        value = next(v for v in values if v not in self.confirmation["revise_values"] and v != FRAMEWORK_NONE_VALUE)
        return {"kind": "say", "label": "confirm", "spec_path": f"confirmation.intent_values[{values.index(value)}]",
                "vars": {self.confirmation["intent_variable"]: value}}

    def refusal_value(self) -> str:
        ends = self.negotiation.get("product_end_values") or []
        return ends[0] if ends else self.negotiation["close_values"][0]

    def refuse(self, value: str | None = None, label: str = "refuse") -> dict[str, Any]:
        value = value or self.refusal_value()
        key = "close_values" if value in self.negotiation["close_values"] else "product_end_values"
        return {"kind": "say", "label": label, "repeat": True, "until": ("offer_say", "confirm_record"),
                "spec_path": f"negotiation.{key}[{self.negotiation[key].index(value)}]",
                "vars": {self.negotiation["intent_variable"]: value}}

    def good_day(self, products: list[dict[str, Any]]) -> str | None:
        days = [self.calendar.first_allowed(product) for product in products]
        if any(day is None for day in days):
            return None
        return max(days).isoformat()

    def promise(self, product: dict[str, Any], day: str, amount: float | None = None) -> tuple[str, float, str]:
        account = self.spec.account.data
        return (str(product[account["product_id_field"]]),
                float(self.calendar.full(product) if amount is None else amount), day)

    def note_reasons(self, products: list[dict[str, Any]], promised: set[str], close_reason: str,
                     refused: set[str] = frozenset(), failed: set[str] = frozenset(),
                     written: dict[str, str] | None = None) -> list[tuple[str, str]] | None:
        """The notes the spec's note rule asks for (F-061): every product without a promise."""
        if not self.notes:
            return None
        account = self.spec.account.data
        notes = []
        for product in products:
            pid = str(product[account["product_id_field"]])
            if pid in promised:
                continue
            if written and pid in written:
                notes.append((pid, written[pid]))
            elif pid in failed:
                notes.append((pid, self.notes["failed_reason"]))
            elif pid in refused:
                notes.append((pid, self.notes["refused_reason"]))
            elif close_reason in self.notes["reasons"] and close_reason != self.notes["failed_reason"]:
                notes.append((pid, close_reason))
            else:
                notes.append((pid, self.notes["refused_reason"]))
        return sorted(notes)


def _row_reason(spec: PhoneAgentSpec, state: str) -> str:
    row = next((item for item in spec.outcomes if state in item.on), None)
    row = row or next(item for item in spec.outcomes if "default" in item.on)
    return row.reason


def scenarios(spec: PhoneAgentSpec, now: str) -> list[Scenario]:
    plan = _Plan(spec, now)
    one = synthetic_products(spec, 1)
    result: list[Scenario] = []

    def notes_for(products, promised=(), refused=(), failed=(), state="", written=None, pair=None):
        reason = pair[1] if pair else _row_reason(spec, state)
        outcome = pair[0] if pair else None
        if plan.notes and outcome in plan.notes.get("skip_outcomes", []):
            return []
        if plan.notes:
            row = next((item for item in spec.outcomes if state in item.on), None)
            if row is not None and row.outcome in plan.notes.get("skip_outcomes", []):
                return []
        return plan.note_reasons(products, set(promised), reason, set(refused), set(failed), written)

    # Opening routes.
    for index, value in enumerate(plan.opening.get("close_values", [])):
        result.append(Scenario(f"opening_{value}", [{"kind": "say", "label": "opening",
                                                       "spec_path": f"opening.close_values[{index}]",
                                                       "vars": {plan.opening["who_answered_variable"]: value}}],
                               "opening:" + value, one, step="opening"))
    if plan.opening.get("stay_values"):
        result.append(Scenario("opening_unclear", [{**plan.answer_who("stay_values"), "repeat": True}],
                               "opening_unclear", one, step="opening"))

    # Identity: attempts used up; one wrong answer, then right.
    result.append(Scenario("identity_failed", [plan.answer_who("identity_values"),
                                               {"kind": "tool", "label": "identity", "repeat": True,
                                                "args": {"choice": plan.questions[0] if plan.questions else ""}}],
                           "identity_failed", one, identity=[False] * (BANK_WRONG_ANSWERS + 1), step="identity"))

    # A promise for the full amount on the first allowed day (after one wrong answer).
    day = plan.good_day(one)
    if day:
        result.append(Scenario(
            "promise", [plan.answer_who("identity_values"),
                        {"kind": "tool", "label": "identity", "args": {"choice": plan.questions[0]}},
                        *plan.verify(), plan.offer(1, day), plan.confirm()],
            "promise_recorded", one, identity=[False], promises=[plan.promise(one[0], day)],
            notes=notes_for(one, promised=["p1"], state="promise_recorded"), step="negotiate"))
        result.extend(_offer_scenarios(spec, plan, one, notes_for))
        # The record call fails every time.
        attempts = plan.confirmation["max_attempts_per_product"]
        record_tool = _record_tool_name(spec)
        result.append(Scenario(
            "record_failed", [*plan.reach_negotiation(), plan.offer(1, day), plan.confirm()],
            "promise_failed", one, answers={record_tool: [False] * attempts},
            notes=notes_for(one, failed=["p1"], state="promise_failed"), step="confirm_record"))

    # Refusals: each negotiation value that closes the call.
    for value in plan.negotiation.get("close_values", []):
        persuasion = spec.offer.data.get("persuasion_attempts") or []
        counted = value in (plan.negotiation.get("product_end_values") or [])
        rule = first_rule(persuasion, one[0]) if persuasion and counted else None
        state_value = value if value in plan.negotiation["close_values"] else plan.refusal_value()
        refused = ["p1"] if counted else []
        result.append(Scenario(
            f"refusal_{value}", [*plan.reach_negotiation(), plan.refuse(value)],
            "negotiation:" + state_value, one,
            notes=notes_for(one, refused=refused, state="negotiation:" + state_value),
            repeats={"refuse": int(rule["value"]) + 1} if rule else {}, step="negotiate"))

    # Third party.
    result.extend(_third_party_scenarios(spec, plan, one))

    # Special paths.
    for path in spec.special_paths:
        result.extend(_special_scenarios(spec, plan, path, one, notes_for))

    # Several products: when the spec has per-product handling.
    if plan.notes or plan.negotiation.get("product_end_values"):
        result.extend(_multi_scenarios(spec, plan, notes_for))
    return result


# Scripted answers name the promise tool by role; ``play`` resolves it on the workflow.
RECORD = "@record"


def _record_tool_name(spec: PhoneAgentSpec) -> str:
    return RECORD


def _promise_tool(workflow: dict[str, Any], spec: PhoneAgentSpec) -> str:
    """The tool of the record loop's api step (F-063)."""
    node = workflow["nodes"].get(RECORD_PROMISE)
    return node["pre_actions"][0]["function"]["name"] if node and node.get("pre_actions") else ""


def _offer_scenarios(spec, plan, one, notes_for) -> list[Scenario]:
    calendar, product = plan.calendar, one[0]
    deadline = calendar.deadline(product)
    full, floor = calendar.full(product), calendar.floor(product)
    result = []

    def promise_case(name, turns, day, amount=None):
        result.append(Scenario(f"offer_{name}", [*plan.reach_negotiation(), *turns, plan.confirm()],
                               "promise_recorded", one, promises=[plan.promise(product, day, amount)],
                               notes=notes_for(one, promised=["p1"], state="promise_recorded"), step="check_offer"))

    start = calendar.earliest()
    # A day that is not a business day, before the deadline.
    if spec.offer.data.get("promise_date_must_be_business_day"):
        probe = start
        while probe <= deadline and calendar.is_business(probe):
            probe += datetime.timedelta(days=1)
        if probe <= deadline:
            moved, _ = calendar.outcome(probe.isoformat(), product)
            promise_case("not_business_day", [plan.offer(1, probe.isoformat()), plan.accept(1)], moved.isoformat())
    late = deadline + datetime.timedelta(days=5)
    moved, _ = calendar.outcome(late.isoformat(), product)
    promise_case("after_deadline", [plan.offer(1, late.isoformat()), plan.accept(1)], moved.isoformat())
    day = plan.good_day(one)
    if floor > 0:
        promise_case("below_floor", [plan.offer(1, day, round(floor / 2, 2)), plan.offer(1, day)], day, floor)
    promise_case("over_full", [plan.offer(1, day, full + 50), plan.offer(1, day, full)], day, full)
    limit = spec.offer.data.get("max_rejected_offers")
    if isinstance(limit, int) and limit > 0:
        turns = [plan.offer(1, (deadline + datetime.timedelta(days=3 + index)).isoformat()) for index in range(limit)]
        result.append(Scenario("offer_limit", [*plan.reach_negotiation(), *turns], "offer_limit", one,
                               notes=notes_for(one, state="offer_limit"), step="check_offer"))
    return result


def _third_party_scenarios(spec, plan, one) -> list[Scenario]:
    result = []
    third = plan.third
    if not plan.opening.get("third_party_values"):
        return result
    who = plan.answer_who("third_party_values")
    for index, value in enumerate(third.get("close_values", [])):
        result.append(Scenario(f"third_party_{value}", [who, {
            "kind": "say", "label": "third_party", "spec_path": f"third_party.close_values[{index}]", "vars": {
            third["intent_variable"]: value, THIRD_PARTY_CLOSE_KIND: THIRD_PARTY_CLOSE_EXPLICIT}}],
            "third_party:" + value, one, step="third_party"))
    window = callback_window(spec)
    today = plan.calendar.today
    clock = int(plan.now[11:13] or 0) * 60 + int(plan.now[14:16] or 0) if len(plan.now) >= 16 else 0
    if window is None:
        day, minutes = today + datetime.timedelta(days=1), 12 * 60
    else:
        day = today if window["days_ahead"] == 0 else plan.calendar.add(today, 1, window["day_unit"])
        minutes = window["earliest"] if day > today else max(window["earliest"], clock + 60)
        if minutes > window["latest"]:
            return result
    said = f"{minutes // 60:02d}:{minutes % 60:02d}"
    callback = {"kind": "say", "label": "callback_time", "vars": {DAY_TEXT: day.isoformat(), TIME_TEXT: said}}
    result.append(Scenario("callback_booked", [who, callback], "callback_scheduled", one, step="callback_check"))
    if window is not None:
        outside = window["latest"] + 60 if window["latest"] + 60 < 24 * 60 else max(0, window["earliest"] - 60)
        late = {"kind": "say", "label": "callback_time", "repeat": True,
                "vars": {DAY_TEXT: day.isoformat(), TIME_TEXT: f"{outside // 60:02d}:{outside % 60:02d}"}}
        result.append(Scenario("callback_outside", [who, late], "third_party:" + window["outside_close_value"],
                               one, step="callback_check"))
    return result


def _special_scenarios(spec, plan, path, one, notes_for) -> list[Scenario]:
    from .workflow import special_result_variable

    entry = next((step for step in ("negotiate", "identity", "opening", "third_party", "confirm_record")
                  if step in path.available_in), None)
    if entry is None:
        return []
    before = {"negotiate": plan.reach_negotiation(), "identity": [plan.answer_who("identity_values")],
              "opening": [], "third_party": [plan.answer_who("third_party_values")]}.get(entry)
    if before is None:
        day = plan.good_day(one)
        if not day:
            return []
        before = [*plan.reach_negotiation(), plan.offer(1, day)]
    enter = {"kind": "special", "label": "special", "node": "special_" + path.id,
             "choice_variable": special_result_variable(path) + "_choice"}
    result = []
    notes_reason = (path.tool_args or {}).get((plan.notes or {}).get("reason_field", ""), "")
    if path.then == SPECIAL_THEN_CLOSE:
        written = {"p1": notes_reason} if path.tool and plan.notes and path.tool == plan.notes["tool"] else None
        result.append(Scenario(f"special_{path.id}", [*before, enter], "special:" + path.id, one,
                               pair=(path.outcome, path.reason), step=entry,
                               notes=notes_for(one, pair=(path.outcome, path.reason), written=written)))
        if path.tool:
            result.append(Scenario(f"special_{path.id}_tool_failed", [*before, enter], "special_tool_failed", one,
                                   answers={path.tool: [False]}, step=entry))
    elif entry == "negotiate":
        written = {"p1": notes_reason} if path.tool and plan.notes and path.tool == plan.notes["tool"] else None
        state = "negotiation:" + plan.refusal_value()
        result.append(Scenario(f"special_{path.id}", [*before, enter, plan.refuse()], state, one, step=entry,
                               notes=notes_for(one, refused=[] if written else ["p1"], state=state, written=written)))
    return result


def _multi_scenarios(spec, plan, notes_for) -> list[Scenario]:
    products = synthetic_products(spec, 3)
    day = plan.good_day(products)
    if not day:
        return []
    ids = [f"p{number}" for number in range(1, 4)]
    offers = [plan.offer(number, day) for number in range(1, 4)]
    all_promises = [plan.promise(product, day) for product in products]
    result = [Scenario("multi_accept_all", [*plan.reach_negotiation(), *offers, plan.confirm()], "promise_recorded",
                       products, promises=all_promises,
                       notes=notes_for(products, promised=ids, state="promise_recorded"), step="negotiate")]
    if plan.negotiation.get("product_end_values"):
        turns = [offers[0], plan.refuse(label="refuse"), offers[2], plan.confirm()]
        result.append(Scenario("multi_refuse_one", [*plan.reach_negotiation(), *turns], "promise_recorded", products,
                               promises=[all_promises[0], all_promises[2]],
                               notes=notes_for(products, promised=["p1", "p3"], refused=["p2"], state="promise_recorded"),
                               step="product_refusal"))
    attempts = plan.confirmation["max_attempts_per_product"]
    result.append(Scenario("multi_record_failure", [*plan.reach_negotiation(), *offers, plan.confirm()],
                           "promise_recorded", products,
                           answers={_record_tool_name(spec): [True, *([False] * attempts), True]},
                           promises=[all_promises[0], all_promises[2]],
                           notes=notes_for(products, promised=["p1", "p3"], failed=["p2"], state="promise_recorded"),
                           step="confirmation_progress"))
    return result


# ---------------------------------------------------------------------------
# Playing and checking
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class Result:
    scenario: str
    passed: bool
    kind: str = ""          # SPEC or BUILDER when failed
    reason: str = ""
    path: str = ""          # the spec path a SPEC problem points at
    step: str = ""


@dataclasses.dataclass
class Report:
    results: list[Result]
    seconds: float
    nows: list[str] = dataclasses.field(default_factory=list)   # the moments played, the build's first
    played: int = 0          # scenarios played over all moments (only failures of extra moments are listed)

    @property
    def spec_problems(self) -> list[Result]:
        return [item for item in self.results if not item.passed and item.kind == SPEC]

    @property
    def builder_problems(self) -> list[Result]:
        return [item for item in self.results if not item.passed and item.kind == BUILDER]

    def trace_lines(self) -> list[tuple[str, str]]:
        lines = []
        for item in self.results:
            text = f"scenario={item.scenario} result={'pass' if item.passed else 'fail'}"
            if not item.passed:
                text += f" kind={item.kind} reason={item.reason}"
            lines.append(("self_check", text[:300]))
        played = max(self.played, len(self.results))
        failed = sum(not item.passed for item in self.results)
        lines.append(("self_check_summary", (
            f"scenarios={played} pass={played - failed} fail={failed} spec={len(self.spec_problems)} "
            f"builder={len(self.builder_problems)} seconds={self.seconds:.1f}"
            + (f" now={self.nows[0]}" if self.nows else "")
            + (f" extra_nows={','.join(self.nows[1:])}" if len(self.nows) > 1 else ""))))
        return lines

    def repair_messages(self) -> list[tuple[str, str]]:
        """(spec path, message) for extraction repair: each names the scenario and the step."""
        messages, seen = [], set()
        for item in self.spec_problems:
            if item.path in seen:  # the same problem at another moment
                continue
            seen.add(item.path)
            messages.append((item.path, f"self-check scenario {item.scenario!r} (step {item.step or '-'}): {item.reason}"))
        return messages


def _expected_pair(spec: PhoneAgentSpec, scenario: Scenario) -> tuple[str, str]:
    if scenario.pair is not None:
        return scenario.pair
    row = next((item for item in spec.outcomes if scenario.expect_state in item.on), None)
    if row is None and scenario.expect_state == "special_tool_failed":
        row = next(item for item in spec.outcomes if "promise_failed" in item.on)
    row = row or next(item for item in spec.outcomes if "default" in item.on)
    return row.outcome, row.reason


def _close_tool(workflow: dict[str, Any], spec: PhoneAgentSpec) -> str:
    closing = spec.closing.data
    for node in workflow["nodes"].values():
        if node.get("node_type") != "api_request" or not node.get("pre_actions"):
            continue
        tool = node["pre_actions"][0]
        properties = tool["function"]["parameters"]["properties"].get("body", {}).get("properties", {})
        if closing["outcome_field"] in properties and closing["reason_field"] in properties:
            return tool["function"]["name"]
    return ""


def play(workflow: dict[str, Any], spec: PhoneAgentSpec, scenario: Scenario, now: str) -> tuple[Simulator, list[str]]:
    """Play ``scenario``; return the simulator and the failed checks."""
    record_tool = _promise_tool(workflow, spec)
    answers = {record_tool if name == RECORD else name: values for name, values in scenario.answers.items()}
    bank = Bank(spec, scenario.products, answers, scenario.identity)
    variables = {"now": now, spec.offer.data.get("today_variable") or "now": now}
    for name in CALL_VARIABLES:
        variables.setdefault(name, "sim-" + name)
    sim = Simulator(workflow, spec, bank, variables)
    failures: list[str] = []
    counts: dict[str, int] = {}
    for action in scenario.actions:
        repeat = MAX_REPEATS if action.get("repeat") else 1
        label = action.get("label", "")
        for _ in range(repeat):
            waiting = sim.advance()
            if waiting == END_CALL:
                break
            if action["kind"] == "say":
                moved = sim.turn(dict(action["vars"]))
                if not moved:
                    failure = f"dead end at {waiting}: the {label} turn has no route"
                    if action.get("spec_path") and not sim.extract_failed:
                        # The step took the spec's own value and still has no route for it.
                        sim.spec_failures.append((action["spec_path"], failure))
                    else:
                        failures.append(failure)
                    break
            elif action["kind"] == "tool":
                sim.tool_turn(dict(action["args"]))
            elif action["kind"] == "special":
                # A path that starts per step has its own entry (``special_<id>_at_<step>``).
                entry = f"{action['node']}_at_{waiting}"
                if not sim.enter_special(entry if entry in sim.globals else action["node"]):
                    break
                for _ in range(3):
                    inside = sim.advance()
                    node = sim.nodes.get(inside, {})
                    if not inside.startswith(action["node"]) or node.get("node_type") != "conversation":
                        break
                    if node.get("tools"):
                        # The model calls the path's tool for the product being discussed.
                        sim.tool_turn({spec.confirmation.data["product_number_field"]: 1})
                    else:
                        # The path asks first (F-055 ask): the customer still wants it.
                        proceed = next((t for t in node.get("transitions", []) if t["target_node"] != PREVIOUS), None)
                        operand = next((c.get("operand") for c in _leaves(proceed["condition"])), None) if proceed else None
                        sim.turn({action["choice_variable"]: operand} if proceed else {})
            counts[label] = counts.get(label, 0) + 1
            # A repeated turn goes on until the call ends or reaches one of its ``until`` steps.
            if action.get("repeat") and (sim.advance() in (END_CALL, *action.get("until", ()))):
                break
        if sim.step == END_CALL:
            break
    final = sim.advance()
    failures.extend(sim.problems)
    if final != END_CALL:
        failures.append(f"the call does not reach {END_CALL}; it waits at {final}")
    for label, expected in scenario.repeats.items():
        if counts.get(label) != expected:
            failures.append(f"{label} turns: {counts.get(label)} (the spec's attempts give {expected})")
    close_tool = _close_tool(workflow, spec)
    closes = [index for index, call in enumerate(bank.calls) if call.tool == close_tool]
    if len(closes) != 1:
        failures.append(f"{len(closes)} close calls (want exactly one)")
    elif closes[0] != len(bank.calls) - 1:
        failures.append(f"close call is not the last tool call ({bank.calls[-1].tool} after it)")
    closing = spec.closing.data
    if closes:
        body = bank.calls[closes[-1]].body
        got = (str(body.get(closing["outcome_field"], "")), str(body.get(closing["reason_field"], "") or ""))
        want = _expected_pair(spec, scenario)
        if got != (want[0], want[1] or ""):
            failures.append(f"closes as {got[0]}/{got[1] or '-'}, the spec gives {want[0]}/{want[1] or '-'}")
    confirmation = spec.confirmation.data
    promises = sorted(
        (str(call.body.get(confirmation["promise_product_id_field"])), float(call.body.get(confirmation["promise_amount_field"]) or 0),
         str(call.body.get(confirmation["promise_date_field"])))
        for call in bank.calls if call.tool == record_tool and call.ok)
    if promises != sorted(scenario.promises):
        failures.append(f"promises {promises}, the spec gives {sorted(scenario.promises)}")
    notes_rule = closing.get("product_notes")
    if scenario.notes is not None and notes_rule:
        notes = sorted((str(call.body.get(notes_rule["product_field"])), str(call.body.get(notes_rule["reason_field"])))
                       for call in bank.calls if call.tool == notes_rule["tool"] and call.ok)
        if notes != scenario.notes:
            failures.append(f"notes {notes}, the spec gives {scenario.notes}")
    if sim.rejected:
        failures.append(f"rejected typed writes {sim.rejected[:3]}")
    if len(sim.spoken_after_turn) > 1:
        failures.append(f"{len(sim.spoken_after_turn)} spoken messages in the closing turn: {sim.spoken_after_turn}")
    return sim, failures


def _leaves(condition: dict[str, Any]) -> list[dict[str, Any]]:
    if "conditions" in condition:
        return [leaf for item in condition["conditions"] for leaf in _leaves(item)]
    return [condition]


def unreached_rows(spec: PhoneAgentSpec, plays: list[Scenario]) -> list[tuple[int, str]]:
    """Non-default outcome rows that no scenario ends with: an ending the call can never write."""
    reached = {_expected_pair(spec, scenario) for scenario in plays}
    rows = []
    for index, item in enumerate(spec.outcomes):
        if item.on or (item.outcome, item.reason) in reached:
            continue  # a mapped call-end state reaches it (states the scenarios do not play included)
        returning = any(path.then != SPECIAL_THEN_CLOSE and path.tool and (path.outcome, path.reason) ==
                        (item.outcome, item.reason) for path in spec.special_paths)
        rows.append((index, f"{item.outcome}/{item.reason or '-'}" + (" (returning path)" if returning else "")))
    return rows


def check_nows(spec: PhoneAgentSpec, now: str) -> list[str]:
    """``now`` plus dates from the spec's own calendar where date rules differ most: the last
    business day before a non-business day (a Friday on a Saturday-Sunday weekend) and the
    business day before a spec holiday (the next one, else the latest listed)."""
    calendar = SpecCalendar(spec, now)
    today, clock = calendar.today, now[10:]
    days = []
    for offset in range(14):
        day = today + datetime.timedelta(days=offset)
        if calendar.is_business(day) and not calendar.is_business(day + datetime.timedelta(days=1)):
            days.append(day)
            break
    holidays = sorted(calendar.holidays)
    holiday = next((day for day in holidays if day > today), holidays[-1] if holidays else None)
    if holiday is not None:
        eve = holiday - datetime.timedelta(days=1)
        for _ in range(14):
            if calendar.is_business(eve):
                days.append(eve)
                break
            eve -= datetime.timedelta(days=1)
    nows = [now]
    for day in days:
        if day.isoformat() + clock not in nows:
            nows.append(day.isoformat() + clock)
    return nows


def _play_all(spec: PhoneAgentSpec, workflow: dict[str, Any], now: str,
              suffix: str = "") -> tuple[list[Result], list[Scenario]]:
    results: list[Result] = []
    try:
        plays = scenarios(spec, now)
    except Exception as exc:  # a spec shape the generator does not know: a builder problem
        return [Result("generate" + suffix, False, BUILDER, f"scenario generation failed: {type(exc).__name__}: {exc}")], []
    for scenario in plays:
        try:
            sim, failures = play(workflow, spec, scenario, now)
            spec_failures = sim.spec_failures
        except Exception as exc:
            failures, spec_failures = [f"simulator error {type(exc).__name__}: {exc}"], []
        name = scenario.id + suffix
        if spec_failures:
            path, failure = spec_failures[0]
            results.append(Result(name, False, SPEC, "; ".join([
                f"the routed value {path} has no route: {failure}", *failures])[:400], path=path, step=scenario.step))
        elif failures:
            results.append(Result(name, False, BUILDER, "; ".join(failures)[:400], step=scenario.step))
        else:
            results.append(Result(name, True, step=scenario.step))
    return results, plays


def run_selfcheck(spec: PhoneAgentSpec, workflow: dict[str, Any], now: str | None = None) -> Report:
    """Play every scenario of ``spec`` on ``workflow``. Never raises.

    With ``now`` given, the scenarios run for that moment only. Without it (the build), they
    run for the build's moment and for ``check_nows``, so a date rule cannot pass or fail by
    the day of the build alone; only the failures of the extra moments are listed."""
    started = time.monotonic()
    nows = [now] if now else [time.strftime("%Y-%m-%dT11:00", time.gmtime())]
    if not now:
        try:
            nows = check_nows(spec, nows[0])
        except Exception:  # an odd calendar: the build's moment only
            pass
    results, plays = _play_all(spec, workflow, nows[0])
    played = len(results)
    for extra in nows[1:]:
        more, more_plays = _play_all(spec, workflow, extra, "@" + extra[:10])
        played += len(more)
        plays += more_plays
        results += [item for item in more if not item.passed]
    for index, label in unreached_rows(spec, plays):
        if "(returning path)" in label:
            # Several products: reached through the notes, which the closing does not derive yet
            # (AB-FRESH risk 5). Known gap, not a repair.
            results.append(Result(f"reach_outcomes[{index}]", False, BUILDER,
                                  f"{label}: only a returning path names it; the closing does not derive it"))
            continue
        results.append(Result(
            f"reach_outcomes[{index}]", False, SPEC,
            f"no call reaches the outcome row {label}: no call-end state, routed value or closing special path "
            "leads to it; add the special path or the state the documents give for this ending",
            path=f"outcomes[{index}]", step="closing"))
        played += 1
    return Report(results, time.monotonic() - started, nows, played)


SelfCheck = Callable[[PhoneAgentSpec], Report]
