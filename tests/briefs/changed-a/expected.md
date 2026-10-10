# changed-a: values a correct extraction must contain (hand-written)

Same structure as Brief A, different values, run with `openapi-changed-a.json` (tool names unchanged; field names, enums and queues changed). Reference spec: `reference-spec.json`. The rule texts and sentences in it are hand-written; `compare_spec.py` ignores their wording.

**Leftover-value check:** nothing from Brief A or the kit OpenAPI may appear in the extracted spec. That covers:

- the outcome codes `promise`, `no_promise`, `not_reached`, `not_verified`, `transferred`;
- the queues `general`, `support`, `restructuring`;
- the field names `all_verified`, `wrong_answers_left`, `products`, `product_id`, `past_due`, `days_late`, `minimum_payment`, `instalment_amount`, `date`, `outcome`;
- `date_of_birth`, `phone_last4`, `Freya`.

| Area | Brief A / kit | changed-a | Spec path |
|---|---|---|---|
| Address | title + last name | **first name + last name** | `opening.address_with = ["first_name", "last_name"]` |
| Unclear asks | 2 | **3** | `opening.max_unclear_asks` |
| Identity questions | date_of_birth, phone_last4 | **postcode, birth_year, account_last4** (in this order) | `identity.questions[*].field` |
| Identity result fields | verified / wrong_answers_left / all_verified | **answer_ok / tries_remaining / identity_confirmed** | `identity.answer_verified_field`, `attempts_left_field`, `verified_field` |
| Swapped-format hint | day_month_swapped | **format_postcode** (spell the postcode) | `identity.failed_answer_instruction` |
| Wrong answers allowed | 3 | **2** (enforced by the tool; text only) | `identity.rules` |
| Products list / id | products / product_id | **late_accounts / account_ref** | `account.products_field`, `account.product_id_field` |
| Product kinds | credit_card, personal_loan, car_loan | **card, overdraft, loan** | `offer.min_amount[*].when` |
| Business days | Mon-Fri | **Mon-Sat** | `offer.non_business_weekdays = [7]` |
| Holidays | 5 dates | **2026-11-30, 2026-12-24, 2026-12-26, 2027-01-04** | `offer.holidays` |
| Earliest date | today | **tomorrow** | `offer.earliest = {days: 1, unit: calendar}` |
| Bands (days overdue) | 1-7: 12th / 1 attempt; 8-45: 7th / 2 | **1-10: 8th / 2; 11-30: 5th / 1; 31-60: 3rd / 2** (business days) | `offer.latest`, `offer.max_rejected_offers_by_product` |
| "Next <weekday>" | following week | **nearest after today** | `offer.next_weekday = "upcoming"` |
| Floor | minimum_payment / instalment_amount | **min_due (card), monthly_payment (loan), 25% of arrears (overdraft)** | `offer.min_amount` (overdraft: `field: arrears, share: 0.25`) |
| Maximum | past_due | **arrears** | `offer.max_amount` |
| Promise tool fields | product_id, amount, date | **account_ref, amount, pay_date** | `confirmation.promise_*_field` |
| Recording attempts | 2 | **3** | `confirmation.max_attempts_per_product` |
| Sentence after recording | text message | **"A confirmation letter will be sent to your home address."** | `outcomes[pledged].say` |
| Close tool fields | outcome / reason | **result / reason_code** (reason is an enum here) | `closing.outcome_field`, `closing.reason_field` |
| Callback window | today or next business day, 10:00-19:00 | **today or next two business days, 09:00-18:00** | `third_party.rules` |
| Deceased sentence | "I am sorry for your loss." | **"Please accept our condolences."** | `third_party.rules` |

**Outcome table (16 rows):**

- `pledged`/-, `already_settled`/-;
- `handed_over`/{plan_request, person_request, hardship}, all with `wins_over_promise`;
- `no_pledge`/{declined_to_pay, hardship_declined, disputed, system_error};
- `unverified`/{wrong_answers, refused_check};
- `unreachable`/{callback_booked, no_callback, wrong_person, deceased, unclear_answer}.

**State mapping:**

| State | Row |
|---|---|
| `identity_failed` | `unverified/wrong_answers` |
| `opening_unclear` | `unreachable/unclear_answer` |
| `callback_scheduled` | `unreachable/callback_booked` |
| `promise_recorded` | `pledged` |
| `promise_failed` | `no_pledge/system_error` |
| `default` | `no_pledge/declined_to_pay` |

**Special paths:**

| Situation | Tool and queue | Outcome |
|---|---|---|
| Already paid | none | `already_settled` |
| Dispute | none | `no_pledge/disputed` |
| Payment plan | `transfer_to_agent`, queue `payment_plans` | `handed_over/plan_request` |
| Person, after one "can I help first" | `transfer_to_agent`, queue `general_enquiries` | `handed_over/person_request` |
| Hardship, offer accepted | `transfer_to_agent`, queue `hardship_team` | `handed_over/hardship` |
| Hardship, offer declined | none | `no_pledge/hardship_declined` |

`add_note` is not used.
