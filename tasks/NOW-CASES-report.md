# NOW-CASES report: public cases on other "now" values (offline)

**Owner:** claude (second developer)
**Not done:** no Freya request, no model call, no commit, no env.sh. No builder code was changed; only test files were added.

## What was built

| File | Content |
|---|---|
| `tests/fixtures/now-cases.json` | 13 synthetic cases from 8 public cases, on 4 `now` values. Each case has its base case, a description, the variables with the new `now`, the base case's products, the customer turns, the bank answers for `create_promise`, and the expected ledger (outcome, reason, promises, notes), plus `dates_why`: one line per date (named day, deadline, rule, result). |
| `tests/now_calendar.py` | `SpecCalendar` reads the spec's own calendar data: `holidays`, `non_business_weekdays`, `earliest`, `latest` per product band, `latest_on_non_business_day`, `min_amount`/`max_amount` and `next_weekday`. It resolves the day words used in the cases, applies the rules, and `expected_ledger` gives the ledger. It is independent of `builder/offer_check.py`, so the cases check the generated code against the spec rather than against itself. |
| `tests/test_now_cases.py` | 5 tests (see below). |

No brief value is in builder code. The fixture and the tests contain dates and amounts, which is allowed: the leak test scans only `builder/`.

## The "now" values and cases

| now | Why | Cases (base) | Expected dates |
|---|---|---|---|
| Fri 2026-10-16 | Friday before a weekend | FRI-01 today (PUB-01); FRI-02 "tomorrow" = Saturday (PUB-01); FRI-03 three products "next Friday" (PUB-11); FRI-04 a day after the deadline (PUB-04) | 10-16; 10-19 (Monday); 10-23 ×3; deadline 10-28 |
| Mon 2026-11-09 | Holiday week (Wed 11-11) | HOL-01 "this Wednesday" (PUB-07); HOL-02 floor this Friday (PUB-06); HOL-03 one date for both, the loan's deadline is earlier (PUB-13) | 11-12; 11-13 at 637.5; p1 11-27, p2 deadline 11-19 |
| Wed 2026-11-25 | Day before a holiday (Thu 11-26) | EVE-01 "tomorrow" + first `create_promise` fails (PUB-10); EVE-02 card "tomorrow", two loans refused (PUB-12) | 11-27 (Friday), 2 calls; 11-27 + notes p2/p3 `refused` |
| Wed 2026-12-30 | Month and year end (holiday 2027-01-01) | YEAR-01 today (PUB-01); YEAR-02 "this Friday" = 1 January + first call fails (PUB-10); YEAR-03 a January day after the deadline (PUB-04); YEAR-04 three products "next Monday" (PUB-11) | 12-30; 2027-01-04; deadline 2027-01-11; 2027-01-04 ×3 |

**Checked by hand** (also asserted in `test_some_dates_checked_by_hand`):
- 7 business days from Fri 16 October: 19, 20, 21, 22, 23, (26 is a holiday), 27, 28 → **28 October**.
- From Mon 9 November: 12 business days (11 and 26 are holidays) → **27 November**; 7 business days → **19 November**.
- From Wed 30 December: 31, (1 January is a holiday), 4, 5, 6, 7, 8, 11 → **11 January 2027**.
- "This Friday" on 30 December is 1 January → **4 January**.
- "20 January" rolls into 2027.
- "Tomorrow" on a Friday → Monday 19 October.

## Tests (`tests/test_now_cases.py`)

1. **File:** there are at least 3 different `now` values; each case's products and brief equal its base case; `now` differs from the base case.
2. **The expected ledger is the spec calendar:** `expected_ledger` on Brief A (`spec-brief-a.json`) and A+B v2 gives exactly the dates and notes in the file. Brief A and v2 have the same calendar data; Brief A's `latest_on_non_business_day: previous` makes no difference, because business-day deadlines always fall on a business day.
3. **Hand checks** (above).
4. **Ledger reached:** each case is walked with the `Session` simulator (from `test_multi_ready`): the offer, accept and refuse turns, one confirmation, the code record loop with the case's bank answers, then closing and the note loop.
   - Checked: the promises equal the expected ones, with one call per promise plus one retry per failure; the outcome and reason; the notes; no rejected typed writes.
   - Brief A cases run on Brief A and v2; Brief B cases run on v2.
5. **The check proposes the calendar's day:** for a non-business day or a day after the deadline, `check_offer` gives `date_not_business_day` or `date_too_late` and its `offer_suggested_date` is the day the calendar gives; an allowed day gives `ok`.

**Results:**
- `tests.test_now_cases`: 5/5, which covers 22 case and spec runs.
- **Mutation check:** one wrong expected date fails both runs of that case.
- Full suite **410 OK**; `git diff --check` clean.

## Results and notes

- **All 22 runs reach the expected ledger.** No code fault was found, so there is nothing for `UAT-FINDINGS`.
- These tests use an ideal extraction: the day words go into `offer_date` as the customer says them ("tomorrow", "this Wednesday", "20 January"). What a live model writes is not covered here; that needs a chat run (with approval).
- `SpecCalendar.resolve` reads only the forms used in the cases (today, tomorrow, this/next <weekday>, "<day> <month>"). A new form needs a new branch in that helper; the helper fails loudly on an unknown form.
- Regenerating the file: the expected values came from `expected_ledger` (generator script in the scratchpad, not committed). Test 2 keeps the file and the calendar in step.
