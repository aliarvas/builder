# T-009d report: prompt budget on the fresh A+B spec

**Owner:** claude (second developer) · **Input:** `traces/ab-fresh.spec.json` (same content as `tests/fixtures/extract/brief-ab-extracted-v2.json`), the CTO's addition (AB-FRESH risk 2).
**Not done:** no Freya request, no commit, no env.sh, no model call. `offer_check.py` and `product_notes.py` were not touched (claude-dev, risks 1, 3, 4, 5). `workflow.py` was re-read before the edits.

## Result

| Spec | negotiate / offer_say / revise_ask | Limit 1500 |
|---|---|---|
| ab-fresh before | ~1744 | over |
| **ab-fresh now** (`traces/t009d-ab-fresh.print.log`) | **~1547** | over by ~47; ships with the warning |
| ab-fresh with the new tags a fresh extraction should give (added by hand in a test) | ~1488 | **under** |
| Brief A, real extraction (`traces/brief-a.spec.json`) | 1484 → 1409 | under |
| Brief A fixture (`spec-brief-a.json`) | 726 → 710 | under (only the fixed text changed) |

**≤1500 on the existing ab-fresh spec is not reached.** The remaining rules about counting attempts (negotiation rules 4, 5, 11) and "no notes on a transfer" (global 5) are code-enforced, but this spec does not tag them. The new tags (below) are in the extraction prompt, so a fresh extraction should tag them; I could not run one (no env.sh, no model call). **≤1200 cannot be reached without cutting rules:** most of the ~25 remaining negotiate rules are things the agent must say or decide.

## What changed (general, no brief value)

1. **New `enforced_by` checks** (`spec.py`, `workflow.enforcement_available`, extraction prompt):
   - `persuasion_attempts`: attempts are counted per product, a refusal uses one, and the product ends when they are used up (F-062);
   - `product_refusal`: products one by one in account order, and a refusal ends only that product (code chooses the lowest unhandled number);
   - `product_notes`: a note for every product without a promise, none on skipped outcomes (F-061).

   Each check counts only when its code step was really rendered (`product_refusal`, `note_record`). `enforcement_available` takes the rendered node names for this.
2. **Code-enforced stage, two additions** (`RulePlan.drop_code_enforced`):
   - **A step rule naming a tool that a code loop calls** (the promise loop F-063, the note loop F-061), where the step does not offer that tool. Every sentence of the rule must name the tool. Example: negotiation rule 22 "For each product … call add_note …" goes to "code: add_note is called by code (note_record), not by this step". This applies to step rules only; a global rule such as "Say a promise is recorded only after create_promise returns ok" stays.
   - **A word-for-word copy of a rule that code guarantees.** Example: negotiation rule 18 equals offer rule 4 (`offer_dates`).
3. **Duplicates also catch a contained sentence** (`_covers`):
   - The shorter sentence (5 words or more) appears in order inside a longer sentence of the same step. The left-out words must contain no condition, limit or negation word (`if`, `only`, `not`, `never`, …).
   - Example: negotiation rule 19 is contained in offer rule 5 ("… and use a persuasion attempt").
   - "If X, ask …" does not cover "ask …", and "never offer" does not cover "offer".
4. **Rules a special path carries out** (new stage `move_to_special_paths`):
   - The rule's `source` excerpt contains the path's spoken line or question excerpt, plus at most 4 joining words.
   - The path must be rendered, and its line must not be the fallback.
   - Such a rule leaves the steps where the path is available. A global rule needed by exactly one other step moves to that step.
   - Examples: global rule 1 (scam) → special path `scam_question`. Global rule 3 (human) → step `third_party`, the only step without that path.
5. **Repeated fixed text merged** (`prompts.py`, `docs/PROMPTS.md` regenerated):
   - **system prompt:** three honesty sentences became one, with the same content (the `create_promise … ok true` wording is kept);
   - **negotiate:** "offer exactly that" and "say a limit only when…" were each merged into the sentence next to it, and "here" was dropped;
   - **`PERSUASION_STATE_LINE`:** shorter wording, same content;
   - **the wording tests pin stays** (calendar, limit, internal names).

**AB-FRESH risk 2:**
- **Copied rules:** of the 4 copies, 3 (rules 7, 8, 17) were already said once (the offer copy was dropped as a duplicate). The 4th (rule 18) is now dropped as a copy of the code-enforced offer rule.
- **add_note rule:** dropped (item 2).

Every move is a `rule_placement` line in the trace.

## Brief A

The real Brief A extraction changes in two placements:
- offer rule 5 is contained in negotiation rule 4, so it is said once;
- the human-request rule moves from the global prompt to `third_party`, because the `human_request` path covers opening, identity, negotiate and confirm.

Apart from that, only the shortened fixed text differs. No rule is lost.

## Tests

- New in `tests/test_prompt_budget.py` (`BudgetT009dTests`, 6 tests):
  - ab-fresh drops below 1560 and every rule is placed exactly once;
  - the copies are said once, and there are trace notes for rule 18, rule 22, rule 19, global 1 and global 3;
  - with the new tags ab-fresh is ≤1500 and has no `budget_exceeded_but_shipped`;
  - each new check needs its code step;
  - the note rule stays without the note loop;
  - the covering guard (condition and negation words);
  - the special path needs its spoken line.
- `test_untagged_extraction_ships_with_a_clear_warning`: an untagged rule may now go to code only via "is called by code".
- **Results:** full suite **391 tests OK**. `git diff --check` is clean.

## Files

- `builder/spec.py`: new checks.
- `builder/workflow.py`: `enforcement_available`, `_covers`/`_covered_by`, and in `RulePlan`: `observe`, `_code_tool`, `drop_code_enforced`, `drop_duplicates`, `_path_for`, `move_to_special_paths`, plus the stage list.
- `builder/prompts.py` and `docs/PROMPTS.md`.
- `docs/ARCHITECTURE.md`: the tag list and the budget paragraph.
- `tests/test_prompt_budget.py`.

## Open

- A fresh A+B extraction with the new extraction prompt is needed to confirm ≤1500 on a real spec (this needs a model call).
- The global closing rule "no promise → paid / first non-paid reason" (risk 5) stays in the global prompt. Under T-009b, an untagged closing rule is not moved.

## Fix (review `reviews/T-009d-review.md`, findings 1–5)

**Principle (CTO):** no budget stage drops a rule that carries a negation, a condition or a prohibition that code does not guarantee. In doubt the rule stays; going over the limit is only a warning. I re-read `workflow.py`, `callback.py` and `prompts.py` (after F-064) before editing; I edited only the budget code (`enforcement_available`, the helpers, `RulePlan`), the tag list and the extraction text.

1. **`_covers`** (finding 1):
   - Contractions are normalized first (`don't` → `do not`, `cannot`/`can't` → `can not`, `won't` → `will not`).
   - `_LIMIT_WORDS` now also has `twice again none nothing or instead rather avoid stop refuse decline other otherwise than most least more less any all every each first last same can cannot must may should`.
   - Nothing may come before the shorter sentence's first word (a prefix such as "avoid" or "you must not" governs the whole sentence), and no left-out word may be a number.
   - Test: 9 longer sentences (don't, cannot, if, never, avoid, stop and, or refuse instead, twice, "for 2 products") keep the shorter rule. Control: "… and use one attempt" still covers it.
2. **`_path_for`** (finding 2): the rule stays
   - when its leftover source words contain a `_LIMIT_WORDS` word;
   - when its text has more sentences than the path pieces it matched;
   - or when a word of its text that is not in the path's own lines (`when`/`say`/`ask`, text and source) is a `_LIMIT_WORDS` word (a leading "if"/"when" names the trigger and is allowed).

   Tests:
   - source "do not …" → stays global (control: the same rule without "do not" moves);
   - scam rule plus "Never say this to anyone who has not been verified." → stays, and the sentence is in the system prompt.

   Effect on v2: global rule 3 (human request: "This applies before and after verification") now stays global. On Brief A it still moves to `third_party` (that rule is a single sentence that the path covers).
3. **`_code_tool`** (finding 3): a rule leaves the step only when every sentence is a plain call of the tool: `call X …` or `for each …, call X …`, with no speech word (`say tell mention inform explain announce read ask`) and no `_LIMIT_WORDS` word.
   - Tests: "Never tell the customer that add_note was called.", "Do not call add_note when … Call add_note only after the customer confirmed …", "Call add_note only after …" and "Call add_note and tell the customer it is noted." all stay. Control: "For each product, call add_note with its product_id and reason." goes to code.
   - Effect on v2: negotiation rule 22 ("… that ends without a promise …, also when no product gets a promise") now stays untagged. With the `product_notes` tag it goes to code.
4. **`product_notes`** (finding 4): the tag is split.
   - `product_notes` means a note for every product without a promise.
   - New `product_notes_skip` means "no notes on X". It is available only when `skip_outcomes` is not empty.
   - A "no notes" rule tagged `product_notes` stays (trace: "tagged product_notes but it says more than that check does, kept").
   - The extraction prompt lists both tags.
   - Tests: `skip_outcomes = []` keeps the rule; the wrong tag keeps the rule.
5. **Tag versus rule text** (finding 5): a rule with one of the four T-009d tags that contains a proposal or speech word (`propose offer ask say tell amount date deadline floor`) stays, with the same trace note.
   - Test: negotiation rules 13, 14 and 15 ("Attempt 1 is for the full past-due amount …", "Attempt 1: propose …", "Attempt 2 …") tagged `persuasion_attempts` stay. Control: rule 5 (counting only) goes to code.

**New numbers** (the earlier ≤1500 claim with tags no longer holds; it was only test data):

| Spec | negotiate |
|---|---|
| ab-fresh, untagged (`traces/t009d-ab-fresh.print.log`, regenerated) | 1744 → **~1639**, ships with `budget_exceeded_but_shipped` |
| ab-fresh with the tags a fresh extraction should give (counting 4/5/11, note 22, skip global 5; test only) | ~1540 |
| Brief A real extraction | 1484 (HEAD) → ~1444; its offer rule 5 now stays ("instead") |

Fixed-text merges and the honesty sentence are unchanged.

**Checks:**
- `tests/test_prompt_budget.py` (`BudgetT009dTests`): 10 tests, one or more per finding;
- full suite **401 OK**;
- `git diff --check` clean;
- `docs/ARCHITECTURE.md` (tag list, budget paragraph) and `docs/PROMPTS.md` regenerated.

No Freya request, no commit, no env.sh, no model call.

**Open:** a fresh A+B extraction with the new tags (model call, with approval) to see the real tagging. ≤1500 on ab-fresh is not reached; the remaining gap comes from rules the agent must follow and that code does not guarantee.
