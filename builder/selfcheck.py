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
import functools
import json
import re
import time
from typing import Any, Callable

from .callback import (
    CALLBACK_BOOK as CALLBACK_BOOK_STEP, DAY_TEXT, THIRD_PARTY_CLOSE_EXPLICIT, THIRD_PARTY_CLOSE_KIND, TIME_TEXT,
    callback_window,
)
from .offer_check import (
    ACCEPTS_YES, OFFER_ACCEPTS, OFFER_AMOUNT, OFFER_DATE, OFFER_PRODUCT, OFFER_PRODUCT_NAME, OFFER_REFUSED_NAME,
    OFFERS_ACCEPTED, OFFERS_NOTED,
)
from .selfcheck_calendar import SpecCalendar, first_rule
from .goodbye import goodbye_states, unconfirmed_note_reason
from .record_loop import RECORD_PROMISE
from .spec import FRAMEWORK_NONE_VALUE, OPENING_GREETING_VALUE, SPECIAL_THEN_CLOSE, THIRD_PARTY_CUSTOMER_VALUE, PhoneAgentSpec, special_note_pairs
from .tools_from_openapi import CALL_VARIABLES

END_CALL = "end_call"
END_OF_CALL = "end_of_call"   # the step name the ledger gives the platform's end-of-call tools
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
    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        # An allowed module's own lazy import from C (``datetime.strptime`` loads ``_strptime``)
        # also goes through this hook. CPython passes a list as its fromlist; an import
        # statement passes None or a tuple. Only the step's own imports count (T-012).
        internal = isinstance(fromlist, list)
        if name.split(".")[0] not in ALLOWED_IMPORTS and not internal:
            problems.append(f"{where} imports {name} (the platform allows {', '.join(ALLOWED_IMPORTS)})")
        return builtins.__import__(name, globals, locals, fromlist, level)
    return {**names, "__builtins__": {**vars(builtins), "__import__": guarded}}


@functools.lru_cache(maxsize=1024)
def _compiled(code: str) -> Any:
    """Generated code compiled once: every scenario runs the same steps (T-012, time)."""
    return compile(code, "<generated>", "exec")


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
                 answers: dict[str, list[bool]] | None = None, identity: list[bool] | None = None,
                 identity_known: bool = False) -> None:
        self.spec = spec
        self.products = products
        self.answers = {name: list(values) for name, values in (answers or {}).items()}
        self.identity = list(identity or [])
        self.identity_known = identity_known
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
            if self.identity_known:
                # PUB-05 (v19): verified in an earlier session, the bank sent no overall field.
                del data[identity["verified_field"]]
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
        self.spec_failures: list[tuple[str, str]] = []   # (spec path, problem): for repair
        self.offer_passes: list[tuple[Any, Any]] = []      # T-025: handled products after each offer check
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
            exec(_compiled(code_of(self.nodes[key])), _sandbox(self.problems, f"code step {key}", vars=self.vars))
        except Exception as exc:  # generated code must never raise
            self.problems.append(f"code step {key} raised {type(exc).__name__}: {exc}")
        if key == "check_offer":
            self.offer_passes.append((self.vars.get(OFFERS_ACCEPTED), self.vars.get(OFFERS_NOTED)))
        for name, field in self.fields.items():
            if name in self.vars and self.vars[name] != before.get(name) and not fits(self.vars[name], field):
                self.rejected.append((key, name, self.vars[name]))
                if name in before:
                    self.vars[name] = before[name]
                else:
                    del self.vars[name]

    def call_tool(self, tool: dict[str, Any], step: str, args: dict[str, Any] | None = None) -> bool:
        """A tool call (an api step's pre-action, or the model's call with ``args``)."""
        body = self._tool_body(tool)
        body.update(args or {})
        config = {"body": body}
        if tool.get("pre_process_code"):
            try:
                exec(_compiled(tool["pre_process_code"]),
                     _sandbox(self.problems, f"pre-hook of {tool['function']['name']}", vars=self.vars, config=config))
            except Exception as exc:
                self.problems.append(f"pre-hook of {tool['function']['name']} raised {type(exc).__name__}")
        name = tool["function"]["name"]
        result = self.bank.answer(name, config["body"], step)
        if tool.get("post_process_code"):
            try:
                exec(_compiled(tool["post_process_code"]),
                     _sandbox(self.problems, f"post-hook of {name}", result=result, vars=self.vars))
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

    def advance(self, stop_at: str = "") -> str:
        """Walk the passthrough steps until a conversation step waits or the call ends (or,
        with ``stop_at``, until the walk enters that step, which is then not run)."""
        for _ in range(MAX_PASSTHROUGH):
            key = self.step
            if key == END_CALL or key not in self.nodes or key == stop_at:
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
        for name, value in extracted.items():
            field = schema.get(name)
            if field is None or not fits(value, field):
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

    def intent_turn(self, extracted: dict[str, Any], node_key: str) -> str:
        """A turn that both sets the step's fields and matches a special path's intent. The
        platform tries the step's own routes first and the intents only when none holds
        (T-023, seen live in PUB-08). Returns "step", "special", or "" (nothing moved)."""
        key = self.advance()
        if key == END_CALL or key not in self.nodes:
            return ""
        self.spoken_after_turn = []
        self.extract(key, extracted)
        target = self.route(key)
        if target is not None:
            self.path.append(key)
            self.step = self._target(target)
            return "step"
        return "special" if self.enter_special(node_key) else ""

    # -- call-end events (T-012) ---------------------------------------------
    hung_up = False

    def hang_up(self, at: str = "") -> str:
        """The customer hangs up at the waiting step, or (``at``) when the walk enters that
        step (for example while the closing sentence is said). Returns the step."""
        key = self.advance(stop_at=at)
        self.hung_up = True
        return key

    def turn_limit(self) -> bool:
        """The waiting step reaches its turn limit: the platform takes ``max_turn_transition``."""
        key = self.advance()
        target = self.nodes.get(key, {}).get("max_turn_transition")
        if not target:
            self.problems.append(f"{key} has no turn-limit transition")
            return False
        self.spoken_after_turn = []
        self.path.append(key)
        self.step = self._target(target)
        return True

    def leave_special(self) -> bool:
        """At a special-path step that can return (a spoken-only path, or the customer
        declining an ask-first path): take its transition back to the step it came from."""
        key = self.advance()
        back = next((t for t in self.nodes.get(key, {}).get("transitions", []) if t["target_node"] == PREVIOUS), None)
        if back is None:
            self.problems.append(f"{key} has no way back to the step it came from")
            return False
        operand = next((c.get("operand") for c in _leaves(back["condition"]) if c.get("operator") == "equals"), None)
        variable = next((c.get("variable") for c in _leaves(back["condition"]) if c.get("operator") == "equals"), None)
        return self.turn({variable: operand} if variable else {})

    def end_of_call(self, tools: list[dict[str, Any]]) -> None:
        """The call is over: the platform runs every ``end_of_call`` tool once. Its pre-hook
        decides whether to send (an empty URL sends nothing)."""
        for tool in tools:
            if "end_of_call" not in (tool.get("config") or {}).get("alwaysRunsAt", []):
                continue
            name = tool["function"]["name"]
            properties = tool["function"]["parameters"]["properties"]
            config = {"body": self._tool_body(tool), "url": str(properties.get("url", {}).get("default", ""))}
            if tool.get("pre_process_code"):
                try:
                    exec(_compiled(tool["pre_process_code"]),
                         _sandbox(self.problems, f"pre-hook of {name}", vars=self.vars, config=config))
                except Exception as exc:
                    self.problems.append(f"pre-hook of {name} raised {type(exc).__name__}")
            if config.get("url"):
                self.bank.answer(name, config["body"], END_OF_CALL)

    def _tool_body(self, tool: dict[str, Any]) -> dict[str, Any]:
        """The request body before the model's arguments: defaults and ``{{variable}}`` fields."""
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
        return body


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
    callback: tuple[str, ...] | None = None  # T-012: (day, time) booked; () none; None not checked
    identity_known: bool = False            # T-028: the bank verified the customer earlier


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
        own = {pid for pid in [*(written or {}), *failed, *refused] if pid not in promised}
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
        return Notes(sorted(notes), own, {pid for pid in written or {} if pid not in promised})


class Notes(list):
    """Expected notes; ``own`` names the products whose note a special path or a per-product
    refusal or record failure wrote (not the note loop's default reason), T-011."""

    def __init__(self, notes: list[tuple[str, str]], own: set[str], special: set[str] = frozenset()) -> None:
        super().__init__(notes)
        self.own = set(own)
        self.special = set(special)   # T-017: the products a returning special path noted


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
        # T-028 (PUB-05): the bank had verified the customer earlier and sends no overall field.
        result.append(Scenario(
            "identity_known_earlier", [*plan.reach_negotiation(), plan.offer(1, day), plan.confirm()],
            "promise_recorded", one, promises=[plan.promise(one[0], day)],
            notes=notes_for(one, promised=["p1"], state="promise_recorded"), step="identity",
            identity_known=True))
        result.extend(_offer_scenarios(spec, plan, one, notes_for))
        result.extend(_spoken_date_scenarios(spec, plan, one, notes_for))
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
    result.extend(_customer_return_scenarios(spec, plan, one, notes_for))

    # Special paths.
    for path in spec.special_paths:
        result.extend(_special_scenarios(spec, plan, path, one, notes_for))

    # Several products: when the spec has per-product handling.
    if plan.notes or plan.negotiation.get("product_end_values"):
        result.extend(_multi_scenarios(spec, plan, notes_for))
        result.extend(_without_product_field(_multi_scenarios(spec, plan, notes_for)))
        result.extend(_mixed_refusal_scenarios(spec, plan, notes_for))
        result.extend(_product_word_scenarios(spec, plan, notes_for))
    # T-027: a goodbye during the offer talk ends the call within two turns.
    result.extend(_goodbye_scenarios(spec, plan, one, notes_for))
    # T-034: the kit's customer styles (corrects, pieces, talkative, asks_back, in_words).
    result.extend(_style_scenarios(spec, plan, one, notes_for))

    # T-012: call-end states and the other families.
    result.extend(_call_end_scenarios(spec, plan, one, notes_for))
    return result


# Scripted answers name the promise tool by role; ``play`` resolves it on the workflow.
RECORD = "@record"


def _record_tool_name(spec: PhoneAgentSpec) -> str:
    return RECORD


def _promise_tool(workflow: dict[str, Any], spec: PhoneAgentSpec) -> str:
    """The tool of the record loop's api step (F-063)."""
    return _role_tool(workflow, RECORD)


# T-012: scripted answers may name a tool by the api step that calls it.
ACCOUNT, CALLBACK_BOOK = "@account", "@callback"
ROLE_STEPS = {RECORD: RECORD_PROMISE, ACCOUNT: "account", CALLBACK_BOOK: CALLBACK_BOOK_STEP}


def _role_tool(workflow: dict[str, Any], role: str) -> str:
    node = workflow["nodes"].get(ROLE_STEPS[role])
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
    slot = _callback_slot(spec, plan)
    if slot is None:
        return result
    day, said, window = slot
    callback = {"kind": "say", "label": "callback_time", "vars": {DAY_TEXT: day.isoformat(), TIME_TEXT: said}}
    result.append(Scenario("callback_booked", [who, callback], "callback_scheduled", one, step="callback_check",
                           callback=(day.isoformat(), said)))
    if window is not None:
        outside = window["latest"] + 60 if window["latest"] + 60 < 24 * 60 else max(0, window["earliest"] - 60)
        late = {"kind": "say", "label": "callback_time", "repeat": True,
                "vars": {DAY_TEXT: day.isoformat(), TIME_TEXT: f"{outside // 60:02d}:{outside % 60:02d}"}}
        result.append(Scenario("callback_outside", [who, late], "third_party:" + window["outside_close_value"],
                               one, step="callback_check"))
    return result


def _callback_slot(spec, plan) -> tuple[datetime.date, str, dict[str, Any] | None] | None:
    """(day, time said, window) of a callback the spec's window allows; None if none is left today."""
    window = callback_window(spec)
    today = plan.calendar.today
    clock = int(plan.now[11:13] or 0) * 60 + int(plan.now[14:16] or 0) if len(plan.now) >= 16 else 0
    if window is None:
        day, minutes = today + datetime.timedelta(days=1), 12 * 60
    else:
        day = today if window["days_ahead"] == 0 else plan.calendar.add(today, 1, window["day_unit"])
        minutes = window["earliest"] if day > today else max(window["earliest"], clock + 60)
        if minutes > window["latest"]:
            return None
    return day, f"{minutes // 60:02d}:{minutes % 60:02d}", window


def _customer_return_scenarios(spec, plan, one, notes_for) -> list[Scenario]:
    """T-015 (F-069): the third party says they are the customer (or hands the phone over);
    the call goes back to the confirmation question, identity and a normal promise."""
    if not plan.opening.get("third_party_values") or THIRD_PARTY_CUSTOMER_VALUE in plan.third["intent_values"]:
        return []
    day = plan.good_day(one)
    if not day:
        return []
    is_customer = {"kind": "say", "label": "third_party",
                   "vars": {plan.third["intent_variable"]: THIRD_PARTY_CUSTOMER_VALUE}}
    return [Scenario(
        "third_party_is_customer",
        [plan.answer_who("third_party_values"), is_customer, *plan.reach_negotiation(), plan.offer(1, day), plan.confirm()],
        "promise_recorded", one, promises=[plan.promise(one[0], day)],
        notes=notes_for(one, promised=["p1"], state="promise_recorded"), step="third_party")]


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
        # T-016: the same notes rule as the path at its other steps (no products before the account).
        result.append(_closing_case(plan, path, entry, one, notes_for, f"special_{path.id}", before))
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
# T-012: call-end states, callback answers, a revise at the read-back, special paths
# ---------------------------------------------------------------------------

# Words that name no day and no clock time (an unclear callback answer).
UNCLEAR_CALLBACK = "not sure yet"
# Steps before the account is read: the call has no products there, so no notes.
BEFORE_ACCOUNT = ("opening", "identity", "third_party")


def _call_end_scenarios(spec, plan, one, notes_for) -> list[Scenario]:
    return [
        *_hangup_scenarios(spec, plan, one, notes_for),
        *_turn_limit_scenarios(spec, plan, one, notes_for),
        *_account_failed_scenarios(spec, plan, one),
        *_callback_answer_scenarios(spec, plan, one),
        *_relative_callback_scenarios(spec, plan, one),
        *_revise_scenarios(spec, plan, one, notes_for),
        *_two_special_scenarios(spec, plan, one, notes_for),
        *_special_elsewhere_scenarios(spec, plan, one, notes_for),
        *_competing_label_scenarios(spec, plan, one, notes_for),
        *_decline_scenarios(spec, plan, one, notes_for),
    ]


def _hangup_pair(spec: PhoneAgentSpec, verified: bool) -> tuple[str, str]:
    """The row a hang-up writes: the unverified hang-up row before identity passed, then the
    hang-up row, then the default row."""
    for state in ([] if verified else ["hangup_unverified"]) + ["hangup"]:
        row = next((item for item in spec.outcomes if state in item.on), None)
        if row is not None:
            return row.outcome, row.reason
    row = next(item for item in spec.outcomes if "default" in item.on)
    return row.outcome, row.reason


def _hangup_scenarios(spec, plan, one, notes_for) -> list[Scenario]:
    """The customer hangs up; the end-of-call close writes the row. The closing chain (and so
    the note loop) never runs, so notes are not checked, except after a promise, where the
    hang-up comes while the closing sentence is said."""
    hangup = {"kind": "hangup", "label": "hangup"}
    result = [
        Scenario("hangup_opening", [hangup], "hangup_unverified", one,
                 pair=_hangup_pair(spec, False), step="opening"),
        Scenario("hangup_identity", [plan.answer_who("identity_values"), hangup], "hangup_unverified", one,
                 pair=_hangup_pair(spec, False), step="identity"),
        Scenario("hangup_negotiate", [*plan.reach_negotiation(), hangup], "hangup", one,
                 pair=_hangup_pair(spec, True), step="negotiate"),
    ]
    day = plan.good_day(one)
    if day:
        result.append(Scenario(
            "hangup_after_promise", [*plan.reach_negotiation(), plan.offer(1, day), plan.confirm(),
                                     {**hangup, "at": "closing_say"}],
            "promise_recorded", one, promises=[plan.promise(one[0], day)],
            notes=notes_for(one, promised=["p1"], state="promise_recorded"), step="closing_say"))
    return result


def _turn_limit_scenarios(spec, plan, one, notes_for) -> list[Scenario]:
    limit = {"kind": "turn_limit", "label": "turn_limit"}
    return [
        Scenario("turn_limit_opening", [limit], "turn_limit", one,
                 notes=[] if plan.notes else None, step="opening"),
        Scenario("turn_limit_negotiate", [*plan.reach_negotiation(), limit], "turn_limit", one,
                 notes=notes_for(one, state="turn_limit"), step="negotiate"),
    ]


def _account_failed_scenarios(spec, plan, one) -> list[Scenario]:
    # The account read fails: no products are known, so the note loop writes nothing.
    return [Scenario("account_failed", plan.reach_negotiation(), "account_failed", one,
                     answers={ACCOUNT: [False] * 3}, notes=[] if plan.notes else None, step="account")]


def _callback_answer_scenarios(spec, plan, one) -> list[Scenario]:
    """Callback answers other than a clean day and time: unclear, a day without a time, and
    the booking tool failing. With a window, unclear or day-only answers end in giving up."""
    if not plan.opening.get("third_party_values"):
        return []
    slot = _callback_slot(spec, plan)
    if slot is None:
        return []
    day, said, window = slot
    who = plan.answer_who("third_party_values")

    def answer(day_text, time_text, repeat=False):
        return {"kind": "say", "label": "callback_time", "repeat": repeat,
                "vars": {DAY_TEXT: day_text, TIME_TEXT: time_text}}

    booked, slot = answer(day.isoformat(), said), (day.isoformat(), said)
    result = [
        Scenario("callback_unclear_then_booked", [who, answer("", UNCLEAR_CALLBACK), booked],
                 "callback_scheduled", one, step="callback_check", callback=slot),
        # The day named first is kept when the next answer names only the time.
        Scenario("callback_need_time_then_booked", [who, answer(day.isoformat(), ""), answer("", said)],
                 "callback_scheduled", one, step="callback_check", callback=slot),
        Scenario("callback_book_failed", [who, booked], "callback_failed", one,
                 answers={CALLBACK_BOOK: [False] * 3}, step="callback_book", callback=()),
    ]
    if window is not None:
        give_up = "third_party:" + window["outside_close_value"]
        result += [
            Scenario("callback_unclear_give_up", [who, answer("", UNCLEAR_CALLBACK, repeat=True)], give_up, one,
                     step="callback_check", callback=()),
            Scenario("callback_need_time_give_up", [who, answer(day.isoformat(), "", repeat=True)], give_up, one,
                     step="callback_check", callback=()),
        ]
    return result


# T-014 (F-073): relative callback times and the minutes they name (None: not exact, asked
# again). Generic English forms, digits and number words; no brief value.
RELATIVE_CALLBACKS = (
    ("two hours later", 120), ("in 2 hours", 120), ("in an hour", 60), ("half an hour later", 30),
    ("an hour and a half from now", 90), ("in forty five minutes", 45), ("in a couple of hours", None),
    ("in 2 hours 30 minutes", 150), ("two hours thirty minutes later", 150), ("in one hour fifteen", None),
)


def _callback_allowed(spec, plan, day: datetime.date, minutes: int) -> bool:
    """Whether the spec's callback window allows ``day`` at ``minutes`` (written apart from
    the generated callback code)."""
    window = callback_window(spec)
    today = plan.calendar.today
    if window is None:
        return day >= today
    days = [today] + [plan.calendar.add(today, step, window["day_unit"]) for step in range(1, window["days_ahead"] + 1)]
    clock = int(plan.now[11:13]) * 60 + int(plan.now[14:16]) if len(plan.now) >= 16 else None
    if day not in days or not window["earliest"] <= minutes <= window["latest"]:
        return False
    return not (window["after_now"] and day == today and clock is not None and minutes <= clock)


def _relative_callback_scenarios(spec, plan, one) -> list[Scenario]:
    """A relative callback time is counted from ``now``: booked when the window allows it;
    otherwise (or when it is not exact) the person is asked again and names a slot that fits,
    or, with no further asks allowed, the call closes with the window's close value."""
    if not plan.opening.get("third_party_values") or len(plan.now) < 16:
        return []
    slot = _callback_slot(spec, plan)
    window = callback_window(spec)
    who = plan.answer_who("third_party_values")
    clock = int(plan.now[11:13]) * 60 + int(plan.now[14:16])
    phrases = [(words, minutes, "_".join(re.findall(r"[a-z0-9]+", words))) for words, minutes in RELATIVE_CALLBACKS]
    # The window's edge: now + duration on its last minute is booked; one minute later is outside.
    if window is not None and clock < window["latest"]:
        last = window["latest"] - clock
        phrases += [(f"in {last} minutes", last, "window_last_minute"),
                    (f"in {last + 1} minutes", last + 1, "window_one_minute_past")]
    result = []
    for words, minutes, slug in phrases:
        name = "callback_relative_" + slug
        said = {"kind": "say", "label": "callback_time", "vars": {DAY_TEXT: "", TIME_TEXT: words}}
        if minutes is not None:
            day = plan.calendar.today + datetime.timedelta(days=(clock + minutes) // (24 * 60))
            target = (clock + minutes) % (24 * 60)
            if _callback_allowed(spec, plan, day, target):
                result.append(Scenario(name, [who, said], "callback_scheduled", one, step="callback_check",
                                       callback=(day.isoformat(), f"{target // 60:02d}:{target % 60:02d}")))
                continue
            if window is not None and window["max_outside_asks"] == 0:
                result.append(Scenario(name, [who, said], "third_party:" + window["outside_close_value"], one,
                                       step="callback_check", callback=()))
                continue
        if slot is None:
            continue
        day, time_said, _ = slot
        again = {"kind": "say", "label": "callback_time", "vars": {DAY_TEXT: day.isoformat(), TIME_TEXT: time_said}}
        result.append(Scenario(name, [who, said, again], "callback_scheduled", one, step="callback_check",
                               callback=(day.isoformat(), time_said)))
    return result


def _revise_scenarios(spec, plan, one, notes_for) -> list[Scenario]:
    """At the read-back the customer changes the terms, then makes a new offer: only the new
    offer is recorded."""
    confirmation, product = plan.confirmation, one[0]
    values, revise = confirmation["intent_values"], confirmation.get("revise_values") or []
    day = plan.good_day(one)
    if not day or not revise or revise[0] not in values:
        return []
    ask = {"kind": "say", "label": "change_terms",
           "spec_path": f"confirmation.intent_values[{values.index(revise[0])}]",
           "vars": {confirmation["intent_variable"]: revise[0]}}
    other = _another_allowed_day(plan, product, day)
    floor, full = plan.calendar.floor(product), plan.calendar.full(product)
    if other:
        new_offer, promise = plan.offer(1, other), plan.promise(product, other)
    elif 0 < floor < full:
        new_offer, promise = plan.offer(1, day, floor), plan.promise(product, day, floor)
    else:
        return []
    return [Scenario("revise_at_readback", [*plan.reach_negotiation(), plan.offer(1, day), ask, new_offer,
                                            plan.confirm()],
                     "promise_recorded", one, promises=[promise],
                     notes=notes_for(one, promised=["p1"], state="promise_recorded"), step="revise_ask")]


def _another_allowed_day(plan, product, day: str) -> str | None:
    probe, deadline = datetime.date.fromisoformat(day), plan.calendar.deadline(product)
    while probe < deadline:
        probe += datetime.timedelta(days=1)
        if plan.calendar.outcome(probe.isoformat(), product)[1] == "allowed":
            return probe.isoformat()
    return None


def _before(plan, step: str, one) -> list[dict[str, Any]] | None:
    """Turns that bring a call to wait at ``step`` (None: a step the scenarios do not reach)."""
    day = plan.good_day(one)
    if step == "opening":
        return []
    if step == "identity":
        return [plan.answer_who("identity_values")]
    if step == "third_party":
        return [plan.answer_who("third_party_values")] if plan.opening.get("third_party_values") else None
    if step == "negotiate":
        return plan.reach_negotiation()
    if step == "confirm_record" and day:
        return [*plan.reach_negotiation(), plan.offer(1, day)]
    if step == "offer_say":
        late = plan.calendar.deadline(one[0]) + datetime.timedelta(days=5)
        return [*plan.reach_negotiation(), plan.offer(1, late.isoformat())]
    return None


def _enter(path) -> dict[str, Any]:
    from .workflow import special_result_variable
    return {"kind": "special", "label": "special", "node": "special_" + path.id,
            "choice_variable": special_result_variable(path) + "_choice",
            "say_first": path.say.text if path.say_first else ""}


def _closing_case(plan, path, step, one, notes_for, name, before) -> Scenario:
    """A closing path entered at ``step``: its own pair; a note it writes itself counts."""
    reason = (path.tool_args or {}).get((plan.notes or {}).get("reason_field", ""), "")
    written = {"p1": reason} if path.tool and plan.notes and path.tool == plan.notes["tool"] else None
    notes = ([] if plan.notes else None) if step in BEFORE_ACCOUNT else \
        notes_for(one, pair=(path.outcome, path.reason), written=written)
    return Scenario(name, [*before, _enter(path)], "special:" + path.id, one,
                    pair=(path.outcome, path.reason), notes=notes, step=step)


def _two_special_scenarios(spec, plan, one, notes_for) -> list[Scenario]:
    """Two special paths in one call: one that returns (spoken only, or an ask-first path the
    customer declines), then a closing path at the same step."""
    for step in ("negotiate", "confirm_record", "identity", "opening"):
        before = _before(plan, step, one)
        if before is None:
            continue
        here = [path for path in spec.special_paths if step in path.available_in]
        # An ask-first path with on_decline closes on a no (T-023): it does not return.
        first = next((path for path in here if (path.ask and not path.on_decline)
                      or (path.then != SPECIAL_THEN_CLOSE and not path.tool)), None)
        second = next((path for path in here if path.then == SPECIAL_THEN_CLOSE and first is not None
                       and path.id != first.id), None)
        if first and second:
            leave = {"kind": "leave_special", "label": "special_back", "node": "special_" + first.id}
            return [_closing_case(plan, second, step, one, notes_for, f"special_{first.id}_then_{second.id}",
                                  [*before, leave])]
    return []


# Steps where the scenarios can finish a call after a returning path brought it back.
def _finish(plan, step: str, one, path) -> tuple[list[dict[str, Any]], str, dict[str, Any]] | None:
    """(turns, state, Scenario fields) that end the call after a return to ``step``."""
    if step in ("negotiate", "offer_say"):
        return [plan.refuse()], "negotiation:" + plan.refusal_value(), {}
    if path.tool:
        return None  # a returning path with a tool writes for a product: only after negotiation
    if step == "confirm_record":
        day = plan.good_day(one)
        return [plan.confirm()], "promise_recorded", {"promises": [plan.promise(one[0], day)], "promised": ["p1"]}
    if step in ("identity", "opening"):
        turns = [*plan.verify(), plan.refuse()] if step == "identity" else \
            [*plan.reach_negotiation(), plan.refuse()]
        return turns, "negotiation:" + plan.refusal_value(), {}
    if step == "third_party" and plan.third.get("close_values"):
        value = plan.third["close_values"][0]
        return [{"kind": "say", "label": "third_party", "spec_path": "third_party.close_values[0]", "vars": {
            plan.third["intent_variable"]: value, THIRD_PARTY_CLOSE_KIND: THIRD_PARTY_CLOSE_EXPLICIT}}], \
            "third_party:" + value, {"no_products": True}
    return None


def _competing_label(plan, step: str) -> tuple[str, str] | None:
    """(choice field, value) a forced extraction would give a special situation at ``step``:
    the closest refusal (T-023, PUB-08: "I already paid" read as a refusal)."""
    if step == "negotiate":
        return plan.negotiation["intent_variable"], plan.refusal_value()
    if step == "confirm_record":
        values = plan.confirmation.get("revise_values") or [
            value for value in plan.confirmation["intent_values"] if value not in (plan.confirmation.get("confirm_values") or [])]
        return (plan.confirmation["intent_variable"], values[0]) if values else None
    if step == "opening" and plan.opening.get("close_values"):
        return plan.opening["who_answered_variable"], plan.opening["close_values"][0]
    return None


def _competing_label_scenarios(spec, plan, one, notes_for) -> list[Scenario]:
    """T-023 (PUB-08): a closing special path whose turn also gets a step choice. The
    platform tries the step's own routes first, so the path starts only when the choice field
    offers a value that routes nowhere and names the path; the turn then carries that value,
    else the closest refusal (and the step's refusal route wins: caught)."""
    result = []
    for path in spec.special_paths:
        if path.then != SPECIAL_THEN_CLOSE:
            # A returning path at negotiate (a note for one product, then on with the call): the
            # same turn, then the customer refuses (as in _special_scenarios).
            competing = _competing_label(plan, "negotiate")
            if "negotiate" not in path.available_in or competing is None:
                continue
            written = ({"p1": (path.tool_args or {}).get(plan.notes["reason_field"], "")}
                       if path.tool and plan.notes and path.tool == plan.notes["tool"] else None)
            state = "negotiation:" + plan.refusal_value()
            turn = {**_enter(path), "kind": "say_special", "label": "special_topic",
                    "vars": {competing[0]: competing[1]}, "topic": True}
            result.append(Scenario(
                f"special_{path.id}_over_choice_at_negotiate", [*plan.reach_negotiation(), turn, plan.refuse()],
                state, one, step="negotiate",
                notes=notes_for(one, refused=[] if written else ["p1"], state=state, written=written)))
            continue
        for step in ("negotiate", "confirm_record", "opening"):
            competing = _competing_label(plan, step) if step in path.available_in else None
            before = _before(plan, step, one) if competing else None
            if before is None:
                continue
            scenario = _closing_case(plan, path, step, one, notes_for, f"special_{path.id}_over_choice_at_{step}", before)
            scenario.actions[-1] = {**_enter(path), "kind": "say_special", "label": "special_topic",
                                    "vars": {competing[0]: competing[1]}, "topic": True}
            result.append(scenario)
    return result


def _decline_scenarios(spec, plan, one, notes_for) -> list[Scenario]:
    """T-023 (PUB-05): the customer says no to an ask-first path that names its closing path
    for a no (``on_decline``): the call closes on that path, not back at the step."""
    by_id = {path.id: path for path in spec.special_paths}
    result = []
    for path in spec.special_paths:
        target = by_id.get(path.on_decline) if path.ask is not None and path.on_decline else None
        step = next((step for step in ("negotiate", "confirm_record", "identity", "opening")
                     if target is not None and step in path.available_in and _before(plan, step, one) is not None), None)
        if step is None:
            continue
        scenario = _closing_case(plan, target, step, one, notes_for, f"special_{path.id}_declined", _before(plan, step, one))
        scenario.actions[-1] = {**_enter(path), "decline": True}
        result.append(scenario)
    return result


def _special_elsewhere_scenarios(spec, plan, one, notes_for) -> list[Scenario]:
    """Each special path at a step of its ``available_in`` other than the one
    ``_special_scenarios`` plays it at."""
    result = []
    for path in spec.special_paths:
        played = next((step for step in ("negotiate", "identity", "opening", "third_party", "confirm_record")
                       if step in path.available_in), None)
        for step in path.available_in:
            before = _before(plan, step, one) if step != played else None
            if before is None:
                continue
            name = f"special_{path.id}_at_{step}"
            if path.then == SPECIAL_THEN_CLOSE:
                result.append(_closing_case(plan, path, step, one, notes_for, name, before))
                break
            finish = _finish(plan, step, one, path)
            if finish is None:
                continue
            turns, state, extra = finish
            reason = (path.tool_args or {}).get((plan.notes or {}).get("reason_field", ""), "")
            written = {"p1": reason} if path.tool and plan.notes and path.tool == plan.notes["tool"] else None
            promised = extra.get("promised", [])
            refused = [] if written or promised or state.startswith("third_party:") else ["p1"]
            notes = ([] if plan.notes else None) if extra.get("no_products") else \
                notes_for(one, promised=promised, refused=refused, state=state, written=written)
            result.append(Scenario(name, [*before, _enter(path), *turns], state, one,
                                   promises=extra.get("promises", []), notes=notes, step=step))
            break
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
        return scenario.pair  # a closing special path keeps its own pair
    row = next((item for item in spec.outcomes if scenario.expect_state in item.on), None)
    if row is None and scenario.expect_state == "special_tool_failed":
        row = next(item for item in spec.outcomes if "promise_failed" in item.on)
    row = row or next(item for item in spec.outcomes if "default" in item.on)
    return _notes_pair(spec, scenario, (row.outcome, row.reason))


def _notes_pair(spec: PhoneAgentSpec, scenario: Scenario, pair: tuple[str, str]) -> tuple[str, str]:
    """T-011: with ``closing.product_notes.outcome_from_notes``, a call without a promise
    closes on the pair the expected notes give (in account order), when it is a table row."""
    notes = spec.closing.data.get("product_notes") or {}
    rule = notes.get("outcome_from_notes")
    if not rule:
        return _special_notes_pair(spec, scenario, pair)
    if (scenario.promises or not scenario.notes or pair[0] in notes.get("skip_outcomes", [])
            or scenario.expect_state == "special_tool_failed"):
        return pair
    by_product = dict(scenario.notes)
    ids = [str(product[spec.account.data["product_id_field"]]) for product in scenario.products]
    if any(pid not in by_product for pid in ids):
        return pair
    # The same condition as the generated step: some product's own note says more than the
    # provisional close (a plain list, as a test may give, counts every note as own).
    own = getattr(scenario.notes, "own", set(by_product))
    if not any(by_product[pid] != pair[1] for pid in ids if pid in own):
        return pair
    others = [by_product[pid] for pid in ids if by_product[pid] != rule["all_reason"]]
    derived = (rule["otherwise_outcome"], others[0]) if others else (rule["all_outcome"], rule["all_outcome_reason"])
    return derived if derived in {(item.outcome, item.reason) for item in spec.outcomes} else pair


def _special_notes_pair(spec: PhoneAgentSpec, scenario: Scenario, pair: tuple[str, str]) -> tuple[str, str]:
    """T-017: without that block, a call without a promise whose every product a returning
    special path noted, all naming the same row, closes on that row (as the generated step)."""
    pairs = special_note_pairs(spec)
    notes = spec.closing.data.get("product_notes") or {}
    if (not pairs or scenario.promises or not scenario.notes or pair[0] in notes.get("skip_outcomes", [])
            or scenario.expect_state == "special_tool_failed"):
        return pair
    by_product = dict(scenario.notes)
    ids = [str(product[spec.account.data["product_id_field"]]) for product in scenario.products]
    # A plain list, as a test may give, counts every note as written by a special path.
    special = getattr(scenario.notes, "special", set(by_product))
    derived = {pairs.get(by_product.get(pid, "")) if pid in special else None for pid in ids}
    if len(derived) != 1 or None in derived:
        return pair
    return derived.pop()


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


def _callback_failures(workflow: dict[str, Any], bank: Bank, scenario: Scenario) -> list[str]:
    """T-012: the callback the bank booked (its day and time) against the scenario's."""
    if scenario.callback is None:
        return []
    tool = _role_tool(workflow, CALLBACK_BOOK)
    booked = [call.body for call in bank.calls if call.tool == tool and call.ok]
    if not scenario.callback:
        return [f"a callback was booked {booked}, the spec gives none"] if booked else []
    if len(booked) != 1 or not set(scenario.callback) <= {str(value) for value in booked[0].values()}:
        return [f"callbacks booked {booked}, the spec gives one at {' '.join(scenario.callback)}"]
    return []


def _play_call_end(sim: Simulator, action: dict[str, Any]) -> bool:
    """T-012 action kinds: ``hangup`` (optionally ``at`` a step of a passthrough chain),
    ``turn_limit`` and ``leave_special``. False when the scenario's walk stops here."""
    if action["kind"] == "hangup":
        sim.hang_up(action.get("at", ""))
        return False
    if action["kind"] == "turn_limit":
        return sim.turn_limit()
    if action["kind"] == "leave_special":
        if not sim.enter_special(_special_entry(sim, action["node"])):
            return False
        return sim.leave_special()
    if action["kind"] == "goodbye":
        return _play_goodbye(sim, action)
    sim.problems.append(f"unknown scenario action {action['kind']!r}")
    return False


def _topic_choice(sim: Simulator, step: str, entry: str, said: dict[str, Any]) -> dict[str, Any]:
    """The extraction follows the field's description: when the step's choice field offers the
    special-topic value and names this path's situation, the turn carries that value."""
    from .workflow import SPECIAL_TOPIC_VALUE

    when = str(sim.globals.get(entry, {}).get("description", "")).rstrip(".")
    for field in sim.nodes.get(step, {}).get("extraction_schema") or []:
        if field.get("name") in said and SPECIAL_TOPIC_VALUE in (field.get("enum_values") or []) \
                and when and when in field.get("description", ""):
            return {**said, field["name"]: SPECIAL_TOPIC_VALUE}
    return said


def _inside_special(sim: Simulator, spec: PhoneAgentSpec, action: dict[str, Any]) -> None:
    """The customer's turns inside a special path: the model fills its tool for the product
    being discussed, or the customer answers its question (go ahead, or ``decline``)."""
    from .workflow import SPECIAL_PROCEED, SPECIAL_STAY

    for _ in range(3):
        inside = sim.advance()
        node = sim.nodes.get(inside, {})
        if not inside.startswith(action["node"]) or node.get("node_type") != "conversation":
            return
        if node.get("tools"):
            sim.tool_turn({spec.confirmation.data["product_number_field"]: action.get("number", 1)})
            continue
        if not any(field.get("name") == action.get("choice_variable") for field in node.get("extraction_schema") or []):
            sim.turn({})  # a spoken-only path: its line, then back
            continue
        # The path asks first (F-055 ask). T-023: the answer is read by its operand, since a no
        # may close the call (on_decline) instead of going back.
        said = " ".join(str(part) for part in ((node.get("on_enter") or {}).get("text"), node.get("task_message")) if part)
        if action.get("say_first") and action["say_first"].strip() not in said:
            # T-028 (PUB-05): the line (a sympathy sentence) comes before the question.
            sim.problems.append(f"{inside} asks before saying {action['say_first']!r}")
        wanted = SPECIAL_STAY if action.get("decline") else SPECIAL_PROCEED
        operands = {c.get("operand") for t in node.get("transitions", []) for c in _leaves(t["condition"])}
        if wanted not in operands:
            sim.problems.append(f"{inside} has no route for the answer {wanted!r}")
            return
        if not sim.turn({action["choice_variable"]: wanted}):
            return


def _special_entry(sim: Simulator, node: str) -> str:
    """A path that starts per step has its own entry (``special_<id>_at_<step>``)."""
    entry = f"{node}_at_{sim.advance()}"
    return entry if entry in sim.globals else node


def play(workflow: dict[str, Any], spec: PhoneAgentSpec, scenario: Scenario, now: str) -> tuple[Simulator, list[str]]:
    """Play ``scenario``; return the simulator and the failed checks."""
    record_tool = _promise_tool(workflow, spec)
    answers = {_role_tool(workflow, name) if name in ROLE_STEPS else name: values
               for name, values in scenario.answers.items()}
    bank = Bank(spec, scenario.products, answers, scenario.identity, scenario.identity_known)
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
            waiting = sim.advance(stop_at=action.get("at", ""))
            if waiting == END_CALL:
                break
            if action["kind"] == "say" and action.get("stays"):
                # T-034: a turn that answers nothing (a question back) keeps the step.
                if sim.turn(dict(action["vars"])):
                    failures.append(f"the {label} turn at {waiting} moved the call to {sim.step}; a turn "
                                    "that answers nothing must keep the step")
                    break
            elif action["kind"] == "say":
                moved = sim.turn(dict(action["vars"]))
                if not moved:
                    failure = f"dead end at {waiting}: the {label} turn has no route"
                    # The builder renders a route for every spec value, so a lost route is a
                    # builder fault unless the spec's own lists disagree (re-review note A).
                    clash = route_inconsistency(spec, action["spec_path"]) if action.get("spec_path") else ""
                    if clash:
                        sim.spec_failures.append((action["spec_path"], f"{failure}: {clash}"))
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
                _inside_special(sim, spec, action)
            elif action["kind"] == "say_special":
                # T-023: the turn sets the step's choice field and matches the path's intent.
                entry = f"{action['node']}_at_{waiting}"
                entry = entry if entry in sim.globals else action["node"]
                said = dict(action["vars"])
                if action.get("topic"):
                    said = _topic_choice(sim, waiting, entry, said)
                moved = sim.intent_turn(said, entry)
                if moved == "step":
                    failures.append(f"at {waiting} the step's own route takes the turn {action['vars']}, so "
                                    f"{action['node']} never starts (the platform tries intents last)")
                    break
                if not moved:
                    break
                _inside_special(sim, spec, action)
            elif not _play_call_end(sim, action):
                break
            counts[label] = counts.get(label, 0) + 1
            # A repeated turn goes on until the call ends or reaches one of its ``until`` steps.
            if action.get("repeat") and (sim.advance() in (END_CALL, *action.get("until", ()))):
                break
        if sim.step == END_CALL or sim.hung_up:
            break
    final = END_CALL if sim.hung_up else sim.advance()
    sim.end_of_call(workflow.get("tools") or [])
    failures.extend(sim.problems)
    failures.extend(_offer_loop_failures(sim))
    if final != END_CALL:
        failures.append(f"the call does not reach {END_CALL}; it waits at {final}")
    for label, expected in scenario.repeats.items():
        if counts.get(label) != expected:
            failures.append(f"{label} turns: {counts.get(label)} (the spec's attempts give {expected})")
    # The end-of-call close (a hang-up) writes the same ledger row as the closing chain's call.
    close_tools = {_close_tool(workflow, spec), *(call.tool for call in bank.calls if call.step == END_OF_CALL)}
    closes = [index for index, call in enumerate(bank.calls) if call.tool in close_tools]
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
    failures.extend(_callback_failures(workflow, bank, scenario))
    failures.extend(accepted_refusal_notes(sim, spec, scenario.products))
    if sim.rejected:
        failures.append(f"rejected typed writes {sim.rejected[:3]}")
    if len(sim.spoken_after_turn) > 1:
        failures.append(f"{len(sim.spoken_after_turn)} spoken messages in the closing turn: {sim.spoken_after_turn}")
    return sim, failures


# Per section: the list of every value the step extracts, and the lists that route a value.
# ``product_end_values`` and ``attempt_values`` mark values of a route list, so they may overlap.
_VALUE_LISTS = {
    "opening": ("who_answered_options", ("identity_values", "third_party_values", "stay_values", "close_values")),
    "negotiation": ("intent_values", ("confirm_values", "close_values")),
    "third_party": ("intent_values", ("close_values",)),
    "confirmation": ("intent_values", ("revise_values",)),
}


def route_inconsistency(spec: PhoneAgentSpec, spec_path: str) -> str:
    """Why the spec's own lists disagree about the routed value at ``spec_path`` ("" if not):
    the value is routed but not among the values the step extracts, or two route lists of the
    section both name it."""
    section, _, rest = spec_path.partition(".")
    key, _, index = rest.partition("[")
    if section not in _VALUE_LISTS:
        return ""
    data = getattr(spec, section).data
    try:
        value = data[key][int(index.rstrip("]"))]
    except (KeyError, IndexError, ValueError, TypeError):
        return ""
    options, routes = _VALUE_LISTS[section]
    if key != options and value not in (data.get(options) or []):
        return f"{value!r} is routed by {section}.{key} but missing from {section}.{options}"
    named = [name for name in routes if value in (data.get(name) or [])]
    if len(named) > 1:
        return f"{value!r} is in two route lists: {', '.join(f'{section}.{name}' for name in named)}"
    return ""


def _leaves(condition: dict[str, Any]) -> list[dict[str, Any]]:
    if "conditions" in condition:
        return [leaf for item in condition["conditions"] for leaf in _leaves(item)]
    return [condition]


# T-012: call-end states the scenarios play (``_call_end_scenarios``). A row mapped only by
# these must be reached by a played call, not just counted.
PLAYED_CALL_END_STATES = ("hangup", "hangup_unverified", "turn_limit", "account_failed", "callback_failed")


def unreached_rows(spec: PhoneAgentSpec, plays: list[Scenario]) -> list[tuple[int, str]]:
    """Non-default outcome rows that no scenario ends with: an ending the call can never write."""
    reached = {_expected_pair(spec, scenario) for scenario in plays}
    rows = []
    for index, item in enumerate(spec.outcomes):
        if (item.outcome, item.reason) in reached or "default" in item.on:
            continue
        if set(item.on) - set(PLAYED_CALL_END_STATES):
            continue  # a mapped call-end state the scenarios do not play reaches it
        if item.on:
            # T-012: these states are played, so the row must really be reached.
            rows.append((index, f"{item.outcome}/{item.reason or '-'} (state not played: {', '.join(item.on)})"))
            continue
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


def shadowed_intent_steps(spec: PhoneAgentSpec, workflow: dict[str, Any]) -> list[tuple[str, str]]:
    """(step, problem) for each conversation step where special paths start by intent but its
    choice field has no value that matches none of the step's routes and names their
    situations (T-023, PUB-08). The platform tries the step's routes first, so a forced
    choice hides the paths."""
    from .workflow import SPECIAL_TOPIC_VALUE, choice_variables

    choices = choice_variables(spec)
    globals_ = workflow.get("global_nodes", {})
    problems = []
    for key, node in workflow.get("nodes", {}).items():
        starts = [name for name, other in globals_.items()
                  if (other.get("condition") or {}).get("operator") == "matches_intent"
                  and key not in (other.get("excluded_nodes") or [])]
        routed = {leaf.get("variable") for transition in node.get("transitions", [])
                  for leaf in _leaves(transition.get("condition") or {})}
        fields = [field for field in node.get("extraction_schema") or []
                  if field.get("name") in choices and field["name"] in routed]
        if node.get("node_type") != "conversation" or not starts or not fields:
            continue
        whens = [str(globals_[name].get("description", "")).rstrip(".") for name in starts]
        for field in fields:
            value = SPECIAL_TOPIC_VALUE if SPECIAL_TOPIC_VALUE in (field.get("enum_values") or []) else None
            taken = value is not None and any(
                not t.get("is_tool_call") and holds(t["condition"], {field["name"]: value})
                for t in node.get("transitions", []))
            missing = [when for when in whens if when not in field.get("description", "")]
            if value is None or taken or missing:
                problems.append((key, (
                    f"special paths start here by intent ({', '.join(sorted(starts)[:4])}), but the choice "
                    f"{field['name']} has no value that routes nowhere and names them"
                    + (f" (a step route takes {value!r})" if taken else "")
                    + (f" (not named: {missing[0]!r})" if missing and value else "")
                    + "; a forced choice hides the paths, since the platform tries the step's routes first")))
    return problems


def global_always_exits(workflow: dict[str, Any]) -> list[tuple[str, str]]:
    """(global step, problem) for each global step that leaves by an ``always`` transition
    (T-028, PUB-08). From a global step the platform tried the other paths' intents before
    that exit, so two paths matching the same words looped without a word."""
    problems = []
    for key, node in workflow.get("global_nodes", {}).items():
        for transition in node.get("transitions") or []:
            if (transition.get("condition") or {}).get("operator") == "always":
                problems.append((key, (
                    f"global step {key} leaves to {transition.get('target_node')} by 'always'; the platform "
                    "tries the other special paths' intents before it, so two paths can hand the call "
                    "back and forth without speaking")))
    return problems


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
    try:
        shadowed = shadowed_intent_steps(spec, workflow)
    except Exception as exc:  # a render shape the check does not know
        shadowed = [("-", f"check failed: {type(exc).__name__}: {exc}")]
    for step, problem in shadowed:
        results.append(Result(f"intent_shadow[{step}]", False, BUILDER, problem, step=step))
        played += 1
    try:
        exits = global_always_exits(workflow)
    except Exception as exc:  # a render shape the check does not know
        exits = [("-", f"check failed: {type(exc).__name__}: {exc}")]
    for step, problem in exits:
        results.append(Result(f"global_exit[{step}]", False, BUILDER, problem, step=step))
        played += 1
    try:
        from .goodbye import goodbye_exit_gaps
        stalls = goodbye_exit_gaps(workflow)
    except Exception as exc:  # a render shape the check does not know
        stalls = [("-", f"check failed: {type(exc).__name__}: {exc}")]
    for step, problem in stalls:
        results.append(Result(f"goodbye_exit[{step}]", False, BUILDER, problem, step=step))
        played += 1
    try:
        claims = recorded_claim_gaps(workflow)
    except Exception as exc:  # a render shape the check does not know
        claims = [("-", f"check failed: {type(exc).__name__}: {exc}")]
    for step, problem in claims:
        results.append(Result(f"recorded_claim[{step}]", False, BUILDER, problem, step=step))
        played += 1
    try:
        cycles = sandbox_down_gaps(workflow)
    except Exception as exc:  # a render shape the check does not know
        cycles = [("-", f"check failed: {type(exc).__name__}: {exc}")]
    for step, problem in cycles:
        results.append(Result(f"code_cycle[{step}]", False, BUILDER, problem, step=step))
        played += 1
    for index, label in unreached_rows(spec, plays):
        if "(returning path)" in label:
            # Several products: reached through the notes, which the closing does not derive yet
            # (AB-FRESH risk 5). Known gap, not a repair.
            results.append(Result(f"reach_outcomes[{index}]", False, BUILDER,
                                  f"{label}: only a returning path names it; the closing does not derive it"))
            continue
        if "(state not played" in label:
            # T-012: the self-check could not play the state here (a scenario limit, not the spec's).
            results.append(Result(f"reach_outcomes[{index}]", False, BUILDER,
                                  f"{label}: no scenario played this call-end state, so the row is unchecked"))
            continue
        results.append(Result(
            f"reach_outcomes[{index}]", False, SPEC,
            f"no call reaches the outcome row {label}: no call-end state, routed value or closing special path "
            "leads to it; add the special path or the state the documents give for this ending",
            path=f"outcomes[{index}]", step="closing"))
        played += 1
    return Report(results, time.monotonic() - started, nows, played)


# ---------------------------------------------------------------------------
# Routing walks for single decisions (T-012: the tests' walkers, moved here)
# ---------------------------------------------------------------------------

def follow(workflow: dict[str, Any], key: str, variables: dict[str, Any], stop: tuple[str, ...] = ("closing",),
           limit: int = 20) -> str:
    """Route from ``key`` with the given variables and no customer turn: run code steps (in
    the platform sandbox), take the first transition that holds, and stop at a ``stop`` step
    or where no transition holds (the step waits). Raises on a code error, an import the
    platform does not allow, or a routing loop."""
    every = {**workflow["nodes"], **workflow.get("global_nodes", {})}
    problems: list[str] = []
    for _ in range(limit):
        if key in stop:
            return key
        node = every[key]
        if node["node_type"] == "code":
            exec(_compiled(code_of(node)), _sandbox(problems, f"code step {key}", vars=variables))
            if problems:
                raise RuntimeError(problems[0])
        target = next((t["target_node"] for t in node.get("transitions", [])
                       if not t.get("is_tool_call") and holds(t["condition"], variables)), None)
        if target is None:
            return key
        key = target
    raise RuntimeError(f"routing loop from {key}")


# The sentence of SPECIAL_CLOSE_TOOL_TASK_TEMPLATE that keeps a closing tool turn silent.
SILENT_TOOL_RULE = "When you call the tool, say nothing before or after it"


def _speaks_on_entry(node: dict[str, Any]) -> bool:
    """A conversation step without ``on_enter`` speaks: the default entry is ``llm``."""
    if node.get("node_type") == "conversation" and "on_enter" not in node:
        return True
    return node.get("on_enter", {}).get("type") in SPEAKING


def spoken_per_turn(workflow: dict[str, Any], start: str, within: tuple[str, ...]) -> tuple[int, bool]:
    """Every route from ``start`` through steps whose names start with one of ``within``:
    (most speaking steps in one customer turn, whether ``end_call`` is reached).

    A conversation step either speaks and waits for the customer (a new turn starts after
    it), or, when it has tools, routes on the tool result in the same turn; it is silent then
    only if its task says so (``SILENT_TOOL_RULE``). Code and api steps are passthrough."""
    every = {**workflow["nodes"], **workflow.get("global_nodes", {})}
    worst, reached, seen = 0, False, set()
    todo = [(start, 0)]
    while todo:
        key, count = todo.pop()
        if (key, count) in seen or key not in every or not key.startswith(within):
            continue
        seen.add((key, count))
        if key == END_CALL:
            reached = True
            continue
        node = every[key]
        targets = [t["target_node"] for t in node.get("transitions", [])]
        if node.get("node_type") == "conversation":
            worst = max(worst, count + _speaks_on_entry(node))
            todo.extend((target, 0) for target in [*targets, node.get("max_turn_transition")] if target)
            if node.get("tools"):
                spoken = count + (0 if SILENT_TOOL_RULE in node.get("task_message", "") else 1)
                worst = max(worst, spoken)
                todo.extend((target, spoken) for target in targets)
            continue
        spoken = count + _speaks_on_entry(node)
        worst = max(worst, spoken)
        todo.extend((target, spoken) for target in [*targets, node.get("passthrough_default_transition")] if target)
    return worst, reached


SelfCheck = Callable[[PhoneAgentSpec], Report]


# ---------------------------------------------------------------------------
# T-022 (F-076): dates said in words, and a turn without a readable date
# ---------------------------------------------------------------------------

SPOKEN_UNITS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
                "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth", "sixteenth", "seventeenth",
                "eighteenth", "nineteenth"]
SPOKEN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                 "November", "December"]
# A date answer the offer check cannot read: no day, no weekday, no month.
UNREADABLE_DATE = "when my salary comes in"


def spoken_ordinal(number: int) -> str:
    """1 -> "first", 23 -> "twenty-third", 30 -> "thirtieth"."""
    if number < 20:
        return SPOKEN_UNITS[number - 1]
    tens = {2: "twenty", 3: "thirty"}[number // 10]
    if number % 10 == 0:
        return tens[:-1] + "ieth"
    return tens + "-" + SPOKEN_UNITS[number % 10 - 1]


def digit_ordinal(number: int) -> str:
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def spoken_date_forms(day: datetime.date) -> dict[str, str]:
    """The ways a customer says ``day`` that the offer check must read (PUB-04, asks_back)."""
    month = SPOKEN_MONTHS[day.month - 1]
    return {
        "word_ordinal": f"the {spoken_ordinal(day.day)} of {month}",
        "word_ordinal_capital": f"{spoken_ordinal(day.day).capitalize()} of {month}",
        "digit_ordinal": f"{digit_ordinal(day.day)} of {month}",
        "month_first": f"{month} {digit_ordinal(day.day)}",
        "month_the_word": f"{month} the {spoken_ordinal(day.day).replace('-', ' ')}",
        # T-027 (PUB-07): a weekday and the day in words, no month ("Monday the twenty sixth").
        "weekday_the_word": f"{day.strftime('%A')} the {spoken_ordinal(day.day).replace('-', ' ')}",
    }


def _spoken_date_scenarios(spec, plan, one, notes_for) -> list[Scenario]:
    """T-022: a good day said in words is promised on that day; an answer without a readable
    date gets the latest allowed date proposed, and a plain yes takes it."""
    day = plan.good_day(one)
    if not day:
        return []
    product = one[0]
    result = []
    from .language import language_code, spoken_date_forms_for
    forms = {**spoken_date_forms(datetime.date.fromisoformat(day)),
             **spoken_date_forms_for(language_code(spec.agent.language), datetime.date.fromisoformat(day))}
    for name, phrase in forms.items():  # T-041: plus the call language's own forms
        result.append(Scenario(
            f"spoken_date_{name}", [*plan.reach_negotiation(), plan.offer(1, phrase), plan.confirm()],
            "promise_recorded", one, promises=[plan.promise(product, day)],
            notes=notes_for(one, promised=["p1"], state="promise_recorded"), step="check_offer"))
    latest, _ = plan.calendar.outcome(plan.calendar.deadline(product).isoformat(), product)
    result.append(Scenario(
        "spoken_date_unreadable_then_yes",
        [*plan.reach_negotiation(), plan.offer(1, UNREADABLE_DATE), plan.accept(1), plan.confirm()],
        "promise_recorded", one, promises=[plan.promise(product, latest.isoformat())],
        notes=notes_for(one, promised=["p1"], state="promise_recorded"), step="check_offer"))
    return result


# ---------------------------------------------------------------------------
# T-025: fields only a model fills stay empty; offer checks that go nowhere
# ---------------------------------------------------------------------------

# Offer checks in a row that handle no product: more is a loop (check_offer <-> offer_say).
NO_PROGRESS_PASSES = 3


def _without_product_field(scenarios: list[Scenario]) -> list[Scenario]:
    """The same calls with the product list number left empty, as the live extractor leaves
    it (T-024: it never filled it): the ledger must not change."""
    result = []
    for scenario in scenarios:
        actions = [{**action, "vars": {name: value for name, value in action["vars"].items() if name != OFFER_PRODUCT}}
                   if action.get("kind") == "say" and OFFER_PRODUCT in action.get("vars", {}) else action
                   for action in scenario.actions]
        if actions != scenario.actions:
            result.append(dataclasses.replace(scenario, id=scenario.id + "_no_product_field", actions=actions))
    return result


def _offer_loop_failures(sim: Simulator) -> list[str]:
    """A run of offer checks that changes neither the accepted offers nor the noted products."""
    run = longest = 0
    previous = None
    for snapshot in sim.offer_passes:
        run = run + 1 if snapshot == previous else 1
        longest = max(longest, run)
        previous = snapshot
    if longest > NO_PROGRESS_PASSES:
        return [f"loop: {longest} offer checks in a row handle no product (check_offer <-> offer_say)"]
    return []


# ---------------------------------------------------------------------------
# T-027 (PUB-12): a goodbye in the offer talk, products refused by name, no false "recorded"
# ---------------------------------------------------------------------------

GOODBYE_STEP = "customer_ends_call"
# Customer turns from the first goodbye to the end of the call (CTO addendum, item 6).
GOODBYE_TURNS = 2


def _play_goodbye(sim: Simulator, action: dict[str, Any]) -> bool:
    """The customer only says goodbye: the extraction gives the step's choice field the value
    that routes nowhere (its description names the goodbye), so the global step starts."""
    from .goodbye import CUSTOMER_GOODBYE, GOODBYE_VALUE
    from .workflow import choice_variables

    if action.get("enter") and not sim.enter_special(_special_entry(sim, action["enter"])):
        return False
    waiting = sim.advance()
    # T-029: a global conversation step leaves by a choice value of its own.
    own = [leaf.get("variable") for transition in sim.nodes.get(waiting, {}).get("transitions") or []
           if transition.get("target_node") == CUSTOMER_GOODBYE for leaf in _leaves(transition.get("condition") or {})]
    if own:
        if not sim.turn({own[0]: GOODBYE_VALUE}):
            sim.problems.append(f"at {waiting} the goodbye value has no route")
            return False
        return True
    names = choice_variables(sim.spec)
    said = {field["name"]: FRAMEWORK_NONE_VALUE for field in sim.nodes.get(waiting, {}).get("extraction_schema") or []
            if field.get("name") in names}
    if GOODBYE_STEP not in sim.globals:
        sim.problems.append(f"no step catches a goodbye at {waiting}")
        return False
    moved = sim.intent_turn(_topic_choice(sim, waiting, GOODBYE_STEP, said), GOODBYE_STEP)
    if moved == "step":
        sim.problems.append(f"at {waiting} a step route takes the goodbye, so the call goes on")
        return False
    return bool(moved)


def _goodbye(label: str = "goodbye") -> dict[str, Any]:
    return {"kind": "goodbye", "label": label, "repeat": True}


def _goodbye_scenarios(spec, plan, one, notes_for) -> list[Scenario]:
    """A goodbye at the offer step closes the call; with an accepted offer the read-back is
    said once, and a second goodbye or a yes records it (T-031). T-029: a
    goodbye at the opening, the identity step, the third party and a special-path question."""
    from .goodbye import goodbye_states

    after, before, third_state = goodbye_states(spec)
    result = [
        Scenario("goodbye_opening", [_goodbye()], before, one, repeats={"goodbye": 1}, step="opening"),
        Scenario("goodbye_identity", [plan.answer_who("identity_values"), _goodbye()], before, one,
                 repeats={"goodbye": 1}, step="identity"),
    ]
    if plan.opening.get("third_party_values"):
        result.append(Scenario("goodbye_third_party", [plan.answer_who("third_party_values"), _goodbye()],
                               third_state, one, repeats={"goodbye": 1}, step="third_party"))
    for path in spec.special_paths:
        if path.ask is not None:
            result.append(Scenario(
                f"goodbye_special_{path.id}", [*plan.reach_negotiation(),
                                               {**_goodbye(), "repeat": False, "enter": "special_" + path.id}],
                after, one, notes=notes_for(one, state=after), step="special_" + path.id))
    result += [Scenario("goodbye_negotiate", [*plan.reach_negotiation(), _goodbye()], after, one,
                       notes=notes_for(one, state=after), repeats={"goodbye": 1}, step="negotiate")]
    day = plan.good_day(one)
    if day:
        # T-037 (CTO): a goodbye at the read-back is not a yes: nothing is recorded.
        state, notes = _unconfirmed_close(spec, one, notes_for, "p1")
        result.append(Scenario(
            "goodbye_at_readback", [*plan.reach_negotiation(), plan.offer(1, day), _goodbye()], state,
            one, promises=[], notes=notes, repeats={"goodbye": GOODBYE_TURNS}, step="confirm_record"))
    if plan.notes or plan.negotiation.get("product_end_values"):
        products = synthetic_products(spec, 3)
        day = plan.good_day(products)
        if day:
            first = {**plan.offer(1, day), "vars": {OFFER_DATE: day, OFFER_PRODUCT_NAME: "the first one"}}
            result.append(Scenario(
                "goodbye_after_one_offer", [*plan.reach_negotiation(), first, {**_goodbye(), "repeat": False},
                                            plan.confirm()],
                "promise_recorded", products, promises=[plan.promise(products[0], day)],
                notes=notes_for(products, promised=["p1"], state="promise_recorded"), step="offer_say"))
    result += _goodbye_accepted_scenarios(spec, plan, notes_for)
    return result


def _attempts(spec: PhoneAgentSpec, product: dict[str, Any]) -> int:
    """Persuasion attempts the spec gives this product (0 without a rule)."""
    rule = first_rule(spec.offer.data.get("persuasion_attempts") or [], product)
    return int(rule.get("value") or 0) if rule and spec.offer.data.get("persuasion_attempts") else 0


def _mixed_refusal_scenarios(spec, plan, notes_for) -> list[Scenario]:
    """One product paid and the others refused in the same turn ("product A tomorrow, but not
    the others"); and a product refused by name while another is under discussion. Each
    refusal counts for the product the words name."""
    if not plan.negotiation.get("product_end_values"):
        return []
    products = synthetic_products(spec, 3)
    day = plan.good_day(products)
    if not day:
        return []
    result = []
    mixed = {"kind": "say", "label": "offer", "vars": {
        OFFER_DATE: day, OFFER_PRODUCT_NAME: "the first one", OFFER_REFUSED_NAME: "the others"}}
    more = sum(_attempts(spec, product) for product in products[1:])
    turns = [mixed, *([{**plan.refuse(), "until": ("confirm_record",)}] if more else []), plan.confirm()]
    result.append(Scenario(
        "multi_pay_one_refuse_rest", [*plan.reach_negotiation(), *turns], "promise_recorded", products,
        promises=[plan.promise(products[0], day)],
        notes=notes_for(products, promised=["p1"], refused=["p2", "p3"], state="promise_recorded"),
        repeats={"refuse": more} if more else {}, step="product_refusal"))
    named = {**plan.refuse(label="refuse_third"), "repeat": False,
             "vars": {**plan.refuse()["vars"], OFFER_PRODUCT_NAME: "the third one"}}
    first = {**plan.offer(1, day), "vars": {OFFER_DATE: day, OFFER_PRODUCT_NAME: "the first one"}}
    second = {**plan.offer(2, day), "vars": {OFFER_DATE: day, OFFER_PRODUCT_NAME: "the second one"}}
    refusals = [named] * (_attempts(spec, products[2]) + 1)
    result.append(Scenario(
        "multi_refuse_named", [*plan.reach_negotiation(), first, *refusals, second, plan.confirm()],
        "promise_recorded", products, promises=[plan.promise(products[0], day), plan.promise(products[1], day)],
        notes=notes_for(products, promised=["p1", "p2"], refused=["p3"], state="promise_recorded"),
        step="product_refusal"))
    return result


def _product_word_scenarios(spec, plan, notes_for) -> list[Scenario]:
    """T-031: the customer names products in other words than the full kind: one kind word
    ("my <word>"), a shared kind word in the plural ("the <word>s") or after "both", and words
    that name no product (one question, never the product under discussion). Each turn pays the
    products the words name and refuses the others; the promises show which products the words
    were matched to."""
    account = spec.account.data
    kind_field = account.get("product_kind_field")
    if not kind_field or not plan.negotiation.get("product_end_values"):
        return []
    products = synthetic_products(spec, 3)
    day = plan.good_day(products)
    if not day or not all(product.get(kind_field) for product in products):
        return []
    parts = [[word for word in re.split(r"[^a-z0-9]+", str(product[kind_field]).lower()) if len(word) >= 3]
             for product in products]
    numbers = range(1, len(products) + 1)
    owners = {word: [index for index in numbers if word in parts[index - 1]] for words in parts for word in words}
    cases = []
    unique = [(word, found[0]) for word, found in owners.items() if len(found) == 1]
    # A product past the first, so a default to the product under discussion shows.
    unique.sort(key=lambda item: -item[1])
    if unique:
        word, number = unique[0]
        cases.append(("kind_word", [], "my " + word, "the others", [number]))
    shared = [(word, found) for word, found in owners.items() if 1 < len(found) < len(products)]
    if shared:
        word, found = shared[0]
        cases.append(("plural", [], "the " + word + "s", "the others", found))
        if len(found) == 2:
            cases.append(("both_kind", [], "both " + word + "s", "the others", found))
        if unique and unique[0][1] not in found:
            cases.append(("refused_plural", [], "my " + unique[0][0], "the " + word + "s", [unique[0][1]]))
    unknown = {"kind": "say", "label": "unknown_product", "vars": {OFFER_DATE: day, OFFER_PRODUCT_NAME: "the unlisted one"}}
    cases.append(("unknown_name", [unknown], "the third one", "the others", [len(products)]))
    result = []
    for name, before, paying, refused, paid in cases:
        turn = {"kind": "say", "label": "offer", "vars": {
            OFFER_DATE: day, OFFER_PRODUCT_NAME: paying, OFFER_REFUSED_NAME: refused}}
        rest = [index for index in numbers if index not in paid]
        more = sum(_attempts(spec, products[index - 1]) for index in rest)
        turns = [*before, turn, *([{**plan.refuse(), "until": ("confirm_record",)}] if more else []), plan.confirm()]
        ids = [str(products[index - 1][account["product_id_field"]]) for index in paid]
        refused_ids = [str(products[index - 1][account["product_id_field"]]) for index in rest]
        result.append(Scenario(
            "product_words_" + name, [*plan.reach_negotiation(), *turns], "promise_recorded", products,
            promises=[plan.promise(products[index - 1], day) for index in paid],
            notes=notes_for(products, promised=ids, refused=refused_ids, state="promise_recorded"),
            repeats={"refuse": more} if more else {}, step="check_offer"))
    return result


def _goodbye_accepted_scenarios(spec, plan, notes_for) -> list[Scenario]:
    """T-031 (review HIGH 2), T-037 (CTO): one product accepted, the read-back said, and the
    customer says goodbye instead of yes: nothing is recorded, and the product is never noted as
    refused."""
    if not (plan.notes or plan.negotiation.get("product_end_values")):
        return []
    products = synthetic_products(spec, 3)
    day = plan.good_day(products)
    if not day:
        return []
    first = {**plan.offer(1, day), "vars": {OFFER_DATE: day, OFFER_PRODUCT_NAME: "the first one"}}
    pid = str(products[0][spec.account.data["product_id_field"]])
    state, notes = _unconfirmed_close(spec, products, notes_for, pid)
    return [Scenario(
        "goodbye_readback_then_goodbye", [*plan.reach_negotiation(), first, _goodbye()], state, products,
        promises=[], notes=notes, repeats={"goodbye": GOODBYE_TURNS}, step="confirm_record")]


def _unconfirmed_close(spec, products, notes_for, pid: str):
    """T-037 (CTO): the customer left after the read-back without a yes. The call closes as the
    goodbye's hang-up state, records nothing, and the product with the unconfirmed offer gets the
    neutral note reason or no note (never a refusal)."""
    state = goodbye_states(spec)[0]
    reason = unconfirmed_note_reason(spec)
    id_field = spec.account.data["product_id_field"]
    if reason:
        return state, notes_for(products, state=state, written={pid: reason})
    return state, notes_for([product for product in products if str(product[id_field]) != pid], state=state)


def accepted_refusal_notes(sim: Simulator, spec: PhoneAgentSpec, products: list[dict[str, Any]]) -> list[str]:
    """T-031: a refused note on a product the customer accepted is a false statement about the
    customer (review HIGH 2); every scenario checks it."""
    rule = spec.closing.data.get("product_notes") or {}
    if not rule.get("refused_reason"):
        return []
    accepted = sim.vars.get(OFFERS_ACCEPTED)
    try:
        accepted = json.loads(accepted) if isinstance(accepted, str) and accepted.strip() else (accepted or {})
    except ValueError:
        accepted = {}
    id_field = spec.account.data["product_id_field"]
    ids = {str(products[int(key) - 1].get(id_field)) for key in accepted
           if str(key).strip().isdigit() and 1 <= int(key) <= len(products)}
    return [f"a {rule['refused_reason']} note on {call.body.get(rule['product_field'])}, which the customer accepted"
            for call in sim.bank.calls if call.tool == rule.get("tool") and call.ok
            and str(call.body.get(rule.get("reason_field"))) == str(rule["refused_reason"])
            and str(call.body.get(rule.get("product_field"))) in ids]


# T-035: api calls the whole silent chain may make with the code sandbox down, from the
# closing or the record loop to end_call (13 notes, 13 promise calls and 2 closes today).
SANDBOX_DOWN_CALL_LIMIT = 40


def sandbox_down_gaps(workflow: dict[str, Any]) -> list[tuple[str, str]]:
    """(loop or start, problem): each loop of silent steps needs an exit on the engine's call
    counters, and with every code run failing the chain from the closing and from the record
    loop must still reach end_call after a bounded number of calls, whether the bank answers
    ok or not (live v20: ~40 notes, T-035)."""
    from .code_cycles import code_cycle_gaps, sandbox_down_chain

    problems = list(code_cycle_gaps(workflow))
    nodes = workflow.get("nodes", {})
    for start in ("closing", "record_next"):
        if start not in nodes:
            continue
        for result in ("failure", "success"):
            reached, calls = sandbox_down_chain(workflow, start, result=result)
            total = sum(calls.values())
            if reached != END_CALL or total > SANDBOX_DOWN_CALL_LIMIT:
                problems.append((f"{start}:{result}", f"with the code sandbox down and every call a {result}, the "
                                                      f"chain from {start} reaches {reached or 'no end'} after {total} "
                                                      f"api calls {dict(sorted(calls.items()))}"))
    return problems


HONEST_RECORD_PATTERN = re.compile(r"never say[^.\n]*recorded", re.IGNORECASE)
OFFER_STATE_PLACEHOLDERS = ("{{offers_summary}}", "{{readback_text}}", "{{offer_message}}")


def recorded_claim_gaps(workflow: dict[str, Any]) -> list[tuple[str, str]]:
    """(step, problem) for each model-spoken step that sees the checked offers but is not told
    never to say a promise was recorded (CTO addendum item 2: PUB-12 said "I have recorded
    your promise" before any tool ran)."""
    problems = []
    for key, node in [*workflow.get("nodes", {}).items(), *workflow.get("global_nodes", {}).items()]:
        task = str(node.get("task_message") or "")
        if node.get("node_type") != "conversation" or not any(item in task for item in OFFER_STATE_PLACEHOLDERS):
            continue
        if not HONEST_RECORD_PATTERN.search(task):
            problems.append((key, "the step sees the checked offers but its prompt never forbids saying that a "
                                  "promise was recorded before the record tool returned ok"))
    return problems


# ---------------------------------------------------------------------------
# T-034: the kit's customer styles (tools/run_cases.py STYLES). The facts stay the same, only the
# way of saying them changes; each style that reaches code (the date phrase, the opening value)
# gets a call. Phrases are built from the spec's own days; no brief value.
# ---------------------------------------------------------------------------

STYLE_CHATTER = "Busy day, the traffic was terrible. Anyway, {date} works"
STYLE_OTHER_DAY = "my cousin's wedding is on the {other}, but I can pay on {date}"
STYLE_OTHER_DAY_NO_PAY = "my cousin's wedding is on the {other}, so {date}"
STYLE_CORRECTION = "{wrong}, sorry, I mean {right}"
STYLE_YEAR_DIGITS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")


def _style_dates(day: datetime.date, today: datetime.date) -> dict[str, tuple[str, ...]]:
    """name -> the date phrases of one offer turn each (several: the date said in pieces)."""
    month = SPOKEN_MONTHS[day.month - 1]
    other = day.day % 28 + 1   # another day number of the same month
    wrong = digit_ordinal(other)
    forms = spoken_date_forms(day)
    phrases = {
        "corrects_digit": (STYLE_CORRECTION.format(wrong=f"the {wrong}", right=forms["digit_ordinal"]),),
        "corrects_month_first": (STYLE_CORRECTION.format(wrong=f"{month} {wrong}", right=forms["month_first"]),),
        "corrects_words": (STYLE_CORRECTION.format(wrong=f"the {spoken_ordinal(other)}", right=forms["word_ordinal"]),),
        "pieces_day_then_month": (f"the {spoken_ordinal(day.day)}", f"of {month}"),
        "pieces_month_then_day": (month, f"the {spoken_ordinal(day.day)}"),
        "talkative_chatter": (STYLE_CHATTER.format(date=forms["digit_ordinal"]),),
        "talkative_other_day": (STYLE_OTHER_DAY.format(other=digit_ordinal(other), date=forms["digit_ordinal"]),),
        "in_words_year_digits": (forms["word_ordinal"] + " " + " ".join(
            STYLE_YEAR_DIGITS[int(digit)] for digit in str(day.year)),),
    }
    if 1 <= (day - today).days <= 6:
        # A weekday corrected to the day's own weekday (the next one is the day itself).
        wrong_day = day + datetime.timedelta(days=1 if (day - today).days < 6 else -1)
        phrases["corrects_weekday"] = (STYLE_CORRECTION.format(wrong=wrong_day.strftime("%A"), right=day.strftime("%A")),)
    return phrases


def _style_scenarios(spec, plan, one, notes_for) -> list[Scenario]:
    day = plan.good_day(one)
    if not day:
        return []
    product = one[0]
    good = datetime.date.fromisoformat(day)
    today = datetime.date.fromisoformat(plan.now[:10])

    def promised(name, turns, step="check_offer"):
        return Scenario(f"style_{name}", [*plan.reach_negotiation(), *turns, plan.confirm()], "promise_recorded", one,
                        promises=[plan.promise(product, day)],
                        notes=notes_for(one, promised=["p1"], state="promise_recorded"), step=step)

    result = [promised(name, [plan.offer(1, phrase) for phrase in phrases])
              for name, phrases in _style_dates(good, today).items()]
    # Several days and no pay word: no day is taken (the wedding day is never booked); the
    # customer then says the day alone.
    other = STYLE_OTHER_DAY_NO_PAY.format(other=digit_ordinal(good.day % 28 + 1),
                                          date=spoken_date_forms(good)["digit_ordinal"])
    result.append(promised("talkative_other_day_no_pay_word",
                           [plan.offer(1, other), plan.offer(1, spoken_date_forms(good)["digit_ordinal"])]))
    # asks_back: a question back before the answer, at each step where the customer answers.
    ask_back = {"kind": "say", "label": "ask_back", "stays": True, "vars": {}}
    greeting = {**ask_back, "vars": {plan.opening["who_answered_variable"]: OPENING_GREETING_VALUE}}
    result.append(Scenario(
        "style_asks_back", [greeting, greeting, plan.answer_who("identity_values"), ask_back, *plan.verify(),
                            ask_back, plan.offer(1, day), ask_back, plan.confirm()],
        "promise_recorded", one, promises=[plan.promise(product, day)],
        notes=notes_for(one, promised=["p1"], state="promise_recorded"), step="opening"))
    return result

