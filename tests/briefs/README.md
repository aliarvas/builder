# Messy and changed briefs (extraction rehearsal, T-006b)

Test data only, no builder code. Each folder has its documents, a hand-written `expected.md` (the values a correct extraction must contain) and a hand-written `reference-spec.json`. Each reference spec passes `builder/spec.py` validation and the extractor's own evidence checks, and renders with `--spec --print`.

| Folder | What it rehearses |
|---|---|
| `raw-a/` | Brief A's rules as raw material, in five documents: a manager's e-mail thread, a numbered policy extract (CP-7), a CSV outcome code list, a holiday list in five non-ISO formats, and a **later memo that changes two rules**. The changes are the early-band deadline (12th to 10th business day) and the identity question order. |
| `changed-a/` | Brief A's structure with different values: bank, address, number of identity questions and their fields, bands and attempts, calendar (Saturday is a business day), floors (one is a share of a field), outcome/reason table, sentences. Runs with `openapi-changed-a.json`: same tool names, changed field names, enums and queues. |

## Run (the CTO; the extraction calls the model, `--print` makes no Freya call)

The documents are given in order, followed by the OpenAPI file. A later document overrides an earlier one.

```bash
# raw-a: the memo must win
python3 builder/build.py \
  tests/briefs/raw-a/01-email-thread.md tests/briefs/raw-a/02-policy-extract.md \
  tests/briefs/raw-a/03-outcome-codes.csv tests/briefs/raw-a/04-holidays.txt tests/briefs/raw-a/05-memo.md \
  build-the-builder-v2/tools/openapi.json --print --slot t006b-raw-a > /tmp/t006b-raw-a.workflow.json
python3 tools/compare_spec.py traces/t006b-raw-a.spec.json tests/briefs/raw-a/reference-spec.json

# changed-a: different values and a changed tool contract
python3 builder/build.py tests/briefs/changed-a/brief-changed-a.md tests/briefs/changed-a/openapi-changed-a.json \
  --print --slot t006b-changed-a > /tmp/t006b-changed-a.workflow.json
python3 tools/compare_spec.py traces/t006b-changed-a.spec.json tests/briefs/changed-a/reference-spec.json

# Leftover Brief A / kit values in the changed-a result (expect no output)
grep -n -E '"(promise|no_promise|not_reached|not_verified|transferred|general|support|restructuring|all_verified|wrong_answers_left|products|product_id|past_due|days_late|minimum_payment|instalment_amount|date_of_birth|phone_last4)"' \
  traces/t006b-changed-a.spec.json
```

On a failure, read `extract_error` in `traces/<slot>.failed.log` and the candidate spec in `traces/<slot>.spec.failed.json`. Warnings and unmapped items are in `traces/<slot>.print.log` (`extract_warning`, `coverage_unmapped`).

## What a correct extraction must contain

Full list in each `expected.md`. The critical values:

- **raw-a:**
  - `offer.latest[0].days = 10` (memo, not 12);
  - identity fields in the order `phone_last4`, `date_of_birth` (memo);
  - both changes listed in `overrides`;
  - holidays `2026-10-26, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01`, normalized from non-ISO text;
  - 16 outcome rows from the CSV;
  - `next_weekday = following_week`;
  - `max_unclear_asks = 2`, `max_attempts_per_product = 2`.
- **changed-a:**
  - identity `postcode, birth_year, account_last4`, read through the result fields `answer_ok / tries_remaining / identity_confirmed`;
  - `late_accounts` / `account_ref`;
  - three bands: 8/5/3 business days with 2/1/2 attempts;
  - `non_business_weekdays = [7]`;
  - `earliest = 1 calendar day`;
  - overdraft floor `arrears × 0.25`;
  - `next_weekday = upcoming`;
  - `max_attempts_per_product = 3`, `max_unclear_asks = 3`;
  - close fields `result` / `reason_code`;
  - 16 rows with the changed codes;
  - queues `payment_plans`, `general_enquiries`, `hardship_team`;
  - no leftover Brief A or kit value.

## Reading the comparison

- `compare_spec.py` ignores wording and the builder-chosen variable names. A `DIFF` on identity fields, offer data, outcome rows, state mapping or special-path signatures is a real difference.
- The reference specs are hand-written. A difference on special paths beyond the six listed above can be a legitimate extra path, for example "says twice they do not want to talk". Judge those by hand.
- `rules per section` is information only.
