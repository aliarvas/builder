# T-009d review — prompt budget, new code-enforced rules (claude-dev2)

**Reviewer:** claude-reviewer · **Scope:** `spec.py` (three new `enforced_by` checks), `workflow.py` (`enforcement_available`, `_covers`, `RulePlan.drop_code_enforced`, `_code_tool`, `move_to_special_paths`, `_path_for`, placements), `prompts.py` text merges, `tests/test_prompt_budget.py`.
**Method:** offline. Rendered the fresh A+B spec (v2) and the real Brief A extraction (`traces/brief-a.spec.json`) and read every `rule_placement` line; compared the dropped rules word for word with the rules that keep them; then mutated rules in the scratchpad (negations, extra clauses, a bad `skip_outcomes`, a path source with `do not`) to see what the new stages do. `python3 -m unittest`: 394 OK on two runs (one earlier run failed once in `test_builder_string_literals_do_not_embed_fixture_values` with the literal `'return'`; it passes alone and on two full reruns, so it came from a file another developer was editing at that moment, not from this change). No Freya, no model, no edits.

## Decision: **düzeltme gerekli** (the stages are limited to steps over budget and the real v2 and Brief A results lose nothing, but four stages can drop a rule that carries a negation, a condition or a prohibition that code does not guarantee)

## What I verified on the real specs (no loss)

**v2 (A+B) — 27 rules leave a prompt, every one has a line in the trace** (`rule_placement`: key → where → reason). I compared each one:

| Rule | Reason in trace | Check |
|---|---|---|
| negotiation[18] "say the latest date you can record is the deadline and offer it" | same wording as offer[4] (offer_dates) | identical sentence; the offer check gives that message in code. OK |
| negotiation[19] "If the customer refuses the deadline, treat it as a flat refusal." | contained in offer[5] "…refuses the deadline date, treat it as a flat refusal and use a persuasion attempt" | only "date" and a trailing clause are added; no condition or negation. OK |
| negotiation[21] never offer a discount… / negotiation[23] twice-no-talk | duplicate of global[2] / global[4] | word for word; global stays in every prompt. OK |
| offer[6], [10], [12] | duplicate of negotiation[17], [7], [8] | identical; the other copy stays. OK |
| negotiation[22] "For each product that ends without a promise, call add_note …" | add_note is called by code (note_record), not by this step | negotiate offers no note tool and the loop does exactly this. OK (see finding 3 for the general rule) |
| global[1] scam question | special path `scam_question`, available in all five steps, `then: return`, its line is the text of the rule | OK |
| global[3] human request | moved to `third_party` only | `human_request` is available in opening, identity, negotiate, confirm_record, not third_party; the path asks once and then transfers. OK |

**Brief A (real extraction): nothing lost.** negotiation[1], [2] are sentences of offer[11] (the `;` splits it); offer[5] is contained in negotiation[4] (adds "instead of a date"); offer[9], [12], [14] are copies of negotiation[5], [6], [7]; negotiation[14] is global[1]; global[3] is moved to `third_party`. Negotiate ~1835 → ~1427 tokens, under 1500, matching the report. The offer/amount/date rules go to code only through tags the earlier tasks already had.

**Trace:** every rule has exactly one line (the test also asserts it) with its place and the reason, the tagged-but-kept rules say "code also enforces X, kept: within budget" or "this spec has no data for that check, kept", and the stage list and per-step budget lines are written. Good.

**The stages run only on steps over the target**, so confirm_record, opening and the like never lose a rule through these new stages.

## Findings

### 1. MEDIUM — `_covers` lets a negating or flipping insert count as "plain words" (`workflow.py:1520`)

`_LIMIT_WORDS` holds `if when only not never no without but …`. After `_norm_rule` an apostrophe becomes a space, so `don't` becomes the two tokens `don t`; `cannot`, `avoid`, `stop`, `instead`, `twice`, `at most` are not in the list either. I ran `_covers` (shorter ← longer):

- "Ask once for the exact day of the payment." ← "**Don't** ask once for the exact day of the payment." → **covered** (True)
- … ← "You **cannot** ask once for …" → True
- "Offer the floor amount on the deadline date." ← "**Avoid** offer …" / "**Stop and** offer …" / "… or refuse **instead**" → True
- "Record the promise on the deadline date." ← "… **twice**" → True
- the guarded cases (`never`, `do not`, `unless`, `only`, `at most once`) correctly stay False.

Result: the positive rule is dropped and the longer, opposite or narrowed rule stays, so the agent loses "ask for the day" and keeps "don't ask". The test only covers `if` and `never`.
**Fix:** treat the normalized form as the unit: add `t`/`don`/`doesn`/`won`/`can`… handling (normalize contractions before `_norm_rule`: `n't` → ` not`, `cannot` → `can not`), and extend the list with `cannot can't avoid stop instead rather twice again most least than unless other`. Better: invert the rule: allow only a small allow-list of filler extras (articles, "date", "the customer", "and use …") is too hard, so keep the deny-list but add the words above and add a test for each.

### 2. MEDIUM — `move_to_special_paths` ignores the rule text and any limit word in the source (`workflow.py:1688`)

`_path_for` matches only the rule's `source` excerpt against the path's `say`/`ask` source excerpts, allowing up to four other words. Two cases that I ran on v2:

- source changed to `do not <the path's transfer excerpt>` (rest = "do not", 2 words) → the human-request rule is still **moved** (it leaves negotiate/opening/etc.); a prohibition is treated as "the path carries it out".
- rule **text** with an extra clause beyond the source ("… Never say this to anyone who has not been verified.", source unchanged) → the scam rule is **removed from every prompt**; the clause is lost silently.

Real v2 and Brief A rules pass, but the extractor writes `text` and `source` separately and the text can be longer than the excerpt.
**Fix:** (a) reject when the leftover source words or any word of the rule `text` that is not in the path's lines includes a `_LIMIT_WORDS` entry; (b) require the rule text's sentence count to be no larger than the number of matched path pieces (a rule with an extra sentence stays); (c) tests for both mutations above.

### 3. MEDIUM-LOW — a rule that names a code-called tool is dropped whatever else it says (`_code_tool`, `workflow.py:1594`)

The stage drops a step rule when every sentence names a tool that a code loop calls and the step does not offer. It does not look at what the sentence asks. I ran on v2:

- "Never tell the customer that add_note was called." → dropped (`add_note is called by code`). That is a speech instruction for the model; code does not stop the model from saying "I will note it", which the AB-FRESH report itself gave as a reason to drop the call rule.
- "Do not call add_note when a promise was recorded … Call add_note only after the customer confirmed they heard the reason." → dropped, including the condition about the customer that no code implements.

Only the positive "call add_note with … for each product …" is what code does.
**Fix:** keep the rule if any sentence has a speech verb (`say tell mention inform announce explain`) or a limit/negation word that is not the tool's own natural wording. A narrower safe version: drop only sentences that start with the tool call ("call X …", "for each …, call X …"); say in the trace what was dropped. The honesty rule on `create_promise` stays because it is global (good, and the stage correctly skips global rules).

### 4. MEDIUM-LOW — `product_notes` is "available" even when the notes do not skip the outcome the rule talks about (`enforcement_available`)

`product_notes` returns True when the spec has `closing.product_notes` and the note node exists. The tagged global rule in v2 ("On any transfer … add no notes") is only enforced by code when `skip_outcomes` names the transfer outcome (v2: `['transferred']`). I set `skip_outcomes = []` (the field is allowed to be empty by `spec.py:359`) and tagged the rule: it is **dropped** (`code: product_notes`) while the note loop would write notes on a transfer. A bad extraction would then both break the rule in code and remove it from the prompt.
**Fix:** treat the tag as available only when `skip_outcomes` is non-empty (or split it: `product_notes` for "a note for each product", `product_notes_skip` for the "no notes on X" rule). Test with `skip_outcomes = []`.

### 5. LOW — the three new tags are checked against spec data, not against the rule

`persuasion_attempts` is available whenever the spec has attempt data. A rule tagged with it that says what to propose on each attempt would be dropped; the extraction prompt says "Not what the agent proposes on each attempt", and v2 puts the proposal rules ("Attempt 1 is for the full past-due amount…", "Attempt 1: propose the last business day of this week…") without the tag, so the live risk is the model's tagging. The existing test only tags the counting rules by hand (4, 5, 11). Cheap guard: log a warning if a tagged rule contains a proposal/amount/date word, or keep tags for these three checks only on rules without digits-plus-"propose/offer/ask". Not blocking.

### 6. Notes (no change needed)

- Fixed-text merges (`prompts.py`): the single honesty sentence still names `create_promise … ok true`; the wording tests are kept. Fine.
- ≤1500 is not reached on the existing v2 spec (1547); it ships with `budget_exceeded_but_shipped` as designed. The ~1488 figure needs a fresh extraction with the new tags; the claim is test-only (hand-added tags), so please keep it `[HYPOTHESIS]` in the docs until the extraction run.
- The global rule "no promise → paid / first non-paid reason" stays in the global prompt (risk 5); agree.

## Answers to your questions

- **Is any policy rule silently lost?** Not on v2 or Brief A. Four general stages can lose one on other inputs: contractions/`cannot`/`avoid`/`instead` in `_covers` (1), source-only matching in `_path_for` (2), tool-name rules with speech or condition clauses (3), `product_notes` with an empty skip list (4).
- **Trace shows each rule's place?** Yes, one line per rule with the reason, including kept rules and the budget stages.
- **Brief A behaviour?** Unchanged except the two placement moves above; negotiate 1835 → 1427; no rule lost.

## Live retest

Fresh A+B extraction (model call, with approval) to see which rules get the new tags and whether negotiate falls to ≤1500; then PUB-12 and PUB-13 chat, plus Brief A PUB-02/05 (no change expected).


---

## Re-review (Fix 1–5)

**Method:** offline. Re-ran every mutation from the first review (13 `_covers` pairs, the path-source and path-text mutations, the tool-name rules, `skip_outcomes = []`), printed all placements for v2 and the real Brief A, and probed `_covers` with 11 new sentences. `python3 -m unittest`: 401 OK. No Freya, no model, no edits.

### Decision: **merge edilebilir** (two LOW notes; no silent policy loss found on the real specs or in the earlier mutations)

| Finding | Result |
|---|---|
| 1 `_covers` | All 13 earlier pairs are now **False** (don't, cannot, avoid, stop and, "or refuse instead", twice, unless, do not, at most once, never, after the call, only on a Monday, or hang up). New probes also False: "Shouldn't …", "Doesn't …", "… no longer", "Asking … wouldn't help", "… before the customer pays". The control "… and use one attempt" is still covered. The "nothing before the first word" rule and the no-number rule explain why. |
| 2 `_path_for` | Source `do not <excerpt>` → rule **stays** in the global prompt; scam rule plus an extra sentence ("Never say this to anyone who has not been verified.") → **stays**. v2: the human-request rule (two extra sentences) now stays global; the scam rule still goes to its path (the rule text is the path line plus "and continue"). Brief A: its one-sentence human-request rule still moves to `third_party`. |
| 3 `_code_tool` | "Never tell the customer that add_note was called.", the conditional two-sentence rule, and v2 negotiation[22] (it has "without" and "no") **stay**; only a plain "call X …" / "for each …, call X …" with no speech or limit word goes to code. |
| 4 `product_notes` split | With `skip_outcomes = []` the "no notes on transfer" rule tagged `product_notes` stays: `tagged product_notes but it says more than that check does, kept`. `product_notes_skip` needs a non-empty skip list. |
| 5 tag vs text | Proposal rules 13–15 tagged `persuasion_attempts` stay; the counting rule goes to code. |

**Trace:** one line per rule, kept ones carry the reason (`it says more than that check does, kept`); the stage list and budget lines are written. **v2 negotiate is 1639 tokens** (was 1547; the safer rules keep more text), shipped with `budget_exceeded_but_shipped`; Brief A is 1444, under 1500. That is the accepted trade-off (CTO principle: in doubt, keep and warn). The ≤1500 claim for tagged v2 (~1540) is test data only and stays `[HYPOTHESIS]` until a fresh extraction.

**Real specs (no loss):** v2's dropped rules are exactly the verbatim copies, the contained sentence (negotiation[19] in offer[5]) and the closing/identity rules from earlier tags; Brief A's are the copies listed before. I compared them again against the keepers; each dropped sentence is in the kept rule.

### LOW notes

1. The deny-list is still a list. These longer sentences still count as plain extras: "… , **nor** anything else", "… **neither** today nor later", "… is **forbidden**", "… is **prohibited**", "… **during the second call**". A negating or conditional insert of that kind inside a copy is rare (a copy is normally word for word), but adding `nor neither forbidden prohibited banned during` costs nothing. A stronger version: cover only when the extra words are a short allow-list (the report's own examples: "date", "and use one attempt").
2. Update `docs/ARCHITECTURE.md` budget paragraph if it still quotes ~1488/≤1500 for v2 (the report says it was regenerated; I did not re-read it).

### Live

Unchanged: fresh A+B extraction (model call, with approval) to see the real tags and the negotiate size, then PUB-12 / PUB-13 chat and Brief A PUB-02/05.
