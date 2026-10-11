# RUN-CASES-PREP report

Prepared an offline-safe runner for SELF-TEST Step 6. No Freya request was made.

## One-command plan

After both workflows have been built and `.freya-agents.json` contains the cumulative slot, run:

```bash
python3 tools/run_all_cases.py
```

Preview the exact commands without creating files or making requests:

```bash
python3 tools/run_all_cases.py --dry-run
```

The current local slot map contains:

- Brief A slot `brief-a`: workflow `b0bdd6e6-3b68-48ae-a319-ac7dc1cf06f9`, agent `35816296-c6f7-45ff-a281-d41af8ca79fc`.
- Cumulative A+B slot `brief-a+brief-b`: not present yet. The runner stops before execution until this slot exists; it never substitutes the A-only agent for the multi-product cases.

At execution time the runner reads only `workflow_id` and `agent_id` from those two slot records. It does not read credential values from the file or print environment values. Alternate slot names can be selected with `--a-slot` and `--ab-slot`.

## Matrix and kit flags

The runner serializes twelve kit commands because the workspace permits one simulation at a time:

- A agent: `--brief A`, the ten cases PUB-01 through PUB-10.
- Cumulative A+B agent: `--brief B`, the three multi-product cases PUB-11 through PUB-13.
- Each group uses `--reps 3` and explicit `--cases build-the-builder-v2/public-test-set.json`.
- Each group runs once at baseline and once for every kit style: `pieces`, `corrects`, `talkative`, `asks_back`, and `in_words`.
- Every invocation has a distinct `--out results/<date-time>/<suite>-<style>.json`.
- `--rerun-if-slow` defaults to zero. It can be enabled explicitly, but each discarded slow run waits five minutes and adds another simulation, so it should not be confused with a 5xx retry.

This is 6 conversation variants, 36 simulations and 234 case-repetition rows. Existing valid output files are skipped when the same `--run-label` is used, so an interrupted matrix can resume without repeating completed jobs.

## Results and summary

The default run directory is `results/YYYY-MM-DD_HHMMSS/` and contains:

- `manifest.json`: selected slots, workflow/agent IDs, exact commands, counts, duration basis and cost estimate;
- one raw kit JSON and captured console log per suite/style;
- `summary.tsv` and `summary.md`: one row per case and repetition, with ledger, policy, honesty, overall result and call ID.

The unmodified kit runner will also maintain its own generated `.personas.json` and `results/log.jsonl` beneath `build-the-builder-v2/`, as documented by its source. The wrapper does not edit kit source or configuration; the complete per-run evidence remains under the top-level dated result directory above.

The kit provides ledger failures separately but returns a single combined conversation-judge result for policy and honesty. A successful judge result is shown as `PASS` in both columns. A combined judge failure is shown as `REVIEW` in both columns instead of inventing which dimension failed; the call transcript must be inspected to separate them.

## Duration and cost estimate

The kit states that ten customers take 3-11 minutes. Scaling that published range by 234 customer calls gives a planning range of about 70-257 minutes (1.2-4.3 hours), excluding slow-run repeats and five-minute waits. It is only a proportional estimate; simulation setup and the three-case B group can make the actual duration differ.

The kit publishes no simulation price, so the default cost estimate is `unknown`. If an approved per-call USD rate becomes available, `--cost-per-call <rate>` records `234 × rate` in the manifest without changing execution.

## 5xx procedure

The runner stops at the first failed kit command, preserves its log and all completed JSON results, and does not automatically retry a 5xx. First use any saved `call_id` to inspect the call record and the corresponding ledger, determining whether the turn or tool call was already processed. Only after confirming it was not processed should the operator rerun with the same `--run-label`; completed suite/style outputs will be skipped. Platform failures stay separate from agent failures.

## Verification

- Read `build-the-builder-v2/tools/run_cases.py` and `build-the-builder-v2/README.md`; the wrapper uses only their documented flags.
- `python3 -m unittest tests.test_run_all_cases -v` — 4 tests passed.
- `python3 -m py_compile tools/run_all_cases.py tests/test_run_all_cases.py` — passed.
- `python3 -m unittest` — 410 tests passed.
- `git diff --check` — passed.
- A real `python3 tools/run_all_cases.py --dry-run` made no request or files and reported the expected missing `brief-a+brief-b` slot.

No kit file, `env.sh`, or credential was read or changed. No Freya request or commit was made.

## Fix

Applied all findings from `reviews/RUN-CASES-PREP-review.md`.

### First run

The first approved live run should use only the normal conversation style (three repetitions remain the default):

```bash
python3 tools/run_all_cases.py --styles baseline --run-label <date>-baseline
```

Its offline preview is the same command with `--dry-run`. After baseline passes, the five styled variants can use a separate label:

```bash
python3 tools/run_all_cases.py \
  --styles pieces corrects talkative asks_back in_words \
  --run-label <date>-styles
```

Calling the runner without `--styles` still selects baseline plus all five styles.

### Resume and evidence integrity

- A saved result is skipped only after its JSON parses and its `agent_id`, repetition count, per-repetition case count, and final customer count match the planned job.
- The manifest now records each slot's workflow ID, agent ID and local published version, plus the repository git commit.
- An existing manifest is never overwritten when its agents, versions, options, commands or git commit differ. The operator must select a new `--run-label`.
- Relative `--results-root` paths are resolved against the repository root, matching the kit subprocess working directory.

### Honest scoring and incomplete runs

- `summary.md` now leads with the kit's all-or-nothing `final` score per suite/style. It lists each failed customer's `passes/runs`; per-repetition rows remain supporting detail rather than the headline score.
- The two ledger messages proving tools were used before identity or while the customer was not on the line are classified as `policy: FAIL`, not ledger failure with policy PASS.
- Missing, malformed, stale or incomplete job results are listed with reasons. The summary shows expected versus found detail rows, and `manifest.json` carries the same `incomplete_jobs` list.

### Failure handling and hygiene

- Every non-zero kit exit now prints the instruction to inspect the call record and ledger before retrying, regardless of whether the output visibly contains a 5xx. A strict platform-error pattern only adds a 5xx hint; it no longer mistakes standalone amounts or IDs for status codes.
- The message explains that resuming restarts every repetition of the failed job because the kit writes `--out` only after that job completes.
- Top-level `results/` is now ignored by git.
- Real mode verifies that `FREYA_BANK_TEAM_KEY` is at least 16 characters without printing its value.

### Verification

- `python3 -m unittest tests.test_run_all_cases -v` — 13 tests passed, including findings 1-7, manifest version/commit evidence, and `--styles baseline`.
- `python3 -m py_compile tools/run_all_cases.py tests/test_run_all_cases.py` — passed.
- `git diff --check` — passed.
- `python3 -m unittest` — 431 tests ran; 428 passed and three unrelated concurrent workflow assertions failed in `test_closing_speech`. No RUN-CASES-PREP test failed.

No Freya request, simulation, commit or `env.sh` access was made.
