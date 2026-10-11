# T-010 — Offline self-check and repair inside the builder (layer 1 of "tests and improves it")

**Owner:** claude-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

## Why

The orange box is "reads the brief, creates the phone agent, tests and improves it". Today the builder repairs the spec before rendering and runs three synthetic chats after publishing, but it never tests the rendered workflow against what the spec requires, and it never improves the agent from a test result. Layer 1 closes that gap without Freya and without practice customers: it works for any hidden brief.

## What to build

1. **Move the simulator into the builder.** The test `Session` / `PlatformCall` walker (`tests/test_multi_ready.py`, `test_product_notes.py`, `test_now_cases.py`) becomes `builder/selfcheck.py`. It runs the generated code steps, evaluates rendered transitions, applies the platform rule for typed writes, plays the bank from the spec and the OpenAPI shapes, and uses "ideal extraction" from spec values. Tests import it from there.
2. **Scenarios generated from the spec only** (no practice file, no brief value in code):
   - identity: pass, each fail path, attempts used up;
   - third party: callback inside the window, outside, each close value;
   - each outcome row of the closing table must be reached by at least one scenario;
   - each special path (return and close);
   - offer checks: ok, not a business day, after the deadline, below the floor, over the full amount, the invalid-offer limit;
   - multi-product when the spec has it: accept all, refuse one, a record failure.

   For each scenario the expected ledger comes from the spec (outcome/reason, promise dates from the spec calendar via an independent helper like `tests/now_calendar.py`, notes).
3. **Checks per scenario:**
   - reaches `end_call`;
   - exactly one `close_call`, and it is the last tool call;
   - the ledger matches the expectation;
   - no rejected typed write;
   - no dead end (a step with no route the scenario can take);
   - at most one spoken message per closing turn.
4. **Repair loop:**
   - A failure that points at the spec goes back to extraction as a repair round. Examples: an unreachable row, a missing state or path, a value that cannot be routed. The repair message names the scenario and the step.
   - A failure that points at builder code is a trace warning, not a repair.
   - At most 2 rounds. A time guard keeps the build inside the 30-minute limit.
   - If it is still failing, ship with warnings: the build never stops for this.
5. **Trace:**
   - one `self_check:` line per scenario (pass/fail/reason);
   - a summary;
   - the repair rounds it caused.

   `tools/submission_check.py` must accept the new lines.
6. **Runs in every mode:** with `--print` and `--spec` as well. It takes seconds and makes no model or Freya call (except the repair rounds).

## Tests

- Every fixture and recorded extracted spec passes the self-check, or fails only where a known gap exists (list it).
- The REPRO 13:00 spec fails on the hardship row and goes to repair.
- A mutated workflow (a broken route, a missing tool) is caught.
- Leak test green.
- Timing: the self-check of A+B runs in under 10 seconds.

## Constraints

- Python 3.10+, stdlib.
- No Freya, no commit, no `env.sh`, no live model call.
- Do not change the kit `freya.py`.
- Report in `tasks/T-010-report.md`. Write a short design note at its top before you implement.
