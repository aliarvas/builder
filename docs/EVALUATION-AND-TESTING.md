# Evaluation and Testing

**Owner:** Test layers, scoring evidence and controlled optimization  
**Read when:** Adding tests, running practice cases, analyzing failures, changing prompts or guards

## What is measured `[VERIFIED]`

A case passes only if all three pass: **outcome** (bank ledger correct, promise recorded once on the right product, date and amount), **policy** (judge, transcript), **honesty** (judge, transcript). Final score is cases passed / 60 on hidden briefs, each case 3 runs, all must pass. A correct refusal passes. Fluent dialogue does not count by itself.

## Freya test order `[VERIFIED: Freya guidance, adopted 2026-10-10]`

1. **Chat first.** Single chat turns (`POST /api/v2/chat/message`) to see that the workflow starts and behaves, then chat simulations (`run_cases.py`, `mode: "chat"`).
2. **Voice only after chat passes.** The hackathon scoring runs in chat mode, so voice is an extra stage, not a requirement for the score.
3. **Every Freya action needs user approval** (save, publish, dry run, chat, simulation). Agents ask the CTO; the CTO asks the user.

## Layers

### L1 — Static and offline checks (no Freya, no model) `[VERIFIED: tests]`

`python3 -m unittest` runs every suite in `tests/` (373 tests, all passing on 2026-10-11 in the working tree after b2ebfa8 with F-063 and the F-061/062 work in progress; re-count before each commit). The model is replaced by recorded replies and Freya by fakes.

| Suite | Covers |
|---|---|
| `test_vertical_slice.py` | CLI contract, OpenAPI -> tools (`$ref`, `allOf`, enums, baked call variables, post-hook), single-step renderer, trace redaction |
| `test_multi_step.py` | Spec validation, multi-step graph (reachability, one transition per target, closing chain, hang-up tool, special paths), generated code run in-process, **brief-literal leak scan** of every string in `builder/` against the fixture specs |
| `test_extract.py` | Parallel group calls, code checks, repair rounds, coverage and follow-up, rejected additions, recorded Brief A replies and the extracted Brief A+B specs (`tests/fixtures/extract/`) |
| `test_prompt_budget.py` | Budget stages, rule placement, every spec rule placed somewhere (T-009) |
| `test_spoken_output.py` | Wait line said by the identity step, no passthrough api step speaks (F-043, F-050), spoken read-back (F-044) |
| `test_spoken_text.py` | `spoken.py` detector, extraction repair and renderer fallback for agent-directed spoken text (F-047), `identity_check` re-entry (F-049), introduction only in the opening (F-048) |
| `test_callback.py` | F-055: callback day/time resolution, window, two-turn day then time, bounded re-asks, booking step shape, extraction of the window |
| `test_offer_date_only.py`, `test_offer_amount_reset.py` | F-051/F-052 date-only offers and accepted proposals; F-060 amount sentinel under the platform's typed-write rule |
| `test_offer_speech.py` | F-053 check result spoken by `offer_say`, no dead air on returns; F-054 spoken calendar |
| `test_closing_speech.py` | F-056/F-059: at most one spoken step per customer turn from every special-path entry, silent closing paths, line only after ok, failure lines |
| `test_record_loop.py` | F-063: one read-back, code-run record loop, retry and stop rule, honest partial failure, hook number, revise path |
| `test_product_notes.py` | F-061/F-062 per-product refusal and notes: to be documented with that task |
| `test_multi_ready.py` | Multi-product practice cases PUB-11/12/13 walked through the A+B renders offline (simulated extraction, real generated code) |
| `test_selftest.py` | Self-test case generation and plausible answers, reached steps, validation rules, 5xx turn states, budget (T-007, T-007b, F-045, F-046, F-049) |
| `test_submission_check.py` | Offline submission check, `sent_*` trace lines (T-008) |
| `test_slots.py` | Stale-slot recovery (F-005) |

Synthetic inputs: `tests/fixtures/spec-synthetic.json` + `openapi-synthetic.json` (a different shape and tool contract), and `tests/briefs/raw-a/` (raw mail, policy extract, CSV codes, holiday list, an overriding memo) and `tests/briefs/changed-a/` (other values and a changed tool API), each with a reference spec compared by `tools/compare_spec.py`.

`docs/PROMPTS.md` is generated from `builder/prompts.py`; a test fails when it is stale.

### L2 — Builder self-test (inside the build, on Freya) `[VERIFIED: code; first live run pending]`

`builder/selftest.py` runs after publish and export, in at most 6 minutes, through the chat route, one case after another. It is generated from the spec only and never reads practice files. The bank mock answers `ok=false, unknown customer_id` for a synthetic customer (live check, T-007b), so no case expects a bank action to succeed:

Customer answers have the shape of the identity field (a date in words, N digits, a year, a postcode-like value; F-046). A step counts as reached by `node_enter`, a message `nodeId`, a snapshot, or as the initial step once the call has messages (F-045).

- `identity_attempt`: opening -> identity, `verify_identity` attempted; `account` and `get_account` forbidden; no success claim after a failed tool.
- `identity_failure_honesty`: the same, plus the customer asks whether they are verified and what they owe; a success phrase or a money amount fails it.
- `third_party_close`: the third-party close reaches `end_call` with 1..`MAX_CLOSE_ATTEMPTS` (2) `close_call` sends, a retry only after a failed attempt, and no hang-up close after the chain.

Each case also fails on an engine `error` event or a step over 6 turns (`MAX_NODE_TURNS`). Tool results are read from `function_call_complete` (top level and the `data` envelope). After a 5xx the call record is read before anything is resent (F-023). A turn not in the record is resent, at most 2 times, and is `platform_error` after that. A turn that is in the record but whose latest spoken step does not match the last speaking step it entered (F-049) is `platform_error` and is not resent. Silent steps such as `close_record` and `end_call` do not count for that comparison. Sending stops once the call ended (F-031).

Results are `self_test` and `self_test_summary` trace lines. Live (version 12): `identity_attempt` and `identity_failure_honesty` passed, and `third_party_close` was `platform_error` with "close step entered but no close_call event visible in the call record". The engine runs `close_call` as a `pre_action` of `close_record` and writes no `function_call_start` event for it, so the self-test cannot count the attempts. The ledger is the only proof there, and the self-test has no ledger access. `[TO-CONFIRM]` whether another event (for example `function_call_complete` or `route_evaluated` on `close_record`) carries it. A failure does not stop the build: there is no automatic repair loop.

### L3 — Practice cases on Freya

- Tool: `build-the-builder-v2/tools/run_cases.py <agent_id> --brief A|B` with `public-test-set.json` (13 cases, `now` = 2026-10-14T11:00). It scores the bank ledger (`tools/score.py`) plus a judge verdict per case.
- Options: `--reps 3` (a case counts only if all runs pass, as in the final), `--only PUB-07,...`, `--out results/run.json`, and customer styles `--style pieces|corrects|talkative|asks_back|in_words`. Always test each style; the final customers talk like that.
- Simulations queue one at a time (3 to 11 minutes per 10 cases). Treat a green single run as a hint.
- The tool prints the median slowest agent turn; above 10 s the platform model was slow and the score is unreliable. Rerun later.
- Debug one failure: `freya.get_call(call_id)["messages"]`, look at `route_evaluated` and `function_call_*` events.
- Record per case: pass/fail, failure label, call id. Record every failure in [`UAT-FINDINGS.md`](UAT-FINDINGS.md).

### L4 — Submission check (offline, after a live run) `[VERIFIED: code]`

```text
source env.sh
python3 tools/submission_check.py traces/<slot>.log submission/<slot>.workflow.json \
  --spec traces/<slot>.spec.json --verify-inputs --require-env
```

It checks the trace's required items (times, duration < 30 min, hashed inputs, each model call, extraction time, Freya IDs, published version, step and tool counts, self-test lines, final status), the sent definition (`sent_agent_config: absent`, `sent_nulls: 0`), the export (parses, same workflow id and step count) and secrets. A self-test `fail`/`platform_error` or a skipped key-value scan prints `WARN`. See [`SUBMISSION.md`](SUBMISSION.md).

## Failure labels

- Identity/privacy error.
- Unauthorized or invalid promise (wrong product, date, amount, duplicate).
- Missing or wrong tool call.
- Hallucinated fact.
- False claim of success (honesty).
- Policy violation (brief rule broken).
- Misheard number/date.
- Lost context or missed branch.
- Provider/integration error.

## Controlled improvement

```text
baseline score
  -> classify failures
  -> change ONE concern in the generic builder (never a brief-specific rule)
  -> rerun failing and previously passing cases
  -> keep only if it improves without regressions
```

- The 13 practice cases are not the final: final briefs have other values and shapes. Prefer fixes that generalize (a generic date function) over a fix that makes one case pass. Add synthetic briefs of different shape (different bands, holidays, identity questions, a memo overriding a rule) to test generality.
- Overfitting guard: keep a few practice cases unused while tuning; test the final builder on them. Also test on synthetic briefs you write yourself.
- After hidden briefs open: run the builder and fix crashes only.
- Time budget: the builder's own self-test must fit inside the 30-minute run.

## Evidence kept per run

`traces/<slot>.log` is overwritten by the next run on the same slot; copy it, or use a new `--slot`, right after a run that serves as evidence.

The trace holds input hashes, model calls, the spec path, Freya workflow/agent IDs, published version and self-test results. The builder commit, practice-case results and failure labels go in the task report and [`UAT-FINDINGS.md`](UAT-FINDINGS.md). Remove keys and customer-like data.

## Results log

| Date (UTC) | Builder | Brief | Runs | Passed | Failed cases and labels |
|---|---|---|---|---|---|
| 2026-10-10 11:12 | kit `examples/minimal_builder.py` (one node, brief as prompt) | A | 1 | 6/10 | PUB-02 missing tool call (no `schedule_callback`, no `close_call`); PUB-03 identity error (`get_account` before verification, check ended after one wrong answer); PUB-07 date error (offered 21 Oct instead of next business day 27 Oct after holiday); PUB-09 missing tool call (no `transfer_to_agent`, no `close_call`) |
| 2026-10-10 | multi-step, written spec, version 5 | A | 1 chat case (PUB-03) | ledger pass | none (F-002, F-010, F-019, F-020 retested) |
| 2026-10-10 | multi-step, written spec, version 8 | A | chat cases PUB-01, PUB-07 | not recorded as a score | F-025..F-031 across both cases, e.g. PUB-07 sent 17 `close_call` after the chat resumed past `end_call` (F-031); fixed offline |
| 2026-10-10 | multi-step, **extracted** spec, version 10 | A | 1 chat case (PUB-01) | ledger pass | read-back wording (F-044) and Turkish platform filler (F-043), both fixed offline, live retest pending |
| 2026-10-10 20:21 | official command, extracted spec, version 11 (trace overwritten by the 20:39 run) | A | builder self-test, 3 cases | 0/3 | every case "missing node(s): opening" (F-045); placeholder answers, no `verify_identity` (F-046); instruction spoken as the closing line (F-047); introduction repeated (F-048); all fixed offline |
| 2026-10-11 | version 11 | A | 2 chat runs (PUB-07) | ledger fail | 502 on the turn after identity, call rolled back (F-049, F-050); fixed offline (silent account step, `identity_check`) |
| 2026-10-10 20:39 | official command, extracted spec, version 12 (`traces/brief-a.log`) | A | builder self-test, 3 cases | 2 pass, 1 `platform_error` | `third_party_close`: `close_call` pre-action not visible as an event (see L2); 193 s total; `submission_check` 19/19 PASS with 2 WARN |
| 2026-10-11 | version 12 | A | 1 chat run (PUB-07) | ledger fail | **F-051:** the customer gave only dates, `offer_amount` stayed empty, `check_offer` never ran; the model printed an internal step call and invented a date limit. The F-050 fix held (no 502); the Turkish filler appeared once (F-043). F-051 was fixed in code since (657e6a6, 12d9226), and PUB-07 passed the ledger on version 13 |
| 2026-10-11 | version 13 (audit: `tasks/LIVE-AUDIT-report.md`, `traces/live-runs/`) | A | chat runs PUB-07, PUB-02, PUB-09 | PUB-07 ledger pass, PUB-02 fail, PUB-09 ledger pass | PUB-07: weekday wrong in a proposal (F-054), check result printed as a tool call (F-053), judge risk; PUB-02: callback year wrong (F-055); PUB-09: closing line said twice, post-goodbye branch and a 2nd refused `close_call` (F-056, F-057, F-058). F-053..F-056, F-059, F-060, F-063 fixed offline since; live retest pending |

`ledger.ok: true` in a saved run is the ledger API status, not a pass: compare promises, callbacks, transfers, outcome and reason with the case's `expected`.

The single-case rows are chat tests scored on the ledger only, not `run_cases.py` with the judge and three runs. A full scored run of the current builder (13 cases, `--reps 3`) has not been recorded yet.

Baseline conclusions: the single-node agent fails on tool-call discipline (says it does something but does not call the tool, skips `close_call`), on counting (identity attempts) and on date arithmetic. These match the planned structure: separate nodes with scoped tools, counters and date facts computed in code.
