#!/usr/bin/env python3
"""Offline compliance checks for one builder trace and exported workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


MAX_BUILD_SECONDS = 30 * 60
SECRET_PATTERNS = (
    ("Freya API key", re.compile(r"fak_[A-Za-z0-9_-]+")),
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_-]+")),
    (
        "secret header",
        re.compile(r"(?i)[\"']?(?:authorization|x-api-key|x-team-key)[\"']?\s*[:=]"),
    ),
    (
        "bank team key assignment",
        re.compile(
            r"(?i)(?:FREYA_BANK_TEAM_KEY|bank[_ -]?team[_ -]?key|team[_ -]?key)"
            r"[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_./+=-]{16,}"
        ),
    ),
    ("bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    (
        "key in query string",
        re.compile(r"(?i)[?&](?:api[_-]?key|team[_-]?key|access[_-]?token|token)=[^&\s\"'{}]{8,}"),
    ),
)
SECRET_ENV_NAMES = ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY", "ANTHROPIC_API_KEY")


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str
    warning: str = ""


def _line_values(text: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values.setdefault(key.strip(), []).append(value.strip())
    return values


def _timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _integer(values: dict[str, list[str]], key: str) -> int | None:
    try:
        return int(values[key][-1])
    except (KeyError, TypeError, ValueError):
        return None


def _float(values: dict[str, list[str]], key: str) -> float | None:
    try:
        return float(values[key][-1])
    except (KeyError, TypeError, ValueError):
        return None


def _resolve_named_path(raw: str, trace_path: Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    candidates = [Path.cwd() / path, trace_path.parent / path]
    if trace_path.parent.name == "traces":
        candidates.append(trace_path.parent.parent / path)
    return next((candidate for candidate in candidates if candidate.exists()), candidates[0])


def _first_token(value: str) -> str:
    return value.split(None, 1)[0] if value else ""


def _secret_findings(parts: list[tuple[str, str]]) -> list[str]:
    findings: list[str] = []
    for source, text in parts:
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"{source}: {label}")
        for name in SECRET_ENV_NAMES:
            secret = os.environ.get(name)
            if secret and secret in text:
                findings.append(f"{source}: value from {name}")
    return sorted(set(findings))


def _input_hash_findings(lines: list[str], trace_path: Path) -> list[str]:
    """Re-hash every traced input file; return one finding per missing or changed file."""
    findings: list[str] = []
    for line in lines:
        match = re.match(r"(.+?)\s+sha256=([0-9a-f]{64})\b", line)
        if not match:
            findings.append(f"malformed input line: {line[:80]}")
            continue
        path = _resolve_named_path(match.group(1), trace_path)
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            findings.append(f"{match.group(1)}: file not found")
            continue
        if digest != match.group(2):
            findings.append(f"{match.group(1)}: sha256 differs from the trace")
    return findings


def check_submission(
    trace_path: Path,
    export_path: Path,
    spec_path: Path | None = None,
    *,
    verify_inputs: bool = False,
    require_env: bool = False,
) -> list[Check]:
    checks: list[Check] = []
    try:
        trace_text = trace_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [Check("trace_readable", False, str(exc))]
    values = _line_values(trace_text)

    start = _timestamp(values.get("start_utc", [""])[-1])
    end = _timestamp(values.get("end_utc", [""])[-1])
    times_valid = bool(
        start is not None and end is not None
        and start.tzinfo is not None and end.tzinfo is not None and end >= start
    )
    wall_seconds = (end - start).total_seconds() if times_valid and start and end else None
    checks.append(Check("trace_times", times_valid,
                        "valid start_utc and end_utc" if times_valid else "missing or invalid UTC timestamps"))

    duration = _float(values, "total_duration_seconds")
    checks.append(Check("trace_total_duration", duration is not None and duration >= 0,
                        f"{duration:.3f}s" if duration is not None else "missing total_duration_seconds"))
    under_limit = bool(
        duration is not None and duration < MAX_BUILD_SECONDS
        and wall_seconds is not None and wall_seconds < MAX_BUILD_SECONDS
    )
    checks.append(Check(
        "build_under_30_minutes", under_limit,
        f"duration={duration:.3f}s timestamps={wall_seconds:.3f}s"
        if duration is not None and wall_seconds is not None else "duration unavailable",
    ))

    input_lines = values.get("input", [])
    valid_hashes = all(re.search(r"\bsha256=[0-9a-f]{64}\b", line) for line in input_lines)
    checks.append(Check("trace_input_hashes", len(input_lines) >= 2 and valid_hashes,
                        f"{len(input_lines)} hashed input(s)" if valid_hashes else "missing or malformed input hash"))
    if verify_inputs:
        hash_findings = _input_hash_findings(input_lines, trace_path)
        checks.append(Check(
            "inputs_match_files", bool(input_lines) and not hash_findings,
            "; ".join(hash_findings) if hash_findings else f"{len(input_lines)} file(s) re-hashed and equal",
        ))

    model_summary = values.get("model_calls", [])
    call_lines = values.get("model_call", [])
    summary_match = re.match(r"(\d+)\b", model_summary[-1]) if model_summary else None
    expected_calls = int(summary_match.group(1)) if summary_match else None
    calls_valid = bool(call_lines) and all(
        re.search(r"\bmodel=\S+", line)
        and re.search(r"\bpurpose=\S+", line)
        and re.search(r"\bduration_seconds=\d+(?:\.\d+)?", line)
        for line in call_lines
    )
    checks.append(Check(
        "trace_model_calls",
        expected_calls is not None and expected_calls > 0 and len(call_lines) == expected_calls and calls_valid,
        f"declared={expected_calls} detailed={len(call_lines)}",
    ))
    extraction_match = re.search(r"\bextract_seconds=(\d+(?:\.\d+)?)", model_summary[-1]) if model_summary else None
    checks.append(Check("trace_extraction_duration", extraction_match is not None,
                        f"{extraction_match.group(1)}s" if extraction_match else "missing extract_seconds"))

    for key in ("workflow_id", "agent_id", "published_version"):
        value = values.get(key, [""])[-1]
        valid = bool(value) and (key != "published_version" or value.isdigit())
        checks.append(Check("trace_" + key, valid, value or f"missing {key}"))

    nodes = _integer(values, "nodes")
    global_nodes = _integer(values, "global_nodes")
    steps = _integer(values, "steps")
    tools = _integer(values, "tools")
    counts_valid = (
        nodes is not None and nodes >= 0 and global_nodes is not None and global_nodes >= 0
        and steps == nodes + global_nodes and tools is not None and tools >= 0
    )
    checks.append(Check("trace_step_tool_counts", counts_valid,
                        f"nodes={nodes} global_nodes={global_nodes} steps={steps} tools={tools}"))

    self_tests = values.get("self_test", [])
    self_summary = values.get("self_test_summary", [])
    self_valid = bool(self_tests) and bool(self_summary) and all(
        re.search(r"\bcase=\S+\s+result=(?:pass|fail|platform_error)\b", line)
        for line in self_tests
    )
    not_passed = [
        match.group(1) + "=" + match.group(2)
        for line in self_tests
        for match in [re.search(r"\bcase=(\S+)\s+result=(fail|platform_error)\b", line)]
        if match
    ]
    checks.append(Check(
        "trace_self_tests", self_valid,
        f"{len(self_tests)} case line(s), summary={'yes' if self_summary else 'no'}",
        "self-test not passed: " + ", ".join(not_passed) if not_passed else "",
    ))
    status = values.get("status", [""])[-1]
    checks.append(Check("trace_final_status", status == "ok", f"status={status or 'missing'}"))

    # The kit's no-null / no-agent_config rules apply to the definition the builder sent;
    # the exported file always carries platform-filled agent_config and null defaults.
    sent_agent_config = values.get("sent_agent_config", [""])[-1]
    sent_nulls = _integer(values, "sent_nulls")
    checks.append(Check(
        "sent_definition_clean", sent_agent_config == "absent" and sent_nulls == 0,
        f"sent_agent_config={sent_agent_config or 'missing'} sent_nulls="
        + (str(sent_nulls) if sent_nulls is not None else "missing"),
    ))

    named_spec = _first_token(values.get("spec", [""])[-1])
    named_spec_path = _resolve_named_path(named_spec, trace_path) if named_spec else None
    named_exists = bool(named_spec_path and named_spec_path.is_file())
    matches_argument = True
    if spec_path is not None:
        matches_argument = spec_path.is_file() and bool(
            named_spec_path and named_spec_path.resolve() == spec_path.resolve()
        )
    checks.append(Check(
        "trace_spec_artifact", named_exists and matches_argument,
        str(named_spec_path) if named_spec_path else "trace has no spec path",
    ))

    try:
        export_text = export_path.read_text(encoding="utf-8")
        exported = json.loads(export_text)
        export_valid = isinstance(exported, dict) and isinstance(exported.get("workflow"), dict)
    except (OSError, json.JSONDecodeError) as exc:
        export_text, exported, export_valid = "", {}, False
        export_error = str(exc)
    else:
        export_error = "valid JSON export"
    checks.append(Check("export_parses", export_valid, export_error))

    trace_workflow_id = values.get("workflow_id", [""])[-1]
    export_workflow_id = str(exported.get("workflow_id", "")) if export_valid else ""
    checks.append(Check("export_workflow_id_matches", bool(trace_workflow_id) and export_workflow_id == trace_workflow_id,
                        f"trace={trace_workflow_id or 'missing'} export={export_workflow_id or 'missing'}"))
    workflow = exported.get("workflow", {}) if export_valid else {}
    export_steps = (
        len(workflow.get("nodes", {})) + len(workflow.get("global_nodes", {}))
        if isinstance(workflow.get("nodes"), dict) and isinstance(workflow.get("global_nodes", {}), dict)
        else None
    )
    checks.append(Check("export_step_count_matches", steps is not None and export_steps == steps,
                        f"trace={steps} export={export_steps}"))

    secret_parts = [("trace", trace_text), ("export", export_text)]
    if named_spec_path and named_spec_path.is_file():
        try:
            secret_parts.append(("spec", named_spec_path.read_text(encoding="utf-8")))
        except OSError:
            pass
    findings = _secret_findings(secret_parts)
    missing_env = [name for name in SECRET_ENV_NAMES if not os.environ.get(name)]
    env_note = "exact-value scan skipped: " + ", ".join(missing_env) + " not set" if missing_env else ""
    if findings:
        detail = "; ".join(findings)
    elif missing_env:
        detail = "no secret patterns" + ("; " + env_note if require_env else "")
    else:
        detail = "no secret patterns or configured secret values"
    checks.append(Check(
        "no_secrets", not findings and not (require_env and missing_env), detail,
        env_note if not require_env else "",
    ))
    return checks


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check one trace and workflow export offline.")
    parser.add_argument("trace", type=Path)
    parser.add_argument("export", type=Path)
    parser.add_argument("--spec", type=Path, help="expected extracted spec artifact")
    parser.add_argument("--verify-inputs", action="store_true",
                        help="re-hash the input files named in the trace and compare")
    parser.add_argument("--require-env", action="store_true",
                        help="fail when a secret env variable is unset (exact-value scan needs them)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    checks = check_submission(
        args.trace, args.export, args.spec,
        verify_inputs=args.verify_inputs, require_env=args.require_env,
    )
    for check in checks:
        line = f"{'PASS' if check.passed else 'FAIL'} {check.name}: {check.detail}"
        print(line + (f" WARN: {check.warning}" if check.warning else ""))
    passed = sum(check.passed for check in checks)
    warnings = sum(bool(check.warning) for check in checks)
    print(
        f"SUMMARY: {'PASS' if passed == len(checks) else 'FAIL'} ({passed}/{len(checks)} checks passed"
        + (f", {warnings} warning(s))" if warnings else ")")
    )
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
