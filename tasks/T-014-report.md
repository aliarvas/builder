# T-014 report: relative callback times (F-073)

**Owner:** claude (claude-dev2 role) · **Input:** `tasks/T-013-voice-call-review.md` C5, `docs/UAT-FINDINGS.md` F-073.
**Not done:** no Freya request, no model call, no commit, no env.sh. I did not touch prompts or the third-party/opening rendering (claude-dev, T-015).

## The rule, and why

**Rule:** an exact relative time is counted from the call's `now`. "Two hours later", "in two hours", "in an hour", "half an hour later", "an hour and a half from now", "in 45 minutes" and "twenty five minutes later" (digits or number words) all mean now + duration. The result goes through the same window check as a clock time:
- inside the window: booked;
- after the window: the person hears the window and is asked again;
- past midnight: the next day.

**Asked again (unclear):**
- a vague amount: "a couple of hours", "a few minutes", "an hour or two", "2 to 3 hours";
- a range: "within two hours";
- an amount with no "in / after / later / from now": "two hours" could also mean "for two hours";
- a duration together with a named day other than today ("tomorrow, in two hours").

**Why counting, and not asking for a clock time (as "in two hours" did until now):**
- **No guess.** An exact duration from a known `now` gives one time, so this is not the "wrong guess" the earlier review warned about (finding 2b). The F-073 bug was the clock reading of "two"; the duration itself is exact.
- **Asking again costs the case.** With a window, unclear answers are counted. A person who repeats "in two hours" reaches the give-up limit, and the call closes as "no callback" although a bookable time was named.
- **The ledger checks the booked time.** The expected callback is now + duration; asking again would never book it.
- **One rule for every relative form.** "In two hours" changes from "asked again" to "counted", the same as "two hours later". Only inexact forms are asked again.

## What changed in `builder/callback.py` (the generated `callback_check` code)

- **`duration_minutes(text)`:**
  - number words become digits;
  - "an hour", "half an hour", "a quarter of an hour" and "N and a half hours" are normalised;
  - it then reads `(in|after) <amount>` or `<amount> (later|from now|after now)`, including "1 hour and 15 minutes".
  - It returns None (no duration), -1 (not exact) or the minutes.
- **`DURATION`** is now "any hour or minute word". Such words are never read as a clock time, which is the F-073 fix in `clock_candidates`.
- **Check step:** the duration is read from the time field first, then from the day field (the model may put the whole phrase there). With an offset: day = today (+1 past midnight), and the time is now + offset. Everything after this is the existing window logic.
- **`in_window` without a spec window:**
  - **Found with this task:** without a window, a clock time already past today was booked. At 15:30, "at 2" became 02:00 today; the old code's first reading of "two hours later" was 02:00 too.
  - Now a time already past today is "outside" and asked again; with two readings, the later one is taken ("at 4" at 15:30 → 16:00).
- **No brief value in `builder/`.** The phrases are generic English, and the window values come from the spec.

**Reproduction of the review's table (T-013 C5):**

| `now` | "two hours later" before | after |
|---|---|---|
| 11:00 | 14:00 | **13:00** |
| 15:30 | outside the window | **17:30** |
| 15:30, "four hours later" | outside | outside (19:30 > 19:00), asked again |

## Self-check family (`builder/selfcheck.py`, `_relative_callback_scenarios`)

- **Phrases:** `RELATIVE_CALLBACKS`: "two hours later", "in 2 hours", "in an hour", "half an hour later", "an hour and a half from now", "in forty five minutes" (exact), and "in a couple of hours" (not exact).
- **Expected ledger, written apart from the callback code** (`_callback_allowed`, from the spec window and the spec calendar):
  - **exact and allowed:** `callback_scheduled`, with the booked day and time = now + duration;
  - **exact but not allowed:** with `max_outside_asks` = 0, the window's close value and no booking; otherwise the person is asked again, names the first bookable slot, and that slot is booked;
  - **not exact:** asked again, then the slot.
- **Moments:** in build mode the family runs on every moment of `check_nows` (the build's `now`, a Friday, a holiday eve), with the same clock time.

## Tests

- **`tests/test_callback.py`:**
  - `test_f073_relative_times_count_from_now`: 16 forms at 11:00 and 15:30, with the expected times worked out; outside the window → `window_outside`. Also the review's three cases by hand, "today" + duration, and the phrase in the day field.
  - `test_f073_without_a_window_a_duration_past_midnight_is_the_next_day`: 23:30 + 2 h → 01:30 the next day.
  - `test_without_a_window_a_time_already_past_today_is_asked_again`.
  - `test_durations_and_several_clock_numbers_are_unclear` (extended): a duration with "tomorrow", and inexact or unmarked amounts, stay unclear.
- **`tests/test_selfcheck_families.py`, `RelativeCallbackTests`:**
  - the family passes on Brief A (no window) and A+B v2 (window 10:00–19:00, next business day) at **11:00 and 15:30**;
  - expected times by hand: 13:00, 17:30, 16:00, 11:45; the inexact form → next business day 10:00; Friday 18:30 + 2 h → Monday 10:00;
  - build mode (three moments) has no failing relative scenario;
  - **mutation:** removing the duration reading from the generated code brings the old behaviour back (A+B: 14:00 at 11:00, no booking at 15:30; Brief A: 02:00), and the family catches it at both moments.
- **Every fixture** (11 specs) passes the family at 11:00, 15:30, Friday 18:30, 23:30 and in build mode.
- `python3 -m unittest`: **537 OK**. Leak test green; `git diff --check` clean.

**Coordination:**
- The Brief A render pin in `tests/test_notes_outcome.py` changes with this task, because the callback code is part of the render. claude-dev re-pinned it for T-015 together with this change (the comment says so).
- While claude-dev was editing, a leak-test hit and a render error in `workflow.py` came and went. Both pass now.

**`docs/UAT-FINDINGS.md`:** F-073 is now "fixed offline (T-014)", with the past-time-without-a-window finding added. Retest: a chat callback case with a relative time (needs approval).

## Open

- **Prompt proposal for T-015, not done here:** `CALLBACK_TIME_DESCRIPTION` gives only clock examples. Adding a relative example ("in two hours") would make the model copy such words into the time field instead of dropping them. The code already accepts the phrase in either field.
- **Forms still asked again:** "later by two hours", "two hours on", "after lunch" and "in the evening" without a clock time. They are inexact or rare; asking again is the safe default.

## Fix (review T-014)

Review: `reviews/T-014-review.md`. No Freya request, no model call, no commit, no env.sh.

**Finding 1 (MEDIUM), compound durations: fixed in `builder/callback.py` (`duration_minutes`).**
- `SPAN` now takes "N hours M minutes" with or without "and". "In 2 hours 30 minutes" and "two hours thirty minutes later" now give 13:30 at 11:00, not 13:00 or 11:30.
- **Every span must be read:** if the text has a number-unit span that the match leaves out, the result is -1 (asked again). Example: "30 minutes and 2 hours later".
- **A bare number after a unit is -1:** "in one hour fifteen" and "in 2 hours and 30" are asked again. They are no longer booked as 12:00 or 13:00.
- An amount that is not exact, "in 2 hours or 30 minutes", stays unclear.

| at 11:00 | before the fix | now |
|---|---|---|
| "in 2 hours 30 minutes" | 13:00 | **13:30** |
| "two hours thirty minutes later" | 11:30 | **13:30** |
| "in one hour fifteen" | 12:00 | **asked again** |

**Finding 3 (LOW), the family's phrases: done in `builder/selfcheck.py`.**
- `RELATIVE_CALLBACKS` has three new phrases: "in 2 hours 30 minutes", "two hours thirty minutes later" (150 min), and "in one hour fifteen" (not exact).
- **The window's edge is computed from the spec window and `now`**, when the window ends later today:
  - `callback_relative_window_last_minute`: "in N minutes" with now + N = the latest time, which is booked;
  - `callback_relative_window_one_minute_past`: N + 1, which is outside, so the person is asked again and the slot is booked.

**Tests:**
- **`tests/test_callback.py`:**
  - the three compound forms are added to `test_f073_relative_times_count_from_now`;
  - new `test_f073_a_compound_duration_it_cannot_read_whole_is_asked_again`;
  - new `test_f073_a_duration_on_the_window_edge`: 11:00 + 8 h and 15:30 + 3 h 30 min are booked at 19:00; 481 minutes and 3 h 31 min are outside.
- **`tests/test_selfcheck_families.py`:**
  - hand-made expected results for the compound and edge scenarios at 11:00 and 15:30;
  - new mutation `test_reading_only_the_first_span_of_a_compound_duration_is_caught`: putting the T-014 code back fails all three compound scenarios on Brief A and A+B.
- The family passes on all 10 specs in `SPECS` at 11:00, 15:30, Friday 18:30 and 23:30.
- **Render pin:** `tests/test_notes_outcome.py` `BRIEF_A_RENDER_SHA256` was re-pinned (`63bfaf8e…`). With this fix reverted in a scratch copy, the old pin still matches, so only the callback code changed it. The comment says so.
- `python3 -m unittest`: **540 OK**. `git diff --check` clean.

**Finding 2 (LOW), noted and not changed:**
- Without a spec window, a relative time can fall at night: "in two hours" at 23:30 books 01:30 the next day.
- The person asked for that time and the spec gives no hours, so the builder has no rule to refuse it. It is kept as it is.

**Finding 4 (LOW), noted and not changed:**
- Any hour or minute word now stops the clock reading. "at 3 for an hour" is unclear, not 15:00, so the person is asked again.
- This errs on the safe side. It is noted so it is not a surprise in a trace.
