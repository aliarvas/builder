# F-061 / F-062 review — per-product refusal and code-owned notes

**Reviewer:** claude-reviewer · **Scope:** `builder/product_notes.py` (new), `offer_check.py` (`PRODUCT_REFUSAL_BODY`, `NOTE_NEXT_BODY`, state names), `spec.py` (`product_end_values`, `attempt_values`, `persuasion_attempts`, `closing.product_notes`), `extract.py` + prompts for the new fields, the hooks in `workflow.py`, `tests/test_product_notes.py`, `tests/test_multi_ready.py`. The F-063 record loop was read only where the note loop touches it.
**Method:** offline. I rendered A, B, the version 11 extraction and the tagged A+B extraction and compared the graphs; read both generated code bodies; drove the real code with the `Session` simulator from `test_multi_ready.py` in scenarios the tests do not cover (a failing second product with a third accepted, failing note calls, every product refused); read the brief's rules 9–11, 30–31 and the Brief B notes rules; checked the extraction validators and the leak allowance. `python3 -m unittest`: 373 OK. No Freya, no model, no edits.

## Decision: **düzeltme gerekli** (one MEDIUM wrong-label bug in the ledger, two MEDIUM robustness points; the design, the loop bounds, F-050, the transfer skip and the old-spec behaviour are right)

## Findings

### 1. MEDIUM — a product the customer accepted but the record loop never reached is noted `refused` (`NOTE_NEXT_BODY`, with the F-063 stop rule)

The F-063 loop stops at the first product whose attempts are used up. `note_next` gives `failed_reason` only when **that** product's own attempts reached the limit; every other unrecorded product gets the call's reason or `refused_reason`. Reproduced on the tagged A+B spec and on fixture B: three products accepted, product 2 fails twice, product 3 is never tried → notes `p2 service_error`, **`p3 refused`**. The customer never refused product 3; the ledger says so, and the report itself lists it (open note 5). For the brief's rule 11 ("keep the promises that were recorded and note `service_error` for the failed product") the extra `refused` note is a wrong statement in the bank's record, and it will fail the outcome check of any such hidden case.
**Fix (either):** in `note_next`, an accepted-but-unrecorded product gets `failed_reason` (the promise was agreed and not recorded), or let the record loop continue past an exhausted product so product 3 is recorded (the brief says to keep trying the others; the cost is a longer chain). The second is closer to the brief. Add a test with the sequence above.

### 2. MEDIUM — a render-time `SpecError` in the optional note feature fails the whole build (`note_tool`)

`note_tool` raises `SpecError` when the note tool is missing, a field is not in its body, a reason is not in the enum, or the tool needs a required field that no code value fills. In the extraction step this goes to the repair turn, which is good, but after the repair rounds a build with an optional feature that cannot be rendered stops entirely (no workflow for that brief), where the old behaviour for such a spec was "no notes". The kit's tool has `text` optional, so Brief B renders; a hidden tool API with a required free-text field on `add_note` would fail the build. **Fix:** after the repair rounds, or when the final render raises for `closing.product_notes` / `persuasion_attempts`, drop the optional block with a trace `warning` and build without it, as the code does for the callback tool without date and time fields (F-055).

### 3. MEDIUM — `persuasion_attempts` numbers are not checked against the documents (`extract.py`)

`product_end` / `attempt` flags and the note rule have shape and source checks (`check.excerpt`, tool fields, enum), but the attempt counts (`value` per band) have no evidence check. A wrong number (say a copy of the invalid-offer limit, which the prompt warns about) changes how many times the agent persuades, and nothing catches it. Add an evidence check like the other numbers (the value must appear in the documents as a digit or a word, or be derived with a `source` excerpt), and a `source` field for the whole list.

### 4. LOW-MEDIUM — product choice by account order, not by what the customer discusses (`PRODUCT_REFUSAL_BODY`)

The refused product is "the first product in account order not yet handled". The agent presents products in that order and `more` follows it, so this fits the normal path. If the customer jumps ("the car loan is the one I cannot pay"), the first unhandled product is marked refused. `offer_product_number` (set by extraction) is available and could take precedence when it names an unhandled product. Record it as a known limit if not changed.

### 5. LOW — a product with no matching persuasion rule never closes by count

If `persuasion_attempts` has no `when` that matches the product (a band gap), `rule` is `None`, the state stays `persuade`, and the model persuades without end until `close_turn_limit`. Treat "no matching rule" as "no attempts left" (end the product) or as the last rule's value.

### 6. LOW — what changes for Brief A on a fresh extraction

Fixture A and the version 11 extraction render with no new node and identical `negotiate` routes (`check_offer`, `confirm_record`, `closing`; `closing` → `closing_say`), so today's Brief A is unchanged. The report's risk 4 is real: a fresh Brief A extraction can now fill `persuasion_attempts` (the brief's table gives 1 and 2) and the `per_product` / `uses_attempt` flags, which makes code count the attempts on a single product. The outcome should stay `no_promise/refused`, but the persuasion mechanics change, so PUB-04–06 style refusals need a live retest after the first fresh extraction (the report asks for the fresh extraction anyway).

### 7. LOW — budget and long chain

`negotiate` on the tagged A+B spec is now 1627 tokens (above the 1500 limit; shipped with the warning, not a block). The note loop adds up to two steps per unnoted product to the closing chain (three products: six steps, plus retries) before `closing_say`; every step is silent, so one spoken message holds, but the chain length is live-unproven like the F-063 one. Add it to the open live checks.

## Verified

- **Brief A unchanged / old behaviour without the fields.** New nodes exist only when the spec asks (`product_refusal`, `note_next`, `note_record` appear on fixture B and the tagged extraction only). Fixture A, the version 11 extraction and (by the test) the old live A+B specs keep the old routes and `closing` → `closing_say`.
- **No brief value in code or prompts.** The code and the prompts contain no reason, outcome or tool-name literal for the notes (I grepped `product_notes.py`, `offer_check.py`, `spec.py`, `record_loop.py` for the Brief B reason words and `add_note`; none). The `"type"` allowance in the leak test is justified: `product_notes.py` writes the Freya entry keyword `{"type": "silent"}` (the same literal `workflow.py` uses), the literal clashes only because "type" is also a product field name in the fixtures, and the allowance is file-scoped to this one module. (`record_loop.py` avoided the literal with `dict(type=…)`; either is fine; keep the allowance scoped.)
- **Per-product refusal.** `negotiate` and both twins carry one `product_refusal` transition after `check_offer` (a date or an amount in the same message still goes to the check first, matching rule 29); no duplicate targets. `product_refusal` counts one attempt per refusal while attempts remain; the next refusal ends the product, which reproduces rules 30–31 (early band: one attempt then close; late band: two attempts, then close). The ended product is marked `refused` in `offers_noted`; the next product's line, the read-back (offers accepted) or the closing (`negotiation:<value>`, intent kept for the close rule) follow. An exception falls back to `persuade` and still resets the intent, so no same-turn loop. The state per product is kept in `persuasion_used`; the model sees the count (`PERSUASION_STATE_LINE`).
- **Note loop and bounds.** `closing` → `note_next` (code) → `note_record` (silent passthrough api step, `maxRetries 0`, node-level `data.ok` mapping) → `note_next` → … → `closing_say`. Each product is written once or given up after two failed sends, so the loop is at most twice the number of products. A tested note failure (two sends fail on product 2): the loop gives up on it, writes the others, and says nothing about notes. A transfer (`skip_outcomes`) writes none. A product already noted by a special path (`notes_written`) is not noted again; recorded products are skipped (`promises_recorded_numbers`). Identity failure, account failure and third-party calls have no products, so the loop does nothing there.
- **Reasons.** Order: attempts used up → `failed_reason` (own attempts); a reason chosen by code (`refused` on the invalid-offer limit or a refusal); the call's close reason when it is a listed note reason (so hardship notes the others `hardship`); else `refused_reason`. All-refused PUB-12-like call: `no_promise/refused`, notes `refused` for all three (3 calls). Promise on product 1 and refusals on 2 and 3: outcome `promise`, notes `refused` on 2 and 3, matching the case's `expected`.
- **F-050 / spoken output.** `note_record` is silent with no `tts`; the notes add no spoken step; `closing_say` is still the only one. The note tool body carries only `customer_id`, `product_id` (`{{note_product_id}}`) and `reason` (`{{note_reason}}`); the optional model field `text` is removed; the enum is kept. `[TO-CONFIRM]` live: an enum field with a template default (no live evidence yet; the promise record step has the same shape for an integer).
- **Honesty.** No spoken claim depends on a note. A failed note is never reported as written, and nothing is said about it.
- **Extraction validation.** Errors name their path and say what to fix (`closing.product_notes.reasons … is not in the add_note enum […]`, `negotiation.intents[i].per_product may be true only with route end`, `a uses_attempt value needs a per_product end value`, unknown skip outcomes list the table's outcomes, the source excerpt is required), so the repair turn gets usable messages. `spec.py` repeats the same rules for hand-written specs.
- **Interaction with F-063.** The note loop only reads `promises_recorded_numbers` and `promise_attempts_N`; it does not touch `confirm_record`, `record_next` or `confirmation_progress`. Finding 1 is the one place the two rules disagree.

## Brief B gap the report names (not a defect of this task)

Open note 7: with a dispute on product 1 and a refusal on product 2 and no promise, rule "close with the reason of the first product whose note is not `paid`" needs the closing row to read the note reasons; today the reason is `refused`. A fresh live case (PUB-13 style) can expose it; plan the small follow-up the report proposes.

## Live checks

Fresh A+B extraction (do the new fields appear with sources and sensible counts, and does Brief A still extract without them being forced), PUB-12 (notes `refused` on two products, promise on one), a record failure on one product of several (finding 1), a refusal after a persuasion attempt on the late band, and a transfer after a promise (no notes).


---

## Re-review (Fix 1–5, and the changed F-063 record loop)

**Method:** offline. I drove the real record loop, closing code and note loop with the `Session` simulator on the tagged A+B spec and on fixture B in six record-failure sequences each; rendered fixture B with five broken note blocks (tool missing, field missing, reason outside the enum, reason field missing) to check the drop path; read `confirmation_progress`, `record_next` and the evidence check. `python3 -m unittest`: 378 OK. No Freya, no model, no edits.

### Decision: **merge edilebilir**

### Finding 1 (wrong `refused` note) and the changed F-063 loop — fixed; the F-063 honesty and bound properties still hold

| Sequence (three products accepted) | Calls | Promises | Progress | Outcome | Notes | Closing starts |
|---|---|---|---|---|---|---|
| product 2 fails twice | p1, p2, p2, p3 | p1, p3 | exhausted | promise | **p2 service_error only** | "I am sorry, I could not record every promise." |
| product 1 fails twice | p1, p1, p2, p3 | p2, p3 | exhausted | promise | p1 service_error | same |
| product 3 (last) fails twice | p1, p2, p3, p3 | p1, p2 | exhausted | promise | p3 service_error | same |
| product 1 fails once, then ok | p1, p1, p2, p3 | all three | complete | promise | none | the spec's recorded sentence |
| product 2 fails once (ok on retry), product 3 fails twice | p1, p2, p2, p3, p3 | p1, p2 | exhausted | promise | p3 service_error | "…could not record every promise." |
| all fail | two calls each | none | exhausted | no_promise / service_error | service_error on all three | failure line |

Same results on both specs. No product is noted `refused` unless the customer refused it; a product the loop had not reached no longer exists, since every accepted product is now tried.
- **Bound:** a failing call counts against its product; at the limit the product goes into `promises_failed_numbers` and `record_next` skips it, so the loop makes at most (products × attempts) calls (six for three products), a retry takes the same product, and nothing returns to `confirm_record`. An exception while setting a product aside ends the loop as `exhausted` (honest).
- **Honesty:** the state is `complete` only when every accepted product is recorded; any failure makes it `exhausted`, so the closing never presents a partial result as complete; a recorded promise still wins the outcome row (rule: promise wins) and the failure line goes first; a total failure gives `no_promise/service_error`. The retry of a failed call is the same bounded rule as before.
- The brief's rule 11 is now followed (keep the recorded ones, note `service_error` only for the failed product, and keep trying the others).

### Finding 2 (a broken optional block fails the build) — fixed
Rendering with the note tool missing, a note field missing, a reason outside the tool's enum or a missing reason field no longer raises: the note nodes are not built, `closing` goes straight to `closing_say`, the per-product refusal step is still built, and the trace gets `warning: closing.product_notes dropped (F-061 not applied): …` naming the cause. In extraction the errors go to the repair turn first and the optional blocks (`product_notes`, `persuasion_attempts`, `intent_flags`) are dropped only in the last round, with an `extract_warning` line. Dropping the flags drops the attempts that depend on them. This is the right degradation.

### Finding 3 (persuasion numbers unchecked) — fixed
Each `value` must be a positive integer written in the documents as a digit, ordinal or word (`count_written`), the list needs a `sources["offer.persuasion_attempts"]` excerpt, and a list needs a `uses_attempt` intent. Honest limit: a small number such as 1 or 2 is written somewhere in nearly every brief, so the digit check alone is weak; the required excerpt is the real guard. No further action.

### Findings 4 and 5 — fixed
The refusal goes to the product named by `offer_product_number` when it names an unhandled product; if the named product is already handled, the first open product in account order is used (so a stale number cannot reopen a finished one). With no matching `persuasion_attempts` rule, the product closes on the first refusal instead of persuading without end. Both are tested.

### Live checks that remain
Fresh A+B extraction and a fresh Brief A extraction (the report's items 6, 7), PUB-12, a record failure on one product of three (calls p1, p2, p2, p3 and one `service_error` note), and the long silent chain (up to six record steps and six note steps before `closing_say`) completing without a 502 or rollback; an enum field with a template default (`reason`) in the note call. F-061/F-062: fixed offline, retest pending.
