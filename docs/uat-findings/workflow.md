# Workflow Review: Brief A, version 17 output

**Owner:** Design review of one workflow the builder produced. Linked from [`../UAT-FINDINGS.md`](../UAT-FINDINGS.md).

- **Date:** 2026-10-11
- **Source:** the workflow JSON the builder rendered for Brief A (version 17), read offline. Nothing was run on Freya for this review.
- **Status of all items:** open. No task has been given to the developer yet.
- IDs `W-01`, `W-02`, ... are review items. When one is confirmed by a live run, it gets an `F-` entry in `UAT-FINDINGS.md` that links back here.

## Verdict

The architecture is in the right family: the model speaks, code decides (offer check, closing table, code-driven promise recording, hang-up close). It has not reached its ceiling. Three problems: the same code is copied into many nodes, decisions are spread over three places (global intent nodes, transition lists, the closing rule table), and there are several visible logic faults (W-01 to W-07).

## Logic faults (most severe first)

### W-01: Hardship support question can read "yes, connect me" as "stay"

- **Symptom (expected):** The customer accepts the transfer, but the extraction picks `stay`; no transfer, the call returns to negotiation.
- **Cause:** The hardship confirm node reuses the human-request template. Its choice field says "proceed: still insists on this request; stay: they accept help or drop it". For the hardship question ("connect you with customer support?"), accepting help means proceed, so the meaning is inverted.
- **Category:** routing
- **Fix / lesson:** Write choice descriptions from the question actually asked (yes to the question / no to the question), not from one shared template.

### W-02: Declined hardship is not reachable in the normal flow

- **Symptom (expected):** Customer mentions hardship, declines support, then refuses to pay: ledger gets `no_promise / refused` instead of the hardship outcome.
- **Cause:** The hardship-declined global node is excluded while the hardship confirm node is active, and that node's "no" leads to `stay` (back to negotiation). Related to F-065 (path missing from extraction); here the path exists but routing cannot reach it.
- **Category:** routing
- **Fix / lesson:** A "no" in the hardship confirm node must route to the declined-hardship close state directly.

### W-03: Failure closes say "I could not record your promise" when no promise was discussed

- **Symptom:** Account read failure and failed transfer both speak the promise-failure sentence; the failed transfer adds a second sentence before it.
- **Cause:** Same as F-075 (account case); the special-tool-failed state has the same problem.
- **Category:** honesty
- **Fix / lesson:** Each failure state speaks its own sentence. See F-075.

### W-04: Account read failure may not be detected

- **Symptom (expected):** If the account tool returns HTTP 200 with `ok` false, the call goes on to the offer setup with "No products were returned" and negotiates on nothing.
- **Cause:** The account node leaves on the platform failure counter, which most likely counts only transport failures. The post-process sets `ok` to false but nothing routes on it.
- **Category:** tool-call
- **Fix / lesson:** Route the account node on the mapped `ok` value as well as the failure counter. **[TO-CONFIRM]** what the failure counter counts.

### W-05: Identity "declined" path has no code route; turn limit closes unverified callers as refused

- **Symptom (expected):** A customer who keeps asking "what is this about?" instead of answering is never closed as `not_verified / declined`. The model can loop until the turn limit, which closes as `no_promise / refused`.
- **Cause:** The identity node has no extraction field or transition for declining; only the "does not want to talk twice" global node can end it, and that intent does not match a question. The turn-limit close state does not check whether identity was verified (the hang-up close does).
- **Category:** routing
- **Fix / lesson:** Add a decline value to the identity step and count it in code. The turn-limit close picks the unverified row when identity is not verified.

### W-06: Opening question uses single braces, so the name is not filled

- **Symptom (expected):** The model may read the raw placeholder aloud ("Am I speaking with {title} {last_name}?").
- **Cause:** The opening and re-ask prompts write the confirmation question with single braces; only double braces are substituted.
- **Category:** prompt
- **Fix / lesson:** Use the substitution syntax in every spoken template; add a render check for single-brace placeholders.

### W-07: The "unknown information" global node is too broad

- **Symptom (expected):** In the identity step, "why are you calling?" can trigger "I do not have that information", which is a policy error.
- **Cause:** Its intent is "a question the tools cannot answer", which covers almost any question, and it is active in opening and identity.
- **Category:** routing
- **Fix / lesson:** Narrow the intent and exclude it from steps that have their own rule for questions.

### W-08: Platform default `agent_config` uses Turkish speech settings

- Already logged as the `agent_config` language finding in `UAT-FINDINGS.md`. Matters for voice runs only. **[TO-CONFIRM]** with the organizers.

## Architecture observations

- **Same helper library embedded five times.** The ~400-line date, limit and product-name helpers are copied into the offer check, offer setup, callback check, product refusal and promise pre-process. The workflow is larger than it needs to be, and the callback copy carries dead code that refers to config keys it does not have.
- **Three near-identical negotiation nodes.** Negotiate, offer-say and revise-ask share the task message, seven extraction fields and four transitions; only the entry line differs.
- **Brief rules pasted into node prompts.** The negotiation prompt carries about 25 rules, some repeated, many of them already enforced by code. Nodes without tools still say "call create_promise only after a clear yes", then a patch line says the program does it. The model reads contradicting instructions.
- **14 global intent nodes.** Each one is a misfire risk on every customer turn (dispute vs already paid, unknown information swallowing questions), and none can be simulated deterministically by the self-check.
- **Decisions in three places.** Global intents, node transitions (with true/True duplicates) and the closing rule table. To explain one outcome you must read all three.

## Proposed direction (not started)

1. One `intent` enum field on each conversation node, including the special paths. Remove the global intent nodes except one-line answers that return (robot, scam).
2. Every conversation node goes to one router code node that computes the next step from the variables. One state machine, one place, and the self-check can simulate it exactly.
3. Conversation node prompts carry only what the model must do in that step. The builder splits brief rules into "model work" and "code work".
4. Merge the negotiation nodes if the entry line can come from a variable; otherwise render them from one definition.
5. Shared library: one node stores the helper source in a variable and the others run it. **[TO-CONFIRM]** that the code sandbox allows it (needs a live test, so approval first). Low priority.

**Order if time is short:** fix W-01, W-02 and W-03 first (direct score loss), then W-04 to W-07 (small changes), then the architecture.
