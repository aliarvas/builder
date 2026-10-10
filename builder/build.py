#!/usr/bin/env python3
"""CLI entry point for the generic Freya workflow builder."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

if __package__:
    from . import freya, freya_chat
    from .extract import ExtractionError, ExtractionResult, extract_spec
    from .llm import AnthropicClient, LLMResult
    from .run_trace import ANTHROPIC_KEY_PATTERN, FREYA_KEY_PATTERN, SECRET_ENV_NAMES, TraceWriter
    from .selftest import run_self_tests
    from .slots import save_with_slot_check
    from .spec import SpecError, load_spec, spec_entry_variables
    from .tools_from_openapi import CALL_VARIABLES, OpenAPIError, tools_from_openapi
    from .workflow import build_spec_workflow, build_workflow, workflow_prompt_estimates, workflow_tools_by_step
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from builder import freya, freya_chat
    from builder.extract import ExtractionError, ExtractionResult, extract_spec
    from builder.llm import AnthropicClient, LLMResult
    from builder.run_trace import ANTHROPIC_KEY_PATTERN, FREYA_KEY_PATTERN, SECRET_ENV_NAMES, TraceWriter
    from builder.selftest import run_self_tests
    from builder.slots import save_with_slot_check
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
    mode.add_argument("--print", dest="print_only", action="store_true", help="print JSON without Freya calls (spec extraction still calls the model unless --spec)")
    mode.add_argument("--validate", action="store_true", help="run only Freya's dry-run validation")
    parser.add_argument("--slot", help="stable workflow slot name")
    parser.add_argument(
        "--no-self-test", action="store_true",
        help="save and publish without post-publish chat checks (development only)",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--spec", dest="spec_path",
        help="use this written spec JSON instead of extracting one from the brief (tests, comparisons)",
    )
    source.add_argument(
        "--single-step", action="store_true",
        help="legacy single-step agent with the whole brief in one prompt (no spec, no model calls)",
    )
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
    text = ANTHROPIC_KEY_PATTERN.sub("[REDACTED]", text)
    for name in SECRET_ENV_NAMES:
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text[:300]


def _extract(
    brief_paths: list[Path], document: dict[str, Any], slot: str, trace: TraceWriter
) -> ExtractionResult:
    """Extract the spec from the brief with the builder model and write traces/<slot>.spec.json."""
    calls: list[LLMResult] = []

    def log_call(purpose: str, result: LLMResult) -> None:
        calls.append(result)
        trace.add_model_call(
            result.model, purpose, result.duration_seconds,
            result.input_tokens, result.output_tokens, result.cache_read_tokens,
        )

    documents = [(path.name, path.read_text(encoding="utf-8")) for path in brief_paths]
    spec_path = Path("traces") / f"{slot}.spec.json"
    started = time.monotonic()
    try:
        client = AnthropicClient(log=log_call, note=lambda message: trace.add("warning", message))
        trace.add("model_settings", client.settings())
        result = extract_spec(documents, document, client, log=trace.add)
    except ExtractionError as exc:
        if exc.candidate is not None:
            failed_path = Path("traces") / f"{slot}.spec.failed.json"
            failed_path.parent.mkdir(parents=True, exist_ok=True)
            failed_path.write_text(json.dumps(exc.candidate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            trace.add("spec_failed", failed_path)
        raise
    finally:
        trace.add("model_calls", (
            f"{len(calls)} input_tokens={sum(call.input_tokens for call in calls)} "
            f"output_tokens={sum(call.output_tokens for call in calls)} "
            f"model_seconds={sum(call.duration_seconds for call in calls):.1f} "
            f"extract_seconds={time.monotonic() - started:.1f}"
        ))
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(result.spec_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    trace.add("spec", f"{spec_path} extracted; unmapped_items={len(result.unmapped)} warnings={len(result.warnings)}")
    return result


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
        if args.print_only or args.validate:
            trace.add("self_tests", "not run in --print/--validate mode")
        elif args.no_self_test:
            trace.add("self_tests", "disabled by --no-self-test")
        else:
            trace.add("self_tests", "enabled after publish")
        spec = None
        unmapped: list[str] = []
        known_entry_variables = CALL_VARIABLES
        if args.spec_path:
            trace.add("model_calls", "none")
            spec_path = Path(args.spec_path)
            spec = load_spec(spec_path)
            trace.add_input(spec_path)
        elif args.single_step:
            trace.add("model_calls", "none")
        else:
            extraction = _extract(brief_paths, document, slot, trace)
            spec, unmapped = extraction.spec, extraction.unmapped
        if spec is not None:
            known_entry_variables = CALL_VARIABLES | spec_entry_variables(spec)
        openapi_warnings: list[str] = []
        tools = tools_from_openapi(
            document,
            warnings=openapi_warnings,
            known_entry_variables=known_entry_variables,
        )
        for warning in openapi_warnings:
            trace.add("warning", warning)
        if spec is not None:
            spec_warnings: list[str] = []
            workflow = build_spec_workflow(spec, tools, spec_warnings)
            for warning in spec_warnings:
                trace.add("warning", warning)
            trace.add("renderer", "multi-step spec_version=1")
        else:
            workflow = build_workflow(brief_text, tools)
            trace.add("renderer", "single-step fallback (--single-step)")
        trace.add("nodes", len(workflow["nodes"]))
        trace.add("global_nodes", len(workflow.get("global_nodes", {})))
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
            saved = save_with_slot_check(
                freya, slot, workflow, warn=lambda message: trace.add("warning", message)
            )
            workflow_id = saved["workflow_id"]
            output_path = Path("submission") / f"{slot}.workflow.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            published_version = _ensure_published_version(workflow_id)
            freya.export_workflow(workflow_id, str(output_path))
            trace.add("workflow_id", workflow_id)
            trace.add("agent_id", saved["agent_id"])
            trace.add("published_version", published_version)
            trace.add("export", output_path)
            if spec is None:
                trace.add("self_test_summary", "skipped=no_spec")
            elif args.no_self_test:
                trace.add("self_test_summary", "skipped=--no-self-test")
            else:
                try:
                    self_test_results = run_self_tests(freya_chat, workflow_id, spec, document)
                    for item in self_test_results:
                        trace.add(
                            "self_test",
                            f"case={item.case_id} result={item.result} reason={item.reason} "
                            f"call_id={item.call_id} seconds={item.seconds:.1f}",
                        )
                    counts = {
                        name: sum(item.result == name for item in self_test_results)
                        for name in ("pass", "fail", "platform_error")
                    }
                    trace.add(
                        "self_test_summary",
                        f"total={len(self_test_results)} pass={counts['pass']} "
                        f"fail={counts['fail']} platform_error={counts['platform_error']}",
                    )
                    print(
                        f"self-test: total={len(self_test_results)} pass={counts['pass']} "
                        f"fail={counts['fail']} platform_error={counts['platform_error']}"
                    )
                except Exception as exc:
                    # The exported workflow remains the build artifact even when its checks fail.
                    trace.add("self_test_summary", "platform_error=" + _error_text(exc))
                    print("self-test: platform_error=" + _error_text(exc))
            print(
                f"save: ok (workflow_id={workflow_id}, agent_id={saved['agent_id']}, "
                f"published_version={published_version}, export={output_path}, trace={trace.path})"
            )
        if unmapped:
            # Last line of the run's summary output (stderr with --print, whose stdout is the JSON).
            print(
                f"warning: {len(unmapped)} brief item(s) not mapped to the spec; "
                f"see coverage_unmapped in {trace.path}",
                file=sys.stderr if args.print_only else sys.stdout,
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
