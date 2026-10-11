# AB-FRESH follow-up review (F-061/062: risks 1, 3, 4 and the v2 fixture)

**Reviewer:** claude-reviewer · **Scope:** `offer_check.py` (`PRODUCT_REFUSAL_BODY`, `NOTE_NEXT_BODY`, `note_next_code`, the escape in the prelude), `product_notes.py` (new description, `FAILED_NUMBERS` passed on), `prompts.py` (`PRODUCT_END_COUNTED_DESCRIPTION` and the three entries added to `PROMPTS`), `tests/fixtures/extract/brief-ab-extracted-v2.json` and the new tests. I did not look at claude-dev2's T-009d (`workflow.py` budget) or codex-dev's F-064 (`callback.py`, third party).
**Method:** offline. Ran the `Session` simulator on the v2 and tagged specs for new sequences (below), read the rendered extraction description, compiled every `builder/`, `tests/` and `tools/` source with warnings as errors, ran `python3 -W error::SyntaxWarning -m unittest`: **391 tests OK** (the developers' last count was 385; the extra tests come from the F-064 work running in parallel). No Freya, no model, no edits.

> Disclosure: while checking that `docs/PROMPTS.md` is current I ran `python3 builder/prompts.py --check`. That command does not only check: it rewrote `docs/PROMPTS.md`. A test (`test_vertical_slice.py:653`) compares the file with the generated text and was green just before, so the content should be identical (only the modification time changed). I did not edit it by hand. Please run `git diff docs/PROMPTS.md` once; if the F-064 developer is still adding prompts, the file may now include their latest text.

## Decision: **merge edilebilir** (two LOW notes)

## Risk 1 — an end value uses an attempt while attempts are left: fixed

`PRODUCT_REFUSAL_BODY` now computes `counted = persuasion_attempts and (end or intent in attempt_values)`. For a counted turn it looks up the product's band rule: attempts left → counts one, `end = False`, back to `negotiate` with the intent reset to `none`; attempts used up → `end`. No matching band rule → the product ends (finding-5 behaviour kept). Without `persuasion_attempts` nothing changes (`counted` is false, `end` stays the plain intent test); a test covers fixture B.

Sequences I ran on **v2** and **tagged** (PUB-12 case: card, personal loan 16 days late = 2 attempts, car loan 7 days late = 1 attempt):

| Sequence | Steps after each turn (step, attempt) | Result |
|---|---|---|
| end value every turn, nothing accepted | (negotiate,1) (negotiate,2) (offer_say,0) (negotiate,1) (negotiate,2) (offer_say,0) (negotiate,1) (closing,1) | `no_promise/refused`; notes p1, p2, p3 `refused`; closing reads the end value |
| attempt value, end value, end value, attempt value, end value | (negotiate,1) (negotiate,2) (offer_say,0) (negotiate,1) (confirm_record,1) | mixed values count the same; the card's offer goes to the read-back |
| same, then the record call for the card fails twice | | `no_promise/service_error`; notes p1 `service_error`, p2 and p3 `refused` |

Attempt counts are per product (`persuasion_used` keyed by product number), restart at 0 for the next product, and the closing sets the intent to the first end value when the attempts ran out through an attempt value, so the outcome mapping still sees a refusal. The pre-existing "customer names another product" choice still works (the counter is stored under the product named).

`PRODUCT_END_COUNTED_DESCRIPTION` renders as intended, only when the spec has attempts. `spec.py:313` guarantees `attempt_values` is not empty in that case, so the text can never say "choose none".

## Risk 3 — `failed_reason` only after a record attempt: fixed

`NOTE_NEXT_BODY` gives `failed_reason` to an accepted product only if it is in `promises_failed_numbers` or `promise_attempts_N > 0`. Otherwise: reason marked by code, then close reason, then `refused_reason`. I checked the counter's life: it is written only in `confirmation_progress` (increment on a failed call, reset to 0 on success); a recorded product is skipped before the reason is chosen; an exhausted product is also in the failed list. So an accepted offer that was never sent (call closed first) now gets the close reason: the test runs card accepted + hardship declined and gets `hardship` ×3 (was `service_error` for the card). Record failures keep `service_error` (my table above and the existing F-063 sequences). Honesty is unchanged: the failure note is still never replaced by a refusal.

## Risk 4 — escape: fixed

`offer_check.py:285` now has `\\s`/`\\d` inside the non-raw prelude; the generated code still contains `r'^\s*-\s*\d'` (I checked the prelude text). All 41+ sources compile with warnings as errors, and the new test fails on the old line (the developer's claim; I verified the compile side, not the old line).

## v2 fixture and tests

- v2 is a fresh live A+B extraction copied unchanged. The leak test passed with it present (fixtures are test data, not builder strings).
- It was added to the PUB-11/12/13, record-loop and note tests; PUB-11 `220/640/75`, PUB-12 `p1 510` + refused notes, PUB-13 two promises: all pass (I ran PUB-12 myself above and the other two through the unit tests).
- `Session.end_product()` is a fair helper: it repeats the refusal only while the step stays on `negotiate`, bounded by 5.
- Persuasion test now reads the attempt value from the spec instead of a literal intent name. Good.

## Findings

### 1. LOW — the first sentence of the intent description still says "refuses any payment after being asked for alternatives"

Rendered text (v2): "Values refuses_after_attempts, refuses_to_talk mean the customer refuses any payment or arrangement after being asked for alternatives … Values refuses_after_attempts end only the product … while attempts are left, refuses_after_attempts also uses one attempt. For any no about the product being discussed, choose flat_refusal." The last two sentences correct the first, and the code no longer depends on the model's choice, so the live risk is small. The report notes the first sentence comes from `workflow.py` (T-009d area). When claude-dev2 is free, drop the end value from that first sentence when the spec has attempts (keep `refuses_to_talk`). Not blocking.

### 2. LOW — one `refuses_after_attempts` choice costs a full extra turn when the customer was in fact final

With a counted end value the agent persuades once more even if the customer said "I will never pay this" at the first turn. That matches the brief rule (attempts are mandatory before a refusal can be recorded) and the report's own risk 1 reasoning, so it is the right behaviour; I only note that PUB-12-style live chats will now show two or three persuasion messages per late product, and the 30-minute and per-turn time budgets in the live test should allow for it.

## Not reviewed, as asked

T-009d (negotiate budget; the report's risk 2 about duplicate rules and a rule that tells the model to call `add_note`) and F-064 (third-party closing). The report's risk 2 point that the negotiation rule "For each product that ends without a promise, call add_note…" is now redundant (negotiate has no tools) is correct and worth the dev2 fix, because the model could say "I will note it".

## Risk 5 (not implemented, proposal in the report)

Agree with not hardcoding it. The proposed optional `closing.product_notes.outcome_from_notes` block is the right shape (spec-driven, evidence, dropped with a warning like the other optional blocks); it needs the note loop to run before the outcome, so it should be reviewed as its own task. Until then the result is correct for PUB-12 only because both set-aside products carry the same reason.

## Live retest

PUB-12 on the fresh A+B build: the personal loan gets two persuasion messages, the car loan one, whatever value the model writes on the first "no"; notes p2, p3 `refused`. Add: PUB-11 with one record failure (p2) should still show p1/p3 promises and a single `service_error` note. UAT F-061/F-062: "fixed offline on the fresh spec, retest pending".
