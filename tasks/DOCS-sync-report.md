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

## Fix (reviews `DOCS-sync-review.md` and `F-045-046-review.md`)

**Owner:** claude (second developer). Changed files: `builder/selftest.py`, `tests/test_selftest.py` and the four documents. `workflow.py` and `extract.py` were not touched. No Freya call, no commit, no `env.sh`.

### 1. Self-test: a processed closing turn after a 5xx (F-045-046 review, finding 1)

`_turn_state` compared the latest spoken step with the last step the turn entered. A closing turn speaks in `closing_say` and then runs silent steps (`close_attempt`, `close_record`, `end_call`), so a processed closing turn after a 504 was reported as `turn_state_lost`.

The reference step is now the last step the turn entered **that also spoke** after the user message. When none of the entered steps spoke, an ended call (or a turn with no step change) counts as processed. An open call is still compared with the last entered step, which keeps the F-049 stale-step case as state-lost.

New tests: a closing turn with silent steps, ended or not, is processed; a 504 on the closing turn finishes the case as `pass` without resending; a multi-step turn (silent `account`, then `negotiate` speaks) is processed. The existing stale and no-reply cases are still state-lost.

### 2. Documents (DOCS-sync review)

| Review item | Fix |
|---|---|
| 1. "F-001..F-004 no longer appear" | ARCHITECTURE now names the only evidence: PUB-03 v5 (F-002 retested) and PUB-01 v10 ledger passes. F-001, F-003 and F-004 are fixed in code and still to be retested live; PUB-07 v11 failed on F-050. |
| 2. "committed live run" | FREYA-INTEGRATION and DoD say the `traces/` and `submission/` evidence is local and **not committed**. |
| 3. "No other module imports `freya`" | Now: besides `build.py` and `freya_chat.py`. |
| 4. "exactly one close" | Now: at most one successful close; a failed `close_call` is retried once. |
| 5. Retry list | Now: every tool except `get_account` has `maxRetries: 0`. |
| 6. Stale numbers and lists | `builder/spoken.py` added to the pipeline and the component table; `test_spoken_text.py` added and `test_spoken_output.py` / `test_selftest.py` rows updated in the EVALUATION table; the test count is 245 with a date and a "re-count before each commit" note. |
| Note: "works" on a different brief | DoD now says "Extraction and rendering work … (not yet a live agent run)" and mentions the 3 unmapped items in `f041-raw`. |
| Note: commit tags | Tags now say d5f6af1; the budget line no longer has `[TO-CONFIRM]`. The over-limit behavior is committed: the workflow ships with `budget_exceeded_but_shipped`. |

Other code changes since e4ed265, now in the documents:
- **F-050:** the `account` step is silent again. The identity step says the wait line after the answers match. FREYA-INTEGRATION records the 502/rollback platform behavior.
- **F-049:** new `identity_check` code step (an already verified identity goes straight to `account`). It appears in the skeleton, the platform notes and the DoD identity item.
- **F-048:** the introduction is only in the opening.
- **F-047:** spoken-text check and fallback via `spoken.py`, traced as a `spoken_fallback` warning.
- **Official version 11 run** (`traces/brief-a.log`): end to end with `status: ok` in 183 s. The DoD contract and 30-minute items are now ticked with this evidence, and the self-test 0/3 caused by F-045/F-046 is stated. EVALUATION's results log has rows for this run and for PUB-07 v11.

```text
python3 -m unittest tests.test_selftest   # 41 OK
python3 -m unittest                        # 245 OK
git diff --check                           # clean
```

Open: the UAT-FINDINGS statuses for F-047..F-050 still say "open", although the code fixes are committed (d5f6af1). That file is not part of this task; the owner should update it.

## Fix 2 (DOCS-sync review, "Fix kontrolü")

**Owner:** claude (second developer). Only the four documents changed. No code, no Freya, no commit, no `env.sh`.

The documents cited the official **version 11** run, but `traces/brief-a.log` now holds the **version 12** run. Current evidence from the file:
- start 2026-10-10 20:39 UTC, `total_duration_seconds: 193.161`, `status: ok`;
- extraction 103.5 s with 6 calls and 0 unmapped items;
- 24 nodes + 9 global = 33 steps;
- self-test `identity_attempt` pass, `identity_failure_honesty` pass, `third_party_close` `platform_error`;
- `negotiate` ~1586 -> ~1208 tokens.

The reviewer ran `submission_check` on it and got 19/19 PASS with 2 WARN.

| Review item | Fix |
|---|---|
| (a) numbers and references | Moved to version 12 in four places: DoD contract items 1–3, ARCHITECTURE pipeline tag, "Time" and the budget sentence, and FREYA-INTEGRATION "Vertical slice". |
| (b) version 11 as history only | Kept only in the EVALUATION results log, marked "trace overwritten by the 20:39 run". The DoD contract item points there. |
| (c) submission gate | DoD submission item: the version 12 rehearsal gave `SUMMARY: PASS (19/19 checks passed, 2 warning(s))` (reviewer run, without `--require-env`). The box stays open: it is meant for the hidden briefs, with `--require-env`. |
| (d) `platform_error` cause | EVALUATION L2: the engine runs `close_call` as a `pre_action` of `close_record` and writes no `function_call_start` for it, so the self-test cannot count attempts. Only the ledger proves it. `[TO-CONFIRM]` whether another event carries it. |
| Overwritten traces | EVALUATION "Evidence kept per run", DoD intro and FREYA-INTEGRATION now note that `traces/<slot>.log` is overwritten by the next run on the same slot: copy it or use a new `--slot` right after an evidence run. |

Also:
- **F-051 (open)** was added to the results log as the PUB-07 version 12 chat run (ledger fail): with a date-only answer `check_offer` never ran, and the model printed an internal step call and invented a limit. ARCHITECTURE's evidence sentence also names it.
- The F-050 fix held live (no 502 at the end of identity). The Turkish filler still appeared once (F-043), so the `[TO-CONFIRM]` in FREYA-INTEGRATION is replaced by this observation.

```text
git diff --check        # clean
python3 -m unittest     # 255 run, 1 failure: tests/test_offer_date_only.py (claude-dev's untracked F-051 work in progress; expects a negotiate-prompt sentence not yet in prompts.py). Not from this change.
```

Note: the test count in EVALUATION/DoD (245) is the count at the last commit. claude-dev's F-051 work adds tests; re-count when it is committed.
