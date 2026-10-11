# NOW-CASES review (claude-dev2, tests only)

**Reviewer:** claude-reviewer · **Scope:** `tests/fixtures/now-cases.json` (13 cases), `tests/now_calendar.py`, `tests/test_now_cases.py`, `tasks/NOW-CASES-report.md`.
**Method:** offline. (1) Recomputed every expected date and amount of the 13 cases by hand from the Brief A text (`brief-a.md` lines 53–66: holidays, bands, rules 19–23), without `now_calendar.py`. (2) Read `now_calendar.py` for imports and logic. (3) Ran extra `now` values and band edges through the same `walk` helper against the generated code and compared with the calendar. (4) `python3 -m unittest`: 410 OK (the report's number; the tests of this task pass). No Freya, no model, no edits.

## Decision: **merge edilebilir** (LOW notes and a list of missing `now` scenarios)

## 1. Are the expected dates right? (hand check of all 13)

Brief A: business days Monday–Friday except 2026-10-26, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01; deadline = 12th business day after today for 1–7 days late, 7th for 8–45; "next X" = following calendar week, "this X" = current week.

| Case | My calculation | File | |
|---|---|---|---|
| FRI-01 today (Fri 10-16) | 10-16, full 420 | same | ✓ |
| FRI-02 "tomorrow" = Sat | next business day Mon 10-19 | 10-19 | ✓ |
| FRI-03 "next Friday" ×3 | following week's Friday 10-23; deadlines 10-28 (9 days late) and 11-04 (3 days late) are later | 10-23 ×3 | ✓ |
| FRI-04 "20 Nov", 14 days late | 7th business day: 19,20,21,22,23,(26 holiday)27,28 | 10-28 | ✓ |
| HOL-01 Mon 11-09 "this Wednesday" | Wed 11-11 is a holiday → Thu 11-12; deadline (5 late, 12 bd) 11-27 | 11-12 | ✓ |
| HOL-02 "this Friday", floor | 11-13, floor 637.5; deadline (12 late, 7 bd) 11-19 | 11-13 @ 637.5 | ✓ |
| HOL-03 "27 Nov" for both | card 4 late: deadline 11-27 → 11-27; loan 20 late: 7 bd = 10,12,13,16,17,18,19 → 11-19 | 11-27 / 11-19 | ✓ |
| EVE-01 Wed 11-25 "tomorrow" | 11-26 holiday → Fri 11-27 | 11-27, 2 calls | ✓ |
| EVE-02 | card 11-27; loans refused → notes p2, p3 `refused` | same | ✓ |
| YEAR-01 Wed 12-30 today | 12-30 | same | ✓ |
| YEAR-02 "this Friday" | Fri 2027-01-01 holiday → Sat, Sun skipped → Mon 2027-01-04; deadline 8 late: 12-31, 01-04…08, 01-11 | 2027-01-04 | ✓ |
| YEAR-03 "20 January", 14 late | deadline 12-31, (1-1 hol), 1-4,5,6,7,8, 1-11 | 2027-01-11 | ✓ |
| YEAR-04 "next Monday" ×3 | Monday of 12-28's week + 7 = 2027-01-04 | 2027-01-04 ×3 | ✓ |

Amounts (full past-due, or the floor field for HOL-02) and outcomes (`promise`, notes only for the refused loans) also match the brief rules. The "next Friday said on a Friday = the Friday of the following week" example in rule 22 is covered by FRI-03.

## 2. Is `now_calendar.py` independent of the builder?

Yes for logic: it imports nothing from `builder/`, reads only the spec JSON (holidays, `non_business_weekdays`, `earliest`, `latest` bands, amount fields, `next_weekday`), and has its own business-day arithmetic, deadline and "not a business day → next, after deadline → deadline" rule. `test_now_cases.py` imports only three variable-name constants (`ACCEPTS_YES`, `OFFER_ACCEPTS`, `OFFER_AMOUNT_KIND`) and the `Session` simulator from `test_multi_ready`; no builder date function is called.

Two honest limits:
- It is independent of the **code** but not of the **spec**. If an extraction missed a holiday or a band, the calendar and the generated code would agree and the case would pass. The only anchor to the brief is the hand-check test (8 dates typed in). **Add one test** that parses the holiday list and the band table from `build-the-builder-v2/briefs/brief-a.md` and compares them with the fixture specs (the brief is in the repo; a leak test is not affected, it only scans `builder/`).
- `test_expected_ledger_is_the_spec_calendar` recomputes the same function that generated the file, so on its own it is a snapshot test (it does detect drift of the spec fixtures). The value comes from my table above and from the hand test, not from this test; the docstring should say so.

## 3. Do the tests exercise the generated code (no tautology)?

Yes. `walk` builds the real workflow (`build_spec_workflow`), executes the generated `offer_setup`, `check_offer`, the record loop (`confirm_record` → `record_next` → api step → `confirmation_progress`), `closing` and the note loop in the `Session`, and compares the ledger with the file. `test_the_check_names_the_date_the_calendar_gives` compares the check's verdict (`date_not_business_day`, `date_too_late`, `ok`) and `offer_suggested_date` with the independent calendar. I confirmed the `now` really reaches the code: with other `now` values the generated dates move exactly as my hand calculation (below). The report's mutation check (one wrong expected date fails both specs) is consistent with this.

## 4. Extra `now` values I ran against the generated code (all match my hand calculation and the calendar)

| now | phrase | Generated | Hand |
|---|---|---|---|
| Sat 2026-10-17 | "today" | `date_not_business_day` → 10-19 | Mon 10-19 ✓ |
| Sun 2026-10-18 | "tomorrow" | ok, 10-19 | ✓ |
| Mon 2026-10-26 (holiday) | "today" | `date_not_business_day` → 10-27 | ✓ |
| Thu 2026-12-24 | "tomorrow" = 25 Dec holiday | → Mon 12-28 | ✓ (Sat, Sun skipped) |
| Thu 2026-12-31 23:30 | "today" | ok 12-31; "tomorrow" → 2027-01-04 | ✓ (date taken from the date part; the time does not change it) |
| Fri 10-16, 1 and 7 days late | "20 Nov" | `date_too_late` → 11-04 | 12th business day ✓ |
| same, 8 and 45 days late | "20 Nov" | → 10-28 | 7th business day ✓ |
| 7 days late, "29 Oct" | ok (deadline 11-04) | | ✓ |
| 8 days late, "29 Oct" | `date_too_late` → 10-28 | | ✓ |

## 5. Findings

### LOW 1 — the report says `dates_why` is in the file; it is not
Report: "plus `dates_why`: one line per date". The fixture keys are `id, base, brief, description, variables, products, turns, record_answers, expected`. Either add the lines (they are the human-readable hand calculation, useful for the next reviewer) or correct the report.

### LOW 2 — `now_calendar.deadline` crashes when no band matches
With `days_late` outside every band (46, 60, 0) `SpecCalendar.deadline` raises `TypeError` (`rule` is `None`). The generated code does not crash: it accepts any date (I ran 46, 60 and 0 with "20 November": all `ok`, no deadline applied). The brief does not define those products, so this is a hidden-brief question for the policy, not a test failure; but the helper should fail with a clear message, and a test could pin the current code behaviour ("no deadline when no band matches") so a change is noticed.

### LOW 3 — ideal extraction only (the report says so)
The day words are put into `offer_date` as typed in the case. Live wording ("on the twentieth", "next Friday" when the model resolves it itself) is not covered; that stays a chat check.

## 6. Missing important `now` scenarios (suggested additions)

1. **Weekend / holiday `now`**: Saturday, Sunday and Monday 2026-10-26 (holiday) with "today" (the earliest date, deadline counting from a non-business day). I ran them (table above), they pass; add them as cases.
2. **Day before a holiday that is followed by a weekend**: 2026-12-24 "tomorrow" → Monday 12-28. Passes; add.
3. **Band edges**: 7/8 days late and 45 (deadlines 11-04 vs 10-28 on Friday 10-16) and a date on either side of the deadline; the public products never sit on an edge. Pass; add as synthetic products.
4. **Late-evening `now`** (23:30) to pin that the date comes from the date part. Passes; add.
5. **Past weekday word** ("this Monday" said on a Wednesday): `outcome()` has a "before the earliest date" branch but no case uses it; add one case for the earliest-date message.
6. **Callbacks on other `now`** (third-party callback, window 10:00–19:00, later than `now`): not in this file at all; `tests/test_callback.py` covers a few `now` values, but a Friday 18:45 / day-before-holiday set would belong here (the expected next business day follows the same calendar).
7. **Persuasion proposal on a Friday** ("last business day of this week; if today is that day, of next week"): the calendar text is checked by `test_offer_speech`, not by a ledger case on another `now`; add a persuasion case on Friday 2026-10-16 and on Monday 2026-11-09 (holiday week).

## 7. Live

Nothing to run for the file itself. For the self-test step ("different `now` with automatic assertions"), the CTO can replay FRI-02, HOL-01, EVE-01 and YEAR-02 in chat with approval, because those rely on the model passing the day words through unchanged.
