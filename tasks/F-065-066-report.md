# F-065 / F-066 report (CTO, 2026-10-11)

Source: another team's notes (sandbox payload limit, snekbox outages). Done by the CTO directly, offline, no Freya action.

## F-066: sandbox payload measurement
- `workflow.workflow_code_payloads()` measures every code step and hook (JSON-escaped bytes).
- `build.py` writes one `code_payload` trace line per site; warning when code > 131072 - 32768 bytes.
- Measured: largest code `check_offer` 31.5 KB; live call variables peaked at 9.4 KB (traces/live-runs). Far below the limit.
- Test: `tests/test_prompt_budget.py` `SandboxPayloadTests`.

## F-065: silent loops without the sandbox
- `record_next` -> closing and `close_record` -> end_call now also exit on engine counters (`<node>_success_count` / `_failure_count`), which need no code.
- Record cap: max attempts per product x 6; close cap: counter > 1 (at most 3 close calls).
- Without the pre-hook, the promise body has no date or amount: the bank cannot record wrong data.
- Tests: `tests/test_record_loop.py` `SandboxDownTests` (both loops end; the cap never cuts a working loop).

## Not committed
Codex's F-064 / T-009d work is in progress in the same files (workflow.py, build.py, test_prompt_budget.py). 4 tests from that work fail right now (test_callback F-064, BudgetT009dTests); my tests pass (36/36 in the affected modules).
