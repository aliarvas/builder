# T-016: unverified refusal expects product notes (self-check, first live A+B build)

No Freya, no model call, no commit, no env.sh.

## Symptom

`traces/brief-a+brief-b.log`: `self_check_summary: scenarios=201 pass=198 fail=3 builder=3`, all from `special_refuses_to_talk_unverified`. The three failures are the same scenario at the three nows (build now plus two extra nows): `notes [], the spec gives [('p1', 'refused')]`.

## Which side is wrong: the self-check

**What the bank expects:**
- Brief A rule 16: `get_account` is called only after both security questions pass. Before identity the call has no product list, so there is no `product_id` to note.
- Brief A rule 1 and rule 10: nothing about the account is disclosed before identity. A note per product would need the products.
- Brief B rule 8 ("for each product without a promise call `add_note`") speaks about the products of the call. Before identity there are none.
- The kit practice case PUB-03 (`not_verified` / `failed`, before the account) expects `notes: []`. The scorer compares notes exactly, so any note there fails the case.

**What the workflow does:**
- It closes as `not_verified` / `declined` and writes no note. The note loop runs over the products read by the account step, and that list is empty before identity.
- This is right.

**Why the self-check expected a note:**
- `_special_scenarios` built the expected notes for a closing path with `notes_for(...)` at every entry step.
- The path's reason `declined` is not a note reason, so it fell back to `refused` for the synthetic product p1.
- claude-dev2's T-012 `_closing_case` already had the right rule. It plays the same path at its other steps and expects no notes at `BEFORE_ACCOUNT` (`opening`, `identity`, `third_party`). That is why `special_refuses_to_talk_unverified_at_opening` passed and the scenario at `identity` did not.
- No fixture had a closing path that starts before negotiation and has no skipped outcome. The fixture's `human_transfer` is listed at identity but is played at negotiate, and `transferred` is skipped anyway. So the tests never saw this case.

## Fix

- `builder/selfcheck.py`, `_special_scenarios`: a closing path is now built by `_closing_case`, the same function used for its other steps. The notes rule now has one place: no notes before the account, and the note rule after it.
- The `_tool_failed` variant is unchanged.
- Generic: no brief value.

## Tests

`tests/test_unverified_notes.py` (2 new tests), using `spec-brief-b` plus a test-only closing path (`not_verified` / `declined`):
- **Path at `opening` and `identity`:** the expected notes are `[]`, and the scenario passes on the render. Without the fix this test fails with the live message (checked by stashing the fix).
- **Path only at `negotiate`:** a note per product (`p1` with the refused reason) is still expected and the scenario passes. The note rule after the account is unchanged.

`python3 -m unittest`: **542 tests OK**.

**Check on the live A+B spec** (`traces/brief-a+brief-b.spec.json`, rendered with the current code and the kit OpenAPI): every self-check scenario passes, with 0 failures.

## Note: the submitted file is not the self-check's input

`submission/brief-a+brief-b.workflow.json` is the workflow as Freya returned it after the save. Freya fills platform default fields (`on_enter`, `role_message`, `passthrough` and others) into every node.

Running the self-check directly on that file gives 9 hangup failures ("2 spoken messages in the closing turn"). These come from the platform defaults: on the build's own render, which is what the build checks, the hangup scenarios pass (log and re-run).

This is not a builder fault. If we ever want to self-check the saved copy, the simulator must first read the platform's default fields. I propose no change now.

## UAT (CTO)

Proposed entry: "Self-check expected a product note for a special close before identity; the account is not read there, so the workflow (no note) was right. The self-check now uses one notes rule for closing paths at every step (T-016). Status: fixed offline."
