# T-017: outcome from returning special paths' notes (no outcome_from_notes block)

No Freya, no model call, no commit, no env.sh. Timebox: 15 minutes.

## Problem

In the rehearsal spec (`traces/rehearsal-clean.spec.json`), three returning special paths write a note with the note tool:
- `payment_reported` → `resolved_elsewhere`
- `disputed` → `no_commitment` / `dispute`
- `vulnerability_declined` → `no_commitment` / `vulnerability`

The spec has no `outcome_from_notes` block. So a single-product paid, dispute or vulnerability call closed on the default refusal row, and the ledger failed.

The self-check reported it as `reach_outcomes[1,6,7]` (BUILDER, "only a returning path names it").

## Fix (generic, no brief value)

**`spec.special_note_pairs(spec)`** maps each note reason to its row. It applies only when there is a note rule and no `outcome_from_notes` block. The map takes the returning paths that use the note tool: their note reason (`tool_args[reason_field]`) → the path's `(outcome, reason)`. A reason is left out when:
- two paths give it different rows, or
- its pair is not a table row, or
- its outcome is in `skip_outcomes`.

**The `notes_outcome` step** (T-011 code, `offer_check.SPECIAL_NOTES_OUTCOME_BODY`) is rendered only when this map is not empty. It changes the close only when all of these hold:
- no promise was recorded;
- the close is not a closing special path or a failed special tool;
- the outcome is not skipped;
- **every** product has a note from a returning special path, and they all name the same row.

Then the call closes on that row, with that row's sentence (the failure sentence is kept after a failed record, as in T-011). In every other case today's behaviour stays.

**Recording the special note:** the special path's done step already records its note reason (T-011 `NOTED_REASON_BODY`). It is now also rendered in this mode. The T-011 "sent reasons" state is not rendered without the block.

**Reach and self-check:**
- `workflow.unreachable_outcomes` counts these pairs as reached.
- The self-check mirrors the step (`_special_notes_pair`). `Notes.special` names the products a returning path noted.

**With the block (T-011) nothing changes.** Brief A (no notes) renders identically: the pin test passes unchanged. For Brief B, the config key order is kept.

## Results

- **Rehearsal spec** rendered with its own OpenAPI: self-check 0 failures (before: 3 `reach_outcomes`), and `unreachable_outcomes` is empty.
- **The recorded A+B extractions without the block** (`brief-ab-extracted-tagged`, `-v2`) now reach the paid and dispute rows. Their known gaps `reach_outcomes[1,7]` are removed from `KNOWN`. The oldest recording has no note rule and keeps its gap.

## Tests

`python3 -m unittest`: **548 OK**.

**New: `tests/test_special_notes_outcome.py`** (v2 recording, no block):
- one product disputed → dispute row;
- two products both paid → paid row;
- mixed (paid + dispute) → default row unchanged;
- one product refused by the customer + one disputed → default row unchanged;
- the step is rendered;
- the full self-check passes.

**Updated to the new behaviour:**
- `test_notes_outcome.RenderTests`: without the block, the T-017 step is rendered and the T-011 state is not; with no returning note path, nothing is rendered.
- `test_outcome_reach`: rows are reached; the warning still appears when the paths' note has no reason.
- `test_product_notes` structure test.
- `test_selfcheck` `KNOWN`.

## Notes

- **Risk:** this rule is an inference. When the documents give no rule, "every product noted by the same special path → its row" is the only reading under which these rows can be reached at all. A brief that wants the refusal row in that case would now fail; none we know of does.
- **Mixed cases** (for example paid + dispute without a block) keep the default row. A brief that wants "first in account order" there needs the `outcome_from_notes` block, which the extraction asks for.
- **Not verified:** the rehearsal brief's own wording for mixed cases (rules 31–33, 43–44). The timebox did not allow it.
