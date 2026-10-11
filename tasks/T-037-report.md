# T-037 report: identity answers in pieces, PUB-06, and the second-goodbye decision

**Owner:** claude-dev2.
**Not done:** no Freya request, no commit, no env.sh. Generic: no brief value.
**`python3 -m unittest`:** 659 tests, OK. The Brief A pin is re-pinned to `04f40fd7…`.
**Closed early:** the CTO asked me to close this task within 10 minutes. The parts I did not finish are listed under "Open".

## 1. Identity loops when answers come in pieces (F-099)

**Finding from the records:**
- **PUB-03 (`9da14484`) and PUB-05 (`734a09de`):** `verify_identity` was never called. The customer gave the answer in two parts ("12 July", then "1991"). The model answered each part with "I need the full date, including the year" and asked for the whole answer again.
  - `wrong_answers_left` never changed, so the step had no exit.
  - PUB-03 ended when the customer said goodbye: `declined`.
  - PUB-05 hit the 30-turn limit, and that limit closed with the negotiation-stage row `no_promise/refused`.
- **PUB-06 (`aab20006`):** the model did put "seventeenth of May" and "nineteen eighty six" together, so the model's behaviour varies between runs.

**Fix:**
- **Identity prompt (`IDENTITY_TASK_TEMPLATE`):** the parts are put together, the agent asks only for the missing part, and it calls the tool once the answer is whole. It never calls the tool with a part and never asks for the whole answer again.
- **Identity turn bound:** `max_node_turns` = 6 per question (12 for Brief A).
  - When the bound is reached, the new step `identity_turn_limit` writes the state the end-of-call hook gives before identity passed (`hangup_unverified`), then the closing chain runs.
  - The bank's attempts counter still closes first.

## 2. PUB-06 pieces: no promise, transferred to restructuring (F-100)

**Root cause (from the record):** the task's guess was close but not exact.
1. **"Yes, I can do that" to the proposed minimum of 637.50 booked the full amount 2125.10.**
   - The amount field was empty.
   - The proposed-amount kind was not extracted on that turn, so the code used the default, full.
2. **The read-back was corrected, and the fixed revise line asked "Which date or amount would you like instead?"** That is an amount question, which the brief forbids.
3. **"six hundred thirty seven" was not read as a number** (the extraction failed at c=0.53), and only `offer_amount_kind=minimum` came through.
   - No route of the revise step took an amount kind alone.
   - So the restructuring intent took the turn, and the call ended as a transfer.

**Fix:**
- **Amount field:** on a plain yes, it copies the amount the agent proposed (the same rule the date field already has).
- **`REVISE_ASK_LINE`:** now "Of course. What would you like to change?"
- **Routes:** `revise_ask` sends an amount kind alone to `check_offer`. The read-back's T-038 route does the same (CTO approved).
- **`CHECK_BODY`:** a turn with only an amount or an amount kind keeps the date of that product's accepted offer.

## 3. Second goodbye: record nothing (CTO decision; F-096 updated)

- **`goodbye_code`:** the read-back is said once for each read-back text. The goodbye after it closes by stage. There is no `record` route any more.
- **`unconfirmed_note_reason(spec)`:** the reason used for the product with the unconfirmed offer, in this order:
  - the spec's neutral note reason (not refused or failed, and not used by any outcome row or special path);
  - otherwise the hang-up row's reason, if it is not refused or failed;
  - otherwise none.
  - With a reason, it goes into the per-product reasons. With none, the product goes into the new `note_skip_numbers`, and the note loop writes no note for it.
  - In the current fixtures no neutral reason exists, so the unconfirmed product gets no note.
- **Self-check:** `goodbye_at_readback` and `goodbye_readback_then_goodbye` now expect no promise, the hang-up state, and no refused note. `accepted_refusal_notes` stays on for every scenario.
- **T-031 tests updated:** read-back once, then close; no record route; the v19 mutation (a refused note) is still caught.

## T-038 blocks (CTO: I now own them)

The reviewer's partial T-038 edits in `workflow.py` and `offer_check.py` stay, because the tests are green:
- refusals keep the date route from taking the turn;
- the read-back sends new terms straight to the check;
- with no open product, the only accepted product is used.

Two test expectations follow the new route order: `test_multi_step` and `test_offer_date_only`.

## Tests

- **New `tests/test_t037_pieces_goodbye.py` (5 tests):**
  - the identity bound and its close state;
  - the revise line asks no amount, and an amount kind alone routes to the check;
  - the unconfirmed goodbye with no neutral reason (no note);
  - the unconfirmed goodbye with a neutral reason.
- **Changed:** `tests/test_t031_product_words.py`, `tests/test_multi_step.py`, `tests/test_offer_date_only.py`, the pin.

## Open (not finished in the time box)

- **Self-check play of a half answer followed by the rest at identity:** the model joins the parts, so the simulator cannot show it; only the prompt line and the bound are tested.
- **A play of the turn bound itself:** only the static check is done.
- **A self-check scenario for PUB-06** (persuasion to the minimum, a plain yes, an amount-only revision): not written.
- **Other steps:** the generic 30-turn limit there still closes with the negotiation row before identity, for example at the opening.
- **Live checks (with approval):** PUB-03, PUB-05 and PUB-06 with `--style pieces`, and the double goodbye on PUB-12.
