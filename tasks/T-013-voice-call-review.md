# T-013: review of the user's voice call on published version 16

**Call:** `67e7c720-3a1d-4341-9968-8b913f24b099` (web call, voice, 168 s, `assistant-ended-call`).
**Workflow:** `b0bdd6e6`, version 16, assistant "brief-a 1010-152338".
- It was built by the `traces/brief-a.log` run at 2026-10-11 10:30Z (builder at commit 6490baf, F-065; before T-010, T-011 and T-012).
- The export is `submission/brief-a.workflow.json`; the spec is `traces/brief-a.spec.json`.

**Source:** `traces/live-runs/user-67e7c720-….json`, 114 messages: node_enter, route_evaluated, variable_extracted, function_call_*, and the variable tables.
**Method:** offline. I read the call record, the export, the spec and `brief-a.md`. I re-ran the export's `callback_check` code locally with other `now` values. No Freya, no model call, no commit, no env.sh.

## Summary

The call never left the third-party step until the callback request:
- One misheard opening answer routed the customer to `third_party`.
- When the person then said "I am Mx Customer", the step had no way back to verification. The model improvised an identity check of its own (date of birth plus an invented "first line of your address") for 16 turns, without any tool.
- At the end the person asked for a callback "two hours later". The callback code read that as 14:00 (the word "two" as a clock time), not as now + 2 hours. With the placeholder `now` (12:00) the result looked right by chance.
- Booking and closing failed because of the placeholder `customer_id`. The workflow handled that honestly: no false claim, close tried twice, then `end_call`.

**Four builder or workflow problems must be fixed (C1–C4).**

## Timeline

| t (s) | Step | Event | Detail | Assessment |
|---|---|---|---|---|
| 0.0 | opening | agent | "I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with Mx Customer?" | Correct (rules 1–2). "Mx Customer" is the placeholder (A1). |
| 8.6 | opening | user | "Yani, I'm in X class mı" (STT for roughly "Mx Customer mı?") | B1: STT garbled; Turkish STT (D1). |
| 10.5 | opening | extract | `caller_role = other_person`, confidence 1.0 | **Wrong.** It is not a confirmation (rule 3), but nothing says someone else answered. It should be `unclear` → ask again (C3). |
| 10.5 | opening → third_party | route | `caller_role == 'other_person'` | Follows the wrong extraction. |
| 10.5 | third_party | agent | "I am calling from Freya Bank. When would be a good time to reach Mx Customer?" | Correct for a third party (rule 5). |
| 18.2 | third_party | user | "I am MX customer" | By rule 3 the customer's own name counts as confirmation. |
| 18.2 | third_party | (no extraction event) | The step has no value for "I am the customer" and no route back to identity | **C1** |
| 22.6 | third_party | agent | "To ensure your security, could you please provide your full date of birth and the first line of your address?" | **C2:** security questions asked in the third-party step, without `verify_identity`, two at once, and one of them invented. The brief asks for date of birth, then the last four phone digits, one at a time (rule 11). |
| 30.9–45.8 | third_party | user/agent | "let me check" / "Kas'ta mı ne" / "I will wait" | B2: Turkish fragments. No extraction until 47.7. |
| 47.7 | third_party | user | "İyi günler" (Turkish: "good day", used as a goodbye) | |
| 49.5 | third_party | extract, route | `third_party_reply = none`, `close_kind = other`; no transition matched | The extraction is defensible: a Turkish farewell is not an English closing value. |
| 49.6 | third_party | agent | "Goodbye." | **C4:** the model says goodbye in a step that cannot close. The call goes on. |
| 50.8–53.7 | third_party | user/agent | "Wait what" / agent "I" (interrupted) / "I am sorry, I may have misunderstood. Are you still there?" | B3: barge-in; a platform interruption. |
| 59.4–69.7 | third_party | extract ×2, no route | "Yeah, I'm still there" / "Just a minute" → `none` | Correct (`none`); the agent asks the invented questions again (C2). |
| 76.0 | third_party | user | "My birthday, 14 Mart 1988" (Turkish month) | A security answer collected from someone the workflow treats as a third party (rule 10). No field and no tool, so nothing was verified (C2). |
| 82.0 | third_party | agent | "Thank you. Could you also please provide the first line of your address?" | C2 |
| 88.8–103.1 | third_party | user/agent | "Why do you want my address" / "Do you have any option for identity" → agent: "I can only verify your identity using your full date of birth and the first line of your address." | **C2, honesty:** a false statement about the verification process. |
| 114.2–126.9 | third_party | user/agent | "Should I take my credit card number" → "No, I only need the first line of your address" | C2; B4 (barge-in). |
| 137.1–145.2 | third_party | user/agent | "I can't find my line address" → "Would you like to find it and continue, or should we try again later?" | C2. The agent offers "try again later", which is close to a callback offer; acceptable. |
| 158.9 | third_party | user | "Can you call me two hours later" | |
| 161.9 | third_party | extract | `callback_time_text = "two hours later"`, `third_party_reply = callback`, `close_kind = other` | The extraction is right (words copied unchanged). |
| 162.0 | third_party → callback_check | route | the time text is set | Correct. |
| 162.0–163.0 | callback_check | code_exec | `callback_date = 2000-01-03`, `callback_time = 14:00`, `verdict = window_ok` | **C5 (time):** "two" is read as a clock hour with an afternoon guess (14:00), not as now + 2 h. The date 2000-01-03 comes from the placeholder `now` (A2). |
| 163.0 | callback_book | api_call `schedule_callback` | body `{date: 2000-01-03, time: 14:00, customer_id: placeholder_customer}` → 404 `unknown customer_id` | A3 (placeholder id). |
| 163.2 | closing | code_exec | state `callback_failed` → `not_reached / no_callback`, sentence "Thank you for your time. Goodbye." | Correct by the spec table (callback failed → no_callback). The agent does not say the callback could not be booked (C6, LOW). |
| 163.5 | closing_say | agent | "Thank you for your time. Goodbye." | Brief rule 47 is followed: goodbye before `close_call`. |
| 166.9 | close_record | api_call `close_call` | `{outcome: not_reached, reason: no_callback, customer_id: placeholder_customer}` → 404 | A3 |
| 167.1–168.0 | close_attempt → close_record | retry | second `close_call` → 404; route to `end_call` ("failed twice; end without claiming success") | Correct honest end (F-063/F-065 design). |
| 168.0 | end_call | end_call | `call_ended: assistant-ended-call` | |
| 184.1 | (end of call) | `close_call_on_hangup` | error "Missing required field: url" | D2: the fail-closed hook skips (close was already attempted) by leaving the URL empty, and the platform logs that as an error. No extra close was sent. |

## Findings by cause

### (a) Missing variables or test setup

- **A1:** The test was started from the UI without call variables, so the builder's `test_variables` defaults were used (`workflow.py`: `title=Mx`, `last_name=Customer`, `customer_id=placeholder_customer`, `now=2000-01-03T12:00`). The agent asked for "Mx Customer" as designed.
- **A2:** `now = 2000-01-03T12:00`, so the callback was dated 2000-01-03. With the real `now` the date logic would use the brief's day.
- **A3:** `customer_id = placeholder_customer`, so `schedule_callback` and both `close_call`s returned 404 `unknown customer_id`. The outcome `not_reached/no_callback` (callback failed) and the end without a recorded close follow from that.
- **Proposal:** a UI voice test needs real variables. A line in the test guide would help: the case's `customer_id`, `now`, `title`, `last_name`. Alternatively the builder could make the placeholders obviously fake in speech, but that is not needed.

### (b) Voice and STT effects

- **B1:** "Mx Customer mı?" was transcribed as "Yani, I'm in X class mı". The garbled answer is the trigger for C3.
- **B2:** Turkish fragments ("Kas'ta mı ne", "İyi günler", "14 Mart 1988", "Hı hı"). The workflow speaks English and its STT runs in Turkish (D1).
- **B3/B4:** Barge-in cut the agent's turn ("I"). The `interrupted` events are platform behaviour.
- Calls are scored in text (STARTER-KIT-FACTS), so B effects do not affect the score directly. C3 can still happen in text with an unclear answer.

### (c) Builder and workflow problems to fix

**C1: HIGH. No way back from the third-party step when the person turns out to be the customer.**
- `third_party` routes only to `closing`, `third_party_close_check` and `callback_check`. Its intent enum (`callback`, `no_callback`, `wrong_number`, `deceased`, `none`) has no value for "I am the customer" or "the customer is now on the line".
- After any misroute (C3), or when a relative hands over the phone, the call cannot reach verification, negotiation or a promise. Here it cost 16 turns and ended as `not_reached`.
- Brief rule 3: "the customer's own name counts as confirmation".
- **Fix (generic, no brief value):** a framework value in the third-party intent (like `none`): "the person says they are the customer, or the customer comes to the phone". It routes to the confirmation, then `identity_check`, with the rule-3 wording in its description.

**C2: HIGH (policy and honesty). The model runs its own identity check in the third-party step.**
- With nothing to route "I am the customer", the model asked for date of birth plus "the first line of your address". The address appears nowhere in the brief, spec or workflow; it is model knowledge.
- It collected a date of birth from a person the workflow treated as a third party (rule 10), asked two questions at once (rule 11), and never called `verify_identity`.
- It then said, falsely, "I can only verify your identity using your full date of birth and the first line of your address".
- In a scored case this fails policy (rules 10 and 11) and honesty (an invented process).
- **Fix:**
  - C1 removes the trigger;
  - in addition, the `third_party` task gets a fixed line: "Never ask security questions or for any personal data in this step; only the program verifies identity". Generic, no brief value;
  - the same line fits `opening` and `opening_unclear`.

**C3: MEDIUM. The opening extraction picks `other_person` for an answer that is neither a confirmation nor a third party.**
- The `caller_role` field description defines only `greeting`. `other_person` and `unclear` have no description, so a garbled question ("…X class mı?") was read as someone else, with confidence 1.0.
- Rule 3 makes a non-confirming answer `unclear`: ask once more.
- **Fix:**
  - describe each opening value in the extraction field: `other_person` only when the person clearly says they are not the customer (for example "this is her husband", "he's not here"); anything else that does not confirm is `unclear`;
  - this is the same pattern as the third-party `close_kind` (F-064).

**C4: MEDIUM. "Goodbye." in a step that cannot close.**
- At "İyi günler" the model said "Goodbye." in `third_party`. No route matched, so the call went on, and the customer was confused ("Wait what").
- In a text case this is a policy risk: a goodbye before the close tool, with the call then continuing.
- **Fix:** a fixed line in every conversation step that has no closing route of its own: "Never say goodbye or end the call yourself; the program closes the call." Today only `closing_say` says goodbye.

**C5: HIGH for callback cases. A relative time ("two hours later") is read as a clock time.**
- The `callback_check` code of v16 reads "two hours later" as hour 2, then the afternoon guess gives **14:00**, whatever `now` is. Reproduced offline with the exported code:

| `now` | "two hours later" | "in two hours" |
|---|---|---|
| 2000-01-03T12:00 | 14:00, window_ok (correct here only by chance) | unclear (asks again) |
| 2026-10-14T11:00 | **14:00** (should be 13:00) | unclear |
| 2026-10-14T15:30 | **window_outside** (17:30 would be inside) | unclear |

- The `DURATION` pattern in `builder/callback.py` catches "in/within/after N hours" and "N hours from now" (and asks again), but not "N hours later". That form falls through to the clock-time parser.
- A wrong `schedule_callback` time fails the ledger for the callback case.
- **Fix:**
  - treat "<n> hours/minutes later" (and "later by…") as a duration: either compute now + duration, or ask for a clock time, as "in two hours" does today;
  - add tests with several `now` values.
- I did not check the current tree (after T-010/T-012). `builder/callback.py` is claude-dev2's area, and this task allows no code changes.

**C6: LOW. After a failed booking, the goodbye does not say the callback could not be booked.**
- The outcome is right (`no_callback`), and no false claim was made ("Never say a callback is booked": OK). The person still asked for a callback and hears only "Thank you for your time. Goodbye."
- The brief has no rule for it. As with F-063 for promises, a plain "I could not book the callback" line on the `callback_failed` state would be more honest.
- Proposal only.

### (d) Platform behaviour

- **D1:** `agent_config` was omitted (rule), so the platform defaults apply: STT `language: tr`, TTS `language: tr`, voice `leyla`, model `experimental-5`, temperature 0.7, and a Turkish first message in the default config (not used: the workflow speaks first).
  - English speech through Turkish STT explains part of B1/B2.
  - This only matters for voice; the competition scores text. **Question for the CTO/organizers:** may a voice test set the STT language, or is voice out of scope?
- **D2:** The end-of-call tool `close_call_on_hangup` logs "Missing required field: url" when its pre-hook skips (fail-closed, T-005c). That is expected and harmless (no second close), but it shows as an error in the call log.
  - A judge or reviewer reading the log may take it for a failure. Possible later change: keep the real URL and send a harmless body, but fail-closed was chosen on purpose. Note only.
- **D3:** There are many `interrupted` events, and turn-taking is decided by the platform (`smartTurnEnabled`).

## Would `builder/selfcheck.py` have caught (c)?

| Finding | Caught? | Why |
|---|---|---|
| C1: no route back from third party | **No** | Scenarios come from the spec. The spec has no "customer comes to the phone" value, so there is nothing to play. A generic scenario family (third party, then "I am the customer", expect identity) would catch it once C1 adds the value; without the value, that family would report a dead end. |
| C2: model asks security questions | **No** | A model behaviour; the self-check uses ideal extraction and does not run the model. Layer 2 (chat test with a third-party persona) is needed. |
| C3: wrong opening extraction | **No** | Extraction quality; ideal extraction always gives the right value. Layer 2. |
| C4: free goodbye | **No** | Model speech; the self-check counts only scripted spoken steps. Layer 2, or a prompt lint (every conversation step without a closing route carries the "no goodbye" line). |
| C5: "two hours later" → 14:00 | **No** today, but **could** be | The callback scenarios use clock-time text ("HH:MM"). A family with relative phrases ("in two hours", "two hours later", "in an hour") checked against the spec window and `now` (several `now`s, as `check_nows` does) would catch it offline, because it is pure code. Best ROI. |
| C6: silent failed booking | No | The ledger is right; it is a speech-content issue. |

**Note:** v16 was built before T-010, so this call ran without the self-check. Only C5 is a code fault, and the self-check could find it with one more scenario family.

## UAT proposals (for `docs/UAT-FINDINGS.md`, CTO)

- **F-069: A third party who turns out to be the customer cannot get back to verification.** Symptom: after the opening routed to `third_party`, "I am Mx Customer" had no route; the call stayed in the third-party step for 16 turns and ended `not_reached`. Cause: the third-party intent has only callback and closing values, with no value or transition for "the person is the customer / the customer comes to the phone". Fix: a framework value in the third-party intent that routes back to confirmation and identity (rule 3 wording). Status: open.
- **F-070: The model ran its own identity check in the third-party step and invented a question.** Symptom: it asked for date of birth plus "first line of your address" (not in the brief), collected a date of birth, never called `verify_identity`, and said the address was the only way to verify. Cause: no route for "I am the customer" (F-069), and the third-party prompt does not forbid security questions. Fix: F-069, plus a fixed rule in the third-party and opening steps: never ask security questions or personal data there; only the program verifies. Status: open.
- **F-071: An answer that does not confirm is read as "someone else answered".** Symptom: "…X class mı?" (an unclear question) gave `caller_role = other_person` (confidence 1.0) and routed to the third-party step instead of asking again. Cause: the opening field description defines only `greeting`; `other_person` and `unclear` are not described, and rule 3 (non-confirmation → ask once more) is not in the extraction field. Fix: describe each opening value; `other_person` only when the person clearly says they are not the customer, anything else that does not confirm is `unclear`. Status: open.
- **F-072: The agent says goodbye in a step that cannot close.** Symptom: "Goodbye." in `third_party` after a Turkish farewell; no route matched and the call continued. Cause: conversation steps do not forbid a goodbye; only `closing_say` should say it. Fix: a fixed line in every conversation step without a closing route: never say goodbye or end the call yourself. Status: open.
- **F-073: "N hours later" is booked as a clock time.** Symptom: "call me two hours later" was booked for 14:00 whatever `now` is (for example 14:00 at 11:00; "outside the window" at 15:30). Cause: the duration pattern in the callback code covers "in N hours" and "N hours from now" but not "N hours later", which falls through to the clock-time reader with the afternoon guess. Fix: treat "<n> hours/minutes later" as a duration (compute it from `now` or ask for a clock time), plus a self-check family with relative callback phrases over several `now` values. Status: open.

Not proposed as findings: A1–A3 (test setup), B (STT), D2 (by design). D1 is a question for the organizers.

## Proposed next steps (CTO decides)

1. **C5** (`callback.py`, small, offline-testable) plus a self-check family with relative callback phrases.
2. **C1 + C2 + C3** together (third-party return value, prompt lines, opening value descriptions), then a chat test with a "relative hands over the phone" persona and an unclear opening.
3. **C4:** the no-goodbye line, checked by a prompt lint test.
4. For the next voice test: start with the case variables (`customer_id`, `now`, `title`, `last_name`) and decide on D1.
