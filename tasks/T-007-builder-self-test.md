# T-007 — Builder self-test inside the 30-minute budget

**Owner:** codex-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

## Why

The hidden briefs have no practice cases. The builder must check its own agent before it finishes: catch a broken workflow, a missing close, or a step that never routes. The trace must show what was tested and the result; the organizers' reviewer compares trace, code and agent. Read `AGENTS.md`, `docs/SELF-TEST.md` (step 3–4 and "Dikkat edilecekler"), `docs/EVALUATION-AND-TESTING.md`, `build-the-builder-v2/docs/api.md` (chat route), `builder/build.py`, `builder/freya.py`, `docs/UAT-FINDINGS.md` F-021, F-023, F-031.

## Design

New module `builder/selftest.py`, called by `build.py` after save + publish (not in `--print` / `--validate`; a `--no-self-test` flag for development).

1. **Cases from the spec, not from practice files.** Generate 3–5 short scripted chat cases deterministically from the extracted spec and the OpenAPI file:
   - opening + identity happy path up to the account step;
   - identity exhausted (wrong answers until the limit) → expects the identity-failed close;
   - third party answers → expects the third-party close or callback path;
   - (optional) one offer inside the rules → expects a promise call.
   The customer lines are built from templates plus spec values (identity questions, names from call variables). No model call needed. If the bank's practice API is not available for a hidden brief, use synthetic call variables; the check is about the **workflow**, not the ledger.
2. **Run each case through `POST /api/v2/chat/message`**, one turn at a time, with `callId`. Stop sending after the agent ends the call (F-031). Handle 5xx: before resending, read the call record (`get_call`) to see if the turn was processed (F-023); at most 2 retries per turn, then mark the case `platform_error`, not `fail`.
3. **Checks per case from the call record** (`get_call(call_id)["messages"]`): expected step reached (`node_enter`), expected tool called (`function_call_start`), `close_call` (or the hang-up tool) ran exactly once, no tool error, no step stuck for more than N turns. Report `pass` / `fail` / `platform_error` with a one-line reason.
4. **Budget:** a hard wall-clock limit for the whole self-test (config, default 6 minutes) so extraction + build + self-test stays well under 30 minutes. Cases run sequentially (one Freya key; do not load the platform).
5. **Trace:** one line per case (`self_test: case=<id> result=<...> reason=<...> call_id=<...> seconds=<...>`) and a summary line. The builder does **not** fix the agent automatically in this task; a failing self-test is reported, the build still exports.

## Tests (offline)

Fake Freya client: case generation from the three fixtures, a passing call record, a stuck call, a missing close, a 5xx where the turn was processed, a 5xx where it was not, budget exhaustion. No real network.

## Constraints

Python 3.10+, stdlib only. No real Freya calls (the CTO runs the live check). No commit. No `env.sh`. No brief values in `builder/`. Do not touch `builder/extract.py`, `builder/llm.py` or the extraction prompts in `prompts.py` (claude-dev is working there). Report in `tasks/T-007-report.md` with the exact live command.
