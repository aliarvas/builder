# T-025: offers with several products (T-024: A+B 0/3, endless product_unknown loop)

Fixes 1, 2, 4 and 5 from `tasks/T-024-report.md`. Generic, no brief value. No Freya, no model call, no commit, no env.sh.

## Scope: only specs that handle products one by one

`offer_check.multi_product(spec)` is true when the spec has `closing.product_notes` or `negotiation.product_end_values`. Only then is the new code rendered.
- **Other specs render byte-identically:** a test renders every non-multi fixture with and without T-025 (6 specs) and compares.
- **Brief A pin:** unchanged by T-025.
- **But:** the live Brief A spec (`traces/brief-a.spec.json`) and the recording `brief-a-repro-1300` have per-product refusal values, so they get the new `check_offer` and the name field.
  - With one product the result is the same: nothing named means product 1, as before.
  - The code and the extraction field still change in their render.

## Fix 1: the product from the customer's words

**New extraction field `offer_product_name`** (prompt `OFFER_PRODUCT_NAME_DESCRIPTION`): "The product or products the customer's last message names for this payment, copied in the customer's words … Empty if the message names no product."
- It sits next to `offer_product_number` in `negotiate`, `offer_say` and `revise_ask`.
- It is added in `product_notes.add_product_name_field`, before the copies are made. `workflow.py` is not touched (claude-dev2's T-023 area).
- It goes to the extraction model, not into the prompt budget.

**`check_offer` (multi only)** puts a product picker (`pick_products`) before the existing check:
1. A valid `offer_product_number` is used as before.
2. Otherwise the words are matched against the names the builder already speaks (`product_name`):
   - the label field (for example the last four digits);
   - an ordinal ("second one");
   - the kind in words ("credit card"). A kind shared by two products only makes them *plausible*. A word of the kind ("loan") makes products plausible.
   - "both", "all", "each" … name every open product.
3. **Named products:** those still open (or all named ones, for a revise).
4. **Exactly one plausible open product:** that one.
5. **Two or more plausible and none named:** `product_unknown`, **once per product under discussion**. The next time the product under discussion is taken.
6. **Nothing named, or no match:** the product under discussion, which is the first product not yet handled (accepted or noted). That is the product the agent's `more` line proposes.

**Several products:** the existing check runs once per product (`check_once`, the unchanged `CHECK_BODY` inside a function), with the same date for each.
- A single spoken amount cannot be meant for several products, so each takes its full or minimum amount.
- It stops at the first product whose check is not ok. That product's line is spoken ("The latest date I can record for the personal loan is …"), and a "yes" then completes it.
- PUB-13 ("both on 30 October") now records the card on 30 October and, after one "yes", the loan on 23 October.

## Fix 2: a pending offer is kept

- **On `product_unknown`:** the date, amount and kind stay for the next turn. A date that came from a "yes" to a proposal is kept as that date. A product-only answer ("the personal loan") then completes the offer, because the date is still set and the existing route to `check_offer` holds.
- **On `missing`:** the amount and kind stay; the unreadable date and the "yes" are cleared, so T-022's proposed date works.

## Fix 4: loop guard

`offer_no_progress` counts check passes in a row that handle no product. At `NO_PROGRESS_LIMIT` = 5 the code takes a safe exit:
- `ready` when offers were accepted: the read-back records them, and the note loop notes the rest;
- otherwise `limit`, which goes to the closing as `offer_limit`.

With T-022's streak and the offer limit, a normal call ends before the guard. It is a backstop.

## Fix 5

`offer_product_number` (set to 0, a valid integer for the typed field) and `offer_product_name` ('') are reset after every check, like the other offer fields.

## Self-check

**`_without_product_field`:**
- Every multi-product scenario (`multi_accept_all`, `multi_refuse_one`, `multi_record_failure`) is also played with the product number left empty, as the live extractor leaves it. It must give the same ledger.
- It passes on all multi fixtures.
- With the old `check_offer`, all three variants fail as BUILDER (dead end at `offer_say`, no promise).

**No-progress check in `play()`:**
- `Simulator.run_code` records the accepted and noted products after each `check_offer` pass.
- `_offer_loop_failures` reports "loop: N offer checks in a row handle no product" when more than 3 passes in a row change nothing.
- Small additions to `Simulator.__init__`, `run_code` and `play()`; the rest is in my own functions at the end of the file.

**Live specs** (Brief A, A+B in `traces/`) rendered with the current code: self-check without failures.

## Replay of the live PUB-11 call

- **Fixtures:**
  - `tests/fixtures/replay/pub-11-extractions.json`: every customer turn of `traces/live-runs/user-fc8bdd72-*.json` with its step and the fields the live extractor wrote (from `variable_extracted`; failed extractions are absent), plus the products and now;
  - `tests/fixtures/replay/brief-ab-live-spec.json`: the spec of that build (workflow 8887e79f, run 20261011T133610Z).
- **`tests/test_replay_pub11.py`** reaches `negotiate`, then feeds each recorded turn to the step the simulator waits at (only that step's fields).
- **New code:**
  - three checks, one per product, with no `product_unknown`;
  - `confirm_record` after the "…this Friday as well" turn;
  - after the confirmation, the three promises the case expects (p1 220, p2 640, p3 75 on 2026-10-16).
- **Old `check_offer`** on the same turns: zero offers accepted, still at `offer_say`, and the loop check fires. This is the live loop, reproduced offline.

## Tests

`python3 -m unittest`: **587 OK**.

**New:**
- `tests/test_product_pick.py` (11 tests):
  - no product named → the product under discussion;
  - by kind and by label;
  - "both" with a date too late for one product;
  - ambiguous words asked once, with the date kept;
  - the fields reset;
  - `missing` keeps the amount;
  - loop guard (ready, limit, reset);
  - identical non-multi renders;
  - field placement.
- `tests/test_replay_pub11.py` (2 tests).

**Changed to the new behaviour (both were the old risk records):**
- `test_multi_ready.test_pub11_one_turn_for_all_three`: an empty number → product 1; "all three" → three offers in one turn.
- `test_multi_step.test_brief_b_products_and_progress`: no number → product 1 ok.

`docs/PROMPTS.md` is regenerated (new field description).

## Risks and what is not done

- **Fix 3 (a route for a product-only answer) is not done.** It works through Fix 2's kept date.
  - **Risk:** while a date is pending after `product_unknown`, any next turn routes to `check_offer` first, so a refusal in that one turn is checked as an offer. `product_unknown` is now rare (ambiguous words, once per product).
- **Fix 6 (honesty of free turns in `offer_say`) is not done.** With the loop gone, free turns there are much rarer.
- **The refusal step does not use the name yet.** PUB-12's "…but I am not paying the personal loan or the car loan" in one turn still needs per-product refusals from words. `product_refusal` takes the product under discussion.
- **Name matching is English:** kind words, the label, ordinals and "both/all/each".

## Live check (with approval, chat first)

PUB-11, PUB-12 and PUB-13 on a freshly built A+B agent. Look for:
- `offer_product_name` extracted or the default taken;
- one `check_offer` `ok` per product;
- `offers_accepted_count` 1, 2, 3;
- one `create_promise` per product (PUB-13: card 30 October, loan 23 October);
- no `product_unknown` loop.
