# T-020: Brief A v18, style asks_back: PUB-02 and PUB-04

Analysis only: no code change, no Freya, no commit, no env.sh.

Sources:
- `results/e2e-v18/a-asks_back.log` (6/10)
- `traces/live-runs/user-8e3d1980-*.json` (PUB-02)
- `traces/live-runs/user-67fa26bd-*.json` (PUB-04)
- `traces/brief-a.spec.json`
- `submission/brief-a.workflow.json` (version 18)

The run log warns that the agent was slow (median slowest turn 26 s, worst 50 s).

## PUB-02: close_call before schedule_callback

**Ledger:** `close_call` (not_reached / no_callback) arrives as n=1. Then `schedule_callback` (2026-10-15 11:00) arrives as n=2: `ok:false, "the call is already closed"`. The case expects `callback` and the booked slot.

**Timeline** (seconds from start):

| t | event |
|---|---|
| 2.1 | user: "No, this is her husband. What is this call about?" → `caller_role=other_person` → `third_party` |
| 4.5 | user: "Why do you need to reach her?" → `third_party_reply=none`, no route; agent asks again |
| 11.2 | user: "She can be reached tomorrow morning around" (cut off) → day `tomorrow`, time `morning around` → `callback_check` → verdict not ok → `third_party_ask` ("Sorry, could you tell me the day and the time…"). Right. |
| 15.1 | user: "…tomorrow morning around eleven." → `callback_check` → `window_ok` → `callback_book` |
| **16.7** | `function_call_start api_call schedule_callback` {date 2026-10-15, time 11:00} (`timeoutMs 10000`, `maxRetries 0`) |
| **26.7** | **no `function_call_complete`**. Exactly 10.0 s later, `callback_book` takes its `always` route → `closing` |
| 26.9 | `closing` computes `callback_failed` (no ok result) → row not_reached / no_callback; `closing_say` "Thank you for your time. Goodbye." |
| 27.2 | `close_record` → `close_call` ok → `end_call` |
| later | the timed-out `schedule_callback` reaches the bank after `close_call` and is refused (ledger n=2) |

**Root cause:**
- The platform timed out the booking request after 10 s (`timeoutMs` 10000, which our renderer sets for every OpenAPI tool).
- The bank received it more than 10.5 s after the start, after the close. The mock was slow in this run.
- The workflow behaved honestly: with no result it booked nothing and said nothing false. But it closed the call, and so the late booking was refused.
- Category: platform/bank latency, plus our timeout choice. Not a routing bug.

**Generic fix proposal:**
1. Raise `timeoutMs` for the tools that write (`schedule_callback`, `create_promise`, `add_note`, `transfer_to_agent`, `close_call`) to about 30000, the same as the documented `code_exec` default.
   - The kit documents no default or limit for `timeoutMs`; its examples use 10000. Check it in one chat run before relying on it.
   - **Risk:** low to medium. A real outage now means up to 30 s of silence, after which the failure path runs as today. The customer may hang up during the wait; the hangup tool then records the provisional close.
2. Optional: a short spoken holding line before slow write steps ("One moment while I book that."), so a long wait is not silent. The `on_enter` of an `api_request` step is silent today.
   - **Risk:** low, but it is a new spoken line in every booking path.
3. **Do not retry** a timed-out write (`maxRetries` stays 0). The kit warns that a retried write can record twice, and the timeout here did reach the bank.

**Same risk elsewhere:** `create_promise` (record loop) also has 10 s. A timeout there is counted as a failure and retried by our record loop. The bank may then get the first request late *and* the retry, a possible double promise or a "service_error" note. Raising the timeout reduces this too.

**Self-check:** cannot play it today. The simulated bank always answers at once.
- It could play a "no result" answer (the tool step leaves its result variable empty) and check that the call does not claim the booking.
- But it cannot model the late arrival after the close, which is the real failure here. Only the timeout value fixes that.

## PUB-04: promise 1250 on 2026-10-23 not recorded (no_promise / refused)

**Ledger:** two `verify_identity` calls, `get_account` (p1 car_loan 1250, 14 days late), then `close_call` no_promise / refused from the **hangup tool**. No promise.

The robot question was answered this time (`special_robot_question`, msg 57), so F-074 did not occur in this run.

**Timeline of the wrong part** (msg index, seconds):

| msg | t | event |
|---|---|---|
| 50 | 192.3 | `negotiate`: states 1250, 14 days late, "Can you make this payment today?" |
| 51 | 213.2 | user: "My salary arrives on the sixth of November and I can pay then. Am I talking to a robot?" |
| 52–54 | 226.2 | `offer_date` = "the sixth of November" **extraction_failed (confidence 0.53)**; `offer_amount_kind` failed (0.62); `negotiation_reply=proposes_terms` |
| 55–59 | 226.4 | route → `special_robot_question` ("I am Freya Bank's digital assistant.") → back to `negotiate` |
| 60 | 231.7 | `negotiate` (**the model, not `check_offer`**): "The latest date I can record is Friday, 23 October. Can you make the payment of 1250 on that date?" |
| 61 | 244.6 | user: "Yes, I can pay on the twenty-third of October." |
| 62–66 | 262.1 | `offer_date` = "twenty-third of October" **failed (0.62)**; `offer_accepts_proposal` = yes **failed (0.53)**; `offer_amount_kind=full`; `negotiation_reply=agrees_terms` → **no transition matched** |
| 67 | 279.2 | assistant: **"Bir saniye lütfen."** (Turkish filler on an English call) |
| 68–70 | 285.9 | user: "Okay." → `offer_accepts_proposal=yes` (0.96) → `check_offer` |
| 71–76 | 288.1 | `check_offer`: `offer_date` is empty, so it uses `offer_suggested_date`, which is **empty** (no check proposed a date; the model did). Verdict `missing` → `offer_say`: "Could you tell me the exact day you would like to pay?" |
| 77–124 | 289–415 | four times: user "Twenty-third of October." → `offer_date="Twenty-third of October"` (0.97–1.0) → `check_offer` → **`missing`** again → the same question |
| 125–128 | 416.8–431 | user repeats; the call ends (customer hang-up) → `close_call_on_hangup` no_promise / refused |

**Root causes** (all builder-side, generic):

1. **The date reader does not read spelled-out ordinals.**
   - `resolve_offer_day` (offer_check `PRELUDE`) needs a digit day. "23 October", "October 23rd" and "2026-10-23" work. "Twenty-third of October", "the twenty third of October" and "the sixth of November" return `None`. Reproduced with the v18 `check_offer` code.
   - The extraction field says "copy the payment date phrase … unchanged", so spoken words reach the code as words.
   - The asks_back and in_words customer styles say dates this way.
2. **`missing` has no limit and no help.**
   - The rejection counter skips `missing` (and `amount_missing`, `product_unknown`, `date_ambiguous`). The same unreadable answer loops with the same question until the customer gives up.
   - The question also gives no hint of the form wanted.
3. **A date the model proposed is not stored.**
   - The deadline offer at msg 60 came from the `negotiate` prompt, not from `check_offer`. So `offer_suggested_date` was empty, and a plain "yes" / "okay" could not resolve to 23 October.
   - The negotiate prompt lets the model propose a date the code never saw.
4. **Contributing: low extraction confidence on a turn that both accepts and names a date** (msg 62–64). Both fields failed the 0.8 threshold, so no route matched.
5. **Platform:** the filler "Bir saniye lütfen." comes from the omitted `agent_config` defaults (Turkish), as seen in T-013. Not ours to fix while `agent_config` must be omitted; worth an FAQ question to the organisers.

**Generic fix proposals:**

- **(a) Number words in `resolve_offer_day`** (biggest effect, low risk): convert English cardinal and ordinal words 1–31 to digits before the month match:
  - "first" … "thirty-first", "twenty three", "twenty-third", "the sixth";
  - the same normalisation in the callback reader if it lacks it.
  - **Risk:** low. English only (the agent language), the code only. Words like "second" may be read as a day only when a month name is in the same phrase.
  - **Test:** a table of spoken forms → dates, plus a self-check scenario with a word-form date.
- **(b) A limit and a clearer question for `missing`**:
  - after the second `missing` in a row for the same product, say a fixed line that asks for "the day and the month, for example the 23rd of October" (the example built from the latest allowed date, so there is no brief value);
  - after the third, treat it as a rejected offer, so the existing offer limit applies.
  - **Risk:** low to medium. It changes how many turns a confused customer gets; the limit must not count a date that was read but rejected twice.
- **(c) Keep the model from proposing a date the code has not checked:**
  - On a `missing` verdict, `check_offer` already proposes `[date]`. When the customer names no readable date, the code could propose the latest allowed date itself and store it in `offer_suggested_date`, so "yes" works.
  - Alternatively, a negotiate prompt line "never propose a date yourself; the program proposes dates" (+~20 tokens on a step already over 1500).
  - **Risk:** medium. It changes who says the first counter-offer.
- **(d) Lower the extraction threshold** for `offer_accepts_proposal` / `offer_date` from 0.8 to about 0.6:
  - **Risk:** medium, with false accepts. Only together with (b), so a wrong accept still reaches the read-back confirmation.
  - I would not do it first.

**Self-check:**
- (a) **yes**: the scenarios pass dates in ISO form only (`plan.offer(1, day)` with `day` ISO). A family with spoken forms ("twenty-third of October", "the 6th of November", "23rd October") would have caught this offline, as T-014 did for relative callback times.
- (b) **yes**: a scenario that answers an unreadable date three times and expects the clearer line and then the offer limit (today it would run into the turn limit).
- (c) **partly**: the simulator does not run the model's speech, so it cannot see the model proposing a date. It can check that "yes" after a `missing` verdict resolves to the code-proposed date once (c) exists.
- (d) no: confidence is the platform's.

## Proposed UAT entries (CTO)

- **F-075 — Booking request timed out and arrived after the close (PUB-02, v18 asks_back).**
  - Symptom: close_call came before schedule_callback; no_callback instead of callback.
  - Cause: 10 s tool timeout on a slow bank; the late request was refused as "already closed".
  - Fix: a longer timeout for writing tools (proposal above).
  - Status: open.
- **F-076 — Spelled-out dates are not read (PUB-04, v18 asks_back).**
  - Symptom: "twenty-third of October" was asked again four times; the customer hung up; no_promise instead of the promise.
  - Cause: the offer date reader needs digits, `missing` has no limit, and a date the model proposed is not stored for "yes".
  - Fix: number words in the reader, a limit and a clearer question for `missing`, code-proposed dates.
  - Status: open.
