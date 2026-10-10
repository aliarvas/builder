# T-005d — Simpler closing routing, safer opening

**Owner:** claude-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

Read first: `AGENTS.md`, `builder/workflow.py`, `builder/spec.py`, `builder/prompts.py`, `tests/test_multi_step.py`, `build-the-builder-v2/docs/workflow-format.md` (passthrough, `on_enter`, `on_enter_first_entry_only`, extraction), `reviews/T-004-rereview.md` N7, `docs/UAT-FINDINGS.md` F-021, F-022.

## 1. Closing without per-state tagging steps

Today 18 one-line code steps (`close_<state>`) feed `closing`, each only writing `vars['close_state']`. The engine cannot set a variable on a transition, which is why they exist. Goal: remove them, keep identical outcomes.

- Source steps route straight to `closing` (the deterministic conditions stay as they are).
- Where the source is already a code step (`check_offer`, `confirmation_progress`, special entry/`_done` steps, ...), it writes `close_state` itself before routing.
- For the rest, the `closing` code derives the call-end state from variables that already exist (identity result and attempts left, who answered, opening unclear count, promise counts and results, offer verdict and rejected count, callback result, special path markers, turn counters), in one explicit priority order kept in one place. An explicit `close_state` written by a code step wins over derivation.
- If a state cannot be derived from existing variables without ambiguity, keep a tagging step for that one state only, and say why in the report.
- One shared derivation must also feed the hang-up lifecycle hook (T-005c), so both paths pick the same row.
- Proof of equivalence: the existing "every call-end state gives the right outcome" tests must pass unchanged in expectation; add a test per fixture that simulates the variable state of each terminal path and checks the derived state. Report the step count before and after.

## 2. Opening: greeting, repeated introduction, disclosure

- **Greeting is not an unclear answer.** Add a separate value for a bare greeting or a line check ("Hello?", "Who is this?" before the identity question was understood) to the who-answered extraction, generic wording. It does not count toward the unclear limit; the step stays and repeats the question. Only genuinely unclear answers to the question count. The value name is framework vocabulary, not brief data.
- **No repeated introduction.** Re-entering `opening` (after `opening_unclear`) must not repeat the introduction and recording notice; it only repeats the question. Use `on_enter_first_entry_only: true` or a re-entry prompt, whichever the kit docs support; make sure the agent still speaks on re-entry (no silence). Mark engine behavior `[TO-CONFIRM]`.
- **Disclosure first.** Add one generic rule to the system prompt (or the steps that can be reached first): if the introduction and the recording notice have not been said yet in this call, say them first, whatever the customer said. The actual sentences come from the spec.

## Tests

Existing tests green; new tests for the derivation, the greeting value not counting, `on_enter_first_entry_only` (or the chosen mechanism) on `opening`, the disclosure rule present; no repeated `target_node` per node; leakage scan green; prompt budget ≤ 1,500 per step; `docs/PROMPTS.md` regenerated.

## Constraints

Python 3.10+, stdlib only. No Freya requests. No commit. No `env.sh`. No brief values in `builder/`. New failures to `docs/UAT-FINDINGS.md`. Report in `tasks/T-005d-report.md`: step count before/after, the priority order, the opening mechanism chosen, `[TO-CONFIRM]` items for the chat test.
