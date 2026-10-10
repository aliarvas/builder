# Definition of Done

**Owner:** Completion and submission gates  
**Read when:** Finishing a milestone or preparing the submission

Mark an item only with a test result, artifact or verified official rule, and name the evidence. This is a checklist, not a design document. Status as of commit d5f6af1 plus the F-045/046 review fix (2026-10-11). The live evidence files in `traces/` and `submission/` are local and **not committed yet**; commit them or a fresh clone cannot check these boxes. `traces/<slot>.log` is overwritten by the next run on the same slot; copy it, or use a new `--slot`, right after a run that serves as evidence.

## Contract

- [x] `python3 builder/build.py {brief} {tool_api}` runs end to end with no manual step. Evidence: the official command on Brief A (no flags) did extraction, save, publish (version 12), export and 3 self-test cases with `status: ok` (`traces/brief-a.log`, 2026-10-10 20:39 UTC; self-test 2 pass, 1 `platform_error`, see EVALUATION L2). The earlier version 11 run (0/3, F-045/F-046) is recorded only in the EVALUATION results log; its trace was overwritten.
- [x] A Freya workflow is created or updated in place, published, and exported with `freya.export_workflow`. Evidence: `traces/brief-a.log` (workflow `b0bdd6e6…`, updated in place up to published version 12) and `submission/brief-a.workflow.json`; publish is read back by `_ensure_published_version`.
- [x] Runs finish well under 30 minutes per brief, including self-tests. Evidence: the official version 12 run took 193 s in total (extraction 103.5 s, self-test ~84 s); live extraction-only runs took 91 to 222 s (`traces/f040-*`, `f041-*`). Re-check on the larger hidden briefs.
- [x] Only the bank's tool API is used by the phone agent; the phone-agent model is unchanged; `agent_config` is not sent. Evidence: tools come only from the OpenAPI file; `builder/freya.py` is identical to the kit; the trace lines `sent_agent_config: absent` / `sent_nulls: 0` (`test_submission_check.py`).
- [ ] Runs on Python 3.10+ from a fresh checkout; keys come from environment variables only. Keys: done (`llm.py`, `freya.py`, `run_trace.py` masking). Fresh-checkout run on Python 3.10: not yet tested.

## Generality

- [x] No rule, date, value, holiday or outcome name from any specific brief in code or prompts. Evidence: the literal leak scan in `tests/test_multi_step.py`.
- [x] Extraction and rendering work on a brief with a different layout and a different tool API (not yet a live agent run). Evidence: live extractions of `tests/briefs/changed-a` (changed values and tool contract) and `raw-a` (raw material) ended `status: ok` with `unmapped_items=0` and rendered with `--print` (`traces/f040-changed.print.log`, `traces/f040-raw.print.log`); the later `f041-raw` rerun left 3 unmapped items. Their reference specs are compared with `tools/compare_spec.py` (T-006b). `spec-synthetic` + `openapi-synthetic` render offline.
- [x] Handles an override memo, a code list and tables without crashing. Evidence: `tests/briefs/raw-a` (memo wins; CSV codes; holiday list), T-006b.
- [x] Tool field names and enums come from the OpenAPI file. Evidence: `tools_from_openapi.py`, with field names in the spec checked against `tool_contract`.
- [x] Every step's dialogue prompt is measured and reported in the trace (`prompt_estimate`, `budget`, `rule_placement`; target 1,200, limit 1,500). Evidence: `test_prompt_budget.py`, T-009.

## Safety and honesty

- [ ] No debt details before identity verification, where the brief requires it. Graph: `get_account` runs only in `account`, which is reached from `identity` or `identity_check` only when `identity_verified` is true; the self-test forbids it after a failed check. Chat: PUB-03 version 5 passed. Not yet proven over 3 scored runs.
- [ ] Promises recorded only after read-back and confirmation; correct product, date and amount, once. Code: `check_offer`, the read-back, the per-product attempt limit. Chat: PUB-01 version 10 recorded one correct promise. Not yet proven over 3 scored runs.
- [ ] The agent never claims a record that the tool did not confirm. Code: the post-hook `what_to_do_next`, the global success-evidence rule (F-030), the self-test honesty check. Live proof is pending.
- [x] Prompt-only rules are not described as guarantees. Evidence: every rule's tier is traced (`rule_placement`); `enforced_by` is honoured only when `enforcement_available` is true for the spec.
- [x] No API keys in the repo, traces or logs. Evidence: `.gitignore` (`env.sh`), `run_trace.py` masking, and the `no_secrets` check in `tools/submission_check.py`.

## Evidence

- [ ] Practice-case baseline and final scores recorded; no regression versus the baseline. The baseline is recorded (6/10). There is no scored `run_cases.py` run of the current builder, only single chat cases ([`EVALUATION-AND-TESTING.md`](EVALUATION-AND-TESTING.md), Results log).
- [x] Static and unit tests pass: `python3 -m unittest`, 245 tests OK on the working tree, 2026-10-11. Re-run and re-count before every commit.
- [x] Each run has a trace: start/end time, every model call (model and one-line purpose), Freya IDs with step and tool counts, self-tests. Evidence: `run_trace.py`, `build.py`; checked by `tools/submission_check.py`.

## Submission (before Sun 20:00 UTC)

- [ ] Builder run on each hidden brief; one agent per brief; traces kept.
- [ ] Exports committed, e.g. `submission/hidden-1.workflow.json`, `traces/hidden-1.log`, `traces/hidden-1.spec.json`.
- [ ] `tools/submission_check.py … --verify-inputs --require-env` prints `SUMMARY: PASS` for each (see [`SUBMISSION.md`](SUBMISSION.md)). Rehearsal on Brief A, version 12 (reviewer run, without `--require-env`): `SUMMARY: PASS (19/19 checks passed, 2 warning(s))`, with the warnings being the `third_party_close` `platform_error` and the skipped key-value scan.
- [ ] Fresh checkout reproduces the run from the committed commit.
- [ ] Form sent with `team`, `repo`, `commit`, `run_command`, `workflows`, `traces`.
- [ ] No agent edited after its run.

## Done means

An unseen brief and tool file go in, and a working, policy-configured Freya agent plus its trace come out, reproducibly, with no hand edits.
