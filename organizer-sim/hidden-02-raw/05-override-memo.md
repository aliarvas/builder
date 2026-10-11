# Risk memo 14 — immediate overrides to RC-12

Issued 6 November 2026. This memo is later than the RC-12 extract and overrides
only the items listed here. All other RC-12 rules remain in force.

1. The identity service no longer accepts date of birth or telephone digits.
   Ask **billing postcode first**, then the **last three characters of the
   customer reference**. Use verification kinds `billing_postcode` and
   `customer_ref_last3`, in that order. Normalize the postcode to uppercase
   without spaces and the reference characters to uppercase.
2. There are **two wrong answers total**, not three. After two wrong answers use
   `security_stop / wrong_answers`. The refusal handling in RC-12 is unchanged.
3. Callback staffing changed. A callback is valid today or within the next
   **two** business days, from **11:00 through 18:30**, and later than `now`.
   The same one-retry rule and disposition codes still apply.
4. The calendar file contains an obsolete closure. **2026-12-28 is a business
   day.** Add **2026-12-31 as a non-business day** instead. The other listed
   dates remain non-business days.
5. Following a successful promise, replace the RC-12 sentence with exactly:
   "We will send confirmation by secure message."
