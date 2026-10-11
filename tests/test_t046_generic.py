"""T-046: generic mode. A synthetic folder and a fake model (no network): contract, design,
render, local validation and the repair loop, and the CLI's --print run end to end."""

from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from builder import build, generic
from builder.case_folder import read_case

MOCK = "https://mock.example.invalid"

DOCS = {
    "BRIEF.md": "# Brief\nA shop line. Call variables: shopperId and now.\n",
    "integration.md": "Service GET /orders/{shopperId} returns status 200 with orderState and etaDate, or 404.\n"
                      "Service POST /orders/notify takes shopperId and channel (sms or email); returns 200 sent.\n",
}

CONTRACT = {
    "openapi": "3.0.3", "info": {"title": "x", "version": "1"}, "servers": [{"url": "https://mock.invalid"}],
    "paths": {
        "/orders/{shopperId}": {"get": {"parameters": [{"name": "shopperId", "in": "path"}], "responses": {
            "200": {"content": {"application/json": {"schema": {"properties": {
                "orderState": {"type": "string"}, "etaDate": {"type": "string"}}}}}}, "404": {}}}},
        "/orders/notify": {"post": {"requestBody": {"content": {"application/json": {"schema": {"properties": {
            "shopperId": {"type": "string"}, "channel": {"type": "string", "enum": ["sms", "email"]}}}}}},
            "responses": {"200": {"content": {"application/json": {"schema": {"properties": {
                "sent": {"type": "boolean"}}}}}}}}},
    },
}


def tool(name, method, path):
    return {"type": "function", "function": {"name": name, "handler": "__function__:api_call", "parameters": {
        "type": "object", "properties": {"url": {"type": "string", "default": MOCK + path},
                                         "method": {"type": "string", "default": method}}}},
            "response_mapping": [{"path": "data.orderState", "variable": "order_state"}]}


def end_node(key):
    return {"name": key, "node_type": "end_call", "transitions": [], "terminal": {"type": "function", "function": {
        "name": "end_call", "handler": "__function__:end_call", "parameters": {"type": "object", "properties": {}}}}}


WORKFLOW = {
    "initial_node": "lookup",
    "system_prompt": "Speak the call's language.",
    "test_variables": {"shopperId": "12345678", "now": "2026-10-12T10:30:00+03:00"},
    "nodes": {
        "lookup": {"name": "lookup", "node_type": "api_request", "passthrough": True,
                   "pre_actions": [tool("get_order", "GET", "/orders/{{shopperId}}")],
                   "transitions": [
                       {"target_node": "tell", "description": "found", "condition": {"logic": "or", "conditions": [
                           {"variable": "get_order_success_count", "operator": "greater_than", "operand": 0}]}},
                       {"target_node": "goodbye", "description": "else", "condition": {"operator": "always"}}]},
        "tell": {"name": "tell", "node_type": "conversation", "task_message": "Say {{order_state}}.",
                 "tools": [tool("notify", "POST", "/orders/notify")],
                 "extraction_schema": [{"name": "wants_more", "type": "string", "enum_values": ["yes", "no", "none"]}],
                 "transitions": [{"target_node": "goodbye", "description": "done", "condition": {
                     "logic": "or", "conditions": [{"variable": "wants_more", "operator": "equals", "operand": "no"}]}}]},
        "goodbye": end_node("goodbye"),
    },
    "global_nodes": {
        "leave": {"name": "leave", "node_type": "conversation", "description": "The caller says goodbye",
                  "condition": {"operator": "matches_intent", "description": "The caller clearly takes leave"},
                  "task_message": "Say goodbye.", "excluded_nodes": ["goodbye"],
                  "transitions": [{"target_node": "goodbye", "description": "always", "condition": {"operator": "always"}}]},
    },
}


def broken():
    workflow = copy.deepcopy(WORKFLOW)
    workflow["nodes"]["tell"]["transitions"][0]["target_node"] = "nowhere"
    workflow["nodes"]["tell"]["description"] = "plain nodes carry no description"
    workflow["nodes"]["lookup"]["pre_actions"][0]["function"]["parameters"]["properties"]["url"]["default"] = \
        MOCK + "/order/{{shopperId}}"
    workflow["agent_config"] = {"x": 1}
    return workflow


def folder(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in DOCS.items():
        (root / name).write_text(text, encoding="utf-8")
    return root


class FakeModel:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def settings(self):
        return "fake"

    def complete(self, system, messages, purpose):
        self.calls.append((purpose, messages[-1]["content"]))
        text = self.replies.pop(0)
        return type("R", (), {"text": text if isinstance(text, str) else json.dumps(text)})()


class Trace:
    def __init__(self):
        self.lines, self.path = [], None

    def add(self, key, value):
        self.lines.append((key, str(value)))

    def add_model_call(self, *args):
        pass


class ValidateTests(unittest.TestCase):
    def test_a_good_workflow_has_no_problems(self):
        self.assertEqual([], generic.validate(generic.clean(WORKFLOW), generic.with_server(CONTRACT, MOCK), MOCK))

    def test_broken_references_shapes_and_tools_are_named(self):
        problems = "\n".join(generic.validate(broken(), generic.with_server(CONTRACT, MOCK), MOCK))
        self.assertIn("'nowhere', which is not a node", problems)
        self.assertIn("`description` belongs only on global nodes", problems)
        self.assertIn("GET /order/{{shopperId}} is not a service of the contract", problems)
        self.assertIn("omit `agent_config`", problems)

    def test_undefined_variables_and_unguarded_loops(self):
        workflow = copy.deepcopy(WORKFLOW)
        workflow["nodes"]["tell"]["task_message"] = "Say {{missing_value}}."
        workflow["nodes"]["lookup"]["transitions"] = [
            {"target_node": "lookup", "description": "again", "condition": {"operator": "always"}}]
        problems = "\n".join(generic.validate(workflow, generic.with_server(CONTRACT, MOCK), MOCK))
        self.assertIn("'missing_value' is used but never set", problems)
        self.assertIn("loop lookup", problems)

    def test_contract_names_must_be_written_in_the_documents(self):
        invented = copy.deepcopy(CONTRACT)
        invented["paths"]["/orders/cancel"] = {"post": {}}
        plain = "\n".join(DOCS.values()).lower()
        self.assertEqual([], generic.contract_problems(CONTRACT, plain))
        self.assertIn("segment 'cancel'", "\n".join(generic.contract_problems(invented, plain)))

    def test_a_patch_replaces_changed_nodes_only(self):
        patched = generic.apply_patch(WORKFLOW, {"nodes": {"tell": {"name": "tell"}, "goodbye": None},
                                                 "top": {"system_prompt": "new"}})
        self.assertEqual({"name": "tell"}, patched["nodes"]["tell"])
        self.assertNotIn("goodbye", patched["nodes"])
        self.assertEqual("new", patched["system_prompt"])
        self.assertIn("lookup", patched["nodes"])


class BuildLoopTests(unittest.TestCase):
    def test_contract_design_render_validate_repair(self):
        fix = {"nodes": {"tell": WORKFLOW["nodes"]["tell"], "lookup": WORKFLOW["nodes"]["lookup"]}}
        model = FakeModel([CONTRACT, {"steps": [{"key": "lookup"}]}, broken(), fix])
        trace = Trace()
        with tempfile.TemporaryDirectory() as tmp:
            case = read_case(folder(Path(tmp) / "case"), MOCK)
            workflow, contract = generic.build(case, MOCK, trace, model)
        self.assertEqual(["generic:contract", "generic:design", "generic:render", "generic:repair_1"],
                         [purpose for purpose, _ in model.calls])
        self.assertEqual(MOCK, contract["servers"][0]["url"])
        self.assertEqual([], generic.validate(workflow, contract, MOCK))
        self.assertNotIn("agent_config", workflow)
        # The repair request named the exact problems.
        self.assertIn("'nowhere', which is not a node", model.calls[-1][1])
        self.assertIn(("validation", "round 1: 0 problem(s)"), trace.lines)
        # The platform docs and the documents go in the cached prefix.
        first = model.calls[0][1]
        self.assertTrue(any("cache_control" in block for block in first))

    def test_repair_for_outside_problems(self):
        model = FakeModel([{"nodes": {"tell": {**WORKFLOW["nodes"]["tell"], "task_message": "Say {{order_state}} now."}}}])
        with tempfile.TemporaryDirectory() as tmp:
            case = read_case(folder(Path(tmp) / "case"), MOCK)
            repaired = generic.repair(case, WORKFLOW, ["scenario A failed: too short"], Trace(), model,
                                      contract=generic.with_server(CONTRACT, MOCK))
        self.assertEqual("Say {{order_state}} now.", repaired["nodes"]["tell"]["task_message"])
        self.assertIn("scenario A failed", model.calls[0][1])


class CliTests(unittest.TestCase):
    def test_print_runs_the_generic_mode_for_a_case_folder(self):
        model = FakeModel([CONTRACT, {"steps": []}, WORKFLOW])
        with tempfile.TemporaryDirectory() as tmp:
            root = folder(Path(tmp) / "case")
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(build, "AnthropicClient", lambda **kwargs: model), \
                    redirect_stdout(out), redirect_stderr(err):
                code = build.main(["--print", "--slot", "t046-test", str(root), MOCK])
        self.assertEqual(0, code, err.getvalue())
        printed = json.loads(out.getvalue())
        self.assertEqual("lookup", printed["initial_node"])
        self.assertIn("print: ok", err.getvalue())


if __name__ == "__main__":
    unittest.main()


class T051Tests(unittest.TestCase):
    """T-051: streaming replies, the tool base URL, tool timeouts and render without a design."""

    def test_a_streamed_reply_is_read_whole(self):
        import os
        from builder.llm import AnthropicClient

        events = [{"type": "message_start", "message": {"model": "m", "usage": {"input_tokens": 5}}},
                  {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "{\"a\":"}},
                  {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "1}"}},
                  {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 7}}]
        data = b"".join(b"event: x\ndata: " + json.dumps(item).encode() + b"\n\n" for item in events)

        class Reply(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        sent = {}

        def opener(request, timeout):
            sent.update(json.loads(request.data), timeout=timeout)
            return Reply(data)

        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
            client = AnthropicClient(stream=True, timeout=120, opener=opener)
            result = client.complete("s", [{"role": "user", "content": "hi"}], "t")
        self.assertEqual(('{"a":1}', 5, 7, "end_turn"),
                         (result.text, result.input_tokens, result.output_tokens, result.stop_reason))
        self.assertTrue(sent["stream"])
        self.assertEqual(120, sent["timeout"])

    def test_the_base_url_drops_a_prefix_the_paths_already_have(self):
        contract = {"paths": {"/v1/a.list": {}, "/v1/b.get": {}}}
        self.assertEqual("https://h.dev", generic.base_url("https://h.dev/v1/", contract))
        self.assertEqual("https://h.dev", generic.base_url("https://h.dev", contract))
        self.assertEqual("https://h.dev/api", generic.base_url("https://h.dev/api", contract))

    def test_api_tools_wait_at_least_30_seconds(self):
        cleaned = generic.clean(WORKFLOW)
        tool = cleaned["nodes"]["lookup"]["pre_actions"][0]
        self.assertEqual(generic.TOOL_TIMEOUT_MS, tool["config"]["timeoutMs"])

    def test_render_without_a_design_call(self):
        model = FakeModel([CONTRACT, WORKFLOW])
        with tempfile.TemporaryDirectory() as tmp:
            case = read_case(folder(Path(tmp) / "case"), MOCK)
            workflow, _ = generic.build(case, MOCK, Trace(), model, design=False)
        self.assertEqual(["generic:contract", "generic:render"], [purpose for purpose, _ in model.calls])
        self.assertEqual("lookup", workflow["initial_node"])


class T052Tests(unittest.TestCase):
    """T-052: a reply cut at the output limit is continued; the design has its own small limit."""

    @staticmethod
    def client(replies, sent, **options):
        import os
        from builder.llm import AnthropicClient

        def opener(request, timeout):
            payload = json.loads(request.data)
            sent.append(payload)
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            text, stop = reply
            body = {"model": "m", "content": [{"type": "text", "text": text}], "stop_reason": stop,
                    "usage": {"input_tokens": 1, "output_tokens": 10}}

            class Reply(io.BytesIO):
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return Reply(json.dumps(body).encode())

        patcher = mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"})
        patcher.start()
        try:
            return AnthropicClient(opener=opener, temperature=None, **options)
        finally:
            patcher.stop()

    def complete(self, client, **limits):
        import os
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
            return client.complete("s", [{"role": "user", "content": "hi"}], "render", **limits)

    def test_a_cut_reply_is_continued_with_a_prefill_and_joined(self):
        sent = []
        client = self.client([('{"a": "one ', "max_tokens"), ('two", ', "max_tokens"), ('"b": 2}', "end_turn")], sent)
        result = self.complete(client, max_tokens=64000)
        self.assertEqual('{"a": "one two", "b": 2}', result.text)
        self.assertEqual(30, result.output_tokens)
        self.assertEqual([64000] * 3, [item["max_tokens"] for item in sent])
        self.assertEqual({"role": "assistant", "content": '{"a": "one'}, sent[1]["messages"][-1])
        self.assertEqual('{"a": "one two",', sent[2]["messages"][-1]["content"])

    def test_still_cut_after_two_continuations_is_an_error(self):
        from builder.llm import LLMError
        client = self.client([("x" * 5, "max_tokens")] * 3, [])
        with self.assertRaisesRegex(LLMError, "output limit"):
            self.complete(client)

    def test_a_rejected_prefill_continues_with_a_user_note_without_the_repeat(self):
        import urllib.error
        sent = []
        rejected = urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(b'{"error": "prefill not supported"}'))
        head = '{"steps": ["alpha beta gamma delta epsilon"'
        client = self.client([(head, "max_tokens"), rejected, ('beta gamma delta epsilon", "zeta"]}', "end_turn")], sent)
        result = self.complete(client)
        self.assertEqual('{"steps": ["alpha beta gamma delta epsilon", "zeta"]}', result.text)
        self.assertEqual("user", sent[2]["messages"][-1]["role"])

    def test_the_design_is_limited_and_asked_shorter_once(self):
        from builder.llm import LLMError
        calls = []

        def complete(system, messages, purpose, **limits):
            calls.append((purpose, limits))
            if purpose == "generic:design":
                raise LLMError("model call 'generic:design' hit the output limit (8000 tokens)")
            return json.dumps({"steps": [{"key": "a"}]})

        design = generic.make_design({}, complete, [], Trace())
        self.assertEqual([{"key": "a"}], design["steps"])
        self.assertEqual([("generic:design", {"max_tokens": 8000, "continuations": 0}),
                          ("generic:design_shorter", {"max_tokens": 8000, "continuations": 0})], calls)

    def test_a_design_too_long_twice_falls_back_to_no_design(self):
        from builder.llm import LLMError

        def complete(system, messages, purpose, **limits):
            raise LLMError(f"model call {purpose!r} hit the output limit (8000 tokens)")

        trace = Trace()
        self.assertIn("note", generic.make_design({}, complete, [], trace))

    def test_the_render_asks_for_64000_tokens(self):
        calls = []

        def complete(system, messages, purpose, **limits):
            calls.append((purpose, limits))
            return json.dumps(WORKFLOW)

        generic.render({}, {}, complete, [], Trace())
        self.assertEqual([("generic:render", {"max_tokens": 64000})], calls)

    def test_a_refused_64000_limit_falls_back_to_48000(self):
        import urllib.error
        sent = []
        refused = urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(b'{"error": "max_tokens: 64000 > 48000"}'))
        client = self.client([refused, ("{}", "end_turn")], sent)
        self.assertEqual("{}", self.complete(client, max_tokens=64000).text)
        self.assertEqual([64000, 48000], [item["max_tokens"] for item in sent])

    @staticmethod
    def stream_client(streams, sent):
        import os
        from builder.llm import AnthropicClient

        class Reply(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def opener(request, timeout):
            sent.append(json.loads(request.data))
            pieces, stop = streams.pop(0)
            events = [{"type": "message_start", "message": {"model": "m", "usage": {"input_tokens": 1}}},
                      *({"type": "content_block_delta", "delta": {"type": "text_delta", "text": piece}}
                        for piece in pieces),
                      {"type": "message_delta", "delta": {"stop_reason": stop}, "usage": {"output_tokens": 9}}]
            return Reply(b"".join(b"data: " + json.dumps(item).encode() + b"\n\n" for item in events))

        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
            return AnthropicClient(opener=opener, temperature=None, stream=True)

    def test_a_whitespace_run_after_whole_json_ends_the_reply(self):
        sent = []
        client = self.stream_client([(['{"a": 1}', " " * 1500, "\n" * 1500, "never read"], "max_tokens")], sent)
        result = self.complete(client)
        self.assertEqual(('{"a": 1}', "end_turn", 1), (result.text.strip(), result.stop_reason, len(sent)))

    def test_a_whitespace_run_inside_json_is_continued(self):
        sent = []
        client = self.stream_client([(['{"a": [1,', " " * 2500], "max_tokens"), ([' 2]}'], "end_turn")], sent)
        result = self.complete(client)
        self.assertEqual('{"a": [1, 2]}', result.text)
        self.assertEqual('{"a": [1,', sent[1]["messages"][-1]["content"])


class T053Tests(unittest.TestCase):
    """T-053: an api_call body or headers given as one default object becomes properties leaves."""

    def tool(self):
        return {"type": "function", "config": {"timeoutMs": 30000}, "function": {
            "name": "load", "handler": "__function__:api_call", "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": MOCK + "/v1/a.list"},
                "method": {"type": "string", "default": "POST"},
                "headers": {"type": "object", "default": {"Content-Type": "application/json"}},
                "body": {"type": "object", "default": {"call": {"ani": "", "count": 2, "live": True},
                                                       "data": {"no": "{{customerNumber}}"}}}}}}}

    def test_a_default_object_becomes_properties_in_pre_actions_and_tools(self):
        workflow = copy.deepcopy(WORKFLOW)
        workflow["nodes"]["lookup"]["pre_actions"] = [self.tool()]
        workflow["global_nodes"] = {"g": {"node_type": "conversation", "tools": [self.tool()]}}
        cleaned = generic.clean(workflow)
        for tool in (cleaned["nodes"]["lookup"]["pre_actions"][0], cleaned["global_nodes"]["g"]["tools"][0]):
            properties = tool["function"]["parameters"]["properties"]
            self.assertEqual({"type": "object", "properties": {"Content-Type": {
                "type": "string", "default": "application/json"}}}, properties["headers"])
            self.assertEqual({"type": "object", "properties": {
                "call": {"type": "object", "properties": {"ani": {"type": "string", "default": ""},
                                                          "count": {"type": "number", "default": 2},
                                                          "live": {"type": "boolean", "default": True}}},
                "data": {"type": "object", "properties": {"no": {"type": "string",
                                                                 "default": "{{customerNumber}}"}}}}},
                properties["body"])

    def test_a_written_leaf_keeps_its_description(self):
        spec = {"type": "object", "default": {"no": "{{n}}"},
                "properties": {"no": {"type": "string", "description": "number"}}}
        self.assertEqual({"type": "object", "properties": {"no": {"type": "string", "default": "{{n}}",
                                                                  "description": "number"}}},
                         generic._as_properties(spec))

    def test_validate_names_a_default_object_body(self):
        problems = []
        generic_tool = self.tool()
        problems = generic._tool_problems(generic_tool, "node lookup", [], MOCK)
        self.assertTrue(any("body must use properties" in item for item in problems), problems)
        self.assertTrue(any("headers must use properties" in item for item in problems), problems)
