# T-001 — Vertical slice: generic builder skeleton

**Owner:** codex-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

## Goal

`python3 builder/build.py <brief.md> [<more briefs>...] <tools.json>` produces a valid Freya workflow from any brief + OpenAPI file, saves it in place, exports it and writes a trace. Behaviour may equal the kit's minimal builder (one conversation node, brief as prompt). What matters now is the generic, reproducible pipeline that later tasks fill in.

## Scope

1. **Self-contained package** under `builder/`. Copy `build-the-builder-v2/freya.py` to `builder/freya.py` unchanged (keep `AGENT_LLM`). No imports from `build-the-builder-v2/`.
2. **CLI** (`builder/build.py`): the last argument is the OpenAPI file, all earlier arguments are brief files (concatenated in order; Brief B builds on A). Flags:
   - `--print`: print the workflow JSON, no network.
   - `--validate`: Freya dry run only (`validate_workflow`), no save.
   - `--slot NAME`: workflow slot name; default derived from brief file names.
   - default (no flag): dry run, then `save_workflow` (create once, update + publish later), then `export_workflow`.
3. **OpenAPI → tools, fully generic** (`builder/tools_from_openapi.py` or similar):
   - Base URL from `servers[0].url`; one tool per POST path; tool name = path without `/`.
   - Body fields from the request schema: type, `enum`, description, `required`.
   - A field whose name equals a known call variable (`customer_id`, `first_name`, `last_name`, `title`, `now`) is baked with `default: "{{name}}"`. Every other field gets `default: "{{field}}"` so the model fills it.
   - Tool description from the operation `summary` plus the field descriptions. No hardcoded tool names, field names, enum values or descriptions anywhere.
   - `config`: `timeoutMs` 10000-12000, `maxRetries` 0.
   - Nothing about `close_call` may be hardcoded except what the kit verifies as fixed: the seven tool names are fixed by the rules, so identifying the closing tool by the name `close_call` is allowed. The end-of-call transition reads `close_call_response.data.ok` (test `"true"` and `"True"`) and goes to an `end_call` node.
4. **Workflow rules** from `build-the-builder-v2/docs/workflow-format.md` and `tools-and-code.md`: no `null`, no `agent_config`, node `name` equals key, tools only on conversation nodes, `test_variables` present with neutral placeholder values (not copied from a practice case).
5. **Outputs**:
   - Export to `submission/<slot>.workflow.json`.
   - Trace to `traces/<slot>.log` (plain text): start/end time (UTC), inputs (file names + sha256), model calls (none yet, but the writer must support `model`, one-line purpose, duration), Freya workflow id, agent id, published version, number of nodes and tools, self-tests (none yet). Never write keys or env values.
6. **Tests** (stdlib `unittest`, `tests/`), runnable offline with `python3 -m unittest`:
   - Kit OpenAPI → 7 tools, correct enums/required, `customer_id` baked.
   - A synthetic OpenAPI with renamed fields, different enums and an extra field → tools follow the file (proves nothing is hardcoded).
   - Generated workflow contains no `null` and no `agent_config`; every node name equals its key; an `end_call` node is reachable.
   - Trace writer never contains the values of `FREYA_API_KEY` / `FREYA_BANK_TEAM_KEY` (set fake values in the test).

## Out of scope (later tasks)

LLM rule extraction, multiple nodes, code nodes for dates, hooks, self-test simulations.

## Constraints

- Python 3.10+ syntax, standard library only.
- Do not run `save_workflow`, simulations or `run_cases.py`. Allowed network: `--validate` (dry run) only. The CTO runs the real save and simulations.
- Do not read `build-the-builder-v2/env.sh`. Do not commit; the CTO commits after review.
- No value from `briefs/` or `public-test-set.json` in code or prompts. Brief text reaches the workflow only as runtime input.

## Done when

- `python3 -m unittest` passes.
- `python3 builder/build.py build-the-builder-v2/briefs/brief-a.md build-the-builder-v2/tools/openapi.json --print` prints a workflow.
- `--validate` passes the Freya dry run (if `env.sh` is sourced by the user/CTO; otherwise report it as not run).
- Short report: files created, how to run, what was not verified.
