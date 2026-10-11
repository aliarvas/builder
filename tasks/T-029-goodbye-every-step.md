# T-029: A goodbye exit at every conversation step

**Owner:** claude-dev · **Approver:** CTO

## Why

T-027 added the global `customer_ends_call` step only for `negotiate`, `offer_say`, `revise_ask` and `confirm_record`. The user's rule: every conversation step must have a goodbye exit, otherwise we fail in a loop (PUB-12 ran to max duration).

## What to build (generic, no brief value)

1. **Scope.** Every conversation step (including global conversation steps) can leave on a plain goodbye:
   - opening, identity and third party;
   - special-path ask steps, revise and callback steps;
   - every other conversation step the builder renders.
2. **Where each goodbye goes.**
   - **Accepted offers not yet recorded:** the read-back once, as now.
   - **Before identity has passed** (opening and identity): the closing, with the state the spec gives for a hang-up or end at that point. If the spec has no row, use the same state the end-of-call hook would compute (no account talk, no tool beyond close).
   - **Third party:** the same close the third-party path uses.
   - **Everything else:** `close_state='hangup'` → closing (notes, outcome, close_call).
   - A second goodbye always closes.
3. **Identity.** The kit says to keep interrupts out of identity. A goodbye is not an interrupt: it ends the call. If the kit's rule makes a global route impossible there, add the goodbye as the step's own route, a choice value or a condition, not a global. The intent must be strict: only goodbye or thanks to end the call, never an answer to a question.
4. **No routing shadow.** The T-023 `intent_shadow` check must stay green; name the goodbye in every choice field that can reach it.
5. **Turn-limit guard.** No step may loop on a goodbye. The self-check fails as BUILDER if any conversation step lacks a goodbye exit (a static check), and the goodbye family plays a goodbye at each step and reaches end_call within 2 goodbye turns.

## Tests

- The static check on all 10 fixtures and the live Brief A and A+B specs.
- A mutation that removes the exit from one step, which the check names.
- Play: goodbye at the opening, identity, third party, a special-path question and negotiate.
- `python3 -m unittest`, the leak test and the prompt budget guard.

## Constraints

- No Freya, no model call, no commit, no env.sh.
- claude-dev2 is editing the persuasion line in `builder/prompts.py` / `builder/product_notes.py` at the same time (T-030). Coordinate on shared files, and do not undo their lines.
- Report: `tasks/T-029-report.md`.
