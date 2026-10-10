# T-009 — Keep every step under the prompt budget with extracted specs

**Owner:** claude-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

## Why

With extracted specs the `negotiate` step is at ~1,334 tokens (Brief A), ~1,351 (raw-a) and **~1,498 (Brief A+B)**: at the 1,500 limit. A hidden brief with more rules will go over, and long prompts make the fixed phone-agent model less reliable. See `docs/ARCHITECTURE.md` ("Prompt budget", "Fallback tiers"), `traces/f040-b.print.log`, `traces/f041-a.print.log`.

## Design (generic, no brief values)

1. **Do not repeat what code enforces.** Rules already guaranteed by code (offer date and amount checks, calendar, deadlines, floors, invalid-offer limits, identity attempt counting, closing outcome) should not be spelled out in the step prompt. The step gets the computed facts and the check result instead. Let extraction mark such rules (e.g. a `tier`/`enforced_by` field on a rule) or classify them in code by the spec section they came from. The trace lists each rule's tier (ARCHITECTURE "fallback tiers").
2. **Budget guard in the renderer:** target ≤ 1,200 tokens per step (configurable), hard limit 1,500. If over target: drop code-enforced rules first, then compress duplicates, then move cross-step rules to the global prompt. If still over the hard limit, fail the build with a clear message (never silently cut a policy rule). Trace shows before/after per step.
3. **No rule may disappear silently:** the trace states, for every rule, where it ended up (code, step prompt, global prompt).

## Tests

Offline: Brief A+B extracted spec (`traces/f040-b.spec.json` copied into `tests/fixtures/extract/`) renders with every step under the target; no policy rule lost (each rule accounted for in the trace); a synthetic spec with many rules triggers the guard and the clear failure; leakage scan green; `docs/PROMPTS.md` regenerated.

## Constraints

Python 3.10+, stdlib only. No Freya, no commit, no `env.sh`, no live model calls. Codex is working on `tools/submission_check.py` and the trace (`run_trace.py`, maybe `build.py` trace lines); coordinate by not changing those files beyond adding trace lines in `workflow.py`/`build.py` render summary. Report in `tasks/T-009-report.md`.
