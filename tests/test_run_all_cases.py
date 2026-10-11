from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tools import run_all_cases


class RunAllCasesTests(unittest.TestCase):
    def state(self, root: Path, include_ab: bool = True) -> Path:
        data = {
            "brief-a": {"workflow_id": "workflow-a", "agent_id": "agent-a", "version": 7},
        }
        if include_ab:
            data["brief-a+brief-b"] = {
                "workflow_id": "workflow-ab", "agent_id": "agent-ab", "version": 8,
            }
        path = root / "agents.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_jobs_cover_baseline_and_five_styles_with_the_right_agents(self):
        agents = {
            "A": run_all_cases.AgentRef("a", "wa", "aa"),
            "B": run_all_cases.AgentRef("ab", "wab", "aab"),
        }
        jobs = run_all_cases.build_jobs(
            agents, Path("results/date"), run_all_cases.DEFAULT_STYLES, 3, 0,
        )
        self.assertEqual(12, len(jobs))
        self.assertEqual(6, sum(job.brief == "A" for job in jobs))
        self.assertEqual(6, sum(job.brief == "B" for job in jobs))
        self.assertTrue(all("--reps" in job.command and "3" in job.command for job in jobs))
        self.assertTrue(all(job.agent.agent_id == ("aa" if job.brief == "A" else "aab") for job in jobs))
        self.assertNotIn("--style", jobs[0].command)
        self.assertIn("--style", jobs[2].command)

    def result(self, job, reps=1, failed_rows=None, failed_final=None):
        count = 10 if job.brief == "A" else 3
        failed_rows = failed_rows or {}
        failed_final = failed_final or {}
        rows = []
        for repetition in range(reps):
            run = []
            for index in range(1, count + 1):
                case = f"PUB-{index:02d}" if job.brief == "A" else f"PUB-{index + 10:02d}"
                failures = failed_rows.get((repetition, case), [])
                run.append({
                    "id": case, "pass": not failures, "failed": failures,
                    "call_id": f"call-{repetition}-{case}",
                })
            rows.append(run)
        final = []
        for row in rows[0]:
            case = row["id"]
            passes = failed_final.get(case, reps)
            final.append({
                "id": case, "family": "test", "passes": passes, "runs": reps,
                "pass": passes == reps,
            })
        return {
            "agent_id": job.agent.agent_id, "runs": reps, "all_rows": rows, "final": final,
        }

    def test_dry_run_only_prints_commands_and_makes_no_result_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.state(root)
            results = root / "never-created"
            output = StringIO()
            with redirect_stdout(output):
                code = run_all_cases.main([
                    "--state-file", str(state), "--results-root", str(results),
                    "--run-label", "fixed", "--dry-run",
                ])
            lines = output.getvalue().splitlines()
            self.assertEqual(0, code)
            self.assertEqual(12, len(lines))
            self.assertTrue(all("run_cases.py" in line and "--reps 3" in line for line in lines))
            self.assertIn("agent-a", lines[0])
            self.assertIn("agent-ab", lines[1])
            self.assertFalse(results.exists())

    def test_baseline_only_prints_two_commands_without_a_style_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = StringIO()
            with redirect_stdout(output):
                code = run_all_cases.main([
                    "--state-file", str(self.state(root)), "--results-root", str(root / "results"),
                    "--run-label", "baseline", "--styles", "baseline", "--dry-run",
                ])
            lines = output.getvalue().splitlines()
            self.assertEqual(0, code)
            self.assertEqual(2, len(lines))
            self.assertTrue(all("--style" not in line for line in lines))

    def test_missing_cumulative_slot_stops_offline_without_creating_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.state(root, include_ab=False)
            results = root / "results"
            error = StringIO()
            with redirect_stderr(error):
                code = run_all_cases.main([
                    "--state-file", str(state), "--results-root", str(results), "--dry-run",
                ])
            self.assertEqual(2, code)
            self.assertIn("brief-a+brief-b", error.getvalue())
            self.assertFalse(results.exists())

    def test_summary_has_one_row_per_case_and_rep_and_does_not_invent_judge_split(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = run_all_cases.AgentRef("brief-a", "workflow-a", "agent-a")
            job = run_all_cases.Job(
                "a", "A", "baseline", agent, root / "a-baseline.json", root / "a-baseline.log", (),
            )
            result = self.result(
                job,
                failed_rows={
                    (0, "PUB-02"): ["wrong callback"],
                    (0, "PUB-03"): ["conversation: policy or honesty check failed"],
                },
                failed_final={"PUB-02": 0, "PUB-03": 0},
            )
            job.output.write_text(json.dumps(result), encoding="utf-8")
            count = run_all_cases.write_summary(root, [job], 1)
            rows = run_all_cases.summary_rows(root, [job], 1)
            self.assertEqual(10, count)
            self.assertEqual(("FAIL", "PASS", "PASS"),
                             (rows[1]["ledger"], rows[1]["policy"], rows[1]["honesty"]))
            self.assertEqual(("PASS", "REVIEW", "REVIEW"),
                             (rows[2]["ledger"], rows[2]["policy"], rows[2]["honesty"]))
            self.assertTrue((root / "summary.tsv").exists())
            self.assertTrue((root / "summary.md").exists())
            summary = (root / "summary.md").read_text(encoding="utf-8")
            self.assertIn("competition score", summary)
            self.assertIn("| a | baseline | 8 | 10 | PUB-02 0/1, PUB-03 0/1 |", summary)
            self.assertNotIn("Overall passes:", summary)

    def test_ledger_identity_breaches_are_policy_failures(self):
        row = {
            "failed": ["get_account called before identity was verified"],
        }
        ledger, policy, conversation = run_all_cases._failure_parts(row)
        self.assertEqual([], ledger)
        self.assertEqual(["get_account called before identity was verified"], policy)
        self.assertEqual([], conversation)

    def test_existing_result_for_another_agent_is_not_resumable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = run_all_cases.AgentRef("brief-a", "workflow-a", "new-agent", 2)
            job = run_all_cases.Job(
                "a", "A", "baseline", agent, root / "a.json", root / "a.log", (),
            )
            result = self.result(job)
            result["agent_id"] = "old-agent"
            job.output.write_text(json.dumps(result), encoding="utf-8")
            loaded, reason = run_all_cases._read_result(job, 1)
            self.assertIsNone(loaded)
            self.assertIn("agent_id differs", reason)

    def test_existing_manifest_for_another_version_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = {"agents": {"A": {"version": 1}}, "repetitions": 3, "styles": ["baseline"],
                   "rerun_if_slow": 0, "git_commit": "same", "commands": ["command"]}
            new = {**old, "agents": {"A": {"version": 2}}}
            path = root / "manifest.json"
            path.write_text(json.dumps(old), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different agents"):
                run_all_cases.prepare_manifest(root, new)
            self.assertEqual(old, json.loads(path.read_text(encoding="utf-8")))

    def test_manifest_records_slot_versions_and_git_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agents = run_all_cases.load_agents(self.state(root), "brief-a", "brief-a+brief-b")
            jobs = run_all_cases.build_jobs(agents, root / "results", ("baseline",), 3, 0)
            manifest = run_all_cases._manifest("run", agents, jobs, 3, 0, None)
            self.assertEqual(7, manifest["agents"]["A"]["version"])
            self.assertEqual(8, manifest["agents"]["B"]["version"])
            self.assertRegex(manifest["git_commit"], r"^(?:[0-9a-f]{40}|unknown)$")

    def test_relative_results_root_is_resolved_against_repository_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = StringIO()
            previous = Path.cwd()
            try:
                os.chdir(root)
                with redirect_stdout(output):
                    code = run_all_cases.main([
                        "--state-file", str(self.state(root)), "--results-root", "relative-results",
                        "--run-label", "fixed", "--styles", "baseline", "--dry-run",
                    ])
            finally:
                os.chdir(previous)
            self.assertEqual(0, code)
            self.assertIn(str(run_all_cases.ROOT / "relative-results" / "fixed"), output.getvalue())
            self.assertFalse((root / "relative-results").exists())

    def test_summary_names_incomplete_jobs_and_updates_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text("{}", encoding="utf-8")
            agent = run_all_cases.AgentRef("brief-a", "workflow-a", "agent-a")
            job = run_all_cases.Job(
                "a", "A", "baseline", agent, root / "missing.json", root / "missing.log", (),
            )
            self.assertEqual(0, run_all_cases.write_summary(root, [job], 3))
            summary = (root / "summary.md").read_text(encoding="utf-8")
            self.assertIn("Expected detailed rows: 30. Found: 0.", summary)
            self.assertIn("`a/baseline`: missing output", summary)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("missing output", manifest["incomplete_jobs"][0]["reason"])

    def test_every_nonzero_run_prints_inspection_advice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            error = StringIO()
            with patch.dict(os.environ, {
                "FREYA_API_KEY": "present", "FREYA_BANK_TEAM_KEY": "sixteen-characters",
            }, clear=True), patch.object(run_all_cases, "_run", return_value=(1, "KeyError: calls")), \
                    redirect_stderr(error):
                code = run_all_cases.main([
                    "--state-file", str(self.state(root)), "--results-root", str(root / "results"),
                    "--run-label", "failed", "--styles", "baseline", "--reps", "1",
                ])
            self.assertEqual(1, code)
            self.assertIn("Inspect any saved call_id", error.getvalue())
            self.assertIn("failed job restarts all of its repetitions", error.getvalue())

    def test_short_bank_team_key_stops_before_creating_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results"
            error = StringIO()
            with patch.dict(os.environ, {
                "FREYA_API_KEY": "present", "FREYA_BANK_TEAM_KEY": "short",
            }, clear=True), redirect_stderr(error):
                code = run_all_cases.main([
                    "--state-file", str(self.state(root)), "--results-root", str(results),
                    "--run-label", "short", "--styles", "baseline",
                ])
            self.assertEqual(2, code)
            self.assertIn("at least 16", error.getvalue())
            self.assertFalse(results.exists())


if __name__ == "__main__":
    unittest.main()
