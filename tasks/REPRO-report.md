# REPRO: Brief A extraction repeatability (SELF-TEST step 8)

No Freya, no model call, no commit, no env.sh. All comparisons are offline.

## Inputs

| Spec | Run | Prompts |
|---|---|---|
| `traces/rep1.spec.json` | 2026-10-10 23:13 | old (before F-055/F-061/F-062) |
| `traces/rep2.spec.json` | 2026-10-10 23:13 | old |
| `traces/brief-a.spec.json` | 2026-10-11 10:00 UTC (13:00 local) | current |
| (spec lost) | 2026-10-11 09:24 UTC (`traces/brief-a.log`) | current |

**The second fresh spec from today is lost.** Both of today's runs used the slot `brief-a`, so the 13:00 run overwrote the 12:24 spec. The 12:24 run can be compared only from its log (step list, rule_tiers).

**Commands:**
- `python3 tools/compare_spec.py A B` for each pair.
- `python3 builder/build.py brief-a.md openapi.json --print --spec <spec> --slot repro-<name>`, rendered with the current code. Traces: `traces/repro-{rep1,rep2,brief-a}.print.log`. The workflow JSONs are in the scratch folder.

## Unstable fields

| Field | rep1 | rep2 | brief-a 13:00 | 12:24 (log) | Effect |
|---|---|---|---|---|---|
| **special path `hardship_declined`** | yes | yes | **missing** | yes | **ledger (PUB-05)** |
| outcome / special `say` style | spoken lines | **instructions** ("Thank the customer and say goodbye.") | spoken lines | spoken (0 fallback) | judge (policy) |
| `special_tool_failed` state | service_error | **missing** → default refused | service_error | ? | ledger only if a transfer fails (no public case) |
| `turn_limit` state | refused | missing → default (refused) | refused | ? | none (same row) |
| refuses to talk | intent value | intent value | intent value | **special paths** `refuses_to_talk_verified/unverified` | same outcome expected; not checkable (spec lost) |
| `offer.persuasion_attempts`, `product_end_values` | none | none | present (1 / 2 by band) | ? | old prompts did not have the field; code or prompt counts |
| `third_party.callback_window` | none | none | present | ? | old prompts; with it, the callback is checked in code (F-055) |
| `confirmation.revise_values` | 1 | 2 (`rejects_readback` too) | 1 | ? | none (both go to revise) |
| `forbidden_before_verification` | 3 product names as words | one phrase "the product (…)" | phrase | ? | prompt only |
| robot question `available_in` | includes third_party | not | includes third_party | ? | small: answer to a third party |
| intent value names | refuses_after_attempts | refused_after_attempts / declines_to_talk | refuses_payment | — | none (routes use roles, not names) |
| identity `exhausted_say` | instruction | instruction | spoken line | — | the code speaks the line (F-047 check) |

**Unmapped:** 0 in all three specs (coverage added 2 rules on 12:24 and 1 on 13:00).

**Rule counts:**

| Section | rep1 | rep2 | brief-a |
|---|---|---|---|
| opening | 5 | 4 | 5 |
| third_party | 7 | 10 | 7 |
| identity | 8 | 10 | 8 |
| account | 4 | 4 | 4 |
| negotiation | 21 | 20 | 18 |
| confirmation | 11 | 9 | 8 |
| offer | 15 | 15 | 12 |
| closing | 3 | 4 | 3 |
| global_rules | 10 | 8 | 7 |

- The 12:24 and 13:00 runs both have 65 step_prompt rules and 7 global_prompt rules.
- Special paths in code: 11 (12:24) and 8 (13:00).
- negotiate estimate: rep1 ~1419, rep2 ~1494, brief-a ~1375 tokens (all under 1500).

## Effect on the render (current code)

- **Nodes:** 32+9 (rep1, rep2) and 33+8 (brief-a).
  - Only in brief-a: `product_refusal` (it has product_end and attempts).
  - Only in rep1 and rep2: `special_hardship_declined`.
  - Other ids are only renamed: restructuring vs restructuring_request, robot_question vs digital_assistant_question, unknown vs unanswerable_question.
- **Transitions:** the only difference is that negotiate, offer_say and revise_ask get a `product_refusal` edge in brief-a.
- **Code:**
  - `offer_setup`, `check_offer` and `callback_check` differ only by CONFIG (persuasion attempts, callback window, messages).
  - `closing` differs in the outcome rows and sentences, in detail:
    - **rep2:** all 16 goodbye sentences are instructions. The spoken-text check (F-047) replaces each with "Thank you for your time. Goodbye." (21 `spoken_fallback` warnings). These required sentences are lost: "You will receive a text message confirming this promise.", "Please use the mobile app or a branch.", "I am sorry for your loss.", "Payments can take one business day to appear." The failure sentence ("could not record") is still added by code (F-063 fix).
    - **rep1 and brief-a:** the sentences are kept.

## Ledger (offline, current code; `tests/test_multi_ready.Session`)

| Case | rep1 | rep2 | brief-a |
|---|---|---|---|
| PUB-01 p1 420 2026-10-14 | ✅ | ✅ | ✅ |
| PUB-04 (6 Nov → deadline) p1 1250 2026-10-23 | ✅ | ✅ | ✅ |
| PUB-06 p1 637.5 2026-10-16 | ✅ | ✅ | ✅ |
| PUB-07 (26th holiday → 27th) p1 540 2026-10-27 | ✅ | ✅ | ✅ |
| PUB-10 p1 365 2026-10-16 | ✅ | ✅ | ✅ |
| **PUB-05 hardship, support declined** | `special_hardship_declined` → no_promise/hardship ✅ | ✅ | **no route** ❌ |

**PUB-05 on brief-a 13:00:**
- The `no_promise/hardship` row has `on=[]`, and no special path closes with it, so the row cannot be reached.
- When the customer declines support, `special_hardship_support` goes back (`stay` → `__previous__`) to negotiate.
- The only exit is a refusal. In the simulation, code then makes 2 persuasion attempts (late band) and closes `no_promise/refused`.
- Both the ledger (reason hardship) and the policy ("no persuasion attempt") fail.
- This spec should not be submitted.

Other cases:
- PUB-08 paid: `already_paid` is in every spec.
- PUB-09 restructuring: present in every spec, only renamed.
- PUB-02/03: the identity questions and third-party values are the same. In rep1/rep2 the callback window is in the prompt, not in code.

## Proposals (not done)

1. **Check that every outcome row can be reached (extraction, generic).** If an outcome row has no `on` state and no `then=close` special path points to it, it is an extraction error and goes to repair. "Row X can never be reached; add the special path or call-end state that closes with it." The default row is excepted. This would have repaired the 13:00 spec. This is a spec or extract change; it is safe for Brief B too (each of its rows has a path).
2. **Stronger spoken fallback.** When an instruction quotes speech (`Say: "…" Then …`), keep the quoted part per sentence and add the goodbye, instead of dropping the whole line. Example: rep2's promise row would keep "You will receive a text message confirming this promise." With current prompts the F-047 repair fixes most of these, but in the last round the soft fallback still loses the required sentence.
3. **`special_tool_failed`:** when the spec does not map it, the default row is used (refused). Map it to the row the spec uses for `promise_failed` (the failure row), or add an extraction check for this state when a `then=close` special path has a tool. Small: no public case.
4. **Trace hygiene for REPRO:** each run overwrites `traces/<slot>.spec.json`, so the 12:24 spec is gone. Proposal: also keep `traces/<slot>.<start_utc>.spec.json`, or let SELF-TEST step 8 run with a different `--slot` for each repeat (`rep1`/`rep2`, as yesterday). build.py is not my file; it needs a decision.
5. **Repeat run:** after proposal 1, two fresh Brief A extractions with the current prompts, using separate slots. The point to watch is the `hardship_declined` path and refuses_to_talk (intent value or special path).

## UAT proposal

New finding: "Brief A extraction sometimes leaves out the special path for declined hardship; the hardship outcome cannot be reached (PUB-05 fails)". Root cause: the extraction checks do not test that every outcome row can be reached. Status: open, fix proposal 1.
