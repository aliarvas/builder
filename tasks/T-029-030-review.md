# Review of 24550f0 and 9561b1d (T-026..T-030)

**Reviewer:** claude-reviewer. **Scope asked:** things that can cause a loop or a wrong close in a live call: `GLOBAL_EXIT_CONDITION`, `customer_goodbye` decisions and hang-up state, `identity_pass_hook`, multi-product refusal counting (`refuse_product`), `readback_text`, the recording-notice rules in `spoken.py`, leak.
**Method:** offline only. Read both diffs. `python3 -m unittest`: **623 OK**. Rendered `traces/brief-a+brief-b.spec.json` and the test fixtures, then ran the generated code steps through the existing `Session` / `Simulator` harness with my own inputs (scratchpad scripts, nothing in the repo changed). No Freya, no model, no env.sh, no commit.

## Decision: **düzeltme gerekli** (2 HIGH, 3 MEDIUM; the loop fixes themselves hold)

What I checked and found sound:
- **The goodbye path cannot loop.** `customer_ends_call` → `customer_goodbye` → (`confirm_record` once) → `closing` is bounded by the counter. A second goodbye always closes. `goodbye_exit_gaps` shows no conversation step without an exit.
- **Hang-up state selection** matches the end-of-call hook on all five specs: verified → `hangup` (or `default`), unverified → `hangup_unverified`, third party → `third_party:no_callback`, empty `identity_verified` → unverified. I played `(identity_verified, who) = (false, confirmed) / ('', confirmed) / (false, other_person) / ('', '')` and the closing outcomes are `not_verified/declined`, `not_verified/declined`, `not_reached/no_callback`, `not_verified/declined`.
- **`GLOBAL_EXIT_CONDITION`** (`now not_equals ''`): `now` is a call variable that is always present (`docs/STARTER-KIT-FACTS.md:21`, and `source: customer` in the live variable table), so the condition always holds. It replaces only `always` transitions of global nodes, after the same-target grouping, so order and merging are unchanged. No live evidence yet for this exact condition on a global step (T-028 was never run live); see the live check at the end.
- **Leak test green; no brief value in the logic** (details in LOW 4).

---

## HIGH

### 1. A product the customer names in other words is silently booked on the wrong product, and "both loans" books all three
**File:** `builder/offer_check.py:1373-1398` (`named_product_numbers`), `:1468-1490` (`pick_products`), `:1378` (the `both` regex).
**Cause:** when `offer_product_name` is not empty but matches no product, `pick_products` falls through to `[current]`, the first open product, with no question. The match is also exact-token only (plurals fail) and a part word must be longer than 3 letters (`"car"` is skipped).
**Probe (A+B v2 spec, PUB-11 products: card, personal loan, car loan; date "this Friday", `offer_product_name` as listed):**

| Customer's words | Accepted offers | Expected |
|---|---|---|
| "the car" | **product 1 (credit card)** | product 3 |
| "my car payment" | **product 1** | product 3 |
| "the loans" | **product 1** | ask, or products 2 and 3 |
| "my vehicle" | **product 1** | ask |
| "both loans" | **products 1, 2 and 3** | products 2 and 3 |
| "the car loan", "the personal one", "the second one", "the card", "the credit card ending 2288" | correct | |

**Scenario:** a hidden A+B case where the customer says "I will pay the car on Friday" gets a promise on the credit card (wrong `product_id` in the ledger, and a read-back that names the wrong product). The same for "both loans" in a three-product account. The single-product case never meets this, and the public cases use the full kind words, so the tests do not see it.
**Fix:**
1. A non-empty `offer_product_name` that names nothing and is not "this/that one" must **not** default to the current product. Return `([], True)` (ask once, the existing `offer_product_asked` guard already limits it to one question per product).
2. Singularise tokens before matching (strip a trailing `s` on words of 4+ letters) and drop the `len(part) > 3` limit, or use `>= 3`. The padded-token match already keeps `car` apart from `card`.
3. `both` means "all" only if the account has two open products; with more, or when a kind word follows ("both loans"), match the kind words and take the products they name. Same rule for `refused_numbers`.
4. Add the table above as a test (words → accepted product numbers) on the A+B fixtures.

### 2. A second goodbye after an accepted offer drops the offer and writes a false "refused" note on that product
**File:** `builder/goodbye.py:60-70` (`goodbye_code`), counter never reset (`:52-55`).
**Probe (A+B, product 1 accepted for "tomorrow", then two goodbyes):** first goodbye → `confirm_record` (read-back, fine); second goodbye → `close_state = hangup`, closing writes **`no_promise/refused`, no promise, and a `refused` note on p1, p2 and p3**. p1 was accepted by the customer, never refused.
**Scenario:** read-back said, customer answers "ok, thanks, bye" instead of "yes" (very likely for a voice customer, and exactly the PUB-12 shape). The customer agreed to pay; the ledger says the opposite, and a `refused` note on p1 is a false statement about the customer.
**Also:** `customer_goodbye_count` counts goodbyes of the whole call. A goodbye-like "thanks" earlier in the call (see MEDIUM 3) uses up the one read-back, and the real goodbye at the end then closes directly.
**Fix (pick one, both generic):**
- At the second goodbye with accepted offers, do not write the hang-up state. Either route to the record loop (the read-back was said twice and the customer never objected; a silent leave is not a refusal), or close with a state that has **no** per-product `refused` note for accepted products (at least: skip the note for products in `offers_accepted`).
- Reset `customer_goodbye_count` when `check_offer` accepts a new offer, and only count a goodbye heard **at** `confirm_record` as an answer to the read-back.
- Self-check: a `goodbye_readback_then_goodbye` scenario that must end with either the promises recorded or no note on the accepted product. Today the family only checks that the call closes.

---

## MEDIUM

### 3. The goodbye intent matches bare thanks in the middle of the call
**File:** `builder/prompts.py:318` (`CUSTOMER_ENDS_CALL_INTENT`), `builder/goodbye.py:101-107`.
**Scenario A:** the agent says "Thank you, that works for the credit card. Now let us look at the personal loan…" and the customer answers "Okay, thank you." The step's own routes match nothing, the global intent "only says goodbye or **thanks** to end the call" can match, and the call closes as a hang-up with the rest of the products unnegotiated (notes `refused`, outcome `no_promise/refused`). I cannot run the routing model offline; the risk is the wording ("thanks" alone).
**Scenario B:** hardship support offer, customer: "No thanks, goodbye." The choice field now has `ends_call` ("the customer only says goodbye or thanks … not an answer to the question"), next to `stay`. If the extractor picks `ends_call`, the call closes on the hang-up row (`no_promise/refused`) instead of the spec's declined row (`on_decline`, `no_promise/hardship` in the Brief A style). A "no" **is** an answer to the question.
**Fix:** require an explicit leave-taking in both texts ("says goodbye or that they are done / that is all"), say that "thanks", "okay" or "yes" alone are not goodbyes, and that a "no" to the question is `stay`. Add the case "no thanks, goodbye" at an ask-first path to the live checks.

### 4. `identity_pass_hook` counts the same question twice
**File:** `builder/workflow.py:387-401`.
**Probe (the generated post-process code executed twice with `{verified: True}` and no overall field):** the first call leaves `all_verified` absent, the second sets `all_verified: True`. One right answer given twice (the model repeats the tool call, or the customer repeats it after a mis-hear) passes a two-question check.
**When it matters:** only when the bank sends no overall field (the PUB-05 variant). The mock does send `all_verified` in all stored live calls, so the live risk is small; the cost is a security bypass.
**Fix:** count distinct fields. The tool's request args are available in the post hook (or keep a list of answered fields in `vars` written by the pre-hook), and compare with the set of `identity_questions` fields instead of an integer.

### 5. Refusals by plural or description are not counted; a repeated refused name counts again
**File:** `builder/offer_check.py:1425-1440` (`refused_numbers`), `:1505-1511`.
**Probe (card accepted, `offer_refused_product_name` as listed):** "the personal loan and the car loan", "both loans", "the others" → p2 and p3 each get one persuasion attempt (as intended). **"the loans" → nothing counted. "the car" → nothing counted.** Same plural/short-word gap as HIGH 1.
**Second point:** each pass of `check_offer` or the refusal step that finds a non-empty `offer_refused_product_name` uses one attempt of the named products, with no memory of which turn said it. The extractor already copies old text into other fields on "Yes, I confirm." (live PUB-11: `offer_date` copied from the agent's line). If it repeats the refused name on a later turn, a cooperating customer's product loses attempts and ends with a `refused` note. The field description does not tell the extractor to leave it empty on a message that does not refuse.
**Fix:** same matcher fix as HIGH 1; put "empty unless this message itself refuses a product" in the field description; optionally remember the last counted text in `vars` and ignore an identical repeat on the next pass.

---

## LOW

1. **Recording notice grammar** (`builder/spoken.py:101-103`). The rewrite replaces only the clause, so "Calls are recorded **and monitored** for quality purposes." becomes "We are recording this call and monitored for quality purposes." and "this call will be recorded and may be used for training" becomes "We are recording this call and may be used for training". Fix: rewrite only when the match is followed by end of sentence, `,`, `.`, "for", "to" or "so that", else leave the line and emit the existing "left in the line" warning. "This call **may** be recorded" is not matched (warning only); add `may be` to the pattern.
2. **`confirm_record` re-entry repeats the whole read-back** (`goodbye.py:74-78`, tts on entry). Every return to the step (a side-question path through `__previous__`, a special path started at the read-back, the goodbye read-back) says the full text again. Acceptable for the goodbye, wordy for the others; consider `on_enter_first_entry_only` for entries that did not come from `customer_goodbye`.
3. **Empty `readback_text`.** If the step is ever entered with accepted offers lost, the tts says an empty line and waits. All current routes set the text with the accepted offer, so I found no path; a guard in `customer_goodbye` (route to `readback` only when `readback_text` is not empty) costs nothing.
4. **Leak.** The leak test is green and there is no brief value in any condition or table. Generated code comments and docstrings carry domain examples: `builder/offer_check.py:1436` (`("loan")`), `:1508` ("the card tomorrow, but not the loans") inside the code strings that end up in the workflow. They do not run, but a reviewer grepping the exported workflow for brief words finds them. Replace them with neutral examples ("product A", "the others").
5. **Persuasion counts in one message** (`offer_check.py:1505-1511`). "Not paying the personal loan or the car loan" uses the first attempt of both at once; only the first open product is then persuaded, the second one's attempt is used without a turn of its own. The public PUB-12 checks ("two attempts on the loan, one on the car loan") still come out as the agent makes one proposal per product, so I rate this as a note, not a defect. Record it in the UAT findings so a live PUB-12 transcript can confirm.

## Why the simulator did not see HIGH 1 and 2
- HIGH 1: every scenario writes `offer_product_name` with the full kind words (`"personal loan"`, `"all three"`) or the list number; none writes a paraphrase or a plural. Add paraphrase and plural phrases to the scenario table.
- HIGH 2: the goodbye family checks "the call closes" and the close count, not the ledger content for accepted products. Add the check "no note for a product with an accepted offer" to every scenario, and the double-goodbye scenario above.

## Live checks (CTO, with approval, chat first)
1. A+B: "I will pay the car on Friday" and "both loans on Friday"; look at the accepted product numbers in the check_offer variables and the ledger.
2. A+B: accept one product, let the read-back come, answer "ok thanks, bye" twice; expect the promise recorded or at least no `refused` note for it.
3. Brief A hardship ask: "No thanks, goodbye" → expect the declined row, not the hang-up row.
4. Any normal call: "Okay, thank you" in the middle of the offer talk must not close the call.
5. One normal completed call: the new `GLOBAL_EXIT_CONDITION` on a special path (for example "I already paid") reaches its exit without a silent loop (it was the PUB-08 failure).
