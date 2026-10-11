# F-065 review (claude-dev): reachable outcome rows, quoted speech, tool-failure row, spec copy

**Reviewer:** claude-reviewer · **Scope:** `extract.py` (`reach_soft`, the reach check in `_cross_group_checks`), `workflow.py` (`unreachable_outcomes`, `clean` in `speakable_spec`, `close_table` row for `special_tool_failed`), `spoken.py` (`quoted_speech`), `build.py` (`spec_copy`), `tests/test_outcome_reach.py`, `tests/test_extract.py`, fixtures.
**Method:** offline. Ran `unreachable_outcomes` on every spec in `tests/fixtures/**` and `traces/*.json` (26 specs); fed 12 plausible instruction lines to `quoted_speech`; ran `quoted_speech` over every outcome/path line of all those specs; read the Brief B text (rules 8–11, 23); checked `submission_check.py`'s spec-path logic and the new trace line; deleted the `promise_failed` row to see the new `close_table` row's failure mode. `python3 -m unittest`: 431 OK (test_extract + test_outcome_reach + test_multi_step re-run: OK). No Freya, no model, no edits.

## Decision: **düzeltme gerekli** (one MEDIUM: `quoted_speech` can turn a quoted *non-speech* word into a spoken sentence; the reach check, the tool-failure row and the spec copy are sound)

## 1. Reach check and `then=return`

- **Is "a returning path counts" right for Brief B?** Yes. Brief B rule 9: "A dispute or an 'already paid' claim on one product does not end the call. Note it and continue." If these rows went to repair, the model would have a reason to make the paths `then=close`, which would end a multi-product call on one product. Rule 23 (no promise: all products `paid` → `paid`, otherwise the reason of the first non-paid note) is what really reaches those rows, and that is AB-FRESH risk 5, still open: the closing cannot derive the outcome from notes. The render warning `only a special path that returns names it` is the right way to keep that gap visible. **Please keep risk 5 on the list:** a hidden Brief B case where every product is "already paid" would close as the default row today.
- **False positives on working specs:** none on any spec that is known to be good. Results on the 26 specs: no warning on Brief A reference, v11, `spec-brief-a`, synthetic, rep1, rep2, f040 A/raw/changed, f041-raw, t006 A/B, t006b. The returning-path warning (`paid`, `no_promise/dispute`) appears on the five A+B specs and on `spec-brief-b`, as the report says. Real gaps found by the check: `traces/brief-a.spec.json` (13:00), **`traces/f041-a.spec.json`** and `traces/f041-changed.spec.json` — all three lack any state or path for the hardship-declined ending (`no_promise/hardship`). So the check would have caught a gap two earlier live runs also had, and no good spec is sent to repair. In the extraction check the same rule applies (`states` on the row, `route end` in opening/third_party/negotiation, any special path with that pair), so the render result is the right proxy.
- **LOW 1 — a returning path with no tool can mask a real gap.** The extraction check counts *any* special path with the row's outcome/reason, returning or closing. The question paths (`scam_question`, `robot_question`) return with outcome `no_promise/refused`; if a table row had that pair and nothing else, it would count as reached. Narrow it: a returning path counts only when it has a tool (the per-product note, `add_note` in every Brief B spec: `already_paid`, `dispute`, `product_paid`, `product_dispute`). Brief B stays unaffected, question paths no longer mask.
- **LOW 2 — cost of a false alarm.** An error goes to repair for up to `MAX_REPAIR_ROUNDS` and only the last round is a warning. A hidden brief with a table row that no text can reach would spend two repair calls of the 30-minute budget before becoming a warning, and the repair prompt invites the model to invent a path or to delete the row. I found no such spec in the repo, so this is a risk note; make sure a deleted-row repair is rejected (coverage/row checks) and watch `extract_seconds` on the next live run.
- **Known limit (the report's):** cross-group checks run only when all groups pass on their own; agree with the proposal to run the reach check when other groups fail.

## 2. `quoted_speech` — MEDIUM: quoted words that are not speech

`quoted_speech` keeps every quoted part of an instruction unless that part itself reads like an instruction. It does not check *why* the words are quoted. I ran these:

| Instruction line | Result spoken |
|---|---|
| `Say that payments can take one business day to appear; close as "paid".` | **`paid.`** |
| `If the customer says "I already paid", say that payments can take one business day.` | **`I already paid.`** (the customer's words, said by the agent) |
| `Tell the customer to use the mobile app, then close as no_promise / "refused".` | **`refused.`** |
| `Close with outcome "promise" and thank the customer.` | **`promise.`** |
| `Do not say "payment" or "debt" before verification; thank the customer and say goodbye.` | **`payment. debt.`** (forbidden words, spoken) |
| `Never say "debt". Say goodbye.` | **`debt.`** |
| `Thank the customer for "their time" and say goodbye.` | `their time.` |
| `Say "Is this a scam?" is answered by phoning the bank.` | `Is this a scam?` |

Then `clean` puts that in place of the whole line and appends the goodbye ("paid. Thank you for your time. Goodbye."). On a pre-verification line or a third party, "payment. debt." is a policy breach; "I already paid." is a nonsense sentence; and the previous fallback (goodbye only) was safe. This code runs in the last extraction round and with `--spec`, i.e. exactly when the model failed to write a spoken sentence, so such instruction lines are the likely input.

On the real specs in the repo the function is right (all 8 quoted lines found are real sentences: the text-message line, "I am sorry for your loss."), and unquoted ones return "" as designed. The risk is the model's next phrasing.

**Fix (any of these, together is best):**
1. Keep a quote only when a speech verb introduces it directly: `^\s*(say|tell [a-z ]{1,20}|read|state|answer)\b[^"“]{0,12}:?\s*["“]` immediately before the quote, and not when the verb is preceded by a negation (`do not`, `never`, `don't`, `must not`) or by `if/when ... says`.
2. Require at least three words or a closing `.!?` inside the quote; reject a quote that is a single word or equals an outcome name, reason, state or value of the spec (`snake_case` or any outcome/reason string) or an enum value.
3. If the line has more than one quoted part, keep them only when each passes the same test; otherwise return "" (the safe fallback).
4. Tests with the eight lines above; each must give the plain goodbye.

**LOW 3 — `Say: <text>` without quotes.** A line such as `Say: A confirmation letter will be sent to your home address.` (seen in `f040-changed`) loses its sentence and gets only the goodbye. The text after `Say:` is literal, so it can be kept safely when the colon follows the verb directly and the sentence is not itself directed at the agent. Optional; the extraction check still sends such lines to repair in the earlier rounds.

## 3. `special_tool_failed` row

Correct and small: `close_table` adds a row with the promise-failure row's outcome/reason (`no_promise/service_error`) only when no row maps the state, before `default`, with an empty sentence so the closing says the builder's failure line and the goodbye (test: rep2 gives `no_promise/service_error`, not `refused`). A row mapped by the spec still wins (test). `promise_failed` is a required state (`spec.py:388,402`), so the `next(...)` cannot raise. A recorded promise still wins when the failed tool came later, through the row's `wins_over_promise`, as for any row.

## 4. Spec copy per run

`traces/<slot>.<start_utc stamp>.spec.json` is written right after the main file, with the same text, and the trace has `spec_copy: …`. The stamp is built from the trace's `start_utc` (digits only; works with `+00:00`, fractions and `Z`). `submission_check.py` reads the last `spec:` value and compares it with the `--spec` argument, so the new `spec_copy` key does not interfere (tests pass). A failed extraction writes only `.spec.failed.json`. Notes: (a) the trace log itself is still one file per slot and is overwritten by the next run, so the copy outlives its trace; copy the log too, or name the log with the stamp; (b) `submission_check` could verify that the `spec_copy` file exists and equals the main spec (cheap, LOW).

## 5. No brief value

The added builder strings are generic ("no call-end state, routed value or special path …", "unreachable_outcome …"); my grep of the added lines in `builder/` for the brief's words (hardship, paid, dispute, deceased, loss, Brief) found only the `reach_soft` argument line. The brief words occur only in tests and fixtures.

## 6. Live checks (with approval)

A fresh Brief A extraction (the reach check should not fire on a good result; if it fires, look at `extract_issue … never end this way` and whether repair adds a path rather than deleting the row), a fresh A+B extraction (only the `returns` warnings), and PUB-05 chat on the result. The quoted-speech path needs no live run once finding 2 is fixed.


---

## Re-review (Fix: `quoted_speech`, returning paths with a tool, reach check while other groups fail)

**Method:** offline. Ran `quoted_speech` on my 12 earlier lines and 14 new adversarial ones (with a reserved set of outcome/reason names), ran it over every quoted outcome line of all 26 repo specs with their real reserved values, re-ran `unreachable_outcomes` on every spec, and read `_check_reach` and the new call site in `extract_spec`. `python3 -m unittest`: **437 OK**. No Freya, no model, no edits.

### Decision: **merge edilebilir** (one LOW note on the extraction side)

### `quoted_speech` — the MEDIUM is fixed

All 12 lines from the first review now give `""` (goodbye only) except the one that is real speech:

| Line | Before | Now |
|---|---|---|
| `…close as "paid".` | `paid.` | `""` |
| `If the customer says "I already paid", say that payments…` | `I already paid.` | `""` |
| `…no_promise / "refused".` | `refused.` | `""` |
| `Close with outcome "promise"…` | `promise.` | `""` |
| `Do not say "payment" or "debt" before verification…` | `payment. debt.` | `""` |
| `Never say "debt". Say goodbye.` | `debt.` | `""` |
| `Say "Is this a scam?" is answered by phoning the bank.` | `Is this a scam?` | `""` |
| `Say "You will receive a text message confirming this promise." Then thank…` | kept | **kept** |

Adversarial lines also give `""`: customer quotes before a real `say "…"` (`If the customer says "…", say "…"` — the line has two quotes and one fails, so the whole line falls back), `When the customer asks "who are you", tell them "…"`, `Do not tell them "…". Say "Thank you for your time."`, a one-word `Say "paid"`, `Answer "yes"`, `Say, "…"` (comma), `Say hello and read "…" aloud` (the verb is not directly before the quote), a negated verb with `No, do not say "…"`, and a quote that is itself an instruction (`Say "Do not worry about this."`). `Say: “I am sorry for your loss.” Ask nothing else.` and `Say "Your account number is 12345678." Then goodbye.` are kept, correctly. The rule is strict on purpose: when in doubt the safe fallback is spoken, which loses a sentence at worst but never invents one. On the real specs, 14 quoted outcome lines (rep2, the A+B extractions, f040, f041, rep2) give exactly the two real sentences ("You will receive a text message confirming this promise.", "I am sorry for your loss."). `reserved` (outcomes, reasons, call-end states, routed values) is built in `speakable_spec`.

### LOW 1 — returning path with a tool: fixed

Both places (`_check_reach` in extraction and `unreachable_outcomes` at render) count a returning path only when it has a tool. A question path (no tool) with the hardship pair no longer masks the row (tests exist). The Brief B specs keep the `only a special path that returns names it` warning for `paid` and `no_promise/dispute` (re-run on the five A+B specs, `spec-brief-b`, `f040-b`: same two lines); the 13:00, f041-a and f041-changed specs still warn that hardship cannot be reached. No spec that was fine before warns now.

### Reach check while other groups fail

`_check_reach` is defensive (every access goes through `part(...)`/`items(...)`, no key error on a broken reply), runs only when all replies parsed and at least one group fails, sends its errors to the owning group (outcomes), and is soft in the last round. The test (offer group broken plus the 13:00 outcomes → two errors in round 0) shows the benefit.

**LOW 2 (new, extraction): the check can blame a good group for a broken feeder.** The check reads the opening, third-party and negotiation `route end` entries. If one of those groups (`opening_identity`, `flow`) is the one that failed, its broken or empty entries make a row that it normally reaches look unreachable, so the *outcomes* group is sent to repair for a row it got right (a wasted call, and a repair that may add an invented state or path). Suggested guard: in the "other groups fail" branch, skip the routed-value part (or the whole check) when `opening_identity` or `flow` is in `failing`; run it fully only when the failing groups are not feeders (as in the report's example, `offer`). It does not change the all-groups-pass path.

### Other notes from the report

- `SPECIAL_THEN_CLOSE` in `spec.py` keeps the literal `"close"` out of `extract.py` for the leak test; fine.
- The changed assertion in `test_broken_section_is_repaired_with_only_its_errors` (errors 2 instead of 1) is explained by the new reach error; consistent with LOW 2 only if `identity_failed` is the removed state of a feeder-free group, which it is here (the states live in the outcomes group).
- `Say: <text>` without quotes, a per-run trace log name and a `submission_check` test for the `spec_copy` file are not done; all were LOW and optional.
- AB-FRESH risk 5 stays open (closing does not derive the outcome from the notes); the render warning keeps it visible.
