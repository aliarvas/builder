# raw-a: effective rules after the memo (hand-written)

Brief A's rules, delivered as raw material. Give the builder the documents **in this order** (the memo is last and overrides earlier text):
`01-email-thread.md 02-policy-extract.md 03-outcome-codes.csv 04-holidays.txt 05-memo.md`, then the kit OpenAPI.

Reference spec: `reference-spec.json` (fixture A with the two memo changes). The rule texts and sentences are written by hand; `compare_spec.py` ignores their wording.

## Changed by the memo (must win over CP-7)

| Rule | CP-7 v3.2 (superseded) | Effective (memo 8 Oct) | Spec path |
|---|---|---|---|
| Early-band deadline (1-7 days late) | 12th business day | **10th business day** | `offer.latest[0].days = 10`, unit `business` |
| Security question order | date of birth, then phone last 4 | **phone_last4, then date_of_birth** | `identity.questions[*].field = ["phone_last4", "date_of_birth"]` |

A correct extraction lists both in `overrides`. No rule may cite the old 12th-business-day text or the old question order as its source.

## Must be present (unchanged values)

- **Call variables:** address with `title`, `last_name`; the date rules use `now` (`offer.today_variable = "now"`).
- **Opening:** introduction (digital assistant, Freya Bank, call recorded); forbidden before verification: collections, debt, payment, product. Confirmation question asked at most **2** times in total (`max_unclear_asks = 2`), then `not_reached/unclear`.
- **Identity:** `verify_identity` fields `phone_last4`, `date_of_birth` (in that order); date of birth as `YYYY-MM-DD`, numbers read day-month-year; `day_month_swapped` hint retry is not a wrong answer; three wrong answers end the check (`identity_failed` -> `not_verified/failed`); declining -> `not_verified/declined`.
- **Third party:** callback today or the next business day, 10:00-19:00 inclusive, later than `now` -> `not_reached/callback`; second out-of-window answer -> `not_reached/no_callback`; wrong number -> `not_reached/wrong_number`; deceased (say "I am sorry for your loss.") -> `not_reached/deceased`.
- **Calendar:** business days Monday-Friday (`non_business_weekdays = [6, 7]`); holidays **2026-10-26, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01** (the source writes them in five different non-ISO formats); promise date must be a business day; earliest = today (`{days: 0, unit: calendar}`).
- **Bands:** days late 1-7: deadline **10th** business day, 1 attempt; 8-45: 7th business day, 2 attempts.
- **"Next <weekday>"** = the following calendar week (`offer.next_weekday = "following_week"`).
- **Invalid-offer limit:** the documents set none, so `offer.max_rejected_offers = 2` and `offer.max_rejected_offers_by_product = []`. The persuasion attempts (1 and 2) belong in `negotiation.rules`, not in this field (F-040).
- **Amounts:** maximum = `past_due`; floor = `minimum_payment` for `credit_card`, `instalment_amount` for `personal_loan` and `car_loan`.
- **Recording:** read back and "Do you confirm?"; create_promise retried once (`max_attempts_per_product = 2`), then `no_promise/service_error`; after a recorded promise the sentence "You will receive a text message confirming this promise."
- **Outcome table (16 rows, from the CSV):** promise/-, paid/-, transferred/{restructuring, human, support}, no_promise/{refused, hardship, dispute, service_error}, not_verified/{failed, declined}, not_reached/{callback, no_callback, wrong_number, deceased, unclear}. A transfer after a recorded promise wins (`wins_over_promise` on the transferred rows).
- **Special paths:** already paid -> `paid`; dispute -> `no_promise/dispute`; plan request -> `transfer_to_agent` queue `restructuring` -> `transferred/restructuring`; human after one "can I help first" -> queue `general` -> `transferred/human` (also before verification); hardship -> offer support: accepted -> queue `support`, `transferred/support`; declined -> `no_promise/hardship`.
- **Not used:** `add_note` (10.7).

## Noise a correct extraction ignores

E-mail headers, signatures and the confidentiality footer, the vendor's request, "sections 1-3 omitted", the holiday names, "ignore the 2025 list", the CSV `policy_ref` column.
