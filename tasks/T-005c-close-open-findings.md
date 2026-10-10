# T-005c — Close the last open code findings (F-012, F-005)

**Owner:** claude-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

Read `docs/UAT-FINDINGS.md` F-012 and F-005, `build-the-builder-v2/docs/workflow-format.md` (top-level `tools`, lifecycle `config.alwaysRunsAt`), `tools-and-code.md`, `builder/freya.py` and `builder/build.py`.

## 1. F-012: outcome recorded when the customer hangs up

- If the call ends before the closing chain ran `close_call` (customer hangs up, timeout), an end-of-call lifecycle tool runs `close_call` with an outcome computed from call state. Use the same code and the same spec outcome table as the closing chain: the last `close_state` if set, otherwise derived from state (promise recorded → its row, identity not verified → its row, else `default`). If the spec has a row for a hang-up state, use it; add `hangup` (or similar) as an optional call-end state name in `spec.CLOSE_STATE_NAMES`.
- **Never double-record:** if the closing chain already recorded successfully (`close_call_ok` true), the lifecycle tool must not send a second `close_call`. Prefer a `pre_process_code` that cancels or neutralizes the request; check the kit docs for how a lifecycle tool can be skipped. If skipping cannot be guaranteed, document the options and pick the safer one (a double close is likely worse than a missing one when the brief says "exactly one close"). Mark the engine behavior `[TO-CONFIRM]`.
- Write tool: `maxRetries: 0`.

## 2. F-005: stale workflow slot

- Before updating, `build.py` checks that the stored workflow ID still exists (a read through the existing `freya.py` functions). If it is gone (404), create a new workflow, write a `warning:` line to the trace, and continue. Do not change `freya.py` itself (kit copy). If a wrapper is needed, put it in `build.py` or a small module.
- Offline test with a fake client: stored ID missing → create path taken, warning traced; stored ID present → update path.

## Tests

Lifecycle tool rendered with `alwaysRunsAt` end of call, baked values, no `{{ }}` in code, code never raises, skip logic covered; existing tests green; leakage scan green; `docs/PROMPTS.md` regenerated if prompts changed.

## Constraints

Python 3.10+, stdlib only. No Freya requests. No commit. No `env.sh`. No brief values in `builder/`. Update F-012 and F-005 status in `docs/UAT-FINDINGS.md`. Report in `tasks/T-005c-report.md`.
