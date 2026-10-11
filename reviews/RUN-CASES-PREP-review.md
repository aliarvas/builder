# RUN-CASES-PREP review (Codex)

**Reviewer:** claude-reviewer · **Scope:** `tools/run_all_cases.py`, `tests/test_run_all_cases.py`, `tasks/RUN-CASES-PREP-report.md`, against the kit's `build-the-builder-v2/tools/run_cases.py`, `tools/score.py`, `freya.py`.
**Method:** offline. Read the kit runner line by line and compared flags, output shape and failure behaviour; ran the wrapper's `--dry-run` from a different directory and with no Freya variables set, and its real mode with the variables missing (it stops before any file or request). `python3 -m unittest tests.test_run_all_cases`: 4 OK. No Freya, no kit run, no key read, no edits.

## Decision: **düzeltme gerekli** (small: three summary/resume honesty problems; the command construction, dry run, slot stop and no-retry behaviour are right)

## What I verified

| Check | Result |
|---|---|
| Kit flags | `run_cases.py <agent_id> --cases F --brief A\|B --reps N --out PATH [--style S] [--rerun-if-slow N]` exactly matches the kit's argparse. Styles `pieces corrects talkative asks_back in_words` equal the kit's `STYLES` keys; `baseline` correctly passes no `--style`. `--brief B` selects PUB-11..13 and `--brief A` the ten others (public set: A 10, B 3). Each suite uses its own agent (A agent for A, cumulative A+B agent for B). `--only` is unused. |
| `--dry-run` | Prints the 12 commands, makes no file and no request: I ran it from another directory with `FREYA_API_KEY` and `FREYA_BANK_TEAM_KEY` unset; it printed the commands and created nothing. It runs before the environment check, so it needs no key. It does read the slot map (ids only). |
| Keys | The wrapper only tests `os.environ.get(NAME)` for the two names and never prints or writes a value; the commands contain agent ids only. The slot map file is parsed whole but only `workflow_id` and `agent_id` are used (its keys are `agent_id, version, workflow_id`). The child output (log files) can contain only what the kit prints; the kit prints no header. |
| A+B slot missing | `load_agents` raises, `main` returns 2 with "slot 'brief-a+brief-b' is missing", before any file is created (checked live: the real map has only `brief-a`). It never falls back to the A agent. |
| No automatic 5xx retry | The loop stops at the first non-zero exit and returns its code; there is no retry loop. `--rerun-if-slow` defaults to 0, is only passed through when set, and the help says each discarded run waits five minutes (the kit's slow-run discard, not a 5xx retry). |
| Counts | 6 variants × 2 suites × 3 reps = 36 simulations; (10 + 3) cases × 3 reps × 6 variants = 234 case-repetitions; the manifest's `13 * reps * styles` matches. The 3–11 minute scaling gives 70–257 minutes (excluding the 5-minute waits), as the report says. |
| Result tree | `results/<label>/{manifest.json, <suite>-<style>.json, .log, summary.tsv, summary.md}`; each command has its own `--out`. The kit's own `.personas.json` and `build-the-builder-v2/results/log.jsonl` are git-ignored. |
| Summary shape | `all_rows` (list per repetition of rows with `id, pass, failed, call_id`) is exactly what the kit writes; one summary row per case and repetition. |

## Findings

### 1. MEDIUM — resume can attribute old results to a new agent (`main`, `build_jobs`)

A finished job is skipped when `job.output.exists()`. The file name has only suite and style; the agent id, the reps and the style options are not compared, and the manifest is **overwritten** on every start with the *current* agent ids. Case: run, rebuild the agent (new ids or a new published version), start again with the same `--run-label` → the old results are skipped and the manifest and summary present them as results of the new agent. The report says "existing valid output files", but nothing validates them (not even that the JSON parses).
**Fix:** on skip, read the output and require `agent_id == job.agent.agent_id` and `runs == reps`; otherwise stop with a clear error (or move the file to `*.stale`). Do not overwrite an existing manifest whose agents differ; stop instead. Also record the slot `version` and the git commit in the manifest, so the evidence names the build it tested.

### 2. MEDIUM — the summary counts rows, not customers (`write_summary`)

The kit scores a customer only if **all** repetitions pass (`final[...]["pass"]`, "a customer counts with 3 of 3 runs"). The wrapper's footer says "Overall passes: 200/234" (rows) and ignores the kit's `final` block, so the headline number is not the competition number and can look much better than the real result.
**Fix:** read `final` from each output: per suite and style print `customers passed all N reps: x / 13` (or /10, /3), and list the customers that failed with their `passes/runs`; keep the per-row table as detail. Say in the header that the all-or-nothing line is the one that counts.

### 3. MEDIUM — ledger-based policy failures are shown as `policy: PASS`

`score_ledger` also checks policy from the ledger ("`get_account`/`create_promise` called before identity was verified", "identity or account tools used although the customer was not on the line"). The wrapper puts every non-`conversation:` failure in the **ledger** column and leaves policy as PASS, so a policy breach reads as "ledger FAIL, policy PASS". It is also not true that policy was verified clean when the judge passed and the ledger found such a breach.
**Fix:** classify those two messages (match on `before identity was verified` and `although the customer was not on the line`) as `policy: FAIL`; keep the rest as ledger. The header note about the combined judge is correct and should stay.

### 4. LOW — result paths are relative to the caller's directory, the kit runs in the repo root

The kit command runs with `cwd=ROOT` and `--out results/<label>/...`, but `run_dir.mkdir`, the manifest, the logs and the summary use `args.results_root` relative to the *current* directory (only the slot map path is made absolute). Run from another directory and the kit writes under the repo, while the summary looks in the wrong place (every job looks "missing"). Make `--results-root` absolute against `ROOT` before building jobs.

### 5. LOW — a missing or unreadable job disappears from the summary

`summary_rows` skips missing outputs and swallows JSON errors silently, so a stopped or damaged run gives a short but clean-looking summary (`Rows: 78`). Add an "incomplete jobs" list (suite/style with no valid result, and why) to `summary.md` and the manifest; print the number of expected versus found rows.

### 6. LOW — the 5xx hint is not reliable

The kit's own bank calls (`score.http`) catch `HTTPError` and return the error body as JSON, so a 5xx from the bank mock does not raise a message with the code: the kit then dies with a `KeyError` and the wrapper's regex finds no "5xx" and prints no hint. Freya platform errors (`... -> 502: ...`) are matched. The pattern `\b5(?:02|03|04)\b` can also match an amount or an id fragment in the printed case lines. **Fix:** print the "inspect the call record and the ledger first, then resume with the same label" advice on **every** non-zero exit; keep the regex only to say "looks like a platform 5xx".
Related note for the operator (not a bug): the kit writes `--out` only after all reps finish, so a failure in repetition 2 or 3 loses the finished repetitions of that job; the resume repeats the whole job on fresh practice sessions.

### 7. LOW — hygiene and checks

- `results/` (top level) is not in `.gitignore`; only the kit's `build-the-builder-v2/results/` is. The run directory holds call ids and ledger/judge texts, no keys. Decide whether to ignore it or to commit selected summaries; do not commit it by accident.
- The kit requires `FREYA_BANK_TEAM_KEY` of 16+ characters; the wrapper could check `len()` (without printing) and stop early with the same message as for a missing variable.
- The test file covers the command list, dry run, missing slot and the row split. Add tests for findings 1–4 (skip with another agent id; footer with `final`; policy mapping; `--results-root` from another directory).

## Answers to the CTO's questions

- **Right kit flags?** Yes (table).
- **`--dry-run` no request?** Correct; no file, no request, no key needed.
- **Keys read/printed?** Only presence is tested; values are never printed or written.
- **A+B slot missing stops?** Yes, offline, exit 2.
- **No auto retry on 5xx?** Correct; it stops at the first failure (hint reliability: finding 6).
- **`results/` structure?** As the report describes; fix finding 4.
- **Summary honesty?** Policy and honesty are marked together (`REVIEW`) when the judge fails, which is honest; but findings 2 and 3 make the headline number and the policy column misleading.

## Before the real run (CTO, with approval)

Both slots built and published; `FREYA_API_KEY` and a 16+ character `FREYA_BANK_TEAM_KEY` set by the user; start with `--styles baseline --reps 1` for a smoke run to see the result tree, then the full matrix. One simulation at a time; expect 70–257 minutes.


---

## Re-review (Fix: findings 1–7, `--styles baseline`)

**Method:** offline. Read the new `run_all_cases.py` (469 lines), ran `--dry-run` from another directory (`--styles baseline`, and an unknown style), and fed `write_summary` kit-shaped result files (one with a failed customer, one with a different `agent_id`). `python3 -m unittest`: **431 OK** (13 in `test_run_all_cases`). No Freya, no kit run, no key, no edits.

### Decision: **merge edilebilir** (two LOW notes)

| Finding | Result |
|---|---|
| 1 stale resume | A saved result is accepted only if it parses and its `agent_id`, `runs`, per-repetition case count (10 or 3) and `final` count match; otherwise the run stops with exit 2 ("choose a new --run-label or move the stale file"). An existing manifest is never overwritten when agents, versions, repetitions, styles, `rerun_if_slow`, git commit or commands differ. The manifest now carries each slot's `version` and the git commit. Checked with a result whose `agent_id` was another agent: it is reported as "agent_id differs (expected agent-b)" and not counted. |
| 2 headline score | `summary.md` starts with "All-or-nothing customer score (this is the competition score)": per suite and style, customers passing all N reps, total, and the failed customers as `id passes/runs` (my test: 9 of 10, `C0 2/3`). Per-repetition rows are below as detail. |
| 3 policy column | Messages containing `before identity was verified` or `although the customer was not on the line` give `policy: FAIL`; a judge failure still gives `REVIEW` for policy and honesty together (the combined verdict is not split). |
| 4 paths | `--results-root` is resolved against the repo root; the dry-run from another directory printed absolute `--out` paths under the repo and created nothing. |
| 5 incomplete jobs | A "Completeness" section lists expected versus found detail rows and every incomplete job with the reason; the manifest gets `incomplete_jobs`. |
| 6 5xx hint | Every non-zero exit prints "Do not blindly retry … inspect the call_id in the call record and ledger … the failed job restarts all of its repetitions"; the regex (`HTTP[ Error] 5xx` or `-> 5xx`) only adds "looks like a platform 5xx" and no longer matches a bare number. No retry exists. |
| 7 hygiene | `results/` is in `.gitignore` (line 26, `git check-ignore` confirms); a `FREYA_BANK_TEAM_KEY` shorter than 16 characters stops before any run (length only, value never printed); tests cover the fixes. |
| `--styles baseline` | `python3 tools/run_all_cases.py --styles baseline` builds only the two baseline jobs (A with `--brief A`, A+B with `--brief B`), no `--style` flag; an unknown style is a parser error. Without `--styles` the default is still baseline plus the five styles. |

Still true from the first review: kit flags exact, `--dry-run` offline and key-free, A+B slot missing stops with exit 2, no automatic retry.

### LOW notes

1. **Incomplete state is not on top of the summary.** When a job is missing or stale, the headline table simply lacks its row (my test showed only suite `a`), and "Incomplete jobs" comes below it. A reader of the first lines could take the table for the whole result. Add a first line like `INCOMPLETE: 1 of 2 jobs have no valid result` above the table when `incomplete` is not empty, and print the same line at the end of the run.
2. **The git commit does not identify the tested build while the tree is dirty.** The manifest records `HEAD`, but the builder code under test is uncommitted today. Two different working trees at the same HEAD pass the resume check. The slot `version` helps (a rebuilt agent bumps it), so this is only a note: also record `git status --porcelain` (or a hash of `builder/`) in the manifest. Also, a later commit of unrelated files (docs) changes HEAD and blocks the resume of an unfinished run; say so in the help text so the operator commits after the run, not during it.

### Before the real run (unchanged)

Both slots built and published; the user sets `FREYA_API_KEY` and a 16+ character `FREYA_BANK_TEAM_KEY`; first run `python3 tools/run_all_cases.py --styles baseline --run-label <date>-baseline` (3 reps by default; add `--reps 1` for a pure smoke test), then the five styles under a separate label; one simulation at a time.
