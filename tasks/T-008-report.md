# T-008 Report — Trace and submission compliance check

## Result

Implemented an offline submission gate for one trace/export pair and filled the two missing trace fields. No Freya request was made.

## Deliverables

### `tools/submission_check.py`

Usage:

```text
python3 tools/submission_check.py \
  traces/<slot>.log \
  submission/<slot>.workflow.json \
  --spec traces/<slot>.spec.json
```

The command prints `PASS` or `FAIL` for every item, prints an aggregate summary, returns `0` only when every check passes, and uses only the standard library.

Checks include:

- valid UTC start/end timestamps;
- explicit total duration and both recorded/timestamp wall time below 30 minutes;
- input SHA-256 records;
- model-call count and a model, purpose, and duration for every call;
- extraction duration;
- workflow ID, agent ID, published version, node/global-node/total-step/tool counts;
- self-test case lines, self-test summary, and final successful status;
- existence of the spec artifact named by the trace and agreement with `--spec` when supplied;
- parseable export, no recursive `null`, no recursive `agent_config`;
- workflow ID and total step count agreement between trace and export;
- no `fak_`, `sk-ant-`, configured secret value, bank-team-key assignment, or Authorization/API-key header in trace, export, or named spec.

### Trace gaps filled

- `builder/run_trace.py` now records `total_duration_seconds` from a monotonic clock on every successful or failed run.
- `builder/build.py` now records `steps`, equal to `nodes + global_nodes`, while preserving the individual counts.

Existing input hashes, per-model-call metadata, extraction timing, Freya IDs, published version, tool count, export path, self-test evidence, status, and UTC timestamps were already present and remain unchanged.

### Submission documentation

Added `docs/SUBMISSION.md` with:

- the workflow and trace files submitted per brief;
- the retained extracted-spec artifact;
- the official builder command;
- the offline checker command;
- required form fields and the no-hand-edit reminder.

## Offline tests

Added `tests/test_submission_check.py` covering:

- a fully compliant trace/export/spec set;
- secret exposure;
- missing trace fields;
- workflow-ID and step-count mismatch;
- export `null` and `agent_config` rejection;
- the 30-minute boundary;
- monotonic total-duration trace output;
- offline builder trace total-step output;
- CLI PASS summary and exit code.

Commands run:

```text
python3 -m unittest tests.test_submission_check -v
python3 tools/submission_check.py --help
python3 -m unittest discover -s tests
python3 -m py_compile tools/submission_check.py builder/run_trace.py builder/build.py
git diff --check
```

Result: full offline suite passed, 176/176.

## Constraints observed

- No Freya request.
- No commit.
- No `env.sh` access.
- No changes to `builder/extract.py`, `builder/llm.py`, or `builder/selftest.py`.

## Fix (review `reviews/T-008-review.md`)

**Owner:** claude (second developer).

1. **Finding 1 (no-null / no-agent_config moved to the sent definition).** `builder/build.py` now writes `sent_agent_config: absent|present` and `sent_nulls: <n>` right after the `tools` line, before validate/save, counted on the workflow the builder sends. Two small helpers `_count_nulls` and `_has_key`. claude-dev's T-009 lines (`rule_placement`, `budget`, `steps`) are untouched. `tools/submission_check.py` drops `export_has_no_null` and `export_omits_agent_config` and adds `sent_definition_clean` (both trace lines must exist and be `absent` / `0`). The export is checked only for parse, workflow id, step count and secrets. Checked on the real `submission/brief-a.workflow.json`: no false FAIL from `agent_config`/`null` and no secret pattern hit.
2. **Finding 2 (secret scan).** The team-key pattern accepts a quoted name (`"team_key": "..."`). New patterns: `Bearer <16+ chars>` and a key in a query string (`?apikey=`, `api_key`, `team_key`, `access_token`, `token`, 8+ chars; `{{template}}` placeholders are not matched). When `FREYA_API_KEY`, `FREYA_BANK_TEAM_KEY` or `ANTHROPIC_API_KEY` is unset, `no_secrets` stays PASS with `WARN: exact-value scan skipped: ... not set`; `--require-env` makes it FAIL.
3. **Finding 3.** `trace_self_tests` stays PASS but carries `WARN: self-test not passed: <case>=fail|platform_error`. The summary line counts warnings.
4. **Finding 4.** New `--verify-inputs`: re-hashes each file named on an `input:` line and compares with the trace; missing or changed file → `inputs_match_files` FAIL. (The review's `updated_at` within start/end idea was not added; the CTO asked only for the hash option.)
5. `docs/SUBMISSION.md`: check command now runs after `source env.sh` with `--verify-inputs --require-env`; explains WARN and why the export's own `agent_config`/`null` are not checked.

Tests (`tests/test_submission_check.py`): platform-shaped export with `agent_config` and `null` passes; sent nulls / `present` / missing line fail; quoted JSON, Bearer and query-string keys caught; template placeholder not flagged; missing env warns and `--require-env` fails; exact env value caught; failed self-test passes with WARN (also in CLI output); `--verify-inputs` equal, changed and missing file; builder `--print` trace has `sent_agent_config: absent` and `sent_nulls: 0`.

```text
python3 -m unittest tests.test_submission_check   # 15 tests OK
python3 -m unittest                               # 201 tests OK
git diff --check                                  # clean
python3 tools/submission_check.py traces/brief-a.log submission/brief-a.workflow.json --verify-inputs
```

The last command runs on the old live trace (made before T-008 with `--spec`), so it still FAILs on fields that trace never had (`total_duration_seconds`, `model_call`, `steps`, self-test lines, `sent_*`). The export checks pass, and `inputs_match_files` passes. A full PASS needs a new approved live run.

Constraints: no Freya call, no commit, no `env.sh` access; `builder/selftest.py` and `builder/workflow.py` not touched.
