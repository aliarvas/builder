# T-009c review — shorter runtime texts (budget)

**Reviewer:** claude-reviewer · **Scope:** `builder/offer_check.py` (product facts, calendar, shares, exhausted-product fix), `NEGOTIATION_TASK_TEMPLATE`, the estimate code in `workflow.py`, tests. F-055/callback was not reviewed.
**Method:** offline. I rendered setup/check code with the test `Call` helper and the `setup_vars` helper, ran calendars for 5 dates × 3 product sets, products with extra fields, the budget estimate for every fixture and extracted spec, and the exhausted-product turn sequence. `python3 -m unittest`: 320 OK. No Freya, no model, no edits.

## Decision: **düzeltme gerekli** (one MEDIUM, small fix; the rest is good)

The exhausted-product fix is right in text but leaves the amount state inconsistent: after the card closes, the agent asks for the loan's **full** amount (300) while `offer_proposed_kind` is still `minimum`, so a date-only answer records the loan's **minimum (150)**. That is a wrong amount in the ledger.

## Findings

### 1. MEDIUM — `offer_proposed_kind` stays `minimum` after a product is closed by the invalid-offer limit (`offer_check.py` ~648-660)

Only the `ok` branch resets it to `full` ("the next product starts again from the full amount", F-052). The limit path goes through `amount_too_low`, which sets `minimum`, then the product is noted and the message moves to the next product with "The amount due is 300. Could you pay 300?".
Reproduced: card, two invalid offers (`2026-11-30`, then `2026-10-16` with amount 1) → `more`, message as above, `offer_proposed_kind = minimum`. Next turn: customer says only a date (`2026-10-20`), `offer_amount` empty → `offers_summary`: "personal loan: **150** on Tuesday, 20 October". The customer was asked for 300.
The extraction description tells the model to reset the kind per product, which may hide this live, but the code state and the spoken question must agree and the code owns that state.
**Fix:** whenever `progress == 'more'` set `vars[proposed_kind_var] = 'full'` (the message always proposes the full amount of the next product). One line, inside the `if progress == 'more' and upcoming` block. Test: the sequence above must record 300.

### 2. LOW — facts line drops boolean fields and the share is sized for kit-shaped products

- `product_facts` skips `bool` values (`not isinstance(value, (dict, list, bool))`). The kit products have none, but a hidden account with a flag (a dispute or secured flag) would lose it, while the old raw line showed it. The report says "no policy fact lost"; for booleans that is not true. Render them in words ("secured yes") or keep them out only when the name says nothing; do not drop silently.
- The facts share is 140 chars per product, measured on three kit-shaped products (max 138). A product with five extra plain fields gives about 175 chars (I measured `status`, `notes`, `currency`, `account ref` extras). The estimate then under-counts by roughly 10 tokens per product. Acceptable, but the extra values include internal-looking ids (`account ref acc-77`); the prompt already says never read an internal id, so only note it.

### 3. LOW — `ESTIMATED_PRODUCTS = 3` and the leak test

- The leak test (`test_builder_string_literals_do_not_embed_fixture_values`) forbids the int `3` in `workflow.py` to keep a product-count limit out of the renderer. The constant moved to `offer_check.py` and is imported. It is **used only** as the default of `workflow_prompt_estimates` / `runtime_text_characters` (grep: no other use, not in generated code, no rendering decision). It sizes a warning, not a rule, so it does not break the test's purpose. But the move is what lets the test pass; it is honest only because it is documented and used only for the estimate.
- The value 3 comes from the kit (briefs say one to three products), not a hidden-brief fact. Record that in `STARTER-KIT-FACTS.md` and add a test that the constant appears only in the estimate functions (not in `build_spec_workflow` or generated code), so a later use in a rule is caught. A 4-product hidden case would add about 55 tokens to the figure (I computed 1630 for A+B).

## Verified, no change needed

- **Product facts:** `Product 1, credit card ending 0377 (days late 4): deadline Monday, 2 November; minimum amount 28.50; full amount 95.` The id, type, label and the amount-limit fields are omitted because the name and the limits already say them; `days_late` stays in words, which the A+B rule "state the past-due amount and how many days late" needs. The rule for what drops is derived from the spec (`said_fields()`: id field, kind field, label field, fields of the min/max rules), no field name in code. Deadline per product is kept. "Earliest date" moved to the calendar (it is the same for all products).
- **Calendar** (hand-checked): Wed 14 Oct → this week Wed 14, Thu 15, Fri 16; next week 19–23; last business day Fri 16 / Fri 23. Fri 16 Oct → this week Fri 16 only. Sat 17 Oct → "Earliest date: Monday, 19 October.", this week "none", last business day next week only. Thu 22 Oct → next week Tue 27–Fri 30 (26 Oct holiday skipped). Fri 30 Oct → next week "Monday 2, … Friday 6 November" with one month name. Year shown only when it differs from today's.
- **Cut at the latest deadline:** only a shorter-deadline product set cuts (test: Monday 12 Oct, deadline Wed 21 Oct → "No day after Wednesday, 21 October can be recorded."). The persuasion line "last business day of this week" is kept while that day is listed; when a day is cut the note says so and `check_offer` still refuses later days with `date_too_late` and the deadline (tested). With two products the later deadline sets the cut, so nothing valid is hidden. On the kit's two-week window the fixture A+B specs are not cut (deadline up to 12 business days), so the gain there comes from the grouping, as the report says.
- **Checks unchanged:** the only logic change in the limits code is `earliest_day()` extracted from `limits()` with the same body (`shift_to_business(earliest_counted(), 1)` when business-day promises are required); `check_offer` verdict code is untouched apart from `suggest_amount` for `amount_missing` and the exhausted flag. Verdict matrix in the existing tests still passes.
- **Budget numbers** reproduced: `negotiate` per product count (1 / 3 / 4): fixture A 616 / 726 / 781; version 11 Brief A 1327 / 1437 / 1492; tagged A+B 1465 / **1575** / 1630. As the report says, the target is not met for A+B with 3 products and the build still ships with `budget_exceeded_but_shipped`. The remaining excess comes from the brief's own rules, so I agree with the developer's list of next steps; option 1 (tune the share to 2 products) should not be done.
- **Template:** `NEGOTIATION_TASK_TEMPLATE` shrank (1345 → 1079 chars as measured; the report says 1180, the figure includes the rules placeholder either way). All rules remain: use only given dates/amounts, name products, no internal id/step names, "a checked offer is not recorded", verdict none, no limits unless the check names one, date-only takes the proposed amount, "not paying on one date is not a refusal". `{{today_text}}` is gone because the calendar starts with "Today is …". The test that asserts the prompt now matches the F-053 wording ("has already said the last offer check … do not repeat it").
- **Out-of-scope fix (exhausted product message):** the idea is right: the old line said "Could you pay 28.50? Now … Could you pay 300?" — two questions, one for a product already closed, and the suggested date/amount stayed in state so a "yes" could accept the closed product. Clearing both is correct and keeps the work in `offer_check.py`. Keep it, with finding 1 fixed. Also add: if `upcoming` is `None` while `progress == 'more'` (cannot happen today) the message would stay empty and the tts line empty; fall back to the `more` text without the next-product slots.

## Live retest (CTO)

PUB-11 / PUB-13 as the report lists. Add for PUB-12: after the card's second invalid offer the agent asks only the loan question, and a plain date as the answer records the loan's full amount.

UAT: nothing new to add besides finding 1 (log as a finding if the developer agrees: "stale proposed kind after a limit-closed product").


---

## Re-review (Fix: findings 1 and 2)

**Method:** offline; replayed the failing sequence and three more through the `Call` helper, rendered facts with boolean fields. `python3 -m unittest`: 322 OK. No Freya, no model, no edits.

### Decision: **merge edilebilir**

- **Finding 1 fixed.** Card with two invalid offers (`2026-11-30`, then `2026-10-16` with amount 1) → `more`, `offer_proposed_kind = full`, message "Now let us look at the personal loan. The amount due is 300. Could you pay 300?". A date-only answer for the loan now gives `personal loan: 300 on Tuesday, 20 October`. The same reset holds on the `date_too_late` limit path (two late dates → `more`, `full`) and on the `ok` path (card accepted at the minimum → `full`). A single-product call that hits the limit still ends with `limit` and goes to closing, unchanged.
- **Empty-message fallback:** `more` without a next product now says "Which of your products is this payment for?" instead of an empty line. I accept that over my suggestion: the `more` text is meaningless without a next-product name. It cannot occur today.
- **Finding 2 (booleans) fixed.** Facts now read `(days late 4, secured yes, dispute flag no, status overdue)`; no flag is dropped.
- **Not done, accepted:** the `STARTER-KIT-FACTS.md` entry and the "only used in the estimate" test for `ESTIMATED_PRODUCTS`, and the ~10-token per-product undercount for products with many extra fields. Both were LOW. Please add the kit fact and the usage test when `docs/` is free.

UAT: "stale proposed kind after a limit-closed product" — fixed offline, PUB-12 retest pending.
