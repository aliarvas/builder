# T-029: a goodbye exit at every conversation step

Generic, no brief value. No Freya, no model call, no commit, no env.sh. `python3 -m unittest`: **623 OK**, including the leak test and the prompt budget guard.

## How it works (`builder/goodbye.py`)

**One decision step, `customer_goodbye` (code, a normal step).** It counts the goodbyes and chooses where to go:

| Situation | Goes to |
|---|---|
| Accepted offers and the first goodbye | `confirm_record`: the code-built read-back, once (as in T-027) |
| Identity passed | `close_state` = the hang-up state → `closing` (notes, outcome, close_call) |
| Before identity, the person who answered is a third party (`who_answered_variable` in `third_party_values`) | the third party's close without a callback: `third_party:` + `callback_window.outside_close_value` (else the first third-party close value) → `closing` |
| Before identity, otherwise (opening, identity) | the state the end-of-call hook would write → `closing` |
| A second goodbye | always one of the closes above, never the read-back again |

**The states follow the hook's order (`goodbye_states`).**
- Before identity: `hangup_unverified` if a row maps it, else `hangup`, else `default`.
- After identity: `hangup` if mapped, else `default`.
- Before identity there are no products, so the closing writes no notes and calls only close_call.
- For the live A and A+B specs: `hangup`, `hangup_unverified`, `third_party:no_callback`.

**Two ways in:**
1. **Normal conversation steps, through the global step `customer_ends_call`.**
   - Its sources are every step that waits for the customer: opening, `opening_reask`, identity, third party and `third_party_ask`, the offer steps, the read-back, and the special-path steps among the normal steps.
   - It hands over to `customer_goodbye`. Its exit becomes `GLOBAL_EXIT_CONDITION` through claude-dev2's T-028 post-pass.
2. **Global conversation steps, through a choice value of their own.**
   - These are the special-path asks, such as the support and human-request questions.
   - The platform never starts a global step from a global step: every global is excluded from the others.
   - So their choice field gets the value `ends_call` (`GOODBYE_CHOICE_DESCRIPTION`) and a first route to `customer_goodbye`.
   - Passthrough global lines (scam, robot and unknown answers) do not wait for the customer, so they need nothing.

**Intent, made stricter (`CUSTOMER_ENDS_CALL_INTENT`):** "The customer only says goodbye or thanks to end the call: not an answer to a question, no refusal, no offer and no question."

## Identity (task item 3)

**Decision: the global step, not the step's own route.**
- The kit says to exclude identity from interrupts *where an interrupt would do harm*. That is guidance, not a rule that makes a global impossible.
- A global fires only when the step's own routes found no match. The intent rules out an answer to a question.
- **Own route considered and not chosen:** the identity step has no extraction field. An own route would need a new field and an extraction call on every identity turn, with the same risk of a wrong reading.
- **Cost of the global:** the routing model checks one intent on identity turns that match no route.
- **Risk:** a wrong match would end the call at identity. If live runs show that, the fallback is a goodbye field on the identity step.

## No routing shadow (item 4)

- The opening and third-party choice fields now get `special_topic`, whose description names the goodbye.
- This is done by T-023's `_add_special_topic`, because the goodbye step is added before it.
- `intent_shadow` is green on every fixture and on the live specs.
- One existing test was updated: `test_multi_step.test_greeting_is_its_own_value_and_never_counts_as_unclear`. The opening enum is now `[…, greeting, special_topic, none]`.

## Self-check (item 5)

**Static check `goodbye_exit[<step>]` (BUILDER).** Every conversation step that waits for the customer needs one of two exits:
- the global goodbye step is active there; or
- it has a route of its own to `customer_goodbye`.

**Goodbye family:**
- **Steps covered:**
  - `goodbye_opening`, `goodbye_identity`, `goodbye_third_party`;
  - `goodbye_special_<id>` for every special path with a question;
  - `goodbye_negotiate`, `goodbye_at_readback`, `goodbye_after_one_offer`.
- Each checks the outcome row and notes, the end at end_call, and the number of goodbye turns (1, or at most 2 with accepted offers).
- The `goodbye` action now also handles a global ask step: it sets the choice field to `ends_call`.

## Tests (`tests/test_goodbye_every_step.py`, 7)

- **Static check:** no gap on all 10 fixtures and the live Brief A and A+B specs (12 renders).
- **Mutation:** identity is taken out of the global step, and the own route is removed from one global ask step. The check names both, and the self-check reports `goodbye_exit[identity]` and `goodbye_exit[<ask>]`.
- **The goodbye value:** every global ask step has the value, its description and the first route.
- **States:** the hook order is followed, including fallbacks when a spec maps neither hang-up state and has no callback window.
- **Play on both live specs:** goodbye at the opening, identity, third party, every special-path question and negotiate all pass.
- **Without the goodbye step:** the same plays fail.

## Shared files and coordination

- **claude-dev2 (T-030):** changed only `PERSUASION_STATE_LINE` / `PERSUASION_PRODUCT_LINE`. My `prompts.py` changes are other definitions:
  - `CUSTOMER_ENDS_CALL_INTENT` (wording);
  - new `GOODBYE_CHOICE_DESCRIPTION`.
- **`workflow.py`:** one line (the `add_goodbye_exit` call now also passes `spec`).
- **`selfcheck.py`:** the goodbye action for global ask steps, the new scenarios in my goodbye family, and the static check in `run_selfcheck`.
- **`docs/PROMPTS.md`:** regenerated.
- **Brief A pin:** re-pinned to `dde9db86…`. It moves because of the opening and third-party `special_topic` value, the goodbye value on the global ask steps and the `customer_goodbye` step. claude-dev2 confirmed T-030 does not move it.

## Risks

- **Extraction descriptions grow:** the opening and third-party descriptions now carry the special-topic sentence, and the global ask steps carry one more value sentence. These go to the extraction model; the phone-agent prompt budget is unchanged.
- **An unclear opening answer:** "special_topic" at the opening routes nowhere, as "greeting" does. If the intent then does not match, the step simply waits.
- **Not live-checked:** a global intent check at the identity step and at the opening (see Identity above). One chat run should play a goodbye at the opening, identity and a special question.

## UAT (CTO)

Proposal: "PUB-12 follow-up: a goodbye had no exit outside the offer steps". Fixed offline (T-029). Live retest: a chat run with a goodbye at the opening, identity, the third party and a special question, each ending at `end_call` with one close_call.
