"""T-047: the generic mode's self-test loop, offline (fake model, fake Freya chat)."""

import json
import unittest
from types import SimpleNamespace

from builder import generic_selftest as gs


class FakeCase:
    def text_documents(self):
        return [("policy.md", "Rules of a synthetic service line."), ("tests.md", "Synthetic test customers.")]

    def attachments(self):
        return []


def scenario_json(sid, **extra):
    item = {"id": sid, "persona": "calm caller", "goal": "ask the balance", "language": "xx",
            "variables": {"callerNumber": "00000000", "now": "2030-01-01T10:00:00"},
            "opening": "Hello", "expected": ["reads the balance"], "expected_tools": ["/balance"],
            "max_turns": 3}
    item.update(extra)
    return item


class FakeModel:
    """Answers by purpose; the judge passes a scenario when its id is in ``passing``."""

    def __init__(self, scenarios, passing):
        self.scenarios = scenarios
        self.passing = passing
        self.calls = []

    def complete(self, system, messages, purpose):
        self.calls.append(purpose)
        task = messages[0]["content"][-1]["text"]
        if purpose == "selftest_scenarios":
            text = json.dumps({"scenarios": self.scenarios})
        elif purpose == "selftest_caller":
            text = '{"message": "bye", "hang_up": true}'
        else:
            sid = json.loads(task.split("Scenario:\n", 1)[1].split("\n\nThe call", 1)[0])["id"]
            ok = sid in self.passing()
            text = "Verdict: " + json.dumps({"pass": ok, "reasons": [] if ok else ["did not read the balance"],
                                             "fix": "call the balance service first"})
        return SimpleNamespace(text=text)


class FakeChat:
    def __init__(self):
        self.started = []
        self.ended = []
        self.count = 0

    def chat_message(self, workflow_id, message, variables, call_id=None, timeout_seconds=0):
        if call_id is None:
            self.count += 1
            call_id = f"call-{self.count}"
            self.started.append((workflow_id, dict(variables)))
        return {"callId": call_id, "response": "Merhaba"}

    def get_call(self, call_id, timeout_seconds=0):
        return {"messages": [
            {"role": "user", "message": "Hello"},
            {"role": "system", "message": json.dumps({"event": "function_call_start", "function": "balance",
                                                      "args": {"n": 1}})},
            {"role": "system", "message": json.dumps({"event": "function_call_complete", "function": "balance",
                                                      "result": {"ok": True}})},
            {"role": "assistant", "message": "Your balance is ..."}]}

    def end_chat(self, call_id, timeout_seconds=0):
        self.ended.append(call_id)


class Trace:
    def __init__(self):
        self.items = []

    def add(self, key, value):
        self.items.append((key, value))

    def keys(self, key):
        return [value for name, value in self.items if name == key]


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        self.now += 0.01
        return self.now


class ParsingTests(unittest.TestCase):
    def test_scenarios_parse_and_skip_bad_ones(self):
        scenarios, notes = gs.parse_scenarios({"scenarios": [
            scenario_json("Ok One"), scenario_json("ok_one"), scenario_json("no_goal", goal=""),
            scenario_json("long", max_turns=99), "text"]})
        self.assertEqual([item.id for item in scenarios], ["ok_one", "ok_one_x", "long"])
        self.assertEqual(scenarios[2].max_turns, gs.MAX_CALLER_TURNS)
        self.assertEqual(scenarios[0].variables["callerNumber"], "00000000")
        self.assertEqual(len(notes), 2)

    def test_missing_call_variable_is_filled_from_another_scenario(self):
        other = scenario_json("b")
        other["variables"] = {"callerNumber": "11111111"}
        scenarios, notes = gs.parse_scenarios({"scenarios": [scenario_json("a"), other]})
        self.assertEqual(scenarios[1].variables, {"callerNumber": "11111111", "now": "2030-01-01T10:00:00"})
        self.assertTrue(any("call variable now" in note for note in notes))

    def test_large_documents_are_cut(self):
        case = FakeCase()
        case.text_documents = lambda: [("small.md", "rules"), ("dump.json", "x" * (gs.DOCUMENT_CHAR_LIMIT + 500))]
        text = gs._documents_blocks(case)[-1]["text"]
        self.assertIn("rules", text)
        self.assertIn("dump.json: cut here for the self-test, 500 more characters", text)
        self.assertLess(len(text), gs.DOCUMENT_CHAR_LIMIT + 400)

    def test_verdict_parse(self):
        self.assertEqual(gs.parse_verdict(gs.parse_json_object('```json\n{"pass": "false", "reasons": "x"}\n```')),
                         (gs.FAIL, ["x"], ""))
        self.assertEqual(gs.parse_verdict({"pass": True})[0], gs.PASS)
        with self.assertRaises(ValueError):
            gs.parse_verdict({"reasons": []})

    def test_transcript_has_tools_and_results(self):
        text = gs.transcript_of(FakeChat().get_call("c"))
        self.assertIn("Caller: Hello", text)
        self.assertIn("[tool balance called with", text)
        self.assertIn('[tool balance returned {"ok": true}]', text)
        self.assertIn("Agent: Your balance", text)

    def test_repair_line_forbids_customer_values(self):
        results = [gs.ScenarioResult("a", gs.FAIL, ["r1", "r2"], "fix it"), gs.ScenarioResult("b", gs.PASS, []),
                   gs.ScenarioResult("c", gs.ERROR, ["platform"])]
        scenarios = {"a": gs.parse_scenarios({"scenarios": [scenario_json("a")]})[0][0]}
        lines = gs.problem_lines(results, scenarios)
        self.assertEqual(len(lines), 1)
        self.assertIn("a failed (ask the balance): r1; r2. Suggested fix: fix it.", lines[0])
        self.assertIn("never copy a test customer's value", lines[0])


class LoopTests(unittest.TestCase):
    def run_loop(self, passing_by_round, rounds=2, deadline=10_000.0):
        state = {"round": 0}
        model = FakeModel([scenario_json("good"), scenario_json("bad")],
                          lambda: passing_by_round[min(state["round"], len(passing_by_round) - 1)])
        chat = FakeChat()
        saves, repairs = [], []

        def save(workflow):
            saves.append(workflow)
            return "wf-%d" % len(saves)

        def repair(problems, workflow=None):
            repairs.append((problems, workflow))
            state["round"] += 1
            return {"version": state["round"]}

        trace = Trace()
        best, results = gs.self_test_loop(FakeCase(), {"version": 0}, save, repair, trace, model=model, chat=chat,
                                          deadline=deadline, workflow_id="wf-0", rounds=rounds, clock=Clock())
        return best, results, saves, repairs, chat, trace

    def test_failures_go_to_repair_and_only_failed_rerun(self):
        best, results, saves, repairs, chat, trace = self.run_loop([{"good"}, {"good", "bad"}])
        self.assertEqual(len(repairs), 1)
        problems, workflow = repairs[0]
        self.assertEqual(workflow, {"version": 0})
        self.assertEqual(len(problems), 1)
        self.assertIn("bad failed", problems[0])
        self.assertIn("did not read the balance", problems[0])
        # round 0 ran both on the given id; round 1 ran only the failed one on the re-saved id
        self.assertEqual([item[0] for item in chat.started], ["wf-0", "wf-0", "wf-1"])
        self.assertEqual(chat.started[0][1]["callerNumber"], "00000000")
        self.assertEqual(best, {"version": 1})
        self.assertEqual(saves, [{"version": 1}])
        self.assertEqual(sorted(item.verdict for item in results), [gs.PASS, gs.PASS])
        rows = [json.loads(value) for value in trace.keys("self_test_result")]
        self.assertEqual([(row["round"], row["id"], row["verdict"]) for row in rows],
                         [(0, "good", "pass"), (0, "bad", "fail"), (1, "bad", "pass")])
        self.assertTrue(all(row["call_id"] for row in rows))
        self.assertTrue(trace.keys("self_test_scenarios"))

    def test_no_gain_keeps_and_resaves_the_earlier_version(self):
        best, results, saves, repairs, *_ = self.run_loop([{"good"}], rounds=2)
        self.assertEqual(len(repairs), 2)
        self.assertEqual(best, {"version": 0})
        self.assertEqual(saves[-1], {"version": 0})
        self.assertEqual(sum(item.verdict == gs.PASS for item in results), 1)

    def test_all_pass_needs_no_repair(self):
        best, results, saves, repairs, *_ = self.run_loop([{"good", "bad"}])
        self.assertEqual((repairs, saves, best), ([], [], {"version": 0}))

    def test_short_time_stops_repair(self):
        best, results, saves, repairs, _, trace = self.run_loop([{"good"}], deadline=60.0)
        self.assertEqual((repairs, saves, best), ([], [], {"version": 0}))
        self.assertTrue(any("not enough time" in value for value in trace.keys("self_test")))

    def test_platform_errors_are_not_repaired(self):
        class BrokenChat(FakeChat):
            def chat_message(self, *args, **kwargs):
                raise RuntimeError("POST /api/v2/chat/message -> 400: bad")

        model = FakeModel([scenario_json("a")], lambda: set())
        repairs = []
        best, results = gs.self_test_loop(FakeCase(), {"v": 0}, lambda w: "id", lambda p, w=None: repairs.append(p),
                                          Trace(), model=model, chat=BrokenChat(), deadline=10_000.0,
                                          workflow_id="id", clock=Clock())
        self.assertEqual(results[0].verdict, gs.ERROR)
        self.assertEqual(repairs, [])

    def test_save_may_return_the_workflow_it_really_saved(self):
        model = FakeModel([scenario_json("good"), scenario_json("bad")], lambda: {"good"})
        saves = []

        def save(workflow):
            saves.append(workflow)
            return "wf-%d" % len(saves), {**workflow, "freya_fixed": True}

        best, _ = gs.self_test_loop(FakeCase(), {"version": 0}, save, lambda p, w=None: {"version": 1}, Trace(),
                                    model=model, chat=FakeChat(), deadline=10_000.0, workflow_id="wf-0",
                                    rounds=1, clock=Clock())
        # no gain: the earlier version is saved again, and what that save returned is the export
        self.assertEqual(saves, [{"version": 1}, {"version": 0}])
        self.assertEqual(best, {"version": 0, "freya_fixed": True})

    def test_two_argument_and_one_argument_repair(self):
        calls = []
        gs._call_repair(lambda problems: calls.append(("one", problems)), ["p"], {})
        gs._call_repair(lambda problems, workflow=None: calls.append(("two", workflow)), ["p"], {"w": 1})
        self.assertEqual(calls, [("one", ["p"]), ("two", {"w": 1})])


if __name__ == "__main__":
    unittest.main()
