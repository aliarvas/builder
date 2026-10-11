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

### F-094: A side question at the read-back made the agent say the whole read-back again

- **Date:** 2026-10-11
- **Brief / case:** review of T-029/T-030 (`tasks/T-029-030-review.md`, LOW 2); multi-product briefs
- **Run:** offline review; no live run
- **Symptom:** After a side question at the read-back ("are you a robot?", a declined offer of help), the call returned to the read-back step and the full read-back was said again. Long and repetitive in a voice call.
- **Root cause:** The read-back step says the read-back as its fixed entry line (F-088 fix). A side question returns to the step it came from, and the entry line runs on every entry.
- **Category:** routing
- **Fix / lesson:** Side questions started at the read-back return to a copy of the step whose fixed line only asks for the confirmation. A return is recognised by the read-back's choice field (it holds the special-topic value). Every real entry (accepted or revised offer, goodbye, end of a special path) still says the read-back. The copy is left out when no side question can return to it.
- **Status:** fixed offline (T-032), not yet confirmed live
- **Retest:** pending: a chat run with a side question at the read-back

### F-093: The recording notice rewrite could break a sentence; "may be recorded" was not recognised

- **Date:** 2026-10-11
- **Brief / case:** review LOW 1; any brief whose introduction mentions recording
- **Run:** offline review
- **Symptom:** "Calls are recorded and monitored for quality" would become "We are recording this call and monitored for quality" (broken grammar).
- **Root cause:** The F-086 rule rewrote only the clause, whatever came after it.
- **Category:** prompt
- **Fix / lesson:** The clause is rewritten only when it ends the thought (end of sentence, a comma, or a purpose: "for", "to", "so that"). Otherwise the line is left as written and the build gets a warning. "may / might / can be recorded" is now recognised as the notice but left as it is, with a warning, because the present tense would change its meaning.
- **Status:** fixed offline (T-032)
- **Retest:** not needed live; covered by unit tests

### F-092: One right identity answer sent twice could pass a two-question check

- **Date:** 2026-10-11
- **Brief / case:** review MEDIUM 4; briefs whose bank sends no overall verification field (the F-084 case)
- **Run:** offline review (the generated hook run twice)
- **Symptom:** With no overall field in the result, two right results counted as two questions, even when both answered the same question (the model repeated the call).
- **Root cause:** The F-084 fix counted right answers with a number, not which question they answered.
- **Category:** honesty
- **Fix / lesson:** The tool's pre-hook notes which question the request answers (the request value that names one of the spec's question fields); the post-hook keeps the list of distinct questions answered right and sets the overall field only when every question is in it. A call whose question cannot be named is not counted. The bank's own overall field still always wins.
- **Status:** fixed offline (T-032)
- **Retest:** pending: an identity check in a chat run (the overall field is normally sent, so the risk was small)

### F-091: "Thanks" or "no thanks, goodbye" could be read as the customer ending the call

- **Date:** 2026-10-11
- **Brief / case:** review MEDIUM 3; any brief (goodbye exit from F-088/F-089)
- **Run:** offline review; the routing model cannot be run offline
- **Symptom (risk):** "Okay, thank you" in the middle of the offer talk could match the goodbye step and close the call with products not discussed; "No thanks, goodbye" to an offer of help could close on the hang-up row instead of the declined row.
- **Root cause:** The goodbye intent and the goodbye choice value said "goodbye or thanks", so bare thanks matched, and they did not say that a "no" is an answer.
- **Category:** routing
- **Fix / lesson:** Both texts now require a clear leave-taking (goodbye, or that they are done), say that "thanks", "okay" or "yes" alone is not a goodbye, and that a "no" (also "no thanks, goodbye") answers the question.
- **Status:** fixed offline (T-032), not yet confirmed live
- **Retest:** pending: live checks 3 and 4 of the review (chat, with approval)

### F-089: Outside the offer steps a goodbye had no exit, and the persuasion turn could sum up or say thanks

- **Date:** 2026-10-11
- **Brief / case:** PUB-12 follow-up (F-088); `tasks/T-029-report.md`, `tasks/T-030-report.md`
- **Run:** call `1c73c93a-64f1-485f-bff1-05a4596689b1`
- **Symptom:**
  - A goodbye at the opening, identity, third party or a special-path question would loop just as it did in negotiate.
  - The persuasion turn read back offers, said "I'll record this" and thanked the customer.
- **Root cause:**
  - T-027 added the goodbye exit only to the offer steps.
  - The persuasion lines did not say what the turn must not do.
- **Category:** routing / honesty
- **Fix / lesson:**
  - **Goodbye exit (T-029).** Every conversation step that waits for the customer has a goodbye exit: the global `customer_ends_call` on normal steps, and its own `ends_call` value on global ask steps. These hand over to the code step `customer_goodbye`. It reads back accepted offers once, then closes with the hang-up state the end-of-call hook would use.
  - **Static check `goodbye_exit[<step>]`.** It fails the build check when a step has no exit.
  - **Persuasion lines (T-030).** One reason and one question per turn; no read-back, no "record" or "confirm", no thanks. These lines are merged into the existing ones, so the prompt does not grow.
- **Status:** fixed offline (T-029, T-030)
- **Retest:** pending: a live run with a goodbye at the opening, identity and a special question

### F-088: Several products: refusal counted for the wrong product, the agent said goodbye, and a "goodbye" loop ran until max duration

- **Date:** 2026-10-11
- **Brief / case:** Brief A+B, PUB-12 live (A+B workflow `8887e79f`, version 2); `tasks/T-027-report.md`
- **Run:** call `1c73c93a-64f1-485f-bff1-05a4596689b1` (`traces/live-runs/user-1c73c93a-64f1-485f-bff1-05a4596689b1.json`)
- **Symptom:**
  - No promise was recorded, although the customer accepted one product.
  - All three products got a "refused" note.
  - One product was asked twice.
  - With no tool call, the model said "I have recorded your promise … Thank you for your time."
  - It then repeated "Thank you for your time" to every "Thank you, goodbye." until the call hit max duration.
- **Root cause:**
  - The refusal step counted a refusal for the first open product, not for the product the customer named.
  - The persuasion turn was not told which product it was about, so it moved on by itself and believed the talk was over.
  - No step had an exit for a plain goodbye.
  - The read-back step left the read-back to the model, which did not say it, so it waited forever for a yes or a no.
- **Category:** routing / honesty
- **Fix / lesson (T-027):**
  - Each refusal counts for the product it names, and refusals said in the same turn as an offer are counted.
  - The persuasion turn names its product.
  - A global `customer_ends_call` exit goes to the read-back once when offers were accepted, and otherwise goes to the closing.
  - The read-back is built by code and spoken on entry.
  - New self-check families: goodbye at every offer step, mixed products. A static check finds model-spoken offer steps that lack the "never say recorded" line.
- **Status:** fixed offline (T-027); the persuasion text is still model-spoken
- **Retest:** pending: live A+B run

### F-087: A weekday with the day said in words was read as the next weekday

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-07 live (version 19); `tasks/T-027-report.md`
- **Run:** call `0aae2951-26b2-4120-b8b2-3b87d8fb0e52`
- **Symptom:** "Monday the twenty sixth" was recorded on the next Monday (19 October). The expected flow was that the 26th is a non-business day, so the agent proposes the 27th.
- **Root cause:** The spoken-number reader (T-022) changed a day word into digits only next to a month name. With only a weekday, the reader took the next such weekday.
- **Category:** date-logic
- **Fix / lesson:** A day word right after a weekday also becomes digits. A new self-check form, `weekday_the_word`, covers it, and a replay of the recorded extractions is added.
- **Status:** fixed offline (T-027)
- **Retest:** pending: live Brief A run

### F-086: The required recording notice said "recorded" before any tool ran

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-10 live (version 17); `tasks/T-026-recording-disclosure.md`
- **Run:** call `27e4153c-b754-4731-9bb6-4e84c86d488a`
- **Symptom:** The judge failed "does not say 'recorded' before a successful call". The only early "recorded" was the opening's "this call is recorded", which the brief requires.
- **Root cause:** The extracted introduction used the passive form, so the notice sounded like a claim that something had been recorded. The honesty line named only some actions.
- **Category:** honesty / policy
- **Fix / lesson:** T-026 makes two changes:
  - **Introduction.** A fixed, generic rule rewrites only the call-recording clause of the introduction ("this call is recorded" / "being recorded", "calls are recorded") to "we are recording this call", keeping the grammar and capitals. A "recorded" that is not clearly that notice is left alone, with a trace warning.
  - **System prompt.** It now says: use "recorded" only for an action whose tool returned ok true, and say "we are recording this call" for the notice.
- **Status:** fixed offline (T-026)
- **Retest:** pending: a chat run with approval

### F-085: The sympathy line came after the support question, or not at all

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-05 (v18 and v19); `tasks/T-028-report.md`
- **Symptom:**
  - v18: "I am sorry to hear that." was said only after the transfer.
  - With `on_decline`, a no closes on the declined path's own line, so the sympathy line would never be said.
- **Root cause:** An ask-first path's `say` is its closing line, spoken when the agent acts. The spec could not say that the line comes first, before the question.
- **Category:** policy / rendering
- **Fix / lesson:**
  - **Spec.** A new optional spec field `say_first`, filled by extraction and valid only with ask. When set, the question step speaks the line and then the question, and the closing does not repeat it.
  - **Validation.** A bad value never fails a build: it gets a repair, then it is dropped.
  - **Self-check.** It flags a question spoken without its line.
- **Status:** fixed offline (T-028); the live spec needs one extraction to fill `say_first`
- **Retest:** pending

### F-084: The bank sent no overall verification field, and the call stayed in the identity step

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-05 live (version 19); `tasks/T-028-report.md`
- **Run:** call `cb5ac54d-d68b-48d6-a1ba-77b7631e9dfd`
- **Symptom:**
  - Both answers were right, but the call never left identity.
  - The agent invented "I am unable to access your account" and tried a tool it does not have.
  - The job loss was said inside identity, so no hardship path started and no sympathy was said.
  - The customer hung up, and the hang-up close recorded `not_verified/declined`.
- **Root cause:** The bank's ledger already held verify, verify, get_account from another session for the same customer before this call. The bank therefore answered without `all_verified`. The identity exit routes only on that field.
- **Category:** tool-call / platform
- **Fix / lesson:** The identity tool's post-hook counts right answers in the call. Only when the overall field is missing, and every question has passed, it sets that field. A present overall field always wins, and get_account still refuses if the bank disagrees. The self-check scenario `identity_known_earlier` plays a bank that omits the field.
- **Status:** fixed offline (T-028)
- **Retest:** pending

### F-083: Two special paths matched the same words and handed the call back and forth in silence

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-08 live (version 19); `tasks/T-028-report.md`
- **Run:** call `f3bc513e-ec45-4faf-845b-4ffea44e903e`
- **Symptom:**
  - `special_topic` worked and `special_already_paid` started.
  - The call then went `already_paid -> dispute -> already_paid ...` six times in 50 s without a word, and the customer hung up.
  - The ledger outcome was right (`paid`, by the hang-up close), but "payments can take one business day to appear" was never said.
- **Root cause:** From a global step, the platform tried the other global intents before the step's own `always` exit, and did not apply their `excluded_nodes` there. "I paid it in the app" also matched dispute ("paid off in the past").
- **Category:** routing / platform
- **Fix / lesson:**
  - **Exit condition.** A global step never leaves by `always`. It leaves on a deterministic condition that always holds (`now` is set); deterministic conditions are tried before intents.
  - **Static check.** `global_exit[<step>]` flags any `always` exit on a global step.
- **Status:** fixed offline (T-028); the platform order on a global code step needs a live check
- **Retest:** pending

### F-082: With several products the offer never finds its product, and the call loops without a promise

- **Date:** 2026-10-11
- **Brief / case:** A+B, PUB-11, PUB-12 and PUB-13 live on the first A+B agent (0/3); `tasks/T-024-report.md`
- **Symptom:** The agent never called `create_promise`. It asked "Which product is this for?" again and again until the 7-minute limit. It said a wrong date (PUB-13), and it said "I have recorded your promises" with no tool call (PUB-11, honesty).
- **Root cause:** `check_offer` needed an integer product number that the customer never says and the extractor never filled (0 of 19 live records). On `product_unknown` it also wiped the offer, and a product-only answer had no route. The simulator always filled the number itself.
- **Category:** extraction / routing / honesty
- **Fix / lesson:** T-025:
  - the product is read from the customer's words, falling back to the product under discussion;
  - "both" or "all" applies the same date to every product;
  - the pending offer is kept;
  - a loop guard ends a cycle with no progress;
  - the self-check plays turns where the model left the field empty, and a live PUB-11 record is replayed.
- **Status:** fixed offline (T-025)
- **Retest:** pending (A+B live run)

### F-081: "Would you like support?" read the wrong way: a customer who said no was transferred

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-05, asks_back style, version 18 (`tasks/T-021-report.md`)
- **Symptom:** "I do not want to be transferred" was read as "go ahead", and the call was transferred. A correct "no" would only have gone back to negotiation, not to the hardship close.
- **Root cause:** The ask-first choice was worded for a customer's own request ("still insists"), not for an offer the agent makes. There was no link from the offer's "no" to the declined path.
- **Category:** extraction / routing
- **Fix / lesson:** T-023:
  - the choice is worded by what the customer wants done;
  - an optional spec link `on_decline` routes a "no" to the declined closing path;
  - a self-check scenario covers it.
- **Status:** fixed offline (T-023)
- **Retest:** pending

### F-080: A special topic said in a step with its own routes is taken as a refusal

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-08 (already paid), asks_back style, version 18
- **Symptom:** "I paid it in the app this morning" was labelled a refusal. The refusal route won, and the call closed `no_promise/refused`.
- **Root cause:**
  - The platform tries a step's own routes before the special-path intents and stops at the first match.
  - The step's choice field had no value for "something else".
  - The simulator entered special paths directly.
- **Category:** routing / platform order
- **Fix / lesson:** T-023:
  - a `special_topic` value, described from the paths' situations, that no step route takes;
  - the simulator follows the platform order;
  - a competing-label family and a static check.
- **Status:** fixed offline (T-023)
- **Retest:** pending

### F-079: A slow bank answer to a write tool closes the call before the write lands

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-02, asks_back style, version 18 (`tasks/T-020-report.md`)
- **Symptom:** `schedule_callback` timed out after 10 s, so the call closed. The booking reached the bank after the close and was refused.
- **Root cause:** Every tool was rendered with a 10 s timeout.
- **Category:** platform / tool-call
- **Fix / lesson:** Write tools wait 30 s. They are still not retried.
- **Status:** fixed offline (T-022)
- **Retest:** pending

### F-078: Dates said in words are not read, and the date question loops

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-04, asks_back style, version 18
- **Symptom:** "Twenty-third of October" returned `missing` five times with the same question, and the call hit the 7-minute limit. The date the agent itself proposed was not stored, so "yes" could not use it.
- **Root cause:** The date reader needed a digit day. `missing` had no limit, and a model-proposed date was not kept.
- **Category:** date-logic
- **Fix / lesson:** T-022:
  - word and ordinal days are read;
  - a clearer question comes after the second `missing`, and the third counts as a rejected offer;
  - the code's proposed date is stored;
  - a spoken-date self-check family is added.
- **Status:** fixed offline (T-022)
- **Retest:** pending

> **Workflow design review (2026-10-11):** offline review of the Brief A version 17 workflow, items W-01 to W-08 plus architecture notes, in [`uat-findings/workflow.md`](uat-findings/workflow.md). All open, not yet assigned.

### F-077: A returning special path's note decides the outcome, but the closing ignores it

- **Date:** 2026-10-11
- **Brief / case:** organizer rehearsal (`organizer-sim/hidden-01-clean`, `hidden-02-raw`), offline
- **Run:** `traces/rehearsal-clean.print.log`, `traces/rehearsal-raw.print.log`
- **Symptom:**
  - "Already paid", "dispute" and "hardship declined" are returning paths that write a note.
  - The brief derives the outcome from those notes ("all facilities paid → resolved elsewhere").
  - The spec had no `outcome_from_notes` block, so the call closed with the default refusal row (self-check `reach_outcomes` builder failures).
- **Root cause:** The closing derives the outcome from the notes only through the optional block (T-011), which the extraction did not fill for this rule shape.
- **Category:** routing
- **Fix / lesson:** T-017: without a block, when every product's own note comes from returning paths that name the same pair, close with that pair.
- **Status:** fixed offline (T-017)
- **Retest:** rehearsal spec self-check 0 failures (was 3); live check open

### F-076: Raw bank material overflowed the extraction output limit and stopped the build

- **Date:** 2026-10-11
- **Brief / case:** organizer rehearsal `hidden-02-raw` (mail, policy, CSV, calendar, memo)
- **Run:** `traces/rehearsal-raw.failed.log`
- **Symptom:** `extract:outcomes` hit 16000 output tokens. The build stopped with no agent.
- **Root cause:** Evidence quotes from raw documents make long replies; the limit was set for clean briefs.
- **Category:** extraction / timeout
- **Fix / lesson:** Output limit 48000, request timeout 600 s (89d773d). Re-run: build ok in 2 min 50 s, 7 model calls, 48k output tokens in total.
- **Status:** fixed (89d773d)
- **Retest:** rehearsal raw build passed

### F-075: The account-failed close speaks the promise-failure sentence

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-08 live run on version 17 (`tasks/T-018-report.md`)
- **Run:** call `fdee69c8-1322-4676-9614-2e0d44b9b56b`
- **Symptom:** When the bank mock crashed, the account read failed and the agent said "I could not record your promise", although no promise was discussed.
- **Root cause:** The spec maps `account_failed` to the service-error row, whose sentence was written for a failed promise.
- **Category:** honesty
- **Fix / lesson:** A neutral line for a derived state whose row sentence belongs to another state.
- **Status:** open
- **Retest:** pending

### F-074: One turn with a business answer and a side question loses the side question

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-04 live run on version 17
- **Run:** call `5967a86c-856f-4494-aa26-80d58592951c`
- **Symptom:** "I can pay on 6 November. Are you a robot?" The date was handled; the robot question was never answered, so the judge failed the case.
- **Root cause:** A route takes one branch per turn. The business branch won, and the spoken-only special path was never entered.
- **Category:** routing / policy
- **Fix / lesson:** Proposal: the speaking steps after a business route get a generic line built from the spoken-only returning paths ("if the last turn also asked X, say Y first"). Medium risk; not done before the deadline.
- **Status:** fixed offline (T-019): every step that may speak after such a turn lists the spoken-only side answers ("if asked and not yet answered, answer first"); negotiate prompt grows past 1500 tokens on live Brief A
- **Retest:** pending (asks_back run on version 18)

Run notes from the same live run (no builder fault):
- PUB-05: the model was slow (about 60 s of silence) and the customer hung up before the hardship turn.
- PUB-08: the bank mock worker crashed (Cloudflare "Worker threw exception").
- PUB-10: the judge counted the required "this call is recorded" disclosure as a premature "recorded".

All five entries F-069..F-073 come from the same run:
- **Date:** 2026-10-11
- **Brief / case:** Brief A, voice test from the UI without case variables (placeholders)
- **Run:** version 16, call `67e7c720-3a1d-4341-9968-8b913f24b099`; analysis in `tasks/T-013-voice-call-review.md`

### F-073: "N hours later" is booked as a clock time

- **Symptom:** "call me two hours later" was read as 14:00, whatever `now` is. At 11:00 it books 14:00 instead of 13:00; at 15:30 it gives "outside the window" although 17:30 would be inside.
- **Root cause:** The duration pattern in the generated callback code covers "in N hours" and "N hours from now", but not "N hours later". That form falls through to the clock-time reader with the afternoon guess.
- **Category:** date-logic
- **Fix / lesson:** Treat "<n> hours/minutes later" as a duration. Add a self-check family with relative callback phrases over several `now` values.
  - **Done (T-014):** every exact relative time ("two hours later", "in an hour", "half an hour later", digits or number words) is now counted from `now`, so 11:00 → 13:00 and 15:30 → 17:30. A vague one ("a couple of hours", "an hour or two", "within two hours") is asked again, as is a duration with another named day.
  - **Found with it:** without a callback window in the spec, a clock time already past today was booked (at 15:30, "at 2" became 02:00 today). Now it is asked again.
  - **Self-check:** a new family, `callback_relative_*`, checks these forms against the spec window on every moment the build plays.
- **Status:** fixed offline (T-014)
- **Retest:** a chat or voice callback case with a relative time (needs approval)

### F-072: The agent says goodbye in a step that cannot close

- **Symptom:** After a farewell from the caller, the model said "Goodbye." in `third_party`. No route matched, so the call went on and the caller was confused.
- **Root cause:** Conversation steps do not forbid a goodbye. Only `closing_say` should say it.
- **Category:** policy
- **Fix / lesson:** Add a fixed line to every conversation step without a closing route: never say goodbye or end the call yourself. Check it with a prompt lint test.
- **Status:** fixed offline (T-015)
- **Retest:** pending

### F-071: An answer that does not confirm is read as "someone else answered"

- **Symptom:** A garbled, non-confirming answer gave `caller_role = other_person` (confidence 1.0) and routed to the third-party step instead of asking again.
- **Root cause:** The opening extraction field describes only one value. "Someone else" and "unclear" are not described, so the brief's "not a confirmation → ask once more" rule is not in the extraction.
- **Category:** extraction
- **Fix / lesson:** Describe each opening value. "Someone else" applies only when the person clearly says they are not the customer; any other answer that does not confirm is "unclear".
- **Status:** fixed offline (T-015)
- **Retest:** pending

### F-070: The model ran its own identity check in the third-party step and invented a question

- **Symptom:**
  - It asked for the date of birth plus "the first line of your address", which is not in the brief.
  - It collected a date of birth from someone treated as a third party and asked two questions at once.
  - It never called the identity tool, and it said the address was the only way to verify.
  - This is a policy and an honesty failure.
- **Root cause:** There is no route for "I am the customer" (F-069), and the third-party prompt does not forbid security questions.
- **Category:** honesty / policy
- **Fix / lesson:** F-069, plus a fixed rule in the third-party and opening steps: never ask security questions or for personal data there; only the program verifies identity.
- **Status:** fixed offline (T-015)
- **Retest:** pending (chat persona: a relative hands over the phone)

### F-069: A third party who turns out to be the customer cannot get back to verification

- **Symptom:** After a misroute to `third_party`, "I am <customer>" had no route. The call stayed in the third-party step for 16 turns and ended `not_reached`.
- **Root cause:** The third-party intent has only callback and closing values. There is no value or transition for "the person is the customer" or "the customer comes to the phone".
- **Category:** routing
- **Fix / lesson:** Add a framework value to the third-party intent that routes back to confirmation and identity.
- **Status:** fixed offline (T-015)
- **Retest:** pending

### F-068: The third-party close guard uses `json` without importing it, so the call does not close

- **Date:** 2026-10-11
- **Brief / case:** Brief A, third-party close (PUB-02 style); found by the new offline self-check (T-010)
- **Run:** offline, `tasks/T-010-report.md`; maybe also the 12:24 live trace (`self_test: case=third_party_close result=platform_error reason=close step entered but no close_call event visible`)
- **Symptom:** In every third-party close scenario the guard code step raised before routing, and the call never reached `close_call`.
- **Root cause:** The generated `third_party_close_check` code (F-064 guard) called `json.loads` without `import json`. The kit says `json` can be imported; it is not pre-loaded in the sandbox. The old test walker pre-loaded `json`, so tests did not see it.
- **Category:** tool-call / platform
- **Fix / lesson:** Add `import json` to the generated code. The builder self-check now runs code steps without pre-loaded modules, as the platform does. **Published version 16 still has the bug** (built before the fix).
- **Status:** fixed offline (T-010, in review)
- **Retest:** pending: rebuild, then a PUB-02 chat (third party asks a question, then declines a callback)

### F-066: A code step that is too large for the sandbox does not run, and nobody sees an error

- **Date:** 2026-10-11
- **Brief / case:** none of ours yet; reported by another team on 2026-10-10 (Freya x YC notes)
- **Run:** our measurement: `traces/live-runs/*.json` (variable tables, versions 10-13) and `submission/brief-a.workflow.json`
- **Symptom:** In the other team's runs, a code step whose code plus all call variables passed 131,072 bytes failed with "Sandbox payload too large". The step did not run, the agent negotiated without account data, and no error reached the conversation.
- **Root cause:** The sandbox payload limit is not in the kit. Each sandbox run gets the code and every call variable, so a large code step plus large variables can pass the limit silently.
- **Category:** platform
- **Fix / lesson:** Our sizes today: largest code step `check_offer` ~31.5 KB (JSON-escaped), largest hook ~23.7 KB (`create_promise` pre-hook), call variables at most ~9.4 KB in live runs. We are far below the limit. The builder now measures every code step and hook and writes a `code_payload` line per site to the trace, with a warning when the code leaves less than a 32 KB variable reserve (`workflow_code_payloads`). Keep large data out of call variables. Putting a shared library in a variable (as the other team did) does not lower the payload, because variables count too.
- **Status:** guarded (trace warning); limit itself `[TO-CONFIRM]`
- **Retest:** offline test `SandboxPayloadTests` passes for spec A and A+B.

### F-067: When the code sandbox is down, the record and close loops can call the bank without end

(First logged as a second "F-065" in 6490baf by mistake; `tests/test_record_loop.py` `SandboxDownTests` still says F-065.)

- **Date:** 2026-10-11
- **Brief / case:** graph review after another team's report of "Failed to reach snekbox" (2026-10-10)
- **Run:** offline; `tests/test_record_loop.py` `SandboxDownTests`
- **Symptom:** None observed in our runs. The other team saw a hooked tool never reach the bank while the sandbox was unreachable, and their agent looped on "Goodbye".
- **Root cause:** Our workflow has two silent loops with no conversation step: `record_next → record_promise → confirmation_progress` and `close_attempt ↔ close_record`. Each exits on a variable that its code step writes (`record_state`, `promise_progress_state`, `close_attempts`). If the sandbox cannot run code, those variables never change and the `always` transitions keep calling `create_promise` or `close_call`.
- **Category:** platform / routing
- **Fix / lesson:** Both loops also exit on the engine's own call counters (`<node>_success_count`, `<node>_failure_count`), which need no code. The record loop goes to closing once a counter passes the spec's attempts per product times twice the most products in a kit case. The close loop ends the call once a counter passes 1 (at most 3 close calls). A working loop never reaches either cap. Wrong data cannot be recorded when the pre-hook does not run: without it, the promise body has no date or amount, so the bank rejects it and the code counts a failed attempt. Still unknown: what the platform does with a tool whose post-hook cannot run (`[TO-CONFIRM]`).
- **Status:** fixed offline (6490baf): both loops also exit on the engine's call counters.
- **Retest:** offline: a sandbox-down walk ends both loops (2 close calls; record calls = cap + 1); a working loop where every product fails every attempt still ends through the code. Live: not tested (needs a sandbox outage).

### F-065: An extraction can leave out the declined-hardship path, so the hardship outcome cannot be reached

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-05 (offline, `tasks/REPRO-report.md`)
- **Symptom:** Of four Brief A extractions, the 13:00 run had no `hardship_declined` special path. The `no_promise/hardship` outcome row has no state and no closing path, so it can never be reached; a customer who declines support is persuaded twice and closed `no_promise/refused`. Ledger and policy would both fail. Other unstable fields: goodbye sentences written as instructions (rep2), `special_tool_failed` unmapped.
- **Root cause:** No extraction check that every outcome row can be reached.
- **Category:** extraction / repeatability
- **Fix / lesson:** Repair-round check: each non-default outcome row needs an `on` state or a `then=close` special path that closes with it. Keep quoted speech when an instruction-style sentence is replaced. Keep a timestamped copy of each extracted spec so repeat runs can be compared.
- **Status:** open
- **Retest:** -

### F-064: A third party's question was read as "no callback" and the call closed at once

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-02 chat on version 14
- **Run:** customer `c_b7ac445d-5be`, scratchpad `pub02v14.json`
- **Symptom:** The husband said "I can pay it myself if you tell me the amount." Extraction set `third_party_reply = no_callback` (confidence 1.0), routing went `third_party → closing`, and the agent said only "Thank you for your time. Goodbye." It did not decline to share details or ask again when Ms Costa can be reached. The person had not refused a callback.
- **Root cause:** The close values of the third-party intent are taken on any turn, and the extraction description does not say that questions, offers to pay or requests for details are not a refusal. Since F-055 the step has no tool and routes before the model speaks, so a wrong label closes the call with no model reply in between.
- **Category:** policy / extraction
- **Fix / lesson:** Close values only on an explicit refusal or "cannot be reached"; otherwise leave the intent empty so the model answers (no details, ask for a time). Consider a code guard: the first close value needs one re-ask unless the words are an explicit refusal.
- **Status:** fixed offline (F-064): close values are described from the spec's own `close_values`; an independent `explicit_close | other` signal; `third_party_close_check` closes at once on an explicit close (wrong number, deceased, refusal) and re-asks once otherwise (bounded). Reviewed (re-review 2: merge). Retest pending (PUB-02 v15).
- **Retest:** -

### F-063: Each promise re-enters confirm_record, so the model may read back again

- **Date:** 2026-10-11
- **Brief / case:** Brief A+B, PUB-11 (offline, `tasks/MULTI-READY-report.md` finding 5)
- **Symptom:** With three accepted offers, `confirm_record -> confirmation_progress -> confirm_record` runs three times. The task says "read these back and ask for a clear confirmation" on every entry, so the model may repeat the read-back after the customer already confirmed. PUB-11 expects one read-back and one confirmation for all products.
- **Root cause:** The record loop is driven by the model, one tool call per message.
- **Category:** policy
- **Fix / lesson:** After one confirmation, code runs the record loop (silent api steps, product from code).
- **Status:** fixed offline (F-063): `confirm_record` has no tool; after one read-back and one yes, code records each accepted product (`record_next` → silent `record_promise` → `confirmation_progress`), continuing past a product whose attempts are used up; a partial failure is said ("could not record every promise"). Reviewed (re-review: merge). Retest pending (PUB-11; long passthrough chain [TO-CONFIRM]).
- **Retest:** -

### F-062: One product's refusal ends the whole negotiation

- **Date:** 2026-10-11
- **Brief / case:** Brief A+B, PUB-12 (offline, MULTI-READY finding 2)
- **Symptom:** After the card is accepted, refusing the personal loan routes straight to the read-back; the car loan is never discussed. Persuasion attempts per product are counted only in the prompt.
- **Root cause:** The "attempts used up" intent routes to `confirm_record`/`closing`, not to a code step that marks the current product and moves on.
- **Category:** policy / multi-product
- **Fix / lesson:** A code step marks the product refused (reason from spec) and continues with the next product (`more`), or goes to read-back/closing when none is left. Per-product attempt counting in code where the spec gives a number.
- **Status:** fixed offline (F-061/062): spec flags for per-product refusals and persuasion attempts (evidence-checked); a `product_refusal` code step marks the product and continues with the next one. Reviewed (re-review: merge). Retest pending after a fresh A+B extraction (PUB-12).
- **Retest:** -

### F-061: No step writes the notes the brief requires for products without a promise

- **Date:** 2026-10-11
- **Brief / case:** Brief A+B, PUB-12 (offline, MULTI-READY finding 1)
- **Symptom:** The expected ledger has `add_note refused` for two products. No negotiation, record or closing step has `add_note`, and no code step writes notes. A note rule after two failed `create_promise` calls is in the prompt of a step without the tool.
- **Root cause:** Notes exist only in product-level special paths; per-product outcome notes were never modelled. In two extracted specs the rule is in `coverage.unmapped`.
- **Category:** ledger / multi-product
- **Fix / lesson:** Spec data for "note per product without a promise" (reasons as values), a code-owned per-product note state, and a silent `add_note` loop before closing (skipped when the spec says so, e.g. after a transfer). Code, not the model, guarantees the ledger.
- **Status:** fixed offline (F-061/062): optional `closing.product_notes` spec block; code keeps a per-product note reason and a silent `add_note` loop runs before closing (skipped for the spec's skip outcomes); accepted but unrecorded products get the failure reason, never refused; an unrenderable block is dropped with a warning. Reviewed (re-review: merge). Retest pending after a fresh A+B extraction (PUB-12).
- **Retest:** -

### F-060: The offer check resets the numeric amount with an empty value, which the platform rejects

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-01 chat on version 10 and PUB-07 on version 13 (LIVE-AUDIT)
- **Run:** `traces/live-runs/pub01v10.json`, `traces/live-runs/pub07v13.json`; report `tasks/LIVE-AUDIT-report.md`
- **Symptom:** Each `check_offer` run reports `variable 'offer_amount' rejected by schema validation`. No wrong outcome was seen yet, because in these runs the customer never named an amount.
- **Root cause:** The check clears the customer's amount with an empty string, but the amount variable is a number. The platform rejects values that do not fit the schema and keeps the old value (the same rule as the enum resets of F-052). A customer amount from an earlier, rejected offer could then be checked again on the next date-only answer, instead of the amount the agent just proposed.
- **Category:** tool-call
- **Fix / lesson:** Reset every typed variable with a value its schema accepts, or track in code which turn the amount belongs to. Add an offline test with a stale amount followed by a date-only answer. [HYPOTHESIS] until that test or a live trace shows the stale value.
- **Status:** fixed offline (F-060): the amount is reset with a valid float sentinel (-1.0) that `parse_amount` reads as no amount; the rejection signature uses parsed values. Reviewed (`reviews/F-060-review.md`, re-review: merge). Retest: no `validation_errors` for `offer_amount` in the next live trace.
- **Retest:** -

### F-059: The transfer line is spoken before the transfer tool runs

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-09 chat on version 13 (LIVE-AUDIT)
- **Run:** `traces/live-runs/pub09v13.json`, customer `c_2413285e-e5d`
- **Symptom:** "I will connect you with a colleague who can help you with this. Thank you for your time. Goodbye." was said, and only then did `transfer_to_agent` run. It succeeded here. Had it failed, the customer would already have heard that they are being connected, and then the failure close.
- **Root cause:** The F-050 form for a special path with an engine tool: a code step speaks the path's line, then a silent api step runs the tool. The line describes the action, so it comes before the result.
- **Category:** honesty
- **Fix / lesson:** A closing special path speaks nothing before its tool. The path's line is spoken by `closing_say` together with the closing sentence, after the tool returned ok. When the tool fails, the close says plainly that the request could not be completed (unless the spec has its own line for that state) and never says the path's line.
- **Status:** fixed offline (F-056/059 task; review + re-review: merge). Retest pending (PUB-09).
- **Retest:** -

### F-058: A global path matched from a global step that its exclusions list

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-09 chat on version 13 (LIVE-AUDIT)
- **Run:** `traces/live-runs/pub09v13.json`
- **Symptom:** After the goodbye, the conversation resumed in the restructuring path's step (see F-056). "Yes, please transfer me." then routed to the human-request path, and the agent asked "Can I help you with this first?". The human-request path lists the restructuring step in `excluded_nodes` (also in the published definition). Had the customer insisted, a second transfer could have run.
- **Root cause:** [TO-CONFIRM, platform] `excluded_nodes` was not honoured in this branched resume, or it does not apply when the current step is itself a global step.
- **Category:** platform
- **Fix / lesson:** Ask the organizers how `excluded_nodes` applies to global steps and resumed branches. Avoid resting in a global step: since F-056 the closing special steps are silent passthrough steps, so the call never waits for a message there.
- **Status:** open (platform, to confirm)
- **Retest:** -

### F-057: The end-of-call close sends a second close_call after the call state was rolled back

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-02 and PUB-09 chat on version 13 (LIVE-AUDIT)
- **Run:** `traces/live-runs/pub02v13.json`, `traces/live-runs/pub09v13.json`
- **Symptom:** After the agent closed the call (`close_call` ok), one more customer message arrived. The conversation resumed as a branch from a point before the close, the agent spoke again after its goodbye, and at hang-up the end-of-call tool sent a second `close_call` with an outcome derived from the old state (`not_verified/declined`, `no_promise/refused`). The bank refused it ("the call is already closed"), but the ledger lists two `close_call` calls, and the brief requires exactly one, as the last tool call.
- **Root cause:** [TO-CONFIRM, platform] The end-of-call tool decides from `close_call_ok` and `close_attempts`, and the rollback erased both. Triggers: a lost 5xx response (F-049, PUB-02) and a closing turn with two spoken messages (F-056, PUB-09).
- **Category:** platform
- **Fix / lesson:** Remove the triggers in our workflow (F-056). Ask the organizers whether the judge's simulation can send a message after the agent ended the call, and whether a rollback can be avoided. A guard that survives a rollback needs a state source outside the variable table; none is known yet.
- **Status:** open (platform, to confirm); the F-056 trigger is fixed offline
- **Retest:** -

### F-056: The closing turn speaks twice, and the next message resumes before the close

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-09 chat on version 13 (ledger passed; LIVE-AUDIT)
- **Run:** `traces/live-runs/pub09v13.json`, customer `c_2413285e-e5d`
- **Symptom:** The restructuring path said its line, and `closing_say` then said the same closing sentence again (twice in the transcript). The turn was recorded as finished at the first line. The next customer message resumed from there as a branch: the close was forgotten, the agent spoke after its goodbye, and the end-of-call tool sent a second `close_call` (F-057).
- **Root cause:** A special path that closes the call spoke its own line on entry, and the closing chain always speaks the closing sentence. The variable the path wrote to mark the line as said was never read. Two spoken messages in one turn make the platform end the turn at the first.
- **Category:** policy
- **Fix / lesson:** A closing turn has exactly one spoken message, from `closing_say`. Closing special steps are silent; `closing` puts the path's line before the closing sentence (once, if one already contains the other). No tts on api steps (F-050). A test walks every spoken step and fails if `closing` can be reached from it through passthrough steps only.
- **Status:** fixed offline (F-056/059 task; review + re-review: merge). Retest pending (PUB-09).
- **Retest:** -

### F-055: Callback date filled by the model with the wrong year

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-02 chat on version 13
- **Run:** customer `c_cd152782-bd5`, scratchpad `pub02v13.json`
- **Symptom:** The husband said Maria can be reached "tomorrow morning around eleven". The agent called `schedule_callback` with `date = 2025-05-15`, `time = 11:00` (expected `2026-10-15 11:00`), then closed `not_reached/callback`. Disclosure rules were kept. Ledger: fail on the callback date only.
- **Root cause:** `schedule_callback.date` is a model-filled field. The model resolved "tomorrow" without knowing the call's date (same family as F-026 for promises).
- **Category:** date-logic
- **Fix / lesson:** Resolve callback dates in code: extract the customer's phrase (date and time), resolve it against `now` with the same resolver as offers, and check it against the brief's callback window, which comes from spec data. A `pre_process_code` hook writes the resolved date into the request, or the step passes a checked value. The model never types the date.
- **Status:** fixed offline (F-055 + review fixes 1–3): `third_party` has no tool; extraction copies the person's day and time words, a `callback_check` code step resolves them against `now` and the spec calendar, checks the spec's callback window (re-asks bounded, then the spec's close value), keeps the day across turns in a code-owned variable, and a silent api step books with the checked values. Unclear or ambiguous times are asked again, never guessed. Reviewed (`reviews/F-055-review.md`, re-review 3: no open finding). Retest pending (PUB-02, day and time in separate messages too).
- **Retest:** -

PUB-09 (restructuring request) **passed the ledger** on version 13: the global special path fired after verification, `transfer_to_agent(restructuring)` and `close_call = transferred/restructuring`.

### F-054: The model computes proposal dates itself and gets the weekday wrong

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-07 chat on version 13 (ledger **passed**)
- **Run:** customer `c_564b6f62-f39`, scratchpad `pub07v13.json`
- **Symptom:** First persuasion: "I can offer a payment of 540 on Friday, 2026-10-17." With `now` = Wednesday 2026-10-14, Friday is the 16th; the 17th is a Saturday. The date was also read as ISO.
- **Root cause:** Brief rules for persuasion name dates relative to the calendar ("last business day of this week"). The prompt gives the rule but not the dates, so the model does calendar arithmetic, which ARCHITECTURE says it must not do.
- **Category:** date-logic
- **Fix / lesson:** Give the negotiate step a computed, spoken calendar: today, the business days of this and next week up to the deadline (weekday + spoken date), the deadline, and the per-product amounts. The prompt says to use only these dates. Generic, from spec calendar data and `now`.
- **Status:** fixed offline (F-053/054 fix): the negotiate step receives a code-made spoken calendar (`calendar_text`) and product facts; the prompt says to use only those dates. Reviewed (`reviews/F-053-054-review.md`, re-review: merge). Retest pending (PUB-07).
- **Retest:** -

### F-053: After the offer check, the agent printed "_call:check_offer{...}" instead of the check result

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-07 chat on version 13 (ledger **passed**)
- **Run:** customer `c_564b6f62-f39`
- **Symptom:** The customer said "Monday the 26th" (a holiday). Routing went `negotiate → check_offer → negotiate` in the same turn, and the agent's message was `_call:check_offer{amount:540.0,date:"2026-10-26"}`. It should have said the check message (offer the next business day). The F-051 prompt rule did not stop it.
- **Root cause:** On re-entry the dialogue model sees the code step's function call in its history and imitates it as text, instead of voicing `offer_message`.
- **Category:** honesty / policy
- **Fix / lesson:** Do not leave the check result to the model. When the verdict is not `ok`, speak `offer_message` deterministically (a code step with a `tts` line, the form that works live, then back to `negotiate` waiting for the customer). When the verdict is `ok` and more is needed, the same. Keep the model's free text for the customer's answers only.
- **Status:** fixed offline (F-053/054 fix): a non-ok or ok+more verdict goes to `offer_say`, a twin of `negotiate` whose entry is the fixed `offer_message` line; `revise_ask` is the same pattern; `negotiate` speaks on every other re-entry, so side-question returns repeat the pending question (no dead air). Reviewed (re-review: merge). Retest pending (PUB-07).
- **Retest:** -

**PUB-07 passed the ledger on version 13** (holiday 26 Oct → promise 27 Oct, 540, one `create_promise`, one `close_call` = `promise`). The judge would likely fail it on F-053 and F-054.

### F-051: Offer check never runs when the customer gives only a date; the model invents limits

- **Date:** 2026-10-11
- **Brief / case:** Brief A, PUB-07 chat on version 12
- **Run:** customer `c_45f705f0-891`, scratchpad `pub07v12.json`
- **Symptom:** The agent proposed "the full payment of 540". The customer answered only with dates ("the week after next", "Monday the 26th", "the 27th works"). `offer_amount` stayed empty, so the route to `check_offer` (date AND amount set) never matched. The agent then:
  - printed "thought `_call:check_offer{amount: 540.0, date: "2026-10-26", product_number: 1}`" to the customer;
  - claimed "Tuesday, October 27th is after the latest possible date; the latest is Monday, November 2nd". This is false and self-contradictory.
  No promise was recorded and the ledger failed.
- **Root cause:** (1) The amount is taken only from the customer's words, but in this brief the agent proposes every amount, so a customer who only names a date accepts the proposed amount. (2) The negotiate prompt lets the model reason about dates and limits when the code verdict is missing (`offer_verdict = none`), and the model treats the code step's name as a tool. Also `offer_setup` writes a value the `offer_amount_kind` enum rejects ("rejected by schema validation").
- **Category:** routing / honesty
- **Fix / lesson:** Route to `check_offer` when a date is set. A missing amount defaults to the amount the agent last proposed: track the proposed kind (full by default, minimum after a floor offer) in state, and let the code fill the number. The negotiate prompt must never state a date or amount limit that is not in `offer_message`, and must not name internal steps. Fix the enum reset in `offer_setup` (write an allowed value or leave the variable unset).
- **Status:** fixed offline (657e6a6, F-052 follow-up 12d9226): a date alone routes to `check_offer`, the amount defaults to the agent's last proposal, the prompt states no limit outside `offer_message`, and enum resets use allowed values. PUB-07 passed the ledger on version 13; a retest of the version 13 judge risks (F-053, F-054) is pending.
- **Retest:** -

Also seen in this run: no 502 at the end of identity (F-050 fix works live); the debt statement and the first persuasion were correct; the Turkish platform filler appeared once more during a slow turn (F-043).

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
