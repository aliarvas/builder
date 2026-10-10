from __future__ import annotations

import ast
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from builder import build
from builder.spec import SpecError, load_spec, parse_spec
from builder.tools_from_openapi import tools_from_openapi
from builder.workflow import build_spec_workflow, workflow_prompt_estimates


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = (
    ROOT / "tests/fixtures/spec-brief-a.json",
    ROOT / "tests/fixtures/spec-brief-b.json",
    ROOT / "tests/fixtures/spec-synthetic.json",
)


def kit_tools():
    document = json.loads((ROOT / "build-the-builder-v2/tools/openapi.json").read_text(encoding="utf-8"))
    return tools_from_openapi(document)


def tool_names(node):
    return [tool["function"]["name"] for tool in node.get("tools", [])]


class SpecTests(unittest.TestCase):
    def test_all_fixtures_load(self):
        for path in FIXTURES:
            with self.subTest(path=path.name):
                self.assertEqual(1, load_spec(path).spec_version)

    def test_missing_section_is_clear(self):
        value = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        value.pop("identity")
        with self.assertRaisesRegex(SpecError, "missing required.*identity"):
            parse_spec(value)

    def test_unknown_special_path_outcome_is_clear(self):
        value = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        value["special_paths"][0]["outcome"] = "not_in_table"
        with self.assertRaisesRegex(SpecError, "unknown outcome/reason"):
            parse_spec(value)

    def test_unclear_limit_must_be_positive(self):
        value = json.loads(FIXTURES[0].read_text(encoding="utf-8"))
        value["opening"]["max_unclear_asks"] = 0
        with self.assertRaisesRegex(SpecError, "max_unclear_asks.*positive integer"):
            parse_spec(value)


class MultiStepWorkflowTests(unittest.TestCase):
    def render(self, index=0):
        return build_spec_workflow(load_spec(FIXTURES[index]), kit_tools())

    def test_all_fixtures_render_without_null_or_agent_config(self):
        for index, path in enumerate(FIXTURES):
            with self.subTest(path=path.name):
                workflow = self.render(index)
                serialized = json.dumps(workflow)
                self.assertNotIn("null", serialized)
                self.assertNotIn("agent_config", workflow)
                for key, node in workflow["nodes"].items():
                    self.assertEqual(key, node["name"])
                    if "tools" in node:
                        self.assertEqual("conversation", node["node_type"])

    def test_reachability_and_terminal_shape(self):
        workflow = self.render()
        nodes = workflow["nodes"]
        reached = {workflow["initial_node"]}
        pending = list(reached)
        while pending:
            node = nodes[pending.pop()]
            for transition in node.get("transitions", []):
                target = transition["target_node"]
                if target not in reached:
                    reached.add(target)
                    pending.append(target)
        self.assertEqual(set(nodes), reached)
        terminals = [key for key, node in nodes.items() if node["node_type"] == "end_call"]
        self.assertEqual(["end_call"], terminals)
        incoming_end = [
            source for source, node in nodes.items()
            if any(item["target_node"] == "end_call" for item in node.get("transitions", []))
        ]
        self.assertEqual(["closing"], incoming_end)
        for node in nodes.values():
            if node["node_type"] in {"api_request", "code"}:
                self.assertEqual("always", node["transitions"][-1]["condition"]["operator"])

    def test_tools_are_scoped(self):
        nodes = self.render()["nodes"]
        self.assertEqual(["verify_identity"], tool_names(nodes["identity"]))
        self.assertEqual(["create_promise"], tool_names(nodes["confirm_record"]))
        self.assertEqual(["close_call"], tool_names(nodes["closing"]))
        for key, node in nodes.items():
            if key != "identity":
                self.assertNotIn("verify_identity", tool_names(node))
            if key != "confirm_record":
                self.assertNotIn("create_promise", tool_names(node))
            if key != "closing":
                self.assertNotIn("close_call", tool_names(node))

    def test_freya_extraction_and_passthrough_wire_shapes(self):
        nodes = self.render()["nodes"]
        for key in ("opening", "third_party", "negotiate"):
            schema = nodes[key]["extraction_schema"]
            self.assertIsInstance(schema, list)
            self.assertIn("name", schema[0])
            self.assertIn("enum_values", schema[0])
            self.assertIn("min_confidence", schema[0])
        account = nodes["account"]
        self.assertTrue(account["passthrough"])
        self.assertEqual("negotiate", account["passthrough_default_transition"])
        self.assertIn("response_mapping", account)
        self.assertNotIn("response_mapping", account["pre_actions"][0])
        for key, node in nodes.items():
            for transition in node.get("transitions", []):
                self.assertNotEqual("is_tool_call", transition.get("condition", {}).get("operator"))
        no_tool_specials = [
            node for key, node in nodes.items()
            if key.startswith("special_already_paid")
        ]
        self.assertTrue(no_tool_specials)
        self.assertTrue(all(node["transitions"][0].get("is_tool_call") is True for node in no_tool_specials))

    def test_special_tool_args_are_baked(self):
        nodes = self.render()
        special = next(
            node for key, node in nodes["nodes"].items()
            if key.startswith("special_human")
        )
        body = special["tools"][0]["function"]["parameters"]["properties"]["body"]
        self.assertEqual("general", body["properties"]["queue"]["default"])
        self.assertNotIn("queue", body.get("required", []))

    def test_identity_routes_on_both_true_spellings_and_attempt_count(self):
        transitions = self.render()["nodes"]["identity"]["transitions"]
        rendered = json.dumps(transitions)
        self.assertIn('"operand": "true"', rendered)
        self.assertIn('"operand": "True"', rendered)
        self.assertIn('"operator": "less_than", "operand": 1', rendered)

    def test_product_hook_maps_any_index_from_three_supported_variable_shapes(self):
        tool = self.render()["nodes"]["confirm_record"]["tools"][0]
        code = tool["pre_process_code"]
        compile(code, "<product-hook>", "exec")
        self.assertNotIn("{{", code)
        products = [
            {"product_id": "id-a"}, {"product_id": "id-b"},
            {"product_id": "id-c"}, {"product_id": "id-d"},
        ]
        sources = (
            {"account_products": products},
            {"account_products": json.dumps(products)},
            {"get_account_response.data.products": products},
        )
        for source in sources:
            config = {"body": {"product_number": 4}}
            exec(code, {"config": config, "vars": source, "json": json})
            self.assertEqual("id-d", config["body"]["product_id"])
            self.assertNotIn("product_number", config["body"])
        for bad in (None, "", "x", 0, 5, {}, []):
            config = {"body": {"product_number": bad}}
            exec(code, {"config": config, "vars": {"account_products": products}, "json": json})

    def test_confirmation_progress_supports_multiple_products_and_one_retry(self):
        node = self.render(1)["nodes"]["confirmation_progress"]
        code = node["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        variables = {"agreed_item_count": 2, "create_promise_args.selected_product_number": 1, "promise_result_ok": True}
        exec(code, {"vars": variables})
        self.assertEqual("continue", variables["promise_progress_state"])
        self.assertEqual("consumed", variables["promise_result_ok"])
        variables.update({"create_promise_args.selected_product_number": 2, "promise_result_ok": True})
        exec(code, {"vars": variables})
        self.assertEqual("complete", variables["promise_progress_state"])

        variables = {"agreed_item_count": 1, "create_promise_args.selected_product_number": 1, "promise_result_ok": False}
        exec(code, {"vars": variables})
        self.assertEqual("retry", variables["promise_progress_state"])
        variables["promise_result_ok"] = False
        exec(code, {"vars": variables})
        self.assertEqual("exhausted", variables["promise_progress_state"])

    def test_opening_unclear_counter_close_and_stay_routes(self):
        nodes = self.render()["nodes"]
        opening = json.dumps(nodes["opening"]["transitions"])
        self.assertIn('"target_node": "opening_unclear"', opening)
        self.assertIn('"target_node": "closing"', opening)
        code = nodes["opening_unclear"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        variables = {"who_answered": "unclear"}
        exec(code, {"vars": variables})
        self.assertEqual(1, variables["opening_unclear_count"])
        self.assertEqual("", variables["who_answered"])
        exec(code, {"vars": variables})
        self.assertEqual(2, variables["opening_unclear_count"])
        synthetic_transitions = self.render(2)["nodes"]["opening_unclear"]["transitions"]
        self.assertIn('"operand": 2', json.dumps(synthetic_transitions))

    def test_model_product_field_is_never_written_as_a_workflow_variable(self):
        workflow = self.render(1)
        tool = workflow["nodes"]["confirm_record"]["tools"][0]
        hook = tool["pre_process_code"]
        progress = workflow["nodes"]["confirmation_progress"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
        self.assertNotIn("vars['selected_product_number'] =", hook)
        self.assertIn("create_promise_args.selected_product_number", progress)
        self.assertNotIn("vars.pop('promise_result_ok'", progress)
        transitions = workflow["nodes"]["confirm_record"]["transitions"]
        result_transition = next(item for item in transitions if item["target_node"] == "confirmation_progress")
        self.assertEqual(
            ["true", "True", "false", "False"],
            [condition["operand"] for condition in result_transition["condition"]["conditions"]],
        )

    def test_special_availability_return_and_deterministic_transition_order(self):
        nodes = self.render(1)["nodes"]
        self.assertFalse(any(key.startswith("special_product_dispute_from_identity") for key in nodes))
        dispute = nodes["special_product_dispute_from_negotiate"]
        self.assertEqual("negotiate", dispute["transitions"][0]["target_node"])
        for key in ("opening", "third_party", "identity", "negotiate", "confirm_record"):
            transitions = nodes[key]["transitions"]
            first_intent = next((index for index, item in enumerate(transitions)
                                 if item.get("condition", {}).get("operator") == "matches_intent"), None)
            if first_intent is not None:
                deterministic = [
                    index for index, item in enumerate(transitions[:first_intent])
                    if item.get("condition", {}).get("logic") == "or"
                ]
                self.assertTrue(deterministic, key)

    def test_account_and_closing_have_bounded_retries_and_confirm_can_revise(self):
        nodes = self.render()["nodes"]
        self.assertEqual(1, nodes["account"]["pre_actions"][0]["config"]["maxRetries"])
        self.assertEqual("closing", nodes["account"]["transitions"][0]["target_node"])
        self.assertEqual("negotiate", nodes["confirm_record"]["transitions"][0]["target_node"])
        self.assertEqual("end_call", nodes["closing"]["max_turn_transition"])
        self.assertIn('"operand": 1', json.dumps(nodes["closing"]["transitions"]))
        closing_success = nodes["closing"]["transitions"][0]
        self.assertEqual(
            ["close_call_response.data.ok", "close_call_response.data.ok"],
            [condition["variable"] for condition in closing_success["condition"]["conditions"]],
        )

    def test_fixture_a_prompts_are_under_budget(self):
        workflow = self.render()
        estimates = workflow_prompt_estimates(workflow)
        self.assertTrue(estimates)
        self.assertTrue(all(value <= 1500 for value in estimates.values()), estimates)
        without_identity_tool = json.loads(json.dumps(workflow))
        without_identity_tool["nodes"]["identity"]["tools"] = []
        self.assertGreater(
            estimates["identity"], workflow_prompt_estimates(without_identity_tool)["identity"]
        )

    def test_cli_print_with_spec_is_offline_and_traced(self):
        with tempfile.TemporaryDirectory() as directory:
            trace_root = Path(directory)
            previous = Path.cwd()
            try:
                import os
                os.chdir(trace_root)
                stdout, stderr = StringIO(), StringIO()
                captured = {}
                def generate_tools(document, **kwargs):
                    captured.update(kwargs)
                    return tools_from_openapi(document, **kwargs)
                with patch("builder.build.tools_from_openapi", side_effect=generate_tools), \
                        redirect_stdout(stdout), redirect_stderr(stderr):
                    result = build.main([
                            str(ROOT / "build-the-builder-v2/briefs/brief-a.md"),
                            str(ROOT / "build-the-builder-v2/tools/openapi.json"),
                            "--spec", str(FIXTURES[0]), "--print", "--slot", "multi-step",
                        ])
                self.assertEqual(0, result)
                self.assertIn("negotiation_intent", captured["known_entry_variables"])
                self.assertIn("agreed_product_count", captured["known_entry_variables"])
                self.assertEqual("opening", json.loads(stdout.getvalue())["initial_node"])
                trace = (trace_root / "traces/multi-step.print.log").read_text(encoding="utf-8")
                self.assertIn("renderer: multi-step spec_version=1", trace)
                self.assertIn("prompt_estimate:", trace)
                self.assertIn("freya: not contacted", trace)
            finally:
                os.chdir(previous)

    def test_builder_string_literals_do_not_embed_fixture_values(self):
        def strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for child in value.values():
                    yield from strings(child)
            elif isinstance(value, list):
                for child in value:
                    yield from strings(child)

        openapi_values = set(strings(json.loads(
            (ROOT / "build-the-builder-v2/tools/openapi.json").read_text(encoding="utf-8")
        )))
        fixture_values = set()
        for path in FIXTURES:
            fixture_values.update(strings(json.loads(path.read_text(encoding="utf-8"))))
        source_literals = set()
        for path in (ROOT / "builder").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            source_literals.update(
                node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            )
        allowed_fixed_tools = {
            "verify_identity", "get_account", "create_promise", "add_note",
            "schedule_callback", "transfer_to_agent", "close_call",
        }
        required_framework_terms = {
            "third_party", "identity", "negotiate", "confirm_record",
            "close", "return", "failed",
        }
        leaked = {
            value for value in fixture_values
            if len(value) >= 4
            and value not in openapi_values
            and value not in allowed_fixed_tools
            and value not in required_framework_terms
            and value in source_literals
        }
        self.assertEqual(set(), leaked)
        workflow_source = (ROOT / "builder/workflow.py").read_text(encoding="utf-8")
        self.assertNotIn("min(len(products), 3)", workflow_source)
        workflow_tree = ast.parse(workflow_source)
        self.assertFalse(any(
            isinstance(node, ast.Constant) and type(node.value) is int and node.value == 3
            for node in ast.walk(workflow_tree)
        ))
        lowered = workflow_source.lower()
        for phrase in ("up to three", "one to three", "at most three"):
            self.assertNotIn(phrase, lowered)


if __name__ == "__main__":
    unittest.main()
