# T-030: A small addition to the persuasion prompt

**Owner:** claude-dev2 · **Approver:** CTO

## Why

In PUB-12 (`traces/live-runs/user-1c73c93a-64f1-485f-bff1-05a4596689b1.json`, msg 61, 73, 109) the persuasion turn is model-spoken. It:
- moved to another product by itself;
- improvised a read-back ("I'll record this");
- said "I have recorded your promise … Thank you for your time."

T-027 added the product line. The prompt still lets the model close, summarise or claim results.

## What to build (generic, keep it small)

Add to the persuasion part of the `negotiate` prompt (or tighten the existing lines) only what is needed:

1. **One persuasion move per turn.** Give the reason or benefit the documents allow for the product under discussion, then ask one question: whether they can pay it, and when. Nothing else.
2. **Never do these in the persuasion turn:**
   - read back or summarise offers;
   - say "record", "recorded" or "confirm";
   - thank the customer for their time or say goodbye;
   - talk about another product.
   The program does all of those.
3. **Merge rather than add.** Replace overlapping sentences, so the total does not grow by more than about 40 tokens.

## Tests

- The negotiate prompt keeps under the 1700 guard on every fixture and the live A and A+B specs. Report the numbers before and after.
- The `recorded_claim_gaps` check stays green.
- Regenerate `docs/PROMPTS.md`.
- `python3 -m unittest` and the leak test.

## Constraints

- No Freya, no model call, no commit, no env.sh.
- claude-dev is adding goodbye exits (T-029) at the same time and may touch `builder/prompts.py` and `builder/workflow.py`. Coordinate on shared files, and do not undo their lines.
- Report: `tasks/T-030-report.md`.
