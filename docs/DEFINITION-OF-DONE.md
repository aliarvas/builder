# Definition of Done

**Owner:** Completion and submission gates  
**Read when:** Finishing a milestone or preparing the submission

Mark an item only with a test result, artifact or verified official rule, and name the evidence. This is a checklist, not a design document. Status as of commit e4ed265 (2026-10-10).

## Contract

- [ ] `python3 builder/build.py {brief} {tool_api}` runs end to end with no manual step: extraction, save, publish, export and self-test in one run. *Proven so far:* extraction alone (`--print` runs, `traces/f040-*.spec.json`), and save/publish/export with a written spec (`traces/brief-a.log`, `--spec`). No single live run of the full chain with self-test is recorded yet.
- [x] A Freya workflow is created or updated in place, published, and exported with `freya.export_workflow`. Evidence: `traces/brief-a.log` (workflow `b0bdd6e6…`, published version 10) and `submission/brief-a.workflow.json`; publish is read back by `_ensure_published_version`.
- [ ] Runs finish well under 30 minutes per brief, including self-tests. Measured parts: extraction took 128 to 222 s in the live `--print` runs (`traces/f040-*.print.log`), and the self-test is capped at 6 minutes. The trace records `total_duration_seconds`, but no timed full run is recorded.
- [x] Only the bank's tool API is used by the phone agent; the phone-agent model is unchanged; `agent_config` is not sent. Evidence: tools come only from the OpenAPI file; `builder/freya.py` is identical to the kit; the trace lines `sent_agent_config: absent` / `sent_nulls: 0` (`test_submission_check.py`).
- [ ] Runs on Python 3.10+ from a fresh checkout; keys come from environment variables only. Keys: done (`llm.py`, `freya.py`, `run_trace.py` masking). Fresh-checkout run on Python 3.10: not yet tested.

## Generality

- [x] No rule, date, value, holiday or outcome name from any specific brief in code or prompts. Evidence: the literal leak scan in `tests/test_multi_step.py`.
- [x] Works on a brief with a different layout and a different tool API. Evidence: live extractions of `tests/briefs/changed-a` (changed values and tool contract) and `raw-a` (raw material) ended `status: ok` with `unmapped_items=0` (`traces/f040-changed.print.log`, `traces/f040-raw.print.log`), and their reference specs are compared with `tools/compare_spec.py` (T-006b). `spec-synthetic` + `openapi-synthetic` render offline.
- [x] Handles an override memo, a code list and tables without crashing. Evidence: `tests/briefs/raw-a` (memo wins; CSV codes; holiday list), T-006b.
- [x] Tool field names and enums come from the OpenAPI file. Evidence: `tools_from_openapi.py`, with field names in the spec checked against `tool_contract`.
- [x] Every step's dialogue prompt is measured and reported in the trace (`prompt_estimate`, `budget`, `rule_placement`; target 1,200, limit 1,500). Evidence: `test_prompt_budget.py`, T-009.

## Safety and honesty

- [ ] No debt details before identity verification, where the brief requires it. Graph: `get_account` is reachable only from `identity` after the verified result, and the self-test forbids it after a failed check. Chat: PUB-03 version 5 passed. Not yet proven over 3 scored runs.
- [ ] Promises recorded only after read-back and confirmation; correct product, date and amount, once. Code: `check_offer`, the read-back, the per-product attempt limit. Chat: PUB-01 version 10 recorded one correct promise. Not yet proven over 3 scored runs.
- [ ] The agent never claims a record that the tool did not confirm. Code: the post-hook `what_to_do_next`, the global success-evidence rule (F-030), the self-test honesty check. Live proof is pending.
- [x] Prompt-only rules are not described as guarantees. Evidence: every rule's tier is traced (`rule_placement`); `enforced_by` is honoured only when `enforcement_available` is true for the spec.
- [x] No API keys in the repo, traces or logs. Evidence: `.gitignore` (`env.sh`), `run_trace.py` masking, and the `no_secrets` check in `tools/submission_check.py`.

## Evidence

- [ ] Practice-case baseline and final scores recorded; no regression versus the baseline. The baseline is recorded (6/10). There is no scored `run_cases.py` run of the current builder, only single chat cases ([`EVALUATION-AND-TESTING.md`](EVALUATION-AND-TESTING.md), Results log).
- [x] Static and unit tests pass: `python3 -m unittest`, 225 tests OK on the working tree, 2026-10-10. Re-run before every commit.
- [x] Each run has a trace: start/end time, every model call (model and one-line purpose), Freya IDs with step and tool counts, self-tests. Evidence: `run_trace.py`, `build.py`; checked by `tools/submission_check.py`.

## Submission (before Sun 20:00 UTC)

- [ ] Builder run on each hidden brief; one agent per brief; traces kept.
- [ ] Exports committed, e.g. `submission/hidden-1.workflow.json`, `traces/hidden-1.log`, `traces/hidden-1.spec.json`.
- [ ] `tools/submission_check.py … --verify-inputs --require-env` prints `SUMMARY: PASS` for each (see [`SUBMISSION.md`](SUBMISSION.md)).
- [ ] Fresh checkout reproduces the run from the committed commit.
- [ ] Form sent with `team`, `repo`, `commit`, `run_command`, `workflows`, `traces`.
- [ ] No agent edited after its run.

## Done means

An unseen brief and tool file go in, and a working, policy-configured Freya agent plus its trace come out, reproducibly, with no hand edits.
