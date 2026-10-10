# T-008 — Trace and submission compliance check

**Owner:** codex-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

## Why

Submission is scored on the exported workflow, and the top teams are re-run: a reviewer agent compares trace, code and agent. A trace that misses a required item, or contains a key, is an avoidable loss. Read `build-the-builder-v2/README.md` (submission and trace sections), `docs/STARTER-KIT-FACTS.md` (submission, trace contents, form fields), `docs/SELF-TEST.md` step 4 and 8–9, `reviews/SELF-TEST-audit.md` findings 10–11, `builder/run_trace.py`, `builder/build.py`.

## Deliverables

1. **`tools/submission_check.py <trace.log> <export.json> [--spec <slot>.spec.json]`** (offline, stdlib): checks and prints PASS/FAIL per item:
   - trace has start and end time, total duration, each model call (model + purpose), extraction duration, Freya `workflow_id`, `agent_id`, published version, step and tool counts, self-test lines and summary, final status;
   - no secret: `fak_…`, `sk-ant-…`, the bank team key value pattern, `Authorization`/`x-api-key` headers;
   - export file parses, has no `null`, no `agent_config`, matches the trace's workflow id when present, and its step count matches the trace;
   - the extracted spec file named in the trace exists;
   - total time under 30 minutes.
2. Fill any gap in the builder's trace that the kit requires (input file hashes, model names, timings, versions). Keep `run_trace.py` redaction.
3. Offline tests with a good trace, a trace with a key, a trace missing items, a mismatched export.
4. A short `docs/SUBMISSION.md` section or update (only if the kit asks for something we do not yet produce): what files go into the submission per brief, which command produces them, and how to run the check.

## Constraints

Python 3.10+, stdlib only. No Freya, no commit, no `env.sh`. Do not touch `builder/extract.py`, `builder/llm.py`, `builder/selftest.py` (under review) unless the trace needs one extra line there; say so in the report. Report in `tasks/T-008-report.md`.
