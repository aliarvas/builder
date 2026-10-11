# T-030 report: a small addition to the persuasion prompt

**Owner:** claude (claude-dev2 role) · **Task:** `tasks/T-030-persuasion-prompt.md`.
**Not done:** no Freya request, no model call, no commit, no env.sh. Generic: no brief value.

## What changed

The two persuasion lines of the `negotiate` prompt are merged and tightened (`builder/prompts.py`, used by `builder/product_notes.py`). Nothing else was edited: claude-dev's T-029 lines in the same file are untouched.

**Before:**
- `PERSUASION_STATE_LINE` = "Persuasion attempt on this product, counted by the bank system: {attempt} (0: none yet). The bank system moves on to the next product when its attempts are used up."
- `PERSUASION_PRODUCT_LINE` (several products) = "A counted attempt is about the {product} only; never move to another product yourself."

**After:**
- `PERSUASION_STATE_LINE` = "Persuasion attempts used on this product (bank count): {attempt}. Each turn: one reason the documents allow, then ask if and when they can pay; never read back or sum up offers, say "record" or "confirm", or thank them."
- `PERSUASION_PRODUCT_LINE` = "Talk only about the {product}."

**How each point of the task is covered:**

| Task point | Where |
|---|---|
| One move per turn: a reason the documents allow, then one question (whether and when) | "Each turn: one reason …, then ask if and when they can pay" |
| No read-back or summary of offers | "never read back or sum up offers" |
| Never "record", "recorded", "confirm" | "say "record" or "confirm"" ("record" also covers "recorded"); the existing line "never say a payment or promise was recorded" stays |
| No thanks for their time, no goodbye | "or thank them"; the goodbye is already covered by the existing step line "Never say goodbye or end the call yourself; the program closes the call", so it is not repeated |
| Not about another product | "Talk only about the {product}" (several products) |
| Merge, not add | The two old sentences are replaced. "(0: none yet)" and "the bank system moves on…" are dropped: the count says it, and the code's "more" line moves to the next product |

## Prompt budget (negotiate, tokens = characters / 4)

"plain" is without the T-019 side-question lines, as the T-009d guard measures it; "full" is with them.

| Spec | Persuasion lines | Before plain / full | After plain / full |
|---|---|---|---|
| brief-ab-extracted-v2 (guard < 1700) | yes | 1699 / 1780 | 1699 / 1780 |
| brief-ab-extracted-tagged | yes | 1664 / 1664 | 1664 / 1664 |
| live A (`traces/brief-a.spec.json`) | yes | 1614 / 1723 | 1613 / 1723 |
| live A+B (`traces/brief-a+brief-b.spec.json`) | yes | 1592 / 1699 | 1591 / 1699 |
| brief-a-repro-1300 | no (spec has attempts but no product-notes block) | 1435 / 1539 | 1435 / 1538 |
| other 7 fixtures | no | unchanged | unchanged |

- **Totals:** the merged text is 11 characters shorter than before, so the total does not grow. A single-product spec with the notes block would get only the first line: +11 tokens, under the 40-token limit.
- **The guard has almost no margin:** brief-ab-extracted-v2 sits at 1699 before and after, against a limit of 1700. That is why the lines are merged and not added to.
- **Scope note:** brief-a-repro-1300 gives persuasion attempts, but the persuasion lines are only added with the per-product block, so that spec gets none of them. That gating is existing structure and was not changed here.

## Tests

- **New** `tests/test_persuasion_prompt.py`:
  - the new rules are in the rendered negotiate prompt;
  - on every fixture with persuasion attempts, negotiate stays under 1700;
  - `recorded_claim_gaps` is empty on every fixture.
- **Docs:** `docs/PROMPTS.md` regenerated.
- **`python3 -m unittest`:**
  - **HEAD + T-030 only** (scratch copy): **615 tests, OK**, including the leak test and the render pin. The pin does not move: the Brief A fixture has no persuasion attempts.
  - **Shared tree:** 2 failures, both from claude-dev's T-029 work in progress (I told claude-dev):
    - the leak test flags 'verified' and 'unverified' in `builder/goodbye.py`;
    - the render pin moves (`8f3bf1a2…`).

## Open

- A live chat run of PUB-12 (with approval) to see whether the persuasion turn stays inside these limits.

## Update after T-029 landed

- **Shared tree:** `python3 -m unittest` now passes in full (claude-dev counts 623 tests, including the T-030 tests).
- **Render pin:** claude-dev set it to `dde9db86…` for T-029; T-030 does not move it.
- **Leak test:** green; the `goodbye.py` keys are gone.
- **Persuasion lines:** unchanged in `builder/prompts.py` and `docs/PROMPTS.md`.
