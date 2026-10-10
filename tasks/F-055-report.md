# F-055 — callback date and time resolved in code

**Owner:** claude (second developer) · **Finding:** `docs/UAT-FINDINGS.md` F-055 (PUB-02 v13: "tomorrow" sent as `2025-05-15`, expected `2026-10-15`).

No Freya call, no commit, no `env.sh`. claude-dev was editing `workflow.py`, `offer_check.py` and `prompts.py` at the same time, so the logic lives in a new module. Each shared file got a small, local edit made right after re-reading it.

## Design

A failed or blanked `schedule_callback` call cannot carry the "outside the window, ask again" answer. The engine counts it in `schedule_callback_failure_count`, and the closing rules turn that into `callback_failed` at once. So the check runs **before** the tool, like the offer path (`negotiate` → `check_offer`):

```text
third_party (conv)    no tools; extraction copies the person's words: callback_day_text, callback_time_text
  -> callback_check (code)   when callback_time_text is set
       window_ok       -> callback_book (api_request; schedule_callback pre-action with {{callback_date}}, {{callback_time}}) -> closing
       window_give_up  -> closing (intent variable = spec outside_close_value -> third_party:<value>)
       otherwise       -> callback_say (code, tts {{callback_message}}) -> third_party
```

- **The model never types the date or time.** The third-party step has no tools. The booking tool's `date`/`time` fields have engine-filled defaults, are no longer required and have `maxRetries: 0`.
- **Resolution:** `callback_check` reuses `offer_check.PRELUDE` with the spec's offer calendar: `resolve_offer_day`, `today()` from the call's `now`, and `is_business` with weekends and holidays.
  - Day words are found in the phrase: tomorrow, weekday, date, "this afternoon", and so on. No day means today.
  - Times: `3pm`, `14:30`, `10.15 am`, `half past three`, `noon`, number words, morning/afternoon hints. A bare hour is tried as both am and pm, and the one inside the window wins.
  - The text variables are cleared after every check, so the step does not loop.
- **Window (spec data, optional):** `third_party.callback_window` = `{days_ahead, day_unit (business|calendar), earliest_time, latest_time, after_now, max_outside_asks, outside_close_value}`.
  - The allowed days are today plus the next N business or calendar days. The time must be inside the window, both ends included, and later than `now` when the day is today.
  - Each offer outside the window is counted. Above `max_outside_asks`, the step closes with `outside_close_value`, which must be one of `third_party.close_values`.
  - Without a window, only "today or later" is checked, but the date is still resolved in code. That is the F-055 fix on its own.
- **Spoken lines:** `CALLBACK_OUTSIDE_SAY` with the window in words ("today or the next business day, between 10:00 and 19:00") and `CALLBACK_UNCLEAR_SAY`. Both are in `prompts.py`.
- **Fallback:** if the OpenAPI tool has no recognisable date and time body fields (name, description or format "date" / "time" / "HH:MM"), the old model-filled tool is kept and a warning `… F-055 not applied` is traced.
- **Close rules:** `callback_failed` also fires on `callback_book_failure_count > 0`; the engine's counter for a pre-action node is named after the node.

## Files

| File | Change |
|---|---|
| `builder/callback.py` (new) | Window validation (`SpecError`), field detection, generated `callback_check` code, the three nodes, extraction fields, entry transition |
| `builder/workflow.py` | One import; after the third-party extraction schema: add the callback nodes, empty the third-party tools, add the 2 extraction fields and the entry transition; one extra condition in `close_rules` → `callback_failed` |
| `builder/extract.py` | Merge copies `third_party.callback_window` (without `source`). Evidence check: `earliest_time`/`latest_time` must appear in the documents (as H:MM / HH:MM / H.MM, or on the hour as "7 pm"). Values are validated by the dry render, so errors go to the repair round. |
| `builder/prompts.py` | `callback_window` added to the `third_party` shape in `EXTRACT_OPENING_IDENTITY_TASK`; 4 new prompts (2 extraction descriptions, 2 spoken lines), registered in `PROMPTS` |
| `docs/PROMPTS.md` | Regenerated (`python3 -m builder.prompts`) |
| `tests/test_callback.py` (new) | 18 tests |

No brief value is in the code. All window numbers come from the spec, and the leak scan in `test_multi_step.py` passes. To pass that scan, `callback.py` uses `dict(type=…)` and prefixed verdict keys.

## Tests

`tests/test_callback.py`, with now = Wed 2026-10-14 11:00 and the fixture calendar:
- The F-055 case: "tomorrow" + "around eleven in the morning" gives 2026-10-15 11:00. The whole phrase in the day field gives the same.
- Time forms; today must be later than now; outside hours and days; the next business day skips the weekend and the 26 Oct holiday.
- A second outside offer gives up with `no_callback`; unclear words do not count; the text is cleared; no window still resolves in code; a 2-calendar-day window.
- Render: no tool in `third_party`, the engine fills `date`/`time`, the routes, no `null`, no `{{` in code, the `callback_failed` rule, invalid windows fail the render, a tool without date/time fields keeps the model tool with a warning.
- Extraction: the merge keeps the window; time evidence is checked; an omitted window is allowed.

```text
python3 -m unittest tests.test_callback   # 18 OK
python3 -m unittest                        # 290 OK (includes claude-dev's current work)
python3 builder/build.py brief-a.md openapi.json --spec traces/brief-a.spec.json --print   # renders: callback_check/say/book, third_party tools []
git diff --check                           # clean
```

## Open / `[TO-CONFIRM]`

1. **The existing extracted spec has no `callback_window`.** `traces/brief-a.spec.json` predates this change, so a `--spec` build resolves dates in code but does not check the window. The next extraction run fills it; check that its values match the brief (today or next business day, 10:00–19:00, after now, one more ask, `no_callback`).
2. **Live:** check that a `tts` line on the code step `callback_say`, followed by a return to a conversation step, does not hit the F-050 platform problem. F-050 was a `tts` line on an **api** step; code steps with `tts` such as `closing_say` work live. Also check that the routing leaves `third_party` in the same turn the time is said, so the dialogue model does not answer there first.
3. The third-party rules from the spec may still say "call schedule_callback". The step has no tool now, and the kit's no-tool rule is shown, so the model cannot call it. A false "I booked it" from the model is unlikely, because the routing leaves the step before it replies. Watch for it in the PUB-02 retest.
4. The spoken lines are English, like the other fixed fallbacks.
5. The F-055 status in `UAT-FINDINGS.md` was not updated (not my file); suggested: "fixed offline, PUB-02 retest pending".

Note: during one run, while claude-dev was editing `prompts.py`/`workflow.py`, 6 tests failed elsewhere (`on_enter_first_entry_only`, offer speech, prompt budget). I re-ran the budget test with the callback integration switched off and it passed, so I ran it again alone with the integration on: it passed too. The final full run was 290 OK. The failures came from the other work in progress, not from this change.

## Fix (review `reviews/F-055-review.md`)

**Owner:** claude (second developer). Changed: `builder/callback.py`, `tests/test_callback.py`, small edits in `builder/workflow.py` (my F-055 block and `STEP_ALIASES` only), `builder/prompts.py` (my callback prompts), `builder/extract.py` (`_clock_in_brief`). I re-read each shared file before editing it. claude-dev's negotiate, opening and budget parts were not touched. No Freya, no commit, no `env.sh`.

| # | Finding | Fix |
|---|---|---|
| 1 | An empty day field booked **today** | `callback_day(day_text, time_text)`: the day field first, then day words found in the time field (tomorrow, weekdays, `the 15th`, `15 October`, `this afternoon`, …), and today only when **neither** names a day. A day field that names no day ("whenever") is unclear. A bare number is never a day. |
| 2 | Wrong time booked silently | New clock parser: a number word or digit hour may be followed by a minute (`ten fifteen`, `four thirty`, `eleven oh five`, `twelve forty five`, `10 30`), plus `half/quarter past/to`. A duration (`in two hours`, `half an hour`, `20 minutes from now`) and more than one clock number (`between 2 and 4`, `2 or 3`) give **no** time, so the step asks again. Day words are removed before the clock is read. The hour comes from the time field only; the day field is read for a time only when the time field is empty. |
| 3 | Nothing asks for day and time | `CALLBACK_COLLECT_RULE` (generic) is added to the third-party task when the code books callbacks: get the day and the time in the person's own words, ask for the missing one, never say it is booked. |
| 4 | Double speech after the fixed line | **Changed from the review's suggestion.** A silent `third_party_ask` failed claude-dev's F-053 rule (`test_offer_speech` NoDeadAir: every step a global path returns to must speak on entry). So `third_party_ask` follows the `offer_say` pattern instead. It is a copy of the finished `third_party` step (same prompt, extraction, routes; made by `third_party_ask_node`), and its entry is the fixed line `{{callback_message}}`, not the model. The model does not talk after the line, and a global path that returns hears the pending question again. `callback_say` was removed, which also removes the tts-on-a-code-step risk. `third_party` itself is unchanged (no `on_enter_first_entry_only`). `STEP_ALIASES["third_party"]` includes the copy, so global paths fire there too. |
| 5 | Field names not found | Names are split on `_`, `-`, `.` and camelCase, and decide first. Descriptions and formats decide only when the names do not. A single date-time field (`…datetime`, `timestamp`, or `date` + `time` in one name, or format `date-time`) gets `{{callback_date}}T{{callback_time}}:00`. Call variables are skipped. |
| 7a | Unbounded loops | With a window, `outside_close_value` is **required** (`SpecError`); the extraction prompt now says so. Unclear tries are counted (`callback_unclear_count`); above `max(1, max_outside_asks)` the step closes with the same value. |
| 6 (optional) | Evidence dropped valid windows | `_clock_in_brief` also accepts a bare 24-hour number in a range or with an hour unit: `10 to 19`, `10-19h`, `between 10 and 19`, `19 hrs`. Not a rule number ("rule 10"). |

Not done: 7b (reading back the booked day and time). The closing line is the spec's text; a code-made read-back would need a change in the closing step, which is outside this task.

### Tests (`tests/test_callback.py`, 30)

New tests:
- the whole phrase in the time field (`tomorrow at 3pm`, `tomorrow around eleven in the morning`, `on the 15th at 3pm`, `this afternoon at 4`, `at 4pm` = today);
- a day field without a day is unclear;
- minute words; durations and several numbers are unclear;
- `20 October` + `3 pm` reads 15:00, not hour 20; `the 15th` + `whenever` is unclear;
- unclear tries are counted and give up;
- the collect rule is in the task;
- the copy equals `third_party` except its tts entry, and `third_party` has no `on_enter` / first-entry flag;
- global paths fire in both;
- field names (`callback_date`, `callbackTime`, `scheduled-date`, time listed before date, format/description only, one datetime field) and the datetime default;
- a window without an exit value fails;
- bare-hour evidence.

```text
python3 -m unittest tests.test_callback   # 30 OK
python3 -m unittest                        # 303 run, 2 failures, both outside this change:
  test_multi_step.OfferCheckTests.test_brief_a_late_deadline_on_holiday_week_and_setup_facts
  test_spoken_output.ReadBackTests.test_facts_tell_the_agent_how_to_name_each_product
  -> both expect the old product facts wording ("Product 1: type credit_card"); builder/offer_check.py
     (claude-dev's uncommitted F-053/054 work, file changed at 00:53) now writes "Product 1, credit card
     ending 0377: ...". With the callback integration switched off, the same 2 tests fail.
git diff --check                           # clean
```

Still `[TO-CONFIRM]` live (PUB-02 retest):
- the tts entry on the `third_party_ask` conversation step, like `offer_say`;
- that routing leaves `third_party` in the turn the time is named;
- that the next extraction fills `callback_window` with a close value.

## Fix 2 (re-review, remaining note 1: day and time in two turns)

**Owner:** claude (second developer). Changed: `builder/callback.py`, `builder/prompts.py` (one new spoken line, re-read before the edit), `tests/test_callback.py`. claude-dev's `offer_check.py` and budget code were not touched. No Freya, no commit, no `env.sh`.

**Problem:** with "tomorrow" in one message and "3pm" in the next, the code relied on the platform keeping `callback_day_text`. If extraction empties it, the second turn books **today**.

**Fix:** the day no longer depends on extraction memory.
- **Entry:** `third_party` → `callback_check` now fires when the person names a day **or** a time.
- **Kept day:** `callback_check` writes the resolved day (ISO) to the code-owned `callback_day_kept`. When a turn names no day, the kept day is used. When no day was named in any turn, today is used.
- **Priority:** this turn's day field, then day words in this turn's time field, then the kept day, then today. A day field that names no day ("whenever") stays unclear.
- **Day alone:** new verdict `window_need_time`. The day is kept and `third_party_ask` speaks `CALLBACK_TIME_ASK_SAY` ("Thank you. At what time of day can we call back?").
- **Clearing:**
  - after booking (`window_ok`) and after giving up;
  - when an offer is outside because the **day** itself is outside the window, so the next bare time does not reuse that day;
  - when only the time was outside, the day is kept ("tomorrow 8pm" → "3pm" books tomorrow 15:00).
- **Loop safety:** day-only turns are counted in their own counter (`callback_need_time_count`), with the same limit as unclear tries, `max(1, max_outside_asks)`; above it the step gives up with `outside_close_value`. The outside and unclear counters are unchanged, and the text variables are still cleared on every check.
- **Kit rule fix:** the entry condition had `"logic": "and"` at the top level, which `workflow-format.md` forbids. It is now an OR of two AND groups (time set and not empty; day set and not empty).

Tests (`TwoTurnTests`, 7 new; `tests/test_callback.py` 37):
- the helper runs `callback_check` once per message on one variable table and empties both text fields on every turn (the worst case);
- day then time books the kept day and clears it;
- a new day replaces the kept one;
- an outside time keeps the day; an outside day is dropped;
- with no day at all, a bare time is today;
- repeated day-only answers give up with `no_callback`;
- the entry condition shape.

```text
python3 -m unittest tests.test_callback   # 37 OK
python3 -m unittest                        # 310 run, 1 failure outside this change:
  test_multi_step ... test_builder_string_literals_do_not_embed_fixture_values -> an int literal 3 in
  workflow.py line 1626, ESTIMATED_PRODUCTS = 3 (claude-dev's T-009c budget work, uncommitted)
git diff --check                           # clean
```

Live check (PUB-02 retest, `pieces` style): the day and the time in separate messages; the expected call is `schedule_callback` with the kept day.

## Fix 3 (re-review 2, notes 1 and 2)

**Owner:** claude (second developer). Changed: `builder/callback.py` (generated `callback_check` code) and `tests/test_callback.py`. No prompt or workflow change. claude-dev's T-009c code was not touched. Note 3 is left as it is. No Freya, no commit, no `env.sh`.

1. **Note 1, a corrected day is not counted.** A day-only turn counts in `callback_need_time_count` only when it does **not** change the kept day. The first day sets it, so it is not counted either; only a repeat of the same day without a time counts. The limit is now `max(2, max_outside_asks)`. Unclear tries keep `max(1, max_outside_asks)`.
2. **Note 2, a day alone that is outside the window.** It now gets the outside verdict at once: the window line ("We can call back today or the next business day, between …") is said, the try counts as an outside offer, and the kept day is dropped. So a following bare time is read for today, not for that day.

Tests (`tests/test_callback.py`, 39):
- `tomorrow` → `Thursday` → `11am` books Thursday 2026-10-15 11:00;
- from Tuesday, `tomorrow` (Wed) → `Thursday` changes the kept day, is not counted, and `11am` books Thursday;
- the same day repeated: the 3rd day-only answer still asks (count 2), the 4th gives up with `no_callback` and clears the kept day;
- `Friday` alone (outside) gives the outside line, outside count 1 and no kept day, and the following `4pm` books today 16:00.

```text
python3 -m unittest tests.test_callback   # 39 OK
python3 -m unittest                        # 319 OK
git diff --check                           # clean
```
