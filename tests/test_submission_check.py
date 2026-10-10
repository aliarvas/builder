from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from builder import build
from builder.run_trace import TraceWriter
from tools.submission_check import check_submission, main


ROOT = Path(__file__).resolve().parents[1]
HASH = "a" * 64


class SubmissionCheckTests(unittest.TestCase):
    def make_artifacts(self, directory: str):
        root = Path(directory)
        spec = root / "slot.spec.json"
        trace = root / "slot.log"
        export = root / "slot.workflow.json"
        spec.write_text("{}\n", encoding="utf-8")
        trace.write_text("\n".join([
            "start_utc: 2026-10-10T10:00:00+00:00",
            f"input: brief.md sha256={HASH}",
            f"input: tools.json sha256={HASH}",
            "model_call: model=test-model purpose=extract:rules duration_seconds=2.500",
            "model_calls: 1 input_tokens=10 output_tokens=5 model_seconds=2.5 extract_seconds=3.0",
            f"spec: {spec} extracted; unmapped_items=0 warnings=0",
            "nodes: 2",
            "global_nodes: 1",
            "steps: 3",
            "tools: 7",
            "sent_agent_config: absent",
            "sent_nulls: 0",
            "workflow_id: workflow-1",
            "agent_id: agent-1",
            "published_version: 4",
            "self_test: case=smoke result=pass reason=ok call_id=call-1 seconds=1.0",
            "self_test_summary: total=1 pass=1 fail=0 platform_error=0",
            "total_duration_seconds: 10.000",
            "status: ok",
            "end_utc: 2026-10-10T10:00:10+00:00",
            "",
        ]), encoding="utf-8")
        export.write_text(json.dumps({
            "workflow_id": "workflow-1",
            "agent_id": "agent-1",
            "updated_at": "2026-10-10T10:00:09Z",
            "workflow": {
                "initial_node": "one",
                "nodes": {"one": {}, "two": {}},
                "global_nodes": {"global": {}},
                "system_prompt": "test",
                "test_variables": {},
                "tools": [],
            },
        }), encoding="utf-8")
        return trace, export, spec

    def failures(self, checks):
        return {check.name for check in checks if not check.passed}

    def test_good_trace_export_and_spec_pass_every_check(self):
        with tempfile.TemporaryDirectory() as directory:
            trace, export, spec = self.make_artifacts(directory)
            checks = check_submission(trace, export, spec)
            self.assertTrue(checks)
            self.assertEqual(set(), self.failures(checks))
            output = StringIO()
            with redirect_stdout(output):
                code = main([str(trace), str(export), "--spec", str(spec)])
            self.assertEqual(0, code)
            self.assertIn("SUMMARY: PASS", output.getvalue())

    def test_trace_with_api_or_team_key_fails_secret_check(self):
        with tempfile.TemporaryDirectory() as directory:
            trace, export, spec = self.make_artifacts(directory)
            trace.write_text(
                trace.read_text(encoding="utf-8")
                + "debug: Authorization: Bearer fak_exposed\n"
                + "debug: FREYA_BANK_TEAM_KEY=abcdefghijklmnop\n",
                encoding="utf-8",
            )
            checks = check_submission(trace, export, spec)
            self.assertIn("no_secrets", self.failures(checks))

    def test_missing_trace_items_fail_individually(self):
        with tempfile.TemporaryDirectory() as directory:
            trace, export, spec = self.make_artifacts(directory)
            trace.write_text("start_utc: 2026-10-10T10:00:00+00:00\n", encoding="utf-8")
            failures = self.failures(check_submission(trace, export, spec))
            self.assertIn("trace_times", failures)
            self.assertIn("trace_model_calls", failures)
            self.assertIn("trace_extraction_duration", failures)
            self.assertIn("trace_self_tests", failures)
            self.assertIn("trace_final_status", failures)

    def test_mismatched_export_id_and_step_count_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            trace, export, spec = self.make_artifacts(directory)
            data = json.loads(export.read_text(encoding="utf-8"))
            data["workflow_id"] = "other-workflow"
            data["workflow"]["global_nodes"] = {}
            export.write_text(json.dumps(data), encoding="utf-8")
            failures = self.failures(check_submission(trace, export, spec))
            self.assertIn("export_workflow_id_matches", failures)
            self.assertIn("export_step_count_matches", failures)

    def test_build_over_thirty_minutes_fails_budget_check(self):
        with tempfile.TemporaryDirectory() as directory:
            trace, export, spec = self.make_artifacts(directory)
            text = trace.read_text(encoding="utf-8")
            text = text.replace("total_duration_seconds: 10.000", "total_duration_seconds: 1800.000")
            trace.write_text(text, encoding="utf-8")
            self.assertIn(
                "build_under_30_minutes", self.failures(check_submission(trace, export, spec))
            )

    def test_platform_shaped_export_with_agent_config_and_nulls_passes(self):
        # The real export carries platform defaults (review T-008 finding 1).
        with tempfile.TemporaryDirectory() as directory:
            trace, export, spec = self.make_artifacts(directory)
            data = json.loads(export.read_text(encoding="utf-8"))
            data["workflow"]["agent_config"] = {"apiKey": None, "llmConfig": {"model": "m"}}
            for node in data["workflow"]["nodes"].values():
                node.update({"max_node_turns": None, "passthrough_default_transition": None})
            export.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(set(), self.failures(check_submission(trace, export, spec)))

    def test_sent_definition_with_null_or_agent_config_fails(self):
        for old, new in (("sent_nulls: 0", "sent_nulls: 3"),
                         ("sent_agent_config: absent", "sent_agent_config: present"),
                         ("sent_nulls: 0\n", "")):
            with self.subTest(change=new or "missing"), tempfile.TemporaryDirectory() as directory:
                trace, export, spec = self.make_artifacts(directory)
                trace.write_text(trace.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
                self.assertIn("sent_definition_clean", self.failures(check_submission(trace, export, spec)))

    def test_more_secret_shapes_are_caught(self):
        for text in ('{"team_key": "abcdefghijklmnopqrst"}',
                     "header Bearer abcdefghijklmnopqrstuv",
                     "GET /v1/thing?apikey=abcdefgh1234"):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                trace, export, spec = self.make_artifacts(directory)
                trace.write_text(trace.read_text(encoding="utf-8") + "debug: " + text + "\n", encoding="utf-8")
                self.assertIn("no_secrets", self.failures(check_submission(trace, export, spec)))

    def test_template_placeholder_is_not_a_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            trace, export, spec = self.make_artifacts(directory)
            trace.write_text(trace.read_text(encoding="utf-8") + "debug: /x?api_key={{team_key}}\n",
                             encoding="utf-8")
            self.assertNotIn("no_secrets", self.failures(check_submission(trace, export, spec)))

    def test_missing_env_warns_and_require_env_fails(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            trace, export, spec = self.make_artifacts(directory)
            check = {c.name: c for c in check_submission(trace, export, spec)}["no_secrets"]
            self.assertTrue(check.passed)
            self.assertIn("FREYA_BANK_TEAM_KEY", check.warning)
            self.assertIn("not set", check.warning)
            strict = {c.name: c for c in check_submission(trace, export, spec, require_env=True)}
            self.assertFalse(strict["no_secrets"].passed)
            self.assertIn("exact-value scan skipped", strict["no_secrets"].detail)

    def test_env_values_present_scan_exact_value_without_warning(self):
        env = {name: "configured-value-" + name for name in
               ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY", "ANTHROPIC_API_KEY")}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, env, clear=True):
            trace, export, spec = self.make_artifacts(directory)
            check = {c.name: c for c in check_submission(trace, export, spec, require_env=True)}["no_secrets"]
            self.assertTrue(check.passed)
            self.assertEqual("", check.warning)
            trace.write_text(trace.read_text(encoding="utf-8") + "x " + env["FREYA_BANK_TEAM_KEY"] + "\n",
                             encoding="utf-8")
            self.assertIn("no_secrets", self.failures(check_submission(trace, export, spec)))

    def test_failed_self_test_passes_with_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            trace, export, spec = self.make_artifacts(directory)
            trace.write_text(trace.read_text(encoding="utf-8").replace(
                "case=smoke result=pass", "case=smoke result=fail"), encoding="utf-8")
            check = {c.name: c for c in check_submission(trace, export, spec)}["trace_self_tests"]
            self.assertTrue(check.passed)
            self.assertIn("smoke=fail", check.warning)
            output = StringIO()
            with redirect_stdout(output):
                main([str(trace), str(export), "--spec", str(spec)])
            self.assertIn("WARN: self-test not passed: smoke=fail", output.getvalue())

    def test_verify_inputs_compares_real_file_hashes(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            trace, export, spec = self.make_artifacts(directory)
            brief = Path(directory) / "brief.md"
            tools = Path(directory) / "tools.json"
            brief.write_text("brief", encoding="utf-8")
            tools.write_text("{}", encoding="utf-8")
            text = trace.read_text(encoding="utf-8")
            text = text.replace(f"input: brief.md sha256={HASH}",
                                f"input: {brief} sha256={hashlib.sha256(b'brief').hexdigest()}")
            text = text.replace(f"input: tools.json sha256={HASH}",
                                f"input: {tools} sha256={hashlib.sha256(b'{}').hexdigest()}")
            trace.write_text(text, encoding="utf-8")
            self.assertNotIn("inputs_match_files", {c.name for c in check_submission(trace, export, spec)})
            self.assertEqual(set(), self.failures(check_submission(trace, export, spec, verify_inputs=True)))
            brief.write_text("changed", encoding="utf-8")
            failures = self.failures(check_submission(trace, export, spec, verify_inputs=True))
            self.assertEqual({"inputs_match_files"}, failures)
            tools.unlink()
            check = {c.name: c for c in check_submission(trace, export, spec, verify_inputs=True)}
            self.assertIn("file not found", check["inputs_match_files"].detail)


class TraceGapTests(unittest.TestCase):
    def test_trace_writer_records_total_duration(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "builder.run_trace.time.monotonic", side_effect=[100.0, 112.5]
        ):
            path = Path(directory) / "trace.log"
            trace = TraceWriter(path, started_at="2026-10-10T10:00:00+00:00")
            trace.finish()
            self.assertIn("total_duration_seconds: 12.500", path.read_text(encoding="utf-8"))

    def test_builder_trace_records_total_step_count_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            os.chdir(directory)
            try:
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    code = build.main([
                        str(ROOT / "build-the-builder-v2/briefs/brief-a.md"),
                        str(ROOT / "build-the-builder-v2/tools/openapi.json"),
                        "--spec", str(ROOT / "tests/fixtures/spec-brief-a.json"),
                        "--print", "--slot", "trace-steps",
                    ])
                self.assertEqual(0, code)
                text = Path("traces/trace-steps.print.log").read_text(encoding="utf-8")
                self.assertRegex(text, r"(?m)^steps: \d+$")
                self.assertRegex(text, r"(?m)^sent_agent_config: absent$")
                self.assertRegex(text, r"(?m)^sent_nulls: 0$")
                self.assertRegex(text, r"(?m)^total_duration_seconds: \d+\.\d{3}$")
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
