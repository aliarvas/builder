from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

from builder import build, freya, freya_chat
from builder.selftest import SelfTestCase, SelfTestResult, _run_case, generate_cases, run_self_tests
from builder.spec import load_spec


ROOT = Path(__file__).resolve().parents[1]
SPECS = (
    ROOT / "tests/fixtures/spec-brief-a.json",
    ROOT / "tests/fixtures/spec-brief-b.json",
    ROOT / "tests/fixtures/spec-synthetic.json",
)
OPENAPIS = (
    ROOT / "build-the-builder-v2/tools/openapi.json",
    ROOT / "build-the-builder-v2/tools/openapi.json",
    ROOT / "tests/fixtures/openapi-synthetic.json",
)


def event(name, **values):
    return {
        "role": "system",
        "messageId": "event-" + str(values.get("node") or values.get("function") or name),
        "message": json.dumps({"event": name, **values}),
    }


def passing_call(*, close=True, stuck=False):
    messages = [
        event("node_enter", node="opening"),
        event("function_call_start", function="verify_identity"),
    ]
    if close:
        messages.extend([
            event("function_call_start", function="close_call"),
            event("node_enter", node="end_call"),
        ])
    if stuck:
        messages.append({
            "role": "assistant", "messageId": "stuck", "message": "again",
            "workflowSnapshot": {"nodeTurnCount": 7},
        })
    return {"messages": messages, "endedReason": "end_call" if close else None}


class FakeClient:
    def __init__(self, call=None, failures=0, processed_on_failure=False):
        self.call = call or {"messages": []}
        self.failures = failures
        self.processed_on_failure = processed_on_failure
        self.chat_calls = 0
        self.end_calls = 0

    def chat_message(self, workflow_id, message, variables, call_id=None, timeout_seconds=120):
        self.chat_calls += 1
        if self.failures:
            self.failures -= 1
            if self.processed_on_failure:
                self.call["messages"].append({
                    "role": "user", "messageId": "processed", "message": message,
                })
            raise RuntimeError("POST /api/v2/chat/message -> 503: unavailable")
        self.call["messages"].append({
            "role": "user", "messageId": "user-" + str(self.chat_calls), "message": message,
        })
        return {"callId": "call-1", "response": "ok"}

    def get_call(self, call_id, timeout_seconds=120):
        return self.call

    def end_chat(self, call_id, timeout_seconds=120):
        self.end_calls += 1


class FreyaChatAdapterTests(unittest.TestCase):
    def response(self, result):
        return BytesIO(json.dumps({"data": {"result": result}}).encode())

    def test_chat_uses_kit_connection_settings_body_and_timeout(self):
        with patch(
            "builder.freya_chat.urllib.request.urlopen",
            return_value=self.response({"callId": "call-1"}),
        ) as urlopen:
            result = freya_chat.chat_message(
                "workflow", "hello", {"customer_id": "test"}, "call-0", timeout_seconds=7.5
            )
        self.assertEqual({"callId": "call-1"}, result)
        request = urlopen.call_args.args[0]
        self.assertEqual(freya.URL + "/api/v2/chat/message", request.full_url)
        self.assertEqual(freya.HEADERS["Authorization"], request.get_header("Authorization"))
        self.assertEqual(7.5, urlopen.call_args.kwargs["timeout"])
        self.assertEqual({
            "workflowId": "workflow", "message": "hello",
            "customerVariables": {"customer_id": "test"}, "callId": "call-0",
        }, json.loads(request.data))

    def test_call_record_and_end_routes_are_unwrapped(self):
        with patch(
            "builder.freya_chat.urllib.request.urlopen",
            side_effect=[self.response({"call": {"messages": []}}), self.response({"ended": True})],
        ) as urlopen:
            self.assertEqual({"messages": []}, freya_chat.get_call("call-1", timeout_seconds=4))
            self.assertEqual({"ended": True}, freya_chat.end_chat("call-1", timeout_seconds=3))
        requests = [call.args[0] for call in urlopen.call_args_list]
        self.assertTrue(requests[0].full_url.endswith("/api/v2/call/call-1"))
        self.assertTrue(requests[1].full_url.endswith("/api/v2/chat/end"))
        self.assertEqual({"callId": "call-1"}, json.loads(requests[1].data))


class SelfTestGenerationTests(unittest.TestCase):
    def test_all_three_fixtures_generate_three_bounded_cases(self):
        for spec_path, openapi_path in zip(SPECS, OPENAPIS):
            with self.subTest(spec=spec_path.name):
                spec = load_spec(spec_path)
                openapi = json.loads(openapi_path.read_text(encoding="utf-8"))
                cases = generate_cases(spec, openapi)
                self.assertEqual(3, len(cases))
                self.assertTrue(all(1 <= len(case.messages) <= 7 for case in cases))
                self.assertEqual(
                    ["identity_to_account", "identity_exhausted", "third_party_close"],
                    [case.id for case in cases],
                )
                self.assertIn(spec.identity_questions[0].ask.text, " ".join(cases[0].messages))
                self.assertIn(spec.opening.data["third_party_values"][0], " ".join(cases[2].messages))


class SelfTestRunnerTests(unittest.TestCase):
    def case(self, *, require_close=True):
        return SelfTestCase(
            "case", ("hello",), {}, ("opening", "end_call") if require_close else ("opening",),
            ("verify_identity",), require_close=require_close,
        )

    def test_passing_call_record(self):
        result = _run_case(FakeClient(passing_call()), "workflow", self.case(), 100, lambda: 1)
        self.assertEqual("pass", result.result)
        self.assertEqual("call-1", result.call_id)

    def test_stuck_node_fails(self):
        result = _run_case(FakeClient(passing_call(stuck=True)), "workflow", self.case(), 100, lambda: 1)
        self.assertEqual("fail", result.result)
        self.assertIn("turn limit", result.reason)

    def test_missing_close_fails_before_cleanup(self):
        client = FakeClient(passing_call(close=False))
        case = SelfTestCase("missing-close", ("hello",), {}, ("opening",), ("verify_identity",), True)
        result = _run_case(client, "workflow", case, 100, lambda: 1)
        self.assertEqual("fail", result.result)
        self.assertIn("close tool count", result.reason)
        self.assertEqual(1, client.end_calls)

    def test_5xx_processed_turn_is_not_resent(self):
        class ProcessedSecondTurn(FakeClient):
            def chat_message(self, workflow_id, message, variables, call_id=None, timeout_seconds=120):
                if self.chat_calls == 1:
                    self.chat_calls += 1
                    self.call["messages"].append({
                        "role": "user", "messageId": "processed", "message": message,
                    })
                    raise RuntimeError("POST /api/v2/chat/message -> 503: unavailable")
                return super().chat_message(
                    workflow_id, message, variables, call_id, timeout_seconds=timeout_seconds
                )

        client = ProcessedSecondTurn({"messages": []})
        case = SelfTestCase("processed", ("hello", "next"), {}, (), ())
        result = _run_case(client, "workflow", case, 100, lambda: 1)
        self.assertEqual("pass", result.result)
        self.assertEqual(2, client.chat_calls)

    def test_5xx_unprocessed_turn_is_retried(self):
        client = FakeClient({"messages": []}, failures=1)
        case = SelfTestCase("retry", ("hello",), {}, (), ())
        result = _run_case(client, "workflow", case, 100, lambda: 1)
        self.assertEqual("pass", result.result)
        self.assertEqual(2, client.chat_calls)

    def test_three_unprocessed_5xx_responses_are_platform_error(self):
        client = FakeClient({"messages": []}, failures=3)
        case = SelfTestCase("retry", ("hello",), {}, (), ())
        result = _run_case(client, "workflow", case, 100, lambda: 1)
        self.assertEqual("platform_error", result.result)
        self.assertEqual(3, client.chat_calls)

    def test_exhausted_budget_marks_every_case_without_chat(self):
        spec = load_spec(SPECS[0])
        openapi = json.loads(OPENAPIS[0].read_text(encoding="utf-8"))
        client = FakeClient()
        results = run_self_tests(client, "workflow", spec, openapi, budget_seconds=0, clock=lambda: 1)
        self.assertEqual(3, len(results))
        self.assertTrue(all(item.result == "platform_error" for item in results))
        self.assertEqual(0, client.chat_calls)


class BuildSelfTestIntegrationTests(unittest.TestCase):
    def test_saved_spec_workflow_runs_self_test_and_traces_results(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                with patch.dict(os.environ, {"FREYA_API_KEY": "fak_test"}, clear=True), patch(
                    "builder.build.freya.validate_workflow"
                ), patch(
                    "builder.build.save_with_slot_check",
                    return_value={"workflow_id": "workflow", "agent_id": "agent"},
                ), patch(
                    "builder.build._ensure_published_version", return_value=4
                ), patch(
                    "builder.build.freya.export_workflow"
                ), patch(
                    "builder.build.run_self_tests",
                    return_value=(SelfTestResult("smoke", "fail", "missing node", "call-7", 1.25),),
                ) as self_tests, redirect_stdout(StringIO()):
                    code = build.main([
                        str(ROOT / "build-the-builder-v2/briefs/brief-a.md"),
                        str(ROOT / "build-the-builder-v2/tools/openapi.json"),
                        "--spec", str(SPECS[0]), "--slot", "self-test-integration",
                    ])
                self.assertEqual(0, code)
                self_tests.assert_called_once()
                trace = Path("traces/self-test-integration.log").read_text(encoding="utf-8")
                self.assertIn(
                    "self_test: case=smoke result=fail reason=missing node call_id=call-7 seconds=1.2",
                    trace,
                )
                self.assertIn("self_test_summary: total=1 pass=0 fail=1 platform_error=0", trace)
                self.assertIn("status: ok", trace)
            finally:
                os.chdir(previous)

    def test_no_self_test_flag_skips_chat_checks(self):
        parser = build._parser()
        args = parser.parse_args(["--no-self-test", "brief.md", "tools.json"])
        self.assertTrue(args.no_self_test)


if __name__ == "__main__":
    unittest.main()
