# T-005e — Make the promise path work (chat test version 8)

**Owner:** codex-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

## Why

Chat tests on version 8 (PUB-01 happy path, PUB-07) reached negotiation and broke there. No case can record a promise until these are fixed. Read `docs/UAT-FINDINGS.md` **F-025..F-031** first: each entry has the observed symptom, the cause and the expected fix. Then read `AGENTS.md`, `tasks/T-005b-report.md`, `tasks/T-005d-report.md`, `builder/workflow.py`, `builder/offer_check.py`, `builder/spec.py`, `builder/prompts.py`, `build-the-builder-v2/docs/workflow-format.md` (extraction, date placeholders) and `tools-and-code.md` (variables in code).

The code was written by claude-dev while you were away (T-005a..d). Keep its design; fix the faults.

## Fix

1. **F-028 Products from flattened variables (highest priority).** In code `vars` the account result is flattened: `account_response.data.products.0.product_id`, `.past_due`, ... (observed, version 8). Rebuild the product list from `<node>_response.data.<list>.<i>.<field>` keys; keep the list and JSON-string forms as fallbacks. Apply the same reader to every code step and hook that reads a tool result (offer setup, product-number hook, promise progress, special paths). With exactly one product the product choice defaults to it.
2. **F-026 "Today" is the call's date.** The extractor resolved "today" with the real clock. Business logic must use the call's `now` variable (name from the spec, fallback to the system date only if absent). Choose one: give the extractor the computed call date (`today_text`) in the field description so it resolves relative dates against it, or extract the phrase and resolve it in code from `now`. Weekday names ("Monday the 26th", "this Friday", "the week after next") must resolve correctly relative to `now`.
3. **F-027 Amount words.** "The full amount", "the minimum", "the instalment" become numbers: extract an amount kind (full / minimum / other, generic names) next to the number, and let the offer code fill the number from the product facts. Which product field is "full" or "minimum" comes from the spec's offer rules.
4. **F-030 Honesty.** No step without the promise tool may say a payment, promise, note or callback was recorded. Only after the tool returned `ok` true. `negotiate` must voice `offer_message` when the verdict is not `ok`. Generic wording in `prompts.py`.
5. **F-029 Refusal.** Precise description of the negotiation intent values: `refusal` only when the customer refuses any payment or arrangement after being asked for alternatives. "Not today", "not now", "I don't know when" are not refusals; the agent asks for another date. Consider requiring one counter-question before a refusal can close (spec-driven if the brief says so).
6. **F-025 Internal ids.** The facts text for the customer never contains internal ids; refer to products by type and the spec's customer-facing label. Generic rule in the prompt: never read internal ids aloud.
7. **F-031 Closing runs again after the call ended.** If a close was already recorded (`close_call_ok` true), the closing chain skips `close_call` and goes straight to `end_call`, same guard as the hang-up hook.

## Tests (offline)

- Code steps fed with the **flattened** variable shape copied from the observed call (one, two and three products) produce the right facts, verdicts and product ids.
- Date resolution table with `now` = a fixed date: today, tomorrow, this Friday, next Monday, "the week after next" + a weekday, an explicit date, a date that is a holiday.
- Amount kinds map to the right numbers per fixture.
- `negotiate` prompt contains the no-claim rule and voices the verdict; refusal description present; no ids in facts.
- Closing chain with `close_call_ok` true goes to `end_call` without a second call.
- Existing tests green; leakage scan green; prompt budget ≤ 1,500; `docs/PROMPTS.md` regenerated.

## Constraints

Python 3.10+, stdlib only. No Freya requests (CTO runs the chat retest with user approval). No commit. No `env.sh`. No brief values in `builder/`. Update F-025..F-031 status in `docs/UAT-FINDINGS.md`. Report in `tasks/T-005e-report.md`: what changed per finding, the date-resolution choice, open questions.
