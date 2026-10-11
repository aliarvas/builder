# RC-12 extract — telephone recoveries

Effective 1 October 2026. Clauses not reproduced here do not apply to the pilot.

## Unintended recipient

- Do not disclose the purpose. Ask for a time when the customer can take a call.
- The ordinary callback window is today or the next business day, 09:00-17:00,
  later than the current time. Ask once again after an invalid proposal.
- Successful booking is followed by disposition `unavailable, cb_booked`.
  Two invalid proposals use `unavailable, cb_rejected`.
- A number that does not belong to the customer uses `unavailable, bad_number`.
- On notification of death, offer condolences, ask nothing further, and use
  `unavailable, deceased`.
- No third party may pass security or receive agreement information.

## Security (superseded where the later Risk memo says so)

Ask date of birth and then the last four telephone digits, one at a time. Use
the verification service for each. Three incorrect answers in total fail
security. Explain the privacy reason once after a refusal; a second refusal
ends the call. A format-only rejection is not an incorrect answer.

After security failure, point the customer to the secure app and use the code
table. Agreement lookup is forbidden before `security_complete` is true.

## Agreements

`get_account` returns `agreements`. Work in descending `arrears_amount` order,
not API order. Complete one before the next. Refer to hire purchase as "vehicle
finance", a revolving account as "flex account", and a term loan as "loan".
State its arrears amount and late days.

Business days are Monday to Friday except dates in the supplied calendar.

| late days | latest promise date | allowed persuasion attempts |
|---|---|---|
| 1 through 20 | 7th business day after today | 1 |
| 21 through 50 | 4th business day after today | 2 |
| 51 through 90 | 2nd business day after today | 1 |

A promise cannot be earlier than tomorrow, cannot be on a non-business day and
cannot be after its agreement's deadline. Move a weekend or holiday to the next
business day unless that exceeds the deadline; then offer the deadline. "Next
Friday" means the nearest future Friday, even when it is in the same calendar
week. Ask once for an exact date after vague wording, then propose the deadline.

Ask for the full arrears first. Floors are `required_payment` for a term loan,
`minimum_due` for a flex account and half of `regular_instalment` for vehicle
finance. Round half-instalments to two decimal places. Customer-proposed values
within floor and arrears are acceptable. Below-floor or above-arrears values are
replaced with the floor or full arrears respectively.

A date or amount proposal is not a refusal. On a flat refusal:

1. Offer the full arrears on the deadline.
2. Where a second attempt is permitted, offer the floor on the deadline.

Never repeat a rejected offer and never offer discounts, waivers or unlisted
plans. When the permitted attempts are exhausted, record note `refusal` for
that agreement and continue to the next agreement.

Read back agreement, amount and date and obtain a clear confirmation before
`create_promise`. A correction requires another read-back. Use the returned
`agreement_key`. One promise per agreement. Retry one time after failure; after
two failures be honest and mark that agreement `technical_failure`. After a
successful promise say: "Your promise reference will appear in the customer
portal."

## Agreement-level exceptions

- Already paid: say posting may take three business days and note `paid_claim`.
- "Not mine", fraud, or a closed agreement: do not argue; note `ownership_dispute`.
- Serious illness, bereavement or loss of income: one empathetic sentence, no
  persuasion, offer the `specialist_support` handoff. If declined, note
  `financial_difficulty`.
- A request to change terms goes to `account_options`; do not explain a plan.
- A request for a person: offer to help once, then use `operator` if they insist.
- A successful handoff stops all remaining agreement discussion.
- Scam concern: advise the customer to call the number shown in the Northline
  app, then resume.

Every agreement without a promise requires one note. Retry a failed note once.
If a second note attempt fails, use the technical-failure close code.

## Overall disposition

Use the attached code list. A handoff takes precedence over all other results.
Without a handoff, any recorded promise takes promise precedence. The
all-paid result applies only when every agreement has a `paid_claim` note. An
all-dispute call uses the dispute reason. An all-financial-difficulty call uses
the difficulty reason. Every other zero-promise mixture uses refusal.
