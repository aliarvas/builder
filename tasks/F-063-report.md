# F-063 report: one read-back, one confirmation, then code records every promise

**Owner:** claude (second developer) · **Finding:** `docs/UAT-FINDINGS.md` F-063 (MULTI-READY finding 5).
**Not done:** no Freya request, no commit, no env.sh. `offer_check.py` was not touched. I re-read `workflow.py` before each edit. At the start of the task claude-dev had no change in `workflow.py`; my edits there are limited to the record part (see "Coordination").

## Problem

`confirm_record` was a conversation step with the promise tool, and the loop went `confirm_record → confirmation_progress → confirm_record` once per product. On every entry the task said "read these back and ask for a clear confirmation". With three products (PUB-11), the model could read back and ask again before the 2nd and 3rd promise. The case expects one read-back and one confirmation.

## New flow

```
confirm_record (conversation, no tool): one read-back, one question
  ├─ revise value                → revise_ask (unchanged)
  └─ "record" value (clear yes)  → record_next (code)
                                     ├─ nothing left → closing
                                     └─ record_promise (api_request, silent, create_promise)
                                          → confirmation_progress (code) → record_next | closing
```

- **`record_next`** (new code step, `builder/record_loop.py`):
  - From `offers_accepted`, it picks the lowest product number that is not in `promises_recorded_numbers` and writes it to `promise_record_number`.
  - It clears `promise_result_ok`, so a call that returns no mapped result (an HTTP error) counts as a failure.
  - The product is chosen in code; the model never names it.
- **`record_promise`** (new silent api step):
  - The same promise tool. The number field's default is `{{promise_record_number}}`, and the existing hook fills product id, date and amount from the checked offer.
  - `maxRetries 0`. The result is mapped at node level (`data.ok → promise_result_ok`).
  - F-050: no tts.
  - It uses a variable name of its own, so a special path whose tool the model fills (`{{<product number field>}}`) never picks up this value.
- **`confirmation_progress`** keeps the existing rule:
  - ok → counted, and the number is added to `promises_recorded_numbers`.
  - failure → per-product attempt +1; `exhausted` when it reaches `max_attempts_per_product`.
  - `complete` or `exhausted` → `closing`; otherwise → `record_next`, which takes the same product again on a retry and the next one after ok.
  - The number is read from `promise_record_number`; `create_promise_args` is no longer read.
- **"Record" values:** every confirmation intent that is not a revise value. The extraction prompt gives each intent the route record or change, so these values mean a clear yes. All 9 existing specs have exactly one such value.
- **`confirm_record` prompt** (`CONFIRM_TASK_TEMPLATE`): "Read all of these back once … and ask for one clear confirmation. Never say the product number in square brackets. After a clear yes, say nothing more: the program records the promises and the closing tells the customer. Never say a promise is recorded."
  - In the confirm turn, routing on the extraction comes before the model speaks, as for the opening.
  - The only spoken message in that turn is the one from `closing_say`.

## Honesty

- Only the closing speaks after the confirmation, and it chooses its sentence from the state (as before): `promise_recorded`, or `promise_failed` → the spec's row.
- **New (a gap the old model loop had too):** a product can fail while another one is recorded. The recorded-promise row then wins the outcome (`promise`), and its sentence ("…confirming this promise…") would hide the failure. In that case the closing now first says **"I am sorry, I could not record every promise."** (new prompt `PROMISE_NOT_ALL_RECORDED_SAY`).
  - It is added only when the chosen row is not the spec's own row for `promise_failed`.
  - A single product that fails twice gets only the spec's sentence, for example Brief A "I am sorry, I could not record your promise…".
- The same `FIRST_LINES` mechanism as F-059 is used. Each row is now (state, line, always); a row that is not `always` is a fallback.

## Files

| File | Change |
|---|---|
| `builder/record_loop.py` (new) | `record_values`, `record_next_code`, `record_promise_node`, and the variable names. |
| `builder/workflow.py` | `confirm_record` has no tool and routes to `record_next`; the `record_next` and `record_promise` nodes; `confirmation_progress` (number from the loop, recorded list, next/retry → `record_next`); `_closing_code` (`FIRST_LINES` with the `always` flag, the `promise_failed` fallback line); the `used` names. |
| `builder/prompts.py`, `docs/PROMPTS.md` | `CONFIRM_TASK_TEMPLATE` reworded; new `PROMISE_NOT_ALL_RECORDED_SAY`; the doc was regenerated. |
| `docs/UAT-FINDINGS.md` | F-063 status only. |
| `tests/test_record_loop.py` (new, 6 tests) | See below. |
| `tests/test_multi_step.py` | 5 tests that described the old shape now test the new one: tools scoped (`create_promise` only in `record_promise`), hook values, number variable, `confirmation_progress` (recorded list; an empty result is a failure), the `promise_failed` scenario. |
| `tests/test_multi_ready.py` (claude-dev's) | The simulator's `record_all` now gives one yes and runs the code loop (code steps plus the api step, with the bank answers as a parameter) instead of the model's tool calls. `Session` keeps `spec` and `calls`. The hook test takes the tool from `record_promise`. The test assertions are unchanged. |
| `tests/test_spoken_output.py` | The confirm prompt assertion follows the new wording. |

## Tests

- `tests/test_record_loop.py`:
  1. **PUB-11, all 4 A+B specs:** after the yes, `confirm_record` routes once. Only `record_next`, `record_promise` and `confirmation_progress` run; there are exactly 3 `create_promise` calls; the ledger is as expected (p1 220, p2 640, p3 75 on 16 October); the outcome is `promise`; there is no failure line.
  2. **One failed call:** retried once for the same product; 4 calls, 3 promises.
  3. **Product 2 fails twice:** the loop stops (p3 is not tried), `promise_failed`, the outcome is `promise`, and the sentence starts with the failure line.
  4. **Single product (Brief A fixture, PUB-01) fails twice:** `no_promise/service_error`, only the spec's sentence, no "confirming".
  5. **Revise:** confirm_record → `revise_ask` → new date → confirm_record → record; p1 is recorded on the new date.
  6. **Graph, 3 fixtures:** confirm_record has no tools; `record_promise` is api and silent with `maxRetries 0`; the loop steps are passthrough with no tts and never return to `confirm_record`; the route into the loop does not use a revise value.
- **Results:** `tests.test_record_loop` 6/6; `tests.test_multi_ready` 7 OK (1 expected failure, F-061, unchanged). Full suite **352/352 OK** (expected failures=1). `git diff --check` clean.

## Coordination (claude-dev, F-061/062)

- In `workflow.py` I changed only:
  - the `confirm_record`, `record_next`, `record_promise` and `confirmation_progress` nodes;
  - `_confirmation_progress_code`;
  - `_closing_code`;
  - the import and `used` lines.
- `negotiate`, `check_offer`, the special paths and `offer_check.py` were not touched.
- For F-061 (`add_note` loop before the close), the same pattern can be used: a picking code step, a silent api step, and a progress step. `exhausted` (`promise_failed`) is the trigger for the `service_error` note. `promises_recorded_numbers` tells which products have a promise.
- `tests/test_multi_ready.py` is claude-dev's file; I changed only `record_all` and the hook test's tool lookup (see Files).

## Open notes

1. **[TO-CONFIRM live]** A long passthrough chain in one turn: with 3 products, `record_next → record_promise → confirmation_progress` runs 3 times, then the closing chain (about 14 steps). The worst case with retries is longer. PUB-01 ran 12 steps in one turn without a problem. Retest PUB-11.
2. **[TO-CONFIRM live]** Routing from `confirm_record` on the extracted confirmation (`min_confidence 0.8`) before the model speaks. Opening and third_party route the same way live. If the extraction is not sure, the step stays and the model asks again, which is safe.
3. Docs: `docs/ARCHITECTURE.md:58-59` ("confirm_record … create_promise") and the `FREYA-INTEGRATION.md:34` retry sentence need the next docs sync. Not my files in this task.
4. MULTI-READY finding 3 (one check turn per product) is unchanged. PUB-11 still needs 3 check turns before the single read-back.

## Fix (review `reviews/F-063-review.md`)

1. **The product number comes from the variable** (MEDIUM).
   - `record_promise`'s tool now has its own pre-hook prefix (`record_number_hook` in `record_loop.py`). It writes `vars['promise_record_number']` into the body's number field, and then the existing promise hook runs (`offer_check.py` was not changed).
   - The body value (`{{promise_record_number}}` template) is now only the fallback, used when the variable is missing.
   - This removes the dependence on the engine substituting text into an integer field.
   - Test `test_hook_reads_the_number_from_the_variable_not_the_template`: with the body field holding the literal template text, empty, or a wrong number, product 2 is recorded with its own id and amount. Without the variable, the body value is used.
2. **Failure line when the row's sentence is only the generic goodbye** (MEDIUM, honesty).
   - In `_closing_code`, a fallback line (not `always`) is skipped only when the chosen row is the state's own row **and** its sentence is not the generic goodbye (`CLOSING_FALLBACK_SAY`). The generic goodbye is what an empty or instruction-style row (F-047) becomes.
   - So for `promise_failed` and `special_tool_failed` with such a row, the builder's failure line is said first, for example "I am sorry, I could not record every promise. Thank you for your time. Goodbye.".
   - A spec row with a real spoken sentence is still said alone.
   - Side effect: a spec row whose real text happens to be exactly "Thank you for your time. Goodbye." also gets the failure line. That is honest, and better than saying nothing.
   - Tests:
     - an instruction-style `service_error` row that also covers `special_tool_failed`, for both states;
     - a spoken row said alone;
     - the extracted A+B spec reproduced by the reviewer, which now starts with the failure line.
3. **Spec rules that name the removed tool** (LOW). `CONFIRM_TASK_TEMPLATE` now says once: "You have no tool here: where a rule below speaks of calling, retrying or checking the promise tool, the program does that after the yes." The rules are not rewritten, since they come from the brief. Test: the sentence appears exactly once and `confirm_record` has no tools.
4. **Spec validation** (LOW). In `builder/spec.py`, `confirmation.intent_values` must contain at least one value that is not in `revise_values`; otherwise `SpecError`. A comment explains why. Test `test_spec_needs_a_record_value`.
5. **Stop at the first exhausted product** (LOW, decision). This is written in the docstrings of `record_loop.py` and `_confirmation_progress_code`:
   - the first product whose attempts are used up ends the loop; later products are not tried;
   - the closing says that not every promise was recorded;
   - a service that failed twice is not called again for the next product in the same call.

   As asked, nothing was added to the docs.

**Results.**
- `tests.test_record_loop`: 12/12 (6 new).
- Full suite: 358 tests, **3 failures, none from F-063**:
  - `test_pub12_promise_then_refusals_reach_the_promise_and_outcome` (tagged, fixture-b);
  - `test_refusal_of_one_product_skips_the_products_after_it`.
  
  All three assert that a refusal goes to `confirm_record`. claude-dev's in-progress F-061/062 (`product_notes.add_product_steps`) now sends the refusal of one product to the next product (`offer_say`), so those tests in `test_multi_ready.py` describe the old behaviour and are claude-dev's to update.
- `git diff --check`: clean.

**Files in this fix:** `builder/record_loop.py`, `builder/workflow.py` (`_closing_code`, the `_confirmation_progress_code` docstring; re-read before each edit), `builder/prompts.py` and `docs/PROMPTS.md` (the confirm sentence), `builder/spec.py` (one check, next to claude-dev's changes), `tests/test_record_loop.py`. No Freya request, no commit, no env.sh.
