# T-010 review (claude-dev, offline self-check and repair)

**Reviewer:** claude-reviewer · **Scope:** `builder/selfcheck.py`, `builder/selfcheck_calendar.py`, `builder/extract.py`, `builder/build.py`, `builder/callback.py` (import line), `tests/test_selfcheck.py` and the changed tests, `tasks/T-010-*.md`, against `build-the-builder-v2/docs/{workflow-format,tools-and-code}.md`.
**Method:** offline. Read all new code; ran `python3 -m unittest` (**472 OK**, 31 s); ran the self-check on 18 specs (traces/ and fixtures) under six `now` values; ran four mutations of the rendered Brief A workflow. Scratchpad probes only. No Freya, no model call, no key, no edits (only this file).

## Decision: **düzeltme gerekli** (small, no blocker for the build: the loop is safe and never stops the build; but two false-pass gaps and one date-dependent false failure should be fixed before the self-check is trusted as evidence)

## What is right

- **`json` not pre-loaded:** `exec(code, {"vars": ...})` has no `json`, so the F-064 guard bug (missing `import json`) was a real catch. The fix (`import json` at the top of the guard code, `callback.py`) is minimal and correct. Kit doc says `json`, `re`, `datetime` "can be imported", so this matches.
- **Typed writes:** `run_code` compares `vars` before/after, rejects a changed value that does not fit its declared field and restores the old value (F-052/F-060 reading). A mutation that shrinks an enum is caught (11 scenarios fail).
- **`__previous__`:** `enter_special` stores the interrupted step, `_target` resolves `__previous__`; `excluded_nodes` honoured; per-step `special_<id>_at_<step>` entries used.
- **Tool vs api step:** model tool calls store `<tool>_args.<field>`; api steps use the pre-action and its `response_mapping`; counters follow the `_success/_failure_count` naming.
- **Spec/builder split is conservative:** only an outcome row with no `on` state that no scenario ends with is a SPEC problem; everything else is BUILDER (trace warning). A row counts as reached even if its scenario **failed**, so a builder bug in a reachable row is never sent to the model. A returning-path-with-tool row (AB-FRESH risk 5) is BUILDER. I tried special paths limited to `third_party` and to `confirm_record`: scenarios exist, no false SPEC problem.
- **Loop:** at most `MAX_SELF_CHECK_ROUNDS` = 2; a self-check exception is logged and breaks the loop; `deadline` is checked before every round; a repair that breaks the normal checks restores all replies and keeps the last good spec (`rejected` line); no round runs with `--spec` (no hook passed). The build cannot stop because of it (`_trace_self_check` and `_self_check_problems` catch everything).
- **Leak:** no brief, practice or outcome word in `selfcheck.py` / `selfcheck_calendar.py` (grep: only schema words and the role words `refused`/`failed` taken from `product_notes`); the leak test is green; the one allowance (`"type"`, JSON-schema key) is a real schema key.
- **Trace / `submission_check`:** `key: value` lines; `_line_values` ignores unknown keys; a test feeds the new lines to `check_submission` and passes. The reason text carries step names and test values (`sim-…`), no key.
- **Speed:** all 18 specs in a few seconds; the A+B self-check is well under 10 s.

## Findings

### 1. MEDIUM — "ideal extraction" is not checked against the step's extraction fields (false pass)

`Simulator.turn` does `self.vars.update(extracted)`. The typed-write rule is applied only to values written by **code steps**, and the extraction is never compared with the waiting node's own `extraction_schema`. Probe: I removed the refusal-intent field from every node's `extraction_schema` of the Brief A workflow (nothing could ever extract it). Result: **0 failing scenarios**; the refusal scenario still "closes" because the simulator writes the value itself. The same holds for a step whose schema lacks the variable its transitions read, or whose enum lacks the value (only the code-written case is caught: a shrunk enum is caught only through the code step path, not through the turn).
**Fix:** in `turn`/`tool_turn`, for every extracted name require (a) the waiting node declares a field of that name and (b) `fits(value, field)`; otherwise record a problem `"<step> cannot extract <name>=<value>"` (BUILDER). Add a mutation test (field removed → scenario fails).

### 2. MEDIUM — the independent calendar ignores `latest_on_non_business_day = "next"` (date-dependent false failure)

`selfcheck_calendar.deadline` handles only `previous`; for `next` it leaves a non-business deadline as is, while the builder moves it forward. Probe on `tests/fixtures/spec-synthetic.json` (20 calendar days, `next`): with `now` = 2026-10-26 the scenario `offer_after_deadline` fails ("promises 2026-11-16, the spec gives 2026-11-15" — a Sunday); with the other five `now` values it passes. So the real build date decides whether the trace shows a builder failure, and a hidden brief with `next` gets noise or, worse, a *correct* builder is accused. Because it is BUILDER-class, no repair is triggered, but the trace and the "self_check passes" evidence become unreliable.
**Fix:** `next` → move forward to the next business day (and honour `keep`); add a test with `now` such that the deadline falls on a weekend and a holiday, for each of `previous`/`next`/`keep`.
**Related (LOW):** `run_selfcheck` uses the real date when `now` is None (`time.strftime`), so the same spec can pass on Monday and fail on Friday. Run the self-check for a fixed set of `now` values (a business day, a Friday, a weekend, the eve of a holiday of the spec) or at least log the `now` used in `self_check_summary`.

### 3. MEDIUM — a self-check repair is accepted even if it adds new problems

After a self-check repair, `validate(True)` uses the **soft** flags of the last round (spoken, optional, reach). A reply that fixes the reported row but breaks something that is soft is therefore **accepted** and only becomes a warning, whereas the earlier spec was clean. Also nothing compares the next self-check with the previous one: a repair that leaves the same problem plus a new one is kept.
**Fix:** accept the repaired spec only if `len(new warnings) <= len(old warnings)` and the next self-check has no problem that the earlier one did not have; otherwise restore (as for hard failures). Log both counts in `self_check_repair`.

### 4. LOW/MEDIUM — spec problems the task asked for are not detected

The task lists "a missing state or path, a value that cannot be routed" as spec problems. The only SPEC check is the unreachable outcome row (same condition as F-065's `_check_reach`, so a repair is requested twice for the same row: up to 2 normal reach rounds, then up to 2 self-check rounds). Rows with an `on` state are counted as reached without being played (known; hangup, turn limit, account failure, unclear callback answer are not scenarios), and "dead end: the turn has no route" is BUILDER. This is acceptable for layer 1 as long as the report says so; the plan "families (a)" should add them. Suggest: a dead end whose input value comes **from the spec** (a routed value that no transition handles) should be SPEC with a spec path; today it only warns.

### 5. LOW — environment fidelity

- `exec` accepts any import (`import os` in a code step passes; mutation D). The platform names `json`, `re`, `datetime` only. Add a restricted `__import__` that allows those three and records a problem otherwise.
- `route()` returns the first holding transition and never applies the platform's **merge of same-target transitions** (OR; one unconditional wins). A duplicate target with an `always` condition appended (mutation C) is not caught. The builder rule "one transition per target" is enforced elsewhere, so this is only a gap in fidelity; a cheap check `len(targets) == len(set(targets))` per node in the simulator closes it.
- `BANK_WRONG_ANSWERS = 3` is the kit's mock bank behaviour, written as a constant in `builder/`. It is a simulator parameter, not a policy, and the identity scenario also uses the bank's returned `attempts_left`, so it should be fine on another bank; say so in the comment.
- `Simulator._identity_tool` picks the first tool whose mapping ends with the verified field; one scenario step, not general. Fine for now.

### 6. LOW — time guard

The guard is checked before each round only. A round is one parallel batch of model calls (each can take minutes), so a round started at minute 19 can end near the 30-minute limit with publish and chat tests still to do. Suggest `deadline = 15 min` or an estimated round length (use the duration of the extraction's first repair round).

### 7. LOW — docs and tests

- `docs/UAT-FINDINGS.md` (changed): the existing entry **F-065** (sandbox down) was **renumbered to F-067**; `F-065` is also the name of the reachability work and is cited in the reviews and in code comments. Check that no file cites the old number.
- Tests: add (1) the extraction-field mutation (finding 1), (2) a `next` deadline on a weekend (finding 2), (3) a repair that adds a soft warning (finding 3). The `KNOWN` list in `test_selfcheck.py` is a good pattern.

## Answers to the CTO's focus questions

1. **Faithful simulator?** Yes for `json` not pre-loaded, typed writes in code steps, `__previous__`, tool args, counters. **No** for extraction (finding 1), merged transitions and import limits (finding 5): these can give false passes.
2. **Spec vs builder:** safe (conservative); a builder bug is never sent to the model; the loop is bounded (2 rounds + time guard). Under-detects spec problems (finding 4); finding 2 shows how a wrong helper can only produce BUILDER noise, not a repair.
3. **Repair loop:** max 2 rounds, last good spec kept, never stops the build, `--spec` no repair. Add finding 3 (soft acceptance) and 6 (time).
4. **Leak:** clean.
5. **Trace / submission_check:** accepted, test present.

## Before the live check (CTO, with approval)

After findings 1–3 are fixed: a fresh Brief A and an A+B build; the trace should show `self_check_summary … spec=0` (A+B: builder=2 for the AB-FRESH risk-5 rows). Then a PUB-02 chat for the third-party close (`import json`).


---

## Re-review (Fix: points 1–7, multi-now play, repair accept/reject rule)

**Method:** offline. Read `tasks/T-010-report.md` "Fix (review T-010)" and the new `extract.py` loop; `python3 -m unittest`: **484 OK** (43 s). Re-ran my four mutations and the six-`now` probe, ran the build-mode self-check (no `now`) on five specs, and added one new mutation (a lost transition). Scratchpad only; no Freya, no model, no env, no edits.

### Decision: **merge edilebilir** (one MEDIUM-LOW classification note and three LOW notes; none blocks)

### My 7 points

| # | Result |
|---|---|
| 1 extraction not checked | **Closed.** My mutation (refusal field removed from every step) now fails `refusal_refuses_to_pay`, `refusal_refuses_to_talk`, `multi_refuse_one` ("negotiate cannot extract …"); an out-of-enum value at `confirm_record` now adds `cannot extract approval_state=…`. No repo or live spec gained a failure. |
| 2 `next`/`keep`, multi-now | **Closed.** The synthetic spec passes under all six `now` values (it failed on 2026-10-26 before). Build mode plays the build's `now` plus the last business day before a non-business day and the eve of the next spec holiday; Brief A: 87 scenarios, 0.9 s; A+B fixtures ≈1–1.6 s; five specs together 4.8 s. Extra-`now` failures are listed as `<id>@<date>`; the summary ends with `now=… extra_nows=…`; repair messages de-duplicated by path. Results on the repo specs are unchanged (known gaps only). |
| 3 repair accept rule | **Closed.** Accepted only if the normal checks pass, no *new* warning (set compare) and no self-check problem at a new spec path; otherwise replies are restored. Logs show `accepted warnings=A->B problems=C->D` or the reason for the rejection. Tests: new-warning repair rejected, second-path repair rejected, 13:00 repair accepted. |
| 4 spec problems | **Closed as stated** (dead end on a routed spec value, with the spec path). The report lists what layer 1 cannot see; that list is honest. See note A for a side effect. |
| 5 fidelity | **Closed.** `import os` now reported (my mutation: `opening_unclear` fails); an extra same-target transition with `always` is reported (4 scenarios fail); `BANK_WRONG_ANSWERS` comment says it is a simulator parameter. |
| 6 time guard | **Closed.** 15 minutes, plus "now + slowest repair round so far" must fit; test with a fake clock. See note C. |
| 7 docs/tests | **Closed.** Docstring renumbered to F-067; new tests cover points 1–3, 5, 6. |

### Notes

**A. MEDIUM-LOW — a lost transition is classified as SPEC and sent to the model.** Mutation: I removed the negotiation transition for a close value from the rendered workflow (a renderer-bug shape). Result: `refusal_refuses_to_pay` etc. fail as **SPEC** with path `negotiation.close_values[0]`, so a builder rendering bug would trigger a model repair of the spec. The new accept rule and the 2-round limit make the damage bounded (a repair that changes nothing useful is dropped, but costs model calls and time), yet it breaks the principle "a builder bug never goes to the model". The value is in the spec and the builder renders a route for every spec value, so "step extracts it, no route" is far more likely a builder fault than a spec fault.
**Fix:** keep it BUILDER unless the spec itself is inconsistent (the value is missing from the step's extraction enum while it is listed as a route, or the value appears in two route lists). Or: SPEC only if the same value is routed at **no** node of the workflow *and* another scenario reaches an unrelated row through the same step.

**B. LOW — an unchanged warning reworded counts as new.** The compare is on `(path, message)`; a repair that rewords an existing warning is rejected. Safe direction (keeps the old spec); compare on path plus a normalised prefix, or accept when the number of warnings at that path does not grow.

**C. LOW — the estimate is 0 before any repair round has run.** If no extraction repair happened, the first self-check round is guarded only by the 15-minute deadline (a round of several minutes can still fit). Acceptable; a default estimate (e.g. 90 s) would remove the gap.

**D. LOW — the build's own `now` may be a weekend** (today is a Sunday): the extra moments cover Friday and a holiday eve, but a Saturday/Sunday `now` is only played when the build itself runs then. Fine, since the build's `now` is always played.

Optional follow-ups (not required): the repeat-repair of the same unreachable row (normal reach rounds and self-check rounds) noted in the report.

### Live check (CTO, with approval, unchanged)
Fresh Brief A and A+B builds: `self_check_summary … spec=0` (A+B builder=2, AB-FRESH risk 5); then a PUB-02 chat for the third-party close (`import json`).
