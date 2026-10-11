#!/usr/bin/env python3
"""Run the complete public-case matrix with the agents recorded by the builder.

Dry-run is offline: it only prints the exact ``run_cases.py`` commands and does
not create a result directory.  A real run requires the Freya environment to be
configured by the caller; this script never reads or prints credential values.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
KIT_RUNNER = Path("build-the-builder-v2/tools/run_cases.py")
PUBLIC_CASES = Path("build-the-builder-v2/public-test-set.json")
DEFAULT_STYLES = ("baseline", "pieces", "corrects", "talkative", "asks_back", "in_words")
STYLE_CHOICES = frozenset(DEFAULT_STYLES)
SERVER_ERROR = re.compile(r"(?:\bHTTP(?:\s+Error)?|->)\s*5\d\d\b", re.I)
POLICY_FAILURE_MARKERS = (
    "before identity was verified",
    "although the customer was not on the line",
)


@dataclass(frozen=True)
class AgentRef:
    slot: str
    workflow_id: str
    agent_id: str
    version: str | int | None = None


@dataclass(frozen=True)
class Job:
    suite: str
    brief: str
    style: str
    agent: AgentRef
    output: Path
    log: Path
    command: tuple[str, ...]


def load_agents(state_path: Path, a_slot: str, ab_slot: str) -> dict[str, AgentRef]:
    """Read only workflow/agent identifiers from the builder's local slot map."""
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"slot map not found: {state_path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"slot map is unreadable: {state_path}: {exc}") from exc
    if not isinstance(state, dict):
        raise ValueError(f"slot map must contain an object: {state_path}")

    def one(slot: str) -> AgentRef:
        item = state.get(slot)
        if not isinstance(item, dict):
            raise ValueError(f"slot {slot!r} is missing from {state_path}")
        workflow_id = item.get("workflow_id")
        agent_id = item.get("agent_id")
        if not isinstance(workflow_id, str) or not workflow_id.strip():
            raise ValueError(f"slot {slot!r} has no workflow_id")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError(f"slot {slot!r} has no agent_id")
        version = item.get("version")
        if version is not None and not isinstance(version, (str, int)):
            raise ValueError(f"slot {slot!r} has an invalid version")
        return AgentRef(slot, workflow_id, agent_id, version)

    return {"A": one(a_slot), "B": one(ab_slot)}


def build_jobs(
    agents: dict[str, AgentRef], run_dir: Path, styles: tuple[str, ...], reps: int,
    rerun_if_slow: int,
) -> list[Job]:
    jobs: list[Job] = []
    for style in styles:
        for suite, brief in (("a", "A"), ("ab", "B")):
            stem = f"{suite}-{style}"
            output = run_dir / f"{stem}.json"
            log = run_dir / f"{stem}.log"
            command = [
                sys.executable,
                str(KIT_RUNNER),
                agents[brief].agent_id,
                "--cases", str(PUBLIC_CASES),
                "--brief", brief,
                "--reps", str(reps),
                "--out", str(output),
            ]
            if style != "baseline":
                command.extend(("--style", style))
            if rerun_if_slow:
                command.extend(("--rerun-if-slow", str(rerun_if_slow)))
            jobs.append(Job(suite, brief, style, agents[brief], output, log, tuple(command)))
    return jobs


def _failure_parts(row: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    failures = [str(item) for item in row.get("failed", [])]
    conversation = [item for item in failures if item.startswith("conversation:")]
    policy = [item for item in failures if any(marker in item for marker in POLICY_FAILURE_MARKERS)]
    ledger = [item for item in failures if item not in conversation and item not in policy]
    return ledger, policy, conversation


def _read_result(job: Job, reps: int) -> tuple[dict[str, Any] | None, str]:
    """Read one complete kit result, including the fields that make resume safe."""
    if not job.output.exists():
        return None, "missing output"
    try:
        result = json.loads(job.output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"unreadable JSON: {exc}"
    if not isinstance(result, dict):
        return None, "result is not an object"
    if result.get("agent_id") != job.agent.agent_id:
        return None, f"agent_id differs (expected {job.agent.agent_id})"
    if result.get("runs") != reps:
        return None, f"runs differs (expected {reps})"
    expected_cases = 10 if job.brief == "A" else 3
    all_rows = result.get("all_rows")
    if not isinstance(all_rows, list) or len(all_rows) != reps:
        return None, f"all_rows does not contain {reps} repetitions"
    if any(not isinstance(rows, list) or len(rows) != expected_cases for rows in all_rows):
        return None, f"a repetition does not contain {expected_cases} cases"
    final = result.get("final")
    if not isinstance(final, list) or len(final) != expected_cases:
        return None, f"final does not contain {expected_cases} customers"
    return result, ""


def _collect_results(
    jobs: list[Job], reps: int,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[dict[str, str]]]:
    """Flatten the kit's all_rows into one row per case and repetition.

    The kit exposes one combined judge verdict for policy and honesty.  A judge
    failure therefore marks both columns REVIEW instead of inventing a split.
    """
    flattened: list[dict[str, str]] = []
    scores: list[dict[str, Any]] = []
    incomplete: list[dict[str, str]] = []
    for job in jobs:
        result, reason = _read_result(job, reps)
        if result is None:
            incomplete.append({"suite": job.suite, "style": job.style, "reason": reason})
            continue
        for repetition, rows in enumerate(result.get("all_rows", []), 1):
            for row in rows:
                ledger_failures, policy_failures, conversation_failures = _failure_parts(row)
                flattened.append({
                    "suite": job.suite,
                    "style": job.style,
                    "case": str(row.get("id", "")),
                    "repetition": str(repetition),
                    "ledger": "FAIL" if ledger_failures else "PASS",
                    "policy": "FAIL" if policy_failures else
                              ("REVIEW" if conversation_failures else "PASS"),
                    "honesty": "REVIEW" if conversation_failures else "PASS",
                    "overall": "PASS" if row.get("pass") else "FAIL",
                    "call_id": str(row.get("call_id") or ""),
                    "failures": " | ".join(str(item).replace("\t", " ").replace("\n", " ")
                                           for item in row.get("failed", [])),
                })
        failed = [
            f"{item.get('id', '?')} {item.get('passes', 0)}/{item.get('runs', reps)}"
            for item in result["final"] if not item.get("pass")
        ]
        scores.append({
            "suite": job.suite,
            "style": job.style,
            "passed": sum(bool(item.get("pass")) for item in result["final"]),
            "total": len(result["final"]),
            "failed": failed,
        })
    return flattened, scores, incomplete


def summary_rows(run_dir: Path, jobs: list[Job], reps: int) -> list[dict[str, str]]:
    """Compatibility helper for consumers that need only per-repetition rows."""
    rows, _, _ = _collect_results(jobs, reps)
    return rows


def write_summary(run_dir: Path, jobs: list[Job], reps: int) -> int:
    rows, scores, incomplete = _collect_results(jobs, reps)
    columns = ("suite", "style", "case", "repetition", "ledger", "policy", "honesty",
               "overall", "call_id", "failures")
    tsv = ["\t".join(columns)]
    tsv.extend("\t".join(row[column] for column in columns) for row in rows)
    (run_dir / "summary.tsv").write_text("\n".join(tsv) + "\n", encoding="utf-8")

    markdown = [
        "# Public case matrix",
        "",
        "## All-or-nothing customer score (this is the competition score)",
        "",
        f"A customer counts only after passing all {reps} repetitions.",
        "",
        "| Suite | Style | Customers passing all reps | Total | Failed customers (passes/runs) |",
        "|---|---|---:|---:|---|",
    ]
    markdown.extend(
        f"| {score['suite']} | {score['style']} | {score['passed']} | {score['total']} | "
        f"{', '.join(score['failed']) or '-'} |"
        for score in scores
    )
    markdown.extend([
        "",
        "## Completeness",
        "",
        f"Expected detailed rows: {sum((10 if job.brief == 'A' else 3) * reps for job in jobs)}. "
        f"Found: {len(rows)}.",
        "",
    ])
    if incomplete:
        markdown.append("Incomplete jobs:")
        markdown.append("")
        markdown.extend(
            f"- `{item['suite']}/{item['style']}`: {item['reason']}" for item in incomplete
        )
        markdown.append("")
    else:
        markdown.extend(("All planned jobs have complete, matching result files.", ""))
    markdown.extend([
        "## Per-repetition detail",
        "",
        "`policy` and `honesty` are `REVIEW` together when the kit's combined conversation judge fails; "
        "`run_cases.py` does not expose separate verdicts for them. Ledger evidence of tools used before "
        "identity or while the customer is not on the line is classified as `policy: FAIL`.",
        "",
        "| Suite | Style | Case | Rep | Ledger | Policy | Honesty | Overall | Call ID |",
        "|---|---|---|---:|---|---|---|---|---|",
    ])
    markdown.extend(
        f"| {row['suite']} | {row['style']} | {row['case']} | {row['repetition']} | "
        f"{row['ledger']} | {row['policy']} | {row['honesty']} | {row['overall']} | "
        f"{row['call_id']} |"
        for row in rows
    )
    markdown.extend(("", f"Detailed rows found: {len(rows)}."))
    (run_dir / "summary.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["incomplete_jobs"] = incomplete
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return len(rows)


def _cost(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("cost must be a decimal number") from exc
    if result < 0:
        raise argparse.ArgumentTypeError("cost must not be negative")
    return result


def _manifest(
    run_label: str, agents: dict[str, AgentRef], jobs: list[Job], reps: int,
    rerun_if_slow: int, cost_per_call: Decimal | None,
) -> dict[str, Any]:
    case_calls = 13 * reps * len({job.style for job in jobs})
    simulations = len(jobs) * reps
    # The kit documents 3-11 minutes for ten customers. This proportional range
    # is a planning estimate, not a platform guarantee.
    low_minutes = case_calls * Decimal("0.3")
    high_minutes = case_calls * Decimal("1.1")
    return {
        "run_label": run_label,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "agents": {
            brief: {
                "slot": agent.slot,
                "workflow_id": agent.workflow_id,
                "agent_id": agent.agent_id,
                "version": agent.version,
            }
            for brief, agent in agents.items()
        },
        "repetitions": reps,
        "styles": list(dict.fromkeys(job.style for job in jobs)),
        "planned_case_calls": case_calls,
        "planned_simulations": simulations,
        "duration_estimate_minutes": {
            "low": float(low_minutes),
            "high": float(high_minutes),
            "basis": "kit says 10 customers take 3-11 minutes; proportional planning estimate",
        },
        "cost_estimate": (
            {"currency": "USD", "per_call": str(cost_per_call),
             "total": str(cost_per_call * case_calls)}
            if cost_per_call is not None
            else {"status": "unknown", "reason": "starter kit publishes no simulation price"}
        ),
        "rerun_if_slow": rerun_if_slow,
        "git_commit": _git_commit(),
        "commands": [shlex.join(job.command) for job in jobs],
        "incomplete_jobs": [
            {"suite": job.suite, "style": job.style, "reason": "missing output"} for job in jobs
        ],
    }


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=ROOT, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _manifest_identity(manifest: dict[str, Any]) -> dict[str, Any]:
    """Fields that must remain identical when resuming into an existing directory."""
    return {
        key: manifest.get(key)
        for key in ("agents", "repetitions", "styles", "rerun_if_slow", "git_commit", "commands")
    }


def prepare_manifest(run_dir: Path, expected: dict[str, Any]) -> None:
    """Create a manifest once, or reject a resume whose tested build differs."""
    path = run_dir / "manifest.json"
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"existing manifest is unreadable: {exc}") from exc
        if not isinstance(existing, dict):
            raise ValueError("existing manifest is not an object")
        if _manifest_identity(existing) != _manifest_identity(expected):
            raise ValueError(
                "existing manifest belongs to different agents, versions, options, or git commit; "
                "choose a new --run-label"
            )
        return
    path.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")


def _run(job: Job) -> tuple[int, str]:
    print(f"\n$ {shlex.join(job.command)}", flush=True)
    lines: list[str] = []
    with job.log.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            job.command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
            lines.append(line)
        return process.wait(), "".join(lines)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run all public A and A+B cases, repetitions and styles")
    ap.add_argument("--state-file", type=Path, default=Path(".freya-agents.json"))
    ap.add_argument("--a-slot", default="brief-a", help="slot whose agent runs the ten Brief A cases")
    ap.add_argument("--ab-slot", default="brief-a+brief-b",
                    help="slot whose cumulative A+B agent runs PUB-11..PUB-13")
    ap.add_argument("--results-root", type=Path, default=Path("results"))
    ap.add_argument("--run-label", help="result directory name; default is local date and time")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument(
        "--styles", nargs="+", default=list(DEFAULT_STYLES),
        help="styles to run; use '--styles baseline' for only the normal no-style run",
    )
    ap.add_argument("--rerun-if-slow", type=int, default=0,
                    help="pass through to the kit; each discarded slow run waits five minutes")
    ap.add_argument("--cost-per-call", type=_cost,
                    help="optional USD planning rate; the kit does not publish one")
    ap.add_argument("--dry-run", action="store_true", help="print commands only; make no files or requests")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.reps < 1:
        parser().error("--reps must be at least 1")
    if args.rerun_if_slow < 0:
        parser().error("--rerun-if-slow must not be negative")
    unknown = [style for style in args.styles if style not in STYLE_CHOICES]
    if unknown:
        parser().error("unknown styles: " + ", ".join(unknown))
    styles = tuple(dict.fromkeys(args.styles))
    run_label = args.run_label or datetime.now().astimezone().strftime("%Y-%m-%d_%H%M%S")
    results_root = args.results_root if args.results_root.is_absolute() else ROOT / args.results_root
    run_dir = results_root / run_label
    state_path = args.state_file if args.state_file.is_absolute() else ROOT / args.state_file
    try:
        agents = load_agents(state_path, args.a_slot, args.ab_slot)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    jobs = build_jobs(agents, run_dir, styles, args.reps, args.rerun_if_slow)

    if args.dry_run:
        for job in jobs:
            print(shlex.join(job.command))
        return 0

    missing = [name for name in ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY") if not os.environ.get(name)]
    if missing:
        print("error: required environment variable(s) are not set: " + ", ".join(missing), file=sys.stderr)
        return 2
    if len(os.environ["FREYA_BANK_TEAM_KEY"]) < 16:
        print("error: FREYA_BANK_TEAM_KEY must contain at least 16 characters", file=sys.stderr)
        return 2

    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(run_label, agents, jobs, args.reps, args.rerun_if_slow, args.cost_per_call)
    try:
        prepare_manifest(run_dir, manifest)
    except ValueError as exc:
        print(f"error: cannot resume {run_dir}: {exc}", file=sys.stderr)
        return 2
    for job in jobs:
        if job.output.exists():
            _, reason = _read_result(job, args.reps)
            if reason:
                print(
                    f"error: cannot resume with {job.output}: {reason}; choose a new --run-label "
                    "or move the stale file",
                    file=sys.stderr,
                )
                write_summary(run_dir, jobs, args.reps)
                return 2
            print(f"SKIP existing result: {job.output}", flush=True)
            continue
        code, output = _run(job)
        write_summary(run_dir, jobs, args.reps)
        if code:
            print(f"run stopped; command exited {code}. Artifacts kept in {run_dir}", file=sys.stderr)
            if SERVER_ERROR.search(output):
                print("output looks like a platform 5xx.", file=sys.stderr)
            print(
                "Do not blindly retry. Inspect any saved call_id in the call record and ledger first; "
                "after confirming the turn was not processed, rerun with the same "
                f"--run-label {run_label}. The failed job restarts all of its repetitions.",
                file=sys.stderr,
            )
            return code
    rows = write_summary(run_dir, jobs, args.reps)
    print(f"\nComplete: {rows} case-repetition rows. Summary: {run_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
