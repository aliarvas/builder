# Technical Architecture

**Owner:** Components, dependencies and repository boundaries  
**Read when:** Adding modules, changing data flow or deciding where code belongs

## Rule

Brief analysis, policy handling and the IR are independent of Freya. All Freya payloads and API calls live in one adapter module. Nothing about a specific brief appears in builder code; everything brief-specific is data extracted at run time.

## Pipeline

```text
read brief(s) + OpenAPI
  -> extract rules and parameters (LLM, structured output, source excerpts)
  -> resolve overrides and conflicts
  -> bind tools from OpenAPI
  -> build IR (flow + parameter tables)
  -> validate IR
  -> render Freya workflow (nodes, prompts, tools, code nodes, hooks)
  -> dry-run validate, save (create or update + publish)
  -> self-test (bounded)
  -> export workflow + write trace
```

Each stage returns typed data or an explicit error. A later stage never guesses what an earlier one failed to produce.

## Core design idea `[HYPOTHESIS]`

Prompts alone are unreliable (the phone-agent model is fixed and sometimes inconsistent, and every case needs 3 of 3 passes). So the builder splits work:

- **Model (in the workflow):** understanding speech, empathy, wording.
- **Generated code nodes/hooks (in the workflow):** date arithmetic (business days, holidays, deadlines, "next Friday"), amount floors and bounds, attempt counters, read-back checks, argument normalization. The generic code is written once; the **numbers, calendars and tables it uses are extracted from the brief** and passed in as data. No brief value is written into the builder.
- **Graph (in the workflow):** separate nodes for distinct stages (opening, identity, account, negotiation, confirmation, closing), tools exposed only in the node that may use them, transitions on tool results.
- **Lifecycle tool:** `close_call` guaranteed at call end where the brief requires exactly one close.

The minimal sample builder (one node, brief pasted as prompt) scores about half; the above is where the remaining points are. Start simple and add structure only when a failure label justifies it.

## Components

- **Entry** (`builder/build.py`): parses the arguments, runs the pipeline, prints the result. No policy logic.
- **Extractor:** brief text to typed rules and parameter tables. The only place brief text is interpreted. Uses a model; every call goes to the trace. Must tolerate raw material (mail, memo, code list) and later documents overriding earlier ones.
- **Resolver/validator:** override order, conflicts, missing information, tool existence.
- **Tool binder:** tool descriptors (fields, enums, required) from the OpenAPI file; never hardcoded field names.
- **Renderer (Freya adapter):** IR to workflow JSON; create/update/publish/export. See [`FREYA-INTEGRATION.md`](FREYA-INTEGRATION.md).
- **Self-test runner:** a bounded run of cases through the Freya simulation route; reports failure labels.
- **Trace writer:** plain-text log: start/end time, each model call (model, purpose), Freya IDs and step/tool counts, self-test results. Strips secrets.

## Repository shape

```text
builder/
  build.py            # official entry point (python3 builder/build.py brief tools)
src/agent_factory/    # or builder/lib; keep imports simple for a fresh checkout
  extract/  resolve/  tools/  ir/  freya/  selftest/  run_trace.py
tests/                # unit, regression; synthetic briefs only
submission/           # exported hidden-brief workflows
traces/               # per-brief run logs
reference/            # copy of kit material we rely on (freya.py client, docs)
```

The kit folder `build-the-builder-v2/` is reference material. Copy the parts the builder needs (e.g. `freya.py`) into the repo so a fresh checkout is self-contained.

## Dependency rules

- `ir/` imports nothing from `freya/`.
- `freya/` consumes validated IR; it does not read the brief.
- `build.py` only wires modules together.
- Standard library only where reasonable (the kit client is stdlib-only; Python 3.10+). Add a model SDK only if needed; pin versions. No syntax newer than 3.10.

## Builder model `[VERIFIED decision, 2026-10-10]`

- Provider: Anthropic Messages API over stdlib `urllib` (no SDK). Key from `ANTHROPIC_API_KEY` in `env.sh`; never logged.
- Default model `claude-sonnet-5-5` for extraction; `claude-opus-5-5` only where a measured failure justifies it. Model names are pinned in one config place and written to the trace for every call.
- Temperature 0, structured JSON output validated against the IR schema; one retry on invalid JSON, then fail the build with a clear error.

## Constraints that shape the design

- 30 minutes per brief including self-tests; a ten-case simulation takes 3 to 11 minutes, and simulations queue one at a time. Budget at most one or two self-test runs.
- Build time is a tie-breaker: few model calls, parallel where independent.
- Reproducibility: organizers rerun the builder from the commit. Pin model names, low temperature, no hidden state; the saved workflow slot file must not be required.
- Update the existing workflow in place with `save_workflow`.
- `save_workflow` keeps its local slot mapping in the ignored root file `.freya-agents.json`. A fresh checkout has no mapping, so its first run creates a workflow; later runs from the same working directory update that workflow in place. This consumes one additional workflow per fresh checkout, so keep the workspace cap in mind.
