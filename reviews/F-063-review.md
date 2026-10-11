# F-063 review — one read-back, one confirmation, code records every promise

**Reviewer:** claude-reviewer · **Scope:** `builder/record_loop.py` (new), the F-063 parts of `workflow.py` (`confirm_record`, `record_next`, `record_promise`, `confirmation_progress`, `_closing_code`), `CONFIRM_TASK_TEMPLATE`, `PROMISE_NOT_ALL_RECORDED_SAY`, `tests/test_record_loop.py`. claude-dev's F-061/062 (`product_notes.py`, `spec.py`, `offer_check.py` notes) not reviewed.
**Method:** offline. I rendered A, A+B, the version 11 extraction and the two A+B extractions; read the five nodes and their routes; drove the real `record_next` / `confirmation_progress` / `closing` code through a loop with synthetic bank answers (all ok, product 2 failing, product 1 failing, fail-then-ok, an empty result), and checked the closing sentence in each case on three specs. `tests.test_record_loop` and `tests.test_multi_ready`: OK. The full suite shows 1 failure, `test_builder_string_literals_do_not_embed_fixture_values` with the literal `'type'`; it comes from `builder/product_notes.py:118` (claude-dev's F-061/062 work in progress), not from F-063. `record_loop.py` has no string literal `"type"` (it uses `dict(type=…)`). No Freya, no model, no edits.

## Decision: **düzeltme gerekli** (two MEDIUM points, both small; the flow, the honesty of partial success, the retry limit and the single-product path are right)

## Findings

### 1. MEDIUM — the product number reaches the tool through an integer field's template default, with no live evidence (`record_loop.py:61-65`)

`record_promise` sets the promise tool's `product_number` (type `integer`) to the default `"{{promise_record_number}}"`. Every platform-baked default seen so far is a string field (`{{customer_id}}`). If the engine does not turn the substituted text into the field value for an integer (or leaves the template text), the hook (`PROMISE_HOOK_BODY`) cannot read a number: `int(str(choice))` fails, `key` is empty, and then it only works when exactly one offer was accepted (`len(accepted) == 1`). With two or three products the body would lack product id, date and amount and **every** promise call would fail: PUB-11 would end `service_error` after two attempts on product 1. The report lists other live checks but not this one.
**Fix (either):** make the record tool's number field a `string` in that copy (the hook already does `str(int(str(choice)))`), or let the hook read `vars['promise_record_number']` directly, falling back to the body value. The second removes the dependence on engine templating for the one value that decides which product is recorded. Add a hook test with the body field left as the literal template text.

### 2. MEDIUM — a failure row written as an instruction loses the failure statement (honesty by omission), because the new fallback line is skipped (`_closing_code`, `FIRST_LINES`)

The new "I am sorry, I could not record every promise." is a fallback (`always = False`), added only when the chosen row is not the spec's own `promise_failed` row. When the spec's own row exists but its sentence is an instruction to the agent, the F-047 spoken-text fallback replaces it with the generic closing, and the line is still skipped. Reproduced with `tests/fixtures/extract/brief-ab-extracted.json` (row text "Say you could not record the promise. Then thank the customer and say goodbye."): with `close_state = promise_failed` the customer hears only "Thank you for your time. Goodbye." The tagged A+B extraction behaves the same (all products failing ends "Thank you for your time. Goodbye."). No success is claimed, but the customer is never told that nothing was recorded, after the model was told to say nothing following the yes. The current version 11 extraction has a spoken row ("I could not record the promise. Thank you, goodbye."), so this shows only with instruction-style rows, but the same mechanism hits `special_tool_failed` and any other failure row.
**Fix:** in `choose`/`_closing_code`, when the row's sentence was replaced by the generic fallback and the state is a failure state (`promise_failed`, `special_tool_failed`), treat it as "not the state's own row" so the builder's failure line is added. Add a test with the instruction-style row.

### 3. LOW — spec rules still tell the model to call the tool

`confirm_record` still carries the spec rule "Read back … and call the tool only after clear confirmation" and "Do not say it was recorded unless the tool succeeds", next to the engine's "No tool call is allowed in this turn." and the new "After a clear yes, say nothing more". The model has no tool; the contradiction can only cause an attempted textual call. The rule placement for this step should drop or reword rules that name the removed tool, or the template should say once that the program records.

### 4. LOW — `record_values` is "everything that is not a revise value" and the spec does not enforce the extraction's two routes

Extraction allows only the routes `record` and `change` and demands at least one of each (`extract.py:571-574`), so extracted specs are safe; all nine specs I listed have one record value, and the A+B ones have two revise values (`wants_change`, `rejects_readback`) and one record value. A hand-written spec (`--spec`) with a neutral third value (say `unclear`) would route that value to recording. Cheap guard: `spec.py` validation that `intent_values − revise_values` is non-empty and a comment/test that it contains only affirmative answers, or an explicit `record_values` field.

### 5. LOW (policy note) — the loop stops at the first exhausted product

With product 2 of 3 failing twice, product 3 is not tried; the sentence says "I could not record every promise", which is true. If the product 3 call would have worked, the ledger would hold more; the choice is defensible under all-or-nothing scoring, but state it as a decision in the spec/docs.

## Verified

- **Flow.** `confirm_record` has no tool and two routes: the revise values → `revise_ask` (unchanged), the record values → `record_next`. `record_next` (silent code) picks the lowest accepted product number not in `promises_recorded_numbers`, clears the result variable (an HTTP error with no mapped answer counts as a failure), routes to `closing` when nothing is left. `record_promise` is a silent api step with the promise tool, `maxRetries 0`, node-level mapping `data.ok → promise_result_ok`, no tts (F-050). `confirmation_progress` counts ok / failure per product; `complete` or `exhausted` → closing, otherwise back to `record_next`, which picks the same product for a retry. Nothing returns to `confirm_record`.
- **Loop driven with the real code** (limit 2 attempts per product, two accepted products):

  | Case | Calls | Progress | Outcome | Closing sentence (start) |
  |---|---|---|---|---|
  | both ok | 2 | complete | promise | the spec's recorded-promise sentence |
  | product 1 ok, product 2 fails twice | 3 | exhausted | **promise** (a recorded one wins) | "I am sorry, I could not record every promise." then the recorded-promise sentence (Brief A, Brief B, tagged A+B) |
  | product 1 fails twice | 2 | exhausted | no_promise / service_error | the spec's own failure sentence only |
  | product 1 fails once, then ok; product 2 ok | 3 | complete | promise | recorded-promise sentence |
  | empty result (HTTP error) twice | 2 | exhausted | no_promise / service_error | failure sentence |

  The loop is bounded by `max_attempts_per_product` per product and by the number of accepted products; nothing can run forever.
- **Honesty.** The model never calls the tool and is told never to say anything was recorded; only `closing_say` speaks after the yes, and its sentence comes from the derived state. Partial success is announced (finding 2 aside). One note: after "I am sorry, I could not record every promise." the recorded row's text may say "confirming this promise" (singular); acceptable, since the first sentence has already said that not everything went through.
- **Revise path.** `revise_ask` → check → `confirm_record` again, and a later yes records the revised values (tested with a revise, `offers_accepted` carries the new date). Recording state starts empty because the loop only begins after the yes.
- **Single-product Brief A (PUB-01/07 shape).** One accepted offer: yes → `record_next` → `record_promise` → `complete` → closing; failing twice gives `no_promise/service_error` with only the spec sentence (tested, fixture A). The hook falls back to the only accepted offer even if the number is not parsed, so this path is the safest one; the multi-product path is where finding 1 matters.
- **F-050, leak.** No tts on any api step; the loop steps are passthrough code and silent api steps. `record_loop.py` holds only framework names (`promise_record_number`, `record_state`, …); no brief values; its code avoids the literal `"type"` on purpose, so the leak test is not triggered by it.
- **Confirm turn risk (open note 2 of the report, agreed).** Routing on the extracted yes happens before the model speaks only if the extraction is confident (`min_confidence 0.8`); otherwise the step stays and asks again (safe). If the model does speak first ("Great, thank you"), the customer hears two messages (the model, then `closing_say`); same residual as F-056, to be checked live on PUB-11.
- **Open note 1 (long passthrough chain)** is fairly labelled: three products give three loop rounds plus the closing chain in one turn; retries lengthen it.

## Live checks

PUB-11 (three products: one read-back, one yes, three `create_promise` calls with the right product ids, one closing message, no call missing the product id fields), PUB-01/07 (single product), a forced `create_promise` failure on product 2.


---

## Re-review (Fix 1–5)

**Method:** offline. I executed the record tool's real pre-hook with eight combinations of variable and body value, ran the generated `closing` code with `promise_failed` and `special_tool_failed` on five specs, and tried the new spec check on a synthetic spec. `tests.test_record_loop`, `tests.test_multi_ready`, `tests.test_closing_speech`: 30 OK. The full suite had no failing test when I ran it a second time (the three `test_pub12_*` / `test_refusal_of_one_product_*` failures the developer reports belong to claude-dev's F-061/062 and had been cleared by then). No Freya, no model, no edits.

### Decision: **merge edilebilir**

- **Fix 1 (product number) — fixed.** `record_promise`'s tool now has a pre-hook prefix that writes `vars['promise_record_number']` into the body's number field before the promise hook runs. With the variable set to 2 or 3 and the body holding the template text, an empty string, a wrong number (1) or the same number, the hook produced the right product's id, date and amount (`p2 / 2026-10-20 / 300.0`, `p3 / 2026-10-21 / 75.0`). With no variable, a body value `"2"` still works. With no variable and the unresolved template text, the body keeps the stray number text and no product fields, so the bank refuses the call and the loop counts a failure: an honest failure, not a wrong promise. This removes the dependence on the engine's integer templating.
- **Fix 2 (failure statement) — fixed.** A fallback line is now skipped only when the chosen row is the state's own row and its sentence is not the generic goodbye. Results: `brief-ab-extracted.json` (instruction-style row): `promise_failed` → "I am sorry, I could not record every promise. Thank you for your time. Goodbye."; `special_tool_failed` → "I am sorry, I could not complete that request right now. Thank you for your time. Goodbye."; the tagged A+B extraction behaves the same. Spoken rows are untouched: Brief A "I am sorry, I could not record this because of a technical problem. …", Brief B "A technical problem stopped the recording. …", version 11 "I could not record the promise. Thank you, goodbye." (no doubled statement). Wording nit: for a single product that failed, "every promise" is slightly broad but true. Note also that when a spec shares one outcome row between states (version 11 uses "I could not record the promise" for a failed transfer too), the sentence comes from the spec; that is the brief's own choice.
- **Fix 3 (spec rules naming the removed tool) — fixed in the cheapest honest way.** `CONFIRM_TASK_TEMPLATE` now says once: "You have no tool here: where a rule below speaks of calling, retrying or checking the promise tool, the program does that after the yes." (present in `PROMPTS.md` line 248). The brief's own rules are not rewritten, which is right for the no-hardcode rule.
- **Fix 4 (spec validation) — fixed for the empty case.** A spec whose confirmation intents are all revise values now fails with "confirmation.intent_values needs a value that is not in revise_values: the clear yes that records the promises". A neutral third value is still accepted and would route to recording; extraction cannot produce one (only the routes `record` and `change` exist), so this remains a hand-written-spec corner. No action needed.
- **Fix 5 (stop at the first exhausted product)** is recorded in the docstrings as a decision; acceptable, as I noted.

The live checks from my first review stand: PUB-11 with three products (right product ids on all three calls), PUB-01/07, and a forced `create_promise` failure on product 2. F-063: fixed offline, retest pending.
