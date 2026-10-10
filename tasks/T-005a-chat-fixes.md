# T-005a — Fix the four PUB-03 chat failures

**Owner:** claude-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

## Why

First chat test of the multi-step agent (Brief A, PUB-03, call `da86613c-a3c8-4f68-b8f3-7e2ae5f1b638`) failed. Read `docs/UAT-FINDINGS.md` F-019..F-022 first; they describe symptom and cause. Also read `reviews/T-004-review.md` finding 5 and `reviews/T-004-rereview.md` (N5–N8 and the three Fix2 notes).

Read before coding: `AGENTS.md`, `docs/ARCHITECTURE.md` (template), `build-the-builder-v2/docs/workflow-format.md` and `tools-and-code.md`, `builder/workflow.py`, `builder/prompts.py`, `builder/spec.py`, `tests/test_multi_step.py`.

## Fix

1. **F-019 Opening uses the customer's name.** The opening prompt must contain the call variables for how to address the customer (e.g. title and last name). Which call variables exist comes from the spec (add a field such as `opening.address_with: ["title", "last_name"]` or a greeting template with placeholders), never typed in code.

2. **F-020 Identity handles a failed answer honestly.**
   - After `verified: false`: say the answer did not match and ask the **same** field again (hints only if the spec allows). Never say "thank you" as if it passed. Move to the next field only after `verified: true` for the current one.
   - Convert spoken answers to the tool format yourself (dates, digits). Never ask the customer to speak a technical format.
   - When no attempts are left: say the spec's identity-failure sentence (e.g. use the app or a branch) and ask nothing more.
   - Wording rules generic in `prompts.py`; brief-specific sentences come from the spec (add fields to the fixtures as needed, all three fixtures).

3. **F-021 Routing after a tool result is suppressed in chat.** Observed: after the tool result, the engine logged `route_evaluated ... "Suppressed: Missing prior assistant message"`, and the step only changed on the next user message. Note the identity step re-enters itself every turn through an `always → identity` transition (`node_enter identity from identity`), which may be why there is "no prior assistant message" in the node. Investigate in the kit docs and pick a generic design so a decisive tool result (verified, no attempts left, promise recorded or failed) takes effect in the **same** turn. Candidates: no self-loop `always` (check what the docs say about staying in a node), or the tool step routes to a passthrough code/api step. If it cannot be guaranteed, make the calling step's own prompt say the right thing for the result (item 2) so a one-turn delay does no harm. Write down which you chose and why in the report; mark unverified engine behavior `[TO-CONFIRM]`.

4. **F-022 Closing knows why the call ends.** Outcome, reason and the closing sentence are computed by code from call state (identity exhausted, third party, promise recorded, promise failed, special path, ...), not chosen by the model. Then `close_call` runs with baked values (prefer an engine-run api step, so the model cannot skip or alter it), then `end_call`. The mapping from state to outcome/reason/sentence comes from the spec's outcome table (add `say` per outcome). Keep bounded retry and honest failure from T-004-fix2. Covers T-004 review 5(a)/(d).

## Tests (offline)

- Rendered workflow for all three fixtures: opening prompt contains the address placeholders; identity prompt contains the failed-answer and exhausted rules; closing computes outcome by code for each terminal state; no step can reach `end_call` without the close path; no hardcoded brief values (existing leakage test must stay green and cover new fields).
- Code snippets compile, contain no `{{`/`}}`, never raise on missing vars.
- Prompt budget per step ≤ 1,500 tokens; regenerate `docs/PROMPTS.md`.

## Constraints

Python 3.10+, stdlib only. No Freya requests (CTO runs the chat test with user approval). No commit. Do not read `env.sh`. No brief values in `builder/`. Record any new failure in `docs/UAT-FINDINGS.md` and update F-019..F-022 status when fixed.

## Done when

`python3 -m unittest` passes; `--print --spec tests/fixtures/spec-brief-a.json` works; short report: what changed per item, the F-021 design choice, open questions.
