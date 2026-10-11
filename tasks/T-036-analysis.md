# T-036 analysis: remaining v20 failures (agents built before 554ae37)

**Owner:** claude-reviewer. Analysis only: no code change, no Freya request, no env.sh, no commit.
**Inputs:** `traces/live-runs/user-<call_id>.json` for the eight calls, `results/e2e-v20/*.log|json`, `submission/*.workflow.json` (the built v20 agents), HEAD = 554ae37.
**How HEAD was checked:** I rendered `traces/brief-a.spec.json` and `traces/brief-a+brief-b.spec.json` with the HEAD builder and ran the generated code steps through `tests/test_multi_ready.Session` with the extractor outputs taken from the records (scratchpad scripts, repo untouched). "Fixed in HEAD" below means that probe now gives the right result; "not fixed" means it reproduces the live failure on HEAD.
Times are seconds from call start.

## Summary

| # | Case | Call | Root cause | In HEAD? |
|---|---|---|---|---|
| 1 | PUB-01 asks_back | acac8c5b | Simulated customer ended the call 5.5 s after the first security question. The end-of-call hook closed correctly. Not an agent defect. | n/a (environment) |
| 2 | PUB-04 (3 variants) | 529d1a12, b85dc252, 3d1db759 | The "are you a robot?" question comes in the **same message as a date**. The step's own `check_offer` route wins, the next step speaks a **fixed** line, and the robot answer rule exists only in the opening steps. | **Not fixed** |
| 3 | PUB-07 asks_back | 63bbf421 | After a correction at the read-back the **fixed** revise question asks the date again, and a revised offer on the only (already accepted) product has no "open" product, so the code asks "Which of your products…". | **Not fixed** |
| 4 | PUB-11 asks_back | 3620a1f9 | "I cannot pay **today**" was extracted as `offer_date = today`; the date route fires before the refusal and accepts the first product for today. | **Not fixed** |
| 5 | PUB-11 in_words | d66add87 | The bank mock threw a Cloudflare "Worker threw exception" on both `create_promise` calls for p1. The builder retried once and then wrote a `service_error` note, as the brief says. | n/a (environment); behaviour is correct |
| 6 | PUB-12 corrects | 0a0e8a46 | "I am not paying **that loan**" was charged to both loans (shared word), so the car loan lost its only attempt without being asked; the model also moved to another product on its own. | Charging: **fixed** (T-031). Model drift: partly open |

---

## 1. PUB-01 asks_back, acac8c5b: customer hung up, `not_verified/declined`

**Timeline**
| t | Event |
|---|---|
| 0.0 | Opening: digital assistant, "we are recording this call". |
| 7.1 | Customer: "Yes, this is Daniel Reyes." |
| 14.0 | `caller_role = confirmed` (the extraction took ~7 s), → `identity_check` → `identity`. |
| 14.4 | Agent: "…What is your date of birth?" |
| 19.9 | **Customer-side hang-up (`customer-ended-call`, duration 17 s)**, no answer given. `close_call_on_hangup` fires: `not_verified/declined`, ok. |

**Root cause:** the simulated customer ended the call without answering. The log says "Failed calls where the customer hung up: 1" and "agent was slow" (median 8 s, worst 17 s). The builder did the right thing: the hang-up hook wrote the unverified row (this is what the spec row for `hangup_unverified` gives). PUB-01 passed in the other v20 runs.
**Fix:** none in the builder. Re-run. The only lever is speed: the first extraction (`caller_role`) took 7 s, so the question came 7 s after the customer spoke. Nothing in our workflow makes that slower than necessary (one small enum field).
**Why not HEAD-related:** same on HEAD.

---

## 2. PUB-04 (asks_back 529d1a12, corrects b85dc252, in_words 3d1db759): the robot question is never answered

Judge: "failed to … respond to the user's direct question 'Am I talking to a robot?'" (3 of 4 runs of the family failed; 1 passed when the model happened to answer.)

**Timeline (same in all three)**
| t | Event |
|---|---|
| 31.5 | Agent states the late car loan, asks to pay today. |
| 34.3 / 20.3 / 21.7 | Customer: "Am I talking to a robot? My salary arrives on the sixth of November and I can pay then." (variants put the question last, or add a self-correction). |
| 36.7–37.9 | Extraction: `offer_date = 'the sixth of November'`, `offer_amount_kind = none`, `offer_accepts_proposal = none`, `negotiation_reply = proposes_date_or_amount` (asks_back) or **`special_topic`** (corrects, in_words). |
| 37.9 | Route from `negotiate`: **`check_offer` True** (first transition: `offer_date` is set). No intent is evaluated (`None`). |
| 38.2 | `check_offer` → `offer_say`; its `on_enter` is a **fixed line** `{{offer_message}}`: "The latest date I can record for the car loan is Friday, 23 October. Would Friday, 23 October work for you?" |
| — | No model turn ever sees the robot question. The call goes on and ends with the right promise (23 October) but without the answer. |

**Root cause (three parts, all builder):**
1. **Own route beats the topic value.** The first transition of `negotiate` and `offer_say` is "date is set → `check_offer`". It does not look at `negotiation_reply`. In two of the three calls the extractor did flag the message as `special_topic` (the value T-023 added so that a step's routes would not hide a topic), but the date route fired anyway. File: the transitions built in `builder/workflow.py` (the "The customer named or accepted a date" transition) and `_add_special_topic` (`workflow.py:683`).
2. **No spoken answer exists for this question.** In Brief A the robot answer is a **rule of the opening step only** ("If the customer asks whether you are a robot or an AI, say that you are Freya Bank's digital assistant and continue."). I checked the rendered Brief A: only `opening` and `opening_reask` contain it; the system prompt and `negotiate` do not. There is no special path for it, so T-019's side-question list (which only knows spoken-only **special paths**) does not carry it either.
3. **The next speaker is a code-fed fixed line.** Even if a rule existed in `negotiate`, the step after the date is `offer_say`, whose `on_enter` is `tts {{offer_message}}`: no model runs, so nothing can add the answer.

**HEAD:** unchanged (T-031/T-032 did not touch these). I confirmed that `negotiate`'s first transition on HEAD has no guard on `negotiation_reply`, and that the robot rule is still only in `opening`/`opening_reask`.

**Generic fix (no brief value):**
- **A (route):** make the date route yield to the topic value: add `negotiation_reply != special_topic` (and the same for the other step choice fields) to the condition of the "named or accepted a date" and the refusal routes. A message flagged as a topic then reaches the special-path intents; with no path that matches, the step stays and the model answers (it has the step's rules). Because `offer_date` is not cleared, the next turn ("yes") still triggers `check_offer`. File: `builder/workflow.py` (offer transitions) + `_add_special_topic`.
- **B (rules that answer questions):** extraction should turn rules of the form "if the customer asks X, say Y" (any step) into returning spoken-only special paths, so T-019 already lists them in every step; or the builder should copy such opening rules into the system prompt's global rules. File: `builder/extract.py` rule classification / `builder/prompts.py` extraction prompt, and `workflow.py:side_question_paths`.
- **C (the fixed line):** when the turn carried a topic, let `offer_say` speak through the model: `on_enter` type `llm` with "answer the customer's question in one sentence, then say exactly: {{offer_message}}". Risk: the model paraphrases the bank line; keep it only for this case (a flag set by the extractor value `special_topic`, otherwise the plain tts). Medium risk; A+B are enough if the intent path exists.
- **Self-check:** add a scenario "side question in the same message as a date" for every spoken-only rule/path: the expected result is that a line containing the rule's answer is spoken before the first fixed check line. Today the simulator writes only business fields in that turn.

**Risk of A:** a real offer misread as `special_topic` is not checked until the next turn; mitigated because the date stays set.

---

## 3. PUB-07 asks_back, 63bbf421: date and product asked twice

Judge: "The agent asked for the payment date twice (Message 12 and 16) … redundant, asking which product …".

**Timeline**
| t | Event |
|---|---|
| 33.5 | "Which account is this about?" → `special_topic`; the model answers (fine). |
| 37.4 | "I can't pay today. I can pay the week after next." → `offer_date = the week after next` → `check_offer`: verdict `missing`. |
| 40.2 | Fixed line: "Could you tell me the exact day…? The latest date … is Monday, 2 November. Would Monday, 2 November work?" (first ask). |
| 42.6 | Customer: "I would like to pay on Monday" → `offer_date = Monday`, `accepts = yes`. The code resolves the bare weekday to the **nearest** Monday, 19 October. |
| 46.4 | Read-back: "…Monday, 19 October. Do you confirm?" |
| 48.4 | Customer: "Monday the 26th." → `readback_reply = changes_offer` (the read-back step extracts only the intent, **not the date she just said**). |
| 49.1 | `revise_ask`, fixed line: **"Of course. Which date or amount would you like instead?"** (second date question). |
| 53.2 | Customer repeats "Monday the 26th." → `offer_date` → `check_offer`. |
| 65.0 | **"Which of your products is this payment for?"** The account has one product, already accepted (19 October). `offer_setup` computes the discussed product only from **open** products; with none open, `pick_products` returns no product → `product_unknown`. |
| 66.7 | Customer: "The personal loan." → check → 68.5 "That day is not a business day… 27 October. Would that work?" |
| 70.1 | "Yes, that works." → check again → **"Which of your products…" a second time** (74.9) → "The personal loan." → read-back. Promise p1 for 27 October is correct. |

**Root causes**
1. **A correction at the read-back repeats a question the customer already answered.** `confirm_record` extracts `readback_reply` only; `revise_ask` always says its fixed ask. Both in `builder/workflow.py` (`confirm_record` extraction, `revise_ask`, `REVISE_ASK_LINE`). **Not fixed in HEAD** (the T-031/T-032 resume line concerns side questions, not this).
2. **A revised offer for an already accepted product finds no "open" product.** `pick_products` → `discussed_number` returns None once the product is in `offers_accepted`. I reproduced it on HEAD: accept p1, then `offer_date = "Monday the 26th"`, empty product name → `product_unknown`, message "Which of your products is this payment for?" With one product on the account the question is also nonsense. File: `builder/offer_check.py`, `discussed_number`/`pick_products` (`PRODUCT_PICK_BODY`). **Not fixed in HEAD.**
3. **Bare weekday resolves to the nearest one** (19 October) although the agent had just offered Monday 2 November and the customer answered "Monday". Not a defect by the brief, but it caused the whole correction round. Low.

**Generic fix**
- In `pick_products`: when there is no open product, use the product that is **being revised**: the only product if the account has one, else the last accepted/discussed number (`offer_discussed_number` already stores it). Never ask "which product" when the account has one product (`len(products) == 1` → that product). Add a scenario: accept, change at the read-back, expect the new verdict with no product question.
- Add `offer_date`/`offer_amount` (and the other offer fields) to the `confirm_record` extraction; transition `confirm_record → check_offer` when `readback_reply == changes_offer` **and** a date or amount is set; use `revise_ask` only when none is set. Files: `workflow.py` (`confirm_record` schema, transitions).
- Bare weekday: if `offer_suggested_date` is set and has the same weekday name, take the suggested date; otherwise (two possible dates) leave it to the check's existing "which date" message. File: `offer_check.py` `resolve_offer_day`.

---

## 4. PUB-11 asks_back, 3620a1f9: p1 promise on 14 October instead of 16 October

**Timeline**
| t | Event |
|---|---|
| 24.1 | Customer: "I cannot pay today." |
| 25.2–25.5 | Extraction: **`offer_date = 'today'` (0.977)**, `offer_accepts_proposal = none`, `negotiation_reply = flat_refusal`. |
| 29.6 | Route: `check_offer` (date set) before `product_refusal` (the refusal route is second). |
| 29.9 | Check accepts "today" for p1 (14 October is allowed): line "Thank you, that works for the credit card ending 2288. Now let us look at the personal loan…" |
| 32.0 | Customer: "I can pay all three of them this Friday." → p2 and p3 accepted for 16 October (all products named). |
| 36.9 | Read-back: card Wednesday 14 October, loan and car loan Friday 16 October. The customer says "Yes, I confirm." |
| 41–46 | Promises p1 14 Oct, p2 and p3 16 Oct recorded. Expected p1 16 Oct. |

**Root cause:** a **negated** date. The extractor copies the date phrase from "I cannot pay today", and the generic route "date is set → `check_offer`" runs before the refusal route and ignores `negotiation_reply = flat_refusal`. The check has no way to know the date was refused. (In T-024 the same sentence gave no date and `flat_refusal` only; extraction variance exposed the hole.)
**HEAD:** reproduced: `offer_date = "today"`, `negotiation_reply = flat_refusal` → `check_offer` accepts p1 for 2026-10-14. **Not fixed.**

**Generic fix**
- Route/ code: the "named a date" transition and the check require that `negotiation_reply` is not a refusal value of the spec (`product_end_values`/`attempt_values`, i.e. what `product_refusal` listens to). Put the refusal route **before** the date route, or add the guard to the date condition. A message that both refuses and names a date ("not today, Friday") is extracted by the model as `proposes…` per the field description ("Not today … are not refusal") so the guard does not lose real offers.
- Field description of `offer_date`: add "Empty when the date is one the customer says they cannot pay on." (builder/workflow.py:1661.)
- Self-check: a scenario "`I cannot pay <date word>`" with the extractor output `offer_date` set and `negotiation_reply = refusal`; the expected result is a persuasion attempt, no accepted offer.

---

## 5. PUB-11 in_words, d66add87: p1 `create_promise` failed, `service_error` note

**Timeline**
| t | Event |
|---|---|
| 29.3 | "I cannot pay today. I can pay all three this Friday." → date, `offer_product_name = all three`, `negotiation_reply = counter_proposal`. |
| 35.3 | `check_offer` accepts all three for 16 October; read-back, customer confirms (37.6). |
| 39.3 | `create_promise` p1 → **`function_call_error: API request failed: <!DOCTYPE html> … Worker threw exception | freya-bank-mock.freyavoice.workers.dev | Cloudflare`**. No bank record exists for it (ledger calls 4–5 are only p2 and p3). |
| 39.8 | The record loop retries once (as the brief's tool-failure rule says): the same error. |
| 40.4 / 41.3 | p2 and p3 succeed (pr1, pr2). |
| 41.9 | Closing writes the note `service_error` for p1 (the table row for a failed record), outcome `promise`; sentence "I am sorry, I could not record every promise…". |

**Root cause:** the bank mock itself threw an HTML 500 (Cloudflare Worker exception) for p1 twice, 0.5 s apart; p2 and p3 with the same body shape worked. The same error text is in the 13:18 PUB-08 call (`user-fdee69c8…`, 13 occurrences), so it is a mock flake, not our request (body `{customer_id, product_id, date, amount}` identical in shape to the successful ones).
**Builder behaviour is correct:** one retry, no success claim, an honest line, the `service_error` note, the promises that did succeed. Nothing to change in the render.
**Possible hardening (optional, low value):** a failed call 0.5 s after the first one gives a transient fault little time; code steps cannot sleep, so a delay is only possible by putting a spoken line between attempts, which would add a turn and may break the brief's wording. I recommend not doing it. Re-run the case; if the mock stays down for one product, no builder change can make it pass.

---

## 6. PUB-12 corrects, 0a0e8a46: persuasion attempts

Judge: "the 'refused' note for the personal loan was only logged after a third attempt, making the prompt count incorrect" (text truncated in the log).

**Timeline**
| t | Event |
|---|---|
| 18.7 | "I will pay the credit card tomorrow" → p1 accepted for 15 October. Line moves on to the personal loan (1320). |
| 21.7 | "I am not paying the personal loan." → refusal 1 of p2 (late band: 2 attempts) → persuasion left. |
| 23.1 | Agent (model) persuades with the minimum 440. Good. |
| 25.0 | "I am not paying **that loan**." → `offer_refused_product_name = 'that loan'`. In the built v20 code the shared word "loan" **plausibly names both loans**, so one refusal is charged to **p2 and to p3** (the car loan, early band, 1 attempt). |
| 26.8 | The model says "I understand. Let's move to your car loan… Can you pay 140 on Friday, 16 October?" although the discussed product is the personal loan with an attempt left (the line "Talk only about the personal loan" is in the prompt). |
| 28.7 | "I won't be paying the car loan." → p3 already had its single attempt used by the charge at 25.0 → **p3 ends at once** (note), the loan comes back: "Now let us look at the personal loan…" (33.5). |
| 34.7 | Third refusal of p2 → ends. Notes p2, p3 `refused`; promise p1. Ledger correct, but the sequence of attempts is not what the checks expect ("two attempts on the loan, one on the car loan"): the car loan got one model-made proposal at 26.8, charged before it was asked, and the loan's attempts were interleaved. |

**Root causes**
1. **A pointer word charged two products.** Fixed in HEAD by T-031: `that loan` now falls back to the product under discussion (`named_product_numbers`: "if not named and discussed in plausible → the discussed one"). My probe on HEAD with the same refusals gives `used {"2": 2}` after "that loan" (p3 untouched), p3 getting its own attempt at its own refusal, and p2 ending at its third refusal.
2. **The model leaves the product under discussion by itself** at 26.8, in spite of the prompt line. That is model variance; the code state (`offer_discussed_product`, attempts) says personal loan. Partly open. What the code can do: put the facts of the discussed product into the prompt (name, amount, deadline) instead of the whole account facts list in persuasion turns, so there is nothing about the other products to talk about. File: `builder/workflow.py` (`product_notes.add_product_steps`, the negotiate copy used after `product_refusal`) and `builder/prompts.py` `PERSUASION_*`.
3. Judge wording: the check counts proposals, the code counts refusals. Both give the same count when the model stays on the product; the interleaving at 26.8 broke it.

**Self-check:** the pointer-word scenario ("that loan", "this one", "it") now exists via T-031's tests; add one scenario where a refusal of the discussed product must leave the other products' attempt counters at 0.

---

## Order of work (my recommendation)

1. **Case 4** (negated date): one condition + one description sentence; reproduced on HEAD; touches every refusal that mentions a day word. Highest value.
2. **Case 3, part 2** (no "which product" for the revised or only product): one fallback in `pick_products`; reproduced on HEAD.
3. **Case 2, A+B** (topic value beats the date route; question rules become side-question paths): fixes the family of "question inside a business message".
4. **Case 3, part 1** (date at the read-back correction goes straight to the check).
5. Case 6 part 2 (prompt facts limited to the discussed product): optional, model-dependent.
6. Cases 1 and 5: environment; re-run only.

## Live checks after the fixes (CTO, with approval, chat first)
- PUB-04 with the robot question in the same message as the date and with a self-correction.
- PUB-07 with "Monday", then "Monday the 26th" at the read-back; expect no second date question and no "which product".
- PUB-11 with "I cannot pay today" followed by "all three this Friday"; expect p1 on 16 October.
- Re-run PUB-01 and PUB-11 in_words once more to confirm they were environment.
