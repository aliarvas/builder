# T-021 report: PUB-05 and PUB-08 on Brief A version 18 (style asks_back)

**Owner:** claude (claude-dev2 role). **Type:** analysis only (15-minute timebox).
**Not done:** no code change, no Freya request, no commit, no env.sh.
**Inputs:**
- call records: `traces/live-runs/user-ced450f3-*.json` (PUB-05) and `user-022175c7-*.json` (PUB-08);
- spec: `traces/brief-a.spec.json`;
- workflow: `submission/brief-a.workflow.json` (version 18).

Times below are seconds from the start of the call.

## Summary

Both failures are **builder bugs**. Neither is model noise.

| Case | Root cause | Self-check can play it? |
|---|---|---|
| PUB-05 | The question "do you want support?" uses the generic `proceed`/`stay` choice of an ask-first path. That choice is written for a customer request ("still insists on this request"), not for an offer the agent makes. "I do not want to be transferred" was read as `proceed`, and the call was transferred. Even a correct `stay` would go back to `negotiate`, not to the `hardship_declined` close. | Partly. The `stay` routing yes (a structural check). The wrong reading of the words no. |
| PUB-08 | In `negotiate` the platform checks the step's own expression branches before the intent branches. The forced `negotiation_reply` labelled "I paid it in the app this morning" as a refusal, so `product_refusal` matched and the `already_paid` intent was never checked (`None`). | Yes, if the simulator follows the same order (step branches first, intents only when none matched) and a scenario plays a refusal-like label with the special intent. Today it does not. |

## PUB-05: the customer declined support but was transferred

**Expected:** `no_promise` / `hardship`. **Ledger:** `transfer_to_agent(queue=support)`, then `close_call(transferred, support)`.

**Timeline of the wrong part:**

| t | Event |
|---|---|
| 140.7 | `node_enter negotiate`. The agent asks for 780 today. |
| 164.7 | Customer: "I lost my job last month and cannot pay anything. Can I get a discount on this amount?" |
| 188.7 | `variable_extracted`: `negotiation_reply = proposes_terms`, `offer_amount_kind = none` (input: the sentence above). |
| 188.8 | `route_evaluated` from `negotiate`: `check_offer` False (no date), `product_refusal` False. Intents: `special_hardship_support` **True**, `special_restructuring_request` **True** (discount); `special_hardship_declined` False. The first match wins: `special_hardship_support`. |
| 188.8 | `node_enter special_hardship_support`; its line: "Would you like me to connect you with our customer support team?" The sympathy sentence (`say` of the path) is **not** said here. |
| 189.6 | Customer: "Which account is this about? I do not want to be transferred." |
| 198.5 | `variable_extracted special_result_hardship_support_choice = 'proceed'`. Input: the same sentence. Enum description: "proceed: the customer still insists on this request; stay: they accept help or drop it". |
| 198.5 | Route to `special_hardship_support_go`, then `transfer_to_agent {queue: support}` at 200.0 (ok), then `closing`. |
| 207.5 | "I am sorry to hear that. Thank you for your time. Goodbye." The sympathy sentence comes only now, after the transfer. Then `close_call(transferred, support)`. |

**Root cause (builder, `builder/workflow.py:570`):**
1. **A request choice used for an offer.** The ask-first node uses one generic choice for every special path that asks first.
   - For `human_request` the agent asks "Can I help you with something first?", and `proceed` (still wants a human) is the right reading.
   - For `hardship_support` the agent offers the transfer, and a "no" is the decline. There "the customer still insists on this request" has no clear meaning, and the model read "I do not want to be transferred" as `proceed`.
2. **A correct decline would still go wrong.** `stay` goes to `__previous__`, back to `negotiate`.
   - The brief wants an immediate close as `no_promise` / `hardship`, and no persuasion (rule 32).
   - Back in `negotiate` the agent would ask for payment again (a persuasion attempt).
   - It would close as hardship only if the customer repeated the decline and the global `hardship_declined` intent matched.
   - The spec has no link between the ask of `hardship_support` and the `hardship_declined` path; they are two separate paths.
3. **Smaller:** the path's `say` ("I am sorry to hear that.") is used as its closing line, so the sympathy comes after the transfer and not before the offer. The judge passed it this time.

**Generic fix proposal:**
- **Choice wording.** Generate the enum description from the path's own `ask` as a yes/no question:
  - `proceed` = "the customer answers yes to: <ask>";
  - `stay` = "the customer answers no, or wants to go on without it".
  - Risk: low. It changes the extraction text of every ask-first path, so `human_request` needs a check ("Can I help you with something first?" with "no" means proceed). The wording must follow the question's direction.
  - **Better: two fields in the spec**: `ask_yes: proceed|stay`, set by extraction from the brief. Risk medium (spec schema plus prompt).
- **Decline target.** Give an ask-first path an optional `on_decline: <path id>`. Here it would be `hardship_declined`, which the extraction can see in the same rule 32 sentence. When it is set, route `stay` to that path instead of `__previous__`.
  - Risk: medium. It is a schema change, and the self-check and render need it. The fallback (no `on_decline`) keeps today's behaviour.
- **Sympathy first.** For an ask-first path, say `say` before `ask` on entry ("I am sorry to hear that. Would you like me to …"). The closing line then does not repeat it.
  - Risk: low. For `human_request`, "I will transfer you now." must not come before the ask, so this needs a spec flag or must apply only when `say` is not a transfer line. **Needs care.**

**Can the self-check play it?**
- **The wrong `proceed` reading: no.** The simulator sets the choice value directly; it does not run extraction on words.
- **`stay` going back to `negotiate`: yes.** A scenario "hardship → asked → declines" exists only as a "two special paths" pair today (return, then path b). A scenario with the ledger "decline closes as the declined path's row" would fail on today's render, once the spec carries `on_decline`.
- Without `on_decline` the self-check has nothing to check against. The brief link exists only in the brief text.

## PUB-08: "already paid" closed as a refusal

**Expected:** `paid`, plus the sentence "Payments can take one business day to appear." **Ledger:** `close_call(no_promise, refused)`.

**Timeline of the wrong part:**

| t | Event |
|---|---|
| 151.3 | `node_enter negotiate`. The agent asks for 180 today. |
| 166.7 | Customer: "I paid it in the app this morning." |
| 173.7 | `variable_extracted negotiation_reply = 'refuses_payment'` (input: the sentence above). |
| 173.7 | `route_evaluated` from `negotiate`: `check_offer` False, **`product_refusal` True**. Every later branch is `None` (not evaluated): `confirm_record`, `closing`, and every intent, including **`special_already_paid` None**. |
| 173.7 | `product_refusal` code: an attempt is left, so back to `negotiate`. |
| 175.1 | The agent: "I cannot see that payment yet. Could you make the payment of 180 by this Friday, 16 October?" That is a persuasion attempt; "I cannot see that payment yet" is the model's own words. |
| 184.6 | Customer: "I already paid it in the app this morning." |
| 210.4 | `negotiation_reply = 'flat_refusal'`. Route again to `product_refusal` (True); `special_already_paid` again `None`. |
| 210.8 | `product_refusal_state = closing`, then `closing`, then `close_call(no_promise, refused)`. "Payments can take one business day…" is never said. |

**Root cause (builder):**
1. **Branch order.** The platform evaluates the step's own transitions first (`check_offer`, `product_refusal`, `confirm_record`, `closing`), then the global intent nodes, and stops at the first match.
   - Any special-path intent in `negotiate` can only fire when no step branch matched.
   - (PUB-05 worked only because `proposes_terms` without a date matched no branch.)
2. **A forced label.** The `negotiation_reply` description says: "none: only the system writes it; choose a value above". So the extractor must pick a value even for "I already paid". It picked the closest one, a refusal.
   - The list has no value for "the customer says something else" (a special topic), and the description does not name the special paths.
3. The same risk applies to every special path offered in a step with an expression branch on extraction (`dispute`, `restructuring_request`, `human_request` …) whenever the customer's words also look like a refusal or an agreement.

**Generic fix proposal:**
- **A new value.** Add one value to `negotiation_reply` (and to the other step-choice enums of steps with special paths), for example `special_topic`.
  - Its description is built from the `when` texts of the special paths offered at that step: "the customer says one of: <when 1>; <when 2>; … — choose this instead of a refusal".
  - No step branch matches `special_topic`, so the platform goes on to the intent branches.
  - Risk: medium.
    - The extractor may choose `special_topic` for a real refusal that mentions money trouble. No intent then matches, so the agent asks again in `negotiate`. That is safe, but costs a turn; the turn limit stays the bound.
    - It changes extraction in every case, so it needs a full chat run.
- **Alternative:** put the closing intents (e.g. `already_paid`, `dispute`) as step transitions **before** `product_refusal`.
  - Risk: high. The platform's intent matching inside step transitions is untested here, and the change affects every closing path.

**Can the self-check play it?**
- **Not today.** `play` enters a special path directly (`_special_entry`), so the step's expression branches never compete with the intent.
- **To catch it:**
  1. Model the platform order in the simulator: step transitions first; intent branches only when none matched.
  2. Add a scenario family "special path with a competing label". For each special path and step, the customer turn sets the step's closest refusal label and the intent.
     - The expected ledger is the special path's row.
     - On today's render it fails, because `product_refusal` wins.
     - With the `special_topic` fix the scenario sets `special_topic` and passes.
- This tests the routing rule, not the model's labelling. A static check helps too: "a step with intent-entered special paths must have an extraction value that matches no step branch". It would flag version 18 right away.

## Also seen (not the failures)

- **PUB-08:** the identity questions "Why do you need that?" and "Which account is this about?" went to `special_unknown_information` ("I do not have that information."), then back to the question. Correct and harmless, but stiff: the brief allows "These questions protect your account", and the next turn said it.
- **PUB-05:** `restructuring_request` also matched ("discount"). `hardship_support` won only because it is earlier in the list. That is the right outcome here, because rule 32 comes first. If the order is ever generated differently, the order of the special paths must follow "comes before" in the spec.

## UAT

To log in `docs/UAT-FINDINGS.md` (not edited, analysis only):
1. An ask-first offer is read with the request choice, and a decline does not reach the declined path (PUB-05).
2. Step branches hide special-path intents, because of a forced label in `negotiation_reply` (PUB-08).
