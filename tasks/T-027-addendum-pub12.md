# T-027 addendum: PUB-12 loop, CTO reading of the call record

Record: `traces/live-runs/user-1c73c93a-85f6-46b7-a0cc-55ef6c18a5ae.json` (message indexes below).

1. **The finished product list goes back to negotiate.**
   - Msg 107: after the last product was refused, `product_refusal` routed to `negotiate` with the reason "Persuasion attempt left always", although every product was handled (p1 accepted, p2 and p3 refused).
   - It should have gone to the readback/record step.
2. **The negotiate LLM spoke a false result and a goodbye.**
   - Msg 109: "I have recorded your promise … Thank you for your time." No tool had run, so this is an honesty failure.
   - negotiate must never say "recorded" and must never say a closing line; it cannot end the call.
3. **No exit for goodbye.**
   - Msgs 110-137: "Thank you, goodbye." is extracted as `negotiation_reply=none`, so no route matches and the step says "Thank you for your time" again and again.
   - Msg 138: it finally went to `confirm_record` through `refuses_to_talk`. But that step waits for `readback_reply`, the LLM never read the promise back, and no route matched until max duration.
   - The fix must be generic: every conversation step needs a route for "the customer ends the call". It goes to the closing chain (record accepted promises, notes, close_call). `confirm_record` must say the readback in its own spoken text, so the step cannot stall.
4. **A refused product is asked again.**
   - Msgs 73-97: after "Yes, I confirm" the flow went `check_offer` → `offer_say`, which asked for the personal loan a second time. The judge counted this as two attempts.
   - A product already refused (or one whose persuasion is used up) must not be asked again.
5. **The accepted promise is lost.**
   - The ledger has no promise and a "refused" note for p1, which the customer had accepted. Check why: whether the end-of-call hook writes notes for every product, or the accepted list was reset.
6. **Self-check gaps to add as scenario families (generic):**
   - The customer says goodbye at any conversation step: the call must reach end_call within 2 turns.
   - Mixed products (one accepted, others refused): one promise is recorded, notes are written only for the refused products, and each refused product is asked once.
   - No LLM step may say "recorded" before a successful tool result.
