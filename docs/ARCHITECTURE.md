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

## Phone agent template `[VERIFIED decision, 2026-10-10; node set refined by evidence]`

The builder renders a fixed, domain-generic skeleton of steps. The skeleton is code; every value, rule text, outcome code and calendar inside it is data extracted from the brief. A brief that lacks a stage simply leaves that branch unused.

```text
setup (code)           now + calendar data -> today, business days, deadlines
  -> opening           who answered: customer / third party / wrong number / deceased / unclear
       -> third_party  callback window checked by code -> schedule_callback -> close
  -> identity          only the identity tool; leave on the tool result, count attempts from results
  -> account (api)     account tool runs on entry; code turns products into short facts per product
  -> negotiate         state the debt, ask for date/amount; extraction of proposal and intent
  -> check_offer (code) date and amount against the brief's rules -> verdict + suggested alternative
  -> confirm_record    read-back, explicit yes, promise tool; honest result handling
  -> close (code + api) outcome/reason computed from call state, closing tool called with baked values
  -> end_call
special paths (from any step): dispute, already paid, hardship, restructuring, human, scam, robot question
```

Responsibilities:

| Work | Owner |
|---|---|
| Speech, understanding, empathy, wording | phone-agent model |
| Attempt counters, date and amount checks, outcome selection | code steps and hooks |
| Which tool is available when; that the closing tool always runs | workflow graph |

Each step's prompt follows the prompt budget below.

## Messy inputs `[VERIFIED decision, 2026-10-10]`

Both inputs can be messy: the brief (raw mail, memo that changes a policy, code list, tables) and the bank's tool responses during a call.

**Brief (builder time).** Extraction is an agent loop, not one model call:

1. Extract rules and tables with a source excerpt for each.
2. Check with code: values against the OpenAPI enums, outcome table complete, dates valid, superseded rules marked, numbers parsed.
3. Coverage check: every brief sentence is linked to a rule or marked irrelevant.
4. Ask the model again only about gaps or conflicts.
5. Arithmetic (business-day counts, windows) is computed by code, never guessed by the model.

**Fallback tiers, so no rule is lost:** (1) structured data enforced by code; (2) a short rule in the prompt of the step it belongs to; (3) a global rule in `system_prompt`. The trace lists each rule's tier, so it is visible which rules are guaranteed and which are only instructions.

**Tool responses (call time).** The agent never guesses a customer fact; it gets it from a tool or says it does not have it. A post-hook on each tool turns the raw response into short plain facts and a `what_to_do_next` line, and tolerates missing or extra fields. The phone agent may call only the bank's tools, so all interpretation that needs extra help happens at builder time.

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

- **Prompt budget:** each step's dialogue prompt (`system_prompt` + `role_message` + `task_message`) stays within 500 to 1,500 tokens (Freya guidance, see [`STARTER-KIT-FACTS.md`](STARTER-KIT-FACTS.md)). The whole brief is never pasted into one step. Each step gets only the rules for its stage, rewritten short, with computed facts (dates, amounts) filled in by code. The builder measures every step and fails or splits when a step is over budget.

- 30 minutes per brief including self-tests; a ten-case simulation takes 3 to 11 minutes, and simulations queue one at a time. Budget at most one or two self-test runs.
- Build time is a tie-breaker: few model calls, parallel where independent.
- Reproducibility: organizers rerun the builder from the commit. Pin model names, low temperature, no hidden state; the saved workflow slot file must not be required.
- Update the existing workflow in place with `save_workflow`.
- `save_workflow` keeps its local slot mapping in the ignored root file `.freya-agents.json`. A fresh checkout has no mapping, so its first run creates a workflow; later runs from the same working directory update that workflow in place. This consumes one additional workflow per fresh checkout, so keep the workspace cap in mind.
