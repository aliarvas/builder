# T-014 review (claude-dev2, F-073 relative callback times)

**Reviewer:** claude-reviewer · **Scope:** `builder/callback.py` (`duration_minutes`, `DURATION`, `RELATIVE`, `VAGUE`, the `callback_check` step, `in_window` without a window), the self-check family `_relative_callback_scenarios`, `tests/test_callback.py`, `tests/test_selfcheck_families.py`, `tasks/T-014-report.md`.
**Method:** offline. Ran the generated `callback_check` code (via the test helper `check`) on about 25 phrases at 11:00, 18:30 and 23:30, with and without a window; `python3 -m unittest`: **537 OK** (24 s). Scratchpad only; no Freya, no model, no env, no edits.

## Decision: **düzeltme gerekli** (one MEDIUM: three common spoken forms book the wrong time silently; the rest is right)

## What is right

- **"Count from now" beats asking again.** An exact relative time ("in two hours", "two hours later", "after two hours", "2 hours from now", "in half an hour", "in 24 hours", "in 20 minutes", "in a minute") gives one exact time from the call's `now`, so there is no guess; asking again would burn the unclear counter (give-up after `max_outside_asks`) for a bookable answer. I agree with the rule and with the line between exact and inexact.
- **Inexact stays unclear and is asked again:** "a couple of hours", "an hour or two", "in two hours or so", "in about two hours", "in the next two hours", "for two hours", "3 pm, I have two hours", and a duration with another named day ("tomorrow, in two hours") all give `window_unclear` (no booking). `now` missing gives unclear, not a crash.
- **Window check:** the counted time goes through the same window logic. With the A+B-style window (10:00–19:00, today or the next business day): 11:00 + 2 h → 13:00 booked; 18:30 + 2 h → 20:30 `window_outside` (asked again with the window text); 23:30 + anything → outside. Past midnight the date moves to the next day first (23:30 + 2 h → 01:30 on the 15th), then the window rejects it. Correct.
- **Without a window** (Brief A shape) the T-014 finding is real and the fix is good: a clock time already past today used to be booked in the past ("at 2" at 15:30 → 02:00 today); now "at 2"/"at 9 am"/"noon" after they have passed give `window_outside` with a generic line ("We can call back on a day and at a time that suits. What time would suit?") and "at 4" at 15:30 gives 16:00 (the later reading). "tomorrow at 9 am" still books. No window means no give-up counter, so a person who keeps naming past times is asked until the turn limit; acceptable and bounded by `max_turn_transition`.
- No brief value in `builder/` (generic English phrases; window values come from the spec); leak test green.

## Findings

### 1. MEDIUM — compound durations book the wrong time

`duration_minutes` handles "N hours and M minutes" only with the word "and", and its second pattern takes the **last** span before "later". Results at 11:00 (same on both specs):

| Customer says | Booked | Should be |
|---|---|---|
| "in 2 hours 30 minutes" | 13:00 (`window_ok`) | 13:30 |
| "two hours thirty minutes later" | **11:30** (`window_ok`) | 13:30 |
| "in one hour fifteen" | 12:00 (`window_ok`) | 12:15 |

These are ordinary ways to say a time, they are accepted silently as exact (`window_ok`), and the bank would receive a callback up to two hours off. The honesty rule ("never claim something was recorded wrongly") makes a wrong exact booking worse than asking again.
**Fix:** after normalising, add **all** `(number unit)` spans that belong together (hours then minutes, with or without "and"), or, simpler and safe: if the text holds more than one number-unit span and the pattern does not account for all of them, return -1 (ask again). A bare trailing number after a unit ("one hour fifteen") also becomes -1. Add these three phrases to `RELATIVE_CALLBACKS` in the self-check family and to `test_f073_relative_times_count_from_now`.

### 2. LOW — callback at night when the spec has no window

Without a window, "in two hours" at 23:30 books 01:30 the next day, and "in 5 hours" at 18:30 books 23:30. The spec gave no hours, so the builder cannot know that night calls are unwanted; it is what was asked. Mention it in the report (the customer asked for it) and keep it.

### 3. LOW — the family's phrase list has no compound or boundary form

Add: a compound duration (finding 1), exactly the window's last minute (for example now + duration = latest time → booked), and one minute past it (outside).

### 4. LOW — `DURATION` is now any hour/minute word

It stops a clock reading whenever such a word is present ("at 3 for an hour" is unclear, not 15:00). Safe direction; the person is asked again. Noted so it is not a surprise in a trace.

## Answers to the CTO's questions

- *"Count from now" vs asking again:* counting is right for exact forms; inexact forms ask again; compound forms are the gap (finding 1).
- *Wrong bookings:* the three compound forms above; none found among the single-span forms (I tried 20).
- *Past midnight:* correct (next date, window rejects; no window books the next day).
- *Without-window behaviour change:* an improvement (no more past-time bookings); one extra turn for a past time; generic message.
- *No brief value in builder/:* yes.


---

## Re-review (Fix: compound durations, bare trailing numbers, edge scenarios)

**Method:** offline. Read "Fix (review T-014)"; re-ran my 25-phrase table at 11:00, 18:30, 23:30 on both specs (with and without a window) and 26 further phrases; `python3 -m unittest`: **540 OK** (26 s). Scratchpad only; no Freya, no model, no env, no edits.

### Decision: **merge edilebilir** (finding 1 closed; one new LOW for a rare phrase)

### Finding 1 — closed

At 11:00, both specs:

| Customer says | Before | Now |
|---|---|---|
| "in 2 hours 30 minutes" | 13:00 | **13:30** |
| "two hours thirty minutes later" | 11:30 | **13:30** |
| "in one hour fifteen" | 12:00 | **asked again** |

More forms, all correct: "in 1 hour 15 minutes" and "one hour and fifteen minutes later" → 12:15; "2 hours 30 minutes from now" and "in 2 hours, 30 minutes" → 13:30; "in 1 hr 20 mins" → 12:20; "in 2.5 hours 10 minutes" → 13:40; "in 3 hours and a half" → 14:30; "in an hour and a half" → 12:30; "in a quarter of an hour" → 11:15. A bare trailing number ("in 2 hours 30", "in 2 hours and 30", "in 1 hour 5", "in two hours 15"), an unconsumed span ("30 minutes and 2 hours later", "in 15 minutes 2 hours"), an extra unit ("… and 30 seconds") and "in 2 hours or 30 minutes" are all `window_unclear` (asked again), not booked. Single-span forms are unchanged. With the A+B-style window the same times go through the window check (18:30 + 1 h 15 → 19:45 outside; 18:30 + 30 min → 19:00 booked).

### Edge scenarios — closed
The window's last minute is booked and one minute past is outside (tests: 11:00 + 8 h and 15:30 + 3 h 30 min booked at 19:00; 481 minutes and 3 h 31 min outside). The family computes the edge from the spec window and `now`, has the three new phrases, and a mutation (the old first-span code) fails all three compound scenarios on Brief A and A+B. The render pin was re-pinned and the report shows the pin changes only with the callback code.

### New LOW — words before the span are ignored

When a span is found, other number words in front of it are not checked. Examples at 11:00 (no window):
- "three quarters of an hour later" → books **12:00** (reads "an hour"); the person meant 11:45. ("in three quarters of an hour" is asked again, correct.)
- "twice an hour later" → 12:00.
- "in 2 hours at 5" → books 13:00 and ignores "at 5" (a clock time and a duration together should be unclear).

These are rare spoken forms, but they are the same kind of silent error as finding 1. **Fix (small, general):** after the match, if the normalised text still holds a digit or number word, or the words `quarter(s)`, `twice`, `thrice`, outside the matched span, return -1; and treat a clock candidate together with a duration as unclear. Add "three quarters of an hour later" to the family phrases.

### Notes kept as stated
Finding 2 (night callback without a window) and finding 4 (any hour/minute word blocks the clock reading) were noted and left; I agree with both.

### Live check (with approval, unchanged)
A chat callback case with a relative time ("call me in two hours"), then one with a compound form ("in an hour and a half"), checking the booked date and time in the ledger.
