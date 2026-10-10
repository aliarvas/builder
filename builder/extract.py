"""Extract a phone-agent spec (``builder/spec.py``) from brief documents and the OpenAPI file.

Pipeline (docs/ARCHITECTURE.md, "Messy inputs"):

1. Four extraction calls run in parallel, each for a group of spec sections, each with the
   whole brief and the tool contract. Their JSON uses a small intermediate shape (routes and
   outcome pairs instead of state names) so no call depends on another.
2. Code validates each group, merges them into a spec, validates the spec (``parse_spec``,
   tool contract, brief values, a dry render) and sends only the errors back to the call
   that owns the failing section (at most ``MAX_REPAIR_ROUNDS`` rounds).
3. A coverage call maps every brief item to a spec path; missing items get one targeted re-ask.
   Additions that would break validation are dropped and traced.

The model never does arithmetic: it copies counts, units and conditions; code evaluates them.
"""

from __future__ import annotations

import copy
import datetime
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .llm import LLMError, LLMResult, text_block
from .prompts import (
    CLOSE_STATE_GUIDE,
    COVERAGE_FOLLOWUP_TEMPLATE,
    COVERAGE_TASK_TEMPLATE,
    EXTRACT_FLOW_TASK,
    EXTRACT_OFFER_TASK,
    EXTRACT_OPENING_IDENTITY_TASK,
    EXTRACT_OUTCOMES_TASK,
    EXTRACT_REPAIR_TEMPLATE,
    EXTRACTION_CONTEXT_TEMPLATE,
    EXTRACTION_SYSTEM_PROMPT,
    PromptDefinition,
    render_prompt,
)
from .spoken import agent_directed, spoken_words
from .spec import (
    CLOSE_STATE_NAMES,
    OPENING_GREETING_VALUE,
    OPTIONAL_CLOSE_STATES,
    PhoneAgentSpec,
    SpecError,
    parse_spec,
)
from .tools_from_openapi import CALL_VARIABLES, contract_field_kind, tool_contract, tools_from_openapi

MAX_REPAIR_ROUNDS = 2
MAX_LOGGED_ISSUES = 60
SPOKEN_MARK = "is said to the customer word for word"

# Routes the intermediate JSON uses; the merge turns them into the spec's value lists.
OPENING_ROUTES = ("verify", "other_person", "ask_again", "end")
THIRD_PARTY_ROUTES = ("stay", "end")
NEGOTIATION_ROUTES = ("readback", "end", "stay")
CONFIRMATION_ROUTES = ("record", "change")
SPECIAL_STEPS = ("opening", "third_party", "identity", "negotiate", "confirm_record")

# Skeleton variable and synthetic field names. Fixed by the builder, never by a brief.
FRAMEWORK_NAMES = dict(
    who_answered_variable="caller_role",
    unclear_count_variable="opening_unclear_asks",
    third_party_intent_variable="third_party_reply",
    negotiation_intent_variable="negotiation_reply",
    confirmation_intent_variable="readback_reply",
    expected_count_variable="readback_product_count",
    products_variable="account_product_list",
    product_number_field="promise_product_number",
)

# Call-end states every outcome table must map; the others are optional.
REQUIRED_FIXED_STATES = tuple(state for state in CLOSE_STATE_NAMES if state not in OPTIONAL_CLOSE_STATES)
# Framework states briefs rarely name. Extraction must still map them, to the closest row,
# recorded as derived (F-040); left out, they would silently fall to the default row.
DERIVED_REQUIRED_STATES = ("account_failed", "offer_limit", "hangup", "hangup_unverified")
REQUIRED_STATES = REQUIRED_FIXED_STATES + DERIVED_REQUIRED_STATES
DERIVED_PREFIX = "derived"
STAGE_NAMES = ("opening", "third_party", "identity", "account", "negotiation", "confirmation", "offer", "closing")


@dataclass(frozen=True)
class Group:
    name: str
    task: PromptDefinition
    sections: tuple[str, ...]


GROUPS = (
    Group("opening_identity", EXTRACT_OPENING_IDENTITY_TASK, ("agent", "opening", "third_party", "identity", "global_rules")),
    Group("flow", EXTRACT_FLOW_TASK, ("account", "negotiation", "confirmation")),
    Group("offer", EXTRACT_OFFER_TASK, ("offer",)),
    Group("outcomes", EXTRACT_OUTCOMES_TASK, ("outcomes", "special_paths", "closing")),
)
SECTION_GROUP = {section: group.name for group in GROUPS for section in group.sections}


class ModelClient(Protocol):
    def complete(self, system: str, messages: list[dict[str, Any]], purpose: str) -> LLMResult: ...


Log = Callable[[str, Any], None]


class ExtractionError(SpecError):
    """Validation still fails after the repair rounds; ``problems`` lists every failing field."""

    def __init__(self, message: str, problems: list[str], candidate: dict[str, Any] | None) -> None:
        super().__init__(message)
        self.problems = problems
        self.candidate = candidate


@dataclass
class ExtractionResult:
    spec_data: dict[str, Any]
    spec: PhoneAgentSpec
    warnings: list[str] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def render_documents(documents: list[tuple[str, str]]) -> str:
    return "\n\n".join(
        f"## Document {index} of {len(documents)}: {name}\n\n{text.strip()}"
        for index, (name, text) in enumerate(documents, start=1)
    )


def context_text(documents: list[tuple[str, str]], contract: dict[str, Any]) -> str:
    return render_prompt(
        EXTRACTION_CONTEXT_TEMPLATE,
        documents=render_documents(documents),
        contract=json.dumps(contract, indent=1, ensure_ascii=False),
        call_variables=", ".join(sorted(CALL_VARIABLES)),
    )


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"“(`*])")
_TABLE_RULE = re.compile(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?")


def brief_items(documents: list[tuple[str, str]]) -> list[tuple[int, str]]:
    """Numbered coverage items: sentences, list items and table rows. Headings are skipped."""
    items: list[tuple[int, str]] = []
    for _, text in documents:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or _TABLE_RULE.fullmatch(stripped):
                continue
            if stripped.startswith("|"):
                pieces = [" | ".join(cell.strip() for cell in stripped.strip("|").split("|"))]
            else:
                pieces = [piece.strip() for piece in _SENTENCE_SPLIT.split(stripped)]
            for piece in pieces:
                if piece:
                    items.append((len(items) + 1, piece))
    return items


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

_CODE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")

MONTHS = {
    name: number for number, names in enumerate((
        ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",),
        ("june", "jun"), ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"),
        ("october", "oct"), ("november", "nov"), ("december", "dec"),
    ), start=1) for name in names
}
_MONTH = r"(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?"
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?:,?\s+(\d{4}))?"
_DAY_MONTH = re.compile(r"(?<![A-Za-z0-9])" + _DAY + r"\s+(?:of\s+)?" + _MONTH + _YEAR + r"(?![A-Za-z])", re.IGNORECASE)
_MONTH_DAY = re.compile(r"(?<![A-Za-z0-9])" + _MONTH + r"\s+" + _DAY + _YEAR + r"(?![A-Za-z0-9])", re.IGNORECASE)
_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_NUMERIC = re.compile(r"(?<![\d/.])(\d{1,2})[/.](\d{1,2})[/.](\d{4})(?![\d/.])")

_WEEKDAY = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekday|<\s*weekday\s*>)"
_NEXT_WEEKDAY = re.compile(r"\bnext\W{0,3}" + _WEEKDAY, re.IGNORECASE)
_NEXT_WEEKDAY_DIRECTION = {
    "following_week": re.compile(r"\bfollowing\b|\bweek after\b|\bnext (?:calendar )?week\b|\bnext week'?s\b", re.IGNORECASE),
    "upcoming": re.compile(r"\bnearest\b|\bupcoming\b|\bcoming\b|\bsoonest\b|\bfirst\b|\bnext such\b", re.IGNORECASE),
}
_PERSUASION = re.compile(r"persua|attempt", re.IGNORECASE)
_ENDS_ITEM = re.compile(r"[.!?:|]\s*$")
_STARTS_ITEM = re.compile(r"(\d+[.)]|[-*+|#])\s?")
_LIST_NUMBER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
_RULE_REFERENCE = re.compile(r"\b(?:rules?|sections?|§)\s+\d+(?:\s*(?:,|and|to|-|–)\s*\d+)*", re.IGNORECASE)

_UNITS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
          "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty")
_ORDINAL_UNITS = ("zeroth", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth",
                  "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth", "sixteenth",
                  "seventeenth", "eighteenth", "nineteenth")


def _number_words(number: int) -> tuple[str, ...]:
    if number < 20:
        return _UNITS[number], _ORDINAL_UNITS[number]
    tens, unit = divmod(number, 10)
    if unit == 0:
        return _TENS[tens], _TENS[tens][:-1] + "ieth"
    return tuple(f"{_TENS[tens]}{sep}{word}" for sep in ("-", " ") for word in (_UNITS[unit], _ORDINAL_UNITS[unit]))


# Day counts 0..69 as words and ordinal words ("twelve", "twelfth", "twenty-one").
NUMBER_WORDS = {number: _number_words(number) for number in range(70)}


def _ordinal(number: int) -> str:
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def brief_dates(text: str) -> tuple[set[datetime.date], set[tuple[int, int]]]:
    """Dates written in the documents: full dates (ISO, '26 October 2026', 'October 26, 2026',
    '26/10/2026' read both ways) and (month, day) pairs for dates written without a year."""
    full: set[datetime.date] = set()
    month_days: set[tuple[int, int]] = set()

    def add(year: str | None, month: int, day: int) -> None:
        try:
            if year:
                full.add(datetime.date(int(year), month, day))
            else:
                datetime.date(2000, month, day)  # validity check only (leap year)
                month_days.add((month, day))
        except ValueError:
            pass

    for match in _ISO.finditer(text):
        add(match.group(1), int(match.group(2)), int(match.group(3)))
    for match in _DAY_MONTH.finditer(text):
        add(match.group(3), MONTHS[match.group(2).lower()], int(match.group(1)))
    for match in _MONTH_DAY.finditer(text):
        add(match.group(3), MONTHS[match.group(1).lower()], int(match.group(2)))
    for match in _NUMERIC.finditer(text):
        first, second, year = int(match.group(1)), int(match.group(2)), match.group(3)
        add(year, second, first)
        add(year, first, second)
    return full, month_days


def _normal(text: str) -> str:
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    text = re.sub(r"[`*]", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("the reply contains no JSON object")
    value = json.loads(cleaned[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("the reply is not a JSON object")
    return value


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


class _Checker:
    """Collects (path, message) errors and warnings for one validation pass."""

    def __init__(
        self, brief: str, contract: dict[str, Any], openapi_strings: set[str], *, spoken_soft: bool = False,
    ) -> None:
        # In the last round a spoken-text problem is a warning: the renderer then uses its fallback.
        self.spoken_soft = spoken_soft
        self.brief = brief
        self.brief_normal = _normal(brief)
        self.contract = contract
        self.openapi_strings = openapi_strings
        self.errors: list[tuple[str, str]] = []
        self.warnings: list[tuple[str, str]] = []
        lines = [line.strip() for line in brief.splitlines() if line.strip()]
        # One line (a table row, a list item, a paragraph). A line joins the next one only when
        # its sentence runs on: it does not end a sentence and the next line starts no new item.
        self.windows = [
            line + " " + lines[index + 1]
            if index + 1 < len(lines) and not _ENDS_ITEM.search(line) and not _STARTS_ITEM.match(lines[index + 1])
            else line
            for index, line in enumerate(lines)
        ] or [brief]
        self.dates, self.month_days = brief_dates(brief)
        # Numbers as evidence: without list numbering and rule references ("12.", "rule 30",
        # "rules 6, 47"), which would otherwise make almost every small number "written".
        self.count_text = _RULE_REFERENCE.sub(" ", _LIST_NUMBER.sub(" ", brief))

    def error(self, path: str, message: str) -> None:
        self.errors.append((path, message))

    def warn(self, path: str, message: str) -> None:
        self.warnings.append((path, message))

    # Brief evidence -------------------------------------------------------
    def in_brief(self, value: str) -> bool:
        return bool(re.search(
            r"(?<![A-Za-z0-9_])" + re.escape(value) + r"(?![A-Za-z0-9_])", self.brief, re.IGNORECASE
        ))

    def known_value(self, value: str) -> bool:
        return value in self.openapi_strings or self.in_brief(value)

    def excerpt(self, path: str, source: Any, *, derived_ok: bool = False) -> None:
        """A verbatim excerpt. ``derived: <why>`` is accepted only where a call-end state is
        derived (``derived_ok``); a rule source with a derived or fallback marker is an error."""
        if not isinstance(source, str) or not source.strip():
            self.error(path, "needs a source excerpt copied from the documents")
            return
        text = source.strip()
        marker = text.lower()
        if derived_ok and marker.startswith(DERIVED_PREFIX):
            return
        if marker.startswith((DERIVED_PREFIX, "fallback")):
            self.error(path, "must be an excerpt copied from the documents; \"derived\" and \"fallback\" are "
                       "only for derived call-end states and data sources, never for a rule")
            return
        if _normal(text) not in self.brief_normal:
            self.warn(path, f"source excerpt not found verbatim in the documents: {text[:80]!r}")

    def rule(self, value: Any, path: str) -> None:
        if not isinstance(value, dict):
            self.error(path, "must be an object {text, source}")
            return
        if not isinstance(value.get("text"), str) or not value["text"].strip():
            self.error(path + ".text", "must be a non-empty string")
        self.excerpt(path + ".source", value.get("source"))

    def rules(self, value: Any, path: str) -> None:
        if not isinstance(value, list):
            self.error(path, "must be an array of rules")
            return
        for index, item in enumerate(value):
            self.rule(item, f"{path}[{index}]")

    # Tool contract ----------------------------------------------------------
    def tool_fields(self, tool: str, side: str) -> dict[str, Any]:
        entry = self.contract.get(tool)
        return entry.get(side, {}) if isinstance(entry, dict) else {}

    def tool_field(self, path: str, value: Any, tool: str, side: str, kinds: tuple[str, ...] = ()) -> dict[str, Any]:
        fields = self.tool_fields(tool, side)
        if not isinstance(value, str) or value not in fields:
            self.error(path, f"must be a {side} field of {tool}: one of {sorted(fields)}")
            return {}
        if kinds and contract_field_kind(fields[value]) not in kinds:
            self.error(path, f"{tool} {side} field {value!r} is {contract_field_kind(fields[value]) or 'untyped'}, expected {' or '.join(kinds)}")
        return fields[value]

    def together(self, *values: str) -> bool:
        """All values occur in one line of the documents (or in a line and the next one)."""
        patterns = [
            re.compile(r"(?<![A-Za-z0-9_])" + re.escape(value) + r"(?![A-Za-z0-9_])", re.IGNORECASE)
            for value in values
        ]
        return any(all(pattern.search(window) for pattern in patterns) for window in self.windows)

    def outcome_pair(self, path: str, outcome: Any, reason: Any) -> None:
        """The outcome and its reason must be written together in the documents (a table row
        or one sentence); an outcome without a reason must itself appear in the documents."""
        if not isinstance(outcome, str) or not outcome:
            self.error(path + ".outcome", "must be a non-empty string")
            return
        if not isinstance(reason, str):
            self.error(path + ".reason", "must be a string (\"\" when the table lists no reason)")
            return
        if not reason:
            if not self.in_brief(outcome):
                self.error(path + ".outcome", f"{outcome!r} does not appear in the documents")
        elif not self.together(outcome, reason):
            self.error(path, f"pair {outcome}/{reason} not found together in the documents "
                             "(same table row or sentence); use a pair the documents list")

    def date_written(self, day: str) -> bool:
        """``day`` (ISO) is written in the documents, in ISO or a common spoken or numeric form."""
        try:
            parsed = datetime.date.fromisoformat(day)
        except ValueError:
            return False
        return parsed in self.dates or (parsed.month, parsed.day) in self.month_days

    def count_written(self, number: int) -> bool:
        """``number`` is written in the documents as digits, an ordinal or a word (0 also as 'today')."""
        forms = [str(number), _ordinal(number), *NUMBER_WORDS.get(number, ())]
        if number == 0:
            forms += ["today", "same day"]
        return any(
            re.search(r"(?<![A-Za-z0-9_])" + re.escape(form) + r"(?![A-Za-z0-9_])", self.count_text, re.IGNORECASE)
            for form in forms
        )


def _routed(entries: Any, routes: tuple[str, ...], path: str, check: _Checker, *, pairs: bool) -> list[dict[str, Any]]:
    """Validate a list of {value, meaning, route[, outcome, reason]} entries."""
    if not isinstance(entries, list) or not entries:
        check.error(path, "must be a non-empty array")
        return []
    seen: set[str] = set()
    good = []
    for index, entry in enumerate(entries):
        where = f"{path}[{index}]"
        if not isinstance(entry, dict):
            check.error(where, "must be an object")
            continue
        value = entry.get("value")
        if not isinstance(value, str) or not _CODE.fullmatch(value):
            check.error(where + ".value", "must be a snake_case code")
            continue
        if value in seen:
            check.error(where + ".value", f"repeats {value!r}")
        if value == OPENING_GREETING_VALUE:
            check.error(where + ".value", f"{value!r} is reserved; the program adds it")
        seen.add(value)
        if entry.get("route") not in routes:
            check.error(where + ".route", f"must be one of {list(routes)}")
            continue
        if pairs and entry["route"] == "end":
            check.outcome_pair(where, entry.get("outcome"), entry.get("reason", ""))
            check.excerpt(where + ".source", entry.get("source"), derived_ok=True)
        good.append(entry)
    return good


def _count_route(entries: list[dict[str, Any]], route: str) -> int:
    return sum(1 for entry in entries if entry.get("route") == route)


# ---------------------------------------------------------------------------
# Group checks (intermediate shape)
# ---------------------------------------------------------------------------

def _check_opening_identity(data: dict[str, Any], check: _Checker) -> None:
    agent = data.get("agent")
    if not isinstance(agent, dict):
        check.error("agent", "must be an object")
    else:
        for key in ("name", "language"):
            if not isinstance(agent.get(key), str) or not agent[key].strip():
                check.error(f"agent.{key}", "must be a non-empty string")
        check.rule(agent.get("introduction"), "agent.introduction")
    opening = data.get("opening")
    if not isinstance(opening, dict):
        check.error("opening", "must be an object")
    else:
        check.rules(opening.get("rules"), "opening.rules")
        check.rule(opening.get("confirmation_question"), "opening.confirmation_question")
        check.rule(opening.get("unclear_instruction"), "opening.unclear_instruction")
        forbidden = opening.get("forbidden_before_verification")
        if not isinstance(forbidden, list) or not all(isinstance(item, str) and item.strip() for item in forbidden):
            check.error("opening.forbidden_before_verification", "must be an array of words or topics")
        address = opening.get("address_with")
        if not isinstance(address, list) or not address or not all(isinstance(item, str) for item in address):
            check.error("opening.address_with", "must list call variable names")
        else:
            for index, name in enumerate(address):
                _call_variable(check, f"opening.address_with[{index}]", name)
        _positive_int(check, "opening.max_unclear_asks", opening.get("max_unclear_asks"))
        answers = _routed(opening.get("answers"), OPENING_ROUTES, "opening.answers", check, pairs=True)
        if answers and not _count_route(answers, "verify"):
            check.error("opening.answers", "needs a value with route verify (the customer confirmed)")
        if answers and _count_route(answers, "ask_again") != 1:
            check.error("opening.answers", "needs exactly one value with route ask_again")
        if answers and not _count_route(answers, "end"):
            check.error("opening.answers", "needs a value with route end for a person who refuses to talk or to "
                        "confirm who they are (closest row, source \"derived: ...\" if the documents name none)")
    third = data.get("third_party")
    if not isinstance(third, dict):
        check.error("third_party", "must be an object")
    else:
        check.rules(third.get("rules"), "third_party.rules")
        _routed(third.get("intents"), THIRD_PARTY_ROUTES, "third_party.intents", check, pairs=True)
    identity = data.get("identity")
    if not isinstance(identity, dict):
        check.error("identity", "must be an object")
    else:
        check.rules(identity.get("rules"), "identity.rules")
        questions = identity.get("questions")
        if not isinstance(questions, list) or not questions:
            check.error("identity.questions", "must list at least one question")
        else:
            for index, question in enumerate(questions):
                where = f"identity.questions[{index}]"
                if not isinstance(question, dict):
                    check.error(where, "must be an object")
                    continue
                if not isinstance(question.get("field"), str) or not question["field"]:
                    check.error(where + ".field", "must be a non-empty string")
                check.rule(question.get("ask"), where + ".ask")
                check.rule(question.get("answer_format"), where + ".answer_format")
        for key in ("failed_answer_instruction", "exhausted_say"):
            check.rule(identity.get(key), f"identity.{key}")
    check.rules(data.get("global_rules"), "global_rules")


def _check_flow(data: dict[str, Any], check: _Checker) -> None:
    for section in ("account", "negotiation", "confirmation"):
        if not isinstance(data.get(section), dict):
            check.error(section, "must be an object")
            return
        check.rules(data[section].get("rules"), f"{section}.rules")
    negotiation = _routed(data["negotiation"].get("intents"), NEGOTIATION_ROUTES, "negotiation.intents", check, pairs=True)
    if negotiation and not _count_route(negotiation, "readback"):
        check.error("negotiation.intents", "needs a value with route readback")
    confirmation = data["confirmation"]
    _positive_int(check, "confirmation.max_attempts_per_product", confirmation.get("max_attempts_per_product"))
    intents = _routed(confirmation.get("intents"), CONFIRMATION_ROUTES, "confirmation.intents", check, pairs=False)
    for route in CONFIRMATION_ROUTES:
        if intents and not _count_route(intents, route):
            check.error("confirmation.intents", f"needs a value with route {route}")


def _check_offer(data: dict[str, Any], check: _Checker) -> None:
    if not isinstance(data.get("offer"), dict):
        check.error("offer", "must be an object")
        return
    check.rules(data["offer"].get("rules", []), "offer.rules")


def _check_outcomes(data: dict[str, Any], check: _Checker) -> None:
    closing = data.get("closing")
    if not isinstance(closing, dict):
        check.error("closing", "must be an object")
    else:
        check.rules(closing.get("rules", []), "closing.rules")
    rows = data.get("outcomes")
    if not isinstance(rows, list) or not rows:
        check.error("outcomes", "must list the closing table rows")
        rows = []
    known_states = set(CLOSE_STATE_NAMES)
    seen: dict[str, int] = {}
    for index, row in enumerate(rows):
        where = f"outcomes[{index}]"
        if not isinstance(row, dict):
            check.error(where, "must be an object")
            continue
        states = row.get("states", [])
        if not isinstance(states, list):
            check.error(where + ".states", "must be an array of state names")
            continue
        for state in states:
            if state not in known_states:
                check.error(where + ".states", f"unknown state {state!r}; allowed: {sorted(known_states)}")
            elif state in seen:
                check.error(where + ".states", f"state {state!r} is also mapped in outcomes[{seen[state]}]")
            else:
                seen[state] = index
    for state in REQUIRED_STATES:
        if rows and state not in seen:
            check.error("outcomes", f"required state {state!r} is not mapped to a row; if the documents do not "
                        "name it, map it to the closest row and list it in derived_states")
    derived = data.get("derived_states", {})
    if not isinstance(derived, dict):
        check.error("derived_states", "must be an object {state: why}")
    else:
        for state, why in derived.items():
            if state not in seen:
                check.error(f"derived_states.{state}", "is not mapped to a row in outcomes[].states")
            if not isinstance(why, str) or not why.strip():
                check.error(f"derived_states.{state}", "needs a short reason for the chosen row")
    if not isinstance(data.get("special_paths"), list):
        check.error("special_paths", "must be an array (empty when the brief has none)")


GROUP_CHECKS = {
    "opening_identity": _check_opening_identity,
    "flow": _check_flow,
    "offer": _check_offer,
    "outcomes": _check_outcomes,
}


def _positive_int(check: _Checker, path: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        check.error(path, "must be a positive integer")


def _call_variable(check: _Checker, path: str, name: Any) -> None:
    if not isinstance(name, str) or not _CODE.fullmatch(name):
        check.error(path, "must be a call variable name")
    elif name not in CALL_VARIABLES:
        if check.in_brief(name):
            check.warn(path, f"{name!r} is not a kit call variable; taken from the documents")
        else:
            check.error(path, f"{name!r} is not a call variable: {sorted(CALL_VARIABLES)}")


# ---------------------------------------------------------------------------
# Merge (intermediate shape -> spec)
# ---------------------------------------------------------------------------

def _values(entries: list[dict[str, Any]], route: str | None = None) -> list[str]:
    return [entry["value"] for entry in entries if route is None or entry.get("route") == route]


def merge_groups(groups: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build the spec dict from validated group replies. Routes become value lists and
    the closing pairs of routed values become ``outcomes[].on`` entries."""
    first = copy.deepcopy(groups["opening_identity"])
    flow = copy.deepcopy(groups["flow"])
    offer = copy.deepcopy(groups["offer"]["offer"])
    ends = copy.deepcopy(groups["outcomes"])
    names = FRAMEWORK_NAMES

    opening_in = first["opening"]
    answers = opening_in["answers"]
    opening = {
        "rules": opening_in.get("rules", []),
        "confirmation_question": opening_in["confirmation_question"],
        "unclear_instruction": opening_in["unclear_instruction"],
        "who_answered_variable": names["who_answered_variable"],
        "forbidden_before_verification": opening_in["forbidden_before_verification"],
        "who_answered_options": _values(answers),
        "identity_values": _values(answers, "verify"),
        "third_party_values": _values(answers, "other_person"),
        "stay_values": _values(answers, "ask_again"),
        "close_values": _values(answers, "end"),
        "unclear_count_variable": names["unclear_count_variable"],
        "max_unclear_asks": opening_in["max_unclear_asks"],
        "address_with": opening_in["address_with"],
    }
    third_in = first["third_party"]
    third_party = {
        "rules": third_in.get("rules", []),
        "intent_variable": names["third_party_intent_variable"],
        "intent_values": _values(third_in["intents"]),
        "close_values": _values(third_in["intents"], "end"),
    }
    identity = {key: value for key, value in first["identity"].items()}
    account_in = flow["account"]
    account = {
        "rules": account_in.get("rules", []),
        "products_field": account_in.get("products_field"),
        "products_variable": names["products_variable"],
        "product_id_field": account_in.get("product_id_field"),
        "product_kind_field": account_in.get("product_kind_field") or "",
        "product_label_field": account_in.get("product_label_field") or "",
    }
    negotiation_in = flow["negotiation"]
    negotiation = {
        "rules": negotiation_in.get("rules", []),
        "intent_variable": names["negotiation_intent_variable"],
        "intent_values": _values(negotiation_in["intents"]),
        "confirm_values": _values(negotiation_in["intents"], "readback"),
        "close_values": _values(negotiation_in["intents"], "end"),
    }
    confirmation_in = flow["confirmation"]
    confirmation = {
        "rules": confirmation_in.get("rules", []),
        "product_number_field": names["product_number_field"],
        "promise_product_id_field": confirmation_in.get("promise_product_id_field"),
        "expected_count_variable": names["expected_count_variable"],
        "intent_variable": names["confirmation_intent_variable"],
        "intent_values": _values(confirmation_in["intents"]),
        "revise_values": _values(confirmation_in["intents"], "change"),
        "max_attempts_per_product": confirmation_in["max_attempts_per_product"],
        "promise_date_field": confirmation_in.get("promise_date_field"),
        "promise_amount_field": confirmation_in.get("promise_amount_field"),
    }
    offer.setdefault("rules", [])

    rows = []
    for row in ends["outcomes"]:
        merged = {key: value for key, value in row.items() if key != "states"}
        merged["reason"] = merged.get("reason") or ""
        merged["on"] = list(row.get("states", []))
        merged["wins_over_promise"] = bool(merged.get("wins_over_promise", False))
        rows.append(merged)
    for prefix, entries in (
        ("opening:", answers), ("third_party:", third_in["intents"]), ("negotiation:", negotiation_in["intents"]),
    ):
        for entry in entries:
            if entry.get("route") != "end":
                continue
            pair = (entry.get("outcome"), entry.get("reason") or "")
            target = next((row for row in rows if (row["outcome"], row["reason"]) == pair), None)
            if target is not None:
                target["on"].append(prefix + entry["value"])
    closing_in = ends["closing"]
    special_paths = []
    for path in ends.get("special_paths", []):
        path = dict(path)
        path.setdefault("tool", "")
        path.setdefault("tool_args", {})
        path["reason"] = path.get("reason") or ""
        ask = path.get("ask")
        if not isinstance(ask, dict) or not str(ask.get("text") or "").strip():
            path.pop("ask", None)  # an empty ask object means no question
        special_paths.append(path)

    provenance: dict[str, Any] = {}
    overrides: list[dict[str, Any]] = []
    for name, reply in groups.items():
        if isinstance(reply.get("sources"), dict):
            provenance.update({str(key): value for key, value in reply["sources"].items()})
        if isinstance(reply.get("overrides"), list):
            overrides.extend(item for item in reply["overrides"] if isinstance(item, dict))
    # Derived mappings carry a reason, not an excerpt (F-040).
    for state, why in (ends.get("derived_states") or {}).items():
        provenance[f"outcomes.state.{state}"] = f"{DERIVED_PREFIX}: {why}"
    for prefix, entries in (
        ("opening:", answers), ("third_party:", third_in["intents"]), ("negotiation:", negotiation_in["intents"]),
    ):
        for entry in entries:
            source = str(entry.get("source") or "")
            if entry.get("route") == "end" and source.lower().startswith(DERIVED_PREFIX):
                provenance[f"outcomes.state.{prefix}{entry['value']}"] = source
    return {
        "spec_version": 1,
        "agent": first["agent"],
        "opening": opening,
        "third_party": third_party,
        "identity": identity,
        "account": account,
        "negotiation": negotiation,
        "confirmation": confirmation,
        "special_paths": special_paths,
        "outcomes": rows,
        "global_rules": first.get("global_rules", []),
        "closing": {
            "rules": closing_in.get("rules", []),
            "outcome_field": closing_in.get("outcome_field"),
            "reason_field": closing_in.get("reason_field"),
        },
        "offer": offer,
        "provenance": provenance,
        "overrides": overrides,
    }


def _cross_group_checks(groups: dict[str, dict[str, Any]], check: _Checker) -> None:
    """Routed closing pairs must be rows of the closing table (owned by other groups)."""
    rows = groups["outcomes"].get("outcomes", [])
    pairs = {(row.get("outcome"), row.get("reason") or "") for row in rows if isinstance(row, dict)}
    listed = ", ".join(f"{outcome}/{reason or '-'}" for outcome, reason in sorted(pairs, key=str))
    for path, entries in (
        ("opening.answers", groups["opening_identity"]["opening"]["answers"]),
        ("third_party.intents", groups["opening_identity"]["third_party"]["intents"]),
        ("negotiation.intents", groups["flow"]["negotiation"]["intents"]),
    ):
        for index, entry in enumerate(entries):
            if entry.get("route") == "end" and (entry.get("outcome"), entry.get("reason") or "") not in pairs:
                check.error(
                    f"{path}[{index}]",
                    f"closes with {entry.get('outcome')}/{entry.get('reason') or '-'}, which is not a closing-table "
                    f"row; the rows are: {listed}",
                )
    # A negotiation value must not close a situation that needs a special path's tool:
    # the call would close with that outcome without calling the tool.
    tool_pairs = {
        (path.get("outcome"), path.get("reason") or ""): path.get("id")
        for path in groups["outcomes"].get("special_paths", []) if isinstance(path, dict) and path.get("tool")
    }
    for index, entry in enumerate(groups["flow"]["negotiation"]["intents"]):
        pair = (entry.get("outcome"), entry.get("reason") or "")
        if entry.get("route") == "end" and pair in tool_pairs:
            check.error(
                f"negotiation.intents[{index}]",
                f"closes with {pair[0]}/{pair[1] or '-'}, which the special path {tool_pairs[pair]!r} closes after "
                "calling its tool; remove this value (route end is only for refusing to pay or to talk)",
            )


# ---------------------------------------------------------------------------
# Spec checks (merged shape)
# ---------------------------------------------------------------------------

def check_spec_data(spec: dict[str, Any], check: _Checker) -> None:
    """Contract and evidence checks on a merged spec dict (beyond ``parse_spec``)."""
    def get(*keys: str) -> Any:
        value: Any = spec
        for key in keys:
            value = value.get(key) if isinstance(value, dict) else None
        return value

    # Identity: question fields in one selector enum; result fields with the right types.
    fields = [question.get("field") for question in get("identity", "questions") or [] if isinstance(question, dict)]
    enums = [set(map(str, entry["enum"])) for entry in check.tool_fields("verify_identity", "request").values()
             if isinstance(entry, dict) and isinstance(entry.get("enum"), list)]
    if fields and not any(set(fields) <= values for values in enums):
        check.error("identity.questions", f"fields {fields} must all be values of one verify_identity enum: "
                    + "; ".join(str(sorted(values)) for values in enums))
    check.tool_field("identity.verified_field", get("identity", "verified_field"), "verify_identity", "response", ("boolean",))
    check.tool_field("identity.attempts_left_field", get("identity", "attempts_left_field"), "verify_identity", "response", ("integer", "number"))
    check.tool_field("identity.answer_verified_field", get("identity", "answer_verified_field"), "verify_identity", "response", ("boolean",))

    # Account products and product fields.
    products = check.tool_field("account.products_field", get("account", "products_field"), "get_account", "response", ("array",))
    item_fields = products.get("items", {}) if isinstance(products.get("items"), dict) else {}
    product_id = get("account", "product_id_field")
    if products and product_id not in item_fields:
        check.error("account.product_id_field", f"must be a field of one product item: {sorted(item_fields)}")
    for key in ("product_kind_field", "product_label_field"):  # optional, "" when the items have none
        value = get("account", key)
        if products and value and value not in item_fields:
            check.error(f"account.{key}", f"must be a field of one product item or \"\": {sorted(item_fields)}")

    # Promise and closing tool fields.
    for key in ("promise_product_id_field", "promise_date_field", "promise_amount_field"):
        check.tool_field(f"confirmation.{key}", get("confirmation", key), "create_promise", "request")
    if get("confirmation", "product_number_field") in check.tool_fields("create_promise", "request"):
        check.error("confirmation.product_number_field", "collides with a create_promise request field")
    check.tool_field("closing.outcome_field", get("closing", "outcome_field"), "close_call", "request")
    check.tool_field("closing.reason_field", get("closing", "reason_field"), "close_call", "request")
    outcome_entry = check.tool_fields("close_call", "request").get(get("closing", "outcome_field") or "", {})
    outcome_enum = outcome_entry.get("enum") if isinstance(outcome_entry, dict) else None

    # Offer data against the product item fields and the brief.
    offer = get("offer") or {}
    if isinstance(offer, dict):
        _call_variable(check, "offer.today_variable", offer.get("today_variable"))
        # next_weekday: a definite reading only when the documents define "next <weekday>".
        reading = offer.get("next_weekday", "ask")
        if reading in _NEXT_WEEKDAY_DIRECTION:
            definitions = [window for window in check.windows if _NEXT_WEEKDAY.search(window)]
            if not definitions:
                check.error("offer.next_weekday", "the documents do not define \"next <weekday>\"; use ask")
            elif not any(_NEXT_WEEKDAY_DIRECTION[reading].search(window) for window in definitions):
                check.error("offer.next_weekday", f"{reading} does not match how the documents define \"next "
                            "<weekday>\" (following_week: the weekday in the following calendar week; upcoming: "
                            "the nearest such weekday after today); use the reading they give, or ask")
        # The invalid-offer limit is not the persuasion-attempt count (T-005g review, F-040).
        provenance = get("provenance") or {}
        for key in ("offer.max_rejected_offers", "offer.max_rejected_offers_by_product"):
            source = str(provenance.get(key) or "")
            if not source.lower().startswith(("fallback", DERIVED_PREFIX)) and _PERSUASION.search(source):
                check.error(key, "cites persuasion attempts; this field counts invalid offers (failed date or amount "
                            "checks), at least 2. Use 2 with a fallback source unless the documents limit invalid offers")
        for index, day in enumerate(offer.get("holidays") or []):
            if isinstance(day, str) and not check.date_written(day):
                check.error(f"offer.holidays[{index}]", f"{day} is not a date written in the documents; "
                            "list only the dates the documents give, converted to YYYY-MM-DD")
        day_rules = [("offer.earliest", offer.get("earliest"))] + [
            (f"offer.latest[{index}]", rule) for index, rule in enumerate(offer.get("latest") or [])
        ]
        for where, rule in day_rules:
            days = rule.get("days") if isinstance(rule, dict) else None
            if isinstance(days, int) and not isinstance(days, bool) and not check.count_written(days):
                check.error(f"{where}.days", f"{days} does not appear in the documents (as digits, ordinal or "
                            "word); copy the day count the documents give")
        rules = [("offer.latest", offer.get("latest"))] + [(f"offer.{key}", offer.get(key)) for key in ("min_amount", "max_amount")]
        for base, items in rules:
            for index, rule in enumerate(items or []):
                if not isinstance(rule, dict):
                    continue
                if "field" in rule and item_fields and rule["field"] not in item_fields:
                    check.error(f"{base}[{index}].field", f"{rule['field']!r} is not a product field: {sorted(item_fields)}")
                for c_index, condition in enumerate(rule.get("when") or []):
                    if not isinstance(condition, dict):
                        continue
                    where = f"{base}[{index}].when[{c_index}]"
                    entry = item_fields.get(condition.get("field"))
                    if item_fields and entry is None:
                        check.error(where + ".field", f"{condition.get('field')!r} is not a product field: {sorted(item_fields)}")
                        continue
                    allowed = entry.get("enum") if isinstance(entry, dict) else None
                    wanted = list(condition.get("in") or []) + ([condition["equals"]] if "equals" in condition else [])
                    for value in wanted:
                        if allowed and value not in allowed:
                            check.error(where, f"{value!r} is not a value of {condition.get('field')}: {allowed}")

    # Outcome table: outcomes in the tool enum, reasons from the documents, no duplicate rows.
    pairs: set[tuple[Any, Any]] = set()
    for index, row in enumerate(get("outcomes") or []):
        if not isinstance(row, dict):
            continue
        where = f"outcomes[{index}]"
        check.outcome_pair(where, row.get("outcome"), row.get("reason", ""))
        if outcome_enum and row.get("outcome") not in outcome_enum:
            check.error(where + ".outcome", f"{row.get('outcome')!r} is not in the close_call enum {outcome_enum}")
        pair = (row.get("outcome"), row.get("reason") or "")
        if pair in pairs:
            check.error(where, f"repeats the row {pair[0]}/{pair[1] or '-'}")
        pairs.add(pair)
        check.rule(row.get("when"), where + ".when")
        check.rule(row.get("say"), where + ".say")

    # Special paths: real tools, real fields, values from the enum or the documents.
    reserved = {"verify_identity", "get_account", "create_promise", "close_call"}
    ids: set[str] = set()
    for index, path in enumerate(get("special_paths") or []):
        if not isinstance(path, dict):
            continue
        where = f"special_paths[{index}]"
        if not isinstance(path.get("id"), str) or not _CODE.fullmatch(path["id"]) or path["id"] in ids:
            check.error(where + ".id", "must be a unique snake_case id")
        else:
            ids.add(path["id"])
        for key in ("when", "say"):
            check.rule(path.get(key), f"{where}.{key}")
        if "ask" in path:
            check.rule(path["ask"], where + ".ask")
            # The skeleton speaks ``ask`` to the customer and waits for the answer.
            ask_text = str((path["ask"] or {}).get("text") or "").strip() if isinstance(path["ask"], dict) else ""
            if ask_text and not ask_text.endswith("?"):
                check.error(where + ".ask", "is spoken to the customer as one question and the agent waits for the "
                            "answer; write a question ending with '?', or leave ask out (instructions go in when/say)")
        steps = path.get("available_in")
        if not isinstance(steps, list) or not steps or any(step not in SPECIAL_STEPS for step in steps):
            check.error(where + ".available_in", f"must list steps from {list(SPECIAL_STEPS)}")
        tool = path.get("tool") or ""
        args = path.get("tool_args") or {}
        if tool:
            if tool in reserved or tool not in check.contract:
                check.error(where + ".tool", f"must be one of {sorted(set(check.contract) - reserved)} or \"\"")
                continue
            request = check.tool_fields(tool, "request")
            for key, value in (args.items() if isinstance(args, dict) else []):
                entry = request.get(key)
                if entry is None:
                    check.error(f"{where}.tool_args.{key}", f"is not a {tool} request field: {sorted(request)}")
                elif isinstance(entry.get("enum"), list) and value not in entry["enum"]:
                    check.error(f"{where}.tool_args.{key}", f"{value!r} is not in the enum {entry['enum']}")
                elif isinstance(value, str) and not check.known_value(value):
                    check.error(f"{where}.tool_args.{key}", f"{value!r} does not appear in the documents")
        elif args:
            check.error(where + ".tool_args", "must be empty when there is no tool")
        check.outcome_pair(where, path.get("outcome"), path.get("reason", ""))

    # F-047: text spoken word for word (or given as the agent's words) must address the customer.
    spoken = [("agent.introduction", get("agent", "introduction")), ("identity.exhausted_say", get("identity", "exhausted_say"))]
    spoken += [(f"outcomes[{i}].say", row.get("say")) for i, row in enumerate(get("outcomes") or []) if isinstance(row, dict)]
    for i, path in enumerate(get("special_paths") or []):
        if isinstance(path, dict):
            spoken += [(f"special_paths[{i}].{key}", path.get(key)) for key in ("say", "ask") if key in path]
    wait_line = get("agent", "wait_line")
    if isinstance(wait_line, str) and wait_line.strip():
        spoken.append(("agent.wait_line", {"text": wait_line}))
    for where, value in spoken:
        text = value.get("text") if isinstance(value, dict) else None
        reason = agent_directed(spoken_words(text)) if isinstance(text, str) else ""
        if reason:
            message = (f"{SPOKEN_MARK}; write the exact words the agent says to the customer (for example "
                       f"\"Thank you for your time. Goodbye.\"), not an instruction to the agent: {reason}")
            (check.warn if check.spoken_soft else check.error)(where, message)

    # Every rule has a source excerpt.
    for section in ("opening", "third_party", "identity", "account", "negotiation", "confirmation", "offer", "closing"):
        check.rules(get(section, "rules") or [], f"{section}.rules")
    check.rules(get("global_rules") or [], "global_rules")
    check.rule(get("agent", "introduction"), "agent.introduction")

    # Overrides: a rule may not cite the superseded text.
    older = {_normal(item.get("older", "")) for item in get("overrides") or [] if isinstance(item, dict) and item.get("older")}
    for index, item in enumerate(get("overrides") or []):
        if not isinstance(item, dict):
            continue
        for key in ("newer", "older"):
            check.excerpt(f"overrides[{index}].{key}", item.get(key))
        newer_at = check.brief_normal.find(_normal(str(item.get("newer", ""))))
        older_at = check.brief_normal.find(_normal(str(item.get("older", ""))))
        if newer_at >= 0 and older_at >= 0 and newer_at < older_at:
            check.warn(f"overrides[{index}]", "the newer text comes before the older text in the documents")
    if older:
        for path, rule in _all_rules(spec):
            if _normal(str(rule.get("source", ""))) in older:
                check.error(path + ".source", "cites text that a later document overrides; use the newer rule")


def _all_rules(spec: dict[str, Any]):
    for section in STAGE_NAMES:
        for index, rule in enumerate((spec.get(section) or {}).get("rules") or []):
            if isinstance(rule, dict):
                yield f"{section}.rules[{index}]", rule
    for index, rule in enumerate(spec.get("global_rules") or []):
        if isinstance(rule, dict):
            yield f"global_rules[{index}]", rule


def spec_problems(
    spec: dict[str, Any], contract: dict[str, Any], tools: list[dict[str, Any]], check: _Checker,
) -> PhoneAgentSpec | None:
    """Run the extra checks, ``parse_spec`` and a dry render; return the parsed spec when clean."""
    check_spec_data(spec, check)
    try:
        parsed = parse_spec(spec)
    except SpecError as exc:
        check.error(_path_in(str(exc)), str(exc))
        return None
    try:
        from .workflow import build_spec_workflow  # local import: workflow imports spec helpers

        build_spec_workflow(parsed, tools, [])
    except (SpecError, KeyError, ValueError) as exc:
        check.error(_path_in(str(exc)), f"render check: {exc}")
        return None
    return parsed if not check.errors else None


_SECTION_IN_TEXT = re.compile(
    r"(?<![A-Za-z0-9_])(" + "|".join(sorted(SECTION_GROUP, key=len, reverse=True)) + r")(?=[.\[\s:'\"]|$)"
)


def _path_in(message: str) -> str:
    """Best-effort spec path named in an error message (``$`` when none)."""
    match = _SECTION_IN_TEXT.search(message.replace("special path", "special_paths"))
    return match.group(1) if match else "$"


def group_of(path: str) -> str | None:
    head = re.split(r"[.\[]", path, maxsplit=1)[0]
    return SECTION_GROUP.get(head)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class _Conversation:
    def __init__(self, group: Group, context: str) -> None:
        self.group = group
        self.messages: list[dict[str, Any]] = [{
            "role": "user",
            "content": [text_block(context, cache=True), text_block(_task_text(group))],
        }]
        self.reply: dict[str, Any] | None = None
        self.parse_error = ""

    def ask(self, client: ModelClient, purpose: str) -> None:
        result = client.complete(EXTRACTION_SYSTEM_PROMPT.text, self.messages, purpose)
        self.messages.append({"role": "assistant", "content": result.text or "(empty reply)"})
        try:
            self.reply = _parse_json(result.text)
            self.parse_error = ""
        except (ValueError, json.JSONDecodeError) as exc:
            self.reply = None
            self.parse_error = f"the reply was not one valid JSON object ({exc})"

    def repair(self, client: ModelClient, errors: list[str], purpose: str) -> None:
        self.messages.append({"role": "user", "content": render_prompt(
            EXTRACT_REPAIR_TEMPLATE, errors="\n".join("- " + error for error in errors)
        )})
        self.ask(client, purpose)


def _task_text(group: Group) -> str:
    if group.task is EXTRACT_OUTCOMES_TASK:
        return render_prompt(EXTRACT_OUTCOMES_TASK, states=CLOSE_STATE_GUIDE.text)
    return group.task.text


def _parallel(function: Callable[[Any], Any], items: list[Any]) -> list[Any]:
    if len(items) <= 1:
        return [function(item) for item in items]
    with ThreadPoolExecutor(max_workers=len(items)) as pool:
        return list(pool.map(function, items))


def _compact(spec: dict[str, Any]) -> str:
    return json.dumps(
        {key: value for key, value in spec.items() if key not in {"provenance", "overrides"}},
        ensure_ascii=False, separators=(",", ":"),
    )


def extract_spec(
    documents: list[tuple[str, str]],
    openapi: dict[str, Any],
    client: ModelClient,
    log: Log = lambda key, value: None,
) -> ExtractionResult:
    """Extract, validate, repair and coverage-check a spec. Raises ``ExtractionError``."""
    contract = tool_contract(openapi)
    tools = tools_from_openapi(openapi, warnings=[])
    brief = "\n\n".join(text for _, text in documents)
    openapi_strings = set(_strings(openapi))
    context = context_text(documents, contract)
    conversations = {group.name: _Conversation(group, context) for group in GROUPS}
    log("extract", f"groups={len(GROUPS)} parallel=yes items={len(brief_items(documents))}")
    _parallel(lambda conv: conv.ask(client, f"extract:{conv.group.name}"), list(conversations.values()))

    candidate: dict[str, Any] | None = None
    parsed: PhoneAgentSpec | None = None
    check = _Checker(brief, contract, openapi_strings)
    for round_number in range(MAX_REPAIR_ROUNDS + 1):
        check = _Checker(brief, contract, openapi_strings, spoken_soft=round_number == MAX_REPAIR_ROUNDS)
        failing: dict[str, list[str]] = {}
        for name, conversation in conversations.items():
            if conversation.reply is None:
                failing[name] = [conversation.parse_error]
                continue
            group_check = _Checker(brief, contract, openapi_strings)
            GROUP_CHECKS[name](conversation.reply, group_check)
            if group_check.errors:
                failing[name] = [f"{path}: {message}" for path, message in group_check.errors]
        if not failing:
            replies = {name: conversation.reply for name, conversation in conversations.items()}
            _cross_group_checks(replies, check)
            candidate = merge_groups(replies)
            parsed = spec_problems(candidate, contract, tools, check)
            for path, message in check.errors:
                owner = group_of(path)
                for name in ([owner] if owner else list(conversations)):
                    failing.setdefault(name, []).append(f"{path}: {message}")
        log("extract_round", f"round={round_number} failing_groups={','.join(sorted(failing)) or 'none'} "
            f"errors={sum(len(errors) for errors in failing.values())}")
        # The errors themselves, so first-round failure types can be studied after a live run.
        issues = [f"[{name}] {error}" for name, errors in sorted(failing.items()) for error in errors]
        for issue in issues[:MAX_LOGGED_ISSUES]:
            log("extract_issue", f"round={round_number} {issue}"[:300])
        if len(issues) > MAX_LOGGED_ISSUES:
            log("extract_issue", f"round={round_number} ... {len(issues) - MAX_LOGGED_ISSUES} more")
        if not failing and parsed is not None:
            break
        if round_number == MAX_REPAIR_ROUNDS:
            problems = [f"[{name}] {error}" for name, errors in sorted(failing.items()) for error in errors]
            for problem in problems:
                log("extract_error", problem)
            raise ExtractionError(
                f"spec extraction failed after {MAX_REPAIR_ROUNDS} repair rounds; {len(problems)} problem(s), "
                f"first: {problems[0] if problems else '(none listed)'}",
                problems, candidate,
            )
        _parallel(
            lambda item: conversations[item[0]].repair(client, item[1], f"repair{round_number + 1}:{item[0]}"),
            sorted(failing.items()),
        )

    assert candidate is not None and parsed is not None
    warnings = [f"{path}: {message}" for path, message in check.warnings]
    for warning in warnings:
        log("extract_warning", warning)
    candidate, parsed, unmapped = _coverage(documents, context, candidate, parsed, contract, tools, brief,
                                            openapi_strings, client, log)
    _log_tiers(candidate, log)
    return ExtractionResult(candidate, parsed, warnings, unmapped)


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

_PATH_PART = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]")


def resolve_path(spec: dict[str, Any], path: str) -> bool:
    value: Any = spec
    text = path.strip().removeprefix("$.").removeprefix("$")
    position = 0
    for match in _PATH_PART.finditer(text):
        between = text[position:match.start()].strip(".")
        if between:
            return False
        position = match.end()
        key, index = match.group(1), match.group(2)
        if key is not None:
            if not isinstance(value, dict) or key not in value:
                return False
            value = value[key]
        else:
            if not isinstance(value, list) or int(index) >= len(value):
                return False
            value = value[int(index)]
    return position > 0 and not text[position:].strip(".")


def _coverage(
    documents, context, candidate, parsed, contract, tools, brief, openapi_strings, client, log,
):
    items = brief_items(documents)
    by_id = dict(items)
    item_text = "\n".join(f"{number}: {text}" for number, text in items)

    def call(task: str, purpose: str) -> dict[str, Any] | None:
        messages = [{"role": "user", "content": [text_block(context, cache=True), text_block(task)]}]
        # Coverage improves a valid spec; it never blocks it. Each failure is traced by kind.
        try:
            text = client.complete(EXTRACTION_SYSTEM_PROMPT.text, messages, purpose).text
        except LLMError as exc:
            return failed(purpose, "model_call", str(exc))
        except Exception as exc:
            return failed(purpose, "internal", f"{type(exc).__name__}: {exc}")
        try:
            reply = _parse_json(text)
        except ValueError as exc:  # json.JSONDecodeError is a ValueError
            return failed(purpose, "invalid_json", str(exc))
        if not isinstance(reply.get(shape_key[purpose]), list):
            return failed(purpose, "bad_shape", f"no {shape_key[purpose]!r} array in the reply")
        return reply

    shape_key = {"coverage": "items", "coverage_followup": "additions"}

    def failed(purpose: str, kind: str, detail: str) -> None:
        log("coverage_error", f"purpose={purpose} kind={kind} detail={detail[:200]}")
        return None

    reply = call(render_prompt(COVERAGE_TASK_TEMPLATE, items=item_text, spec=_compact(candidate)), "coverage")
    if reply is None:
        unmapped = [f"{number}: {text}" for number, text in items]
        log("coverage", f"items={len(items)} check=failed; all items unverified")
        for number, text in items:
            log("coverage_unmapped", f"{number}: {text}"[:200])
        candidate["coverage"] = {"items": len(items), "unmapped": unmapped, "check": "not run"}
        return candidate, parsed, unmapped
    status: dict[int, str] = {}
    for entry in reply.get("items", []) if isinstance(reply.get("items"), list) else []:
        number = _item_id(entry.get("id")) if isinstance(entry, dict) else None
        if number not in by_id:
            continue
        state = entry.get("status")
        paths = entry.get("paths") if isinstance(entry.get("paths"), list) else []
        if state == "covered" and not any(isinstance(path, str) and resolve_path(candidate, path) for path in paths):
            state = "missing"
        status[number] = state if state in {"covered", "not_relevant", "missing"} else "missing"
    missing = [number for number, _ in items if status.get(number, "missing") == "missing"]
    log("coverage", f"items={len(items)} covered={sum(1 for v in status.values() if v == 'covered')} "
        f"not_relevant={sum(1 for v in status.values() if v == 'not_relevant')} missing={len(missing)}")
    if missing:
        followup = call(render_prompt(
            COVERAGE_FOLLOWUP_TEMPLATE,
            items="\n".join(f"{number}: {by_id[number]}" for number in missing),
            spec=_compact(candidate),
        ), "coverage_followup")
        if followup is not None:
            candidate, parsed, settled = _apply_additions(
                candidate, parsed, followup, contract, tools, brief, openapi_strings, log,
            )
            missing = [number for number in missing if number not in settled]
    unmapped = [f"{number}: {by_id[number]}" for number in missing]
    for line in unmapped:
        log("coverage_unmapped", line[:200])
    candidate["coverage"] = {
        "items": len(items), "unmapped": unmapped,
    }
    return candidate, parsed, unmapped


def _item_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _add(spec: dict[str, Any], addition: dict[str, Any]) -> bool:
    target, value = addition.get("target"), addition.get("value")
    if not isinstance(target, str) or not isinstance(value, dict):
        return False
    if target in {"global_rules", "special_paths", "outcomes"}:
        if target == "outcomes":
            value = {"on": [], **value}
            value.pop("states", None)
        spec[target].append(value)
        return True
    stage, _, rest = target.partition(".")
    if stage in STAGE_NAMES and rest == "rules" and isinstance(spec.get(stage), dict):
        spec[stage].setdefault("rules", []).append(value)
        return True
    return False


def _apply_additions(candidate, parsed, reply, contract, tools, brief, openapi_strings, log):
    """Apply re-ask additions that keep the spec valid; return the item ids now settled."""
    settled: set[int] = set()
    for entry in reply.get("not_relevant", []) if isinstance(reply.get("not_relevant"), list) else []:
        number = _item_id(entry.get("item")) if isinstance(entry, dict) else None
        if number is not None:
            settled.add(number)
            log("coverage_not_relevant", f"{number}: {str(entry.get('why', ''))[:160]}")
    additions = [item for item in reply.get("additions", []) if isinstance(item, dict)] \
        if isinstance(reply.get("additions"), list) else []
    # Outcome rows first, so a special path that needs a new row can be added after it.
    additions.sort(key=lambda item: 0 if item.get("target") == "outcomes" else 1)

    def valid(spec: dict[str, Any]) -> PhoneAgentSpec | None:
        return spec_problems(spec, contract, tools, _Checker(brief, contract, openapi_strings))

    trial = copy.deepcopy(candidate)
    applied = [item for item in additions if _add(trial, item)]
    checked = valid(trial) if applied else None
    if checked is not None:
        candidate, parsed = trial, checked
        kept = applied
    else:
        kept = []
        for item in additions:
            attempt = copy.deepcopy(candidate)
            if not _add(attempt, item):
                log("coverage_rejected", f"target={item.get('target')!r}: unsupported target")
                continue
            checked = valid(attempt)
            if checked is None:
                log("coverage_rejected", f"target={item.get('target')!r}: breaks validation")
                continue
            candidate, parsed = attempt, checked
            kept.append(item)
    for item in kept:
        ids = [number for number in map(_item_id, item.get("items") or []) if number is not None]
        settled.update(ids)
        log("coverage_added", f"target={item.get('target')} items={ids}")
    return candidate, parsed, settled


def _log_tiers(spec: dict[str, Any], log: Log) -> None:
    """Enforcement tiers (ARCHITECTURE.md): code data, step prompt rules, global prompt rules."""
    step_rules = sum(len((spec.get(section) or {}).get("rules") or []) for section in STAGE_NAMES)
    log("rule_tiers", (
        f"code: identity questions={len(spec['identity'].get('questions', []))}, outcome rows={len(spec['outcomes'])}, "
        f"special paths={len(spec['special_paths'])}, offer limits=calendar+dates+amounts; "
        f"step_prompt rules={step_rules}; global_prompt rules={len(spec.get('global_rules') or [])}"
    ))
