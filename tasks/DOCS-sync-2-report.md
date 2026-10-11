# DOCS-sync-2 report: three docs aligned with the code since 53efa1a

**Owner:** claude (second developer) · **Scope:** `docs/ARCHITECTURE.md`, `docs/FREYA-INTEGRATION.md`, `docs/EVALUATION-AND-TESTING.md`.
**Not done:** no code change, no Freya request, no commit, no env.sh. The F-061/F-062 part (claude-dev's per-product refusal and note loop) is not described; each doc has a marked place for it.

## How the facts were checked

- **Graph and steps:** I rendered `tests/fixtures/spec-brief-a.json` in the current working tree (b2ebfa8 + F-063 + claude-dev's work in progress) and listed every step with its type, passthrough flag, entry (`tts`/`silent`/`llm`), tools, pre-actions and targets. The skeleton block was written from that list.
- **Code read:**
  - `callback.py`;
  - `record_loop.py`;
  - in `offer_check.py`: `AMOUNT_NONE_VALUE = -1.0`, `parse_amount` (a negative number is never an amount), the `calendar_text` writes;
  - in `workflow.py`: `_closing_code` (`FIRST_LINES`, the `own_row` rule), `_special_nodes`, `_model_tool_task`, `_confirmation_progress_code`;
  - in `spec.py`: the record-value check.
- **Tests:** `python3 -m unittest` gave 370 tests, OK. One earlier run showed a single error while claude-dev was editing; the rerun was clean.

## Changes

**`docs/ARCHITECTURE.md`**
- The skeleton block now lists:
  - `third_party` without a tool, plus `callback_check`, `third_party_ask` and `callback_book` (F-055);
  - `calendar_text` in `offer_setup`, and `negotiate` using only those dates (F-054);
  - `offer_say` and `revise_ask` as speaking twins of `negotiate` (F-053);
  - `confirm_record` with no tool, then `record_next`, `record_promise` and `confirmation_progress` (F-063);
  - `closing_say` as the only spoken step of the closing turn (F-056);
  - closing special paths as silent until `closing_say`;
  - a placeholder line `[product notes]` for F-061/062.
- New paragraph **"Who speaks when"**:
  - a returning path speaks on entry; a closing path is silent;
  - `closing` puts the path line before the row sentence, once, and only on the ok state;
  - fallback lines for `special_tool_failed` and `promise_failed` (`FIRST_LINES`), including the case of a row that became the generic goodbye (F-063 review fix 2);
  - why one message per turn matters (F-056, F-057).
- Owner table: callback, product choice and closing text are owned by code.
- Components:
  - `offer_check.py` (calendar, `offer_message`, the enum `none` and amount `-1.0` resets, F-052/F-060);
  - new rows for `callback.py` and `record_loop.py`;
  - a placeholder row for `product_notes.py`.

**`docs/FREYA-INTEGRATION.md`**
- "What the renderer sends":
  - values that code fills: the callback date and time, and the promise's product number through a hook prefix;
  - where `tts` may appear (conversation entries and `closing_say`), never on an `api_request` step, and one spoken message per closing turn.
- Retries:
  - `schedule_callback` in `callback_book` and `create_promise` in `record_promise` both have `maxRetries 0`;
  - the per-product retry goes through `record_next`;
  - the first product whose attempts are used up stops the loop (F-063 decision);
  - a failed callback booking closes as `callback_failed`.
- Platform behaviour:
  - a typed write that does not fit is rejected and the old value stays (F-052/F-060);
  - the version 13 post-goodbye branch with a second refused `close_call` (F-056/F-057);
  - F-058 marked `[TO-CONFIRM]`.
- New subsection **"Open live checks `[TO-CONFIRM]`"**: callback booking (also day and time in two messages), `offer_say` and the calendar, a closing special path (silent global entry, transfer failure, silent model-filled tool step), routing on the extracted yes in `confirm_record`, the long record-loop chain (PUB-11), F-057 and F-058.

**`docs/EVALUATION-AND-TESTING.md`**
- L1:
  - test count 370 (it was 245);
  - new suite rows: `test_callback`, `test_offer_date_only` / `test_offer_amount_reset`, `test_offer_speech`, `test_closing_speech`, `test_record_loop`, `test_multi_ready`;
  - a placeholder row for `test_product_notes` (F-061/062).
- Results log:
  - a version 13 row (PUB-07 ledger pass with a judge risk, PUB-02 fail, PUB-09 ledger pass with a doubled line and a second `close_call`), with the findings and "fixed offline since, retest pending";
  - a note that `ledger.ok: true` is the API status, not a pass.

## Not changed / notes

- `docs/PROMPTS.md` and `docs/UAT-FINDINGS.md` were not edited by this task (their diffs come from the code tasks).
- The ARCHITECTURE "Pipeline" and "Core design idea" sections still cite commit d5f6af1 and the version 12 evidence. The pipeline shape has not changed, and no new scored run exists, so I left them as they are.
- When F-061/062 is documented, fill the three placeholders:
  - ARCHITECTURE skeleton `[product notes]` and the `product_notes.py` row;
  - the EVALUATION `test_product_notes.py` row;
  - FREYA-INTEGRATION has no placeholder; add the `add_note` tool's retries there.

## Fix (review `reviews/DOCS-sync-2-review.md`, findings 1–7)

1. **EVALUATION results table:** the blank line before the version 13 row was removed, so the row is part of the table again. The `ledger.ok` note stays after the table.
2. **ARCHITECTURE "Who speaks when":** a return path has three shapes:
   - without a tool, it speaks on entry;
   - with an engine tool, a code step speaks **before** the tool. This is marked as a known limit (F-059 is still open for this shape; no current spec has it);
   - with a model-filled tool, the line is said after ok, by the prompt.
3. **"One spoken message":** this now holds "by construction" for no-tool and engine-tool closing paths. For a model-filled closing tool it is a prompt rule `[TO-CONFIRM]`.
4. **Stale lines:**
   - ARCHITECTURE "Evidence…" now lists the versions 5/10/11/12/13 results, with F-051 "fixed in code since" and the version 13 ledger results.
   - The version 12 row in EVALUATION no longer says "F-051 (open)"; it notes the fix commits (657e6a6, 12d9226) and the version 13 ledger pass.
   - `docs/UAT-FINDINGS.md` F-051 status: "fixed offline (657e6a6, 12d9226) … PUB-07 passed the ledger on version 13; retest of the judge risks pending".
   - Test count 373.
5. **FREYA-INTEGRATION tts list:** added "the code entry of a returning special path with an engine tool (none in the current specs)". Return paths without a tool are now named as such.
6. **F-057 mechanism:** the observed sequence (version 13, PUB-09/PUB-02) is listed as observed: the turn ended at the first message, a branch resume, old variables, the agent spoke again, a second `close_call` at hang-up. Why the state is lost, and whether the judge's simulation can send a message after the goodbye, are labelled `[TO-CONFIRM, platform]`.
7. **`third_party` fallback:** the skeleton and the `callback.py` row now say that a callback tool without recognisable date and time fields keeps the model-filled tool and writes a warning (`callback_nodes` returns None).

**Checks:** `git diff --check` clean, `python3 -m unittest` OK (373). Files: the three docs and the F-051 status line in `docs/UAT-FINDINGS.md`. No code change, no Freya request, no commit, no env.sh.
