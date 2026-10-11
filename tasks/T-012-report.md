# T-012 report: more self-check scenario families

**Owner:** claude (claude-dev2 role) · **Input:** `tasks/T-012-selfcheck-scenarios.md`, `tasks/T-010-report.md`.
**Not done:** no Freya request, no model call, no commit, no env.sh.

## Result

- Seven new scenario families, generated from the spec only. Each family has a mutation test that catches it.
- A row mapped only by one of the newly played states now has to be reached by a played call; being mapped is no longer enough.
- The test walkers `walk` and `spoken_per_turn` now run on `builder/selfcheck.py`.
- `submission_check` checks the format of the `self_check_summary` line.
- **Every fixture passes** except the known gaps, on the test `now` and on four other moments: a Friday evening, a holiday eve, 31 December, and build mode.
- **Speed:** the four A+B specs in build mode (three moments each) take **0.46 s in total**. They took 7.4 s before the compile cache below.
- `python3 -m unittest`: **518 OK** in about 21 s.
- Leak test green. `git diff --check` clean.

## 1. New scenario families (`builder/selfcheck.py`, `_call_end_scenarios`)

| Family | Scenarios | Expected ledger (from the spec) |
|---|---|---|
| Hang-up | `hangup_opening`, `hangup_identity`, `hangup_negotiate`, `hangup_after_promise` (the customer hangs up while the closing sentence is said, before `close_call`) | Before verification: the `hangup_unverified` row, else `hangup`, else default. After verification: `hangup`, else default. After a promise: the promise row and the promise. Exactly one close call, written by the end-of-call close. |
| Turn limit | `turn_limit_opening`, `turn_limit_negotiate` | The `turn_limit` row, else default. Notes: none before the account is read; after it, the note rule. |
| Account read fails | `account_failed` (the account tool fails) | The `account_failed` row. No products are known, so no notes. |
| Callback answers | `callback_unclear_then_booked`, `callback_need_time_then_booked` (a day first, then only the time), `callback_book_failed`. With a window: `callback_unclear_give_up`, `callback_need_time_give_up` | `callback_scheduled` with the booked **day and time**; `callback_failed`; giving up uses `third_party:<outside_close_value>`. |
| Revise at the read-back | `revise_at_readback`: offer, "change" at the read-back, a new offer (another allowed day, or the floor amount), confirm | Only the new offer is recorded. |
| Two special paths in one call | `special_<a>_then_<b>`: path a returns (a spoken-only path, or an ask-first path the customer declines), then closing path b at the same step | Path b's pair, plus its notes. |
| Special path at another step | `special_<id>_at_<step>`: a step of `available_in` other than the one T-010 plays. Closing paths: their pair. Returning paths: the call is then finished there (refusal, confirmation, verification then refusal, or a third-party close) | The pair or state of how the call ends; no notes before the account is read. |

**Other new parts:**
- **Simulator:**
  - `hang_up(at)`;
  - `turn_limit()` follows `max_turn_transition`;
  - `leave_special()` takes the `__previous__` transition;
  - `end_of_call(tools)`: the platform's `alwaysRunsAt: end_of_call` tools run after **every** call. Their pre-hook decides, and an empty URL sends nothing.
  - `advance(stop_at=…)`.
- **`play`:**
  - the end-of-call close counts as a close call;
  - so every existing scenario now also checks that the end-of-call close does not send a second close;
  - scripted answers can name a tool by its step: `@account`, `@callback`.
- **Ledger:** a new `Scenario.callback` field.
  - `(day, time)` means the bank must have booked exactly that callback;
  - `()` means no booking;
  - `callback_booked` (T-010) now checks the booked callback as well.
- **Reach rule** (`unreached_rows`, `PLAYED_CALL_END_STATES` = hangup, hangup_unverified, turn_limit, account_failed, callback_failed):
  - a row mapped only by these states counts as reached only when a played scenario ends on it;
  - if no scenario could play the state, the result is a BUILDER note `(state not played: …)`, not a repair. That is a gap in the scenarios, not in the spec;
  - rows mapped by other states keep the T-010 rule.

**Generated per spec:** 12–22 new scenarios. Brief A has 15 (34 in total); A+B v2 has 20 (53 in total).

## 2. Walkers moved to `builder/selfcheck.py`

- **`follow(workflow, key, variables, stop=("closing",))`:**
  - It is the old `tests/test_multi_step.walk`, now on the self-check's `holds` and in the platform sandbox (no pre-loaded `json`, only allowed imports).
  - It raises on a code error, a disallowed import or a loop.
  - `walk` in the test is now a one-line wrapper.
- **`spoken_per_turn(workflow, start, within)` and `SILENT_TOOL_RULE`:**
  - They come from `tests/test_closing_speech.py`.
  - The test keeps a wrapper with its `CHAIN`, and checks that the silent rule is still in `SPECIAL_CLOSE_TOOL_TASK_TEMPLATE`.
- **The existing tests keep their behaviour.** All of `test_multi_step`, `test_closing_speech`, `test_product_notes`, `test_record_loop` and `test_outcome_reach` pass.

## 3. `tools/submission_check.py`

- The `self_check_summary` line is optional. When present, it must start with `scenarios=N pass=N fail=N spec=N builder=N`, in this order, with pass + fail = scenarios.
- Otherwise the new check `trace_self_check_summary` fails.
- **Test** (`test_self_check_summary_format_is_checked_when_present`):
  - a trace without the line is not checked;
  - the good line, with `seconds`, `now` and `extra_nows`, passes;
  - a missing key, a wrong order, wrong counts, a non-number and an empty line each fail.

## Two fixes found along the way

1. **Speed (`_compiled`):**
   - Almost all of the self-check time was spent compiling the same generated code again on every `exec`.
   - A compile cache (`functools.lru_cache`) cut the four A+B specs in build mode from 7.4 s to 0.46 s.
   - The whole suite dropped from about 48 s to about 21 s.
2. **Sandbox import guard, a false alarm (T-010 code):**
   - The import hook also saw imports that an allowed module makes itself from C. For example, `datetime.strptime` loads `_strptime`, and `datetime.now()` loads `time`.
   - This only happens without `now` (as in `follow`), or with the first `strptime` in a fresh process. The self-check always sets `now`, and no trace under `traces/` has such a line, so no live effect was seen. That is why there is no UAT entry.
   - **Fix:** CPython passes a list as the `fromlist` of these imports, and an import statement passes None or a tuple. Only the step's own imports count now.
   - **Test:** `strptime` in a fresh state is not reported; `import time` and `from os import path` are.

## Tests (`tests/test_selfcheck_families.py`, 17 tests)

- Every family is generated (Brief A and A+B v2). The give-up callback scenarios appear only with a window.
- Expected ledgers come from the spec rows: the hang-up rows, `account_failed`, `callback_failed`, the kept callback day, and only the new offer after a revise.
- Every fixture plays the families without failure on three more moments: 2026-10-16 18:45, 2026-11-25 09:00, 2026-12-31 11:00.
- Reach: a row mapped only by `account_failed` (moved to a new row) is reached by the played call. Without that call it is reported as "state not played".
- A+B in build mode stays under 10 s per spec (three moments each).

**Mutations, one or more per family; each is caught:**

| Family | Mutation | Caught as |
|---|---|---|
| Hang-up | end-of-call tool removed | "0 close calls" in all four hang-up scenarios |
| Hang-up | end-of-call hook always sends | "2 close calls" in `promise` and `turn_limit_negotiate` |
| Turn limit | `max_turn_transition` removed from negotiate | "no turn-limit transition" |
| Account | the account step's route to closing removed | "does not reach end_call" |
| Callback (need time) | callback code does not keep the named day | "callbacks booked … the spec gives one at 2026-10-15 12:00" |
| Callback (unclear, A+B window) | gives up at the first unclear answer | "closes as not_reached/no_callback" |
| Revise | read-back "change" routed to recording | wrong promise |
| Two special paths | the declined path has no way back | "no way back" |
| Path at another step | the path is excluded at that step | "cannot start at" |

**Walkers:** `follow` routes and raises on `import os`; `spoken_per_turn` counts a tool turn as spoken once the silent rule is removed from the task.

**Changed T-010 test:** `test_a_missing_close_call_is_caught`. With `close_record` removed, the four hang-up scenarios still pass, because they are closed by the end-of-call tool and not by the closing chain. That is correct, so the test now excludes them.

## Coordination with claude-dev (T-011)

- I re-read `selfcheck.py` before each edit. My additions are in their own functions: `_call_end_scenarios` and the family functions, `_callback_slot`, `_play_call_end`, `_callback_failures`, `_role_tool`, `follow`, `spoken_per_turn`, and the Simulator methods.
- **Shared places I touched, each with a small edit:**
  - `scenarios()`: one line;
  - `play()`: the action dispatch, end-of-call, the close-tool set, the callback check;
  - `Scenario`: one field;
  - `unreached_rows()` and `run_selfcheck()`: the reach rule;
  - `_third_party_scenarios`: uses `_callback_slot`;
  - `_sandbox`: the import fix;
  - `call_tool`: uses `_tool_body`.
- **Not touched:** `note_reasons` / `notes_for` (the expected notes) and `KNOWN` in `tests/test_selfcheck.py`. T-011 shrinks `KNOWN`: Brief B's risk-5 rows are reached during their work.
- The new families build their notes with `notes_for`, so they follow T-011's note rule.

## Limits and open questions

- **Hang-up and notes:** after a hang-up, the closing chain and the note loop do not run, so products without a promise get no note. The spec's note rule asks for one for every such product. The scenarios do not check notes on a hang-up (except after a promise, where the note loop already ran). Whether the bank expects notes after a hang-up is not known. A live or practice case would show it; this is a CTO decision.
- **Returning paths with a tool** (they write a note for a product) are played at another step only when the call can then go on to a refusal (negotiate, offer_say). After the read-back, a promise plus a note for the same product would be contradictory.
- **Two special paths:** for each step, the first returning path or ask-first path is paired with the first closing path. Two returning paths in a row are not played.
- **Hang-up and turn-limit scenarios use one synthetic product.** Several products are already covered by the T-010 multi-product scenarios.
- **Still not seen by layer 1:** a spec that is consistent but wrong against the brief, and a value the brief names but the spec left out (see T-010).

No Freya, no model call, no commit, no env.sh.
