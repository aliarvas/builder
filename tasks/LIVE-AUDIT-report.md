# LIVE-AUDIT report: step-by-step review of five live chat runs

**Owner:** claude (second developer) · **Sources:** `traces/live-runs/{pub01v10,pub07v12,pub07v13,pub02v13,pub09v13}.json` (driver log, Freya call record, bank ledger), `build-the-builder-v2/public-test-set.json`, Brief A.
**Code compared:** commit `53efa1a` (F-053/054/055, T-009c). Each "still in code?" verdict was checked by reading the code. Where possible it was also checked by rendering the current workflow offline from `traces/brief-a.spec.json` and running the generated code with the run's own variables.
**Not done:** no code change, no Freya request, no commit, no env.sh. New findings are proposed numbers (F-056 to F-060). I did not write them into `docs/UAT-FINDINGS.md` because this task named only this report.

Severity:
- **HIGH**: can fail the ledger or the judge (policy or honesty) on a case.
- **MED**: a judge risk, or a defect with a plausible failing case.
- **LOW**: cosmetic, noise or latency.

## Summary

| Run | Expected | Ledger result | Real verdict |
|---|---|---|---|
| PUB-01 v10 | promise p1 420 on 2026-10-14 | promise p1 420 on 2026-10-14, `close_call=promise` | **pass** (ledger); judge risks below |
| PUB-07 v12 | promise p1 540 on 2026-10-27 | no promise; hang-up close `no_promise/refused` | **fail** (F-051) |
| PUB-07 v13 | promise p1 540 on 2026-10-27 | promise 540 on 2026-10-27, `close_call=promise` | **pass** (ledger); judge likely fails (F-053, F-054) |
| PUB-02 v13 | callback 2026-10-15 11:00, `not_reached/callback` | callback **2025-05-15** 11:00, plus a 2nd, refused `close_call` | **fail** (F-055) |
| PUB-09 v13 | transfer restructuring, `transferred/restructuring` | correct, plus a 2nd, refused `close_call` | **pass** (ledger); judge risk on rule 46 |

**False-positive warning.** `ledger.ok: true` in these files is only the status of the ledger API response. It does not mean the case passed. PUB-02 shows `ok: true` with the wrong callback date. Always compare `promises/callbacks/transfers/outcome/reason` with `expected`.

**Most important new finding (HIGH).** In PUB-02 and PUB-09 a message after the goodbye branched the conversation back to a point before the close. The call state was lost, the agent spoke again, and the hang-up hook sent a **second `close_call`**. The bank refused it ("the call is already closed"), but the ledger still lists two `close_call` calls. Brief rule 46 says "exactly one `close_call` … it is the last tool call". In PUB-09 the trigger is in our code (two spoken lines in one turn, F-056). In PUB-02 the trigger is a lost 5xx response (F-049).

## PUB-01 v10 (happy path, ledger pass)

| # | Step | Problem | Severity | F-xxx | Still in code? |
|---|---|---|---|---|---|
| 1 | Opening | Line "…the call is recorded.\n Hello. Am I speaking…": a stray newline and "Hello" after the introduction. | LOW | new (no number) | Seen again in v13 ("…recorded. Hello. Am I…"). The model writes the opening, so it can happen. |
| 2 | Identity turn 3 (DOB) | Driver waited 43.0 s; the engine took 2.8 s. Almost all of the delay is in the chat API. | LOW | F-023 | Platform/test route; not our code. |
| 3 | After identity → account → offer_setup | Platform filler **"Bir saniye lütfen."** (Turkish) was spoken. The model's text `call:get_account{}` was blocked (`wasBlocked`): the model tried to write a tool call as text. | MED | F-043, F-053 family | Possible. `account` stays silent (F-050), so the platform filler can come back. In the three v13 runs it did not appear. |
| 4 | offer_setup | `validation_errors`: `offer_amount_kind` rejected by schema validation (enum reset ""). | LOW | F-051/F-052 | **Fixed.** Enum resets now write `none`, which is in every enum (checked in the current render). v13 setup has no errors. |
| 5 | check_offer | 4 `validation_errors` (`offer_amount_kind`, `negotiation_reply`, `offer_amount`, `readback_reply`). | MED | F-052 + **F-060 (new)** | Enums **fixed**. `offer_amount` (float) is still reset with `""` (`offer_check.py:747`), and the platform rejects it. See F-060. |
| 6 | Read-back | "For Product 1, the amount is 420.00 and the date is Wednesday 2026-10-14." The product number, ISO date and decimals were read aloud. | MED | F-044 | **Fixed** (v13 says "personal loan for 540 on Tuesday, 27 October"). |
| 7 | Close | `create_promise` once, ok; text-message line after the promise; `close_call=promise` once. | — | — | OK |
| 8 | Last turn | Driver: `<processed, response lost>`. The engine finished the turn (end_call 104.7 s). | LOW | F-049 | Platform. |
| 9 | End of call | `close_call_on_hangup` → `function_call_error: Missing required field: url`. | LOW (log noise) | — (T-005c design) | By design: the fail-closed hook leaves the URL empty when the close is already recorded. Not a defect, but a log reader may take it for an error. |

Checks: both security answers came before `get_account` ✓, "collections" was not said before verification ✓, `create_promise` exactly once ✓, text-message sentence ✓.

## PUB-07 v12 (dates, ledger fail)

| # | Step | Problem | Severity | F-xxx | Still in code? |
|---|---|---|---|---|---|
| 1 | offer_setup | `offer_amount_kind` enum reset rejected. | LOW | F-052 | Fixed. |
| 2 | First persuasion | "full payment of 540 by **Friday, October 17th**": 17 Oct 2026 is a Saturday. | HIGH (judge) | F-054 | **Fixed offline.** Replay: `calendar_text` = "…this week Friday, 16 October; next week Friday, 23 October". The model now gets only these dates. Live retest pending. |
| 3 | "The week after next" | The agent asked for the exact day once ✓. The route to `check_offer` needed date AND amount, so it did not run. | HIGH | F-051 | Fixed (date alone routes; v13 shows it live). |
| 4 | "Monday the 26th" | The agent printed `thought\n_call:check_offer{amount: 540.0,…}` to the customer. | HIGH (judge) | F-053 | **Fixed offline.** Replay of the current `check_offer`: "That day is not a business day. The next possible day is Tuesday, 27 October. Would that work for you?" (code-voiced `offer_say`). |
| 5 | "Yes, the 27th works." | Blocked text `thought call:check_offer{…}`, then the filler **"Bir saniye lütfen."** and "One moment please." | MED | F-053, F-043 | F-053 fixed offline; the filler is platform. |
| 6 | "Yes, that's correct." | **False claim:** "27 October is after the latest possible date; the latest is Monday, November 2nd". 27 Oct is before 2 Nov. | HIGH (honesty) | F-051 | Fixed: the model no longer states limits, and the verdict text comes from code. |
| 7 | Driver turn 7 | 23.4 s wait (the engine took 1.0 s). | LOW | F-023 | Platform. |
| 8 | Hang-up | The hook recorded `no_promise/refused` although the customer agreed. The hook was correct for the state it saw (no promise). | — (result of 3–6) | F-051 | — |

## PUB-07 v13 (dates, ledger pass)

| # | Step | Problem | Severity | F-xxx | Still in code? |
|---|---|---|---|---|---|
| 1 | Identity DOB turn | `route_evaluated` 4.2 s; engine turn 7.3 s (the longest in all runs). | LOW | new (no number) | Platform latency; in voice this would be audible dead air. |
| 2 | Debt statement | Correct, after verification. | — | — | OK |
| 3 | "I can't pay today" | "I can offer a payment of 540 on **Friday, 2026-10-17**": wrong weekday and an ISO date. | HIGH (judge) | F-054 | Fixed offline (see v12 #2). |
| 4 | "The week after next" | `check_offer` ran; the model asked for the exact day once ✓. | — | — | Current code says "Sorry, I did not catch the date. On which day would you like to pay?" The customer did name a period, so "did not catch" is slightly off. **LOW**, text only. |
| 5 | "Monday the 26th" | Message was `_call:check_offer{amount:540.0,date:"2026-10-26"}`. The next business day was **not offered**, so the case check "offers the next business day" fails for the judge. The customer said "the 27th" by himself. | HIGH (judge) | F-053 | **Fixed offline** (replay above gives the 27 October line). |
| 6 | Same turn | `extraction_failed` `negotiation_reply` (low confidence 0.53). No effect, because the route uses `offer_date`. | LOW | — | — |
| 7 | check_offer ×3 | `validation_errors` for `negotiation_reply`, `offer_amount`, `readback_reply`. | MED | F-052 / **F-060** | Enums fixed; `offer_amount` "" still in code. |
| 8 | Read-back | "You have a personal loan for 540 on Tuesday, 27 October. Do you confirm?" Ambiguous ("you have a loan for 540"); a payment verb is missing. | LOW | F-044 follow-up | The model phrases it from `offers_summary`, so it can recur. |
| 9 | Recording/close | `create_promise` once ok, one `close_call=promise`, text-message line ✓. | — | — | OK |
| 10 | Last turn | Driver waited 60.2 s and the response was lost (the engine took 2.2 s). | MED (test reliability) | F-049, F-023 | Platform. |
| 11 | End of call | Hook "Missing required field: url" = intended skip. | LOW | — | By design. |

## PUB-02 v13 (third party, ledger fail)

| # | Step | Problem | Severity | F-xxx | Still in code? |
|---|---|---|---|---|---|
| 1 | Opening → third_party | No disclosure ✓, no repeated introduction (F-048 not seen) ✓. "I can pay it myself…" was refused without account details ✓. | — | — | OK |
| 2 | "tomorrow morning around eleven" | The model called `schedule_callback` with **2025-05-15**. | HIGH | F-055 | **Fixed offline.** Replay of the current `callback_check` (all three phrasings: day + time, all in the day field, all in the time field) gives `window_ok 2026-10-15 11:00`. `third_party` has no tool now. |
| 3 | Same turn | The response was lost (driver `<processed, response lost>`). `turn_completed` has `finalAssistantMessageId: null`. | MED | F-049 | Platform. |
| 4 | "Okay, thanks." after goodbye | `conversation_resumed` **isBranch: true** from the previous turn's message (msg_4). The call state was rolled back to `third_party` (`close_call_ok` gone), and the agent spoke again after its goodbye: "When can Ms Costa be reached?" | HIGH (judge) | F-049, F-031 family | Platform trigger. Our code cannot see the lost state. |
| 5 | Hang-up | The hook saw the rolled-back state and sent a **second `close_call` `not_verified/declined`**. The bank refused it ("already closed"), but the ledger lists 2 `close_call` calls (rule 46: exactly one, the last tool call). If the bank had accepted it, the outcome would have been overwritten. | HIGH | **F-057 (new)** | **Yes.** The hook's skip test reads only `close_call_ok`/`close_attempts` (`workflow.py:849ff`), and both are lost in a rollback. |
| 6 | Goodbye | "We will call back at the time we agreed." True (callback ok). The time was not repeated to the husband. | LOW | — | — |

Checks: no reason/product/amount disclosed ✓, `verify_identity`/`get_account` never called ✓, callback date ✗ (F-055).

## PUB-09 v13 (restructuring, ledger pass)

| # | Step | Problem | Severity | F-xxx | Still in code? |
|---|---|---|---|---|---|
| 1 | Identity, debt statement | Correct. The agent describes no plan ✓. | — | — | OK |
| 2 | "I can't pay this amount… lower instalments" | Extraction `offer_amount_kind = full` for "I can't pay this amount" is a wrong value. No effect here (the special path won). | LOW | new (no number) | LLM extraction; possible again. |
| 3 | Special path | The line "I will connect you with a colleague… Goodbye." is spoken **before** `transfer_to_agent` runs. Here it succeeded. If the transfer fails, the customer has already heard "I will connect you … Goodbye" and then the failure close. | MED (honesty) | **F-059 (new)** | **Yes.** `workflow.py:404-413`: a code step speaks, then the `_call` api step (F-050 form). |
| 4 | Closing | **The same goodbye line is spoken twice** (special step, then `closing_say` with the same `closing_sentence`). The transcript shows it twice. | MED (judge) | **F-056 (new)** | **Yes.** `special_result_<id>_said` is written (`workflow.py:410`) but never read; `closing_say` always speaks. |
| 5 | Same turn | The turn has two spoken messages, and `turn_completed` points at the **first** (msg_8, before the close). | HIGH | F-056 | **Yes** (cause of #6–#8). |
| 6 | "Yes, please transfer me." after goodbye | `conversation_resumed` isBranch: true from msg_8. The state went back to `special_restructuring_request` without `close_call_ok`. | HIGH | F-056 (+ F-049 family) | Yes (trigger in our code). |
| 7 | Same | Routed **`special_restructuring_request → special_human_request`** although the human path's `excluded_nodes` lists `special_restructuring_request` (also in `submission/brief-a.workflow.json`). The agent said "Can I help you with this first?" after the goodbye. Had the customer insisted, the human path could have run a **second `transfer_to_agent(general)`** (ledger fail). | HIGH | **F-058 (new)** [TO-CONFIRM: platform] | Our exclusions are correct. The platform did not honour them in this branched state. |
| 8 | Hang-up | Second `close_call` `no_promise/refused` (refused by the bank), so 2 `close_call` calls in the ledger. | HIGH | F-057 | Yes. |

Checks: `transfer_to_agent(restructuring)` ✓, no plan described ✓, no promise ✓.

## Proposed new findings

| ID | Title | Severity | Cause | Fix idea (not done) |
|---|---|---|---|---|
| F-056 | A special path with a tool speaks its line, then `closing_say` speaks the same line again | HIGH | Two spoken messages in one turn. The turn completes at the first, so the next message branches back before the close. | `closing_say` gets a silent twin (or route) when `special_result_<id>_said` is set; or the special step stays silent and only `closing_say` speaks. Goal: exactly one spoken message per closing turn. Watch F-050: no tts on api steps. |
| F-057 | Hang-up hook sends a second `close_call` after a state rollback | HIGH | The skip test uses only `close_call_ok`/`close_attempts`, which a branch/rollback erases. | Remove the branch triggers (F-056). Ask the organizers whether a post-goodbye message is possible in the judge's simulation [TO-CONFIRM]. A hook-side guard that survives rollback needs a state source outside the variable table (none known yet). |
| F-058 | Global path matched from a global step despite `excluded_nodes` | HIGH [TO-CONFIRM] | Platform behaviour in a branched resume, or from a global code step. | Confirm live with the organizers. Possibly every special path step also gets an always-transition, so it never waits for a message. |
| F-059 | Transfer line ("I will connect you … Goodbye") spoken before the transfer tool runs | MED | F-050 form: the code step speaks, then the api step runs. | Speak a neutral line before the tool ("One moment.") and the transfer/goodbye only after `ok`; or let the failure close say plainly that the transfer did not happen. |
| F-060 | `check_offer` resets the float `offer_amount` with `""`, and the platform rejects it | MED [HYPOTHESIS] | Same platform rule as F-052 (an invalid value is rejected and the old value is kept). A stale customer amount could be reused on the next date-only answer instead of the agent's proposed amount. | Reset to a valid sentinel the code treats as empty, or keep a code-owned "amount turn" marker. Needs one offline test with a stale amount. (Area of claude-dev, offer_check.) |

## Already known, status from the code

| F-xxx | Seen in | Status in `53efa1a` |
|---|---|---|
| F-043 Turkish filler | v10, v12 (not in v13) | Platform. Can recur while `account` is silent. |
| F-044 machine read-back | v10 | Fixed (confirmed live in v13). |
| F-049 5xx/lost response loses state | v10, v13 ×2 | Open (platform). |
| F-051 date-only offer, invented limits | v12 | Fixed (live in v13). |
| F-052 enum resets rejected | v10, v13 | Fixed for enums (`none` now in every enum). Float part: F-060. |
| F-053 tool call printed as text | v12, v13 (also v10 `call:get_account` blocked) | Check result fixed offline (code-voiced). The model can still try a tool call as text elsewhere; the platform blocked it in v10. |
| F-054 wrong weekday / ISO date in persuasion | v12, v13 | Fixed offline (calendar replay correct). Live retest pending. |
| F-055 callback year | v13 | Fixed offline (replay `2026-10-15 11:00`). Live retest pending. |

## Latency (engine vs driver)

| Run | Driver wait per turn (s) | Engine user→agent (s) |
|---|---|---|
| PUB-01 v10 | 12.5, 15.3, **43.0**, 20.1, 9.7, 12.0 | 0.6, 3.5, 2.8, 5.2, 1.1, 2.6 |
| PUB-07 v12 | 5.0, 8.5, 11.1, 10.2, 8.4, 6.1, **23.4**, 7.7, 6.3 | ≤ 3.5 |
| PUB-07 v13 | 9.4, 13.5, 13.4, 22.4, 6.4, 25.1, 6.3, 18.3, **60.2** | ≤ 2.2, except **7.3** (DOB turn) |
| PUB-02 v13 | 6.2, 9.6, 4.6, 11.6, 7.5 | ≤ 4.1 |
| PUB-09 v13 | 14.0, 6.5, 5.7, 20.2, 7.9, 7.9 | ≤ 2.0 |

The engine is fast; the long waits are on the chat API side (F-023). The worst engine turns are the end of identity (route evaluation 3.5–4.2 s plus tools).

## Recommended order

1. F-056 (our code, removes the PUB-09 branch, the duplicate line and that trigger of F-057).
2. Retest PUB-02, PUB-07 and PUB-09 on a new version (F-053/054/055 and F-056).
3. Ask the organizers about F-058 and post-goodbye messages (F-057).
4. F-060 offline test, then F-059 wording.
