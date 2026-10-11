# T-034 report: UAT entries for T-031, and the kit's customer styles in the self-check

**Owner:** claude (claude-dev2 role).
**Not done:** no Freya request, no model call, no commit, no env.sh. Generic: every phrase is built from the spec's own days and generic English words; the leak test is green.
**Coordination:** claude-dev (T-033) only works in `organizer-sim/` and confirmed there is no collision. As they asked, I left the forward shift of a non-business day (`shift_to_business(day, 1)`) alone.

## 1. UAT entries for T-031

Both entries are in `docs/UAT-FINDINGS.md`, in the template format.

- **F-095: A product named in other words was booked or refused on the wrong product.** This covers review HIGH 1 and MEDIUM 5. It ends with the open note from LOW 5 (one message refusing two products uses an attempt of each).
- **F-096: A second goodbye after the read-back dropped the accepted offer and noted it as refused.** This covers review HIGH 2. It records the open CTO decision: record on the second goodbye, or close without a refused note.

F-090 is still unused; T-031 proposed it, but it was not written.

## 2. Kit styles compared with the self-check

**Source:**
- `build-the-builder-v2/tools/run_cases.py`, `STYLES`, applied with `--style`.
- In `public-test-set.json` no case sets `style` itself, so a style can be put on any case.

| Style | What the customer does | Reaches our code? | Self-check before T-034 | Gap |
|---|---|---|---|---|
| `in_words` | amounts and dates in words; years and codes digit by digit | dates: yes (the code reads `offer_date`); amounts and identity answers: no (the model fills a number or a tool argument) | dates in words: `spoken_date_*` (6 forms) | the year said digit by digit was not played (it was read correctly; now covered) |
| `corrects` | "the 21st, sorry, I mean the 20th", once or twice | yes, the date phrase | none | **the first (wrong) day was booked** |
| `pieces` | long numbers and dates in two parts, the rest in the next turn | yes, the date phrase | none | **never read**: each piece alone is unreadable, and the extractor copies only the last message |
| `talkative` | small talk before most answers; once "my cousin's wedding is on the 30th" | yes, when the extractor copies the whole phrase | none | **the wedding day was booked** when the phrase holds both days; small talk around one date was already fine |
| `asks_back` | twice a short question back before answering | the opening value counts toward the unclear close | `special_*` and goodbye turns only | **at the opening a question back was "unclear"**: two of them close the call before the customer confirms. At the other steps a turn without an answer was never played |

**Model-only behaviour, not testable offline (listed, no code change):**
- **`pieces` for identity answers.** The model may call `verify_identity` with half an answer, which uses an attempt.
- **`pieces` and `in_words` for amounts.** The model fills `offer_amount` as a number.
- **`corrects` for amounts.**
- **`talkative`:** whether the extractor copies the wedding day into `offer_date` at all.

These need chat runs with `--style`.

## 3. Fixes, all generic

**Date reading (`builder/offer_check.py`, generated code):**
- **`resolve_offer_day` is now a wrapper; the old function is `resolve_offer_day_once`.**
  - **Correction:** after the last correction word (sorry, I mean/meant, no wait, wait, actually, rather, make that, correction), the tail is read. A tail without a month takes the phrase's month.
  - **Several days:** when the phrase holds more than one distinct day ordinal ("14th", "fourteenth") and no correction, only the one part that says pay is read. Without exactly one such part, no day is taken and the existing unreadable path asks again.
  - **What still counts as one day:** cardinals ("at 5") are not counted as days, so "the 20th of October at 5" stays one day.
- **`CHECK_BODY`, pieces:** an unreadable date piece is kept for one turn (`offer_date_piece`) and read again joined with the next piece. It is cleared on any readable date or an empty turn.

**Opening (`builder/prompts.py`):**
- **`WHO_ANSWERED_DESCRIPTION`:** a question back is now the greeting value (not an answer, not counted), and no longer unclear.
- **The two opening prompt lines** say "greet you, check the line or ask a question back".
- **Budget on brief-ab-extracted-v2:** opening 773 → 783, opening_reask 722 → 728. The `check_offer` code payload goes from 52 768 to 55 653 bytes.

## 4. New self-check family `style_*` (`builder/selfcheck.py`)

Every phrase is built from the spec's first allowed day (`plan.good_day`). Each call must record the promise on that day; the existing ledger, notes and close checks apply.

| Scenario | The customer says |
|---|---|
| `style_corrects_digit` | "the <other>th, sorry, I mean the <day>th of <Month>" |
| `style_corrects_month_first` | "<Month> <other>th, sorry, I mean <Month> <day>th" |
| `style_corrects_words` | the same in words |
| `style_corrects_weekday` | "<weekday+1>, sorry, I mean <weekday>"; only when the day is 1–6 days ahead (the fixtures' first allowed day is today, so no fixture plays it now) |
| `style_pieces_day_then_month` / `_month_then_day` | the date in two offer turns |
| `style_talkative_chatter` | small talk, then the date |
| `style_talkative_other_day` | "my cousin's wedding is on the <other>, but I can pay on <date>" |
| `style_talkative_other_day_no_pay_word` | the same without "pay": no day is taken; the customer then says the date alone |
| `style_in_words_year_digits` | the date in words, the year digit by digit |
| `style_asks_back` | a question back twice at the opening (greeting value), and once each at identity, negotiation and read-back |

**New in `play`:** a `"stays": True` turn must keep the step. If it moves the call, the failure is "the ask_back turn at <step> moved the call…".

## Tests

**New `tests/test_t034_customer_styles.py` (5 tests):**
- every fixture plays the 10 or 11 style calls without a failure;
- the old date reading, restored by a mutation, fails the corrects, pieces and talkative calls, and books the wedding day;
- the family is part of `run_selfcheck`;
- the opening description and prompt treat a question back as the greeting;
- a step that moves on a turn without an answer is flagged.

**Other checks:**
- **Pin:** the Brief A render pin moved (the date code and the opening texts) to `008ead0a…`, with a comment line.
- **Docs:** `docs/PROMPTS.md` regenerated.
- **`python3 -m unittest`:** **649 tests, OK**, including the leak test and the prompt budget guard.

## Open (with approval, chat first)

- Chat runs with `--style corrects`, `pieces`, `talkative` and `asks_back` on PUB-01 and PUB-07 (dates), and on PUB-12 (several products).
- `pieces` with a readable first piece ("the 14th" … "of November") still books the 14th of the current month first. The read-back then shows the day, and the customer can revise. I left this because a lone "the 14th" is a valid answer.
