"""T-046: generic mode. The case documents decide the workflow, not a collections spec.

Four steps, each one model call (``llm.py``), the documents and the kit's platform docs in a
cached prefix:

1. **Contract.** The bank's own services from the documents, as OpenAPI 3 JSON with the mock
   URL as server. Every path segment and field name must be written in the documents.
2. **Design.** Steps, spoken rules, variables, transitions and tools, as JSON.
3. **Render.** The Freya workflow JSON from the design, in the kit's format.
4. **Validate and repair.** A local check of the workflow (shape, references, variables,
   tools against the contract, guarded code loops); up to ``REPAIR_ROUNDS`` repairs, each
   sending the exact problems and taking back only the changed parts.

Nothing here knows the case: no domain, language, service, field or value. The platform
rules in the prompts come from the kit docs and from our live runs.
"""

from __future__ import annotations

import concurrent.futures
import json
import re
from pathlib import Path
from typing import Any, Callable

from .case_folder import Case, CaseDocument, with_server
from .code_cycles import code_cycle_gaps
from .llm import AnthropicClient, LLMError, text_block
from .prompts import (
    GENERIC_CONTRACT_TASK, GENERIC_DESIGN_TASK, GENERIC_PLATFORM_RULES, GENERIC_RENDER_TASK, GENERIC_REPAIR_TASK,
    GENERIC_SYSTEM,
)

ROOT = Path(__file__).resolve().parents[1]
KIT_DOCS = ("build-the-builder-v2/docs/workflow-format.md", "build-the-builder-v2/docs/tools-and-code.md")
REPAIR_ROUNDS = 3
# T-052: the design must stay short; the render may be long (and is continued when cut).
DESIGN_MAX_TOKENS = 8000
RENDER_MAX_TOKENS = 64000
DESIGN_TOO_LONG = ("Your design was cut at the output limit ({limit} tokens). Write the whole design again, much "
                   "shorter (at most about 5000 tokens): merge similar steps, short phrases, no copied text.")
CONTRACT_REPAIR_ROUNDS = 1
NODE_TYPES = ("conversation", "api_request", "code", "end_call")
OPERATORS = ("equals", "not_equals", "greater_than", "less_than", "contains", "is_set", "is_not_set", "always",
             "matches_intent")
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
# Variables the engine writes itself (kit docs, "System variables" and the call counters).
SYSTEM_VARIABLE_PATTERNS = (r".+_success_count", r".+_failure_count", r".+_response(\..+)?", r".+_status_code",
                            r".+_args(\..+)?", r"call\..+", r"now", r"current_.+", r"user_.+", r"agent_.+")

Complete = Callable[[str, list[dict[str, Any]], str], str]   # (system, messages, purpose) -> text
Trace = Any

_LAST: dict[str, Any] = {}


class GenericBuildError(RuntimeError):
    """The generic build could not produce a workflow."""


# ---------------------------------------------------------------------------
# Entry points (T-047 uses build and repair)
# ---------------------------------------------------------------------------

def build(case: Case, mock_url: str, trace: Trace, client: Any = None, design: bool = True
          ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Contract, design (optional), render, validate and repair. Returns (workflow, contract)."""
    complete = _completer(client, trace)
    context = _context_blocks(case)
    contract = derive_contract(case, mock_url, complete, context, trace)
    mock_url = base_url(mock_url, contract)
    contract = with_server(contract, mock_url)
    trace.add("tool_base_url", mock_url)
    _write_trace_json(trace, "contract", contract)
    if design:
        design = make_design(contract, complete, context, trace)
        _write_trace_json(trace, "design", design)
    else:
        design = {"note": "no separate design step: design the workflow from the documents directly"}
        trace.add("design", "skipped (render from the documents)")
    workflow, messages = render(design, contract, complete, context, trace)
    workflow = _repair_loop(workflow, contract, mock_url, messages, complete, trace, [])
    _LAST.update(case=case, contract=contract, mock_url=mock_url, design=design, complete=complete,
                 context=context)
    return workflow, contract


def repair(case: Case, workflow: dict[str, Any], problems: list[str], trace: Trace, client: Any = None,
           contract: dict[str, Any] | None = None) -> dict[str, Any]:
    """Repair ``workflow`` for ``problems`` (Freya validation errors, failed self-tests), then
    re-run the local validation and its repair rounds."""
    contract = contract or _LAST.get("contract") or {}
    mock_url = _LAST.get("mock_url") or _server(contract)
    complete = _completer(client, trace) if client is not None or "complete" not in _LAST else _LAST["complete"]
    context = _LAST.get("context") if _LAST.get("case") is case else _context_blocks(case)
    messages = [{"role": "user", "content": [*context, text_block(_render_request(_LAST.get("design") or {}, contract))]},
                {"role": "assistant", "content": json.dumps(workflow, ensure_ascii=False)}]
    return _repair_loop(workflow, contract, mock_url, messages, complete, trace, list(problems))


# ---------------------------------------------------------------------------
# Model calls
# ---------------------------------------------------------------------------

def _completer(client: Any, trace: Trace) -> Complete:
    if client is None:
        client = AnthropicClient(
            log=lambda purpose, result: trace.add_model_call(
                result.model, purpose, result.duration_seconds, result.input_tokens, result.output_tokens,
                result.cache_read_tokens),
            note=lambda message: trace.add("warning", message))
    if callable(client) and not hasattr(client, "complete"):
        return lambda system, messages, purpose, **limits: client(system, messages, purpose)
    if not isinstance(client, AnthropicClient):  # a test client: no per-call limits
        return lambda system, messages, purpose, **limits: client.complete(system, messages, purpose).text
    return lambda system, messages, purpose, **limits: client.complete(system, messages, purpose, **limits).text


def _context_blocks(case: Case) -> list[dict[str, Any]]:
    """PDF files, then every document and the kit's platform docs, as one cached prefix."""
    documents = "\n\n".join(f"## Document {index}: {name}\n\n{text.strip()}"
                            for index, (name, text) in enumerate(case.text_documents(), start=1))
    kit = "\n\n".join(f"## Platform document: {Path(path).name}\n\n{(ROOT / path).read_text(encoding='utf-8')}"
                      for path in KIT_DOCS if (ROOT / path).exists())
    return [*case.attachments(),
            text_block("# THE CASE DOCUMENTS\n\n" + documents + "\n\n# THE PLATFORM (Freya workflow format)\n\n" + kit
                       + "\n\n# PLATFORM RULES LEARNED IN LIVE RUNS\n\n" + GENERIC_PLATFORM_RULES.text, cache=True)]


def _ask(complete: Complete, messages: list[dict[str, Any]], purpose: str, **limits: int
         ) -> tuple[dict[str, Any] | None, str]:
    reply = complete(GENERIC_SYSTEM.text, messages, purpose, **limits)
    messages.append({"role": "assistant", "content": reply or "(empty reply)"})
    try:
        value = json.loads(json_object(reply))
    except (ValueError, json.JSONDecodeError) as exc:
        return None, f"the reply was not one JSON object ({exc})"
    return (value, "") if isinstance(value, dict) else (None, "the reply was not a JSON object")


def json_object(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*|\s*```\s*$", "", (text or "").strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the reply")
    return text[start:end + 1]


# ---------------------------------------------------------------------------
# 1. Contract
# ---------------------------------------------------------------------------

def derive_contract(case: Case, mock_url: str, complete: Complete, context: list[dict[str, Any]],
                    trace: Trace) -> dict[str, Any]:
    if case.openapi:
        trace.add("contract", f"{case.openapi_source} (OpenAPI in the folder)")
        return with_server(case.openapi, mock_url)
    messages = [{"role": "user", "content": [*context, text_block(GENERIC_CONTRACT_TASK.text)]}]
    contract, problem = _ask(complete, messages, "generic:contract")
    plain = documents_text(case)
    for _ in range(CONTRACT_REPAIR_ROUNDS + 1):
        problems = [problem] if contract is None else contract_problems(contract, plain)
        if not problems:
            break
        for item in problems:
            trace.add("contract_problem", item)
        if _ is CONTRACT_REPAIR_ROUNDS:
            break
        messages.append({"role": "user", "content": GENERIC_REPAIR_TASK.text.replace(
            "{problems}", "\n".join("- " + item for item in problems)).replace("{what}", "the whole contract JSON")})
        contract, problem = _ask(complete, messages, "generic:contract_repair")
    if not contract or not isinstance(contract.get("paths"), dict):
        raise GenericBuildError("no service contract could be derived from the documents")
    trace.add("contract", f"derived: {len(contract['paths'])} path(s): {', '.join(contract['paths'])}")
    return with_server(contract, mock_url)


def base_url(mock_url: str, contract: dict[str, Any]) -> str:
    """The URL the tools put in front of a contract path. A mock URL given with the services'
    common path prefix ("https://host/v1/" while the paths are "/v1/...") loses that prefix,
    so the prefix is not sent twice."""
    from urllib.parse import urlsplit

    url = mock_url.rstrip("/")
    prefix = urlsplit(url).path.rstrip("/")
    paths = [str(path) for path in (contract.get("paths") or {})]
    if prefix and paths and all(path == prefix or path.startswith(prefix + "/") for path in paths):
        return url[: len(url) - len(prefix)]
    return url


def documents_text(case: Case) -> str:
    return "\n".join(item.text for item in case.documents).lower()


def contract_problems(contract: dict[str, Any], plain: str) -> list[str]:
    """Every literal path segment and every field name is written in the documents."""
    problems = []
    paths = contract.get("paths")
    if not isinstance(paths, dict) or not paths:
        return ["the contract has no paths"]
    for path, item in paths.items():
        for segment in [part for part in str(path).split("/") if part and not part.startswith("{")]:
            if segment.lower() not in plain:
                problems.append(f"path {path}: segment {segment!r} is not written in the documents")
        if not isinstance(item, dict) or not any(method.upper() in HTTP_METHODS for method in item):
            problems.append(f"path {path}: no HTTP method")
            continue
        for method, operation in item.items():
            for name in _operation_fields(operation):
                if name.lower() not in plain:
                    problems.append(f"{method.upper()} {path}: field {name!r} is not written in the documents")
    return problems


def _operation_fields(operation: Any) -> list[str]:
    if not isinstance(operation, dict):
        return []
    names = [str(item.get("name")) for item in operation.get("parameters") or [] if isinstance(item, dict) and item.get("name")]
    body = (((operation.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
    names += _schema_fields(body)
    for response in (operation.get("responses") or {}).values():
        schema = (((response or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
        names += _schema_fields(schema)
    return list(dict.fromkeys(names))


def _schema_fields(schema: Any, depth: int = 0) -> list[str]:
    if not isinstance(schema, dict) or depth > 6:
        return []
    names = []
    for name, sub in (schema.get("properties") or {}).items():
        names.append(str(name))
        names += _schema_fields(sub, depth + 1)
    names += _schema_fields(schema.get("items"), depth + 1)
    return names


def _server(contract: dict[str, Any]) -> str:
    servers = contract.get("servers") or [{}]
    return str((servers[0] or {}).get("url") or "")


def contract_operations(contract: dict[str, Any]) -> list[tuple[str, str, re.Pattern[str]]]:
    """(method, path, a pattern matching the path with any value in place of a {parameter})."""
    result = []
    for path, item in (contract.get("paths") or {}).items():
        pattern = re.compile("^" + re.sub(r"\\\{[^}]*\\\}", r"[^/]+", re.escape(str(path).rstrip("/"))) + "/?$")
        for method in (item or {}):
            if method.upper() in HTTP_METHODS:
                result.append((method.upper(), str(path), pattern))
    return result


# ---------------------------------------------------------------------------
# 2. Design and 3. render
# ---------------------------------------------------------------------------

def make_design(contract: dict[str, Any], complete: Complete, context: list[dict[str, Any]],
                trace: Trace) -> dict[str, Any]:
    messages = [{"role": "user", "content": [*context, text_block(GENERIC_DESIGN_TASK.text.replace(
        "{contract}", json.dumps(contract, indent=1, ensure_ascii=False)))]}]
    limits = dict(max_tokens=DESIGN_MAX_TOKENS, continuations=0)
    try:
        design, problem = _ask(complete, messages, "generic:design", **limits)
    except LLMError as exc:
        if "output limit" not in str(exc):
            raise
        messages.append({"role": "assistant", "content": "(cut at the output limit)"})
        messages.append({"role": "user", "content": DESIGN_TOO_LONG.replace("{limit}", str(DESIGN_MAX_TOKENS))})
        try:
            design, problem = _ask(complete, messages, "generic:design_shorter", **limits)
        except LLMError as again:
            if "output limit" not in str(again):
                raise
            trace.add("warning", "design still too long after one shorter request: render from the documents")
            return {"note": "no separate design step: design the workflow from the documents directly"}
    if design is None:
        messages.append({"role": "user", "content": GENERIC_REPAIR_TASK.text.replace("{problems}", "- " + problem)
                         .replace("{what}", "the whole design JSON")})
        design, problem = _ask(complete, messages, "generic:design_repair", **limits)
    if design is None:
        raise GenericBuildError("no design: " + problem)
    trace.add("design", f"{len(design.get('steps') or [])} step(s)")
    return design


def _render_request(design: dict[str, Any], contract: dict[str, Any]) -> str:
    return (GENERIC_RENDER_TASK.text
            .replace("{design}", json.dumps(design, indent=1, ensure_ascii=False))
            .replace("{contract}", json.dumps(contract, indent=1, ensure_ascii=False))
            .replace("{mock_url}", _server(contract)))


def render(design: dict[str, Any], contract: dict[str, Any], complete: Complete, context: list[dict[str, Any]],
           trace: Trace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    messages = [{"role": "user", "content": [*context, text_block(_render_request(design, contract))]}]
    workflow, problem = _ask(complete, messages, "generic:render", max_tokens=RENDER_MAX_TOKENS)
    if workflow is None:
        messages.append({"role": "user", "content": GENERIC_REPAIR_TASK.text.replace("{problems}", "- " + problem)
                         .replace("{what}", "the whole workflow JSON")})
        workflow, problem = _ask(complete, messages, "generic:render_retry", max_tokens=RENDER_MAX_TOKENS)
    if workflow is None:
        raise GenericBuildError("no workflow: " + problem)
    workflow = workflow.get("workflow", workflow) if isinstance(workflow.get("workflow"), dict) else workflow
    return workflow, messages


# ---------------------------------------------------------------------------
# 4. Validate and repair
# ---------------------------------------------------------------------------

def _repair_loop(workflow: dict[str, Any], contract: dict[str, Any], mock_url: str, messages: list[dict[str, Any]],
                 complete: Complete, trace: Trace, extra: list[str]) -> dict[str, Any]:
    best, best_count = workflow, None
    for round_number in range(REPAIR_ROUNDS + 1):
        workflow = clean(workflow)
        problems = [*extra, *validate(workflow, contract, mock_url)]
        extra = []
        trace.add("validation", f"round {round_number}: {len(problems)} problem(s)")
        for item in problems[:40]:
            trace.add("validation_problem", item)
        if best_count is None or len(problems) < best_count:
            best, best_count = workflow, len(problems)
        if not problems or round_number == REPAIR_ROUNDS:
            break
        messages.append({"role": "user", "content": GENERIC_REPAIR_TASK.text.replace(
            "{problems}", "\n".join("- " + item for item in problems[:60])).replace(
            "{what}", 'only the changed parts as {"nodes": {key: node or null}, "global_nodes": {key: node or null}, '
                      '"top": {other top-level keys}}')})
        patch, problem = _ask(complete, messages, f"generic:repair_{round_number + 1}")
        if patch is None:
            extra = [problem]
            continue
        workflow = apply_patch(workflow, patch)
    if best_count:
        trace.add("warning", f"generic workflow shipped with {best_count} validation problem(s)")
    return best


def apply_patch(workflow: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Merge a repair: whole workflows replace; else changed nodes (null removes) and top keys."""
    if isinstance(patch.get("workflow"), dict):
        return patch["workflow"]
    if "initial_node" in patch and isinstance(patch.get("nodes"), dict) and "top" not in patch and len(patch["nodes"]) >= len(
            workflow.get("nodes") or {}):
        return patch
    result = json.loads(json.dumps(workflow))
    for section in ("nodes", "global_nodes"):
        for key, node in (patch.get(section) or {}).items():
            target = result.setdefault(section, {})
            if node is None:
                target.pop(key, None)
            else:
                target[key] = node
    for key, value in (patch.get("top") or {}).items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
    return result


def clean(workflow: dict[str, Any]) -> dict[str, Any]:
    """Platform rules the code can apply itself: no agent_config, no null, name = key."""
    def strip(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: strip(item) for key, item in value.items() if item is not None}
        if isinstance(value, list):
            return [strip(item) for item in value if item is not None]
        return value

    result = strip(workflow)
    _tool_timeouts(result)
    result.pop("agent_config", None)
    result.pop("nodePositions", None)
    for section in ("nodes", "global_nodes"):
        for key, node in (result.get(section) or {}).items():
            if isinstance(node, dict):
                node["name"] = key
    return result


# A slow bank service (one test answer waits 12 s) must not fail on the tool's own timeout.
TOOL_TIMEOUT_MS = 30000


def _tool_timeouts(workflow: dict[str, Any]) -> None:
    """Every api tool waits at least TOOL_TIMEOUT_MS per attempt."""
    tools = list(workflow.get("tools") or [])
    for section in ("nodes", "global_nodes"):
        for node in (workflow.get(section) or {}).values():
            if isinstance(node, dict):
                tools += [*(node.get("tools") or []), *(node.get("pre_actions") or [])]
    for tool in tools:
        if isinstance(tool, dict) and (tool.get("function") or {}).get("handler") == "__function__:api_call":
            config = tool.setdefault("config", {})
            try:
                current = int(config.get("timeoutMs") or 0)
            except (TypeError, ValueError):
                current = 0
            config["timeoutMs"] = max(current, TOOL_TIMEOUT_MS)


def validate(workflow: dict[str, Any], contract: dict[str, Any], mock_url: str) -> list[str]:
    """Problems that would fail on the platform or break a call. Empty when none."""
    problems: list[str] = []
    nodes = workflow.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        return ["`nodes` must be a non-empty object"]
    globals_ = workflow.get("global_nodes") or {}
    if not isinstance(globals_, dict):
        problems.append("`global_nodes` must be an object")
        globals_ = {}
    every = {**nodes, **globals_}
    if workflow.get("initial_node") not in nodes:
        problems.append(f"`initial_node` {workflow.get('initial_node')!r} is not a node")
    if "agent_config" in workflow:
        problems.append("omit `agent_config`")
    ends = [key for key, node in nodes.items() if isinstance(node, dict) and node.get("node_type") == "end_call"]
    if not ends:
        problems.append("no `end_call` node")
    defined = _defined_variables(workflow)
    operations = contract_operations(contract)
    for key, node in every.items():
        where = ("global node " if key in globals_ else "node ") + key
        if not isinstance(node, dict):
            problems.append(f"{where}: not an object")
            continue
        kind = node.get("node_type")
        if kind not in NODE_TYPES:
            problems.append(f"{where}: node_type {kind!r} is not one of {', '.join(NODE_TYPES)}")
        if key in globals_:
            if "condition" not in node or "description" not in node:
                problems.append(f"{where}: a global node needs `condition` and `description`")
            else:
                problems += _condition_problems(node["condition"], where + " condition", defined)
            for excluded in node.get("excluded_nodes") or []:
                if excluded not in every:
                    problems.append(f"{where}: excluded node {excluded!r} does not exist")
        else:
            for field in ("condition", "description", "excluded_nodes"):
                if field in node:
                    problems.append(f"{where}: `{field}` belongs only on global nodes; remove it")
        if kind == "conversation" and node.get("pre_actions"):
            problems.append(f"{where}: `pre_actions` is stripped on conversation nodes; move the call into an "
                            "api_request node in front")
        if kind in ("api_request", "code") and node.get("tools"):
            problems.append(f"{where}: `tools` is kept only on conversation nodes")
        if kind == "api_request" and not node.get("pre_actions"):
            problems.append(f"{where}: an api_request node needs `pre_actions`")
        if kind == "end_call":
            handler = (((node.get("terminal") or {}).get("function") or {}).get("handler"))
            if handler != "__function__:end_call":
                problems.append(f"{where}: `terminal` must be the end_call function (handler __function__:end_call)")
        transitions = node.get("transitions")
        if kind != "end_call" and not transitions and not node.get("passthrough_default_transition"):
            problems.append(f"{where}: no transitions; every path must reach an end_call node")
        for index, transition in enumerate(transitions or []):
            target = transition.get("target_node") if isinstance(transition, dict) else None
            if target != "__previous__" and target not in every:
                problems.append(f"{where}: transition {index} goes to {target!r}, which is not a node")
            if isinstance(transition, dict):
                if "condition" not in transition:
                    problems.append(f"{where}: transition {index} has no condition")
                else:
                    problems += _condition_problems(transition["condition"], f"{where} transition {index}", defined)
        default = node.get("passthrough_default_transition")
        if default and default != "__previous__" and default not in every:
            problems.append(f"{where}: passthrough_default_transition {default!r} is not a node")
        if node.get("passthrough") and not any(
                isinstance(item, dict) and (item.get("condition") or {}).get("operator") == "always"
                for item in transitions or []):
            problems.append(f"{where}: a passthrough node must end with an `always` transition")
        for field in node.get("extraction_schema") or []:
            values = field.get("enum_values") if isinstance(field, dict) else None
            if values and values[-1] != "none":
                problems.append(f"{where}: extraction field {field.get('name')!r}: put \"none\" last in enum_values")
        for tool in [*(node.get("tools") or []), *(node.get("pre_actions") or [])]:
            problems += _tool_problems(tool, where, operations, mock_url)
    for tool in workflow.get("tools") or []:
        problems += _tool_problems(tool, "workflow tools", operations, mock_url)
    problems += _reach_problems(workflow, nodes, globals_, ends)
    problems += [f"loop {group}: {problem}; add an exit on `<node>_success_count`/`<node>_failure_count`"
                 for group, problem in code_cycle_gaps(workflow)]
    problems += _variable_problems(workflow, defined)
    return list(dict.fromkeys(problems))


def _condition_problems(condition: Any, where: str, defined: set[str]) -> list[str]:
    if not isinstance(condition, dict):
        return [f"{where}: condition is not an object"]
    if "conditions" in condition:
        if condition.get("logic") not in ("or", "and"):
            return [f"{where}: a condition group needs \"logic\": \"or\" (top level) or \"and\" (nested)"]
        result = []
        for item in condition["conditions"]:
            result += _condition_problems(item, where, defined)
        return result
    operator = condition.get("operator")
    if operator not in OPERATORS:
        return [f"{where}: operator {operator!r} is not one of {', '.join(OPERATORS)}"]
    if operator == "matches_intent" and not condition.get("description"):
        return [f"{where}: matches_intent needs a `description`"]
    if operator not in ("always", "matches_intent") and not condition.get("variable"):
        return [f"{where}: operator {operator} needs a `variable`"]
    return []


def _tool_problems(tool: Any, where: str, operations: list[tuple[str, str, re.Pattern[str]]], mock_url: str) -> list[str]:
    if not isinstance(tool, dict):
        return [f"{where}: a tool is not an object"]
    function = tool.get("function") or {}
    name = function.get("name") or "?"
    handler = function.get("handler")
    if handler not in ("__function__:api_call", "__function__:code_exec", "__function__:end_call"):
        return [f"{where}: tool {name}: handler {handler!r} is not api_call, code_exec or end_call"]
    if handler != "__function__:api_call":
        return []
    properties = (function.get("parameters") or {}).get("properties") or {}
    url = str((properties.get("url") or {}).get("default") or "")
    method = str((properties.get("method") or {}).get("default") or "GET").upper()
    base = mock_url.rstrip("/")
    if not url.startswith(base):
        return [f"{where}: tool {name}: url {url!r} must start with the mock URL {base}"]
    path = re.sub(r"\?.*$", "", url[len(base):]) or "/"
    path = re.sub(r"\{\{[^}]*\}\}", "x", path)
    if operations and not any(method == op_method and pattern.match(path) for op_method, _, pattern in operations):
        listed = ", ".join(f"{op_method} {op_path}" for op_method, op_path, _ in operations)
        return [f"{where}: tool {name}: {method} {url[len(base):]} is not a service of the contract ({listed})"]
    return []


def _defined_variables(workflow: dict[str, Any]) -> set[str]:
    names = set((workflow.get("test_variables") or {}).keys()) | set((workflow.get("context_variables") or {}).keys())
    text = json.dumps(workflow, ensure_ascii=False)
    for section in ("nodes", "global_nodes"):
        for key, node in (workflow.get(section) or {}).items():
            if not isinstance(node, dict):
                continue
            names.add(key)
            for field in node.get("extraction_schema") or []:
                if isinstance(field, dict) and field.get("name"):
                    names.add(field["name"])
            for mapping in node.get("response_mapping") or []:
                if isinstance(mapping, dict) and mapping.get("variable"):
                    names.add(mapping["variable"])
            for tool in [*(node.get("tools") or []), *(node.get("pre_actions") or [])]:
                if isinstance(tool, dict):
                    names.add((tool.get("function") or {}).get("name") or "")
                    for mapping in tool.get("response_mapping") or []:
                        if isinstance(mapping, dict) and mapping.get("variable"):
                            names.add(mapping["variable"])
    names |= set(re.findall(r"vars\[\\?['\"]([A-Za-z0-9_.]+)\\?['\"]\]\s*=", text))
    names |= set(re.findall(r"vars\.update\(\{?\\?['\"]([A-Za-z0-9_.]+)", text))
    return {name for name in names if name}


def _is_defined(name: str, defined: set[str]) -> bool:
    if name in defined or name.split(".")[0] in defined:
        return True
    if any(re.fullmatch(pattern, name) for pattern in SYSTEM_VARIABLE_PATTERNS):
        return True
    prefix = re.sub(r"_(success_count|failure_count|response.*|status_code|args.*)$", "", name)
    return prefix in defined


def _variable_problems(workflow: dict[str, Any], defined: set[str]) -> list[str]:
    used = set()
    for section in ("nodes", "global_nodes"):
        for key, node in (workflow.get(section) or {}).items():
            if not isinstance(node, dict):
                continue
            conditions = [node.get("condition")] + [item.get("condition") for item in node.get("transitions") or []
                                                    if isinstance(item, dict)]
            for condition in conditions:
                for leaf in _leaves(condition):
                    if leaf.get("variable"):
                        used.add((key, str(leaf["variable"])))
            for name in re.findall(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}", json.dumps(node, ensure_ascii=False)):
                used.add((key, name))
    return [f"node {key}: variable {name!r} is used but never set (not a call variable in test_variables, an "
            "extraction field, a response mapping or a code write)"
            for key, name in sorted(used) if not _is_defined(name, defined)]


def _leaves(condition: Any) -> list[dict[str, Any]]:
    if not isinstance(condition, dict):
        return []
    if "conditions" in condition:
        return [leaf for item in condition["conditions"] for leaf in _leaves(item)]
    return [condition]


def _reach_problems(workflow: dict[str, Any], nodes: dict[str, Any], globals_: dict[str, Any], ends: list[str]) -> list[str]:
    every = {**nodes, **globals_}

    def targets(node: Any) -> list[str]:
        if not isinstance(node, dict):
            return []
        found = [item.get("target_node") for item in node.get("transitions") or [] if isinstance(item, dict)]
        found += [node.get("passthrough_default_transition"), node.get("max_turn_transition")]
        return [item for item in found if item in every]

    reached, pending = set(), [workflow.get("initial_node")]
    while pending:
        key = pending.pop()
        if key in reached or key not in every:
            continue
        reached.add(key)
        pending += targets(every[key])
    reached |= set(globals_)
    for key in list(globals_):
        pending = targets(globals_[key])
        while pending:
            item = pending.pop()
            if item not in reached:
                reached.add(item)
                pending += targets(every[item])
    problems = [f"node {key}: not reachable from initial_node or a global node" for key in nodes if key not in reached]
    # Every node must be able to reach an end_call node.
    reverse: dict[str, set[str]] = {}
    for key, node in every.items():
        for target in targets(node):
            reverse.setdefault(target, set()).add(key)
    can_end, pending = set(ends), list(ends)
    while pending:
        for source in reverse.get(pending.pop(), ()):
            if source not in can_end:
                can_end.add(source)
                pending.append(source)
    problems += [f"node {key}: no path from it to an end_call node" for key in every
                 if key not in can_end and not _returns_previous(every[key])]
    return problems


def _returns_previous(node: Any) -> bool:
    return isinstance(node, dict) and ("__previous__" in json.dumps(node.get("transitions") or [])
                                       or node.get("passthrough_default_transition") == "__previous__")


def _write_trace_json(trace: Trace, name: str, value: dict[str, Any]) -> None:
    path = getattr(trace, "path", None)
    if not path:
        return
    target = Path(path).with_name(Path(path).stem + f".{name}.json")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        trace.add(f"{name}_file", target)
    except OSError as exc:
        trace.add("warning", f"{name} not written: {exc}")


__all__ = ["build", "repair", "validate", "apply_patch", "clean", "derive_contract", "make_design", "render",
           "contract_problems", "GenericBuildError", "CaseDocument", "concurrent"]
