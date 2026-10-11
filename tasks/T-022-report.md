# T-022: spoken dates, unreadable dates, write-tool timeout (UAT F-078, F-079; the numbers F-075/F-076 here were taken)

From the T-020 report. Generic, no brief value. No Freya, no model call, no commit, no env.sh.

## (a) Day numbers in words (F-078)

`offer_check.PRELUDE`:
- `DAY_WORD_VALUES` holds the English cardinals and ordinals 1–31: "one" … "thirty one", "first" … "thirty first", "twentieth", "thirtieth".
- `spoken_day_numbers(text)` turns them into digits **only next to a month name**: "the twenty third of october" → "the 23 of october", "november the sixth" → "november the 6".
- A tens word before a unit past 31 is not a day: "thirty second" and "forty first" stay words.
- Words without a month name are left alone, because they may be an amount or a time.

**Where it applies:**
- `resolve_offer_day` runs it after `normalized_date_text`.
- The callback day reader (`callback.CHECK_BODY.day_words`) runs it on the time text too, joining hyphenated words only between letters, so ISO dates keep their hyphens. The callback's day field already goes through `resolve_offer_day`.

**Checked:**

| Read now | Still `None` |
|---|---|
| "Twenty-third of October", "the twenty third of October", "the sixth of November", "November the sixth", "October twenty-first", "twenty three October", "the thirty-first of October", "Friday the twenty third of October" | "twenty", "I can pay twenty pounds", "the first", "thirty second of October" |

## (b) An unreadable date, again and again

In `check_offer`, when the verdict is `missing` because no date was read (a known product), it counts `offer_missing_streak`. Any other verdict resets the streak to 0, and `offer_setup` sets it to 0.
- **1st:** the new message `missing_latest`: "Could you tell me the exact day you would like to pay? The latest date I can record for the [product] is [date]. Would [date] work for you?"
  - It starts with the old question, so a named period is still not told it was "not heard" (the F-060 LOW test still holds).
- **2nd:** `missing_again`: "Please tell me the day and the month, for example [date]." The example is the latest allowed date, or the earliest when the product has no deadline.
- **3rd and later:** each counts as a rejected offer (its own signature), so the spec's offer limit applies. With Brief A (`max_rejected_offers` 2), the 4th unreadable answer closes the product as refused instead of looping.
- `offer_verdict` stays `missing`, so routes and prompts are unchanged; only the message key changes.

## (c) The proposed date is kept

- On (b)'s 1st and 2nd answer, the proposed date is stored in `offer_suggested_date`. A plain "yes" (`offer_accepts_proposal`) then takes it.
- This is the PUB-04 case: the model had proposed 23 October, the code had no date, and "Okay" led to a `missing` loop.

## (d) Write tools wait 30 s (F-079)

- `tools_from_openapi.write_tool_config(tool)` sets `maxRetries 0` and `timeoutMs` `WRITE_TIMEOUT_MS` = 30000.
- It is used where the renderer already marked writes: the callback booking, the note tool, the record loop (`create_promise`), the special-path tools (`transfer_to_agent`, the note tool), the closing tool and the hangup close tool.
- Reads keep 10000 (`get_account` keeps its single retry).
- Not live-checked: the kit documents no limit for `timeoutMs`. One chat run should confirm it.

## Self-check (my own function)

**`_spoken_date_scenarios`**, called next to `_offer_scenarios`:
- Five forms of the first good day: "the twenty-third of October", "Twenty-third of October", "23rd of October", "October 23rd" and "October the twenty third". Each expects the promise on that day.
- `spoken_date_unreadable_then_yes`: an answer with no date, then "yes", expects the promise on the latest allowed date.
- The family runs at the build's now and the extra nows (`check_nows`, multi-now when `now` is None).
- It passes on all 10 fixtures and recordings.

**With the v18 reader** (mutation in the test), the three word-ordinal scenarios fail as BUILDER. The two digit forms passed before too.

## Tests

**New: `tests/test_spoken_dates.py`** (8 tests):
- a table of spoken forms → dates, and the forms that are not a day;
- the spoken forms helper;
- the code proposes the latest date and "yes" takes it;
- 2nd and 3rd unreadable answer, rejections counted 0, 0, 1, 2, and the product noted at the limit;
- a readable date resets the streak;
- the self-check family and its mutation;
- every write tool has 30000 and no retry, while `get_account` keeps 10000.

**Changed to the new behaviour:**
- `test_offer_date_only.test_yes_without_a_proposed_date_asks_for_the_date`: now also "yes → ok on the proposed date".
- `test_offer_amount_reset.PeriodAnswerTests`: the question plus the proposal, still without "did not catch".
- `test_multi_step`: "next week" suggests 2026-11-02.

`docs/PROMPTS.md` is regenerated (two new verdict lines).

**Brief A pin:** changes on purpose (timeouts, reader code, messages). claude-dev2 re-pinned it at T-023 on the shared tree, which already held this work, and the comment says so. T-025 does not move it again.

## UAT (CTO)

Proposed status for F-075 and F-076: "fixed offline (T-022); live retest of PUB-02 and PUB-04 with style asks_back open".
