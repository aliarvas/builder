# T-005b — Global special paths, deterministic special exits, code-checked offers

**Owner:** claude-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

## Why

An outside review of the workflow (version 3) said: the architecture is right, but (1) special paths are copied per step (`special_<id>_from_<step>`), which costs steps and leaves gaps; (2) leaving a special path depends on the model judging "the required response has been given"; (3) `negotiate` leaves only when the extractor labels the turn `proposal` with confidence ≥ 0.8, so it can circle. T-005a already removed the self-loop `always` transitions, so global nodes can now fire (they are checked only when no node transition matches).

Read first: `AGENTS.md`, `build-the-builder-v2/docs/workflow-format.md` ("Order of evaluation", "Global nodes", "Passthrough nodes", "Extraction schema"), `tools-and-code.md`, `docs/ARCHITECTURE.md` (template: `check_offer`), `builder/workflow.py`, `builder/spec.py`, `builder/prompts.py`, both practice briefs (to see what date and amount rules look like; never copy their values into `builder/`), `docs/UAT-FINDINGS.md` F-003, F-011.

## 1. Special paths as global nodes

- One global node per `special_paths` entry, instead of one copy per step. `excluded_nodes` = every step not in the path's `available_in`, plus all opening/identity steps unless the spec lists them, plus the whole closing chain and `end_call` (no loops, no account talk before identity is verified).
- `then: return` uses `__previous__`. `then: close` goes to the path's `close_special_<id>` state step.
- Keep the deterministic transitions of each step first; global nodes only catch what they did not match.
- `[TO-CONFIRM]` in chat: does a global node fire from a step whose only transitions are deterministic or `matches_intent`? Mark it in the report.

## 2. Deterministic special exits

- A special path does not ask the model whether it is done. Sequence: fixed line from the spec (`say`, spoken via `on_enter` tts or a short dialogue turn if the spec needs a question answered) → if the spec names a tool, the engine runs it with baked/spec values (api step, honest result handling, `maxRetries: 0` for write tools) → route on the tool result → close or return.
- If a path genuinely needs a model-filled tool argument, the tool stays on that conversation step and the exit routes on the tool's `response_mapping`, never on `matches_intent`.

## 3. Offer check in code (`check_offer`)

- `negotiate` extracts the customer's proposal as **data**: date (normalized to the tool's date format; the extractor may use the date placeholders listed in workflow-format) and amount (number), plus the product choice when several products exist. No `proposal` label needed to leave the step: leave when date and amount are both set (deterministic `is_set`/value checks), or on an explicit refusal.
- A passthrough code step `check_offer` evaluates the proposal against the brief's rules, given as **data in the spec**, never in code:
  - calendar: non-business weekdays and holiday dates, "today" from the call's `now` variable (or the system date if none);
  - date rules: latest allowed date per condition on the product (e.g. a field threshold → a number of business or calendar days, or "next business day if the deadline falls on a non-business day"), earliest date;
  - amount rules: minimum (a product field, a fixed number or a share of a field), maximum, whole-or-part.
  Design a small generic rule format; prove it with fixtures A, B and the synthetic spec.
- Output variables: verdict (`ok` / `date_too_late` / `amount_too_low` / ...), a suggested alternative (latest valid date, minimum amount), and a short sentence for the agent. Route: `ok` → `confirm_record`; otherwise back to `negotiate`, whose prompt reads the verdict and the suggestion. Count rejected offers; the limit comes from the spec.
- The values `create_promise` sends (date, amount, product) come from the checked variables, not from the model's memory.
- Code: try/except, no `{{ }}`, never raises, writes a fallback for every variable a prompt or condition reads.

## Tests (offline)

- Global nodes rendered for each special path; no `special_<id>_from_*` copies; `excluded_nodes` covers identity (unless allowed), the closing chain and `end_call`; every `then: return` uses `__previous__`.
- No `matches_intent` exit from a special path.
- `check_offer` table tests with each fixture: holiday shift, band deadline, minimum amount, weekend, a date before today, missing values. Expected verdicts computed by hand in the test.
- Existing tests green; leakage scan covers the new spec fields; prompt budget ≤ 1,500 per step; `docs/PROMPTS.md` regenerated; trace lists the step count before and after.

## Constraints

Python 3.10+, stdlib only. No Freya requests (CTO runs the chat test with user approval). No commit. Do not read `env.sh`. No brief values in `builder/`. New failures go to `docs/UAT-FINDINGS.md`.

## Done when

Tests pass; `--print --spec tests/fixtures/spec-brief-a.json` works; report in `tasks/T-005b-report.md`: step count before/after, the rule format, design choices, `[TO-CONFIRM]` items for the chat test (PUB-01 promise, PUB-07 callback), open questions for T-006 (what the extractor must produce).
