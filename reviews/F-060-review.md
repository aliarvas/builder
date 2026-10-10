# F-060 review — `offer_amount` reset with a sentinel

**Reviewer:** claude-reviewer · **Scope:** `offer_check.py` (`AMOUNT_NONE_VALUE = -1.0`, `parse_amount`, reset), the new `missing` sentence in `prompts.py`, `tests/test_offer_amount_reset.py`. The 5 full-suite failures in `workflow.py` (F-056/059, claude-dev2) were not reviewed.
**Method:** offline. I replayed the check code with the `Call` helper: all value forms of the amount (number, text, negative, zero, empty, `None`, NaN, unicode minus), the accept-proposal paths, a repeated invalid offer, and a scan of every string variable for the sentinel. I also scanned the rendered workflows for other typed variables written with an empty value. 42 tests in the offer files pass. No Freya, no model, no edits.

## Decision: **düzeltme gerekli** (one MEDIUM regression; the leak questions are answered clean)

## Finding

### 1. MEDIUM — the sentinel breaks "the same invalid offer again is not a new rejection" (`offer_check.py:676`)

The rejection signature is built from the **raw** variable: `str(vars.get(amount_var))`. The first turn sees the unset value (`None`), every later turn sees the sentinel (`-1.0`), because the reset now really succeeds. So a customer who repeats the same too-late date, with no amount, is counted as two different offers:

| turn (date `2026-11-30`, no amount, limit 2) | before F-060 (the `""` write was rejected, value stayed unset) | after F-060 |
|---|---|---|
| 1 | rejected, count 1, signature `1\|2026-11-30\|None\|none` | same |
| 2 (identical) | rejected, **count 1** | signature `…\|-1.0\|…` differs → **count 2 → limit reached, product closed (`more`)** |

I reproduced both columns (the "before" column by putting the unset value back between turns). The invalid-offer limit then closes a product after the customer merely repeats a date once. That changes the offer policy (`invalid_offer_limit`) and can lose a case. The sentinel is not leaked; it is read by a second reader that was not updated.
**Fix:** build the signature from the parsed values, not the raw text: use `amount` (the result of `parse_amount`, `None` for the sentinel) in the signature, or set the sentinel in `offer_setup` so turn 1 and turn 2 look the same. The first is safer (also covers `""`, `None`, `-1`, `"-1.0"`). Add a test: two identical date-only invalid offers leave the count at 1.

## Your questions

- **Can `-1` reach the customer, a prompt, a summary or `create_promise`?** No. `{{offer_amount}}` appears in no prompt or tool default (grep of `builder/` and `PROMPTS.md`). Every spoken text is built from `suggest_amount`/accepted entries; `suggest_amount` is only ever the floor or the full amount. The promise hook reads `offers_accepted` (amounts stored as `round(parsed, 2)`). After a 3-turn two-product flow I scanned all string variables for `-1`: only the internal signatures can contain it (and that is finding 1); `offers_summary` and `offer_message` never do.
- **Other readers of the variable:** only `check_offer` (line 617, through `parse_amount`) and the signature (finding 1). The routing to `check_offer` is keyed on `offer_date` and the accept flag, not on the amount, so a leftover `-1.0` does not trigger a check. Closing rules, read-back, `offers_summary`, self-test and the spoken-text detector do not read it.
- **`parse_amount` and negatives:** `-1.0`, `"-1.0"`, `"-1"`, `"-0.5"`, `"  - 5"`, NaN, `""` and `None` all count as "no amount" (date-only offers take the proposed amount: full 95, or the floor 28.50 when `offer_proposed_kind = minimum`). `0` and `"0"` stay `amount_missing` ("Could you pay 95?"), as before. A range text such as `"10-15"` (not a float) still parses to 1015 and gives `amount_too_high`; that is old behaviour and the field is a float, so it cannot occur from extraction. The unicode minus is read as a positive number; the sentinel is ASCII, so no effect.
- **Can the extraction model see `-1` and write it back?** I cannot see the platform; if extraction receives current values it may copy `-1`, which is read as "no amount" (harmless). The only harmful write would be a positive number the customer did not say; the extraction text is unchanged ("the payment amount the customer proposes or accepts in their last message… Empty if none"), so the sentinel adds no new instruction. Keep the live check the developer lists (no `validation_errors` for `offer_amount` in the trace).
- **Other typed variables reset with an empty value:** I scanned the rendered code of A, A+B and the tagged A+B spec for `= ''`/`None` writes to variables that are typed or enum extraction fields. None found besides the fixed one (`special_result_*` writes are not extraction fields). The report's note that only the offer flow is proven by test is accurate.
- **`missing` sentence:** "Could you tell me the exact day you would like to pay?" suits both an unclear answer and a period ("the week after next"); it contains no "did not catch"; the spoken-text detector passes it (tested).

## Live checks to keep

`validation_errors` for `offer_amount` gone from the `check_offer` step; PUB-07-like run (amount below the floor, then only a date → the floor is accepted); repeat the same too-late date twice and check the product is not closed after the second.


---

## Re-review (Fix: signature from the parsed offer)

**Method:** offline; replayed the failing sequence and the neighbouring cases on the check code. `python3 -m unittest`: 337 OK. No Freya, no model, no edits.

### Decision: **merge edilebilir**

- **Finding 1 fixed.** The signature is now `product|ISO day|amount to two decimals` (`offer_check.py:678`), built from the parsed day and the amount after the date-only default. The same too-late date with no amount, three times: counts 1, 1, 1; signature `1|2026-11-30|95.00` every time; the product is not closed. Before the fix the second turn gave count 2 and `more`.
- **All "no amount" forms give one signature:** `None`, `""`, `-1.0`, `"-1"`, `"-1.0"` → `1|2026-11-30|95.00`.
- **New offers still count:** a changed amount (10, 10, 12, 12 → counts 1, 1, 2, 2; the limit closes the product on the first different offer, repeats do not add); a changed date (`2026-11-30`, same, `2026-12-01` → 1, 1, 2). The same amount written as `10`, `"10"`, `"10.0"`, `10.0` is one offer. The same day written in another form now matches too, since the day is compared as an ISO date, not text.
- **Dropped the amount kind from the signature:** acceptable. The kind only matters through the amount it resolves to (floor vs full), and that is in the signature.
- The sentinel is still written after each check (`offer_amount` = -1.0), so the platform rejection stays fixed; the earlier leak answers (nothing reaches the customer, a prompt, a summary or `create_promise`) are unchanged.

F-060: fixed offline, retest pending (the three live checks in my first review).
