# T-035 (URGENT): the note loop ran without end when the code sandbox failed

**Owner:** claude-dev (put T-033 aside and do this first) · **Approver:** CTO

## Evidence

- **Run:** A+B v3, PUB-12, style asks_back, call `d7cb2976-419f-491a-8736-d5a340c699f2`
- **Record:** `traces/live-runs/user-d7cb2976-419f-491a-8736-d5a340c699f2.json`

**What happened:**
1. The first `add_note` (p2) succeeded.
2. From then on, every code run (`note_next`, and the post-hook of `note_record`) failed with "Sandbox did not return a parseable result (returncode=0)".
3. `note_state` never changed, so `note_next → note_record → note_next` ran until the customer hung up.
4. The bank got ~40 `add_note(p3, refused)` calls, and the outcome was empty.

The engine's turn counters stay 0 for code steps, so they cannot stop it. F-067 guarded `record_*` and `close_*` with the engine's call counters (`<node>_success_count` / `_failure_count`), but not the note loop.

## What to build (generic)

1. **Guard the note loop** with the same engine counters as F-067. Once the counters pass (number of products in a kit case, or a safe cap) + 1, go to the close.
2. **Static self-check `code_cycle[<nodes>]` (BUILDER).** Every cycle in the graph made only of non-conversation steps (code, api_request) must have at least one exit whose condition reads only engine counters, i.e. one that needs no code to have run.
   - Find the cycles generically: Tarjan or DFS over the rendered workflow, globals included.
   - A mutation test removes the guard and the check names the cycle.
3. **Simulator.** Extend the sandbox-down play (F-067 `SandboxDownTests`) to the note loop and to every code cycle the check finds: with code failing from step N on, the call reaches end_call and the bank gets a bounded number of calls.
4. **Possible cause.** Check whether anything we write makes code output large. The record's vars JSON was ~10 KB, which is not big, so this is probably a platform glitch. Note what you find.

## Tests

- 10 fixtures plus the live A and A+B specs: no unguarded code cycle.
- `python3 -m unittest` and the leak test.

## Constraints

- No Freya, no model call, no commit, no env.sh.
- Report: `tasks/T-035-report.md`.
