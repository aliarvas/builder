# SELF-TEST fix review

**Reviewer:** claude-reviewer · **Scope:** `git diff docs/SELF-TEST.md` against `reviews/SELF-TEST-audit.md` (12 findings), `tasks/SELF-TEST-fix-report.md`.
**Method:** I read the new document and checked each command, flag and limit against the code, the kit and `STARTER-KIT-FACTS.md`. Offline commands only: `build.py --help`, `run_cases.py --help` (no Freya call), `compare_spec.py --help`, `submission_check.py --help`, two `--print --spec` renders. No Freya, no model, no edits to the document.

> Disclosure: my two probe renders wrote `traces/reviewer-probe.print.log` and `.failed.log`. I deleted both right after (they were my own files; nothing else in `traces/` was touched).

## Decision: **düzeltme gerekli** (small): 12 of 12 findings are applied; one command in Step 1 does not run as written, and two statements overreach the tools.

## The 12 audit findings

| # | Audit finding | Applied? | Check |
|---|---|---|---|
| 1 | Two-way prompt gate | Yes | Step 1.3 last bullet. I ran the rule on the specs the builder renders (A, A+B, version 11, tagged A+B, every conversation node and global node): 0 violations (no-tool text present when `tools` is empty; each tool name in the prompt when `tools` is set). The "no tool" half is also a unit test (`test_multi_step.py` uses `CONVERSATION_NO_TOOL_RULE`). |
| 2 | `--print` vs `--print --spec`, `ANTHROPIC_API_KEY` | Yes | Tools table, env paragraph and the approval paragraph now say it correctly; matches the CLI help ("spec extraction still calls the model unless --spec"). The "T-006 will come" text is now past tense. |
| 3 | Extraction repeatability gate | Yes, with a wording problem (see B) | Step 2 and Step 8: two runs on separate slots, `compare_spec.py`, `extract_seconds`, model-call and repair counts, warning/unmapped counts, 5 minute target. |
| 4 | Synthetic spec needs its own OpenAPI | Yes | Step 1.2 names `tests/fixtures/openapi-synthetic.json`. I ran `--print --spec tests/fixtures/spec-synthetic.json brief-a.md openapi-synthetic.json`: `print: ok (nodes=25, tools=7)`. |
| 5 | Final Brief B command shape | Yes | Step 3.2 keeps A+B for the local run and marks the final shape `[TO-CONFIRM]`; consistent with `STARTER-KIT-FACTS.md`. The CLI accepts several briefs followed by the OpenAPI file. |
| 6 | Hang-up and 5xx steps | Yes | Step 5.3 and 5.4. 5.4 matches the F-023 design (read the call record before resending). See D for a missing how-to. |
| 7 | Different `now` with automatic assertions | Yes | Calendar section: three `now` values, `expected` recomputed, ledger assertion. |
| 8 | Brief B multi-product gate | Yes | Step 6.2 (PUB-11, 12, 13 separately with `--only`, `--reps 3`). |
| 9 | 10 vs 200 workflow limit | Yes | Step 3.3; both numbers named, `[TO-CONFIRM]`, rule independent of the limit. Matches the facts file. |
| 10 | Trace list and secrets | Yes | Step 4 list. Every item exists in the real trace (`start_utc`, `end_utc`, `total_duration_seconds`, input hashes, `model_call` lines with model/purpose/tokens/duration, `extract_seconds`, `nodes`, `global_nodes`, `steps`, `tools`, `published_version`, `self_test`, `status`). The `submission_check.py` flags (`--spec`, `--verify-inputs`, `--require-env`) exist in the help. |
| 11 | "First 10 teams" | Yes | Now "üst sıralardaki takımlar" in the opening list and the Step 8 title; matches facts line 69. |
| 12 | Hardcode scan | Yes | Step 1.4: AST leak test first, then fixture-derived literal comparison, framework allowlist with a reason. |

## Findings in the document

### A. MEDIUM — Step 1.2 commands omit the brief path and fail as written

The three bullets say "`--print --spec tests/fixtures/spec-brief-a.json` ve kit OpenAPI". `build.py` requires one or more brief files **and** the OpenAPI file: running it with only the OpenAPI file gives `error: provide at least one brief file followed by one OpenAPI file` (I ran it). The synthetic command works only with a brief path plus `openapi-synthetic.json` (I ran it). Write the full command lines, for example:
`python3 builder/build.py --print --spec tests/fixtures/spec-brief-a.json --slot selftest-a build-the-builder-v2/briefs/brief-a.md build-the-builder-v2/tools/openapi.json` (A+B: add `brief-b.md`; synthetic: any brief file and `tests/fixtures/openapi-synthetic.json`). Add that `--print` writes `traces/<slot>.print.log` (use `--slot`), so repeated runs do not overwrite evidence, and that the output is the workflow JSON on stdout.

### B. LOW-MEDIUM — `compare_spec.py` is described as comparing more than it does

Step 2 and Step 8 say the tool compares "provenance/override sonucu" and "coverage/provenance". The tool compares behaviour values only: identity fields and order, routes, outcome table, offer rules and calendar, special paths, tool fields, limits, required sentences, and `coverage.unmapped` (it ignores wording and provenance by design). The override result is visible through the values (a memo that changes a rule changes a number), not through provenance. It also takes `<extracted> <reference>`, with exit code 1 on any difference; for run-versus-run, one run acts as the reference. Reword: "değerleri karşılaştırır; override sonucu ilgili değerin değişmesiyle görünür", and say that provenance is checked by reading the spec, or by `submission_check.py` (`--spec`), not by `compare_spec.py`. A reader trusting the current text would believe a provenance drift is caught.

### C. LOW — "Testi hep bu komutla yap, ek bayrak kullanma" versus `--slot`

The table row says never to use extra flags with the official command, and the same document later relies on separate slots for two extraction runs (Step 2, Step 8). `--slot` is a CLI option and is needed to keep two traces. Say: "resmi koşuda ek bayrak yok; geliştirme prova koşularında `--slot` kullanılabilir (iz dosyası adını ayırır)". Also say which slot name a no-flag run uses (the trace name `brief-a` in the existing files shows it derives from the brief file name) so Step 4's `traces/<slot>.log` paths are findable.

### D. LOW — the manual chat steps cannot be done as written

Step 5.3 asks to read the ledger for `close_call`, but manual chat with a practice customer needs a practice session first (`POST /v1/practice/sessions` creates the customer; `GET /v1/practice/ledger/{customer_id}` reads it, header `x-team-key`; `STARTER-KIT-FACTS.md` line 82). The document never says so, and Step 5.1 passes `customerVariables` by hand. Add one line pointing to that table row and say that the customer id comes from the session. The same missing line makes the earlier, hang-up and 502 checks hard to reproduce.

### E. LOW — one claim to mark

Step 6 and the opening say a `rerun-if-slow` argument is an integer count; in `run_cases.py` it is the number of reruns allowed, each preceded by a 5-minute wait (the audit also said so). The table row prints `--rerun-if-slow N` without meaning. Write "N = en fazla N tekrar, her biri 5 dakika bekler" so it is not used inside the builder's 30-minute budget. The "Model yoğunluğu" bullet already warns about the slow median; add the cost there.

## Labels

`[TO-CONFIRM]` marks are in the right places: the final run command shape (Step 3.2) and the workspace limit (Step 3.3). One more belongs there: the claim in the opening that verification reruns "top teams from the commit" is `[VERIFIED]` in the facts file, fine; but the document's remark "Yeniden çalıştırmada skoru belirgin düşen takım elenir" is also in the facts (line 69), so no new label needed. No unlabeled new claim contradicts the code or the kit: the 6-minute self-test budget matches `DEFAULT_BUDGET_SECONDS`, the ordered short cases match `selftest.py`, and the secret list matches the trace masking.

## Short summary for the CTO

All 12 findings are in. Fix A before anyone runs Step 1 (as written it errors); B reword so nobody trusts a provenance check that does not exist; C, D, E are one-line additions. No Freya or model use is needed for any of these.


---

## Re-review (fix A–E)

**Method:** I ran the three Step 1.2 commands exactly as written, with only the `/tmp/...` redirect swapped for my scratchpad. They use `--print --spec`, so no model and no Freya call. I read every other new instruction against `api.md`, `score.py`, `run_cases.py`, `freya.py`, `freya_chat.py` and the real spec file. No edits. I deleted the three trace files my runs created (`traces/selftest-*.print.log`), so `traces/` is as it was.

### Decision: **merge edilebilir** (one LOW wording note)

- **A fixed, commands run.**

  | Command | Result |
  |---|---|
  | Brief A: `--print --spec tests/fixtures/spec-brief-a.json --slot selftest-a brief-a.md openapi.json` | `print: ok (nodes=26, tools=7)`, rc 0, 26 steps + 3 global |
  | A+B: `--slot selftest-ab brief-a.md brief-b.md openapi.json` | `print: ok (nodes=28, tools=7)`, rc 0, 28 + 5 global |
  | Synthetic: `--slot selftest-synthetic brief-a.md openapi-synthetic.json` | `print: ok (nodes=25, tools=7)`, rc 0, 25 + 1 global |

  Each trace says `model_calls: none`, `freya: not contacted (--print)`, `status: ok`. The trace names the document gives (`traces/selftest-*.print.log`) are exactly the files that appeared; the workflow JSON goes to stdout and the redirects parse as JSON. The unique `--slot` stops overwriting of earlier evidence, as intended.
- **B fixed.** The `compare_spec.py` paragraph now matches the tool (behaviour values, routes, outcomes, offer rules and calendar, special paths, tool fields, limits, required sentences; `coverage.unmapped` reported; exit code 1 on a difference; wording and provenance deliberately ignored). Step 8 names the second run as the reference, which matches the tool's `<extracted> <reference>` order. LOW wording: it tells the reader to read the `source`/`overrides` fields; in the spec the keys are the top-level `provenance` and `overrides` (plus `source` inside items). Say "`provenance` ve `overrides` alanları".
- **C fixed.** The official command row and the Step 3 paragraph now separate the flag-free official run from `--slot` in rehearsals, state that the slot derives from the brief stem (several briefs joined by `+`), and require the submitted `run_command` to be the flag-free command. This matches the existing traces (`brief-a`, `brief-a+brief-b.print.log`).
- **D fixed, endpoints verified.** Practice session `POST /v1/practice/sessions {"case": …}` returns `variables` (as `run_cases.py` line 86 uses it), `customer_id` comes from it; chat continues with the same `callId`; stop with `POST /api/v2/chat/end {"callId"}` (`api.md` line 250, `freya_chat.end_chat`); read the call with `GET /api/v2/call/{callId}`; read the ledger with `GET /v1/practice/ledger/{customer_id}` and header `x-team-key`, whose `calls` entries carry the tool name (`score.py`). The 5xx path now ties the call record and the ledger together. One small point: the document says to count `close_call` in `calls`; the kit scoring also requires `close_call` to be the **last** call, so a stage check that sees it exactly once and not last should be treated as a failure; add "ve son çağrı olmalı" if you want parity with the scoring rule.
- **E fixed.** `--rerun-if-slow N` is explained as at most N repeats with a 5-minute wait before each, and kept out of the builder's 30-minute self-test.

No new claim contradicts the code or the kit. `git diff --check` on the document is clean.
