# AB-FRESH: fresh A+B spec in the offline simulations

Spec: `traces/ab-fresh.spec.json` was copied to `tests/fixtures/extract/brief-ab-extracted-v2.json` unchanged. Freya, commit and env.sh were not used; no code was changed.

## What changed (tests only)

- `tests/test_multi_ready.py`:
  - added `"v2"` to `AB_SPECS`, so it runs in PUB-11/PUB-13, PUB-12 promise + outcome, `test_record_loop` PUB-11 and the `test_product_notes` structure test (all fixtures);
  - added v2 to the PUB-12 notes test;
  - the persuasion counting test now reads the attempt value from the spec and runs on `tagged` + `v2`.
- `tests/test_record_loop.py`: added v2 to the "p2 fails twice → p1, p3 recorded, p2 service_error" test.
- `python3 -m unittest`: 378 tests OK.

## Results (v2)

| Case | Ledger | Outcome | Notes |
|---|---|---|---|
| PUB-11 | p1 220, p2 640, p3 75 on 2026-10-16 ✅ | promise ✅ | none ✅ |
| PUB-12 | p1 510 on 2026-10-15 ✅ | promise ✅ | p2 refused, p3 refused ✅ |
| PUB-13 | p1 300 on 2026-10-30, p2 900 on 2026-10-23 ✅ | promise ✅ | none ✅ |

- No platform rejections (rejected = []).
- Record failure (PUB-11, p2 fails twice): p1 and p3 are recorded, the only note is p2 `service_error`, the outcome is `promise` and the closing starts with "I am sorry, I could not record every promise."
- Transfer: no notes. Hardship declined (close state written in code): `no_promise/hardship`, every product noted `hardship`. Dispute on p2 + refusals: notes p1/p3 refused, p2 not repeated.

**Product names are in words:** `product_kind_field=type` and `product_label_field=card_last4`. The bank lines say "credit card ending 2288", "personal loan" and "car loan"; `products_facts` and the read-back do the same ("credit card ending 9015 …").

**Persuasion attempts match the brief:** Brief A table: early band (1–7) 1, late band (8–45) 2. v2 `persuasion_attempts` is days_late 1–7 → 1 and 8–45 → 2. In PUB-12 the personal loan (16 days late) gets 2 attempts, the car loan (7 days late) gets 1, then the product ends and is noted `refused`. Intents: `attempt_values=[flat_refusal]`, `product_end_values=[refuses_after_attempts]`.

## Risks / proposals (not fixed)

1. **A product can end without its attempts (live risk).** If the model writes `refuses_after_attempts` on the first "no", code ends the product immediately, and the attempts are not used (Brief A rule 30, judge policy). Two things invite this:
   - The extraction description gives two meanings: the first sentence says "refuses_after_attempts, refuses_to_talk = the customer refuses any payment… after being asked for alternatives", and the F-061 sentence says it ends only the current product.
   - Proposal: when the spec has `persuasion_attempts`, treat a `product_end_values` value as one attempt while attempts are left (the product ends only once they are used up). Alternatively, say clearly in the description that this value is only for after the attempts.
2. **negotiate is ~1744 tokens** (tagged 1627). v2 has 26 negotiation rules (tagged 18).
   - 4 rules are copied word for word in `offer.rules` (full amount too much, below the floor, vague period, date after the deadline), about 440 characters.
   - The rule "For each product that ends without a promise, call add_note…" is now handled in code (negotiate has no tools), so it only costs tokens and could make the model say "I will note it".
   - Proposal: when rendering, skip a negotiation rule whose text is the same as an offer rule, and skip rules covered by `closing.product_notes` (like `enforced_by`).
3. **Accepted but not recorded, with no recording attempt.** If hardship is declined (or the call closes another way) after p1 was accepted but before the read-back, p1 gets `service_error` (finding-1 rule: accepted but unrecorded → failed_reason). No recording failed, so `hardship` (the close reason) is the better note. Proposal: use `failed_reason` only if the product had a record attempt (`promise_attempts_N > 0`); otherwise use the normal order. This is not in the public cases.
4. **Python warning (low):** the generated code at `builder/offer_check.py:285` has `r'^\s*-\s*\d'` inside a non-raw PRELUDE string, which gives a `SyntaxWarning` (it is an error in future Python versions). Proposal: `\\s`/`\\d`, like the line next to it.
5. The v2 Brief B rule "no_promise with the reason of the first non-paid note" is not implemented in code (the same open point as F-061-062). With dispute on p2 and p1 refused, the result is accidentally correct (refused).

## UAT status proposal

- F-061/F-062: offline OK on the fresh A+B spec. Live chat (PUB-11/12/13) is still needed; watch risk 1.

## Fix (AB-FRESH follow-up for F-061/062)

**Risk 1: an end value is counted while attempts are left.**
- Change in `builder/offer_check.py` `PRODUCT_REFUSAL_BODY`: when the spec has `persuasion_attempts`, a `product_end_values` value also uses one attempt while attempts are left. The product ends only when its attempts are used up (or when no band rule matches, finding 5). Without `persuasion_attempts`, the old behaviour stays: the end value ends the product at once.
- Extraction description: new `PRODUCT_END_COUNTED_DESCRIPTION` in `prompts.py`, added only when the spec has attempts: "The bank system counts the persuasion attempts and ends the product only when they are used up; while attempts are left, {product_end} also uses one attempt. For any no about the product being discussed, choose {attempt}." The general first sentence of the description ("...after being asked for alternatives") is in `workflow.py` (claude-dev2's render code); I did not touch it.
- `PERSUASION_STATE_LINE`, `PRODUCT_INTENT_DESCRIPTION` and the new definition were missing from the `PROMPTS` list, so they were not in `docs/PROMPTS.md`. I added them and regenerated `PROMPTS.md`.

**Risk 3: `failed_reason` only after a record attempt.** The note loop (`NOTE_NEXT_BODY`) gives `failed_reason` only to an accepted product that is in `promises_failed_numbers` or has `promise_attempts_N > 0`. An offer that was accepted but never sent (the call closed before the read-back) follows the normal order: the reason marked by code, then the close reason, then `refused_reason`. `note_next_code` now takes the failed list (`product_notes.py` passes `FAILED_NUMBERS`).

**Risk 4: escape warning.** `offer_check.py:285` inside PRELUDE is now `r'^\\s*-\\s*\\d'`. The generated code is unchanged (`r'^\s*-\s*\d'`); only the module-level `SyntaxWarning` is gone.

**Risk 5: not done (proposal).** The spec has no data for this rule. "No promise: all paid → paid; otherwise the reason of the first non-paid note" exists only as `closing.rules` text. In the `outcomes` table the `paid` row has `on=()`, and there is no structured field. Writing it in code would be hardcoding from the brief. Proposal: an optional `closing.product_notes.outcome_from_notes` block, for example:
- `{"when_no_promise": true, "all_reason": "paid", "all_outcome": ["paid", ""], "otherwise_outcome": "no_promise", "reason": "first_other_note"}`
- Extraction schema, prompt, check and evidence for it, like the other optional blocks (dropped if it is invalid).
- The closing code would compute the outcome from the notes in account order after the note loop. The note loop then has to run before the outcome, so closing and note_next must change order; this touches claude-dev2's closing code, so it needs coordination.

**Risk 2:** not touched (claude-dev2, T-009d).

**Tests:**
- `test_multi_ready`:
  - new `Session.end_product()`, which refuses until code ends the product;
  - `test_an_end_value_with_attempts_left_uses_an_attempt` (tagged and v2: loan 2, car loan 1);
  - `test_without_persuasion_attempts_an_end_value_ends_the_product_at_once` (fixture-b);
  - the PUB-12 notes test now uses `end_product`.
- `test_product_notes`:
  - `test_an_accepted_offer_never_sent_takes_the_close_reason` (v2: card accepted, hardship declined → p1/p2/p3 hardship);
  - `test_a_product_whose_record_call_failed_keeps_the_failed_reason` (tagged and v2);
  - `GeneratedCodeTests`: builder modules and all generated code steps compile with `SyntaxWarning` as an error. Checked: on the old line this test fails.
  - The named-product, fallback and special-path tests now refuse until the attempts are used up.
- `python3 -W error::SyntaxWarning -m unittest`: 385 tests OK. During the run claude-dev2 was editing `callback.py`, `workflow.py` and `prompts.py`. Failures seen in between (leak test `callback.py`, third_party end paths, calendar text, budget) went away in the final run; they were not in my files.

Freya, commit and env.sh were not used.
