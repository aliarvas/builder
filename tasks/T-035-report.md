# T-035: the note loop ends without code (short report)

No Freya, no model call, no commit.

## Tests

- **T-035 tests:** `tests/test_t035_code_cycles.py`, 6 tests, all OK.
- **Full suite:** 655 tests, 4 failures, none from T-035:
  - `test_multi_step…confirm_can_revise` and `test_offer_date_only…yes_to_the_proposed_date`: the in-progress `confirm_record`/negotiate edits of T-037/T-038 (other sessions);
  - the Brief A pin: Brief A has no note loop, so T-035 does not move it;
  - `PROMPTS.md`: I did not touch `prompts.py`.
- **Self-check:** the code_cycle check passes on the 10 fixtures and the live A and A+B specs. The only other failures are the known `reach_outcomes` gaps.

## Fix

1. **Guard (`builder/product_notes.py`).** `note_record` (api) gets an exit to after-notes (`notes_outcome` or `closing_say`) that reads only the engine counters, the same pattern as F-067 on `close_record`. It sits before its always exit to `note_next`, so `note_next` keeps its shape.
   - Counters: `note_record_*_count` and `<note tool>_*_count`.
   - **Failure cap** `NOTE_LOOP_CAP` = 2 tries × 2 × `ESTIMATED_PRODUCTS` = 12.
   - **Success cap** `NOTE_SUCCESS_CAP` = 2 × `ESTIMATED_PRODUCTS` = 6, since a product never needs two written notes.
   - **Bound:** at most 13 note calls, and at most 7 when every call succeeds, which was the v20 shape. The live call made ~40.
2. **Static check `code_cycle[...]` (BUILDER, `builder/code_cycles.py`).**
   - Tarjan finds every loop of code and api steps in the rendered workflow, globals included.
   - Each loop needs an exit that holds on that loop's engine call counters alone. The check handles the merged "or" routes.
   - A loop with no api step is always flagged.
   - **Today's loops:** close, record and note; all three are now guarded.
3. **Sandbox-down play (`sandbox_down_walk` / `sandbox_down_chain`, in the self-check as `code_cycle[closing:…]` / `[record_next:…]`).**
   - Every code run fails and stale variables keep each loop going as long as they can.
   - From `closing` and from `record_next`, with every call failing or every call succeeding, the chain must reach `end_call` within 40 api calls.
   - **Today:** 13 notes + 2 closes; 13 promises + 13 notes + 2 closes.
4. **Tests:**
   - no gap on all 12 renders;
   - note loop counts of 13 (failure) and 7 (success);
   - mutation: without the guard, the check names `note_next+note_record` and the chain never ends; the same holds for the close and record loops;
   - a pure code loop is flagged;
   - the caps sit above the largest kit case (3 products).
   - One expectation in `tests/test_multi_step.py:644` changed: `note_record` edges are now `[after, note_next]`.

## Possible cause (item 4): not only a platform glitch

- **What the record shows:** it contains **"Sandbox payload too large"** 25 times, on `note_next`, and "not parseable" 186 times.
- **What it points to:** the variables sent to the sandbox hold copies of the call variables nested as escaped JSON (`\\\"title\\\": …` inside a string). Some variable seems to store a serialised snapshot that grows with each run.
- **Not finished:** I ran out of time before naming the variable.

**Follow-up (proposed T-0xx):** take the last vars snapshot before the first "payload too large", find the largest variables, and stop the variable that nests the call variables (probably a `*_response` or `*_args` mapping, or the pre-hook body). Then add a self-check bound on vars size.

## UAT proposal

**F-new: "The note loop ran ~40 times when the code sandbox failed"**
- **Status:** fixed offline (T-035).
- **Cause:** the code-driven loop had no exit on engine counters; the sandbox failed with "payload too large".
- **Open:** why the payload grew (see the follow-up above).
