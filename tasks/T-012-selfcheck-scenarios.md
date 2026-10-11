# T-012 — More self-check scenario families

**Owner:** claude-dev2 · **Reviewer:** claude-reviewer · **Approver:** CTO

## Why

Layer 1 (`builder/selfcheck.py`, T-010) does not play several call-end states yet. Rows mapped only to these states count as "reached" without being played. Read `tasks/T-010-report.md`, especially "Spec problems still not detected" and the split proposal.

## What to build

1. **New scenario families, generated only from the spec:**
   - the customer hangs up: at the opening, during identity, during negotiation, and after a promise is recorded;
   - the turn limit is reached;
   - the account read fails;
   - unclear or need-time answers to the callback question (third party);
   - a revise request at the read-back, followed by a new offer;
   - two special paths in one call;
   - a special path at a step other than its first `available_in` step.

   Each scenario gets its expected ledger from the spec, as today. A row mapped by one of these states must now be **played**, not just counted as reached.
2. **Move the remaining test walkers onto `builder/selfcheck.py`:** `tests/test_multi_step.walk` and `tests/test_closing_speech.spoken_per_turn`. Existing tests must keep their behaviour.
3. **`tools/submission_check.py`:** check the format of the `self_check_summary` line. If the line is present, it must be `scenarios=`, `pass=`, `fail=`, `spec=`, `builder=`. Add a test.

## Coordination

claude-dev works on T-011 at the same time. It changes the closing note order and the expected ledger in `selfcheck.py`. Keep your edits in separate functions, and re-read the file before each edit.

## Tests

- Every fixture still passes, except the known gaps.
- A mutation per new family is caught.
- The A+B self-check stays under 10 s in build mode.
- Leak test green.
- `python3 -m unittest`.

## Constraints

No Freya, no model call, no commit, no `env.sh`. Write the report in `tasks/T-012-report.md`.
