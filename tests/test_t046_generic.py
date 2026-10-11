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
