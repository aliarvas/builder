# T-027: v19 live runs, PUB-07 (wrong date) and PUB-12 (A+B, no promise and an endless goodbye)

Generic, no brief value. No Freya, no model call, no commit, no env.sh. `python3 -m unittest`: **615 OK**.

## PUB-07: promise on 19 October instead of 27 October

Record: `traces/live-runs/user-0aae2951-26b2-4120-b8b2-3b87d8fb0e52.json` (Brief A v19, now 2026-10-14).

**The wrong event (msg 44-52):**
1. The customer answered "Monday the twenty sixth."
2. The extractor wrote `offer_date = 'Monday the twenty sixth'`.
3. `check_offer` read it as **2026-10-19** (verdict `ok`).
4. The read-back said "Monday, 19 October", and the promise was recorded on that date.

The expected flow: 26 October is a holiday → `date_not_business_day` → propose Tuesday 27 → yes.

**Root cause:**
- T-022 turns a day number said in words into digits **only next to a month name**. Here there was a weekday and no month.
- The reader then saw only "monday" and took the next Monday after today.
- The proposed-date path (T-022 c) was not involved: "the week after next" before it correctly gave `missing`, and the proposal of 2 November was not taken.
- Not a regression of T-022: v18 read this phrase the same way. It is a gap T-022 left.

**Fix (`offer_check.PRELUDE.spoken_day_numbers`):**
- A day word right after a weekday name becomes digits too: "monday the twenty sixth" → "monday the 26".
- The existing weekday + day-number search then finds 26 October. The check moves it to 27 October.
- Unchanged:
  - "twenty sixth" alone stays unread;
  - "Friday the thirty second" stays just Friday;
  - "Monday at two" stays Monday.
- The callback reader uses the same function.

**Tests (`tests/test_live_v19.py`):**
- the phrase table;
- the v19 reader as a mutation (gives 19 October);
- **replay** of the recorded extractions (`tests/fixtures/replay/pub-07-extractions.json`, spec `brief-a-live-spec.json`):
  - "the week after next" → `missing`;
  - "Monday the twenty sixth." → `date_not_business_day`, suggested 2026-10-27;
  - a "yes" (not in the recording, because the live call went on differently) and the recorded "Yes, I confirm." → promise p1 540 on 2026-10-27, as the case expects.

**Self-check guard:**
- The spoken-date family has a new form, `weekday_the_word` ("Wednesday the fourteenth"), played at every now.
- With the v19 reader it fails as BUILDER (tested).

**Risk:**
- When the weekday and the day disagree ("Monday the 27th", a Tuesday), the existing search takes the next month in which they agree. That date is usually after the deadline, so the check offers the deadline instead. This is the old behaviour for digits too, and is not changed.

## PUB-12: no promise, notes on all three products, "Thank you for your time" until max duration

**Records:**
- `traces/live-runs/user-1c73c93a-64f1-485f-bff1-05a4596689b1.json` (A+B workflow 8887e79f version 2).
- The addendum names `user-1c73c93a-85f6-…`; that file does not exist, and the message indexes match the 64f1 file.

**Products:** p1 card 510 (16 days late), p2 personal loan 1320 (16 days), p3 car loan 140 (7 days). Persuasion attempts: 2, 2, 1.

### Timeline and the wrong events

| msg | what happened | wrong? |
|---|---|---|
| 38-46 | "I can pay the credit card tomorrow, but I am not paying the personal loan or the car loan." → card `ok` (2026-10-15), "Now let us look at the personal loan …" | the refusals in the same turn were lost (no field for them) |
| 50-60 | "No, I refuse to pay the personal loan." → `product_refusal`: p2 attempt 1 → `negotiate` | ok |
| 61 | model: "I understand. Let's move to your car loan …" | **W1:** the persuasion turn did not know its product (the prompt only gave the count) |
| 62-72 | "No, I am not paying the car loan." (`offer_product_name='car loan'`) → counted as **p2** attempt 2 | **W2:** the refusal step ignored the name and took the first open product |
| 73-85 | model: an improvised read-back "I'll record this"; "Yes, I confirm." → `check_offer` checked the card again → "Now let us look at the personal loan" | the personal loan was asked again (addendum item 4) |
| 86-96 | personal loan refused → p2 ended (its attempts were used up, one of them by the car loan) → car loan line | consequence of W2 |
| 98-108 | car loan refused → p3 attempt 1 (its first) → `negotiate` | consequence of W2 |
| 109 | model: "I have recorded your promise … Thank you for your time." | **W3:** false claim and goodbye (honesty) |
| 110-137 | "Thank you, goodbye." → `negotiation_reply=none` → no route, the step repeats itself | **W4:** no exit for a goodbye |
| 138-229 | `refuses_to_talk` → `confirm_record`; the model never read back; `readback_reply=none` ×30 | **W5:** the read-back was left to the model |
| 229-262 | turn limit → `close_turn_limit` → closing `turn_limit` → no row → default `no_promise/refused` → note loop p1, p2, p3 `refused` → max duration during note 3 → close by the hang-up tool | consequence |

### Fixes

1. **The refusal counts for the product the words name (W2).**
   - Fix: a new `MULTI_REFUSAL_BODY` for specs with several products. The products named in `offer_product_name` (and in the new refused field) are refused, each counted on its own (`refuse_product`). With no name, the refusal goes to the product under discussion.
   - A name wins over a shared word: "personal loan" does not also count the car loan through "loan".
   - Only multi-product specs render it; the others are unchanged.

2. **Refusals in the same turn as an offer.**
   - Fix: a new extraction field `offer_refused_product_name` (`OFFER_REFUSED_PRODUCTS_DESCRIPTION`) next to `offer_product_name`, only when the spec has per-product refusals.
   - `check_offer` counts one refusal for each named open product before the check runs, so the check's progress and next line already know it.
   - "the others" / "the rest" means every other open product.

3. **The persuasion turn names its product (W1).**
   - Fix: the product under discussion is kept in `offer_discussed_number` / `offer_discussed_product`. It is set by the setup, the check and the refusal step.
   - The `negotiate` prompt gets one line (multi only, with persuasion attempts): "A counted attempt is about the {{offer_discussed_product}} only; never move to another product yourself."
   - A date with no product name is checked for that product.

4. **A goodbye has an exit (W4; addendum item 3, generic).**
   - Fix: a global step `customer_ends_call` (`builder/goodbye.py`), intent "The customer only says goodbye or thanks to end the call, with no refusal, no offer and no question."
   - It is active in `negotiate`, `offer_say`, `revise_ask` and `confirm_record`.
   - With accepted offers, the first goodbye goes to the read-back once. Otherwise, or on the second goodbye, it writes `close_state='hangup'` and goes to `closing`, which runs notes, the outcome and close_call.
   - Each step's `special_topic` value names it, as T-023 requires, otherwise the forced choice would hide it. The self-check's `intent_shadow` check caught this during the work.
   - Its exit is rewritten to `GLOBAL_EXIT_CONDITION` by claude-dev2's T-028 post-pass.

5. **The read-back is spoken by code (W5; addendum item 3).**
   - Fix: `check_offer` builds `readback_text` from the checked offers: "I can record a payment of 220 for the credit card ending 2288 on Friday, 16 October, a payment of … and a payment of …. Do you confirm?" (`READBACK_LINE`, `READBACK_ITEM`).
   - `confirm_record` says it on entry (`on_enter` tts). Its prompt begins with "The program has just said this read-back …; do not read it again unless the customer asks".
   - This applies to all specs, so the Brief A render moves (see the pin note).

### Answers to the addendum

**1. The finished product list goes back to negotiate (msg 107).**
- Not every product was handled at msg 107. Because of W2, the car loan's first refusal had been counted against the personal loan, so the car loan still had its one persuasion attempt, and `persuade` → `negotiate` was right for the state the code had.
- With fix 1, the car loan's refusal at msg 62 is its attempt 1, and the refusal at msg 98 ends it. Every product is then handled → `ready` → `confirm_record`.
- The replay shows the counts: `{"2": 1, "3": 1}` after msg 62 (v19: `{"2": 2}`, tested as a mutation).

**2. negotiate said "recorded" and goodbye (msg 109).**
- The prompt already forbids both ("A checked offer is not recorded: never say a payment or promise was recorded"; "Never say goodbye or end the call yourself"). The model ignored them.
- No code can stop a model sentence. What changed:
  - the turn now knows its product (fix 3), so it no longer believes the talk is over;
  - a goodbye now has an exit (fix 4);
  - a new static self-check `recorded_claim_gaps` fails as BUILDER if any model-spoken step that sees the offers (`offers_summary`, `readback_text`, `offer_message`) lacks the "never say … recorded" line. A test removes the line from `negotiate` and the check names it.
- **Not done:** the persuasion turn is still a model turn. A fixed persuasion line would be the next step; it is a bigger change, because the attempt rules come from the brief.

**3. No exit for a goodbye; confirm_record stalls.**
- Fixes 4 and 5.
- Scope is the offer steps and the read-back. Opening, identity and third party have their own close values, and the kit says to exclude identity from interrupts. So it does not cover "every conversation step": that would need a decision on the identity step.
- The `max_node_turns` value stays 30; with the two fixes the read-back cannot stall.

**4. A refused product is asked again (msg 73-97).**
- The second ask of the personal loan came from the re-check of the card after the improvised read-back, while p2 still had an attempt left by count. That count was wrong only because of W2.
- With fix 1 the counts are right: a product whose attempts are used up is noted and never named again, and a product with attempts left is re-asked as its persuasion attempt.
- **Not done:** the `more` line does not yet prefer a product without a counted refusal.

**5. The accepted promise is lost.**
- The accepted list was not reset: `offers_accepted` held p1 until the end. The promise was never sent, because `confirm_record` never got `confirms` (W5).
- The turn limit closed as `turn_limit`. That state has no row in this spec, so the default `no_promise/refused` applied.
- The note loop gives an accepted-but-never-sent product the normal reason (AB-FRESH risk 3, by design), which here is `refused`.
- The end-of-call hook wrote only the close (`close_call_on_hangup`), no notes.
- With fixes 4 and 5, the read-back is said and the customer's yes records p1.

**6. Self-check families:**
- **goodbye** (new action kind `goodbye`, `_play_goodbye`):
  - `goodbye_negotiate`: closes as hangup, 1 goodbye turn;
  - `goodbye_at_readback`: read-back said again once, then closes, at most 2 goodbye turns (`GOODBYE_TURNS`);
  - `goodbye_after_one_offer` (multi): goodbye at `offer_say` → read-back → yes → p1 recorded, the others noted.
  - Without the global step they fail (tested).
- **mixed products:**
  - `multi_pay_one_refuse_rest`: "the first one" paid with "the others" refused in the same turn. The refusals then repeat exactly as many times as the spec's attempts give, and the ledger is p1 promised, p2 and p3 noted refused.
  - `multi_refuse_named`: the third product refused by name, then the second paid. The ledger is p1 and p2 promised, p3 noted. With the v19 refusal step it fails (tested).
- **no "recorded" claim:** the static check above.
- **On the 10 fixtures and the live Brief A and A+B specs:** all new families pass. The live specs have 0 self-check failures.

### Replay of PUB-12

`tests/fixtures/replay/pub-12-extractions.json`, spec `brief-ab-live-spec.json`:
- the card from the first turn is accepted;
- the refusals count for the product they name;
- after msg 98 the car loan is noted, and the personal loan has had both attempts;
- the recorded goodbye ("Thank you, goodbye.", extracted `none`) now leaves through `customer_ends_call` and reaches end_call within two goodbyes, with no simulator problem.

A turn that names the refused products in the same message as the card counts them before the check (tested).

## Files

**Code:**
- `builder/offer_check.py`:
  - reader: weekday day words;
  - picker: product under discussion, `refused_numbers`, `refuse_product`;
  - `MULTI_REFUSAL_BODY`, `_multi_config`, setup body;
  - `readback`.
- `builder/product_notes.py`: refused field, persuasion product line.
- `builder/goodbye.py` (new).
- `builder/workflow.py`: three lines before `_add_special_topic`, agreed with claude-dev2.
- `builder/prompts.py`: `OFFER_REFUSED_PRODUCTS_DESCRIPTION`, `PERSUASION_PRODUCT_LINE`, `READBACK_LINE`, `READBACK_ITEM`, `CONFIRM_READBACK_SAID_LINE`, `CUSTOMER_ENDS_CALL_INTENT`.
- `builder/selfcheck.py`:
  - the `goodbye` action kind in `_play_call_end`;
  - two calls in `scenarios()`;
  - the static check in `run_selfcheck`;
  - the `weekday_the_word` form;
  - my functions at the end.

**Tests and fixtures:**
- `tests/test_live_v19.py` (13 tests).
- Fixtures `pub-07-extractions.json`, `pub-12-extractions.json`, `brief-a-live-spec.json`.
- `tests/test_spoken_dates.py`: 7 forms.

**Docs:** `docs/PROMPTS.md` regenerated.

**Brief A pin:** re-pinned to `69c6e9db…`, on top of claude-dev2's `1a2af43d…` (T-028/T-026). It moves because of the reader, the read-back said by code and the goodbye step.

## Prompt budget

`negotiate` with the fresh A+B spec is under the 1700 guard. The first wording of the persuasion product line gave 1705, so it was shortened.

## UAT (CTO)

- **F-PUB07-weekday:** "a weekday with the day in words and no month was read as the next weekday". Fixed offline (T-027).
- **F-PUB12:**
  - refusal counted for the wrong product;
  - persuasion without its product;
  - no exit for a goodbye;
  - read-back left to the model;
  - false "recorded" by the model.

  Fixed offline (T-027), except the model's free persuasion text.
- **Live retest (with approval, chat first):**
  - PUB-07: `offer_verdict date_not_business_day`, promise 27 October;
  - PUB-12: `persuasion_used_by_product` per product, the read-back said by `confirm_record`, one `create_promise` for p1, notes p2 and p3 only, no goodbye loop;
  - PUB-11 and PUB-13 unchanged.
