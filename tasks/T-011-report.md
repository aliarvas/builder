# T-011: closing outcome derived from the product notes (AB-FRESH risk 5)

## Design note (written before the implementation)

**Goal:** a multi-product brief can say "no promise and every product noted with reason X → row X; otherwise the row of the first other note". The spec gets an optional block for it, and the closing derives the call's outcome from the notes after the note loop. A spec without the block renders exactly as today.

**Spec block:** `closing.product_notes.outcome_from_notes`, null or an object:
- `all_reason`: a note reason (one of `reasons`);
- `all_outcome`, `all_outcome_reason`: the closing row used when every product's note has `all_reason` (`all_outcome_reason` may be "");
- `otherwise_outcome`: the outcome used otherwise, with the reason of the first product, in account order, whose note reason is not `all_reason`;
- `source`: an excerpt from the documents.

It applies only when the call recorded no promise, the outcome is not in `skip_outcomes`, and every product of the account has a known note reason. Otherwise the outcome stays as today. If the derived pair is not a row of the table, the outcome also stays as today.

**Extraction:**
- the shape in the outcomes prompt, next to `product_notes`;
- a check in `_check_product_notes`: the reasons and the outcome pair must be in the table and in the documents, with a source excerpt;
- a new optional block, `notes_outcome`. If the check fails, only this sub-block is dropped with a warning; the note rule stays;
- the F-065 reach check (`_check_reach`) and the render warning (`unreachable_outcomes`) count the pairs the block can derive as reachable.

**Closing order:**
- Today the order is `closing` (outcome, sentence) → `note_next` / `note_record` loop → `closing_say`.
- The note loop needs a provisional outcome: `skip_outcomes` (no notes after a transfer) and the close reason as the default note reason. So `closing` stays where it is, and the outcome it sets becomes provisional.
- With the block, a new code step `notes_outcome` runs after the loop, before `closing_say`. It reads the note reasons in account order and, if the rule applies, rewrites `close_outcome`, `close_reason`, `close_resolved_state` and `closing_sentence` from the derived row. So the final outcome is chosen after the loop.
- The note reasons are kept in two new variables:
  - `note_next` stores the reason of each note it sends (`note_reasons_sent`);
  - the done step of a returning special path that wrote a note stores the path's fixed reason (`note_reasons_special`).
- These lines are added only when the block exists, so the generated code of every spec without it is unchanged.
- The `note_next` / `product_notes` code belongs to claude-dev2. I add one appended snippet and one new step; the existing body is not changed.

**Self-check:**
- My change is small: `_expected_pair` derives the pair from the scenario's expected notes when the spec has the block, so the risk-5 rows become reachable through the returning-path scenarios.
- A special action may name the product it is for (`number`, default 1), so a test can note several products.
- The `KNOWN` gaps shrink for the fixtures that carry the block.

**Not covered:**
- the end-of-call hangup hook (it computes its own outcome and writes no notes);
- a closing special path that writes a note with the same tool (its reason is not tracked, so the rule does not apply).

**Tests:**
- A+B: every product noted paid gives the paid row; one dispute and the others paid gives `no_promise/dispute`;
- `spec-brief-a.json` renders byte-identically to the committed code;
- the block is dropped when it is invalid;
- the leak test;
- `python3 -m unittest`.

## Implementation

**Spec (`builder/spec.py`)**
- `_validate_notes_outcome` validates the optional block `closing.product_notes.outcome_from_notes`:
  - keys: `all_reason`, `all_outcome`, `all_outcome_reason` (may be "", default ""), `otherwise_outcome`, `source`;
  - `all_reason` must be a note reason;
  - (`all_outcome`, `all_outcome_reason`) must be a row of the table;
  - `otherwise_outcome` must be an outcome of the table;
  - null removes the key.
- `NOTES_OUTCOME_KEYS` and `notes_outcome_pairs(notes)` give the pairs the block can derive. The reach checks use them.

**Extraction (`builder/extract.py`, `builder/prompts.py`)**
- The outcomes prompt has the block's shape inside `product_notes`. It is neutral wording with no brief value, and `docs/PROMPTS.md` was regenerated.
- `_check_notes_outcome`:
  - it checks the reason, the pair, the outcome and the source excerpt;
  - errors go to repair first; in the last round only the sub-block is dropped (`optional block notes_outcome dropped`), and the note rule stays.
- `OPTIONAL_BLOCKS` gains `notes_outcome`; `drop_optional` sets it to null.
- `_check_reach` (F-065) counts the derivable pairs as reached.

**Render**
- `builder/product_notes.py`: with the block, `note_next` → `notes_outcome` (new code step) → `closing_say`. Without the block it stays `note_next` → `closing_say`.
- `builder/offer_check.py`:
  - `NOTES_OUTCOME_BODY` and `notes_outcome_code` add the step. It runs only if:
    - no promise was recorded (both `promise_recorded_count` and the recorded numbers);
    - the provisional outcome is not in `skip_outcomes`;
    - the provisional state is not a closing special path (`special:*`) and not `special_tool_failed`. Those pairs and their spoken lines come from the documents or from the F-065 failure row;
    - every product has a known note reason.
  - What the step does:
    - every product noted `all_reason` → the `all_*` row;
    - otherwise → `otherwise_outcome` with the first other reason in account order;
    - a pair that is not a row changes nothing.
  - If the pair changes, it sets `close_outcome`, `close_reason` (cleared for a row without a reason), `close_resolved_state = notes:<reason>` and the row's sentence. After `promise_failed`, the failure sentence is kept, so the customer still hears that recording failed; only the pair follows the notes.
  - `NOTE_SENT_BODY` is appended to `note_next` and `NOTED_REASON_BODY` to the done step of a returning special path with the note tool. They store the reasons in `note_reasons_sent` and `note_reasons_special`. Both are added only with the block.
- `builder/workflow.py`: passes the path's fixed note reason (`tool_args[reason_field]`) to `special_noted_code`. `unreachable_outcomes` counts the derivable pairs as reached.
- **claude-dev2's code:** I added a step after their note loop and appended snippets to `note_next` and the special done step, only when the block exists. Their bodies (`NOTE_NEXT_BODY`, `NOTED_BODY`) are unchanged, and `closing` still runs before the loop.

**Self-check (`builder/selfcheck.py`, small change):**
- `_notes_pair`: when the spec has the block, `_expected_pair` derives the pair from the scenario's expected notes, with the same conditions as the code. A special path's own pair and `special_tool_failed` keep their own pair.
- A special action may name its product (`number`, default 1); this is one line in `play`.
- I re-read the file before each edit. claude-dev2 was editing `play` (T-012), and my two edits are in separate places.

**Fixture**
- `tests/fixtures/spec-brief-b.json` gets the block, with source text from `brief-b.md`. The file stays in its compact one-line format (a 1-line diff).
- The recorded extractions (`brief-ab-extracted*.json`) are not changed: they record what the model gave, without the block. The tests add the block to copies of them.

## Results

`python3 -m unittest`: 518 tests. **One failure, not from T-011:** `test_selfcheck.MutationTests.test_a_missing_close_call_is_caught`. It runs on Brief A (byte-identical render), and claude-dev2's new hangup scenarios (T-012, in progress) pass there through the end-of-call close. During my run, two other T-012 problems came and went: the leak-test literal `"revise"` in `selfcheck.py`, and a moved walker that rejected `import time`. claude-dev2 should check them.

New tests in `tests/test_notes_outcome.py` (10):
- A+B (`spec-brief-b`, plus copies of the tagged and v2 recorded extractions with the block added), three products:
  - each noted paid by the returning path → `paid/-`. Its sentence is the row's spoken sentence (`close_resolved_state = notes:paid`), and no extra note is written;
  - paid, dispute, paid → `no_promise/dispute`;
  - p1 refused (note by code), p2 dispute, p3 paid → `no_promise/refused` (the first other note in account order);
  - a call with a recorded promise keeps the promise row (`multi_refuse_one` passes);
  - the full self-check passes on these specs, so the risk-5 rows are reached.
- **Render:**
  - `spec-brief-a.json` gives the same sha256 as the render at commit 74eb27a (`f7a8c468…`);
  - without the block, Brief B has no `notes_outcome` step and none of the new variables;
  - I also compared four renders byte for byte before and after (spec-brief-a, spec-brief-b without the block, brief-ab-extracted-v2, brief-a-v11): all identical.
- **Spec:** an invalid block raises `SpecError` (reason, pair, outcome, unknown key).
- **Extraction:** the block survives the round trip; each error is repaired first, then only `outcome_from_notes` is dropped and the note rule stays.

Changed tests:
- `test_multi_step`, `test_product_notes`: the note loop's edge is `notes_outcome` when the spec has the block.
- `test_outcome_reach`: v2 still has 2 warnings; Brief B has none, and 2 again if the block is removed.
- `test_selfcheck`: `KNOWN` loses `spec-brief-b.json` (rows 1 and 3).

The leak test is green.

## Limits and proposals

- **Hangup:** the end-of-call close hook (`close_call_on_hangup`) computes its own outcome and writes no notes. A call cut off after the notes closes as before.
- **A closing special path that writes a note with the note tool:** its reason is not tracked, so the rule does not apply (the provisional pair stays). No fixture has such a path.
- **All products noted by special paths:** the flow needs one more customer turn (a refusal) at `negotiate` to close. That is the flow as before (`NOTED_BODY` reports `ready` only with accepted offers). Proposal for claude-dev2: when every product is handled and nothing was accepted, go to the closing directly.
- **Recorded extractions:** they have no block. A fresh A+B extraction (live, with approval) should now produce it. The trace should show no `unreachable_outcome` line, and the self-check `builder=0` for the risk-5 rows.
- **Closing rule text:** the brief's rule text ("With no promise recorded: …") stays a `closing.rules` entry for the agent's prompt. A new `enforced_by` tag (for example `notes_outcome`) would take it out of the prompt, but that touches the rule placement (`workflow.py`, T-009d, claude-dev2). This is a proposal, not done.
- **UAT proposal (CTO):** "Multi-product: the outcome derived from the notes is not written (AB-FRESH risk 5)". Cause: the spec had no field for the rule, and the closing chose the outcome before the notes. Fix: the optional block plus the `notes_outcome` step after the loop. Status: fixed offline; a live A+B check is open.
- **Live check (with approval):** a fresh A+B build, then a chat where every product is already paid, and one with a dispute among paid products.

No Freya, no model call, no commit, no env.sh.

## Fix (review T-011)

The review is in `reviews/T-011-review.md` (fixes needed). `python3 -m unittest`: **522 tests OK**. T-012 is in the same tree, and its earlier failure is gone.

**1. MEDIUM: rewrite only when the notes say more than the provisional close.**
- `NOTES_OUTCOME_BODY` (generated step) now also needs at least one "own" note whose reason differs from the provisional `close_reason`. A note is "own" when one of these wrote it:
  - a returning special path (`note_reasons_special`);
  - a per-product refusal (the product is in `product_note_reasons`, which `product_refusal` fills);
  - a record failure (the reason is `failed_reason`, which only the failure branch of `note_next` gives).
- Notes the loop wrote by default (the close reason, or the refused reason as a fallback) only repeat the call state, so the outcome stays as the closing chose it.
- With a correct block nothing changes:
  - all paid by special paths → `paid`;
  - paid, dispute, paid → `no_promise/dispute`;
  - refused, dispute, paid → `no_promise/refused`.
- With a wrong `all_reason` (the reviewer's probe, `refused`), a plain refusal stays `no_promise/refused`.
- **Self-check mirror:**
  - `_Plan.note_reasons` now returns `Notes`, a list that also names which products have an own note (written by a special path, refused, or failed). It still compares like a plain list.
  - `_notes_pair` uses the same condition. A plain list, as a test may give, counts every note as own.
- New tests (`WrongBlockTests`):
  - wrong `all_reason`, one and three products refused → the refusal row, no `notes:` state;
  - the self-check of the wrong-block spec expects the refusal row too;
  - with the right block, one product paid through the special path still closes as `paid`.

**2. LOW: render warning for a reason without a row.**
- `product_notes.notes_outcome_gaps(spec)` lists every note reason (other than `all_reason`) whose pair (`otherwise_outcome`, reason) is not a table row. The render adds it as a warning:
  `notes_outcome: reason X has no row <outcome>/X; a call whose first other note has it keeps the outcome the call state gives`.
- Such a call keeps the provisional pair, as before, but the trace now says so.
- In `spec-brief-b.json` this shows for `hardship` (that fixture has no `no_promise/hardship` row).
- Test: the warning appears exactly once with the block and not without it.
- I made it a render warning, not a self-check failure. It can be correct for a brief to have no row for a reason, so it should not count as a failure or trigger a repair.

**3. LOW: a note counts once it is sent.**
- `note_reasons_sent` stores the reason when `note_next` sends the note, before the result is known. A note that fails twice (given up) still counts for the outcome.
- The outcome follows what happened with each product, not whether the note call succeeded. It is never worse than the default row.
- Accepted as is.

**4. "All products handled by special paths still need one more customer turn": how big it is.**
- After the last product is noted by a returning special path, the call goes back (`__previous__`) to `negotiate` with nothing left to discuss. The call closes only on the customer's next turn: a refusal or end value goes to `product_refusal`, then `closing`, then the note loop, `notes_outcome` and `paid`.
- **So it costs one extra agent turn.**
- **Real risk: a hangup at that moment.** If the customer hangs up instead of answering, the end-of-call close writes the provisional outcome and does not derive it from the notes.
  - Measured offline on `spec-brief-b`: all three products paid, then a hangup → `close_call_on_hangup` sends `no_promise/refused`; the brief wants `paid`.
  - The same happens on the turn limit.
- **Exposure:** no public case has this shape. PUB-11/12/13 are promise cases, and PUB-08 ("already paid") is Brief A with one product and a closing special path, which this does not touch. A hidden A+B case like "every product already paid" or "dispute plus paid" would depend on the customer answering once more.
- **Not changed now.** Two possible fixes later:
  - (a) when every product is handled and nothing was accepted, go to the closing directly from the special path's done step (`NOTED_BODY`, claude-dev2);
  - (b) let the hangup hook use the same note reasons. Notes are not written there, so the rule would read only the special notes.

No Freya, no model call, no commit, no env.sh.
