#!/usr/bin/env python3
"""CLI entry point for the generic Freya workflow builder."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

if __package__:
    from . import freya
    from .run_trace import FREYA_KEY_PATTERN, TraceWriter
    from .spec import SpecError, load_spec, spec_entry_variables
    from .tools_from_openapi import CALL_VARIABLES, OpenAPIError, tools_from_openapi
    from .workflow import build_spec_workflow, build_workflow, workflow_prompt_estimates, workflow_tools_by_step
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from builder import freya
    from builder.run_trace import FREYA_KEY_PATTERN, TraceWriter
    from builder.spec import SpecError, load_spec, spec_entry_variables
    from builder.tools_from_openapi import CALL_VARIABLES, OpenAPIError, tools_from_openapi
    from builder.workflow import build_spec_workflow, build_workflow, workflow_prompt_estimates, workflow_tools_by_step


class BuilderInputError(ValueError):
    """Raised when CLI input files cannot be loaded."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a Freya workflow from one or more bank briefs and an OpenAPI file."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--print", dest="print_only", action="store_true", help="print JSON without network calls")
    mode.add_argument("--validate", action="store_true", help="run only Freya's dry-run validation")
    parser.add_argument("--slot", help="stable workflow slot name")
    parser.add_argument("--spec", dest="spec_path", help="validated versioned agent spec JSON")
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="PATH",
        help="brief file(s), followed by the OpenAPI JSON file",
    )
    return parser


def _default_slot(brief_paths: list[Path]) -> str:
    raw = "+".join(path.stem for path in brief_paths)
    slot = re.sub(r"[^A-Za-z0-9._+-]+", "-", raw).strip("-.")
    return slot or "workflow"


def _load_inputs(paths: list[str]) -> tuple[list[Path], Path, str, dict[str, Any]]:
    if len(paths) < 2:
        raise BuilderInputError("provide at least one brief file followed by one OpenAPI file")
    brief_paths = [Path(value) for value in paths[:-1]]
    openapi_path = Path(paths[-1])
    try:
        brief_text = "\n\n".join(path.read_text(encoding="utf-8") for path in brief_paths)
        document = json.loads(openapi_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuilderInputError(str(exc)) from exc
    if not isinstance(document, dict):
        raise OpenAPIError("OpenAPI document must be a JSON object")
    return brief_paths, openapi_path, brief_text, document


def _ensure_published_version(workflow_id: str) -> int:
    """Publish the newest workflow version when needed, then verify it."""
    workspace_id = freya.workspace_id()
    result = freya.api(
        "GET",
        f"/api/v2/versions/workflow/{workflow_id}",
        workspaceId=workspace_id,
    )
    versions = result.get("versions", []) if isinstance(result, dict) else []
    if not versions:
        raise RuntimeError(f"workflow {workflow_id} has no versions to publish")
    newest = max(versions, key=lambda version: version.get("versionNumber", 0))
    if not newest.get("isPublished"):
        freya.api(
            "POST",
            f"/api/v2/versions/workflow/{workflow_id}/publish",
            {"versionId": newest["id"]},
        )
        result = freya.api(
            "GET",
            f"/api/v2/versions/workflow/{workflow_id}",
            workspaceId=workspace_id,
        )
        versions = result.get("versions", []) if isinstance(result, dict) else []
        verified = next((version for version in versions if version.get("id") == newest["id"]), None)
        if not verified or not verified.get("isPublished"):
            raise RuntimeError(f"workflow {workflow_id} newest version was not published")
        newest = verified
    return int(newest["versionNumber"])


def _trace_path(slot: str, print_only: bool, validate: bool) -> Path:
    if print_only:
        suffix = ".print.log"
    elif validate:
        suffix = ".validate.log"
    else:
        suffix = ".log"
    return Path("traces") / f"{slot}{suffix}"


def _error_text(exc: BaseException) -> str:
    text = str(exc).replace("\r", " ").replace("\n", " ")
    text = FREYA_KEY_PATTERN.sub("[REDACTED]", text)
    for name in ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY"):
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[:300]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    provisional_briefs = [Path(value) for value in args.inputs[:-1]]
    slot = args.slot or _default_slot(provisional_briefs)
    trace = TraceWriter(_trace_path(slot, args.print_only, args.validate))
    trace.add("slot", slot)
    status = "failed"
    try:
        brief_paths, openapi_path, brief_text, document = _load_inputs(args.inputs)
        for path in [*brief_paths, openapi_path]:
            trace.add_input(path)
        trace.add("model_calls", "none")
        trace.add("self_tests", "none")
        spec = None
        known_entry_variables = CALL_VARIABLES
        if args.spec_path:
            spec_path = Path(args.spec_path)
            spec = load_spec(spec_path)
            trace.add_input(spec_path)
            known_entry_variables = CALL_VARIABLES | spec_entry_variables(spec)
        openapi_warnings: list[str] = []
        tools = tools_from_openapi(
            document,
            warnings=openapi_warnings,
            known_entry_variables=known_entry_variables,
        )
        for warning in openapi_warnings:
            trace.add("warning", warning)
        if args.spec_path:
            assert spec is not None
            workflow = build_spec_workflow(spec, tools)
            trace.add("renderer", "multi-step spec_version=1")
        else:
            workflow = build_workflow(brief_text, tools)
            trace.add("renderer", "single-step fallback (no --spec supplied)")
        trace.add("nodes", len(workflow["nodes"]))
        trace.add("tools", len(tools))
        for step, step_tools in workflow_tools_by_step(workflow).items():
            trace.add("step", f"{step}: tools={','.join(step_tools) if step_tools else 'none'}")
        for step, estimate in workflow_prompt_estimates(workflow).items():
            trace.add("prompt_estimate", f"{step}: ~{estimate} tokens")
            if estimate > 1500:
                trace.add("warning", f"{step}: prompt estimate ~{estimate} tokens; OVER BUDGET")

        if args.print_only:
            print(json.dumps(workflow, indent=2, ensure_ascii=False))
            trace.add("freya", "not contacted (--print)")
            print(
                f"print: ok (slot={slot}, nodes={len(workflow['nodes'])}, tools={len(tools)})",
                file=sys.stderr,
            )
        elif args.validate:
            if not os.environ.get("FREYA_API_KEY"):
                raise RuntimeError("FREYA_API_KEY is not set; dry-run validation was not run")
            freya.validate_workflow(slot, workflow)
            trace.add("freya", "dry-run validation passed; workflow not saved")
            print(f"validate: ok (slot={slot}, nodes={len(workflow['nodes'])}, tools={len(tools)})")
        else:
            if not os.environ.get("FREYA_API_KEY"):
                raise RuntimeError("FREYA_API_KEY is not set; workflow was not validated or saved")
            freya.validate_workflow(slot, workflow)
            saved = freya.save_workflow(slot, workflow)
            workflow_id = saved["workflow_id"]
            output_path = Path("submission") / f"{slot}.workflow.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            published_version = _ensure_published_version(workflow_id)
            freya.export_workflow(workflow_id, str(output_path))
            trace.add("workflow_id", workflow_id)
            trace.add("agent_id", saved["agent_id"])
            trace.add("published_version", published_version)
            trace.add("export", output_path)
            print(
                f"save: ok (workflow_id={workflow_id}, agent_id={saved['agent_id']}, "
                f"published_version={published_version}, export={output_path}, trace={trace.path})"
            )
        status = "ok"
    except (BuilderInputError, OpenAPIError, SpecError) as exc:
        error = _error_text(exc)
        trace.add("error", f"{type(exc).__name__}: {error}")
        trace.path = Path("traces") / f"{slot}.failed.log"
        print(f"error: {error}", file=sys.stderr)
        return 2
    except BaseException as exc:
        error = _error_text(exc)
        trace.add("error", f"{type(exc).__name__}: {error}")
        trace.path = Path("traces") / f"{slot}.failed.log"
        print(f"error: {error}", file=sys.stderr)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        return 1
    finally:
        trace.finish(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
