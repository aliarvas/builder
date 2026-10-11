# T-031: review fixes for product words and the goodbye after an accepted offer

**Scope:** `tasks/T-029-030-review.md`: HIGH 1, HIGH 2, MEDIUM 5, LOW 3, LOW 4 and "Why the simulator did not see".
**Constraints:** generic, no brief value; no Freya, no model call, no commit, no env.sh.
**Owned by claude-dev2 (T-032):** MEDIUM 3 (goodbye intent text), MEDIUM 4 (identity hook), LOW 1 (spoken.py) and LOW 2 (read-back re-entry). We coordinated on the shared files; their lines are untouched.

**Tests:** `python3 -m unittest`: **644 OK** with both T-031 and T-032 in the tree, including the leak test and the prompt document check.

## HIGH 1: a product named in other words was booked on the wrong product

**Cause (as the review found):**
- Matching used whole tokens only, so plurals never matched.
- A part of a kind word needed more than 3 letters, so `car` was skipped.
- `both`/`all` meant every product.
- Words that named nothing fell back to the product under discussion without asking.

**Fix (`builder/offer_check.py`, `PRODUCT_PICK_BODY`):**
1. **Two passes in `named_product_numbers`:**
   - First labels, list ordinals and whole kinds. Their words are then taken out of the text.
   - Then single kind words in what is left: from 3 letters, plurals reduced to the singular (`singular`: a trailing `s` on 4+ letters, not `-ss`).
   - So "the card and the car loan" gives products 1 and 3.
2. **A kind word only one product has names that product.** "the car", "my car payment", "the personal one" name one product each.
3. **A kind word several products share:**
   - in the plural ("the loans") or after a quantifier ("both loans", "all the loans") it names all of them;
   - in the singular ("the loan") it only *may* mean them, so the agent asks one question.
4. **Quantifiers:**
   - "both" alone means the open products only when exactly two are open; with three open products the agent asks once.
   - "all of them" and "every" mean all products.
   - "the others" alone in an offer means the agent asks once.
5. **Unknown words:** words that name no product ("my vehicle") no longer default to the product under discussion. The agent asks once, using the existing `offer_product_asked` guard, then falls back to the product under discussion.
   - Words that only point ("this one", "it"), payment words and day words (weekdays, months, "tomorrow") are not product names, so they keep the product under discussion.
   - The word lists are generic English; no brief value.

**Probe, the review's table on the PUB-12 products (all as expected):**
- "the car" → product 3
- "my car payment" → product 3
- "the loans" → products 2 and 3
- "both loans" → products 2 and 3
- "my vehicle" → ask once
- "the car loan", "the personal one", "the second one", "the card", "the credit card ending 9015" → unchanged and correct

## MEDIUM 5: refusals by plural or short word, and a copied refusal

- **Same matcher in `refused_numbers`.** "the loans" and "the car" now count. In addition:
  - a singular shared word ("not the loan") counts only the product under discussion, if it is one of them;
  - "the other <kind>" counts that kind except the product under discussion.
- **Copied refusal:** `refusal_repeated()` remembers the last counted words (`offer_refused_counted`).
  - On an offer pass, the same words again do not count again.
  - An empty field clears the memory.
  - A refusal turn (the refusal step, where the intent itself is a refusal) always counts and updates the memory.
- **Field description** (`OFFER_REFUSED_PRODUCTS_DESCRIPTION`): "Empty unless this message itself refuses a product; never copy a product from an earlier message."
- **Not done: one refusal for each product in a single message.** "Not the personal loan or the car loan" still uses one attempt of each (review LOW 5, rated a note). I propose it as a UAT entry below.

## HIGH 2: the second goodbye dropped the accepted offer and wrote a false refused note

**Cause:**
- `goodbye_code` sent the first goodbye of the whole call to the read-back.
- Any later goodbye closed with the hang-up state: no promise, and a `refused` note on the accepted product.
- The counter was never reset.

**Fix (`builder/goodbye.py`, `goodbye_code` only):**
- **Read-back once per text.** With accepted offers, the read-back is said once for each read-back text (stored in `customer_goodbye_readback`). A new accepted offer gives a new text, so an earlier goodbye never uses it up. The call count no longer decides.
- **Then record.** The next goodbye routes `record` → `record_next`: the existing record loop, then closing with notes and outcome.
  - This follows CTO addendum item 3: "the closing chain (record accepted promises, notes, close_call)".
  - The customer agreed to the terms in the offer talk and did not object to the read-back; leaving is not a refusal.
- **A rejected read-back is never recorded.** If the confirmation intent holds a revise value, the goodbye closes by stage. `check_offer` clears that value when it accepts new terms, so a later accepted offer is recorded normally.
- **LOW 3:** the read-back route needs a non-empty `readback_text`. Without one, the goodbye closes.

**Decision to confirm (CTO):** I chose to record on the second goodbye, from the addendum, over the review's other option ("close without a refused note on the accepted product"). If the judge's policy check requires an explicit yes before any recording, the other option is a small change in the same place.

## LOW 4: domain words in generated code

The code-string comments now use neutral examples: "product A … but not the others", "<kind> ending <label>", "a word no kind has". The same applies to the two Python comments in `product_notes.py` and `selfcheck.py`. A test checks that the generated code bodies contain none of the public product kinds' words.

## Why the simulator did not see it: new self-check families (`builder/selfcheck.py`)

**`product_words_*`** (specs with per-product refusals and a kind field). The words are built from the synthetic products' kinds, so there is no brief value. Each pays the products the words name, refuses the rest, and checks the promises and notes:

| Scenario | The customer says |
|---|---|
| `kind_word` | "my <word>", a kind word only one product has; a product past the first, so a fallback to the first product shows |
| `plural` | "the <shared word>s" |
| `both_kind` | "both <shared word>s" |
| `refused_plural` | pays one product and refuses "the <shared word>s" |
| `unknown_name` | "the unlisted one" first (the agent must ask, not book), then "the third one" |

**Goodbye scenarios:**
- **`goodbye_readback_then_goodbye`:** one product accepted, then two goodbyes. The promise must be recorded, with notes only for the other products.
- **`goodbye_at_readback`:** now expects the promise recorded.

**A check on every scenario (`accepted_refusal_notes`):** no refused note on a product in `offers_accepted`.

**Results:**
- 12 renders: the 10 fixtures plus the live Brief A and A+B specs.
- The new scenarios pass.
- The only failures are the three known `reach_outcomes` gaps listed in `KNOWN`.

## Tests (`tests/test_t031_product_words.py`, 13)

- The review's words → products table (offer and refusal), 20 phrases.
- "both" with two open products.
- Unknown words ask once, then fall back to the product under discussion.
- A copied refusal counts once.
- The v19 matcher (mutation) books "the loans" and "my vehicle" on product 1.
- Goodbye:
  - the read-back once per text, then record;
  - a new text is read back again;
  - a rejected read-back closes;
  - no text closes;
  - the `record` route goes to `record_next`.
- Self-check:
  - the families exist and pass;
  - the v19 matcher fails `product_words_plural` and `product_words_unknown_name`;
  - the v19 goodbye fails `goodbye_readback_then_goodbye` with "… which the customer accepted".
- No public kind words in the generated code bodies.

## Pin

The Brief A pin moved: the matcher code, the goodbye code and the field description are all in the render, and so are claude-dev2's T-032 changes. I re-pinned it to `c6e4cfe2…` with both in the tree and told claude-dev2. `docs/PROMPTS.md` is regenerated.

## Shared files

| File | What I changed |
|---|---|
| `offer_check.py` | the matcher, `refused_numbers`, `refusal_repeated`, comments |
| `goodbye.py` | `goodbye_code`, the `record` exit, docstring; not `speak_readback` (claude-dev2) |
| `prompts.py` | only `OFFER_REFUSED_PRODUCTS_DESCRIPTION` |
| `product_notes.py` | one comment |
| `selfcheck.py` | new scenario functions, the `goodbye_at_readback` expectation, the per-scenario check |

I told claude-dev2 that their new `confirm_record_resume` node must exist before `add_goodbye_exit` runs, or the `goodbye_exit` static check flags it.

## UAT proposals (CTO)

- **F-090: "A product named in other words was booked on the product under discussion"** (review HIGH 1). Fixed offline (T-031). Live retest: A+B "I will pay the car on Friday" and "both loans on Friday".
- **F-095 (next free after claude-dev2's F-091..F-094): "A second goodbye after the read-back dropped the accepted offer and noted it as refused"** (review HIGH 2). Fixed offline (T-031): read-back once, then record. Live retest: accept one product, answer the read-back "ok thanks, bye" twice.
- **Open note: one message refusing two products uses an attempt of each** (review LOW 5). Confirm on a live PUB-12 transcript.

## Live checks (with approval, chat first)

Review live checks 1 and 2 above. Checks 3 to 5 belong to T-032 and T-028.
