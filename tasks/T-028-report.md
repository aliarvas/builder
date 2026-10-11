# T-028 report: PUB-05 and PUB-08 on Brief A version 19 (asks_back)

**Owner:** claude (claude-dev2 role).
**Inputs:**
- run log `results/e2e-v19/a-asks_back.log`;
- call records `traces/live-runs/user-cb5ac54d-*.json` (PUB-05) and `user-f3bc513e-*.json` (PUB-08);
- spec `traces/brief-a.spec.json`;
- workflow `submission/brief-a.workflow.json` (version 19).

**Not done:** no Freya request, no model call, no commit, no env.sh. Everything is generic: no brief value in `builder/`.

Times are seconds from the start of the call.

## Summary

| Case | Wrong event | Root cause | Fix | Guard |
|---|---|---|---|---|
| PUB-08 | 54.5–98.5: `special_already_paid` → `special_dispute` → `special_already_paid` … 6 times, no word; the customer hangs up | From a global step, the platform tries the other paths' intents **before** the step's `always` exit, and ignores their `excluded_nodes` there | A global step leaves on a deterministic condition that always holds (`now not_equals ""`) | static check `global_exit[<step>]` |
| PUB-05 | 18.4 and 34.9: `verify_identity` returns no `all_verified`, so the call never leaves identity | The bank ledger already held verify, verify, get_account from **another session** for this customer; the bank then omits the overall field | The identity post-hook counts right answers; only when the overall field is missing, and every question has passed, it sets it | scenario `identity_known_earlier` |
| PUB-05 (sympathy) | No sympathy sentence | In this call: the job loss was said inside identity (special paths are excluded there). In general: an ask-first path says its line only when it acts, after the question; on a no it is never said | Optional spec field `say_first`: the line comes before the question, and the closing does not repeat it | check in `_inside_special` ("asks before saying") |

## PUB-08: "I already paid", then silence until hang-up

**Expected:** `paid`, plus "Payments can take one business day to appear."
**Ledger:** `close_call(paid)` by `close_call_on_hangup` at 106.7. The outcome is right, but the judge failed the missing sentence.

**Timeline:**

| t | Event |
|---|---|
| 37.2 | `negotiate`: "… past-due amount is 180. Can you make this payment today?" |
| 39.2 | Customer: "I paid it in the app this morning." |
| 41.3 | `negotiation_reply = special_topic`. **The T-023 fix worked.** |
| 46.5 | `route_evaluated` from negotiate: every step route False; intent `special_already_paid` True. This route took 6.8 s, all of it in the intent model. |
| 46.5–50.3 | `special_already_paid` (global code step) writes `close_state = special:already_paid`. |
| 54.5 | `route_evaluated` **from `special_already_paid`**: the `closing` branch (`always`) has result `null`, so it was not evaluated, and the intents were tried. **`special_dispute` True** ("… paid off in the past"), so the call goes to `special_dispute`. |
| 62.8 | From `special_dispute`: `always` `null`, `special_already_paid` True, so it goes back. |
| … | Same ping-pong at 65.8, 70.9, 75.2, 81.8, 85.5 and 93.4: about 2–7 s per hop for a code run and an intent call. |
| ~100 | The customer hangs up (`customer-ended-call`). `closing_say` never ran, so the sentence was never said. |

**Root cause (builder plus a platform rule we did not know):**
1. **The platform's routing order differs on a global step.** The kit says a global node is checked only after the current node's own transitions found no match. The record shows otherwise for a global code step: its `always` is left unevaluated (`null`) and the intents win.
   - The deterministic branches of a global conversation step are evaluated first: in v18, `special_hardship_support` went to `_go` with every intent `null`.
   - So `always` behaves as a last fallback, after the intents.
2. **`excluded_nodes` is not applied when the current step is itself global.**
   - `special_dispute` lists `special_already_paid` as excluded, yet it fired from there.
   - It looks as if the platform checks the exclusion against the interrupted step (`negotiate`).
3. **Two paths match the same words.** "I paid it" matches both already_paid and dispute ("paid off in the past"), and the last user message stays the same on every hop, so the loop never ends.

**Latency:** the run reports a 73.7 s slowest turn for this call. That is the loop, not the model being slow: 6 hops of a code run plus an intent call.

**Fix (`builder/workflow.py`):**
- **`GLOBAL_EXIT_CONDITION`.** After rendering, every `always` transition of a global step becomes `{"logic":"or","conditions":[{"variable":"now","operator":"not_equals","operand":""}]}`.
  - `now` is a call variable, always set (STARTER-KIT-FACTS).
  - A deterministic condition is tried before intents, as in `negotiate` and in the v18 ask step.
  - `passthrough_default_transition` stays as the fallback.
- **One condition only.** No second `always` is added: Freya merges same-target transitions, and an `always` in the merge would make the exit unconditional again.
- **Affected steps:** closing paths without a tool, spoken-only returning paths, the tool-path entry steps, and the per-step entry steps of model-tool paths. Plain steps are unchanged, since they are excluded correctly.

**Test and guard:**
- `selfcheck.global_always_exits(workflow)`: `run_selfcheck` reports `global_exit[<step>]` as a BUILDER result for each `always` exit on a global step.
- `tests/test_global_exit_identity.py`:
  - no fixture has an `always` exit on a global step;
  - the v19 render (the `always` restored) is flagged for `special_already_paid` and `special_dispute`, also inside `run_selfcheck`;
  - the exit holds in play: `already_paid` closes, and `dispute` is never entered.
- `tests/test_multi_step.py`: the terminal-shape test now expects `GLOBAL_EXIT_CONDITION` on global passthrough and code steps, and still expects `always` on plain steps.

**Risk:**
- The order is inferred from the trace: a deterministic transition on a global code step has not been seen live yet.
- If the platform puts intents before every transition of a global step, the loop stays. The next chat run of PUB-08 shows this at once: `route_evaluated` from `special_already_paid` must show `closing` True.
- **Fallback idea if it does:** make the closing special paths plain steps entered from a single global code step that only writes the path id.

## PUB-05: identity never passed, then not_verified/declined

**Expected:** `no_promise/hardship`. **Ledger:** `close_call(not_verified, declined)` by the hang-up close.

**The tools line `verify > verify > get_account > verify > verify`:**
- Only the last two verifies, and the close, come from this call. The call's own tag says `tool_calls_count 4` (code, verify, verify, hang-up close).
- The bank ledger for this customer already held `verify(dob) ok all_verified false`, `verify(phone) ok all_verified true` and `get_account ok` before the call started. Our records show no other call for this customer.
  - This was probably a first attempt of the case that the simulation restarted. This is **not** a builder fault.
  - It is still a state the agent must survive.

**Timeline:**

| t | Event |
|---|---|
| 18.0–18.4 | `verify_identity(date_of_birth)` returns `{"ok":true,"verified":true,"wrong_answers_left":3}`. **No `all_verified`** (in a normal call the first answer returns `all_verified:false`; see PUB-08 at 18.2). |
| 34.7–34.9 | `verify_identity(phone_last4)`: the same, again no `all_verified`. The mapping `data.all_verified → identity_verified` writes nothing. |
| 37.6 | The identity route is False (`identity_verified` not set). The agent still says the wait line, "please wait a moment while I look up your account". |
| 42–67 | The agent tries `get_account`, which is not a tool of this step (`get_account_response: "The function get_account is not currently available."`). It says "I am currently unable to retrieve your account details …", then "Please try calling us back later". |
| 70.8 | Customer: "I lost my job last month and cannot pay anything. Can I get a discount?" The step is identity, where hardship and restructuring are excluded, so no path starts. The model answers on its own: "I cannot offer any discounts … I can transfer you to a specialist" (the judge failed this as "a plan offered"). It says no sympathy. |
| 78.0 | "No, I do not want to be transferred." |
| 89.7 → 150.7 | The customer hangs up. The hang-up close computes `not_verified/declined`, since identity never passed. |

**Root cause:** the identity exit depends on the overall field alone (`all_verified`). The bank leaves it out when the customer was verified before, so two right answers in this call are not enough. Everything after (the invented "unable", no sympathy, "a specialist") follows from the stuck step.

**Fix (`builder/workflow.py`, `identity_pass_hook`):** appended to the identity tool's post-hook (it runs before `response_mapping`):
- **Counting:** every answer whose own field (`answer_verified_field`) is true adds 1 to `identity_answers_passed`.
- **Setting the field:** only when the result has **no** overall field (`verified_field`) and the count has reached the number of questions does the hook set that field to true. The mapping then sets `identity_verified`.
- **The bank always wins:** an overall field that is present is never touched (false stays false).
- **Honesty:** get_account still refuses if the bank disagrees, and that closes as `account_failed`.

**Test and guard:**
- **Self-check:** `Bank(identity_known=True)` drops the overall field. The new scenario `identity_known_earlier` (every spec with a promise day) plays the normal promise call against it.
  - It passes on all 10 fixture specs.
  - Without the hook it fails exactly like PUB-05: "the call does not reach end_call; it waits at identity" and "closes as not_verified/declined".
- **Tests:** two right answers verify; one does not; a present `false` wins; a wrong answer does not count; the scenario and its mutation on Brief A and A+B.

**Risk:** low.
- If the live platform writes the variable only after the hook, the count still works, because it does not use the arguments.
- A model that asks the same question twice and gets two right answers could count 2. Then get_account decides, and refuses if the bank disagrees.

## PUB-05: the sympathy line (also without the identity problem)

**Why none in this call:** the job loss came during identity, where no hardship path can start (see above).

**Why it would still go wrong:**
- `support` is an ask-first path. Its `say` ("I am sorry to hear that.") is the line said when the agent acts, so it is spoken in the closing, after the transfer (T-021, T-023 open item).
- With `on_decline: hardship_declined` (now in the live spec), a no closes on `hardship_declined`'s own line ("I understand."), so the sympathy sentence would **never** be said.

**Fix:** the optional spec field `say_first` (only with `ask`). It means the documents say the line when the situation starts, before the question (for example sympathy before an offer).
- **`spec.py`:** parses it and rejects it without ask.
- **Extraction:**
  - the outcomes prompt asks for it;
  - `_check_outcomes` asks for a repair, and in the last round only warns;
  - `merge_groups` drops it when it cannot be used, so a bad value never fails a build.
- **Render:**
  - **tts question:** the step speaks "I am sorry to hear that. Would you like me to connect you with our customer support team?";
  - **agent-phrased question:** the task gets `SPECIAL_SAY_FIRST_LINE` ('Before the question, say word for word: "…"');
  - **Closing:** the closing's FIRST_LINES leave the path out, so the line is not said twice.
- **`human_request`:** unchanged ("I will connect you with a colleague now" stays after the yes), because extraction leaves `say_first` out there.

**Guard:** `_inside_special` checks, at a `say_first` question, that the step speaks the line (on_enter or task). Otherwise it reports "asks before saying …". The test removes the line from the v19 render, and `special_hardship_support_declined` fails.

**Live spec:** `traces/brief-a.spec.json` has `on_decline` but not `say_first`. With `say_first` set by hand, the render speaks the line first, and the self-check is green (95 results, 0 failed). The next build's extraction fills it.

**Prompt budget:** the step prompts are unchanged, except the ask step of a `say_first` path, which grows by one sentence. The extraction prompt grows by one key.

## Tests

- **New** `tests/test_global_exit_identity.py` (11 tests): global exits (3), identity without the overall field (3), say_first (5).
- **Changed:** `tests/test_multi_step.py` (global exits in the terminal-shape test).
- **Render pin:**
  - `BRIEF_A_RENDER_SHA256` = `1a2af43d…` is the value of HEAD plus T-028 and T-026 only, checked in a scratch copy with claude-dev's T-027 files taken out.
  - My diff of the Brief A render: the global exit conditions, the identity hook, the system prompt line (T-026) and the opening line (T-026). Nothing else.
- **`python3 -m unittest`:**
  - **My changes alone** (scratch copy: this tree minus claude-dev's `offer_check.py`, `product_notes.py`, `goodbye.py` and their 3 lines in `workflow.py`): **602 tests, OK**.
  - **The shared tree** is red right now because of T-027 work in progress:
    - The new global `customer_ends_call` is added after the special-topic value, so my T-023 check `intent_shadow` flags it ("not named: The customer ends the call…") in the fixture self-check tests.
    - The leak test flags `'type'` in the new `builder/goodbye.py`.
    - The negotiate budget (1705 > 1700) comes from `PERSUASION_PRODUCT_LINE`.
    - I told claude-dev; I did not edit their files.

## Open

- **Live confirmation (with approval):** a chat run of PUB-08 and PUB-05.
  - PUB-08: the route from a global code step must show its own exit True with the intents `null`.
  - PUB-05 can only repeat the "verified earlier" state if the simulator restarts a case. The hook is checked offline.
- **Re-extract Brief A** so that `say_first` is filled for `support`.
- **Kit docs vs. live:** "global nodes are checked after the current node's own transitions" does not hold for an `always` transition on a global step. Worth a line in `docs/STARTER-KIT-FACTS.md` after the live check (`[TO-CONFIRM]` until then).

## Update after T-027 landed

- **Shared tree:** `python3 -m unittest` gives **615 tests, OK**.
- **Render pin:** claude-dev re-pinned it (`69c6e9db…`); the comment says it moves for both T-028/T-026 and T-027.
- **Global exit check on the new step:** `customer_ends_call` (T-027) also leaves on `GLOBAL_EXIT_CONDITION`, and `global_always_exits` finds nothing on Brief A.
