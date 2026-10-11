# T-011 review (claude-dev, closing outcome derived from product notes)

**Reviewer:** claude-reviewer · **Scope (T-011 parts only):** `closing.product_notes.outcome_from_notes` in `builder/spec.py`, extraction (`extract.py` `_check_notes_outcome`, `drop_optional`, `_check_reach`; `prompts.py`), render (`offer_check.py` `NOTES_OUTCOME_BODY`, `NOTE_SENT_BODY`, `NOTED_REASON_BODY`; `product_notes.py`; `workflow.py`), `selfcheck._notes_pair`, `tests/test_notes_outcome.py`, fixture `spec-brief-b.json`.
**Method:** offline. Read the diff; `python3 -m unittest`: **518 OK** (21 s; the earlier T-012 failure is gone). Compared renders of the HEAD `builder/` (exported with `git archive`, not checked out) with the working tree; played my own scenarios on `spec-brief-b` with right and wrong blocks. Scratchpad only; no Freya, no model, no env, no edits (only this file).

## Decision: **düzeltme gerekli** (one MEDIUM: a valid but wrong block can overwrite the outcome of ordinary calls, and the self-check cannot see it; everything else is right)

## What is right

- **Single-product / no-block renders are byte-identical.** I rendered 23 specs (all `traces/*.spec.json`, all fixtures and recorded extractions, with `outcome_from_notes` removed where present) with the HEAD builder and the working tree: **0 differences** (3 `*-changed` specs need the changed OpenAPI and fail the same way in both). The new variables, the `notes_outcome` step and the appended snippets exist only when the block exists.
- **No brief value in `builder/`:** grep for the outcome and reason words of the practice briefs finds none; the prompt text is neutral; the leak test is green. The pairs come from the spec.
- **Missing or invalid block is safe.** `parse_spec` rejects an invalid block (`SpecError`), and extraction treats it as its own optional block `notes_outcome`: errors go to repair first, in the last round only the sub-block is dropped with a warning; the note rule stays. `null` removes the key. Reach checks (`_check_reach`, `unreachable_outcomes`) count the derivable pairs.
- **Code is defensive:** the step is wrapped in `try/except`, does nothing unless a promise count and recorded numbers are both empty, the provisional outcome is not in `skip_outcomes`, the provisional state is not a closing special path or `special_tool_failed`, every product has a known reason, and the derived pair is a table row. After `promise_failed`/`account_failed` the failure sentence is kept and only the pair follows. The ordering is right: `closing` (provisional) → note loop → `notes_outcome` → `closing_say`; the note loop's own code is untouched.
- **Derived outcome, Brief B fixture:** all paid → `paid` (sentence = the row's, no extra note written); paid/dispute/paid → `no_promise/dispute`; refused/dispute/paid → `no_promise/refused` (first other note in account order); a recorded promise keeps the promise row (`multi_refuse_one`); a pair that is not a table row (for example a reason with no row) leaves the provisional pair. The full self-check of the three A+B specs passes, so the risk-5 gap is closed.

## Findings

### 1. MEDIUM — a wrong (but valid) block rewrites ordinary calls, and the self-check agrees with it

The check validates only that the reasons and pairs exist in the table and that the source excerpt is in the documents; it cannot tell whether `all_reason` is the *right* reason. The derived pair also fires on notes the loop wrote **by default** (the close reason), not only on notes the customer caused. Probe on `spec-brief-b` with `all_reason = "refused"` (everything else as in the fixture), one product, a plain refusal:

- generated workflow closes the call as **`paid`** (`close_resolved_state = notes:paid`, `note_reasons_sent = {"1":"refused"}`, `note_reasons_special` empty) and the bank gets `paid`, although the customer refused;
- the self-check reports **no failure**, because its expected ledger (`_notes_pair`) is derived from the same block.

Wrong `otherwise_outcome` or wrong `all_outcome` are caught by the reach check (a row becomes unreachable), a wrong `all_reason` is not. A block of this shape would damage the most common path (a refusal), and an honesty failure is a policy failure.
**Fix (one small guard, general):** rewrite the outcome only when the notes carry **information beyond the provisional close**: at least one product's reason came from a returning special path (`note_reasons_special` non-empty) or from a per-product refusal/failure note, i.e. skip the rewrite when every reason equals the provisional `close_reason` (the derivation would then only repeat, or contradict, what the call state already says). With a correct block nothing changes (the derived pair equals the provisional one in those cases); with a wrong `all_reason` the refusal case stays `no_promise/refused`. Mirror the same condition in `_notes_pair`, and add a test with the wrong `all_reason` that must still close as the refusal row.

### 2. LOW — a derived reason without a table row falls back silently

If the first other note has a reason with no row for `otherwise_outcome` (in the fixture, a `hardship` note while the table has only `dispute`, `refused`, `service_error` under that outcome), the pair stays the provisional one. That is safe, but the brief's rule ("the reason of the first other note") is then not applied and nothing says so. Add a trace/self-check warning (`notes_outcome: reason X has no row`) at render time, from `notes_outcome_pairs` against the table.

### 3. LOW — notes counted as sent even if the note call fails

`NOTE_SENT_BODY` stores the reason when `note_next` sends the note, before its result is known; a note that fails twice (given up) still counts. The derived outcome follows the customer's situation, not the ledger notes, so this is acceptable, but say it in the report; the outcome is never worse than the default row.

### 4. LOW — known limits (the report lists them; agreed)

Hangup hook (`close_call_on_hangup`) does not derive; a closing special path that writes a note is not tracked; when every product is handled by special paths the flow still needs one more customer turn (proposal for claude-dev2: close directly). The brief's rule text stays in `closing.rules` (prompt tokens; an `enforced_by` tag would drop it — proposal only).

## Answers to the CTO's questions

1. **Single-product briefs byte-identical?** Yes (23 specs, 0 diffs).
2. **No brief value in `builder/`?** Yes.
3. **Safe when wrong or missing?** Missing or invalid: yes (dropped, repaired, rest of the note rule stays). **Valid but wrong `all_reason`: no** (finding 1).
4. **Derived outcome correct?** All paid, one dispute, mixed, and a promise present: yes (tests and my reading of the code). The condition "promise present keeps the promise row" is by count and recorded numbers, both checked.

## Live check (CTO, with approval)

After finding 1: fresh A+B extraction (the trace should show the block, no `unreachable_outcome`, `self_check_summary … builder=0`), then two chats on the A+B agent: every product already paid (expect `paid`) and one dispute among paid products (expect `no_promise/dispute`), plus a plain refusal of one product (expect `no_promise/refused`, unchanged).


---

## Re-review (Fix: wrong block, render warning)

**Method:** offline. Read the "Fix (review T-011)" section, the new `NOTES_OUTCOME_BODY` and `_notes_pair`; `python3 -m unittest`: **522 OK** (22 s). Re-ran my probes on `spec-brief-b` with the right block and two wrong blocks, 1 and 3 products; re-rendered the 23 specs against HEAD. Scratchpad only; no Freya, no model, no env, no edits.

### Decision: **merge edilebilir** (one LOW note; one exposure to decide, not a defect of this fix)

### Fix 1 (MEDIUM) — closed, in both places

The generated step now needs at least one **own** note whose reason differs from the provisional `close_reason`. Own = written by a returning special path, by a per-product refusal, or by the record-failure branch. Notes the loop wrote by default only repeat the call state and no longer trigger a rewrite. `_notes_pair` applies the same condition (`own` from the `Notes` list; a plain list counts every note as own).

| Block | Plain refusal, 1 product | Plain refusal, 3 products | paid×3 | paid/dispute/paid | dispute×3 | Self-check |
|---|---|---|---|---|---|---|
| correct | `no_promise/refused` | `no_promise/refused` | **`paid`** | **`no_promise/dispute`** | `no_promise/dispute` | no failure |
| wrong `all_reason=refused` (my earlier probe) | **`no_promise/refused`** (was `paid`) | `no_promise/refused` | `no_promise/refused` | `no_promise/refused` | `no_promise/dispute` | `reach_outcomes[1]` fails (BUILDER) |
| wrong `all_reason=dispute` | `no_promise/refused` | `no_promise/refused` | `no_promise/refused` | `no_promise/refused` | `paid` | `reach_outcomes[3]` fails (BUILDER) |

- The correct block gives exactly what it gave before (paid, dispute, first-other-in-account-order; a single product noted paid by its special path still closes as `paid`).
- The ordinary refusal can no longer be turned into another row by a wrong `all_reason`. The one remaining effect of a wrong block is on calls where the customer *explicitly* gave that reason through a special path (last column of the third row), which is the block doing what it says.
- The self-check mirror agrees with the code in all rows above and, with a wrong block, now **shows** it: the row that becomes unreachable is reported (BUILDER, no repair). That is useful as a trace signal; it does not stop the build.
- Single-product / no-block renders: still **0 differences** against HEAD on the 23 specs. No brief word added to `builder/`.

### Fix 2 (LOW) — closed
`notes_outcome_gaps(spec)` gives one render warning per reason with no table row: for `spec-brief-b` exactly `notes_outcome: reason hardship has no row no_promise/hardship; a call whose first other note has it keeps the outcome the call state gives`. A render warning (no repair, no failure) is the right level, since a brief may legitimately have no row for a reason.

### Fix 3 (LOW) — accepted as stated.

### LOW note

- The condition "some own note differs from the close reason" compares with the *provisional* reason, which for most calls is the refusal reason. If a brief's provisional reason for the call state is the same word as an own note reason (a refused product, with the rule's `all_reason` also meaning refused) the rewrite is skipped, which is the safe side. No change needed; just remember it when reading a trace that shows no `notes:` state although the notes look informative.

### Exposure to decide (report item 4, not a defect of this fix)

After the last product is noted by a returning special path, the call returns to `negotiate` and closes only on the customer's next turn. If the customer **hangs up instead** (or the turn limit hits), the end-of-call hook writes the provisional outcome and does not derive it from the notes: all three paid, then hang-up → `no_promise/refused`, while the brief wants `paid`. I agree with the report that no public case has this shape (PUB-11/12/13 are promise cases; PUB-08 is Brief A) and that a hidden A+B case "every product already paid" depends on one more customer answer. My view: fix (a), going to the closing directly from the special path's done step when every product is handled and nothing was accepted, is the better one: it also removes an agent turn the customer does not need (an extra "anything else?" after "already paid" reads badly), and it is local (`NOTED_BODY` plus one transition). Fix (b) would duplicate the rule in the hook and cannot write notes. Needs an owner (claude-dev2 owns `NOTED_BODY`) and a test: three products paid by special paths close without a further customer turn.

### Live check (CTO, with approval, unchanged)
Fresh A+B extraction (block present, no `unreachable_outcome`, `builder=0`), then chats on the A+B agent: all products already paid (`paid`), one dispute among paid (`no_promise/dispute`), a plain refusal (`no_promise/refused`).
