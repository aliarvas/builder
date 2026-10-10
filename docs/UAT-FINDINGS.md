# UAT Findings

**Owner:** Every observed failure of the builder or of a phone agent it built, and why it happened.

This is a findings log, not code. Each entry records **why** the builder produced a wrong or failing agent, so the same mistake can be recognized and tested again later. Treat it as UAT data.

## Rule

- Every failure gets an entry: a failed practice case, a failed self-test, a rejected workflow, a wrong outcome, a policy or honesty failure, a timeout.
- Write the entry when the failure is understood, even if it is not fixed yet. Update its status when it is fixed.
- Describe behavior and cause in words. Do not paste code or whole transcripts; link to the trace, call ID or file instead.
- Never write brief-specific values here as rules for the builder (see AGENTS.md priority 1). Describe the general pattern.
- Newest entry on top. IDs never change: `F-001`, `F-002`, ...

## Entry template

```markdown
### F-000: <short title>

- **Date:** YYYY-MM-DD
- **Brief / case:** <brief, case ID or test name>
- **Run:** <trace file, workflow_id, agent_id, call_id>
- **Symptom:** what went wrong (outcome, policy or honesty; what the agent said or did)
- **Root cause:** why the builder produced this behavior (extraction, rendering, routing, prompt, tool mapping, Freya behavior, ...)
- **Category:** extraction | routing | tool-call | honesty | policy | date-logic | platform | timeout | other
- **Fix / lesson:** what changed in the builder, or what should change
- **Status:** open | fixed (commit) | won't fix (reason)
- **Retest:** result after the fix (e.g. 3/3 runs passed)
```

## Findings

### F-050: A fixed spoken line on the account api step crashes the turn (502) and rolls the call back

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-07 chat on version 11, two runs; experiment on a copy
- **Run:** customers `c_4586bc52-288`, `c_674d92c1-105` (version 11); experiment workflow `b83e8dcd-170e-4164-83a7-6fc9d00bdd13`, customer `c_8680078c-41a`
- **Symptom:** In both version 11 runs, the turn that completed identity returned HTTP 502. Both identity calls and `get_account` ran (ledger), and the wait line was said, but the call state was not saved. The next customer message landed back in `identity` with the variables reset. The agent kept asking for the phone digits, nothing was recorded and no `close_call` ran. Ledger: fail.
- **Root cause:** Confirmed by experiment. The same workflow with only `account.on_enter` changed from a `tts` line to `silent` passed that turn without an error, and the platform's own Turkish filler came back (F-043). A `tts` `on_enter` on a passthrough `api_request` step that is followed by more passthrough steps and a conversation step breaks the turn on the platform side.
- **Category:** platform
- **Fix / lesson:** Revert F-043's fixed line on the api step (keep `account` silent). If a wait sentence is wanted, let the identity step say it in its last message after `all_verified`. Report the 502 + rollback to the organizers. Lesson: test every new `on_enter` form live before relying on it.
- **Status:** open
- **Retest:** -
- **Note:** the experiment workflow was created with `create_workflow` only, so it did not get the event model (`experimental-5`, set by `update_workflow`). Its later turns, where tool calls were written out as text, say nothing about our agent. The workspace now holds this extra workflow (the kit has no delete route).

### F-049: A 5xx turn can execute tools but lose the call state

- **Date:** 2026-10-11
- **Brief / case:** PUB-07, version 11 (see F-050)
- **Symptom:** After a 502 the ledger shows the tools of that turn, but the conversation resumes from the previous assistant message with the old node and variables.
- **Root cause:** Platform behavior on a failed turn. In our runs the trigger was F-050, but any 5xx (staging outages, F-023) can do the same.
- **Category:** platform
- **Fix / lesson:** The test driver's "turn was processed" check must look at the node and variables, not only the user message count. Design so a replayed step is safe: identity routing should also leave on `identity_verified` already true at entry. Ask the organizers.
- **Status:** open
- **Retest:** -

### F-048: Introduction repeated in the third-party step

- **Date:** 2026-10-11
- **Brief / case:** Brief A, official build run, self-test case `third_party_close` (version 11)
- **Run:** call `9fd0eeb0-9cf5-4004-86f2-600d7d99b4ee`, `traces/brief-a.log`
- **Symptom:** The opening already said "I am a digital assistant calling from Freya Bank and the call is recorded". After the routing to `third_party`, the agent said it again.
- **Root cause:** The global "say the introduction first if not yet said" rule (T-005d). The model cannot tell that it was already said in an earlier step. The T-005d review predicted this.
- **Category:** policy
- **Fix / lesson:** Track it in state: a variable set when the opening has spoken (the opening step is always first), and the rule appears only while that variable is unset, or the rule lives only in the steps that can be reached first.
- **Status:** open
- **Retest:** -

### F-047: Closing sentence spoken as an instruction ("Thank the customer and say goodbye.")

- **Date:** 2026-10-11
- **Brief / case:** Brief A, official build run (version 11), extracted spec `traces/brief-a.spec.json`
- **Run:** call `9fd0eeb0-9cf5-4004-86f2-600d7d99b4ee`
- **Symptom:** The closing step said "Thank the customer and say goodbye." to the customer. In this extraction 11 of 16 outcome rows have that instruction as their `say` text. Earlier extractions of the same brief produced real sentences ("Thank you for your time, goodbye."), so the result varies from run to run.
- **Root cause:** The `say` field is spoken verbatim by a fixed line, but extraction accepted an instruction copied from the brief ("Thank the customer and say goodbye before `close_call`") as the sentence. No check rejects imperative, third-person instructions in spoken fields.
- **Category:** extraction
- **Fix / lesson:** Validate every spoken field (`say`, `ask`, `introduction`, `wait_line`, exhausted sentence): reject text that addresses the agent ("the customer", "say", "tell", "ask", "offer", imperative at the start) and repair. The prompt must ask for the literal words to the customer. Last resort: a generic polite closing in the agent's language, traced as a fallback.
- **Status:** open
- **Retest:** -

### F-046: Self-test customer answers are not plausible

- **Date:** 2026-10-11
- **Brief / case:** official build run, self-test case `identity_attempt`
- **Run:** call `8a5c1134-489c-4799-ae9f-2d226055fc6d`
- **Symptom:** The scripted customer answered "My answer to 'Ask for the customer's date of birth.' is self-test-answer-1". The agent asked again and never called `verify_identity`, so the case could not check the tool path.
- **Root cause:** Customer lines are built from the question text plus a placeholder, not from the answer format.
- **Category:** other
- **Fix / lesson:** Generate a plausible answer from the identity field's answer format or type (a date, four digits, a postcode-like string), so the agent converts it and calls the tool. The bank will say "unknown customer", which is what the case checks.
- **Status:** open
- **Retest:** -

### F-045: Self-test expects an entry event for the initial step

- **Date:** 2026-10-11
- **Brief / case:** official build run, all three self-test cases failed with "missing node(s): opening"
- **Run:** `traces/brief-a.log`, version 11
- **Symptom:** All cases reported `fail`, although the opening ran (its messages carry `nodeId: opening`).
- **Root cause:** The engine writes no `node_enter` event for the initial node. The self-test only looks at `node_enter`.
- **Category:** other
- **Fix / lesson:** Count a step as reached when a `node_enter` event names it **or** a message carries its `nodeId` (or it is the `initial_node`).
- **Status:** open
- **Retest:** -

The official command (`python3 builder/build.py brief-a.md openapi.json`, no flags) ran end to end in **184 s**: extraction 103 s (6 calls, 0 repair rounds), budget stage brought `negotiate` from ~1547 to ~1175 tokens, save + publish (version 11), 3 self-test cases (~75 s), export and trace.

### F-044: Read-back sounds machine-made ("Product 1", ISO date, "420.00")

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-01 chat, version 10 (extracted spec)
- **Run:** customer `c_de6c4d55-76e`, scratchpad `pub01v10.json`
- **Symptom:** "For Product 1, the amount is 420.00 and the date is Wednesday 2026-10-14. Do you confirm?" The ledger passed, but a judge may count this as unclear communication. The customer never heard "Product 1" before.
- **Root cause:** The confirmation summary is built from the offer-check variables (`offers_summary`) with internal numbering and raw ISO date and amount formats.
- **Category:** policy
- **Fix / lesson:** Use the customer-facing product label (type + the spec's label field, e.g. last digits), a spoken date ("Wednesday, 14 October"), and an amount without needless decimals. Generic formatting, no brief values.
- **Status:** fixed offline (F-043/044 task). The read-back says the customer-facing name (product kind in words plus the spec's label field, e.g. "credit card ending 4821"; without those fields "the first product"), a spoken date ("Friday, 16 October", the year only when it is not this year) and the amount without needless decimals. The product number stays in square brackets for the promise tool only, and the confirm prompt says never to say it. New optional spec fields: `account.product_kind_field`, `account.product_label_field` (extracted and checked against the account tool's product fields).
- **Retest:** pending (chat: PUB-01 read-back)

### F-043: Platform filler "Bir saniye lütfen." (Turkish) spoken during a step change

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-01 chat, version 10
- **Run:** customer `c_de6c4d55-76e`
- **Symptom:** After identity passed, while `account → offer_setup → negotiate` ran, the transcript shows an extra assistant line "Bir saniye lütfen." ("One moment please" in Turkish), then the English debt statement.
- **Root cause:** Not in our workflow or code. The platform's default `agent_config` (which the kit says to omit) has `sttConfig.language` and `ttsConfig.language` = `tr`. The platform seems to insert a wait filler in that language when a turn takes long (passthrough api/code steps).
- **Category:** platform
- **Fix / lesson:** We may not send `agent_config`. Try a short English fixed line on the first passthrough step after identity (the kit allows "a short fixed line that covers the wait") so the platform does not need a filler, and check whether the filler disappears. Ask the organizers whether the hidden-brief runs use an English default. **[TO-CONFIRM]**
- **Status:** fixed offline, to be confirmed live. The account lookup step (the first passthrough step after identity) speaks a short fixed line: the spec's `agent.wait_line` (extracted in the call's language), or the builder's English default "Thank you. One moment while I check your account."
- **Retest:** pending (chat: does the Turkish filler disappear?)

PUB-01 (version 10, extracted spec) **passed the ledger check**: identity two calls, `get_account` after verification, one `create_promise` (p1, 420, 2026-10-14), one `close_call` = `promise`, text-message sentence said after the promise.

### F-042: Closing rules from the spec never reached any prompt

- **Date:** 2026-10-10
- **Brief / case:** T-009, rendering the live extractions `traces/f040-*.spec.json`
- **Run:** offline render, no model or Freya call
- **Symptom:** `closing.rules` (3 to 8 rules per extracted spec) were not rendered anywhere. Most describe what the closing code already does (exactly one close, goodbye first). Some are agent instructions that were simply lost, for example the Brief A+B rule "on any transfer add no notes".
- **Root cause:** The renderer showed step rules and global rules only. The closing step is code and has no prompt, and nothing accounted for its rules.
- **Category:** rendering
- **Fix / lesson:**
  - Every spec rule now has a placement, written to the trace as a `rule_placement` line.
  - A closing rule tagged `enforced_by: closing_outcome` needs no prompt; any other closing rule goes to the global prompt.
  - The extraction prompt asks the model to tag closing rules and to put agent instructions in the step where they apply.
  - Two Brief A+B closing rules are still not enforced by the skeleton: "every product noted paid closes as paid" and "otherwise the reason of the first non-paid note". They sit in the global prompt, but the agent does not choose the closing outcome. This is a skeleton gap, listed in the T-009 report.
- **Status:** fixed offline (T-009); skeleton gap open
- **Retest:** -

### F-041: Repair rounds filled empty special-path questions with instructions

- **Date:** 2026-10-10
- **Brief / case:** live extraction of Brief A, Brief A+B, `tests/briefs/raw-a`, `tests/briefs/changed-a` (F-040 rerun)
- **Run:** `traces/f040-a.print.log`, `traces/f040-raw.print.log` and the matching `.spec.json` files
- **Symptom:** The first extraction round failed with 18 errors (Brief A) and 37 errors (raw-a), all in the outcomes group. Both runs used both repair rounds, the last allowed. In the final specs almost every closing special path had an `ask`, but the asks were instructions, not questions: "Take no promise.", "Do not describe a plan.", "Ask nothing else.". The skeleton speaks `ask` to the customer and waits for an answer. A customer who says they already paid would hear "Take no promise." and the agent would wait.
- **Root cause:** Most likely the model returned an empty `ask` object (`text` and `source` empty) on paths without a question. Each one counted as two errors: Brief A has 9 special paths, which gives exactly 18. The repair message said only "must be a non-empty string", so the model filled the fields with an instruction instead of removing them. The trace held only error counts, not the errors, so the cause had to be inferred.
- **Category:** extraction
- **Fix / lesson:**
  - The merge drops an `ask` whose text is empty, so it no longer counts as an error.
  - A present `ask` must be one question ending with "?"; otherwise it goes to repair with the reason.
  - The outcomes prompt says when to leave `ask` out and lists the checks the code applies.
  - Every repair round now writes its errors to the trace (`extract_issue`, up to 60 lines).
  - Lesson: a repair message must say how to fix an error, not only that a field is empty.
- **Status:** fixed offline (F-040 fix)
- **Retest:** pending (live rerun; expect few first-round errors and asks only as real questions)

### F-040: Extraction leaves internal call-end states and newer offer fields empty

- **Date:** 2026-10-10
- **Brief / case:** live extraction of Brief A, Brief A+B, `tests/briefs/raw-a`, `tests/briefs/changed-a` (T-006, T-006b)
- **Run:** `traces/t006-brief-a.spec.json`, `traces/t006-brief-b.spec.json`, `traces/t006b-raw-a.spec.json`, `traces/t006b-changed-a.spec.json`
- **Symptom:** All four extractions succeeded (128–189 s) and got the critical values right: the memo override in raw-a and the changed field names and codes in changed-a, with no Brief A values leaking. But states the brief never names stay unmapped: `account_failed`, `offer_limit`, `hangup_unverified`, and an opening decline. They then fall to the `default` row. The newer offer fields `next_weekday` and `max_rejected_offers_by_product` (T-005g) are never extracted.
- **Root cause:** The extraction prompts predate T-005g, and they do not ask the model to map framework states that have no wording in the brief.
- **Category:** extraction
- **Fix / lesson:** Extend the extraction prompts and validation for the T-005g fields. For framework states, ask the model to map each one to the closest brief row, and record that it was derived (provenance), not quoted. Then rerun the four comparisons.
- **Status:** fixed offline (F-040 task):
  - The extraction prompts ask for `next_weekday` and explain that the invalid-offer limit is not the persuasion count.
  - `account_failed`, `offer_limit`, `hangup` and `hangup_unverified` must be mapped and recorded in `derived_states`.
  - The opening must have a decline value that closes the call.
  - Code checks reject a `next_weekday` the documents do not define, an invalid-offer limit that cites persuasion attempts, and a negotiation value that closes a tool special path.
  - Offline tests use recorded replies.
- **Retest:** pending (CTO reruns A, A+B, raw-a, changed-a)

### F-039: Offer-schema fixture migration left extraction snapshots stale

- **Date:** 2026-10-10
- **Brief / case:** T-005g full offline suite
- **Run:** local `python3 -m unittest`; no Freya request
- **Symptom:** The first full run had seven failures: recorded extraction output and its reference snapshot still had the scalar-only offer shape, downstream evidence tests stopped on that mismatch, and the leakage test treated the new weekday-policy enum as brief data.
- **Root cause:** The renderer fixtures were migrated before the independent extraction snapshots and generic-enum allowlist. The extraction implementation and prompts were intentionally out of scope.
- **Category:** other
- **Fix / lesson:** Migrate every offline fixture that represents the same spec contract, while keeping extraction code unchanged; classify schema enum vocabulary as framework data in the leakage test.
- **Status:** fixed (T-005g, not committed)
- **Retest:** Full offline suite passed after the fixture migration.

### F-038: New fixture-copy assertion treated enum order as semantic

- **Date:** 2026-10-10
- **Brief / case:** T-005f full offline suite
- **Run:** local `python3 -m unittest`; no Freya request
- **Symptom:** The first full run had two failures: the new synthetic OpenAPI copy test rejected a matching enum in a different order, and the prompt documentation freshness test reported the newly added templates were not generated yet.
- **Root cause:** The fixture test normalized the expected values before performing a whole-document equality check, accidentally making enum order significant. Prompt documentation regeneration had intentionally not yet run.
- **Category:** other
- **Fix / lesson:** Check enum membership independently, then preserve the fixture's order while comparing the remaining OpenAPI document. Regenerate the prompt catalog before the final suite.
- **Status:** fixed (T-005f, not committed)
- **Retest:** Full offline suite passed, 132/132.

### F-037: Parallel extraction calls failed on the model's temperature rejection (race in the fallback)

- **Date:** 2026-10-10
- **Brief / case:** Brief A, first live extraction (T-006)
- **Run:** `traces/t006-brief-a.failed.log`
- **Symptom:** The build stopped with `HTTP 400: temperature is deprecated for this model` on the `flow` call, although the client has a fallback that resends without the temperature setting. The `opening_identity` call of the same run succeeded.
- **Root cause:** The four extraction calls run in parallel and share one "send temperature" flag. The first call to receive the 400 cleared the flag and retried. The second call received its own 400 a moment later, saw the flag already cleared, treated the error as unrelated and gave up. The fallback depends on shared state that parallel calls change under each other.
- **Category:** other (builder client)
- **Fix / lesson:** Decide per request, not from shared state: if the request that failed carried the setting and the error names it, retry that request without it, whatever the flag says. Better still, do not send the setting to a model that has deprecated it. Parallel code must not use a first-error flag as its only guard.
- **Status:** fixed offline (T-006 fix): the resend is decided by the failed request's own payload, the shared setting is changed under a lock, and the pinned model gets no temperature at all (trace line `model_settings`). An offline test fails four parallel requests together and checks that all four are resent; with the old shared-flag check it errors.
- **Retest:** pending (live extraction run by the CTO)

### F-036: First extraction prompt draft carried practice-brief examples

- **Date:** 2026-10-10
- **Brief / case:** T-006, `builder/prompts.py` extraction prompts
- **Run:** offline, during development (no model call)
- **Symptom:** The first draft of the extraction prompts used examples taken from the practice briefs (situations named with the briefs' reason codes and two customer questions from Brief A). A hidden brief could be pushed toward the practice briefs' rules.
- **Root cause:** Examples were picked from the briefs at hand instead of described in general domain words. The existing leak test only catches whole string literals, not words inside a long prompt.
- **Category:** extraction
- **Fix / lesson:** Examples rewritten in general words. New test: no extraction prompt contains a fixture or tool-enum code, a practice-brief example word or an ISO date.
- **Status:** fixed offline (T-006)
- **Retest:** -

### F-035: Extraction code tripped the fixture-value leak test

- **Date:** 2026-10-10
- **Brief / case:** T-006, `test_builder_string_literals_do_not_embed_fixture_values`
- **Run:** offline `python3 -m unittest`
- **Symptom:** The leak test flagged two literals in the new extraction code: the content-block keyword of the model API and a placeholder word used for a missing schema type.
- **Root cause:** Both words also occur as fixture values. The API keyword is protocol vocabulary, not brief data; the placeholder was an unnecessary default.
- **Category:** other
- **Fix / lesson:** API content blocks are built in one helper in `builder/llm.py`, which is added to the file-scoped allowance for that keyword (same reason as the OpenAPI module); the placeholder became an empty string. Builder-chosen variable names for the extracted spec were picked so they match no fixture value.
- **Status:** fixed offline (T-006)
- **Retest:** full offline suite passes

### F-034: Relative “next week” dates could resolve to the current week

- **Date:** 2026-10-10
- **Brief / case:** T-005e code review, offline date table
- **Run:** `reviews/T-005e-review.md`; local generated-code execution
- **Symptom:** A weekday combined with “next week” could resolve to the upcoming weekday in the current week and be accepted silently. Several common phrases were left unresolved, and ambiguous `next <weekday>` phrases were accepted without confirmation.
- **Root cause:** The deterministic parser handled `next <weekday>` and `week after next`, but had no separate `next week` branch or ambiguity state.
- **Category:** date-logic
- **Fix / lesson:** Resolve `next week` from next Monday, return missing when it has no weekday, request confirmation when `next <weekday>` lands in the current week, and support day-after-tomorrow, abbreviated months, and day-only ordinals.
- **Status:** fixed (T-005e review fix, not committed)
- **Retest:** Fixed-`now` offline table passes, including both `Friday next week` orders and the exact ambiguity question; full suite 104/104.

### F-033: Flattened product reader assumed the account tool name

- **Date:** 2026-10-10
- **Brief / case:** T-005e code review of F-028
- **Run:** `reviews/T-005e-review.md`; local generated-code execution
- **Symptom:** `get_account_response.data.products.0.*` worked, but the observed `account_response.data.products.0.*` shape returned no products.
- **Root cause:** The first F-028 fix hardcoded the fixed tool name in the flattened-key prefix, while Freya used the workflow node name for this engine-run result.
- **Category:** platform
- **Fix / lesson:** Match any `<name>_response.data.<products_field>.<index>.<field>` prefix. Generate one shared reader for offer code, product-number hooks and product special-path progress; retain mapped-list and JSON fallbacks.
- **Status:** fixed (T-005e review fix, not committed)
- **Retest:** Both observed node-name and tool-name prefixes pass for one, two and three products, product-id hooks and special-path progress; full suite 104/104.

### F-032: T-005e closing guard made graph assertions and prompt documentation stale

- **Date:** 2026-10-10
- **Brief / case:** T-005e full offline suite
- **Run:** local `python3 -m unittest discover -s tests -v`; no Freya request
- **Symptom:** The first full run had seven failures: six graph assertions still required every path to enter `close_record`, and the generated prompt document did not yet contain the new honesty wording.
- **Root cause:** F-031 deliberately adds a guarded `closing_say → end_call` edge when `close_call_ok` is already true. The old assertions described the pre-guard graph, and the prompt mirror had not yet been regenerated after source prompt edits.
- **Category:** other
- **Fix / lesson:** Update graph assertions to allow only the guarded already-recorded edge, regenerate `docs/PROMPTS.md` immediately after prompt edits, then rerun the complete suite.
- **Status:** fixed (T-005e, not committed)
- **Retest:** Full offline suite passes, 104/104.

### F-031: Closing chain runs again when the conversation resumes after the call ended

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-07 chat test (version 8)
- **Run:** workflow `b0bdd6e6`, version 8, customer `c_27bca007-28e`, call in scratchpad `pub07v8.json`
- **Symptom:** After the agent said goodbye and `end_call` ran, the chat route still accepted user messages. Each message resumed in `closing_say` and ran `close_attempt → close_record` again. The bank answered "the call is already closed" (`ok:false`), the chain retried, and the ledger ended with 17 `close_call` calls (1 good, 16 refused). Several turns timed out (504).
- **Root cause:** In chat, `end_call` is "deferred" and a later message resumes the conversation at the last speaking step. The closing chain does not check whether the close was already recorded. In a real call the line is gone after `end_call`, so this is mostly a chat-route effect, but a judge or simulation could still send a last line.
- **Category:** tool-call
- **Fix / lesson:** The closing chain must skip `close_call` when a close was already recorded (`close_call_ok` true), as the hang-up hook already does, and go straight to `end_call`. The test driver must stop sending after the agent ends the call.
- **Status:** fixed in code (T-005e, not committed); Freya chat retest pending
- **Retest:** Offline graph and condition tests prove `close_call_ok` true routes from `closing_say` directly to `end_call`; full suite 104/104.

### F-030: Agent said the payment was recorded when nothing was recorded

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-01 chat test (version 8)
- **Run:** customer `c_b3228de7-b42`, call `8d87e16c-6325-43f1-98c3-fdf45d0a9900`
- **Symptom:** After the offer check rejected the offer (`product_unknown`), the agent in `negotiate` said "I have recorded your payment of 420 for today ... goodbye". No promise was recorded. This is an honesty failure.
- **Root cause:** The `negotiate` prompt does not forbid claiming a recording, and the check's message ("ask which product") was not voiced. The model filled the gap with a success sentence.
- **Category:** honesty
- **Fix / lesson:** Generic rule in every step without the promise tool: never say a payment, promise, note or callback was recorded; only the step that ran the tool and got `ok` true may say so. `negotiate` must voice the check result (`offer_message`) when the verdict is not `ok`.
- **Status:** fixed in code (T-005e, not committed); Freya chat retest pending
- **Retest:** Offline prompt tests require the global success-evidence rule, require `negotiate` to voice `offer_message` for a non-ok verdict, and forbid a recording claim there; full suite 104/104.

### F-029: "I can't pay today" was treated as a refusal and the call was closed

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-07 chat test (version 8)
- **Run:** customer `c_27bca007-28e`
- **Symptom:** The customer said "I can't pay today." The extractor set `negotiation_intent = refusal`, and the agent closed the call with `no_promise/refused`. The script expected it to ask for another date.
- **Root cause:** The `refusal` value has no clear description. "Not today" is a reason to ask for another date, not a refusal to pay.
- **Category:** extraction
- **Fix / lesson:** Describe the intent values precisely: `refusal` only when the customer refuses any payment or arrangement after being asked for alternatives. "Not today", "not now" and "I don't know when" are not refusals. Consider requiring at least one counter-question before a refusal can close.
- **Status:** fixed in code (T-005e, not committed); Freya chat retest pending
- **Retest:** Offline extraction-schema tests require close values to mean refusal of any arrangement only after alternatives, and explicitly keep date-specific inability or uncertainty in negotiation; full suite 104/104.

### F-028: Offer setup did not find the products (flattened account variables)

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-01 chat test (version 8)
- **Run:** customer `c_b3228de7-b42`
- **Symptom:** `products_facts = "No products were returned."` and the offer check answered `product_unknown` for a single-product customer, so a valid offer was never accepted.
- **Root cause:** Answered TO-CONFIRM: the engine stores the account result in code `vars` as flattened keys (`account_response.data.products.0.product_id`, `.past_due`, ...), not as a list. The setup code looked for a list or JSON string.
- **Category:** tool-call
- **Fix / lesson:** Rebuild the product list from the flattened `<node>_response.data.<list>.<i>.<field>` keys (keep the list and JSON-string forms as fallbacks). Check every other code step that reads a tool result the same way (product-number hook, promise progress). With one product, the product choice must default to it.
- **Status:** fixed in code (T-005e, not committed); Freya chat retest pending
- **Retest:** Flattened observed-style variables for one, two and three products produce facts and the correct selected internal id. The product-number hook and product-note progress use the same shape; full suite 104/104.

### F-027: Spoken amount words ("the full amount") not turned into a number

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-01 chat test (version 8)
- **Run:** customer `c_b3228de7-b42`
- **Symptom:** "I can pay the full amount today" left `offer_amount` empty, so the offer check never ran and the agent asked again for a date.
- **Root cause:** The extractor only takes numbers. "The full amount", "the minimum", "half" refer to account values the extractor does not see.
- **Category:** extraction
- **Fix / lesson:** Add an amount-kind value (full, minimum, other) to the extraction, and let the offer code turn it into the number from the account facts. Or give the extractor the per-product amounts in its prompt.
- **Status:** fixed in code (T-005e, not committed); Freya chat retest pending
- **Retest:** Offline cases map full amount and the spec-derived minimum/instalment amount to the correct number for different product fixtures; full suite 104/104.

### F-026: "Today" extracted as the real date instead of the call's date

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-01 chat test (version 8)
- **Run:** customer `c_b3228de7-b42`
- **Symptom:** "today" became `2026-10-10` (the real clock), while the call's `now` is `2026-10-14`. The offer would be judged against the wrong day.
- **Root cause:** The extractor resolves relative dates with the engine's real clock (`{{date.today}}`, `system.*`), not with the call variable `now`. The kit warns that the system dates are the real clock.
- **Category:** date-logic
- **Fix / lesson:** Give the extractor the call's date (the `now` call variable, named in the spec or detected) and the computed `today_text` in the extraction description, or extract a relative phrase plus weekday and resolve it in the offer code from `now`. Never trust the engine's date for business logic.
- **Status:** fixed in code (T-005e, not committed); Freya chat retest pending
- **Retest:** With fixed `now`, offline cases cover today, tomorrow, this Friday, next Monday, a weekday in the week after next, weekday plus day number, an explicit date and a holiday; full suite 104/104.

### F-025: Internal product id read aloud to the customer

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-07 chat test (version 8)
- **Run:** customer `c_27bca007-28e`
- **Symptom:** "You have a personal loan, product p1, which is 5 days late."
- **Root cause:** The model read the raw account result because `products_facts` was empty (F-028). The facts text for the customer should never contain internal ids.
- **Category:** policy
- **Fix / lesson:** Fixed by F-028 plus a generic rule: never say internal ids; refer to products by type and the spec's customer-facing label (e.g. last digits).
- **Status:** fixed in code (T-005e, not committed); Freya chat retest pending
- **Retest:** Flattened-product facts exclude the configured internal product-id field for one, two and three products, and the negotiation prompt forbids reading raw results or internal ids; full suite 104/104.

Verified in the same tests: greeting "Hello?" and "Hello? Who is this?" did not consume an unclear attempt and the introduction was said once (T-005d). Identity passed with two tool calls and `get_account` only after `all_verified` (F-009 retest pass). Hang-up close worked (F-012): ending the PUB-01 call mid-negotiation produced exactly one `close_call` with the default row, sent by the end-of-call tool.

### F-024: Generic step text was passed through a dict whose key equals a spec value

- **Date:** 2026-10-10
- **Brief / case:** `tests/test_multi_step.py` leakage scan, during T-005d
- **Run:** local `python3 -m unittest`, no Freya
- **Symptom:** The leakage scan failed on the word `unclear`: it appeared as a string literal in `builder/workflow.py` and as a who-answered value in a fixture.
- **Root cause:** The shared opening prompt values (for the first ask and the re-ask) were collected in a dict with string keys. One key, the prompt placeholder name for the "if unclear" instruction, happened to equal a who-answered value in Brief A. It was a placeholder name, not brief data, but the scan cannot tell.
- **Category:** other
- **Fix / lesson:** Pass shared prompt values as keyword arguments (`dict(name=...)`), which are not string literals. When a placeholder name is also a likely spec word, keep it out of string literals.
- **Status:** fixed (T-005d, not committed)
- **Retest:** leakage scan green; 98 tests pass.

### F-023: Freya staging returned 503/504 on several chat turns

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-03 manual chat test on the multi-step agent
- **Run:** workflow `b0bdd6e6`, published version 3, call `da86613c-a3c8-4f68-b8f3-7e2ae5f1b638`; request IDs `86a430c5…`, `d97b1a01…`, `12b28e5b…`, `ece5648a…`, `06239925…`
- **Symptom:** About half of the turns failed with HTTP 503 ("Internal server error") or 504. A failed turn was not recorded in the call and made no tool call. Resending the same message usually worked, sometimes only after a pause. The last turn (in the closing step) never got through, so the closing behavior was not observed.
- **Root cause:** Unknown. The failed turns tended to be ones where a tool call or a step change was due. It may be platform instability (staging, weekend), or our hooks may fail on the server. The call record lists no `problems`.
- **Category:** platform
- **Fix / lesson:** The chat driver needs one automatic retry with a pause. A simulation run (approved) would show whether the errors are ours, because the platform would then report them per call. Ask the organizers if 503s persist.
- **Status:** open (TO-CONFIRM). The driver now retries 503/504/502 with a pause.
- **Retest:** 2026-10-10 PUB-03 rerun: one HTTP 502 on the deciding turn, but the turn was processed (ledger complete). A 5xx does not always mean the turn was lost: check the ledger or call record before resending.

### F-022: Closing step does not know what to say or which outcome to record

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-03 manual chat test
- **Run:** same call as F-023
- **Symptom:** After the third wrong identity answer, the agent correctly moved to the closing step, but it asked again for the phone digits instead of telling the customer to use the app or a branch. No `close_call` was seen before the test stopped (see F-023).
- **Root cause:** The closing prompt only shows the outcome table. It does not know why the call is ending, and the identity step's rules do not carry over. This is review finding T-004 #5(a)/(d), deferred to T-005.
- **Category:** routing
- **Fix / lesson:** T-005a: every path that ends the call now goes through a small step that records why (identity exhausted, third party, promise recorded or failed, special path, turn limit, ...). A code step picks outcome, reason and closing sentence from the spec's outcome table (each row lists the call-end states it covers and its closing sentence). The sentence is spoken as a fixed line, then the engine runs `close_call` with the baked values (one retry), then the call ends. The model can no longer choose, skip or change the outcome. The spec fails to load if a call-end state has no outcome row.
- **Status:** fixed (96f1b80, 608fd1e). Open detail: the closing sentence appears in the transcript as the final message on `end_call`, after the engine ran `close_call`; check whether the judge minds the order.
- **Retest:** Retest 2026-10-10: PUB-03 chat, published version 5, call in `scratchpad pub03v5`, customer `c_5c89791d-107`; ledger score pass. `close_call` = `not_verified/failed` in the same turn as the third wrong answer; sentence said once (app or branch, goodbye).

### F-021: Routing right after a tool result is suppressed in chat

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-03 manual chat test
- **Run:** same call as F-023
- **Symptom:** The third wrong identity answer left 0 attempts, and the mapped counter was 0, but the agent stayed in the identity step for that turn and asked for the next question. It only moved to the closing step on the customer's next message.
- **Root cause:** Freya evaluates routing after the tool result but suppresses it with "Missing prior assistant message". In this run, routing on a tool result happened only on the next user turn, not in the same turn as the kit docs suggest.
- **Category:** platform
- **Fix / lesson:** T-005a, two layers. (1) Conversation steps no longer have an unconditional self-loop: the log showed the step re-entering itself on every turn, which likely leaves no assistant message in the current step when the tool result arrives. With no match the engine stays in the step anyway (kit docs). (2) The identity prompt itself says the failure sentence and asks nothing more when no attempts are left, so a one-turn delay does no harm. A passthrough code step after the tool would not help, because the route into it is the one being suppressed.
- **Status:** fixed (96f1b80). Confirmed: without the self-loop, routing after the tool result ran in the same turn (`identity_attempts_left < 1` → closing chain). Voice still to check.
- **Retest:** Retest 2026-10-10: PUB-03 chat, published version 5, call in `scratchpad pub03v5`, customer `c_5c89791d-107`; ledger score pass.

### F-020: Agent said "thank you" and moved on after a failed identity answer

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-03 manual chat test
- **Run:** same call as F-023
- **Symptom:** After each wrong birth date (`verified: false`), the agent said "Thank you. Now, please provide the last four digits of your phone number." It did not tell the customer the answer did not match, and asked for the next field even though the date of birth was never verified. Once it also asked the customer to repeat a spoken date in YYYY-MM-DD format instead of converting it.
- **Root cause:** The post-hook sentence ("these fields are false, treat as NOT satisfied") arrived correctly, but the identity prompt lists the questions in order and gives no rule for a failed answer. The spec fixture has no wrong-answer wording, and the model follows the question list. The format instruction for the answer was read aloud to the customer as a demand.
- **Category:** honesty
- **Fix / lesson:** Identity step: on `verified: false`, say it did not match and ask the same field again (the brief decides if hints are allowed). Move to the next field only on `verified: true`. Convert spoken dates yourself and never ask the customer for a technical format. The rules come from the spec (T-006 extraction); the "do not move on after a failed check" behavior is generic and belongs in the template. T-005a: generic rules for true / false / not carried out / no attempts left are in the identity template; the per-answer result field, the retry hint wording and the exhausted sentence come from the spec. The answer format is now labelled as a tool format the agent converts itself.
- **Status:** fixed (96f1b80)
- **Retest:** Retest 2026-10-10: PUB-03 chat, published version 5, call in `scratchpad pub03v5`, customer `c_5c89791d-107`; ledger score pass. Each wrong answer: "That answer did not match" and the same question again; no format demand.

### F-019: Opening did not use the customer's name

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-03 manual chat test
- **Run:** same call as F-023
- **Symptom:** The first sentence asked "Am I speaking with the named customer?" instead of using the customer's title and name.
- **Root cause:** The opening prompt describes the rule ("ask for the named customer") but does not insert the call variables for title and name.
- **Category:** other
- **Fix / lesson:** Fill the opening prompt with the customer name variables from the call (generic: the variable names come from the brief or the OpenAPI, never hardcoded). T-005a: the spec lists the call variables to address the customer with (`opening.address_with`); the opening prompt inserts them as placeholders.
- **Status:** fixed (96f1b80)
- **Retest:** Retest 2026-10-10: PUB-03 chat, published version 5, call in `scratchpad pub03v5`, customer `c_5c89791d-107`; ledger score pass. Opening: "Am I speaking with Mr Park?"

Verified in the same test: the Freya editor warning "unresolved variables (`field`, `answer`, `date`, `time`), field is removed from the request" is a false alarm for tools the model calls. The bank ledger shows `verify_identity` received `field` and `answer` filled in by the model.

### F-018: Leakage test treated required routing vocabulary as brief data

- **Date:** 2026-10-10
- **Brief / case:** T-004-fix offline source-leakage test
- **Run:** Local `python3 -m unittest discover -s tests -v`; no Freya request
- **Symptom:** One of 48 tests failed after fixtures gained `available_in` and `then`, reporting mandated step names and the `close`/`return` routing enum as leaked brief values.
- **Root cause:** The leakage allowlist had not been extended for the new spec's framework-level routing vocabulary.
- **Category:** other
- **Fix / lesson:** Explicitly distinguish task-mandated graph/schema vocabulary from fixture policy content while retaining the numeric product-limit regression assertion.
- **Status:** fixed (656cb40)
- **Retest:** Enhanced leakage checks and full offline suite passed (48/48).

### F-017: Prompt documentation was stale during T-003-fix test run

- **Date:** 2026-10-10
- **Brief / case:** T-003-fix offline prompt documentation test
- **Run:** Local `python3 -m unittest discover -s tests -v`; no Freya request
- **Symptom:** One of 44 tests failed because the checked-in prompt catalog did not yet include the newly extracted hook and tool-description messages.
- **Root cause:** The test suite was run after changing `builder/prompts.py` but before running its deterministic documentation generator.
- **Category:** other
- **Fix / lesson:** Regenerate `docs/PROMPTS.md` immediately after prompt catalog changes, before the full suite.
- **Status:** fixed (656cb40)
- **Retest:** Prompt documentation regenerated; full offline suite passed (44/44).

### F-016: Generated post-hook failed to compile after prompt extraction

- **Date:** 2026-10-10
- **Brief / case:** T-003-fix offline compile check
- **Run:** Local `python3 -m py_compile builder/*.py tests/*.py`; no Freya request
- **Symptom:** The generated generic post-hook caused a Python syntax error before the test suite could start.
- **Root cause:** Prompt text was inserted with an outer f-string while the hook source itself contained a literal empty dictionary; its braces were interpreted as an empty f-string expression.
- **Category:** other
- **Fix / lesson:** Generate hook source with token replacement rather than an outer f-string, so hook syntax and Freya placeholders cannot be reinterpreted.
- **Status:** fixed (656cb40)
- **Retest:** Hook and all builder modules compile; full offline suite passed (44/44).

### F-015: Literal leakage scan confused framework words with brief constants

- **Date:** 2026-10-10
- **Brief / case:** T-004 offline source leakage test
- **Run:** Local `python3 -m unittest discover -s tests -v`; no Freya request
- **Symptom:** The new leakage test reported two embedded brief values even though one was a task-mandated workflow step name and the other was the builder trace's failure status.
- **Root cause:** The first scanner compared literal text without distinguishing required framework vocabulary from brief-derived policy values.
- **Category:** other
- **Fix / lesson:** Keep the scan strict for fixture content while explicitly exempting only task-mandated graph and trace vocabulary in addition to OpenAPI values and fixed tool names.
- **Status:** fixed (656cb40)
- **Retest:** Literal scan and full offline suite passed (42/42); no Freya request was made.

### F-014: Multi-step renderer used three invalid workflow field shapes

- **Date:** 2026-10-10
- **Brief / case:** T-004 offline format audit against the kit workflow documentation
- **Run:** Local source/fixture inspection; no Freya request
- **Symptom:** The first rendered skeleton represented extraction as an object instead of an array, placed an entry API response mapping inside its pre-action instead of on the node, and encoded a tool-call transition as a condition operator.
- **Root cause:** The renderer followed generic JSON-schema conventions and shorthand assumptions instead of the exact Freya shapes documented for extraction, pre-actions, and tool-call transitions.
- **Category:** platform
- **Fix / lesson:** Assert the exact documented wire shapes offline: extraction entries use `name` and `enum_values`, entry-call mappings live on the node, passthrough metadata is explicit, and `is_tool_call` is a transition flag.
- **Status:** fixed (656cb40)
- **Retest:** Exact wire-shape assertions and the full offline suite passed (41/41); no Freya request was made.

### F-013: Prompt catalog expansion made the documentation tests stale

- **Date:** 2026-10-10
- **Brief / case:** T-004 offline unit suite, prompt documentation tests
- **Run:** Local `python3 -m unittest discover -s tests -v`; no Freya request
- **Symptom:** Two prompt documentation tests failed after the multi-step prompt templates were added: the generated document no longer matched the checked-in file, and an old test still expected exactly two prompt sections.
- **Root cause:** The prompt catalog was expanded without regenerating its deterministic Markdown mirror or updating the count assertion to reflect a variable-size catalog.
- **Category:** other
- **Fix / lesson:** Regenerate the prompt documentation whenever the catalog changes and test the catalog entries rather than a historical fixed count.
- **Status:** fixed (656cb40)
- **Retest:** Prompt documentation was regenerated; catalog-aware assertion and full offline suite passed (41/41).

### F-012: No closing record when the customer hangs up

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-07, CTO chat test (call ended from the customer side)
- **Run:** T-001 builder, workflow `b0bdd6e6-3b68-48ae-a319-ac7dc1cf06f9`, customer `c_7b974eed-824`
- **Symptom:** The ledger has no outcome at all: the closing tool never ran because the customer ended the call before the agent closed it.
- **Root cause:** The closing tool is only a model tool inside the conversation step. Nothing runs it when the call ends another way.
- **Category:** tool-call
- **Fix / lesson:** Make sure an outcome is recorded on every path, including customer hang-up (for example an end-of-call lifecycle step with an outcome computed from call state). Must not double-record when the agent already closed.
- **Status:** fixed (62a6284)
- **Retest:** 2026-10-10 PUB-01 chat, version 8: call ended mid-negotiation, end-of-call tool sent exactly one `close_call` (`no_promise/refused`, default row).

### F-011: Deadline computed with the wrong band; holiday rule not applied

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-07 (vague period, then a holiday), CTO chat test
- **Run:** T-001 builder, workflow `b0bdd6e6-3b68-48ae-a319-ac7dc1cf06f9`, customer `c_7b974eed-824`
- **Symptom:** The customer was in the early band, but the agent applied the late band's shorter deadline. When the customer named a day that is a bank holiday, the agent did not offer the next business day; it insisted on the wrong "latest date" twice. No promise recorded. Same failure family as F-003, seen again with the T-001 builder.
- **Root cause:** The model chose the band and counted business days from prose rules. It picked the wrong row of the band table and skipped the holiday logic.
- **Category:** date-logic
- **Fix / lesson:** Band, deadline, holiday and "next business day" must come from code using the account result and the extracted calendar; the prompt only receives the finished dates (T-005).
- **Status:** fixed offline (T-005b): a code step computes each product's earliest and latest date, business days, holidays and minimum/maximum amount from spec data and `now`; another code step checks every offer and suggests the next business day or the latest date. The prompt only receives finished dates. Retest pending (PUB-07).
- **Retest:** -

### F-010: Identity check replayed a wrong answer, blamed a "technical issue" and read the account early

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-03 (three wrong answers), CTO chat test
- **Run:** T-001 builder, workflow `b0bdd6e6-3b68-48ae-a319-ac7dc1cf06f9`, customer `c_e53e8ad2-b07`
- **Symptom:** After a wrong date of birth the agent moved on to the next question as if it had passed. It then sent the same wrong answer again on its own, without the customer saying it, which burned an attempt. It told the customer there was "a technical issue" (untrue: the answer was wrong). It called the account tool twice before verification (bank refused). The call ended after the customer's second wrong answer instead of the third. Ledger failed: account tool called before verification.
- **Root cause:** The model ignored negative tool results (known platform behavior with bare results), had the account tool available during identity, and tracked attempts from memory.
- **Category:** routing / honesty
- **Fix / lesson:** Identity step with only the identity tool; a post-hook that states plainly "answer wrong, N attempts left, ask again / end"; leave the step on the tool's verified or no-attempts-left result; never let the model resend an answer the customer did not give in this turn.
- **Status:** fixed (656cb40, 96f1b80)
- **Retest:** Retest 2026-10-10: PUB-03 chat on published version 5 (customer `c_5c89791d-107`), ledger score pass. Each wrong answer said honestly, no replayed answer, no "technical issue", no account call before verification.

### F-009: Identity tool called again after identity was already verified

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-01 (happy path), CTO chat test via `/api/v2/chat/message`
- **Run:** T-001 builder, workflow `b0bdd6e6-3b68-48ae-a319-ac7dc1cf06f9`, customer `c_d25a971b-5c4`
- **Symptom:** After both answers were verified (`all_verified` true) the agent called the identity tool a third time with the date of birth. No visible harm in this case, but it wastes a turn and, with a wrong answer, could burn an attempt.
- **Root cause:** One step holds all tools; nothing removes the identity tool once verification is complete. The model repeated the call on its own.
- **Category:** routing
- **Fix / lesson:** Separate identity step that is left on `all_verified` from the tool result, so the identity tool is no longer available afterwards (T-004).
- **Status:** fixed (656cb40)
- **Retest:** 2026-10-10 PUB-01 chat, version 8 (customer `c_b3228de7-b42`): two identity calls, then `get_account`; no identity call after `all_verified`.

### F-008: Promise tool first called with an invented product id

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-01 (happy path), CTO chat test
- **Run:** T-001 builder, workflow `b0bdd6e6-3b68-48ae-a319-ac7dc1cf06f9`, customer `c_d25a971b-5c4`
- **Symptom:** The first promise call sent the product's spoken name ("credit card ending ...") as the product id and the bank answered `unknown product_id`. The agent silently called the account tool again and retried with the right id; the second call succeeded. The ledger passed, but the practice check "promise tool called exactly once" would fail in a judged run, and in the tool-failure case (first promise call fails on purpose) the wasted call changes the retry logic.
- **Root cause:** The product id is a free, model-filled string. The kit warns about exactly this: ids come from the account result and must be given to the model or filled by code.
- **Category:** tool-call
- **Fix / lesson:** Fill the product id deterministically: map the account result to variables and offer the model a choice by index or an enum of the returned ids, or set the id in a pre-hook. Never let the model type an id.
- **Status:** fixed in code (T-004/T-005a/T-005b), not yet retested in chat
- **Retest:** pending: PUB-01 (promise)

### F-007: Moved string constraint was rendered with JSON quotes

- **Date:** 2026-10-10
- **Brief / case:** T-003 offline tests (`test_kit_openapi_produces_seven_tools_with_schema_details`, `test_local_ref_is_resolved`)
- **Run:** Local `python3 -m unittest`; no Freya run
- **Symptom:** Two tests failed because a string-valued OpenAPI constraint moved into a field description appeared with JSON quotes instead of plain readable text.
- **Root cause:** The generic constraint formatter serialized every value as JSON, including simple strings.
- **Category:** other
- **Fix / lesson:** Render scalar strings directly while retaining deterministic JSON rendering for structured constraint values.
- **Status:** fixed (656cb40)
- **Retest:** Full offline suite passed (29/29); both affected OpenAPI description tests passed.

### F-006: Builder entry point failed when imported as a package

- **Date:** 2026-10-10
- **Brief / case:** T-001 review (`python3 -c "import builder.build"`; no practice case)
- **Run:** `reviews/T-001-review.md` finding 1; local check, no Freya run
- **Symptom:** `ModuleNotFoundError: No module named 'freya'`. The CLI worked only as `python3 builder/build.py`; the unit tests passed anyway because they never imported `build.py`. `builder/trace.py` also shadows the standard library `trace` module when the script directory is first on `sys.path`.
- **Root cause:** Flat imports (`import freya`, `from trace import ...`) depended on the script directory being on `sys.path`; no test exercised `main()`.
- **Category:** other
- **Fix / lesson:** Do not name modules after standard library modules. Add a test that calls `main([... "--print"])` so the entry point is covered, not only the helper modules.
- **Status:** fixed (T-001 commit)
- **Retest:** Package import succeeded; direct `main([... "--print"])` coverage and the full offline suite passed (21/21).

### F-005: Saved workflow disappeared from the workspace

- **Date:** 2026-10-10
- **Brief / case:** setup check
- **Run:** workflow `50dafbaa-36d4-4ee8-babf-9c5ae30a906f` (created 11:12 UTC with the v1 sample builder)
- **Symptom:** Reading the workflow back returned 404 "Workflow not found". The workspace held only the organizers' "Freya Bank Collections Base (2 nodes)" workflow. The local slot file still pointed at the deleted ID, so the next `save_workflow` would have tried to update a workflow that no longer exists.
- **Root cause:** Most likely the organizers reset workspaces when they released kit v3 (the README says the base agent "is already in your workspace"). Not confirmed.
- **Category:** platform
- **Fix / lesson:** Never trust the local slot file alone. Before updating, check that the stored workflow ID still exists; if not, create a new one and say so in the trace. Stale slot file removed by hand.
- **Status:** fixed offline (T-005c): before saving, the builder reads the stored workflow ID (`builder/slots.py`). On 404 it drops the stale slot entry, writes a `warning:` line to the trace and creates a new workflow. Other errors still stop the build. `freya.py` is unchanged. Offline tests with a fake client.
- **Retest:** -

### F-004: Agent said it would transfer but never called the transfer tool

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-09 (restructuring request)
- **Run:** v1 sample builder, simulation `22ed0aea-b13a-4726-ae14-e9fef445d3ab`
- **Symptom:** The judge passed the conversation, but the bank ledger had no transfer and no `close_call`. Outcome check failed.
- **Root cause:** One conversation node with all seven tools and the whole brief as prompt. The model announced the action in words and ended the turn without the tool call; nothing in the workflow forced the call.
- **Category:** tool-call
- **Fix / lesson:** Do not rely on the model to remember a required tool. Put the action in a step whose exit depends on the tool result, give tool descriptions an explicit "CALL it when ..." trigger, and make the closing tool impossible to skip.
- **Status:** fixed in code (T-004/T-005a/T-005b), not yet retested in chat
- **Retest:** pending: PUB-09 (transfer)

### F-003: Promise date ignored the holiday rule

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-07 (vague period, then a holiday)
- **Run:** v1 sample builder, simulation `22ed0aea-b13a-4726-ae14-e9fef445d3ab`
- **Symptom:** The customer named a bank holiday; the agent offered an earlier day instead of the next business day after the holiday. Wrong date recorded.
- **Root cause:** The model did calendar arithmetic itself from prose (business days, holidays, "next business day"). It got it wrong.
- **Category:** date-logic
- **Fix / lesson:** Compute dates in a code step from `now` and calendar data extracted from the brief; give the model finished facts (allowed dates, deadline, next business day).
- **Status:** fixed offline (T-005b): a code step computes each product's earliest and latest date, business days, holidays and minimum/maximum amount from spec data and `now`; another code step checks every offer and suggests the next business day or the latest date. The prompt only receives finished dates. Retest pending (PUB-07).
- **Retest:** -

### F-002: Identity check ended early and account was read before verification

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-03 (three wrong answers)
- **Run:** v1 sample builder, simulation `22ed0aea-b13a-4726-ae14-e9fef445d3ab`
- **Symptom:** The agent stopped after one wrong answer and called `get_account` before both questions passed. Ledger and judge both failed.
- **Root cause:** Attempt counting and the "verify first" gate lived only in the prompt; the account tool was available from the first turn.
- **Category:** routing
- **Fix / lesson:** Keep the account tool out of the identity step; leave the identity step only on the tool's verified/failed result; count attempts from tool results, not from the model's memory.
- **Status:** fixed (656cb40, 96f1b80): identity step holds only the identity tool, account is read in a later step, attempts come from the tool result.
- **Retest:** Retest 2026-10-10: PUB-03 chat on published version 5 (customer `c_5c89791d-107`), ledger score pass. Three wrong answers, no account call, closed `not_verified/failed`.

### F-001: Third party call ended without callback and without close

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-02 (a relative answers)
- **Run:** v1 sample builder, simulation `22ed0aea-b13a-4726-ae14-e9fef445d3ab`
- **Symptom:** Disclosure rules were respected, but no callback was scheduled and `close_call` was never called.
- **Root cause:** Same as F-004: required tool calls depended on the model's initiative in a single all-purpose step.
- **Category:** tool-call
- **Fix / lesson:** A dedicated third-party path whose exit requires the callback/close tool results.
- **Status:** fixed in code (T-004/T-005a/T-005b), not yet retested in chat
- **Retest:** pending: PUB-02 (third party)
