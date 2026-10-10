# T-004 — Multi-step phone agent from a spec

**Owner:** codex-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

## Goal

Replace the single conversation step with the step skeleton in `docs/ARCHITECTURE.md` ("Phone agent template"). The skeleton is generic code; its content comes from a **spec** (JSON) that describes one brief. In T-006 an LLM will write the spec from the brief. In this task the spec is hand-written as a test fixture, so the renderer can be built and tested now.

Read first: `docs/ARCHITECTURE.md` (template, messy inputs, prompt budget), `docs/UAT-FINDINGS.md` F-001..F-012 (what the current agent gets wrong), `build-the-builder-v2/docs/workflow-format.md` and `tools-and-code.md`, `build-the-builder-v2/.claude/skills/build-phone-agent/SKILL.md`, `build-the-builder-v2/examples/base-agent.json`.

## 1. Spec format (`builder/spec.py`)

A small, typed, versioned JSON format (`spec_version: 1`), validated on load with clear errors. Keep it minimal; it will grow in T-005/T-006. Each rule text carries a `source` excerpt field (may be empty in fixtures). Proposed sections:

- `agent`: who the agent is (bank name, how it introduces itself), language.
- `opening`: rules for the first sentence, the confirmation question, what counts as confirmation, what to do when unclear, words forbidden before verification.
- `third_party`: rules when someone else answers (what may be said, callback, wrong number, deceased).
- `identity`: ordered questions (`field` value from the OpenAPI enum, how to ask, answer format), rules for wrong answers, hints, refusal.
- `account`: how to state the debt per product.
- `negotiation`: rules for asking date and amount, persuasion, refusals.
- `confirmation`: read-back rules, sentence after a recorded promise, failure handling.
- `special_paths`: list of `{id, when, say, tool, tool_args, outcome, reason}` (dispute, already paid, hardship, restructuring, human, scam, robot question, ...). Generic: the list comes from the spec, not from code.
- `outcomes`: the outcome/reason table `{outcome, reason, when}`.
- `global_rules`: rules for every step.

Fixtures (test data, may contain practice values): `tests/fixtures/spec-brief-a.json` and `tests/fixtures/spec-brief-b.json` written by hand from the practice briefs, and one **synthetic** spec with different identity questions, outcomes and special paths to prove nothing is hardcoded.

## 2. Renderer (`builder/workflow.py` or a new module)

Render the skeleton from spec + OpenAPI tools:

- **Steps:** `opening` → (`third_party` | `identity`) → `account` (api_request, account tool on entry, passthrough) → `negotiate` → `confirm_record` → `closing` → `end_call`. Special paths as global steps or explicit transitions, generated from `special_paths`.
- **Tool scoping:** each step lists only its tools. The identity tool exists only in `identity`; the promise tool only in `confirm_record`; the closing tool only in closing steps. (Fixes F-009, F-010 partly.)
- **Routing on tool results, not on words:** leave `identity` on `all_verified` (both `"true"`/`"True"`) or when no attempts are left (`wrong_answers_left` ≤ 0 via `less_than 1`); leave `confirm_record` on the promise result. Use `extraction_schema` enums for the customer's intent and for who answered, with `min_confidence` set, as the workflow docs recommend. Field and variable names come from the OpenAPI file and the spec, never typed in code except the seven fixed tool names.
- **Product id never typed by the model (F-008):** the account result is mapped to variables; the promise tool takes a product number chosen from the list the agent was given, and a `pre_process_code` hook maps it to the real id from the stored account result. Generic: works for one to three products.
- **Closing on every path (F-001, F-004, F-012):** every terminal path goes through a closing step that calls the closing tool, then `end_call`. Do not add an end-of-call lifecycle close yet (T-005 decides that with call state).
- **Prompts:** each step's `task_message` built only from that step's spec rules, in `builder/prompts.py` templates. Respect the prompt budget: compute the estimate per step; if a step is over 1,500 tokens, write a trace warning (no automatic split yet). `docs/PROMPTS.md` regenerated.
- Keep T-003 behaviour: post-hooks, tool triggers, tolerant OpenAPI.

## 3. CLI

`python3 builder/build.py <brief...> <tools.json> --spec <spec.json>` uses the given spec (extraction comes in T-006). Without `--spec`, keep the current single-step behaviour as a fallback and say so in the trace. Trace lists steps, tools per step and per-step prompt estimates.

## 4. Tests (offline)

- Spec validation: good fixtures load; missing required section or unknown outcome gives a clear error.
- Rendered workflow for A, B and the synthetic spec: no `null`, no `agent_config`, name == key, tools only on conversation steps, every step reachable, every path ends in the closing step then `end_call`, passthrough steps end with `always`.
- Tool scoping as listed above.
- The product-id hook: compiles, no `{{ }}`, maps 1..3 to ids from a sample account result, never raises on bad input.
- No practice value (names, amounts, dates, holiday dates, outcome names) appears in `builder/` code: scan the source for every string value found in the fixtures and the practice briefs, except the seven tool names and words from the OpenAPI file.
- Per-step prompt estimate under 1,500 for the A fixture (adjust wording if not).

## Constraints

Python 3.10+, stdlib only. No Freya requests (the CTO will request a dry run and chat tests with user approval). No commit. No `env.sh`. Record any observed failure in `docs/UAT-FINDINGS.md`.

## Done when

Tests pass; `--print --spec tests/fixtures/spec-brief-a.json` prints the multi-step workflow; short report with the step list, tools per step, prompt estimates, and open questions for T-005 (date/amount code) and T-006 (extraction).
