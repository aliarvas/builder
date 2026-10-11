# F-064 review — third-party close guard (Codex)

**Reviewer:** claude-reviewer · **Scope:** `builder/callback.py` (`third_party_extraction_fields`, `third_party_close_guard_code/_node`), the wiring in `workflow.py` (third-party transitions, `third_party_ask` now built always), `prompts.py` (three new entries), `tests/test_callback.py`.
**Method:** offline. Rendered the workflow from `tests/fixtures` specs (A fixture and the fresh A+B v2 spec), listed the nodes and routes, ran the guard code with synthetic `vars`, read the rendered extraction texts. `python3 -m unittest tests.test_callback`: 41 OK. No Freya, no model, no edits.

## Decision: **düzeltme gerekli** (one MEDIUM prompt problem that can break the wrong-number / deceased paths; the mechanism itself is sound)

## What I checked

| Criterion | Result |
|---|---|
| Live sentence "I can pay it myself if you tell me the amount" does not close | Mechanism works: if the model still writes a closing value, `kind` is `other` (the intent description and the kind description both give this sentence as the `other` example), so the guard resets the intent to `none`, speaks the fixed re-ask and counts. The model cannot be forced by code to write `other`; that depends on the extraction. The two-field design (intent + independent kind) is the right defence, because both would have to be wrong the same way. |
| Explicit refusal closes at once | `kind = explicit_close` → verdict `close_now`, intent untouched, count not written, route `closing`. Tested ("she doesn't want to be called"). |
| Loop bounded | Count is written only by the guard, never reset; the second closing intent always closes (`count < 1` fails). An exception inside the guard also writes count 1 and re-asks once, so it cannot loop. Worst case: one extra fixed line per call. Same bounded pattern as the callback counters. |
| No debt disclosed to the third party | The fixed line is "I cannot discuss account or payment details. When can the customer be reached?": no amount, no product, no reason for the call. The third-party step's own prompt is unchanged (rules from the brief). |
| F-053 dead air | The re-ask path is third_party (extraction) → silent code step → `third_party_ask` (tts `{{callback_message}}`) → user. One speaking step per customer turn; `third_party_ask` is a copy of `third_party` (same routes and extraction incl. the kind field), so a customer reply is handled the same way and a `__previous__` return replays the pending question (the `offer_say` pattern). The close check has `on_enter` silent and an `always` fallback. |
| F-050 / format | No tts on an api step; code step transitions: one per target, `or` with nested conditions, `always` last, no null. The new node name is in the `used` set, so no variable/node collision. |
| Brief values | None in code. Close values come from the spec (`third_party.close_values`); the new texts name no brief rule. The two example sentences in the kind description are generic test phrases, not brief values. |
| `third_party_ask` built always | Before, it existed only with the callback tool. Now it exists whenever the third party has close values; with no callback tool it has no `callback_check` transition, only the closing routes, which is correct. |

## Findings

### 1. MEDIUM — `wrong_number` and `deceased`-type close values may be pushed into the re-ask (`prompts.py:171-185`)

In the A fixture and in the fresh A+B spec the close values are `no_callback`, `wrong_number`, `deceased`. The guard treats **every** close value the same: it needs `kind == explicit_close`. The kind description defines that as "an explicit refusal or a clear statement that the customer cannot be reached". "This is not her number" and "she passed away" are neither a refusal nor obviously "cannot be reached"; a model may well answer `other`. Then the agent says "I cannot discuss account or payment details. When can the customer be reached?" to someone who just said the customer died, against the brief rule (say a condolence line, ask nothing else, close as deceased) and with one wasted turn on wrong numbers. The intent description has the same narrowing ("choose a closing value only when the person explicitly refuses a callback or clearly says the customer cannot be reached"), so the model may also pick `none` for these and never reach the guard at all.

**Fix (no brief value needed):** make both texts talk about the spec's own closing values instead of only "refusal / unreachable":
- Intent: "Closing values are: {close_values}. Choose one when the person's message states the situation that value names; a question, an offer to pay or a request for account information is not one: choose none …".
- Kind: pass `{close_values}` here too: "explicit_close: the person clearly states a situation named by one of {close_values} (for example a refusal of a callback, or that the customer cannot be reached) …; other: every question, offer to pay, request for information, vague reply or non-answer".
- Test: render with the A+B spec and assert the kind description contains each close value; add a unit check that the examples are still there. Live (chat, with approval): one run per close value (wrong number, deceased, refusal, the live "I can pay it myself" sentence) and see that the first three close in one turn and the fourth gets the re-ask once.

### 2. LOW — the second turn closes even if it is still a question

By design (bound) a second closing intent closes regardless of `kind`. If the customer repeats the payment offer twice, the call ends as a close value (for example no callback) without a model reply. Acceptable for the bound; say so in `docs/COLLECTIONS-POLICY` or the UAT entry so nobody expects "never closes on a question". A cheaper variant would be one more re-ask, not needed.

### 3. LOW — a stale `kind` value

`third_party_close_kind` is not reset after an explicit-but-ignored turn (for example `explicit_close` written on a turn whose intent was `callback`). If a later turn has a closing intent and the kind extraction is below the confidence threshold, the old `explicit_close` lets it close at once. The guard resets the kind only on the re-ask path. Cheap fix: in the `close_now` branch and in the non-close case clear it to `other` (valid enum value, not an empty string) when the intent is not a close value. Low because it needs two odd extractions in a row.

### 4. LOW — the fixed re-ask line is English text, like the other fixed lines

`THIRD_PARTY_CLOSE_REASK_SAY` is a fixed English sentence in `prompts.py`, consistent with the other `*_SAY` lines. If a hidden brief is in another language the line would be in the wrong language; this applies to every fixed line, so it is a project-wide question, not F-064. Note only.

### 5. Tests

The new tests exercise the guard code and the rendered descriptions, not the routed walk. Please add one `Session`-style walk (third_party → check → ask → customer explicit refusal → closing; and second non-explicit close → closing) to prove the routes, not only the code string. The terminal-path fixtures that carry the new signal are fine.

## Live retest (CTO)

Chat first, one run each: the live sentence, an explicit refusal, wrong number, deceased, a callback time inside the window, then a repeated payment offer (expect one re-ask then close). Check the third party never hears an amount or a product. UAT F-064: "fixed offline for the question/offer case; wrong-number and deceased wording needs finding 1 before the retest".

## Not reviewed

T-009d (budget in `workflow.py`) and the AB-FRESH changes (reviewed separately in `reviews/AB-FRESH-review.md`).


---

## Re-review (Fix: findings 1–3, new route walker)

**Method:** offline. Read the rendered extraction texts, the new guard code and the third-party routes, and walked eight turn sequences through the test `ThirdPartySession` (and `callback_check` where it applies). `python3 -m unittest`: 394 OK. No Freya, no model, no edits.

### Decision: **düzeltme gerekli** (one MEDIUM regression introduced by the stale-kind fix; finding 1 is fixed)

### Finding 1 (wrong number / deceased) — fixed

Both descriptions now carry the spec's own closing values ("Closing values are: no_callback, wrong_number, deceased. Choose one when the message clearly states the situation that value names" and the same list in the kind text), with the question / payment-offer / information-request cases still `none` / `other`. Walks with the guard:

| Turn(s) (intent, kind) | Route | Result |
|---|---|---|
| no_callback, explicit_close | check → closing | closes at once, kind cleared |
| deceased, explicit_close | check → closing | closes on the first turn |
| no_callback, other (the live sentence) | check → third_party_ask | one fixed re-ask, count 1, intent reset to `none` |
| same twice | re-ask, then closing | bounded: second time closes |
| re-ask, then no_callback explicit_close | closing | OK |

A deceased/wrong-number message that the kind model still labels `other` gets the re-ask once; that is now only a classification risk of the model, with the right wording given. Keep it in the live checks.

### New route (stale kind) — MEDIUM regression

The fix adds `third_party_close_kind == explicit_close` as one more condition of the transition `third_party → third_party_close_check`. Transitions to the same target are merged, so this condition sits **before** the `callback_check` transition (order in the node: closing, close check, callback check). The new `else` branch of the guard returns the verdict `return_to_third_party` and routes back to `third_party`.

Walk: intent `callback`, day "tomorrow", time "3pm", kind `explicit_close` → `third_party_close_check` → back to `third_party`; `callback_check` is **not run** that turn, so nothing is booked, and the step is entered again, where the model speaks (it has no tool and no booking). The booking happens only at the next customer turn, if the day/time fields are still set. This misfire is easy to get: the kind description names "the customer cannot be reached" as an `explicit_close` example, and a typical callback reply ("she is not in right now, call tomorrow at three") says exactly that. The old flow booked the same turn.

(The other stale case works: intent `none` with a stale `explicit_close` → guard clears it and returns to `third_party`; this one speaks once, so there is no dead air or loop, since the kind is reset to `other` and the same data cannot return again.)

**Fix (one of):**
- put the stale-clear clause only when no callback day/time is set: condition `kind == explicit_close AND day_text empty AND time_text empty` (the callback fields are cleared by `callback_check`, which already resets the kind); or
- drop the stale-clear transition and reset the kind where the third-party step is entered or after the callback is checked (it is already reset in `callback_check`); the guard alone then handles the close cases; or
- remove `cannot be reached` from the kind examples when the spec has a callback tool, so a callback reply is not labelled explicit.
Add a walk test: `callback` + day + time + `explicit_close` must reach `callback_check` and book.

### Finding 3 and the walker

The stale kind is also cleared on `close_now` and in `callback_check`; the test walker is a real route walk now (it caught nothing wrong in the paths it covers, but it does not cover the case above). Findings 2 and 4 are accepted as intentional (bounded fallback; one English fixed line like the others).

### Live checks (with approval)

The live sentence; an explicit refusal; wrong number; deceased; **"call me tomorrow at three, she is out now"** (must book in the same turn); a repeated payment offer (one re-ask, then close).


---

## Re-review 2 (Fix 2: stale-kind transition removed)

**Method:** offline. Read the rendered third-party routes and walked eight sequences through `ThirdPartySession`. `python3 -m unittest`: **401 OK** now (the three `test_prompt_budget` failures in the developer's run were T-009d work in progress and are gone). No Freya, no model, no edits.

### Decision: **merge edilebilir** (one LOW note)

- **Regression fixed.** `third_party` now has three transitions: closing (callback done or failed), `third_party_close_check` (only the spec's closing values), `callback_check`. The guard node has two exits (`close_now` → closing, otherwise `third_party_ask`); the `return_to_third_party` branch is gone from the routes.
- **Walks**

  | Turns (intent, kind) | Route | Result |
  |---|---|---|
  | callback + "tomorrow" + "3pm", kind `explicit_close` | third_party → callback_check → callback_book | booked in the same turn: 2026-10-15 15:00, kind cleared |
  | same with kind `other` | same | same |
  | day only, then time | callback_check → ask for the time → callback_check → book | OK |
  | no_callback, explicit_close | check → closing | closes at once |
  | deceased, explicit_close | check → closing | closes on the first turn |
  | no_callback, other twice (live sentence) | check → third_party_ask (one fixed re-ask) → check → closing | bounded |
  | none + stale explicit_close | stays in third_party | no dead air, no loop |

- **LOW (accepted):** a stale `explicit_close` stays in the variable after a non-closing turn, and the next closing intent whose kind extraction is below the confidence threshold would then close without the re-ask. It needs two unusual extractions in a row and the effect is the spec's own close value; I withdraw the finding as a blocker. A one-line clear in the step that writes it would remove it, if wanted later.
- Findings 1, 2, 4 and the live checks from the earlier sections stand. Live list unchanged, including "call me tomorrow at three, she is out now" (must book in the same turn).
