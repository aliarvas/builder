"""Callback booking by code (F-055): the model never types a callback date or time.

The third-party step only copies the person's words for the day and the time into two
variables. ``callback_check`` (a code step) resolves them against the call's ``now`` with
the offer resolver (``offer_check.PRELUDE``), checks the spec's callback window
(``third_party.callback_window``) and then books through ``callback_book`` (the engine runs
``schedule_callback`` with the checked values), or goes to ``third_party_ask`` (a copy of the
third-party step that says why and asks again), or closes with the spec's close value after
too many times that cannot be booked. Every window value is spec data.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .offer_check import PRELUDE, _py_literal
from .prompts import (
    CALLBACK_COLLECT_RULE,
    CALLBACK_DAY_DESCRIPTION,
    CALLBACK_OUTSIDE_SAY,
    CALLBACK_TIME_ASK_SAY,
    CALLBACK_TIME_DESCRIPTION,
    CALLBACK_UNCLEAR_SAY,
    THIRD_PARTY_CLOSE_KIND_DESCRIPTION,
    THIRD_PARTY_CLOSE_REASK_SAY,
    THIRD_PARTY_INTENT_DESCRIPTION,
    render_prompt,
)
from .spec import FRAMEWORK_NONE_VALUE, OFFER_UNITS, PhoneAgentSpec, SpecError
from .tools_from_openapi import CALL_VARIABLES

CALLBACK_TOOL = "schedule_callback"
CALLBACK_CHECK = "callback_check"
CALLBACK_BOOK = "callback_book"
DAY_TEXT = "callback_day_text"
TIME_TEXT = "callback_time_text"
CALLBACK_DATE = "callback_date"
CALLBACK_TIME = "callback_time"
VERDICT = "callback_verdict"
MESSAGE = "callback_message"
OUTSIDE_COUNT = "callback_outside_count"
UNCLEAR_COUNT = "callback_unclear_count"
THIRD_PARTY_ASK = "third_party_ask"
THIRD_PARTY_CLOSE_CHECK = "third_party_close_check"
THIRD_PARTY_CLOSE_KIND = "third_party_close_kind"
THIRD_PARTY_CLOSE_COUNT = "third_party_close_reask_count"
THIRD_PARTY_CLOSE_VERDICT = "third_party_close_verdict"
THIRD_PARTY_CLOSE_EXPLICIT = "explicit_close"
THIRD_PARTY_CLOSE_OTHER = "other"
THIRD_PARTY_CLOSE_NOW = "close_now"
THIRD_PARTY_CLOSE_REASK = "reask_once"
# Verdicts of callback_check (prefixed so they never read as brief values).
WINDOW_OK, WINDOW_OUTSIDE, WINDOW_UNCLEAR, WINDOW_GIVE_UP, WINDOW_NEED_TIME = (
    "window_ok", "window_outside", "window_unclear", "window_give_up", "window_need_time",
)
# The resolved day from an earlier turn (ISO), owned by callback_check.
DAY_KEPT = "callback_day_kept"
NEED_TIME_COUNT = "callback_need_time_count"
# The engine's failure counter for the booking step (pre_actions node).
BOOK_FAILURE_COUNT = CALLBACK_BOOK + "_failure_count"
_CLOCK = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")


def callback_window(spec: PhoneAgentSpec) -> dict[str, Any] | None:
    """The validated ``third_party.callback_window``, or None when the spec has none."""
    third = spec.third_party.data
    raw = third.get("callback_window")
    if raw is None or raw == {}:
        return None
    path = "third_party.callback_window"
    if not isinstance(raw, dict):
        raise SpecError(f"{path} must be an object")
    days = raw.get("days_ahead")
    if not isinstance(days, int) or isinstance(days, bool) or days < 0:
        raise SpecError(f"{path}.days_ahead must be a non-negative integer (0 = today only)")
    if raw.get("day_unit") not in OFFER_UNITS:
        raise SpecError(f"{path}.day_unit must be one of {list(OFFER_UNITS)}")
    times = []
    for key in ("earliest_time", "latest_time"):
        value = raw.get(key)
        if not isinstance(value, str) or not _CLOCK.fullmatch(value.strip()):
            raise SpecError(f"{path}.{key} must be a time HH:MM")
        hours, minutes = value.strip().split(":")
        times.append(int(hours) * 60 + int(minutes))
    if times[0] > times[1]:
        raise SpecError(f"{path}.earliest_time must not be after latest_time")
    after_now = raw.get("after_now", True)
    if not isinstance(after_now, bool):
        raise SpecError(f"{path}.after_now must be true or false")
    asks = raw.get("max_outside_asks", 0)
    if not isinstance(asks, int) or isinstance(asks, bool) or asks < 0:
        raise SpecError(f"{path}.max_outside_asks must be a non-negative integer")
    close_value = raw.get("outside_close_value", "")
    if not isinstance(close_value, str) or not close_value:
        raise SpecError(f"{path}.outside_close_value is required with a window: the third_party close value "
                        "used when the person keeps naming times that cannot be booked")
    if close_value not in third.get("close_values", []):
        raise SpecError(f"{path}.outside_close_value {close_value!r} must be one of third_party.close_values")
    return {
        "days_ahead": days, "day_unit": raw["day_unit"],
        "earliest": times[0], "latest": times[1], "after_now": after_now,
        "max_outside_asks": asks, "outside_close_value": close_value,
    }


def _name_words(name: str) -> set[str]:
    """``callbackDate``, ``callback_date``, ``callback-date`` -> {"callback", "date"}."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return {word.lower() for word in re.split(r"[\s_\-.]+", spaced) if word}


def _field_kind(name: str, prop: dict[str, Any], by_name: bool) -> str:
    """"datetime", "date", "time" or "" for one body field."""
    if by_name:
        words = _name_words(name)
        if words & {"datetime", "timestamp"} or {"date", "time"} <= words:
            return "datetime"
        if words & {"date", "day"}:
            return "date"
        if words & {"time", "hour", "clock"}:
            return "time"
        return ""
    text = " ".join((str(prop.get("description", "")), str(prop.get("format", "")))).lower()
    if re.search(r"date-?time|yyyy-mm-ddthh", text):
        return "datetime"
    if re.search(r"\bdate\b|yyyy", text):
        return "date"
    if re.search(r"\btime\b|hh:mm|\bhour", text):
        return "time"
    return ""


def _body_fields(tool: dict[str, Any]) -> tuple[str, str] | None:
    """(date field, time field) of the callback tool; both are the same field when the API
    takes one date-time value. Names decide first, descriptions and formats second."""
    properties = tool["function"]["parameters"]["properties"].get("body", {}).get("properties", {})
    for by_name in (True, False):
        kinds: dict[str, str] = {}
        for name, prop in properties.items():
            if name in CALL_VARIABLES:
                continue
            kind = _field_kind(name, prop if isinstance(prop, dict) else {}, by_name)
            kinds.setdefault(kind, name)
        if "date" in kinds and "time" in kinds:
            return kinds["date"], kinds["time"]
        if "datetime" in kinds:
            return kinds["datetime"], kinds["datetime"]
    return None


def _book_tool(tool: dict[str, Any], date_field: str, time_field: str) -> dict[str, Any]:
    result = copy.deepcopy(tool)
    body = result["function"]["parameters"]["properties"]["body"]
    if date_field == time_field:
        # One date-time field: ISO date and time; callback_check sets both before booking.
        body["properties"][date_field]["default"] = "{{" + CALLBACK_DATE + "}}T{{" + CALLBACK_TIME + "}}:00"
    else:
        body["properties"][date_field]["default"] = "{{" + CALLBACK_DATE + "}}"
        body["properties"][time_field]["default"] = "{{" + CALLBACK_TIME + "}}"
    required = [field for field in body.get("required", []) if field not in (date_field, time_field)]
    if required:
        body["required"] = required
    else:
        body.pop("required", None)
    # Write tool: the engine does not retry; the closing rules read the result.
    result.setdefault("config", {})["maxRetries"] = 0
    return result


CHECK_BODY = r'''
UNIT_WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven',
              'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen']
TENS_WORDS = dict(twenty=20, thirty=30, forty=40, fifty=50)
WEEKDAY_WORDS = '|'.join(name.lower() for name in WEEKDAYS)
MONTH_WORDS = '|'.join(sorted([name.lower() for name in MONTHS] + [name[:3].lower() for name in MONTHS], key=len, reverse=True))
ORDINAL = r'\d{1,2}(?:st|nd|rd|th)?'
# Words that name a day. A bare number is never a day here: it is read as a time.
DAY_PATTERN = (r'\b(\d{4}-\d{1,2}-\d{1,2}|day after tomorrow|tomorrow|today|tonight|'
               r'this (?:morning|afternoon|evening)|later today|'
               r'(?:next |this )?(?:' + WEEKDAY_WORDS + r')(?: the ' + ORDINAL + r')?|'
               r'(?:the )?' + ORDINAL + r' (?:of )?(?:' + MONTH_WORDS + r')|(?:' + MONTH_WORDS + r') (?:the )?' + ORDINAL + r'|'
               r'the \d{1,2}(?:st|nd|rd|th))\b')
DURATION = re.compile(r'\b(?:in|within|after)\s+(?:an?|half an?|a few|\d+|[a-z]+)\s+(?:hours?|minutes?|mins?)\b'
                      r'|\b(?:hours?|minutes?|mins?)\s+from now\b|\bhalf an hour\b')


def day_words(text):
    # The first day named in text, resolved against now; None when no day is named.
    lowered = re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 -]+', ' ', str(text or '').lower()))
    for match in re.finditer(DAY_PATTERN, lowered):
        part = match.group(1)
        if part in ('tonight', 'later today') or part.startswith('this ') and part.split(' ')[1] in ('morning', 'afternoon', 'evening'):
            return today()
        day = resolve_offer_day(re.sub(r'^the ', '', part))
        if day is not None:
            return day
    return None


def named_day(day_text, time_text):
    # The day this turn names: the day field first, then day words in the time field.
    if day_text.strip():
        day = resolve_offer_day(day_text)
        if day is None:
            day = day_words(day_text)
        if day is not None:
            return day
    return day_words(time_text)


def number_value(words, index):
    # (value, words used) for a number at words[index], or (None, 0).
    word = words[index]
    if word.isdigit():
        return int(word), 1
    if word in TENS_WORDS:
        value = TENS_WORDS[word]
        if index + 1 < len(words) and words[index + 1] in UNIT_WORDS[1:10]:
            return value + UNIT_WORDS.index(words[index + 1]), 2
        return value, 1
    if word in UNIT_WORDS:
        return UNIT_WORDS.index(word), 1
    return None, 0


def clock_candidates(text):
    # Minutes after midnight that the words can mean; [] when no single clock time is named.
    text = str(text or '').lower()
    text = re.sub(r'\b([ap])\.?\s?m\b\.?', r'\1m', text)
    text = re.sub(r'(\d)\.(\d{2})\b', r'\1:\2', text)
    if DURATION.search(text):
        return []
    meridiem = ''
    found = re.search(r'(?:\b|\d)(am|pm)\b', text)
    if found:
        meridiem = found.group(1)
    elif re.search(r'\bmorning\b', text):
        meridiem = 'am'
    elif re.search(r'\b(afternoon|evening|tonight)\b', text):
        meridiem = 'pm'
    text = re.sub(DAY_PATTERN, ' ', text)
    text = re.sub(r'\d{4}-\d{1,2}-\d{1,2}', ' ', text)
    text = re.sub(r"o'?clock", ' ', text)

    def past_to(match):
        value, used = number_value([match.group(3)], 0)
        if value is None:
            return match.group(0)
        if match.group(2) == 'to':
            return ' %d:%02d ' % ((value - 1) % 24, 45 if match.group(1) == 'quarter' else 30)
        return ' %d:%02d ' % (value, 30 if match.group(1) == 'half' else 15)

    text = re.sub(r'\b(half|quarter) (past|to) (\d{1,2}|[a-z]+)\b', past_to, text)
    words = re.findall(r'\d{1,2}:\d{2}|\d+|[a-z]+', text)
    clocks = []
    index = 0
    while index < len(words):
        word = words[index]
        if ':' in word:
            hour, minute = (int(part) for part in word.split(':'))
            clocks.append((hour, minute))
            index += 1
            continue
        value, used = number_value(words, index)
        if value is None:
            index += 1
            continue
        if value > 23:
            return []
        hour, minute = value, 0
        index += used
        if index < len(words):
            if words[index] == 'oh' and index + 1 < len(words):
                later, later_used = number_value(words, index + 1)
                if later is not None and later < 10:
                    minute = later
                    index += 1 + later_used
            else:
                later, later_used = number_value(words, index)
                spoken = not words[index].isdigit() and later is not None and later >= 10
                digits = words[index].isdigit() and len(words[index]) == 2
                if later is not None and later <= 59 and (spoken or digits):
                    minute = later
                    index += later_used
        clocks.append((hour, minute))
    if not clocks and re.search(r'\b(noon|midday)\b', text):
        return [12 * 60]
    if len(clocks) != 1:
        return []
    hour, minute = clocks[0]
    if hour > 23 or minute > 59:
        return []
    if meridiem == 'pm' and hour < 12:
        return [(hour + 12) * 60 + minute]
    if meridiem == 'am':
        return [(hour % 12) * 60 + minute]
    if hour == 0 or hour > 12:
        return [hour * 60 + minute]
    return [hour * 60 + minute, ((hour % 12) + 12) * 60 + minute]


def window_days(start):
    days = [start]
    if WINDOW['day_unit'] == 'business':
        day = start
        for _ in range(400):
            if len(days) > WINDOW['days_ahead']:
                break
            day = day + datetime.timedelta(days=1)
            if is_business(day):
                days.append(day)
    else:
        days.extend(start + datetime.timedelta(days=step) for step in range(1, WINDOW['days_ahead'] + 1))
    return days


def now_minutes():
    match = re.search(r'[T ](\d{1,2}):(\d{2})', str(vars.get(OFFER['today_variable']) or ''))
    return int(match.group(1)) * 60 + int(match.group(2)) if match else None


def in_window(day, minutes):
    if WINDOW is None:
        return day >= today()
    if day not in window_days(today()):
        return False
    if minutes < WINDOW['earliest'] or minutes > WINDOW['latest']:
        return False
    current = now_minutes()
    if WINDOW['after_now'] and day == today() and current is not None and minutes <= current:
        return False
    return True


def say_clock(minutes):
    return '%02d:%02d' % (minutes // 60, minutes % 60)


def bump(name):
    try:
        count = int(vars.get(name) or 0) + 1
    except Exception:
        count = 1
    vars[name] = count
    return count


try:
    day_text = str(vars.get(CALLBACK['day_text']) or '')
    time_text = str(vars.get(CALLBACK['time_text']) or '')
    vars[CALLBACK['day_text']] = ''
    vars[CALLBACK['time_text']] = ''
    # A day named in an earlier turn is kept here, by code: extraction may empty the day
    # field when the next message names only the time.
    kept = parse_day(vars.get(CALLBACK['day_kept']))
    fresh = named_day(day_text, time_text)
    day_changed = fresh is not None and fresh != kept
    if fresh is not None:
        kept = fresh
        vars[CALLBACK['day_kept']] = fresh.isoformat()
    if fresh is not None:
        day = fresh
    elif day_text.strip():
        day = None  # this turn's day words name no day
    elif kept is not None:
        day = kept
    else:
        day = today()  # no day named in any turn
    # The time is read from the time field; the day field only when no time field was given.
    candidates = clock_candidates(time_text if time_text.strip() else day_text)
    verdict = CALLBACK['verdict_unclear']
    if day is not None and candidates:
        chosen = next((minutes for minutes in candidates if in_window(day, minutes)), None)
        if chosen is not None:
            verdict = CALLBACK['verdict_ok']
            vars[CALLBACK['date_var']] = day.isoformat()
            vars[CALLBACK['time_var']] = say_clock(chosen)
        else:
            verdict = CALLBACK['verdict_outside']
            if WINDOW is not None and day not in window_days(today()):
                vars[CALLBACK['day_kept']] = ''  # the day itself cannot be used again
    elif fresh is not None and not time_text.strip() and not clock_candidates(day_text):
        if WINDOW is not None and fresh not in window_days(today()):
            # A day alone that cannot be booked: say the window now and forget the day.
            verdict = CALLBACK['verdict_outside']
            vars[CALLBACK['day_kept']] = ''
        else:
            verdict = CALLBACK['verdict_need_time']  # a day alone: keep it and ask for the time
    if WINDOW is not None and verdict == CALLBACK['verdict_outside']:
        if bump(CALLBACK['outside_count']) > WINDOW['max_outside_asks']:
            verdict = CALLBACK['verdict_give_up']
    elif WINDOW is not None and verdict == CALLBACK['verdict_unclear']:
        if bump(CALLBACK['unclear_count']) > max(1, WINDOW['max_outside_asks']):
            verdict = CALLBACK['verdict_give_up']
    elif WINDOW is not None and verdict == CALLBACK['verdict_need_time'] and not day_changed:
        # Only a repeated day without a time counts; a corrected day is progress.
        if bump(CALLBACK['need_time_count']) > max(2, WINDOW['max_outside_asks']):
            verdict = CALLBACK['verdict_give_up']
    if verdict == CALLBACK['verdict_give_up']:
        vars[CALLBACK['intent_variable']] = WINDOW['outside_close_value']
    if verdict in (CALLBACK['verdict_ok'], CALLBACK['verdict_give_up']):
        vars[CALLBACK['day_kept']] = ''
    if verdict == CALLBACK['verdict_outside']:
        vars[CALLBACK['message_var']] = CALLBACK['outside_say']
    elif verdict == CALLBACK['verdict_need_time']:
        vars[CALLBACK['message_var']] = CALLBACK['time_ask_say']
    else:
        vars[CALLBACK['message_var']] = CALLBACK['unclear_say']
    vars[CALLBACK['verdict_var']] = verdict
except Exception:
    vars[CALLBACK['verdict_var']] = CALLBACK['verdict_unclear']
    vars[CALLBACK['message_var']] = CALLBACK['unclear_say']
'''


def _window_text(window: dict[str, Any] | None) -> str:
    if window is None:
        return "on a day and at a time that suits"
    days = window["days_ahead"]
    unit = "business day" if window["day_unit"] == "business" else "day"
    if days == 0:
        when = "today"
    elif days == 1:
        when = f"today or the next {unit}"
    else:
        when = f"today or one of the next {days} {unit}s"
    clock = lambda minutes: "%02d:%02d" % (minutes // 60, minutes % 60)
    return f"{when}, between {clock(window['earliest'])} and {clock(window['latest'])}"


def callback_check_code(spec: PhoneAgentSpec) -> str:
    """Code for ``callback_check``: resolve the person's words, check the window, set the verdict."""
    window = callback_window(spec)
    config = {
        "day_text": DAY_TEXT, "time_text": TIME_TEXT, "date_var": CALLBACK_DATE, "time_var": CALLBACK_TIME,
        "verdict_var": VERDICT, "message_var": MESSAGE, "outside_count": OUTSIDE_COUNT,
        "unclear_count": UNCLEAR_COUNT,
        "intent_variable": spec.third_party.data["intent_variable"],
        "verdict_ok": WINDOW_OK, "verdict_outside": WINDOW_OUTSIDE, "verdict_unclear": WINDOW_UNCLEAR,
        "verdict_give_up": WINDOW_GIVE_UP, "verdict_need_time": WINDOW_NEED_TIME,
        "day_kept": DAY_KEPT, "need_time_count": NEED_TIME_COUNT,
        "time_ask_say": CALLBACK_TIME_ASK_SAY.text,
        "outside_say": CALLBACK_OUTSIDE_SAY.text.replace("{window}", _window_text(window)),
        "unclear_say": CALLBACK_UNCLEAR_SAY.text,
    }
    offer = {key: value for key, value in spec.offer.data.items() if key != "rules"}
    return (
        PRELUDE.replace("__CONFIG__", _py_literal({"offer": offer}))
        .replace("__PRODUCT_READER__", "")
        + "CALLBACK = " + _py_literal(config) + "\n"
        + "WINDOW = " + _py_literal(window or dict()) + " or None\n"
        + f"vars[{THIRD_PARTY_CLOSE_KIND!r}] = {THIRD_PARTY_CLOSE_OTHER!r}\n"
        + CHECK_BODY
    )


def callback_extraction_fields() -> list[dict[str, Any]]:
    return [
        dict(name=DAY_TEXT, type="string", description=CALLBACK_DAY_DESCRIPTION.text, min_confidence=0.7),
        dict(name=TIME_TEXT, type="string", description=CALLBACK_TIME_DESCRIPTION.text, min_confidence=0.7),
    ]


def third_party_extraction_fields(third_party: dict[str, Any]) -> list[dict[str, Any]]:
    """Intent plus an independent explicit-close signal for the F-064 guard."""
    close_values = ", ".join(str(value) for value in third_party["close_values"])
    return [
        dict(
            name=third_party["intent_variable"], type="string",
            description=render_prompt(THIRD_PARTY_INTENT_DESCRIPTION, close_values=close_values),
            enum_values=[*third_party["intent_values"], FRAMEWORK_NONE_VALUE], min_confidence=0.8,
        ),
        dict(
            name=THIRD_PARTY_CLOSE_KIND, type="string",
            description=render_prompt(THIRD_PARTY_CLOSE_KIND_DESCRIPTION, close_values=close_values),
            enum_values=[THIRD_PARTY_CLOSE_EXPLICIT, THIRD_PARTY_CLOSE_OTHER], min_confidence=0.8,
        ),
    ]


def third_party_close_guard_code(spec: PhoneAgentSpec) -> str:
    """Re-ask once when a close intent is not backed by an independently explicit close."""
    config = {
        "intent": spec.third_party.data["intent_variable"],
        "kind": THIRD_PARTY_CLOSE_KIND,
        "explicit": THIRD_PARTY_CLOSE_EXPLICIT,
        "other": THIRD_PARTY_CLOSE_OTHER,
        "count": THIRD_PARTY_CLOSE_COUNT,
        "verdict": THIRD_PARTY_CLOSE_VERDICT,
        "verdict_close": THIRD_PARTY_CLOSE_NOW,
        "reask": THIRD_PARTY_CLOSE_REASK,
        "none": FRAMEWORK_NONE_VALUE,
        "message": MESSAGE,
        "reask_message": THIRD_PARTY_CLOSE_REASK_SAY.text,
    }
    # T-010 self-check: ``json`` is not pre-loaded in a code step; it must be imported.
    return "import json\nGUARD = " + _py_literal(config) + "\n" + '''try:
    kind = str(vars.get(GUARD['kind']) or '')
    try:
        count = int(vars.get(GUARD['count']) or 0)
    except Exception:
        count = 0
    should_reask = kind != GUARD['explicit'] and count < 1
    if should_reask:
        vars[GUARD['count']] = count + 1
        vars[GUARD['intent']] = GUARD['none']
        vars[GUARD['kind']] = GUARD['other']
        vars[GUARD['message']] = GUARD['reask_message']
        vars[GUARD['verdict']] = GUARD['reask']
    else:
        vars[GUARD['kind']] = GUARD['other']
        vars[GUARD['verdict']] = GUARD['verdict_close']
except Exception:
    vars[GUARD['count']] = 1
    vars[GUARD['intent']] = GUARD['none']
    vars[GUARD['kind']] = GUARD['other']
    vars[GUARD['message']] = GUARD['reask_message']
    vars[GUARD['verdict']] = GUARD['reask']
'''


def third_party_close_guard_node(spec: PhoneAgentSpec, code_node: Any, closing: str) -> dict[str, Any]:
    """Bounded gate between a third-party close intent and the closing chain."""
    return code_node(THIRD_PARTY_CLOSE_CHECK, third_party_close_guard_code(spec), [
        {
            "target_node": closing, "description": "Third party explicitly closed or bounded re-ask used",
            "condition": {"logic": "or", "conditions": [
                {"variable": THIRD_PARTY_CLOSE_VERDICT, "operator": "equals", "operand": THIRD_PARTY_CLOSE_NOW},
            ]},
        },
        {"target_node": THIRD_PARTY_ASK, "description": "Ask once more when the close was not explicit",
         "condition": {"operator": "always"}},
    ])


def callback_entry_transition() -> dict[str, Any]:
    """From the third-party step: the person named a callback day or time. A day alone is
    checked too, so code keeps it for the turn that brings the time (F-055 re-review)."""
    return {
        "target_node": CALLBACK_CHECK,
        "description": "The person named a callback day or time",
        "condition": {"logic": "or", "conditions": [
            {"logic": "and", "conditions": [
                {"variable": name, "operator": "is_set"},
                {"variable": name, "operator": "not_equals", "operand": ""},
            ]}
            for name in (TIME_TEXT, DAY_TEXT)
        ]},
    }


def third_party_ask_node(third_party: dict[str, Any]) -> dict[str, Any]:
    """A copy of the finished third-party step (same prompt, extraction, routes) whose entry
    is the fixed line from ``callback_check`` ({{callback_message}}), not the model.

    The model does not talk a second time (or claim a booking) after the line, and a global
    path that returns here (``__previous__``) hears the pending question again (F-053
    pattern, as ``offer_say``). The original step keeps its normal entry.
    """
    node = copy.deepcopy(third_party)
    node["name"] = THIRD_PARTY_ASK
    node["on_enter"] = dict(type="tts", text="{{" + MESSAGE + "}}")
    return node


def add_collect_rule(third_party: dict[str, Any]) -> None:
    """Tell the third-party step to collect the day and the time and never claim a booking."""
    third_party["task_message"] = third_party["task_message"].rstrip() + "\n" + CALLBACK_COLLECT_RULE.text


def callback_nodes(
    spec: PhoneAgentSpec, tool: dict[str, Any], code_node: Any, closing: str,
    warnings: list[str] | None = None,
) -> dict[str, dict[str, Any]] | None:
    """The check, say and book steps; None (with a warning) when the tool's date and time
    fields cannot be found, so the caller keeps the model-filled tool. A time that cannot be
    booked goes to ``third_party_ask`` (see ``third_party_ask_node``), which says why."""
    fields = _body_fields(tool)
    if fields is None:
        if warnings is not None:
            warnings.append(f"{CALLBACK_TOOL}: no date and time body fields found; the model fills them (F-055 not applied)")
        return None
    callback_window(spec)  # validate before rendering
    check = code_node(CALLBACK_CHECK, callback_check_code(spec), [
        {"target_node": CALLBACK_BOOK, "description": "Callback time is valid",
         "condition": {"logic": "or", "conditions": [
             {"variable": VERDICT, "operator": "equals", "operand": WINDOW_OK}]}},
        {"target_node": closing, "description": "Still outside the callback window",
         "condition": {"logic": "or", "conditions": [
             {"variable": VERDICT, "operator": "equals", "operand": WINDOW_GIVE_UP}]}},
        {"target_node": THIRD_PARTY_ASK, "description": "Ask for another time", "condition": {"operator": "always"}},
    ])
    book = {
        "name": CALLBACK_BOOK, "node_type": "api_request", "on_enter": dict(type="silent"),
        "passthrough": True, "passthrough_default_transition": closing,
        "pre_actions": [_book_tool(tool, *fields)],
        "response_mapping": [{"path": "data.ok", "variable": "callback_ok"}],
        "transitions": [
            {"target_node": closing, "description": "Callback booking finished",
             "condition": {"operator": "always"}},
        ],
    }
    return {CALLBACK_CHECK: check, CALLBACK_BOOK: book}
