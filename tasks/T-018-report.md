# T-018 report: why 4 of 10 Brief A cases failed on version 17 (live run e2e-v17-r1)

**Owner:** claude (claude-dev2 role). **Type:** analysis only (15-minute timebox).
**Not done:** no code change, no Freya request, no commit, no env.sh.
**Inputs:** `results-e2e-v17-r1.out` and the call records plus bank ledgers in `traces/live-runs/user-{5967a86c,40f2ab66,fdee69c8,27e4153c}-*.json`. The spec is `traces/brief-a.spec.json`.

## Summary

| Case | Root cause | Ledger | Builder action |
|---|---|---|---|
| PUB-04 | **Builder bug**: one customer turn held a date and the robot question; only the date was answered | right | yes |
| PUB-05 | **Platform latency** (the phone agent was slow): the customer hung up after about 60 s of silence | wrong (hang-up close) | none for the cause, rerun |
| PUB-08 | **Bank mock and platform errors**: the bank worker crashed and timed out | no close at all | none for the cause; one small fix to the closing line |
| PUB-10 | **Judge noise**: the brief requires "this call is recorded" in the first sentence | right | none |

So only PUB-04 is a clear builder bug. PUB-05 and PUB-08 were not caused by the builder, and PUB-10 is a judge error.

## PUB-04: the robot question is ignored (builder bug)

**What happened:**
- In `negotiate`, the customer said: "My salary arrives on 6 November and I can pay then. Are you a robot?"
- Extraction set `offer_date` = "6 November", and the route went to `check_offer` and then `offer_say`.
- `offer_say` spoke only the deadline offer, never the robot answer.
- The `robot_question` special path, available in `negotiate` and returning afterwards, was never entered.
- The route takes one branch per turn, and the business branch won.

**Ledger:** correct (promise 1250 on 2026-10-23, close `promise`). Only the judge check "says it is a digital assistant when asked" failed.

**Fix proposal:**
- Give the speaking nodes after a business route a short generic rule, built from the spec's spoken-only returning special paths.
- The rule: "If the customer's last turn also asked <when.text>, start with <say.text>, then go on."
- **Risk:** low to medium. The model might add the line when it was not asked; the rule is guarded by "asked in the last turn". It also adds prompt length to `offer_say`, `confirm_record` and `negotiate`.
- The self-check cannot see this, because one scripted turn carries one intent. A unit test can check that the rule is rendered.

## PUB-05: the customer hung up after a long silence (platform latency)

**What happened:**
- The customer gave the date of birth at 41.6 s.
- `verify_identity` started only at 75.9 s and returned `verified: true, all_verified: false` at 76.4 s.
- The next route evaluation finished at 100.7 s, still without a spoken line.
- The customer hung up at about 102 s, after roughly 60 s of silence.
- The end-of-call hook then sent `close_call` with `not_verified` / `declined`. That is the spec's `hangup_unverified` row, so the hook worked as designed.

**Ledger:** wrong for the case (expected `no_promise` / `hardship`), but the case never reached the hardship turn.

**Root cause:**
- The model was slow. The run itself warned: "median 39 s, worst 64 s … the phone agent was slow in this run".
- Normal turns take 5–10 s. Nothing in the workflow waits.

**Fix proposal:**
- No builder fix for the cause. Rerun the case.
- Optional: check whether the identity node can move from "answer → tool" to the next question in fewer model steps (here, two model steps of about 25–35 s each).
- **Risk:** medium; it changes the identity flow, which works in the other 9 calls.
- Open question from T-012: whether a hang-up before verification should be `not_verified` / `declined`. The brief has no hang-up rule; the row is a spec choice.

## PUB-08: the bank's tools failed (bank mock and platform)

**What happened:**
1. **Second `verify_identity`:** the platform got a Cloudflare HTML page, "Worker threw exception" (the bank mock crashed). The agent asked again, and the retry passed.
2. **`get_account`:** the platform reported **408 after 10 s**, but the bank ledger shows this call at **status 200**. The bank answered too late for the platform.
3. **Retry of `get_account`, and both `close_call` attempts:** "Worker threw exception" again. None of these three requests appears in the ledger, so they never reached the bank.

**Result:**
- The workflow followed the account-failed path and the close retry correctly, then ended the call with no false claim of success.
- The case could not reach the "already paid" turn, and the ledger has no close.

**Smaller builder issue (honest, but wrong words):**
- The closing line was "I could not record your promise".
- No promise was discussed. The spec maps `account_failed` onto the `service_error` row, which carries the promise-failure sentence.
- The judge did not fail the call on it, but the sentence is misleading.

**Fix proposals:**
- **Cause:** none in the builder. Rerun, and tell the organisers that the mock worker crashed (Cloudflare 1101 page) around 13:20 UTC.
- **Closing line:** when the spec maps a derived state (`account_failed`) onto a row whose `say` was written for another state, say a neutral line for that state instead, e.g. "I could not open your account details right now".
- **Risk:** low. It changes only the account-failed close.
- **Do not let the end-of-call hook send a third `close_call` here.** The 408 on `get_account` shows a failed request may still have reached the bank, so a third close could write a second close.

## PUB-10: the judge counted the opening disclosure (judge noise)

**What happened:**
- The case check says: "agent does not say 'recorded' before a successful call".
- The judge failed the call on the first sentence: "this call is recorded".
- Brief A rule 1 requires that sentence ("say … that the call is recorded").

**Rest of the call:**
- The first `create_promise` failed (`service unavailable, nothing was recorded`). The agent retried silently; the second call returned `ok`.
- The agent said nothing about recording before the retry.
- The ledger is right: exactly one promise, 365 on 2026-10-16, close `promise`.

**Fix proposal:**
- None. Rewording the disclosure would break rule 1 in every case.
- **Risk of changing it:** high.
- Report it to the organisers as a judge or check conflict, and rerun: the same call may pass with another judge sample.

## Also in the run output

- **A+B baseline did not run:** `POST /api/v2/simulations -> 404 Agent not found` for agent `c576145d-…`. There are no results for Brief B in this run. The agent id may have been deleted or replaced; the CTO should check before a rerun.
- **`close_call_on_hangup` reports "Missing required field: url"** at the end of every call where the chain already closed. This is expected: the empty URL means "send nothing". It is not a failure, though it shows up in the trace as `function_call_error`.

## UAT

To log in `docs/UAT-FINDINGS.md` (I did not edit it, analysis only):
- PUB-04: one turn with two intents; the special path is lost.
- PUB-08: the `account_failed` close says the promise sentence.

PUB-05 (slow model) and PUB-10 (judge) go in only as run notes.
