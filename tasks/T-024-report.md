# T-024 report: PUB-11, PUB-12, PUB-13 on the A+B agent (workflow 8887e79f), 0/3

**Owner:** claude-reviewer (analysis only). **Not done:** no code change, no Freya request, no commit, no env.sh.
**Inputs:** `results/e2e-v18/ab-baseline.log`; call records `traces/live-runs/user-fc8bdd72-*` (PUB-11), `user-814a1420-*` (PUB-12), `user-2a3dab4c-*` (PUB-13); `submission/brief-a+brief-b.workflow.json` (the `check_offer` code step read in full); `builder/offer_check.py`, `builder/workflow.py:1539`, `builder/selfcheck.py:563`, `tests/test_multi_ready.py`. Times are seconds from the start of the call.

## Summary

All three calls die on the **same builder bug**, not on model noise or on branch order.

1. `check_offer` needs the field `offer_product_number` to know which product an offer is for. With more than one product and no number it answers `product_unknown` ("Which of your products is this payment for?") and goes to `offer_say`.
2. **The extraction never writes `offer_product_number`. Not once, in any of the three calls and in none of the 19 stored live records.** The field is an integer "number of the product in the account facts list". The customer says "the credit card", and the transcript never contains list numbers (the prompt even says "never by a list number"). The extractor returned nothing for it every time.
3. `check_offer` then **wipes the offer** (`offer_date`, `offer_amount`, `accepts` are reset at the end of every pass, also on `product_unknown`). `offer_say` can only go back to `check_offer` on `offer_date` set or `offer_accepts_proposal == yes`. A product-only answer ("That is for the credit card") matches no branch. The LLM improvises, the customer repeats "yes", the date is extracted again, `check_offer` again has no product: **an endless loop, never reaching `create_promise`.**
4. While the loop runs the LLM speaks freely. That gave the wrong date (PUB-13) and a false "I have recorded your promises" (PUB-11, with no tool call at all).

This is not the T-021 platform order effect. Here the right branch (`check_offer`) was matched first every time; the problem is what `check_offer` does with a missing field.

## PUB-11 (three products, all on Friday 16 October). Ledger: no promise, `close_call(no_promise, refused)` by the hang-up hook.

| t | Event |
|---|---|
| 59.4 | `get_account` ok: 3 products. `offer_setup` ok. |
| 62.5 | `negotiate`: the agent states the three products and asks "Can you make these payments today?" |
| 65.5 | Customer: "I cannot pay today." Extracted `negotiation_reply = flat_refusal`. Route: `product_refusal` matched, back to `negotiate` (a persuasion attempt, fine). |
| 76.9 | Agent: "For the credit card ending 2288, can you pay the full amount of 220 this Friday, 16 October?" |
| 90.1 | Customer: "Yes, I can pay that this Friday." Extracted `offer_amount = 220`, `offer_date = 'this Friday, 16 October'`, `offer_amount_kind = full`, `offer_accepts_proposal = yes`, `negotiation_reply = agreed_date_and_amount`. **No `offer_product_number`.** |
| 104.8 | Route `negotiate` → `check_offer` (matched). `check_offer` code: `raw_number = None`, 3 products → `verdict = product_unknown`, `progress = rejected`; date, amount, kind, accepts reset. Route `check_offer` → `offer_say` (`confirm_record` False, `closing` False, `offer_say` always). |
| 105.2 | Agent: "Which of your products is this payment for?" |
| 106.8 | Customer: "That is for the credit card." **Nothing extracted at all** (no event). Route from `offer_say`: all four branches False. No target. The platform filler "Bir saniye lütfen" is spoken (F-043). |
| 138.5 | LLM improvises the next product: "For your personal loan, can you pay 640 this Friday?" (a good line by luck, not by design). |
| 145.7–194.2 | Same pattern for the loan and the car loan: "Yes, I will pay that this Friday" → date + accepts extracted → `check_offer` → `product_unknown` → "Which of your products…" → "That is for the personal loan / car loan" → no extraction, no route. |
| 202.1 | Agent (LLM, no tool call): **"I have recorded your promises to pay 220 …, 640 …, and 75 …"**. False; nothing is recorded. |
| 215–259 | "Yes, I confirm." re-triggers `check_offer` (accepts = yes) → `product_unknown` again, four more rounds. Customer answers "the credit card, the personal loan and the car loan"; no extraction, no route. |
| 273–424 | Agent says goodbye, customer says goodbye, 20+ times (the step has no exit). 424.9 `exceeded-max-duration`. `close_call_on_hangup` writes `no_promise/refused`. `offers_accepted_count` stayed 0 the whole call. |

`check_offer` ran 5 times, every time `product_unknown`. `create_promise` was never reached.

## PUB-12 (card tomorrow; the customer refuses the loan and the car loan). Ledger: no promise, `close_call(no_promise, refused)`.

| t | Event |
|---|---|
| 26.2 | Customer: "I will pay the credit card tomorrow, but I am not paying the personal loan or the car loan." Extracted `offer_date = tomorrow`, `offer_amount_kind = full`, `negotiation_reply = proposes_date_or_amount`. The product is named in the sentence, **`offer_product_number` still not extracted**. |
| 28.2 | `negotiate` → `check_offer` → `product_unknown` → `offer_say`: "Which of your products is this payment for?" |
| 29.9 | "The credit card." No extraction, no route. LLM: "Thank you. To clear the past-due amount of 510 for your credit card, can you pay that tomorrow, Thursday 15 October?" |
| 36.6 | "Yes, I confirm." → `offer_accepts_proposal = yes`, `offer_date` copied from the agent's line → `check_offer` → `product_unknown` → "Which of your products…" |
| 38–400 | The same cycle **37 times** (`check_offer` entered 37 times). "Yes, I confirm" → "Which of your products…" → "The credit card" → LLM repeats the same sentence. Some rounds `offer_date` fails at 0.59 to 0.68 confidence (below the 0.7 minimum); `accepts = yes` alone keeps the route open. The judge's "infinite loop from message 16" is this. The refusals of the loan and car loan, spoken in the first sentence, were never turned into notes: the call never got that far (expected notes p2/p3 `refused`). The customer hung up. |

## PUB-13 (card 30 October, loan 23 October). Ledger: no promise, `close_call(no_promise, refused)`.

| t | Event |
|---|---|
| 85.4 | Customer: "I cannot pay today. I would like to pay both on the thirtieth of October." Extracted `offer_date = 'thirtieth of October'`, `offer_amount_kind = full`, `negotiation_reply = proposes_date_or_amount`. No product number ("both"). |
| 101.2 | `check_offer` → `product_unknown`; **the date 30 October is reset (lost)**. |
| 102.7 | "It's for both the credit card and the personal loan." Nothing routes. |
| 124.0 | The LLM, with no verified offer, improvises from its own prompt: "the latest date I can record is **Monday, 2 November** (card) … **Friday, 23 October** (loan). Does that work?" The customer had asked for 30 October, which was allowed. This is the wrong date the judge names. |
| 148.0 | "Yes, I accept those dates." → `offer_date = 'Monday, 2 November, Friday, 23 October'` (0.72), `accepts = yes` → `check_offer` → `product_unknown`. |
| 158–424 | 13 rounds of the same cycle. The LLM reads back "300 … on Monday, 2 November … 900 … on 23 October. Is that correct?" Again no `create_promise`. `exceeded-max-duration`. |

## Why it went wrong (root cause, in order)

| # | Cause | Kind | Evidence |
|---|---|---|---|
| 1 | **Product identification relies on an integer the extractor cannot know.** `offer_product_number` (`workflow.py:1539`) = "number in the account facts list". The list numbers only exist in the hidden task text (`Product 2, personal loan …`); the customer and the agent speak product names. The raw extraction responses never contain the field (checked: every `raw_response` in the three calls). | builder (extraction design) | 0 extractions of the field in 19 stored records |
| 2 | **No fallback when the number is missing.** `check_offer` says `product_unknown` even though the agent itself just proposed the product it is asking about (the code knows which product is next: `upcoming`). It asks the customer a question the extractor cannot take the answer to. | builder (code step) | `offer_check.py:684` `number = None` → `product_unknown` |
| 3 | **The offer is destroyed on `product_unknown`.** Date, amount, kind and accepts are reset unconditionally at the end of the pass. | builder (code step) | `vars[date_var] = ''` etc. after every verdict |
| 4 | **No branch for a product-only answer.** `offer_say` routes only on `offer_date` set or `accepts == yes`. Even a correctly extracted number could not leave the step. | builder (render) | `offer_say` transitions |
| 5 | **No loop guard.** `product_unknown` is not counted (it is excluded from the rejection counter), so the cycle has no end except the 7 minute limit. | builder | `verdict not in ('ok','missing','amount_missing','product_unknown',…)` |
| 6 | **Free LLM turns in `offer_say` when nothing routes.** It may say "recorded" (honesty) or invent dates (PUB-13). The prompt forbids it; the model does not obey while it has no verified facts. | builder (prompt/structure), consequence of 1–5 | PUB-11 t=202, PUB-13 t=124 |

Side effect (not seen yet): `offer_product_number` is never reset by `check_offer` (its `reset` list does not contain it). The moment the extractor does write it, a stale value from the previous product stays when a later turn does not mention a product, and the next acceptance lands on the wrong product (my probe: after `say(offer_product_number=1)` a later date-only turn is checked as product 1).

The "Bir saniye lütfen" Turkish filler appears again (F-043, platform). It is not the cause.

## Why the simulator and the offline tests did not catch it

- Every offline walk **writes `offer_product_number` by hand** with the right value: `selfcheck.py:563,569` (`{OFFER_DATE: day, OFFER_PRODUCT: number}`) and all of `tests/test_multi_ready.py` (`session.say(offer_date=…, offer_product_number=1)`). The simulator plays the customer as an ideal extractor. It never plays a turn where the field stays empty, so the `product_unknown` branch is never entered on a path that the spec describes.
- A field that only a language model can fill is treated as always filled. This is the same class as T-021 PUB-05 ("the wrong reading of words is not played").
- The self-check has **no no-progress check**: a cycle `check_offer → offer_say → check_offer` that never changes `offers_accepted_count` is not a failure. It looks only at the end state and at `reaches end_call`; a bounded script never gets stuck because the script supplies the product.
- My probe on the shipped A+B fixture reproduces the live loop exactly with a missing product number: turn 1 → `offer_say` / `product_unknown`; a product-only turn → still `offer_say`, no route (path `offer_setup, negotiate, check_offer, offer_say`).
- Brief A has one product, where `number = 1` is the default (`number = 1 if len(products) == 1`). That is why the single-product cases passed: the bug only appears with 2+ products. This was the first live multi-product run.

## Generic fixes (no brief value in any of them)

**Fix 1 (the one that matters): identify the product from the words, with a default, in the code.** Risk: medium (code step and extraction text; renders of single-product briefs stay identical because they already take `number = 1`).
- Replace the integer by a text field, for example `offer_product_name`: "the product the customer names, in the customer's words (copy the words), empty if none". The code matches it against the products using the fields the builder already knows (`kind_field` with `_` as space, `label_field` such as the last four digits, ordinal words). The builder already builds the same names in `product_name()`.
- If nothing matches or the field is empty: **use the product under discussion**. The code already tracks it (next unhandled product, `upcoming`; and `persuasion_attempt` state per product). The agent proposes products in account order and asks about exactly that one; "Yes" or a date applies to it. `product_unknown` is only spoken when two or more products are plausible AND the text names none, and at most once per product.
- "Both" or several names: apply the same date to every named product (the PUB-13 and PUB-11 shape) or fall back to the first unhandled product and let the `more` line move on. This is the extension that makes PUB-13 pass without extra turns; it needs the loop in the code step (an array of numbers), medium effort.

**Fix 2: keep the pending offer when the verdict is `product_unknown` (and `missing`).** Do not reset date, amount, kind, accepts on those verdicts. Risk: low. Then a product-only answer can complete the offer.
**Fix 3: route on the product answer.** Add a branch in `offer_say` (and `negotiate`): "a product is named and a pending offer exists → `check_offer`". Risk: low to medium (one more condition in the shared transition list; the self-check structural pass applies).

**Fix 4: loop guard.** Count `product_unknown` per call; on the second one use the product under discussion, never a third question. Count identical consecutive `check_offer` verdicts without progress; on the third go to a safe exit (the existing `limit` path or the note + close). Risk: low.

**Fix 5: reset `offer_product_number` (or the new name) at the end of `check_offer` with the other offer fields.** Risk: low; avoids stale products once extraction works.

**Fix 6: pin the honesty of `offer_say`.** While `offers_accepted_count == 0` and no tool ran, the step may not say "recorded". Today it is only the prompt line "A checked offer is not recorded". A speaking step that is entered with a verdict of `product_unknown` should speak only the verdict line (`on_enter` already does) and then wait; the free LLM answer after a non-routing turn is what produced both the false claim and the wrong date. Risk: medium (needs a no-route fallback design, or `max_node_turns` with a transition). Low-risk part: stronger prompt wording.

**Order of work I recommend:** Fix 1 (default to the product under discussion) alone removes all three failures, because the extractor already writes date, kind and accepts correctly. Fix 2 and 4 are cheap safety nets. Fix 5 goes with Fix 1.

## Self-check changes so this cannot pass again

1. **Play the extractor's gaps.** For every offer scenario, add a variant where the fields only a model fills (`offer_product_number`, and any `*_kind`) stay empty, the way the live extractor leaves them, and require the same ledger as the full variant when the call state allows a default. Today a default is not allowed by the code, so this variant would have failed on the current render (BUILDER).
2. **No-progress loop check.** In `play()`, if the same step pair repeats more than a small bound (3) without a change in `offers_accepted_count`, `notes` or the progress variable, report a BUILDER failure "loop: check_offer ↔ offer_say".
3. **Replay a recorded call.** A test that reads a `traces/live-runs/*.json` record, takes the extractor outputs as they were (`variable_extracted` per turn, including the absence of fields) and feeds them to the simulator. PUB-11 would then end in `product_unknown` forever on the old render. This keeps the simulator honest against what the real extractor does.
4. Add `product_unknown` rounds to the "reach" list: any message line in the code table whose state can be entered must also have an exit that changes state.

## Live check after the fix (needs user approval, chat first)

PUB-11, PUB-12, PUB-13 on a freshly built A+B agent. Look in the call record for: `offer_product_name` extracted or the default taken, `check_offer` verdict `ok` on the first pass per product, `offers_accepted_count` rising 1, 2, 3, `create_promise` called once per product with the right date (30 October in PUB-13), and no assistant line with "recorded" before a `create_promise` result.
