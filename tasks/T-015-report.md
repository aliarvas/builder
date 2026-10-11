# T-015: before-identity fixes from the voice call (F-069 … F-072)

Source: `tasks/T-013-voice-call-review.md` findings C1–C4. All changes are generic: framework values and fixed lines, no brief value. No Freya, no model call, no commit, no env.sh.

## What changed

**C1 / F-069: a third party who is the customer goes back to the confirmation.**
- `spec.py`: a framework value `THIRD_PARTY_CUSTOMER_VALUE = "customer_on_line"`, next to `greeting` and `none`.
- `workflow._add_customer_return`:
  - adds the value to the third-party intent enum, with a description from the new prompt `THIRD_PARTY_CUSTOMER_DESCRIPTION`: "customer_on_line: the person says they are the customer themselves, or the customer has come to the phone";
  - adds a route `third_party` → `third_party_customer` (a new code step) → `opening_reask`.
- The code step resets the third-party intent and the who-answered value to `none`. Neither old answer can route again, so the confirmation question decides: a confirmation goes to `identity_check` → `identity`, as from the opening.
- The route sits before the callback entry: a person who says they are the customer is verified rather than booked for a callback.
- `third_party_ask` (the callback re-ask copy) gets the same value and route, because it is cloned after this change.
- If a spec already uses that value name, nothing is added (tested).
- `builder/callback.py` (claude-dev2, T-014) is not touched. The value is added in `workflow.py` after `third_party_extraction_fields`.

**C2 / F-070: no security questions before identity.**
- New fixed prompt `NO_SECURITY_QUESTIONS_LINE`: "Never ask security questions or for personal data in this step; only the program verifies identity, later."
- It goes into `opening`, `opening_reask`, `third_party` and `third_party_ask` (`BEFORE_IDENTITY_STEPS`).
- `opening_unclear` is a code step with no prompt; the step it hands over to, `opening_reask`, gets the line.

**C3 / F-071: every opening value is described.**
- `who_answered_description(spec)` renders `WHO_ANSWERED_DESCRIPTION`, one line per route, with the spec's own values:
  - confirm values: "the person clearly confirms they are the customer", followed by the documents' rule (`opening.unclear_instruction`, spec text);
  - third-party values: "only when the person clearly says they are not the customer (for example someone else's name, "she is not here", "I am his wife")";
  - close values: "only when the person clearly says what that value names";
  - stay values: "anything else that does not confirm, including a garbled or half-heard answer, an answer in another language, or a question back";
  - `greeting`: as before.
- A route without values gets no line.
- This text goes to the extraction model, so it is not counted in the prompt budget.

**C4 / F-072: no goodbye outside the closing.**
- New fixed prompt `NO_GOODBYE_LINE`: "Never say goodbye or end the call yourself; the program closes the call."
- `_apply_fixed_lines` adds it, before the tool-use rule, to every conversation step (`task_message` and `loop_prompt`) except one whose route ends the call (`CALL_END_STEPS`: `end_call`, `close_attempt`).
- In today's render no conversation step has such a route: `closing_say` is a code step with a fixed spoken line. So every conversation step gets the line, special-path steps included.
- This is right even for steps that route to `closing`: `closing_say` says the goodbye there, so a goodbye from the model would be said twice.

**Self-check (`builder/selfcheck.py`, my own function):**
- `_customer_return_scenarios` plays: third party → `customer_on_line` → confirmation at `opening_reask` → identity → offer → confirmation → promise. The expected ledger is the normal promise and notes.
- It is called next to `_third_party_scenarios`. claude-dev2's T-014 functions are not touched; I re-read the file before the edit.
- It passes on all 10 fixtures and recorded extractions. With the route removed, the scenario fails as BUILDER ("dead end at third_party").

**Prompts:** three new definitions in `PROMPTS`, `WHO_ANSWERED_DESCRIPTION` rewritten, and `docs/PROMPTS.md` regenerated.

## Tests

`python3 -m unittest`: **537 tests OK**, 8 of them new in `tests/test_before_identity.py`.
- **Prompt lint (C4):** in every fixture render, each conversation step has `NO_GOODBYE_LINE` exactly when it has no call-end route, in `task_message` and `loop_prompt`.
- **Prompt lint (C2):** the security line is in exactly the before-identity steps, and all four exist in every render.
- The fixed lines come before the tool-use rule.
- **C3:**
  - every enum value of the opening field (except `none`) is described;
  - third-party and stay values carry the new wording, and the documents' rule is included;
  - no placeholder is left;
  - a route without values has no line.
- **C1:**
  - value, description and route are in `third_party` and `third_party_ask`;
  - the reset step clears both answers and goes to `opening_reask`;
  - a spec that already uses the value keeps its own routes.
- **Self-check:** the scenario passes, and the lost-route mutation fails as BUILDER.
- **Leak test:** green. My first placeholder key `unclear` was caught by it (a fixture value) and renamed to `stay`.
- **Changed test:** `test_notes_outcome.test_brief_a_renders_byte_identically` (T-011's pin) is re-pinned. T-015 changes Brief A's render on purpose. I compared it field by field with the earlier render, and every difference is from T-015 except `callback_check` code, which is claude-dev2's T-014 work in progress. **If T-014 changes the callback code again, this pin must be updated too** (the comment says so).

## Prompt budget (estimate in tokens, character/4 with the system prompt)

| Spec | opening | opening_reask | third_party (+ask) | identity | negotiate / offer_say / revise_ask | confirm_record | other conversation steps |
|---|---|---|---|---|---|---|---|
| spec-brief-a | 330 → 375 | 282 → 327 | 238 → 283 | 597 → 615 | 710 → 728 | 361 → 380 | +18/+19 |
| brief-a, live (`traces/brief-a.spec.json`) | 611 → 656 | 564 → 609 | 513 → 558 | 959 → 977 | **1457 → 1476** | 632 → 651 | +18/+19 |
| brief-a-v11-extracted | 623 → 668 | 568 → 613 | 564 → 609 | 952 → 970 | 1395 → 1413 | 652 → 670 | +18/+19 |
| spec-brief-b | 303 → 348 | 255 → 300 | 237 → 282 | 580 → 598 | 704 → 722 | 362 → 380 | +18 |
| brief-ab-extracted-v2 (A+B) | 630 → 675 | 581 → 626 | 600 → 645 | 991 → 1009 | **1639 → 1658** | 774 → 793 | +18/+19 |

- The before-identity steps grow by 45 tokens (both lines); every other conversation step by 18–19 (the goodbye line).
- **Live Brief A:** negotiate goes from 1457 to 1476, still over the target 1200 and still under the hard limit 1500, as before.
- **A+B v2:** negotiate was already over the hard limit (1639) and is now 1658. The build never stops for this (T-009b), and the budget stages run as before.
- Putting the goodbye line in the system prompt would not save anything: the estimate (and the model) counts the system prompt in every step. The lint test also needs the line per step.
- If the negotiate budget needs room, the place to look is the negotiate prompt itself (T-009d), not these lines.

## UAT (CTO)

Proposed status for F-069, F-070, F-071 and F-072: "fixed offline (T-015); live check open".

**Live check (with approval), chat first:**
1. A relative answers, then hands the phone over ("here she is" → "yes, speaking"). Expect `opening_reask` → identity, with no security question before it.
2. An unclear opening answer ("…is that me?") → asked again, not `third_party`.
3. A third party who says goodbye → no "Goodbye." from the model; the call goes on or closes through `closing_say`.

## Notes

- The opening reask after a customer return asks the confirmation question again, even when the person already said their own name (rule 3 counts that as confirmation). That is one extra turn, chosen because "the customer comes to the phone" is a new speaker who must be confirmed.
- The reset step also clears the who-answered value, so the unclear counter in `opening_unclear` is not reset. A person who was unclear twice before the third-party step would close on the next unclear answer. That is rare and follows the brief's limit.
