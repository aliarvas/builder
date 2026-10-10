from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from builder import build
from builder.prompts import PROMPTS, generate_prompt_doc, prompt_doc_path
from builder.run_trace import TraceWriter
from builder.tools_from_openapi import (
    ALLOWED_SCHEMA_KEYS,
    CALL_VARIABLES,
    POST_PROCESS_CODE,
    OpenAPIError,
    tools_from_openapi,
)
from builder.workflow import build_workflow


ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def tool_body(tool):
    return tool["function"]["parameters"]["properties"]["body"]


def contains_none(value):
    if value is None:
        return True
    if isinstance(value, dict):
        return any(contains_none(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_none(item) for item in value)
    return False


class OpenAPIToolTests(unittest.TestCase):
    def test_kit_openapi_produces_seven_tools_with_schema_details(self):
        document = json.loads(
            (ROOT / "build-the-builder-v2/tools/openapi.json").read_text(encoding="utf-8")
        )
        tools = tools_from_openapi(document)
        self.assertEqual(7, len(tools))
        by_name = {tool["function"]["name"]: tool for tool in tools}
        self.assertEqual(
            ["date_of_birth", "phone_last4"],
            tool_body(by_name["verify_identity"])["properties"]["field"]["enum"],
        )
        self.assertEqual(
            ["product_id", "amount", "date"],
            tool_body(by_name["create_promise"])["required"],
        )
        self.assertEqual(
            "{{customer_id}}",
            tool_body(by_name["get_account"])["properties"]["customer_id"]["default"],
        )
        date_field = tool_body(by_name["create_promise"])["properties"]["date"]
        self.assertIn("format: date", date_field["description"])

    def test_synthetic_openapi_controls_names_enums_and_extra_fields(self):
        document = {
            "openapi": "3.0.3",
            "servers": [{"url": "https://example.invalid/api"}],
            "paths": {
                "/renamed_action": {
                    "post": {
                        "summary": "Perform the renamed action.",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "customer_id": {"type": "string"},
                                            "client_ref": {
                                                "type": "string",
                                                "description": "An input-specific reference.",
                                            },
                                            "choice_v2": {
                                                "type": "string",
                                                "enum": ["alpha_v2", "omega_v2"],
                                            },
                                            "extra_count": {"type": "integer"},
                                        },
                                        "required": ["customer_id", "client_ref", "choice_v2", "extra_count"],
                                    }
                                }
                            }
                        },
                    }
                }
            },
        }
        tools = tools_from_openapi(document)
        self.assertEqual(["renamed_action"], [tool["function"]["name"] for tool in tools])
        body = tool_body(tools[0])
        self.assertEqual(["alpha_v2", "omega_v2"], body["properties"]["choice_v2"]["enum"])
        self.assertEqual("integer", body["properties"]["extra_count"]["type"])
        self.assertEqual("{{customer_id}}", body["properties"]["customer_id"]["default"])
        self.assertEqual("{{client_ref}}", body["properties"]["client_ref"]["default"])
        self.assertEqual(
            ["client_ref", "choice_v2", "extra_count"], body["required"]
        )

    def test_nested_array_object_constraints_move_to_descriptions(self):
        document = {
            "servers": [{"url": "https://example.invalid"}],
            "paths": {
                "/complex": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "values": {
                                                "type": "array",
                                                "minItems": 1,
                                                "items": {"type": "integer", "minimum": 2, "maximum": 8},
                                            },
                                            "metadata": {
                                                "type": "object",
                                                "properties": {
                                                    "code": {"type": "string", "pattern": "^[A-Z]+$"}
                                                },
                                                "required": ["code"],
                                            },
                                        },
                                    }
                                }
                            }
                        }
                    }
                }
            },
        }
        warnings = []
        body = tool_body(tools_from_openapi(document, warnings=warnings)[0])
        values = body["properties"]["values"]
        code = body["properties"]["metadata"]["properties"]["code"]
        self.assertNotIn("minItems", values)
        self.assertIn("minItems: 1", values["description"])
        self.assertIn("minimum: 2", values["items"]["description"])
        self.assertNotIn("pattern", code)
        self.assertIn("pattern:", code["description"])
        self.assertEqual(["code"], body["properties"]["metadata"]["required"])
        self.assertTrue(warnings)

    def test_tool_names_are_sanitized_and_collisions_are_renamed(self):
        document = {
            "servers": [{"url": "https://example.invalid"}],
            "paths": {
                "/v1/verify/{id}": {"post": {}},
                "/v1-verify-id": {"post": {}},
            },
        }
        warnings = []
        tools = tools_from_openapi(document, warnings=warnings)
        self.assertEqual(["v1_verify_id", "v1_verify_id_2"], [tool["function"]["name"] for tool in tools])
        self.assertTrue(any("duplicate tool name" in warning for warning in warnings))

    def test_path_item_parameters_warn_and_are_ignored(self):
        document = {
            "servers": [{"url": "https://example.invalid"}],
            "paths": {
                "/thing/{id}": {
                    "parameters": [{"name": "id", "in": "path", "required": True}],
                    "post": {},
                }
            },
        }
        warnings = []
        tools = tools_from_openapi(document, warnings=warnings)
        self.assertEqual(1, len(tools))
        self.assertTrue(any("parameters" in warning for warning in warnings))

    def test_local_ref_is_resolved(self):
        document = {
            "servers": [{"url": "https://example.invalid"}],
            "components": {
                "schemas": {
                    "Body": {
                        "type": "object",
                        "properties": {"renamed": {"type": "string", "format": "date"}},
                        "required": ["renamed"],
                    }
                }
            },
            "paths": {
                "/ref_action": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/Body"}}
                            }
                        }
                    }
                }
            },
        }
        body = tool_body(tools_from_openapi(document)[0])
        self.assertEqual(["renamed"], body["required"])
        self.assertIn("format: date", body["properties"]["renamed"]["description"])

    def test_only_missing_server_is_fatal_and_unknown_type_falls_back(self):
        with self.assertRaisesRegex(OpenAPIError, "servers"):
            tools_from_openapi({"paths": {}})
        document = {
            "servers": [{"url": "https://example.invalid"}],
            "paths": {
                "/bad": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"field": {"type": "mystery"}},
                                    }
                                }
                            }
                        }
                    }
                }
            },
        }
        warnings = []
        field = tool_body(tools_from_openapi(document, warnings=warnings)[0])["properties"]["field"]
        self.assertEqual("string", field["type"])
        self.assertTrue(any("unsupported type" in warning for warning in warnings))

    def test_messy_schema_builds_with_warnings_and_only_allowed_keys(self):
        document = {
            "servers": [{"url": "https://example.invalid"}],
            "paths": {
                "/messy": {
                    "parameters": [{"name": "ignored", "in": "query"}],
                    "post": {
                        "summary": "Handle a messy request.",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "nullable_name": {
                                                "type": ["string", "null"],
                                                "pattern": "^[A-Z]+$",
                                                "x-unknown": "kept as words",
                                            },
                                            "count": {"enum": [1, 2]},
                                            "composed": {
                                                "allOf": [{"type": "string"}, {"maxLength": 8}]
                                            },
                                            "broken": "not-a-schema",
                                        },
                                        "required": ["nullable_name", "count", "composed", "broken"],
                                    }
                                }
                            }
                        },
                    },
                }
            },
        }
        warnings = []
        tool = tools_from_openapi(document, warnings=warnings)[0]
        body = tool_body(tool)
        self.assertEqual("string", body["properties"]["nullable_name"]["type"])
        self.assertEqual("integer", body["properties"]["count"]["type"])
        self.assertEqual("string", body["properties"]["composed"]["type"])
        self.assertEqual("string", body["properties"]["broken"]["type"])
        self.assertNotIn("nullable", body["properties"]["nullable_name"])
        self.assertNotIn("allOf", body["properties"]["composed"])
        self.assertIn("maxLength: 8", body["properties"]["composed"]["description"])
        self.assertNotIn("x-unknown", body["properties"]["nullable_name"].get("description", ""))
        self.assertGreaterEqual(len(warnings), 6)

        def assert_allowed(schema):
            self.assertLessEqual(set(schema), ALLOWED_SCHEMA_KEYS)
            if isinstance(schema.get("items"), dict):
                assert_allowed(schema["items"])
            for child in schema.get("properties", {}).values():
                assert_allowed(child)

        assert_allowed(body)

    def test_all_of_and_implicit_object_preserve_nested_fields(self):
        document = {
            "servers": [{"url": "https://example.invalid"}],
            "paths": {
                "/composed": {
                    "post": {
                        "requestBody": {"content": {"application/json": {"schema": {
                            "allOf": [
                                {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
                                {"properties": {"count": {"type": "integer"}}, "required": ["count"]},
                            ]
                        }}}}
                    }
                }
            },
        }
        warnings = []
        body = tool_body(tools_from_openapi(document, warnings=warnings)[0])
        self.assertEqual({"q", "count"}, set(body["properties"]))
        self.assertEqual(["q", "count"], body["required"])
        self.assertEqual("integer", body["properties"]["count"]["type"])
        self.assertTrue(any("merged allOf" in warning for warning in warnings))

    def test_implicit_nested_properties_infer_object_and_nested_defaults_are_not_baked(self):
        document = {
            "servers": [{"url": "https://example.invalid"}],
            "paths": {"/implicit": {"post": {"requestBody": {"content": {"application/json": {
                "schema": {"type": "object", "properties": {"payload": {
                    "properties": {"z": {"type": "integer", "default": 7}}
                }}}
            }}}}}},
        }
        payload = tool_body(tools_from_openapi(document)[0])["properties"]["payload"]
        self.assertEqual("object", payload["type"])
        self.assertNotIn("default", payload["properties"]["z"])

    def test_model_field_collision_uses_tool_prefixed_placeholder(self):
        document = {
            "servers": [{"url": "https://example.invalid"}],
            "paths": {
                "/collect_label": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"title": {"type": "string"}},
                                        "required": ["title"],
                                    }
                                }
                            }
                        }
                    }
                }
            },
        }
        warnings = []
        tool = tools_from_openapi(
            document,
            warnings=warnings,
            baked_fields={"customer_id"},
            known_entry_variables=CALL_VARIABLES,
        )[0]
        title = tool_body(tool)["properties"]["title"]
        self.assertEqual("{{collect_label_title}}", title["default"])
        self.assertIn("title", tool_body(tool)["required"])
        self.assertTrue(any("collision" in warning for warning in warnings))

    def test_tool_descriptions_have_generic_call_trigger(self):
        document = json.loads(
            (ROOT / "build-the-builder-v2/tools/openapi.json").read_text(encoding="utf-8")
        )
        for tool in tools_from_openapi(document):
            description = tool["function"]["description"]
            self.assertIn("CALL this tool whenever the situation above applies", description)
            self.assertIn("saying you did it is not enough.", description)
            summary = document["paths"]["/" + tool["function"]["name"]]["post"]["summary"]
            self.assertEqual(1, description.count(summary))
        create_description = next(
            tool["function"]["description"] for tool in tools_from_openapi(document)
            if tool["function"]["name"] == "create_promise"
        )
        self.assertIn("Fields: format: date", create_description)
        self.assertNotIn("date: format: date", create_description)

    def test_post_hook_is_safe_and_writes_readable_next_step(self):
        compile(POST_PROCESS_CODE, "<post_process_code>", "exec")
        self.assertNotIn("{{", POST_PROCESS_CODE)
        self.assertNotIn("}}", POST_PROCESS_CODE)
        cases = [
            ({"status_code": 200, "data": {"ok": True}, "header": {"secret": "x"}}, "returned ok"),
            ({"status_code": 200, "data": {"ok": False}}, "NOT carried out"),
            ({"status_code": 500, "data": {"ok": True}}, "NOT carried out"),
            ({"status_code": 200, "data": {"ok": True, "verified": False}}, "verified"),
            ({"status_code": 200, "data": {"value": 1}}, "NOT carried out"),
            ({"status": "error", "data": {"ok": True}}, "NOT carried out"),
            ({"status_code": 200, "data": {"error": "service unavailable"}}, "NOT carried out"),
            ({"status_code": 200, "data": "unexpected"}, "NOT carried out"),
        ]
        for envelope, expected in cases:
            namespace = {"result": envelope}
            exec(POST_PROCESS_CODE, namespace, namespace)
            self.assertNotIn("header", envelope)
            self.assertIn(expected, envelope["data"]["what_to_do_next"])
            if "ok" not in envelope.get("data", {}):
                self.fail("post-hook must normalize data.ok")
            if expected == "NOT carried out":
                self.assertIs(False, envelope["data"]["ok"])
        non_mapping = ["unexpected"]
        namespace = {"result": non_mapping}
        exec(POST_PROCESS_CODE, namespace, namespace)
        self.assertEqual(["unexpected"], non_mapping)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        document = json.loads(
            (ROOT / "build-the-builder-v2/tools/openapi.json").read_text(encoding="utf-8")
        )
        self.tools = tools_from_openapi(document)
        self.workflow = build_workflow("Synthetic runtime brief.", self.tools)

    def test_workflow_has_no_null_or_agent_config_and_names_match_keys(self):
        self.assertFalse(contains_none(self.workflow))
        self.assertNotIn("agent_config", self.workflow)
        for key, node in self.workflow["nodes"].items():
            self.assertEqual(key, node["name"])
        for node in self.workflow["nodes"].values():
            if "tools" in node:
                self.assertEqual("conversation", node["node_type"])

    def test_close_transition_checks_both_boolean_spellings_then_falls_back(self):
        transitions = self.workflow["nodes"]["call"]["transitions"]
        self.assertEqual(
            ["true", "True"],
            [condition["operand"] for condition in transitions[0]["condition"]["conditions"]],
        )
        self.assertEqual("always", transitions[-1]["condition"]["operator"])
        self.assertEqual("call", transitions[-1]["target_node"])

    def test_end_call_is_reachable(self):
        initial = self.workflow["initial_node"]
        pending = [initial]
        visited = set()
        while pending:
            node_name = pending.pop()
            if node_name in visited:
                continue
            visited.add(node_name)
            node = self.workflow["nodes"][node_name]
            pending.extend(
                transition["target_node"]
                for transition in node.get("transitions", [])
                if transition["target_node"] in self.workflow["nodes"]
            )
        self.assertTrue(
            any(
                name in visited and node["node_type"] == "end_call"
                for name, node in self.workflow["nodes"].items()
            )
        )


class TraceTests(unittest.TestCase):
    def test_trace_redacts_freya_secret_values(self):
        api_secret = "fake-api-secret-value"
        bank_secret = "fake-bank-secret-value"
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"FREYA_API_KEY": api_secret, "FREYA_BANK_TEAM_KEY": bank_secret},
        ):
            path = Path(directory) / "trace.log"
            trace = TraceWriter(path, started_at="2000-01-01T00:00:00+00:00")
            trace.add_model_call(
                "synthetic-model", f"purpose included {api_secret}", 0.25
            )
            trace.add("detail", f"bank={bank_secret}")
            trace.finish()
            text = path.read_text(encoding="utf-8")
        self.assertNotIn(api_secret, text)
        self.assertNotIn(bank_secret, text)
        self.assertIn("[REDACTED]", text)

    def test_trace_redacts_unconfigured_freya_key_pattern(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / "trace.log"
            trace = TraceWriter(path)
            trace.add("error", "header contained fak_Abc-123_secret")
            trace.finish()
            text = path.read_text(encoding="utf-8")
        self.assertNotIn("fak_Abc-123_secret", text)
        self.assertIn("[REDACTED]", text)


def minimal_openapi():
    return {
        "servers": [{"url": "https://example.invalid"}],
        "paths": {
            "/close_call": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "customer_id": {"type": "string"},
                                        "outcome_v2": {"type": "string", "enum": ["done_v2"]},
                                    },
                                    "required": ["customer_id", "outcome_v2"],
                                }
                            }
                        }
                    }
                }
            }
        },
    }


class CLITests(unittest.TestCase):
    def _inputs(self, directory):
        brief = Path(directory) / "raw bank memo.md"
        spec = Path(directory) / "tools.json"
        brief.write_text("Synthetic brief supplied at runtime.", encoding="utf-8")
        spec.write_text(json.dumps(minimal_openapi()), encoding="utf-8")
        return brief, spec

    def test_main_print_is_importable_network_free_and_stdout_is_json(self):
        with tempfile.TemporaryDirectory() as directory:
            brief, spec = self._inputs(directory)
            stdout, stderr = StringIO(), StringIO()
            with patch("builder.build.freya.validate_workflow") as validate, patch.dict(
                os.environ, {}, clear=True
            ), working_directory(directory), redirect_stdout(stdout), redirect_stderr(stderr):
                result = build.main([str(brief), str(spec), "--print"])
            self.assertEqual(0, result)
            parsed = json.loads(stdout.getvalue())
            self.assertEqual("call", parsed["initial_node"])
            validate.assert_not_called()
            self.assertIn("slot=raw-bank-memo", stderr.getvalue())
            self.assertTrue((Path(directory) / "traces/raw-bank-memo.print.log").exists())

    def test_validate_prints_success_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            brief, spec = self._inputs(directory)
            stdout = StringIO()
            with patch.dict(os.environ, {"FREYA_API_KEY": "fak_test"}, clear=True), working_directory(
                directory
            ), patch("builder.build.freya.validate_workflow", return_value={}) as validate, redirect_stdout(stdout):
                result = build.main([str(brief), str(spec), "--validate", "--slot", "validation-slot"])
            self.assertEqual(0, result)
            validate.assert_called_once()
            self.assertIn("validate: ok", stdout.getvalue())
            self.assertTrue((Path(directory) / "traces/validation-slot.validate.log").exists())

    def test_failed_run_does_not_overwrite_good_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            brief, spec = self._inputs(directory)
            traces = Path(directory) / "traces"
            traces.mkdir()
            good = traces / "stable.log"
            good.write_text("known-good\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True), working_directory(directory), redirect_stderr(StringIO()):
                result = build.main([str(brief), str(spec), "--slot", "stable"])
            self.assertEqual(1, result)
            self.assertEqual("known-good\n", good.read_text(encoding="utf-8"))
            self.assertTrue((traces / "stable.failed.log").exists())

    def test_long_error_is_truncated_and_redacted(self):
        error = RuntimeError("fak_exposed_123 " + "x" * 500)
        text = build._error_text(error)
        self.assertLessEqual(len(text), 300)
        self.assertNotIn("fak_exposed_123", text)

    def test_keyboard_interrupt_writes_failed_trace_without_overwriting_good_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            brief, spec = self._inputs(directory)
            traces = Path(directory) / "traces"
            traces.mkdir()
            good = traces / "stable.log"
            good.write_text("known-good\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True), working_directory(directory), patch(
                "builder.build.tools_from_openapi", side_effect=KeyboardInterrupt
            ), redirect_stderr(StringIO()), self.assertRaises(KeyboardInterrupt):
                build.main([str(brief), str(spec), "--slot", "stable"])
            self.assertEqual("known-good\n", good.read_text(encoding="utf-8"))
            self.assertIn("status: failed", (traces / "stable.failed.log").read_text(encoding="utf-8"))

    def test_input_error_also_writes_failed_trace(self):
        with tempfile.TemporaryDirectory() as directory, working_directory(directory), redirect_stderr(
            StringIO()
        ):
            result = build.main(["missing-brief.md", "missing-tools.json", "--slot", "bad-input"])
            self.assertEqual(2, result)
            trace = Path("traces/bad-input.failed.log").read_text(encoding="utf-8")
            self.assertIn("status: failed", trace)

    def test_openapi_warnings_are_written_to_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            brief, spec = self._inputs(directory)
            document = minimal_openapi()
            document["paths"]["/close_call"]["post"]["requestBody"]["content"][
                "application/json"
            ]["schema"]["properties"]["outcome_v2"].pop("type")
            spec.write_text(json.dumps(document), encoding="utf-8")
            with working_directory(directory), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                result = build.main([str(brief), str(spec), "--print", "--slot", "warning-case"])
            self.assertEqual(0, result)
            trace = Path(directory, "traces/warning-case.print.log").read_text(encoding="utf-8")
            self.assertIn("warning:", trace)
            self.assertIn("type is missing", trace)


class PublishTests(unittest.TestCase):
    def test_unpublished_newest_version_is_published_and_verified(self):
        before = {"versions": [{"id": "v2", "versionNumber": 2, "isPublished": False}]}
        after = {"versions": [{"id": "v2", "versionNumber": 2, "isPublished": True}]}
        with patch("builder.build.freya.workspace_id", return_value="ws"), patch(
            "builder.build.freya.api", side_effect=[before, {}, after]
        ) as api:
            version = build._ensure_published_version("wf")
        self.assertEqual(2, version)
        self.assertEqual("POST", api.call_args_list[1].args[0])
        self.assertEqual({"versionId": "v2"}, api.call_args_list[1].args[2])

    def test_already_published_newest_version_is_only_checked(self):
        response = {"versions": [{"id": "v3", "versionNumber": 3, "isPublished": True}]}
        with patch("builder.build.freya.workspace_id", return_value="ws"), patch(
            "builder.build.freya.api", return_value=response
        ) as api:
            version = build._ensure_published_version("wf")
        self.assertEqual(3, version)
        api.assert_called_once()

    def test_publish_verification_failure_is_an_error(self):
        response = {"versions": [{"id": "v4", "versionNumber": 4, "isPublished": False}]}
        with patch("builder.build.freya.workspace_id", return_value="ws"), patch(
            "builder.build.freya.api", side_effect=[response, {}, response]
        ), self.assertRaisesRegex(RuntimeError, "was not published"):
            build._ensure_published_version("wf")


class PromptDocumentationTests(unittest.TestCase):
    def test_generated_prompt_document_is_current(self):
        self.assertEqual(
            generate_prompt_doc(),
            prompt_doc_path().read_text(encoding="utf-8"),
            "docs/PROMPTS.md is stale; regenerate it with: python3 -m builder.prompts",
        )

    def test_prompt_document_exposes_token_budget(self):
        document = generate_prompt_doc()
        self.assertEqual(len(PROMPTS), document.count("- Approximate tokens:"))
        self.assertIn("**OVER BUDGET**", document)
        self.assertIn("`{brief_text}` characters ÷ 4", document)

    def test_system_prompt_contains_generic_tool_honesty_rules(self):
        document = generate_prompt_doc()
        self.assertIn("Call at most one tool per message.", document)
        self.assertIn("Never claim an action succeeded unless the tool result says it succeeded.", document)


if __name__ == "__main__":
    unittest.main()
