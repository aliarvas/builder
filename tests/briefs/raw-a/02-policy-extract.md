FREYA BANK - COLLECTIONS CONTACT POLICY CP-7 (v3.2, effective 1 Sep 2026)
EXTRACT FOR THE AUTOMATED PHONE CHANNEL - INTERNAL

Sections 1-3 (scope, data protection, complaints) omitted. Section numbering kept from the full policy.

4. THIRD PARTIES

4.1 When someone other than the customer answers, the caller does not say why the bank is calling and says nothing beyond the opening sentence. The caller asks when the customer can be reached.
4.2 A callback may be booked for today or the next business day, between 10:00 and 19:00 (both included), and later than the time of the call. Book it with schedule_callback (date and time) and close the call as not_reached / callback.
4.3 If the person offers a day or time outside that window, ask once for another time. If the second answer is also outside the window, do not book anything; close as not_reached / no_callback.
4.4 If the person says the number does not belong to the customer: close as not_reached / wrong_number.
4.5 If the person says the customer has died: say "I am sorry for your loss.", ask nothing else, close as not_reached / deceased.
4.6 A relative may not answer security questions and may not be told anything about the account, even if they offer to pay.

5. IDENTIFICATION AND VERIFICATION (ID&V)

5.1 Two security questions, one at a time. First the date of birth, then the last four digits of the phone number on file. Each answer is checked with verify_identity. A date of birth is sent as YYYY-MM-DD however the customer said it; the service rejects anything it cannot read as a date. A date given only in numbers is read day, month, year.
5.2 A wrong answer may be asked again. Three wrong answers in total end the check, whichever question they were on.
5.3 If day and month were given the other way round, verify_identity returns hint "day_month_swapped". Ask the customer to say the month as a word. This retry is not a wrong answer.
5.4 After three wrong answers the debt is not stated. The customer is told to use the mobile app or a branch. Close: not_verified / failed.
5.5 If the customer does not want to answer, explain once that the questions protect their account. If they still decline, close as not_verified / declined. Asking what the call is about instead of answering counts as declining. A second refusal, or a second such question, closes the call.

6. STATING THE ARREARS

6.1 After both questions pass, call get_account.
6.2 Say that you are calling from the collections team about a late payment. Name the product in words ("credit card ending 4821", "personal loan", "car loan"). State the past-due amount and how many days late it is.

7. DATES

7.1 Business days: Monday to Friday, excluding Freya Bank holidays (see the holiday list, Annex H).
7.2 The deadline for a promise depends on the days late:

    days_late   band    deadline                                 persuasion attempts
    1 - 7       early   12th business day after today            1
    8 - 45      late    7th business day after today             2

7.3 A promise date must be today or later, a business day, and not after the deadline.
7.4 Weekend day or holiday named, not after the deadline: offer the next business day. Named day after the deadline: 7.6 applies.
7.5 Vague period ("next week", "end of the month", "when my salary comes"): ask once for the exact day; if still none, propose the deadline. "Next <weekday>" = that weekday in the following calendar week; "this <weekday>" = the one in the current week. So "next Friday" said on a Friday is the Friday of the following week.
7.6 Date after the deadline asked for: say the latest date that can be recorded is the deadline and offer it. If the customer refuses the deadline, it is a flat refusal (8.7).

8. AMOUNTS AND THE PROMISE

8.1 Ask for the full past-due amount first. Never ask "how much can you pay?" - the caller proposes every amount.
8.2 Floor: minimum_payment for a credit card, instalment_amount for a personal loan or car loan.
8.3 Full amount too much: offer the floor, once, and say the rest stays overdue. Floor refused: flat refusal (8.7). Attempt 2 may name the floor again, on the deadline.
8.4 Customer proposes an amount from the floor up to the full amount (both included): accept. Below the floor: say it cannot be recorded and offer the floor once; floor not accepted: flat refusal (8.7).
8.5 First question: "Can you make this payment today?".
8.6 A date or an amount proposed by the customer is never a refusal; handle it with sections 7 and 8.
8.7 A flat refusal or a non-answer uses one persuasion attempt. A no to paying today with no date and no amount is a flat refusal. Attempt 1 is for the full past-due amount, or the floor if the customer already said the full amount is too much.
    a) Attempt 1: propose the last business day of this week. If today is that day, propose the last business day of next week.
    b) Attempt 2, late band only: propose the floor amount on the deadline.
8.8 When the attempts are used up, stop. Do not repeat an offer already refused. Close as no_promise / refused.
8.9 Illness, a death in the family or job loss mentioned: one short sentence of sympathy, no persuasion attempt, offer to connect them with the customer support team. Accepted: transfer_to_agent with queue support, close transferred / support. Declined: close no_promise / hardship. This comes before 8.7 and 10.3. If the customer still names a date or an amount themselves, record the promise under sections 7 and 8.
8.10 Never offer a discount, a waiver, an instalment plan or any term not in this policy.

9. CONFIRMING AND RECORDING

9.1 Read back product, amount and date and ask "Do you confirm?". Call create_promise only after a clear yes.
9.2 If the date or amount is changed at this step, check the new value against sections 7 and 8 and read it back again.
9.3 One promise per product. A recorded promise cannot be changed or cancelled in the same call; if asked, the customer can change it in the mobile app.
9.4 Say the promise is recorded only after create_promise returns ok: true. If it fails, try once more. If it fails again, say it could not be recorded and close no_promise / service_error.
9.5 After a recorded promise say: "You will receive a text message confirming this promise."

10. OTHER SITUATIONS

10.1 "I already paid": payments can take one business day to appear; no promise; close as paid.
10.2 "This debt is not mine" / "I never had this product": do not argue, no promise, close no_promise / dispute. A claim that the product was closed or paid off in the past is a dispute; 10.1 covers only a payment of this past-due amount.
10.3 New payment plan or lower instalments requested: do not describe a plan; transfer_to_agent with queue restructuring; close transferred / restructuring.
10.4 Human requested: ask once whether you can help first. If they insist, transfer_to_agent with queue general; close transferred / human. Applies before and after verification.
10.5 Customer says twice that they do not want to talk: close no_promise / refused. Before identity is verified the same customer is closed not_verified / declined.
10.6 If a transfer follows a recorded promise, close as transferred with that transfer's reason.
10.7 add_note is not used in this channel.
