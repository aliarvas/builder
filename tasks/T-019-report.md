# T-019: side question in a business turn (F-074, PUB-04)

No Freya, no model call, no commit, no env.sh.

## Problem

"I can pay on 6 November. Are you a robot?" in `negotiate`: one route wins per turn. The date went to the offer check, the spoken-only `robot_question` path was never entered, and the robot question was never answered.

## Change (generic, no brief value)

**Two new prompts** (`builder/prompts.py`; `docs/PROMPTS.md` regenerated):
- `SIDE_QUESTION_LINE`: "If the customer asked one of these and has no answer yet, first say its answer, then go on:"
- `SIDE_QUESTION_ITEM`: `- {when} Say: "{say}"`, one item per path, filled from the spec's `when.text` and `say.text`.

**Which paths** (`workflow.side_question_paths`): the returning special paths with a spoken answer, no tool and no ask-first question. Closing paths, note paths and transfer paths are not listed.

**Which steps** (`workflow.side_question_steps`):
- the conversation steps in the path's `available_in` (expanded with the existing aliases: `negotiate` → `offer_say`, `revise_ask`; `opening` → `opening_reask`; `third_party` → `third_party_ask`);
- and the conversation steps that speak **right after** a customer turn in one of those steps (`next_speakers`: route targets, through code and API steps). Examples: `identity` → `negotiate` after the last security answer; `negotiate` → `check_offer` → `offer_say` / `confirm_record`.
- Global special-path nodes get no line.

**Where in the prompt:** in `_apply_fixed_lines`, after the no-goodbye line and before the tool-use rule (`task_message` and `loop_prompt`).

**Why "has no answer yet" and not "in the last turn":**
- `offer_say`, `revise_ask` and `third_party_ask` speak a fixed TTS line on entry. The model there speaks only after the customer's *next* turn.
- In PUB-04 (a date after the deadline), the counter-offer is spoken by TTS. The robot answer then comes on the model's next turn: in `offer_say`, or in `confirm_record` if the customer accepts.
- "No answer yet" also covers that case; "last turn" would not.
- **Limit:** the robot answer comes one turn late there, not in the same breath as the counter-offer. When the date is accepted directly, `confirm_record` speaks next and answers at once.
- Answering in the same breath needs a code fix: an extraction field for the side question in `negotiate`, and `check_offer` putting the answer before `offer_message`. That is a larger change; I propose it as a follow-up if the judge does not accept the late answer.

## Prompt budget (estimate in tokens, after the budget stages; before → after)

| Spec | paths | opening | opening_reask | third_party | third_party_ask | identity | negotiate / offer_say / revise_ask | confirm_record |
|---|---|---|---|---|---|---|---|---|
| Brief A live (`traces/brief-a.spec.json`) | 4 | 656 → 761 | 607 → 712 | 581 → 686 | 581 (none) | 988 → 1073 | **1419 → 1550** | 657 → 788 |
| brief-a-v11-extracted | 3 | 668 → 747 | 613 → 691 | 609 → 688 | 609 → 688 | 970 → 1049 | 1413 → 1517 | 670 → 774 |
| A+B v2 | 2 | 675 → 756 | 626 → 707 | 645 → 726 | 645 → 726 | 1009 → 1090 | 1658 → 1739 | 793 → 874 |
| Rehearsal (`traces/rehearsal-clean.spec.json`) | 3 | 699 → 803 | 649 → 752 | 610 → 714 | 610 → 714 | 995 → 1073 | 1490 → 1594 | 754 → 828 |
| spec-brief-a / spec-brief-b fixtures | 0 | unchanged | | | | | | |

- **Growth:** about 22 tokens for the header, plus 25–35 per path.
- **Over the hard limit (1500):** Live Brief A (1550) and the rehearsal (1594) cross it now; A+B was already over. The build never stops for this (T-009b) and writes the `budget` placement lines. These steps had no room left. The place to save is the `negotiate` prompt itself (T-009d), not these lines.
- **Small overlap:** in live Brief A, the global rule "If asked something you cannot answer from the tools, say you do not have that information. Never invent figures…" overlaps the `unknown_information` item. I kept both, because the rule says more (no invented figures).
- **Shortened header:** I shortened it once ("…last turn, or an earlier one still unanswered…" → "…has no answer yet…"), which saved about 8 tokens per step.

## Brief A pin

**Not changed.** The pinned fixture `tests/fixtures/spec-brief-a.json` has no spoken-only returning path (its `already_paid` and `dispute` close the call; `human` has a tool). So the render is byte-identical. The live Brief A spec does have such paths and does change, as shown above.

## Tests

`python3 -m unittest`: **553 OK**.

**New: `tests/test_side_questions.py`** (5 tests):
- **Prompt lint:**
  - in every fixture and recorded extraction, each conversation step has the line and the items exactly for the paths whose `available_in` (or the step before it) covers the step, in `task_message` and `loop_prompt`;
  - order: after the goodbye line, before the tool rule, items in path order;
  - global nodes never get it;
  - at least three recordings have such paths.
- **PUB-04 shape, written out by hand:** in A+B v2 the robot answer is in exactly `opening`, `opening_reask`, `third_party`, `third_party_ask`, `identity`, `negotiate`, `offer_say`, `revise_ask` and `confirm_record`.
- **Path filter:** only returning paths with no tool and no ask; when the same paths are turned into closing paths, there is no line.
- **No such paths:** the fixtures without such paths render no line.

**Changed:** `test_prompt_budget.test_fresh_ab_spec_shrinks_and_every_rule_is_placed_once`, the T-009d guard ("< 1700"). A+B `negotiate` is now 1739. The guard now measures T-009d without the T-019 lines (patched out), and caps the T-019 growth at under 100 tokens per step.

**Leak test:** green. No literal from a brief; the items come from the spec at render time.

**Self-check:** cannot see this. One scripted turn carries one intent.

## UAT (CTO)

Proposed F-074 status: "fixed offline (T-019): the answer is in the prompt of every step that may speak after the turn; live retest PUB-04 open (expect the robot answer at the next model turn at the latest)".
