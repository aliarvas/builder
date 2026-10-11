"""F-055: callback day and time resolved and checked in code, never typed by the model (offline)."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from builder import callback
from builder.extract import _Checker, _check_callback_window, _clock_in_brief, merge_groups
from builder.spec import SpecError, parse_spec, spec_entry_variables
from builder.tools_from_openapi import CALL_VARIABLES, tools_from_openapi
from builder.workflow import build_spec_workflow, close_rules
from tests.extract_helpers import groups_from_spec


ROOT = Path(__file__).resolve().parents[1]
SPEC_A = json.loads((ROOT / "tests/fixtures/spec-brief-a.json").read_text(encoding="utf-8"))
OPENAPI = json.loads((ROOT / "build-the-builder-v2/tools/openapi.json").read_text(encoding="utf-8"))
# A window of the same shape as a "today or the next business day, 10:00 to 19:00" rule.
WINDOW = {
    "days_ahead": 1, "day_unit": "business", "earliest_time": "10:00", "latest_time": "19:00",
    "after_now": True, "max_outside_asks": 1, "outside_close_value": "no_callback",
}


def spec_with(window=WINDOW):
    data = copy.deepcopy(SPEC_A)
    if window is not None:
        data["third_party"]["callback_window"] = copy.deepcopy(window)
    return parse_spec(data)


def render(spec, document=OPENAPI, warnings=None):
    tools = tools_from_openapi(document, known_entry_variables=CALL_VARIABLES | spec_entry_variables(spec))
    return build_spec_workflow(spec, tools, warnings)


def code_of(node):
    return next(a for a in node["pre_actions"] if a["function"]["name"] == "code_exec")["function"][
        "parameters"]["properties"]["code"]["default"]


def check(spec, day, time, now="2026-10-14T11:00", extra=None):
    """Run callback_check once; return the variables it left."""
    code = code_of(render(spec)["nodes"][callback.CALLBACK_CHECK])
    variables = {"now": now, callback.DAY_TEXT: day, callback.TIME_TEXT: time, **(extra or {})}
    exec(code, {"vars": variables, "json": json})
    return variables


def close_guard(spec, intent, kind, extra=None):
    """Run the F-064 third-party close guard once."""
    code = code_of(render(spec)["nodes"][callback.THIRD_PARTY_CLOSE_CHECK])
    variables = {
        spec.third_party.data["intent_variable"]: intent,
        callback.THIRD_PARTY_CLOSE_KIND: kind,
        **(extra or {}),
    }
    exec(code, {"vars": variables, "json": json})
    return variables


def holds(condition, variables):
    if "logic" in condition:
        answers = [holds(item, variables) for item in condition["conditions"]]
        return all(answers) if condition["logic"] == "and" else any(answers)
    operator = condition["operator"]
    if operator == "always":
        return True
    value = variables.get(condition.get("variable"))
    if operator == "is_set":
        return value not in (None, "")
    if operator == "equals":
        return value not in (None, "") and str(value) == str(condition.get("operand"))
    if operator == "not_equals":
        return not (value not in (None, "") and str(value) == str(condition.get("operand")))
    return False


class ThirdPartySession:
    """Stateful walk through the rendered third-party conversation and code routes."""

    def __init__(self, spec):
        self.spec = spec
        self.nodes = render(spec)["nodes"]
        self.vars, self.path, self.step = {"now": "2026-10-14T11:00"}, [], "third_party"

    def route(self, key):
        self.path.append(key)
        for transition in self.nodes[key]["transitions"]:
            if holds(transition["condition"], self.vars):
                return transition["target_node"]
        return key

    def say(self, intent, kind, **extracted):
        self.vars[self.spec.third_party.data["intent_variable"]] = intent
        self.vars[callback.THIRD_PARTY_CLOSE_KIND] = kind
        self.vars.update(extracted)
        target = self.route(self.step)
        while target != "closing" and self.nodes[target]["node_type"] == "code":
            exec(code_of(self.nodes[target]), {"vars": self.vars, "json": json})
            target = self.route(target)
        self.step = target
        return self


class ResolveAndWindowTests(unittest.TestCase):
    """now = Wednesday 2026-10-14 11:00; Monday 2026-10-26 is a holiday in the fixture."""

    def assert_booked(self, variables, date, time):
        self.assertEqual(callback.WINDOW_OK, variables[callback.VERDICT])
        self.assertEqual((date, time), (variables[callback.CALLBACK_DATE], variables[callback.CALLBACK_TIME]))

    def test_f055_tomorrow_morning_eleven_uses_the_call_date(self):
        self.assert_booked(check(spec_with(), "tomorrow", "around eleven in the morning"), "2026-10-15", "11:00")
        # The whole phrase in the day field, nothing in the time field.
        self.assert_booked(check(spec_with(), "tomorrow morning around eleven", ""), "2026-10-15", "11:00")

    def test_time_forms(self):
        for words, expected in (("3pm", "15:00"), ("14:30", "14:30"), ("half past three", "15:30"),
                                ("noon", "12:00"), ("2", "14:00"), ("at 4 in the afternoon", "16:00"),
                                ("10.15 am", "10:15")):
            with self.subTest(words=words):
                self.assert_booked(check(spec_with(), "tomorrow", words), "2026-10-15", expected)

    def test_today_must_be_later_than_now(self):
        self.assertEqual(callback.WINDOW_OUTSIDE, check(spec_with(), "today", "10am")[callback.VERDICT])
        self.assert_booked(check(spec_with(), "today", "3pm"), "2026-10-14", "15:00")

    def test_outside_hours_or_days(self):
        for day, time in (("tomorrow", "8"), ("tomorrow", "9am"), ("tomorrow", "8pm"), ("Friday", "11am")):
            with self.subTest(day=day, time=time):
                variables = check(spec_with(), day, time)
                self.assertEqual(callback.WINDOW_OUTSIDE, variables[callback.VERDICT])
                self.assertIn("today or the next business day, between 10:00 and 19:00", variables[callback.MESSAGE])
                self.assertNotIn(callback.CALLBACK_DATE, variables)

    def test_next_business_day_skips_weekend_and_holiday(self):
        friday = "2026-10-23T11:00"  # next business day: Tuesday 27 (Monday 26 is a holiday)
        self.assertEqual(callback.WINDOW_OUTSIDE, check(spec_with(), "Monday", "11am", now=friday)[callback.VERDICT])
        self.assert_booked(check(spec_with(), "Tuesday", "11am", now=friday), "2026-10-27", "11:00")

    def test_second_offer_outside_gives_up_with_the_spec_close_value(self):
        first = check(spec_with(), "Friday", "11am")
        self.assertEqual(callback.WINDOW_OUTSIDE, first[callback.VERDICT])
        second = check(spec_with(), "Monday", "noon", extra={callback.OUTSIDE_COUNT: first[callback.OUTSIDE_COUNT]})
        self.assertEqual(callback.WINDOW_GIVE_UP, second[callback.VERDICT])
        self.assertEqual("no_callback", second[SPEC_A["third_party"]["intent_variable"]])

    def test_unclear_words_ask_again_and_are_counted_separately(self):
        variables = check(spec_with(), "sometime", "whenever")
        self.assertEqual(callback.WINDOW_UNCLEAR, variables[callback.VERDICT])
        self.assertNotIn(callback.OUTSIDE_COUNT, variables)
        self.assertEqual(1, variables[callback.UNCLEAR_COUNT])
        self.assertEqual(callback.CALLBACK_UNCLEAR_SAY.text, variables[callback.MESSAGE])

    def test_repeated_unclear_answers_give_up(self):
        # Review 7a: unclear tries are counted; the limit is max(1, max_outside_asks).
        variables = check(spec_with(), "", "whenever", extra={callback.UNCLEAR_COUNT: 1})
        self.assertEqual(callback.WINDOW_GIVE_UP, variables[callback.VERDICT])
        self.assertEqual("no_callback", variables[SPEC_A["third_party"]["intent_variable"]])

    def test_whole_phrase_in_the_time_field_keeps_its_day(self):
        # Review finding 1: an empty day field is unknown, not today.
        self.assert_booked(check(spec_with(), "", "tomorrow at 3pm"), "2026-10-15", "15:00")
        self.assert_booked(check(spec_with(), "", "tomorrow around eleven in the morning"), "2026-10-15", "11:00")
        self.assert_booked(check(spec_with(), "", "on the 15th at 3pm"), "2026-10-15", "15:00")
        self.assert_booked(check(spec_with(), "", "this afternoon at 4"), "2026-10-14", "16:00")
        self.assert_booked(check(spec_with(), "", "at 4pm"), "2026-10-14", "16:00")  # no day named: today

    def test_day_field_that_names_no_day_is_unclear(self):
        self.assertEqual(callback.WINDOW_UNCLEAR, check(spec_with(), "whenever", "3pm")[callback.VERDICT])

    def test_minute_words_and_spoken_minutes(self):
        # Review finding 2a.
        for words, expected in (("ten fifteen", "10:15"), ("four thirty", "16:30"), ("eleven thirty", "11:30"),
                                ("eleven oh five", "11:05"), ("quarter to four", "15:45"), ("10 30", "10:30"),
                                ("twelve forty five", "12:45")):
            with self.subTest(words=words):
                self.assert_booked(check(spec_with(), "tomorrow", words), "2026-10-15", expected)

    def test_durations_and_several_clock_numbers_are_unclear(self):
        # Review finding 2b, 2c: a wrong guess loses the case, one more question does not.
        for words in ("in two hours", "in an hour", "half an hour", "20 minutes from now",
                      "between 2 and 4", "2 or 3", "at 3 or maybe 5"):
            with self.subTest(words=words):
                variables = check(spec_with(), "tomorrow", words)
                self.assertEqual(callback.WINDOW_UNCLEAR, variables[callback.VERDICT])
                self.assertNotIn(callback.CALLBACK_DATE, variables)

    def test_hour_is_never_read_from_the_day_field_when_a_time_was_given(self):
        # Review finding 2d: "20 October" + "3 pm" is 15:00 on 20 October (outside: 4 business days ahead).
        window = {**WINDOW, "days_ahead": 5}
        self.assert_booked(check(spec_with(window), "20 October", "3 pm"), "2026-10-20", "15:00")
        self.assertEqual(callback.WINDOW_UNCLEAR, check(spec_with(), "the 15th", "whenever")[callback.VERDICT])

    def test_words_are_cleared_after_the_check(self):
        variables = check(spec_with(), "tomorrow", "11am")
        self.assertEqual(("", ""), (variables[callback.DAY_TEXT], variables[callback.TIME_TEXT]))

    def test_without_a_window_the_date_is_still_resolved_in_code(self):
        self.assert_booked(check(spec_with(None), "tomorrow", "eleven"), "2026-10-15", "11:00")

    def test_calendar_window_of_two_days(self):
        window = {**WINDOW, "days_ahead": 2, "day_unit": "calendar", "earliest_time": "09:00", "latest_time": "18:00"}
        self.assert_booked(check(spec_with(window), "Friday", "9am"), "2026-10-16", "09:00")
        self.assertEqual(callback.WINDOW_OUTSIDE, check(spec_with(window), "Saturday", "9am")[callback.VERDICT])


def turns(spec, *messages, now="2026-10-14T11:00"):
    """Run callback_check once per (day words, time words) turn on one variable table.

    Extraction empties both text fields on every turn (the worst case for memory); only
    what the code wrote survives from one turn to the next.
    """
    code = code_of(render(spec)["nodes"][callback.CALLBACK_CHECK])
    variables = {"now": now}
    for day, time in messages:
        variables[callback.DAY_TEXT], variables[callback.TIME_TEXT] = day, time
        exec(code, {"vars": variables})
    return variables


class TwoTurnTests(unittest.TestCase):
    """Re-review note 1: the day and the time arrive in separate messages."""

    def test_day_then_time_books_the_kept_day(self):
        first = turns(spec_with(), ("tomorrow", ""))
        self.assertEqual(callback.WINDOW_NEED_TIME, first[callback.VERDICT])
        self.assertEqual(callback.CALLBACK_TIME_ASK_SAY.text, first[callback.MESSAGE])
        self.assertEqual("2026-10-15", first[callback.DAY_KEPT])
        both = turns(spec_with(), ("tomorrow", ""), ("", "3pm"))
        self.assertEqual(callback.WINDOW_OK, both[callback.VERDICT])
        self.assertEqual(("2026-10-15", "15:00"), (both[callback.CALLBACK_DATE], both[callback.CALLBACK_TIME]))
        self.assertEqual("", both[callback.DAY_KEPT])  # cleared after booking

    def test_a_new_day_replaces_the_kept_one(self):
        result = turns(spec_with(), ("today", ""), ("", "tomorrow at 3pm"))
        self.assertEqual(("2026-10-15", "15:00"), (result[callback.CALLBACK_DATE], result[callback.CALLBACK_TIME]))

    def test_time_outside_keeps_the_day_for_the_next_time(self):
        result = turns(spec_with(), ("tomorrow", "8pm"), ("", "3pm"))
        self.assertEqual(callback.WINDOW_OK, result[callback.VERDICT])
        self.assertEqual(("2026-10-15", "15:00"), (result[callback.CALLBACK_DATE], result[callback.CALLBACK_TIME]))

    def test_day_outside_is_dropped(self):
        first = turns(spec_with(), ("Friday", "11am"))
        self.assertEqual(callback.WINDOW_OUTSIDE, first[callback.VERDICT])
        self.assertEqual("", first[callback.DAY_KEPT])
        # The next bare time is read for today, not for Friday again.
        second = turns(spec_with(), ("Friday", "11am"), ("", "4pm"))
        self.assertEqual(("2026-10-14", "16:00"), (second[callback.CALLBACK_DATE], second[callback.CALLBACK_TIME]))

    def test_without_any_day_a_bare_time_is_today(self):
        result = turns(spec_with(), ("", "4pm"))
        self.assertEqual("2026-10-14", result[callback.CALLBACK_DATE])

    def test_corrected_day_then_time_books_the_new_day(self):
        # Re-review 2 note 1: tomorrow (Thu 15) -> Thursday -> 11am books Thursday.
        result = turns(spec_with(), ("tomorrow", ""), ("Thursday", ""), ("", "11am"))
        self.assertEqual(callback.WINDOW_OK, result[callback.VERDICT])
        self.assertEqual(("2026-10-15", "11:00"), (result[callback.CALLBACK_DATE], result[callback.CALLBACK_TIME]))
        # From Tuesday 2026-10-13 "tomorrow" (Wed) then "Thursday" changes the kept day: not counted.
        window = {**WINDOW, "days_ahead": 2}
        changed = turns(spec_with(window), ("tomorrow", ""), ("Thursday", ""), ("", "11am"), now="2026-10-13T11:00")
        self.assertEqual(("2026-10-15", "11:00"), (changed[callback.CALLBACK_DATE], changed[callback.CALLBACK_TIME]))
        counted = turns(spec_with(window), ("tomorrow", ""), ("Thursday", ""), now="2026-10-13T11:00")
        self.assertNotIn(callback.NEED_TIME_COUNT, counted)

    def test_repeated_day_only_answers_are_bounded(self):
        # The first answer sets the day (not counted); repeats count, limit max(2, max_outside_asks) = 2.
        same = ("tomorrow", "")
        three = turns(spec_with(), same, same, same)
        self.assertEqual(callback.WINDOW_NEED_TIME, three[callback.VERDICT])
        self.assertEqual(2, three[callback.NEED_TIME_COUNT])
        four = turns(spec_with(), same, same, same, same)
        self.assertEqual(callback.WINDOW_GIVE_UP, four[callback.VERDICT])
        self.assertEqual("no_callback", four[SPEC_A["third_party"]["intent_variable"]])
        self.assertEqual("", four[callback.DAY_KEPT])

    def test_day_alone_outside_the_window_says_so_and_is_dropped(self):
        # Re-review 2 note 2.
        result = turns(spec_with(), ("Friday", ""))
        self.assertEqual(callback.WINDOW_OUTSIDE, result[callback.VERDICT])
        self.assertIn("today or the next business day", result[callback.MESSAGE])
        self.assertEqual("", result[callback.DAY_KEPT])
        self.assertEqual(1, result[callback.OUTSIDE_COUNT])
        later = turns(spec_with(), ("Friday", ""), ("", "4pm"))
        self.assertEqual(("2026-10-14", "16:00"), (later[callback.CALLBACK_DATE], later[callback.CALLBACK_TIME]))

    def test_entry_fires_on_a_day_alone_with_an_or_of_and_groups(self):
        transition = callback.callback_entry_transition()
        self.assertEqual("or", transition["condition"]["logic"])  # kit: never "and" at the top level
        groups = transition["condition"]["conditions"]
        self.assertEqual({callback.TIME_TEXT, callback.DAY_TEXT},
                         {group["conditions"][0]["variable"] for group in groups})
        self.assertTrue(all(group["logic"] == "and" for group in groups))


class RenderTests(unittest.TestCase):
    def test_f064_question_or_payment_offer_reasks_once_instead_of_closing(self):
        spec = spec_with()
        fields = {field["name"]: field for field in render(spec)["nodes"]["third_party"]["extraction_schema"]}
        intent_description = fields[spec.third_party.data["intent_variable"]]["description"].lower()
        kind_description = fields[callback.THIRD_PARTY_CLOSE_KIND]["description"].lower()
        phrase = "I can pay it myself if you tell me the amount"
        self.assertIn("offer to pay", intent_description)
        self.assertIn(phrase.lower(), kind_description)

        close_value = spec.third_party.data["close_values"][0]
        first = close_guard(spec, close_value, callback.THIRD_PARTY_CLOSE_OTHER)
        self.assertEqual(callback.THIRD_PARTY_CLOSE_REASK, first[callback.THIRD_PARTY_CLOSE_VERDICT])
        self.assertEqual(1, first[callback.THIRD_PARTY_CLOSE_COUNT])
        self.assertEqual("none", first[spec.third_party.data["intent_variable"]])
        self.assertEqual(callback.THIRD_PARTY_CLOSE_OTHER, first[callback.THIRD_PARTY_CLOSE_KIND])
        self.assertIn("when can the customer be reached", first[callback.MESSAGE].lower())

        second = close_guard(spec, close_value, callback.THIRD_PARTY_CLOSE_OTHER,
                             {callback.THIRD_PARTY_CLOSE_COUNT: 1})
        self.assertEqual(callback.THIRD_PARTY_CLOSE_NOW, second[callback.THIRD_PARTY_CLOSE_VERDICT])

    def test_f064_every_spec_close_value_is_in_both_extraction_descriptions(self):
        fixtures = (
            (ROOT / "tests/fixtures/spec-brief-a.json", OPENAPI),
            (ROOT / "tests/fixtures/spec-brief-b.json", OPENAPI),  # cumulative A+B fixture
            (ROOT / "tests/fixtures/spec-synthetic.json", json.loads(
                (ROOT / "tests/fixtures/openapi-synthetic.json").read_text(encoding="utf-8"))),
        )
        for path, document in fixtures:
            with self.subTest(spec=path.name):
                spec = parse_spec(json.loads(path.read_text(encoding="utf-8")))
                fields = {field["name"]: field
                          for field in render(spec, document)["nodes"]["third_party"]["extraction_schema"]}
                descriptions = (
                    fields[spec.third_party.data["intent_variable"]]["description"],
                    fields[callback.THIRD_PARTY_CLOSE_KIND]["description"],
                )
                for value in spec.third_party.data["close_values"]:
                    self.assertTrue(all(value in description for description in descriptions), value)

    def test_f064_explicit_refusal_closes_without_reask(self):
        spec = spec_with()
        fields = {field["name"]: field for field in render(spec)["nodes"]["third_party"]["extraction_schema"]}
        self.assertIn("she doesn't want to be called",
                      fields[callback.THIRD_PARTY_CLOSE_KIND]["description"].lower())

        close_value = spec.third_party.data["close_values"][0]
        variables = close_guard(spec, close_value, callback.THIRD_PARTY_CLOSE_EXPLICIT)
        self.assertEqual(callback.THIRD_PARTY_CLOSE_NOW, variables[callback.THIRD_PARTY_CLOSE_VERDICT])
        self.assertEqual(close_value, variables[spec.third_party.data["intent_variable"]])
        self.assertEqual(callback.THIRD_PARTY_CLOSE_OTHER, variables[callback.THIRD_PARTY_CLOSE_KIND])
        self.assertNotIn(callback.THIRD_PARTY_CLOSE_COUNT, variables)

    def test_f064_session_routes_refusal_second_nonexplicit_and_deceased_to_closing(self):
        spec = spec_with()
        close_values = spec.third_party.data["close_values"]
        refusal = close_values[0]
        deceased = next(value for value in close_values if "deceas" in value.lower())

        refusal_session = ThirdPartySession(spec)
        refusal_session.say(refusal, callback.THIRD_PARTY_CLOSE_OTHER)
        self.assertEqual(callback.THIRD_PARTY_ASK, refusal_session.step)
        refusal_session.say(refusal, callback.THIRD_PARTY_CLOSE_EXPLICIT)
        self.assertEqual("closing", refusal_session.step)

        bounded_session = ThirdPartySession(spec)
        bounded_session.say(refusal, callback.THIRD_PARTY_CLOSE_OTHER)
        bounded_session.say(refusal, callback.THIRD_PARTY_CLOSE_OTHER)
        self.assertEqual("closing", bounded_session.step)

        self.assertIn(deceased, close_values)
        for close_value in close_values:
            with self.subTest(first_turn_close=close_value):
                close_session = ThirdPartySession(spec)
                close_session.say(close_value, callback.THIRD_PARTY_CLOSE_EXPLICIT)
                self.assertEqual("closing", close_session.step)

    def test_f064_callback_date_and_time_win_over_stale_explicit_kind_in_the_same_turn(self):
        spec = spec_with()
        callback_intent = next(value for value in spec.third_party.data["intent_values"]
                               if value not in spec.third_party.data["close_values"])
        session = ThirdPartySession(spec).say(
            callback_intent, callback.THIRD_PARTY_CLOSE_EXPLICIT,
            **{callback.DAY_TEXT: "tomorrow", callback.TIME_TEXT: "3pm"},
        )
        self.assertEqual(["third_party", callback.CALLBACK_CHECK], session.path)
        self.assertEqual(callback.CALLBACK_BOOK, session.step)
        self.assertEqual(callback.WINDOW_OK, session.vars[callback.VERDICT])
        self.assertEqual(("2026-10-15", "15:00"),
                         (session.vars[callback.CALLBACK_DATE], session.vars[callback.CALLBACK_TIME]))
        self.assertEqual(callback.THIRD_PARTY_CLOSE_OTHER, session.vars[callback.THIRD_PARTY_CLOSE_KIND])

    def test_model_never_fills_the_callback_date(self):
        workflow = render(spec_with())
        nodes = workflow["nodes"]
        self.assertEqual([], nodes["third_party"]["tools"])
        names = [field["name"] for field in nodes["third_party"]["extraction_schema"]]
        self.assertIn(callback.DAY_TEXT, names)
        self.assertIn(callback.TIME_TEXT, names)
        self.assertIn(callback.CALLBACK_CHECK, [t["target_node"] for t in nodes["third_party"]["transitions"]])
        tool = nodes[callback.CALLBACK_BOOK]["pre_actions"][0]
        body = tool["function"]["parameters"]["properties"]["body"]
        self.assertEqual("{{callback_date}}", body["properties"]["date"]["default"])
        self.assertEqual("{{callback_time}}", body["properties"]["time"]["default"])
        self.assertNotIn("required", body)
        self.assertEqual(0, tool["config"]["maxRetries"])
        self.assertEqual(callback.CALLBACK_TOOL, tool["function"]["name"])

    def test_graph_routes_and_no_null(self):
        workflow = render(spec_with())
        nodes = workflow["nodes"]
        targets = lambda key: [t["target_node"] for t in nodes[key]["transitions"]]
        self.assertEqual([callback.CALLBACK_BOOK, "closing", callback.THIRD_PARTY_ASK], targets(callback.CALLBACK_CHECK))
        self.assertEqual(["closing"], targets(callback.CALLBACK_BOOK))
        self.assertEqual(["closing", callback.THIRD_PARTY_ASK],
                         targets(callback.THIRD_PARTY_CLOSE_CHECK))
        serialized = json.dumps(workflow)
        self.assertNotIn("null", serialized)
        self.assertNotIn("{{", code_of(nodes[callback.CALLBACK_CHECK]))

    def test_third_party_asks_for_day_and_time_and_never_claims_a_booking(self):
        # Review finding 3.
        task = render(spec_with())["nodes"]["third_party"]["task_message"]
        self.assertIn(callback.CALLBACK_COLLECT_RULE.text, task)

    def test_third_party_ask_is_a_copy_whose_entry_is_the_fixed_line(self):
        # Review finding 4: the model does not speak after the line; third_party itself is unchanged.
        nodes = render(spec_with())["nodes"]
        twin, original = nodes[callback.THIRD_PARTY_ASK], nodes["third_party"]
        self.assertEqual({"type": "tts", "text": "{{callback_message}}"}, twin["on_enter"])
        self.assertNotIn("on_enter", original)
        self.assertNotIn("on_enter_first_entry_only", original)
        self.assertNotIn("on_enter_first_entry_only", twin)
        for key in ("task_message", "extraction_schema", "transitions", "tools"):
            self.assertEqual(original[key], twin[key], key)

    def test_global_paths_from_third_party_also_fire_in_the_copy(self):
        workflow = render(spec_with())
        for key, node in workflow["global_nodes"].items():
            excluded = set(node.get("excluded_nodes", []))
            self.assertEqual("third_party" in excluded, callback.THIRD_PARTY_ASK in excluded, key)

    def test_booking_failure_closes_as_callback_failed(self):
        failed = dict(close_rules(spec_with()))["callback_failed"]
        self.assertIn(callback.BOOK_FAILURE_COUNT, [condition.get("variable") for condition in failed])

    def test_invalid_window_fails_the_render(self):
        for change in ({"earliest_time": "25:00"}, {"day_unit": "weeks"}, {"days_ahead": -1},
                       {"earliest_time": "19:00", "latest_time": "10:00"}, {"outside_close_value": "callback"},
                       {"outside_close_value": ""}):
            with self.subTest(change=change), self.assertRaises(SpecError):
                render(spec_with({**WINDOW, **change}))

    def test_tool_without_date_and_time_fields_keeps_the_model_tool_with_a_warning(self):
        document = copy.deepcopy(OPENAPI)
        schema = document["paths"]["/schedule_callback"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        schema["properties"] = {"customer_id": {"type": "string"}, "slot": {"type": "string"}}
        schema["required"] = ["customer_id", "slot"]
        warnings: list[str] = []
        nodes = render(spec_with(), document, warnings)["nodes"]
        self.assertNotIn(callback.CALLBACK_CHECK, nodes)
        self.assertEqual([callback.CALLBACK_TOOL], [t["function"]["name"] for t in nodes["third_party"]["tools"]])
        self.assertTrue(any("F-055 not applied" in warning for warning in warnings))


class FieldDetectionTests(unittest.TestCase):
    """Review finding 5: names are split on _, - and camelCase; one date-time field works."""

    def tool_with(self, properties):
        document = copy.deepcopy(OPENAPI)
        schema = document["paths"]["/schedule_callback"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        schema["properties"] = {"customer_id": {"type": "string"}, **properties}
        schema["required"] = list(schema["properties"])
        return next(tool for tool in tools_from_openapi(document) if tool["function"]["name"] == callback.CALLBACK_TOOL)

    def test_names(self):
        cases = (
            ({"callback_date": {"type": "string"}, "callback_time": {"type": "string"}}, ("callback_date", "callback_time")),
            ({"callbackTime": {"type": "string"}, "callbackDate": {"type": "string"}}, ("callbackDate", "callbackTime")),
            ({"scheduled-date": {"type": "string"}, "scheduled-time": {"type": "string"}}, ("scheduled-date", "scheduled-time")),
            ({"time": {"type": "string", "description": "same date, HH:MM"}, "date": {"type": "string"}}, ("date", "time")),
            ({"when": {"type": "string", "format": "date"}, "at": {"type": "string", "description": "HH:MM"}}, ("when", "at")),
            ({"callback_datetime": {"type": "string"}}, ("callback_datetime", "callback_datetime")),
        )
        for properties, expected in cases:
            with self.subTest(fields=list(properties)):
                self.assertEqual(expected, callback._body_fields(self.tool_with(properties)))

    def test_single_date_time_field_gets_both_values(self):
        tool = callback._book_tool(self.tool_with({"slot_datetime": {"type": "string"}}), "slot_datetime", "slot_datetime")
        body = tool["function"]["parameters"]["properties"]["body"]
        self.assertEqual("{{callback_date}}T{{callback_time}}:00", body["properties"]["slot_datetime"]["default"])


class ExtractionTests(unittest.TestCase):
    def test_merge_keeps_the_window_without_its_source(self):
        groups = groups_from_spec(SPEC_A)
        groups["opening_identity"]["third_party"]["callback_window"] = {**WINDOW, "source": "rule 6"}
        merged = merge_groups(groups)
        self.assertEqual(WINDOW, merged["third_party"]["callback_window"])
        parse_spec(merged)

    def test_times_need_brief_evidence(self):
        checker = _Checker("A callback is from 10:00 to 7 pm, both included.", {}, set())
        self.assertTrue(_clock_in_brief("10:00", checker))
        self.assertTrue(_clock_in_brief("19:00", checker))
        self.assertFalse(_clock_in_brief("18:00", checker))
        _check_callback_window({**WINDOW, "latest_time": "18:00"}, checker)
        self.assertEqual(["third_party.callback_window.latest_time"], [path for path, _ in checker.errors])

    def test_bare_hours_in_a_range_count_as_evidence(self):
        # Review finding 6 (optional).
        for brief in ("Callbacks between 10 and 19 only.", "Callbacks 10-19h.", "Callbacks from 10 to 19.",
                      "Callbacks 10 to 19 hrs."):
            with self.subTest(brief=brief):
                checker = _Checker(brief, {}, set())
                self.assertTrue(_clock_in_brief("19:00", checker))
        checker = _Checker("Rule 10 applies; call after 19 days.", {}, set())
        self.assertFalse(_clock_in_brief("10:00", checker))

    def test_missing_window_is_allowed(self):
        checker = _Checker("No callback limits.", {}, set())
        _check_callback_window(None, checker)
        self.assertEqual([], checker.errors)


if __name__ == "__main__":
    unittest.main()
