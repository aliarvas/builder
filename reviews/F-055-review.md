# F-055 review — callback date and time resolved in code

**Reviewer:** claude-reviewer · **Scope:** `builder/callback.py` (new), the F-055 parts of `workflow.py` (third_party, `close_rules`), `extract.py` (`callback_window` merge and evidence), the 4 new prompts, `tests/test_callback.py`. claude-dev's F-053/054 changes were not reviewed.
**Method:** offline only. I ran the generated `callback_check` code with synthetic `vars` (now = Wed 2026-10-14 11:00, fixture calendar, window 1 business day, 10:00–19:00, after now, 1 re-ask), read the rendered graph, and probed field detection with other tool shapes. No Freya, no model, no edits. `tests.test_callback` 18 OK.

## Decision: **düzeltme gerekli**

The design is right (check before the tool, model never types the date, no retry loop on a failed booking). But the code still books the **wrong day without telling anyone** in one very likely input shape. That is the same class of bug as F-055, so it must be fixed first.

## What is correct

- **No brief value in code or prompts.** All numbers come from `third_party.callback_window`; the window sentence is built from them (`_window_text`). The words in `CHECK_BODY` (tomorrow, weekdays, noon) are generic. `callback_window()` rejects bad shapes and an `outside_close_value` that is not in `close_values`.
- **The model has no tool in `third_party`** (`tools: []`, no-tool rule shown). `callback_book` is a silent passthrough api step with `schedule_callback` as pre-action; `date`/`time` get `{{callback_date}}`/`{{callback_time}}` defaults, no `required` left, `maxRetries: 0`. `customer_id` default stays. `response_mapping` `data.ok → callback_ok` is on the node, as the format needs. No `null`, one transition per target.
- **Loop safety:** `callback_check` clears both text variables before it decides, so a re-entry cannot re-check old words. Outside offers are counted; above `max_outside_asks` it sets the intent variable to the spec's close value and goes to `closing` (state `third_party:<value>`; no earlier rule can win, `callback_ok` is unset). Verified: 1st outside → ask, 2nd → `window_give_up` with `no_callback`. Business-day window skips weekend and the 26 Oct holiday (tomorrow on Fri 16 Oct = Saturday → outside, correct).
- **`callback_failed` rule is right:** `callback_ok` false, `schedule_callback_failure_count > 0`, and `callback_book_failure_count > 0`. The first two were already proven names, so the unverified third counter cannot hurt (it is only extra). A failed or 5xx booking goes to `closing` as `callback_failed`; the closing line is the spec's "not scheduled" text; no success claim.
- **Time handling that works:** 3pm, 14:30, 10.15 am, half past three, noon, "2" (→14:00 as the one in the window), "around eleven in the morning", 19:00 ok / 19:01 outside / today earlier than now outside, `now` with seconds and offset (`…T11:00:00+03:00`), `now` without a time (after-now check skipped, no crash), 21:00 now + "today 8pm" outside.
- **Evidence check** (`_clock_in_brief`) uses word-boundary matching, so `7:00` is not found inside `17:00`. `7 pm`/`7pm`/`7 p.m.` on the hour is accepted.
- **F-050 risk:** the `tts` is on a **code** step (`callback_say`), the same shape as `closing_say`, `offer_say`; `callback_book` is silent. No tts on an api step. That is acceptable; live retest still needed (the developer says so).

## Findings

### 1. HIGH — whole phrase in the time field books **today** (wrong day, silent)

`callback_day('')` returns `today()`, so the fallback `callback_day(time_text)` is never reached when the day field is empty (`callback.py:119-122`, `230-231`: `day is None` is false).

| day_text | time_text | result |
|---|---|---|
| (empty) | `tomorrow at 3pm` | **window_ok, 2026-10-14 15:00** (should be 2026-10-15) |
| (empty) | `tomorrow around eleven in the morning` | window_outside (today 11:00 is not after now) → the customer is told "we cannot call back then" for a valid time |

The extraction description only says "words for the time of day", and the entry transition fires on `callback_time_text` alone, so a model that puts the whole sentence into the time field is expected and normal. This is exactly F-055 again (PUB-02 "tomorrow" booked for the wrong day), and it goes to the ledger without an error.
**Fix:** in `callback_day`, treat an empty day field as "unknown", not today. Order: day_text → day words found in time_text → only then today (when neither text names a day). In `check`: `day = callback_day(day_text) if day_text else None; if day is None: day = callback_day_from(time_text); if day is None and not day_text: day = today()`. Add a test for both rows above.

### 2. HIGH — wrong time from number words / digits is booked silently

Same silent-misbooking class (the engine accepts any valid HH:MM):

| text | booked | should be |
|---|---|---|
| `ten fifteen` | 10:00 | 10:15 |
| `four thirty` | 16:00 | 16:30 |
| `eleven thirty` | 11:00 | 11:30 |
| `in two hours` | tomorrow 14:00 | not a clock time → unclear |
| `between 2 and 4` | 14:00 | ambiguous → ask |

Also `clock_candidates(time_text) or clock_candidates(day_text)` (`callback.py:232`): when the time text is not a time, digits of the **day** become the hour (e.g. day `the 15th` / time `whenever` was unclear in my probe only because `15th` has no word boundary; `15 October` + `3 pm` worked by luck, `20 October` + `3 pm` read hour 20 → "outside" for a valid time).
**Fix (generic):** (a) after a number word or digit hour, accept a following minute word (`fifteen`, `thirty`, `forty five`, `oh five`) or two digits; (b) if the text has a duration word (`in … hours/minutes`, `hour`, `minutes from now`) return no candidate; (c) when more than one clock number is present (`between 2 and 4`, `2 or 3`) return no candidate so the step asks; (d) do not read the day text for the hour when `time_text` is set — use `time_text` only. A wrong guess is worse than "unclear" (unclear costs one more question, a wrong time loses the case).

### 3. MEDIUM — nothing tells the model to collect the day and the time, and a day-only answer has no way out

The third-party prompt is now: "Handle the third-party response… Rules: Do not reveal why the bank called; ask only when the customer can be reached." The tool used to force the day/time questions; now the model has no tool and no instruction to ask for the time. If the person says only "tomorrow", nothing routes (entry needs a time), and the model may answer "noted" and wait until `max_node_turns` → `close_turn_limit`. **Fix:** a generic line in the step's task: "To arrange a callback, get the day and the time of day from the person, in their own words; do not say it is booked." (Prompt text only; no brief value.)

### 4. MEDIUM — the model speaks right after the fixed line (double speech, false-hope risk)

`callback_say` (tts) → `third_party` which has the default `on_enter` (llm, speaks on every entry). After "we cannot call back then. We can call back today or the next business day, between 10:00 and 19:00. What time would suit?" the model also talks, likely repeating the question or saying "noted, we will call you then". With no tool, that last sentence is a false statement the judge can read as a claim. It is the same shape as the F-053/054 dead-air review, in reverse: here it speaks twice.
**Fix:** route `callback_say` to a copy of the step, `third_party_ask`, with `on_enter: silent`, the same prompt, extraction, transitions and `callback_check` entry (build it from the same function so they cannot drift). Do **not** set `on_enter_first_entry_only` on `third_party` itself, because global `__previous__` returns would then be silent (F-053 finding 1).

### 5. MEDIUM — field detection fails for common names, so the F-055 fix silently turns off

`_body_fields` uses `\bdate\b`; an underscore is a word character, so `callback_date`, `scheduled_date`, `scheduled_time`, `callbackTime` with no description are **not** found (probe: `None`), and `time` listed before `date` whose description says "same date" is also `None`. The code then keeps the model-filled tool and only adds a warning, which the builder does not repair. A hidden brief with a changed tool API (the repo already has a "changed-a" fixture for that) would get the old, wrong behavior.
**Fix:** split the name on `_`, `-` and camelCase before matching; match `datetime`/`date-time` as a date+time single field (or a clear error), and decide date vs time by name first, description second.

### 6. LOW — evidence check can drop a valid window

`_clock_in_brief` accepts `H:MM`, `H.MM`, and on-the-hour `7 pm`. A brief that says "between 10 and 19", "10-19h", "9 to 5" or "from ten to seven" gives a model value `10:00` that the check rejects; the repair round probably removes the window, and then the window is **not enforced** (only "today or later"), so outside-window callbacks get booked. Accept a bare 24-hour number (`10`, `19`) next to `h`, `hrs`, `to`, `-`, and spelled-out hours; keep the strict check only for minutes.

### 7. LOW — unbounded loops and read-back

- With a window but no `outside_close_value` (it is optional), outside offers repeat forever, and "unclear" is never counted at all. Count unclear tries too, and when no close value exists use the first value of `close_values` that the spec marks as "no callback"… or fail validation: a window without an exit value should be a `SpecError`.
- The booked day and time are never said back to the person; the closing line is the spec's fixed text. Fine for honesty, but a one-line read-back from `callback_date`/`callback_time` (code-made) would help the judge see the right value.
- The existing extracted spec has no `callback_window` (developer noted this); the next real extraction must be checked for it.

## Tests

`tests/test_callback.py` covers the happy paths, the F-055 sample (day and time in separate fields) and the render. It does **not** cover findings 1, 2, 3, 4, 5. Add: whole phrase in `callback_time_text` only; `ten fifteen`/`four thirty`; a duration phrase; two numbers; a tool with `callback_date`/`callback_time`; a render check that `third_party_ask` is silent.

## Short summary for the CTO

Merge **not yet**. Fix 1 and 2 (wrong day or time booked without any error), then 3–5 (prompt, double speech, field names). 6–7 are low. The rest — no brief leak, no model-typed date, loop-free outside path with a close value, `callback_failed` rule, F-050 shape — is correct.


---

## Re-review (fix for findings 1–7a)

**Method:** offline. I re-ran my probe set against the new `callback_check` code (33 day/time pairs, now = Wed 2026-10-14 11:00), read the rendered graph, tested field detection with 8 tool shapes and the evidence check with 10 brief phrasings. `tests.test_callback` 30 OK. The 2 failures in the full run are in `test_multi_step` and `test_spoken_output` and expect the old product-facts wording; they come from claude-dev's uncommitted `offer_check.py` (T-009c), not from F-055. I did not review claude-dev's part. No Freya, no model, no edits.

### Decision: **merge edilebilir** (one MEDIUM note for the live test, two LOW)

### Findings 1 and 2 (wrong day, wrong time) — fixed

| day field | time field | before | now |
|---|---|---|---|
| (empty) | tomorrow at 3pm | today 15:00 | **2026-10-15 15:00** |
| (empty) | tomorrow around eleven in the morning | outside | **2026-10-15 11:00** |
| tomorrow | ten fifteen / four thirty / eleven thirty | 10:00 / 16:00 / 11:00 | **10:15 / 16:30 / 11:30** |
| tomorrow | 4 30, 10 15, quarter to four | — | 16:30, 10:15, 15:45 |
| tomorrow | in two hours, half an hour, between 2 and 4, 2 or 3 | 14:00 etc. | **unclear (asks again)** |
| 20 October | 3 pm | outside by hour 20 | outside, because 20 Oct is outside the window (correct reason) |
| the 15th | whenever | unclear | unclear |
| the 15th | at 11 | — | 2026-10-15 11:00 |
| whenever | 3pm | — | unclear (safe) |
| (empty) | 3pm | today | today 15:00 (no day named at all: acceptable) |

Also correct: noon, 12 pm = 12:00, 12 am outside, 3:30pm, "15:00 or so", "7 in the evening" = 19:00. No wrong value in my set; every doubtful phrase becomes "unclear" and asks again.

### Finding 3 (nothing asks for day and time) — fixed

The third-party task now has a generic collect rule: get the day and the time in the person's own words, ask for the missing one, "never say a callback is booked", the program books it. No brief value.

### Finding 4 (double speech) — the different choice is **right**

I proposed a silent copy. The developer made `third_party_ask`, a copy of `third_party` (I compared `task_message`, `extraction_schema`, `tools`, `transitions`: identical) whose entry is the fixed line `{{callback_message}}`, the same pattern as `offer_say`, and removed `callback_say`. Why this is better than my proposal:
- Global paths that fire in this step (robot, scam, unanswerable questions; the three that exclude both steps are consistent) come back by `__previous__`. A silent copy would leave dead air after a side question, which is the F-053 finding I raised myself. The twin repeats the pending question ("…What time would suit?") instead.
- `callback_message` is always set before the twin is entered (the only route is `callback_check → third_party_ask`), so it is never empty or stale.
- It also removes the `tts` on a code step.
- `third_party` has no `on_enter`/first-entry flag, so returns to it still speak by the model. `STEP_ALIASES["third_party"]` covers the twin; the excluded-nodes lists treat both steps the same.
I withdraw my silent-copy suggestion; this is the consistent design.

### Finding 5 (field names) — fixed
`callback_date/callback_time`, `callbackDate/callbackTime`, `scheduled_time` listed before `scheduled_date`, `day`+`hour` with descriptions, and a single `when` (format date-time) or `callback_datetime` are all detected. For one date-time field the default is `{{callback_date}}T{{callback_time}}:00`. A tool with no recognizable fields still falls back to the model tool with a warning (unchanged, acceptable).

### Finding 6 and 7a — fixed
- Evidence now accepts bare 24-hour numbers in a range or with an hour unit: "between 10 and 19", "10-19h", "9 to 17", "10 am to 7 pm" pass; "see rule 10" and "maximum of 19 customers" do not. (A phrase such as "10 to 19 days late" would also pass; the check is soft and the dry render still validates the value, so this is harmless.)
- A window without `outside_close_value` is a `SpecError`; unclear tries are counted: the first unclear asks, the second gives up with the close value (`window_give_up`, intent `no_callback`); the second outside offer gives up as before. The loop is bounded.
- 7b (read back the booked day and time) is not done; it stays an optional improvement.

### Remaining notes

1. **MEDIUM, live check:** the day and time can come in two turns ("tomorrow" first, then "3pm"). The code relies on the platform keeping `callback_day_text` from the first turn when the second turn's extraction has nothing for it. If extraction overwrites it with an empty value, the second turn books **today** at the time. Check this in the PUB-02 retest with a customer who gives the day and the time in separate messages (the `pieces` style). If it fails, the fix is to keep the day in a code-owned variable (copy it when non-empty) rather than rely on extraction memory.
2. **LOW:** the existing `traces/brief-a.spec.json` still has no `callback_window`; the next real extraction must be checked for the window and for an exit value, otherwise the render now fails with the `SpecError` (a good, loud failure).
3. **LOW:** other live checks the developer listed stay open: the `tts` entry on the conversation twin, routing leaves `third_party` in the same turn the time is named, `callback_book_failure_count` naming (harmless, the other two failure signals already exist).

UAT: F-055 "fixed offline, PUB-02 retest pending".


---

## Re-review 2 (Fix 2: day and time in two turns)

**Method:** offline. I ran `callback_check` turn by turn on one variable table (both text fields set per turn, as the worst case of an extraction that forgets), 12 sequences, now = Wed 2026-10-14 11:00, window 1 business day, 10:00–19:00, `max_outside_asks` 1. `tests.test_callback` 37 OK. The one full-suite failure (`ESTIMATED_PRODUCTS = 3` int literal) is claude-dev's T-009c, not reviewed. No Freya, no model, no edits.

### Decision: **merge edilebilir** (one MEDIUM note, two LOW)

### What now works

| Sequence | Result |
|---|---|
| "tomorrow" → "3pm" | day-only: `window_need_time`, day kept (2026-10-15), line "At what time of day can we call back?"; then **2026-10-15 15:00**, kept day cleared after booking |
| "tomorrow 8pm" → "3pm" | outside (time), day kept → 2026-10-15 15:00 |
| "tomorrow" → "sometime" → "2pm" | unclear keeps the day → 2026-10-15 14:00 |
| "tomorrow" → "8pm" → "9pm" | second outside offer gives up with `no_callback` |
| "3pm" alone | today 15:00 (no day named in any turn → today) |
| "today" → "10am" → "4pm" | 10am outside (before now), 16:00 today booked |
| "whenever" / both empty | unclear, nothing booked |

- **The day no longer depends on platform memory.** It is in the code-owned `callback_day_kept`; the finding 1 risk from my previous review (second turn books today) is closed.
- **Entry condition** is now `or( and(time set, not empty), and(day set, not empty) )`, no top-level `and`; `third_party` and `third_party_ask` have the same condition (compared). Both route only to `closing` and `callback_check`; the check's fall-through goes to `third_party_ask`.
- Loop safety holds: the day-only, unclear and outside counters are separate and all bounded; text variables are still cleared on every check.

### Notes

1. **MEDIUM — a cooperative customer is closed as `no_callback` after one repeated day.** The day-only counter uses the limit `max(1, max_outside_asks)`, so with `max_outside_asks = 1` the **second** day-only turn gives up. Probe: "tomorrow" → (asked for the time) → "Thursday" or "tomorrow morning" (a day plus a vague part of the day, which reads as day-only) → `window_give_up`, intent `no_callback`. A customer who changed the day, or repeated it while answering the time question, loses the callback and the case. Fix: do not count a day-only turn that **changes** the kept day (progress), and give the day-only counter a limit of at least 2 re-asks (for example `max(2, max_outside_asks)`); keep the unclear and outside limits as they are. Add a test: "tomorrow" → "Thursday" → "11am" books Thursday if Thursday is in the window.
2. **LOW — a day outside the window is accepted as a bare day and only rejected once the time comes.** "next Thursday" alone → asks for the time → "3pm" → outside. The customer gives a time for a day that was never possible. Check the window day at the day-only step and say the outside line right away (and drop the kept day, as the code already does in the with-time case).
3. **LOW — after an outside day, a bare time means today.** "next Thursday 3pm" (outside, day dropped) then "3pm" books **today** 15:00. The spoken line lists "today or the next business day", so this is a reasonable reading, but if the line were to name the days, the customer would not be surprised; accept as is, or keep the day asked about in the line ("…today or the next business day. Which day and time?").

Live check stays: `pieces` style on PUB-02 (the day and the time in separate messages). Expect `schedule_callback` with the kept day. UAT: F-055 "fixed offline, PUB-02 retest pending".


---

## Re-review 3 (Fix 3)

**Method:** offline; 10 more turn-by-turn sequences on one variable table with both text fields set each turn (now Wed 2026-10-14 11:00, window 1 business day 10:00–19:00, `max_outside_asks` 1). `tests.test_callback` 39 OK (the developer reports 319 in the full run). No Freya, no model, no edits.

### Decision: **merge edilebilir**, no open finding

- **A cooperative repeat no longer closes the call.** "tomorrow" → "tomorrow morning" → "tomorrow" → "3pm" books 2026-10-15 15:00. Only the fourth same-day answer without a time gives up (`no_callback`, kept day cleared); the limit is `max(2, max_outside_asks)` re-asks. A corrected day is not counted: from Tuesday, "tomorrow" then "Thursday" changes the kept day and "11am" books Thursday (my own probe used "Thursday" on a Wednesday, which is the same day as "tomorrow", so it was counted as a repeat, as designed).
- **An outside day is rejected at once.** "next Thursday" alone and "Saturday" alone give `window_outside` with the window line, the kept day is dropped, the try is counted. A following bare "3pm" books today 15:00 (the accepted reading from my LOW note 3). "next Thursday" then "tomorrow" then "3pm" books 2026-10-15 15:00. A second outside day ("next Friday") gives up with `no_callback`, as the spec's one re-ask means.
- **Unchanged and still right:** "tomorrow" → "8pm" → "3pm" keeps the day and books tomorrow 15:00; "today" → "4pm" books today 16:00; the entry condition is the OR of two AND groups on both steps.

Remaining live check is the same as before (PUB-02 `pieces` style: `schedule_callback` called with the kept day). UAT: F-055 "fixed offline, PUB-02 retest pending".
