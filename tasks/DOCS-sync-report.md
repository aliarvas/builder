# DOCS-sync — architecture, Freya, evaluation and done docs synced with the code

**Owner:** claude (second developer) · **Base:** commit e4ed265 plus the working tree on 2026-10-10.

Only documents changed: `docs/ARCHITECTURE.md`, `docs/FREYA-INTEGRATION.md`, `docs/EVALUATION-AND-TESTING.md`, `docs/DEFINITION-OF-DONE.md`. No code file touched. No Freya call, no commit, no `env.sh`.

## Method

Every statement was checked against code, a rendered workflow, a trace or a report:

- The Brief A skeleton was rendered offline from `tests/fixtures/spec-brief-a.json`, listing nodes, node types, transitions, pre-actions and tools.
- Imports were grepped for the dependency rules. `cmp builder/freya.py build-the-builder-v2/freya.py` showed the files are identical.
- Facts were read from source: `llm.py` (model and temperature), `extract.py` (groups, repair rounds, coverage), `tools_from_openapi.py` (post-hook, retries), `workflow.py` (budget plan, closing chain, hang-up tool, special paths), `selftest.py`, `slots.py`, `freya_chat.py`, `build.py`, `tools/submission_check.py`.
- Live evidence came from `traces/brief-a.log`, `traces/f040-*.print.log`, `traces/t006b-*.print.log`, `docs/UAT-FINDINGS.md` and `tasks/T-006b`, `T-007`, `T-008`, `T-009`, `F-040`, `F-043-044` reports.

## What changed

### ARCHITECTURE.md
- The pipeline is rewritten as the real module chain, with modes (`--print`, `--validate`, `--spec`, `--single-step`, `--no-self-test`, `--slot`) and exit codes.
- The skeleton section matches the rendered node set: `opening_reask`, `opening_unclear`, `offer_setup`, `confirmation_progress`, `closing_say` / `close_attempt` / `close_record`, `close_turn_limit`, `close_special_tool_failed`, global special paths and `close_call_on_hangup`. The old "setup (code)" first node does not exist and was removed.
- New "Spec (the IR)" section: sections, `Rule(text, source, enforced_by)` and the seven `enforced_by` checks.
- Messy inputs now describe what the code does: 4 named parallel groups, checks including the dry render and brief-value evidence, at most 2 repair rounds, coverage plus one follow-up, `spec.failed.json`, and rule tiers via `enforcement_available` / `RULE_STEPS` / the global prompt. The "ask the model again only about gaps" line is now concrete.
- The components table lists the real modules. The invented `src/agent_factory/`, `ir/`, `freya/` and `reference/` layout was replaced by the real repository shape.
- Builder model: "Temperature 0, one retry on invalid JSON" was wrong. Now: no temperature is sent (the model rejects it, T-006), one transport retry, and JSON is checked by code with repair rounds.
- "Self-test via the simulation route" was wrong; it uses the chat route.
- Prompt budget: the T-009 behavior with numbers and the estimate formula.
- The core design idea moved from `[HYPOTHESIS]` to verified, with the chat retest evidence. It still says a full scored run is open.

### FREYA-INTEGRATION.md
- New table of every Freya call site: dry run, slot-checked save, the kit's `llmConfig` update, publish with read-back, export before the self-test, chat self-test.
- The format rules are now "what the renderer sends", with the code location.
- The retry wording was wrong: "a failed `create_promise` is retried once by the agent". It is the flow, up to `max_attempts_per_product`. Also added: `close_call` is sent at most twice, and `get_account` uses `maxRetries: 1`.
- New section on platform behavior seen in our runs: F-021, F-023, F-031, F-043, and the export's own `agent_config` / `null`.
- The vertical slice is marked done with evidence.

### EVALUATION-AND-TESTING.md
- L1 lists the real suites and the synthetic inputs (`spec-synthetic`, `openapi-synthetic`, `tests/briefs/raw-a`, `changed-a`).
- New L2: the builder self-test as implemented after T-007b.
- New L4: the submission check command.
- Results log: added the chat-test rows (version 5 PUB-03, version 8 PUB-01/PUB-07, version 10 PUB-01 extracted spec). It also says that no scored `run_cases.py` run of the current builder exists.

### DEFINITION-OF-DONE.md
- Items are ticked only with named evidence. Ticked: export, model and `agent_config`, generality (leak scan, raw-a and changed-a live extraction `status: ok, unmapped_items=0`), tool fields from OpenAPI, prompt budget in the trace, prompt-only rules not called guarantees, no keys, unit tests (225 OK), trace contents.
- Left open with the reason: a full end-to-end live run with self-test, a timed 30-minute run, fresh checkout on 3.10, the three safety and honesty items (code plus single chat runs, not 3 scored runs), practice scores, and every submission item.
- Added `submission_check … SUMMARY: PASS` as a submission gate.

## Open points for the CTO

1. **Prompt budget over the hard limit.** Commit e4ed265 fails the build (`SpecError`). The working tree has an uncommitted claude-dev change (`BUDGET_EXCEEDED = "budget_exceeded_but_shipped"`, also imported by `build.py`): the workflow ships with a trace line and a warning. ARCHITECTURE.md describes both and marks the new behavior `[TO-CONFIRM]`. Update that line when the change is committed.
2. There is no recorded live run that does extraction, save, publish, export and self-test in one command. `traces/brief-a.log` is a `--spec` run with `self_tests: none`. DoD keeps this open.
3. `docs/UAT-FINDINGS.md` and `builder/build.py` / `workflow.py` have changes from others in the working tree; I did not touch them.

## Checks

```text
python3 -m unittest      # 225 tests OK (working tree, after claude-dev's fixes)
```
