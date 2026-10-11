# T-037: pieces-style identity loop, a refused amount in pieces, and the second-goodbye decision

**Owner:** claude-dev2 · **Approver:** CTO

## 1. Identity loops when answers come in pieces

These runs are Brief A v20 with style `pieces`. The customer gives long numbers and dates in two parts.

| Case | Call | What happened |
|---|---|---|
| PUB-03 | `9da14484-78fb-4563-87c3-5a1c332ff460` | After the third wrong answer the security check did not end. Six wrong or partial answers were taken and the agent asked a seventh time. Expected close: `not_verified/failed`; the run got `declined`. |
| PUB-05 | `734a09de-e77e-4d08-ab5e-b9e1022b1320` | The agent asked for the date of birth for 30 turns, until the turn limit. There was no sympathy line and no support offer, and the call closed as `no_promise/refused`. |

Records: `traces/live-runs/user-<call>.json`.

**Find out** from the events, for each turn:
- whether `verify_identity` was called and with what;
- what `wrong_answers_left` came back;
- why the step neither moves on nor closes.

**Make it generic:**
- A half answer is completed across turns: the model waits for the rest and does not call the tool with a part.
- The step closes on the bank's attempts counter, or on a bounded number of identity turns, whichever comes first.
- Add self-check play for a half answer followed by the rest, and a guard on the turn bound.

## 2. PUB-06 pieces: no promise, transferred to restructuring

- **Call:** `aab20006-b662-4b2f-95de-f5ec2009108e`
- **Expected:** promise p1 637.5 on 2026-10-16.
- **What happened:** the agent asked "what amount would you like to pay", which the brief forbids, and the call ended as a restructuring transfer.

Find the root cause: likely an amount said in pieces was read as a partial number, then the restructuring route took the turn. Make a generic fix.

## 3. Decision on T-031's second goodbye (CTO)

Do NOT record a promise without an explicit yes to the read-back. A customer who leaves is not a yes, and the judge checks for confirmation before recording.

- On the goodbye after the read-back, close with the closing chain and record nothing.
- The product with the unconfirmed offer must not get a `refused` note. Use the spec's neutral no-promise reason if the spec has one; otherwise use the same reason the end-of-call hook would give. Never use "refused".
- Change `builder/goodbye.py`, its tests and its self-check scenario, and update F-096 in UAT.

## Constraints

- Generic, no brief value.
- No Freya, no commit, no env.sh.
- claude-dev is doing T-035 (a guard on the note loop, and code cycles in `selfcheck.py` / `workflow.py`) at the same time. Coordinate with them.
- Report: `tasks/T-037-report.md`.
