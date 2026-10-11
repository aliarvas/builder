# T-010: offline self-check and repair inside the builder

## Design note (written before the implementation)

**Goal:** after the spec is extracted (or loaded with `--spec`) and the workflow is rendered, play generated calls on the rendered workflow offline, compare each call's ledger with what the spec requires, and send spec problems back to extraction (at most 2 rounds). No model call except those repair rounds, no Freya, no practice file, no brief value in code.

**Modules:**
- `builder/selfcheck.py`:
  - `Simulator` walks one whole call from `initial_node`: the test `Session` / `PlatformCall` / `walk`, generalised.
    - It runs code steps with `exec` and evaluates rendered conditions.
    - After every code step it applies the platform rule for typed writes (F-052/F-060: a value that does not fit the extraction field is rejected and the old value kept; logged).
    - It runs api steps and model tool calls through a `Bank`, and enters global special-path nodes when a scenario says so (`__previous__` returns).
  - `Bank` plays the tools from the OpenAPI response shapes and the spec's field names (identity verified / attempts left, products, ok values).
    - The answers are scripted per scenario (an answer is wrong, a record fails).
    - It keeps the ledger: promises, notes, callbacks, transfers and every tool call in order, so the close_call count and position can be checked.
  - Scenario generation (`scenarios(spec, now)`) reads only the spec:
    - opening routes;
    - identity pass, a wrong answer then pass, attempts used up;
    - third party: callback inside and outside the window, each close value;
    - every special path (close, return, with a tool: ok and failed);
    - offers: ok, not a business day, after the deadline, below the floor, over the full amount, the invalid-offer limit;
    - refusal (with persuasion attempts when the spec has them);
    - a record failure;
    - multi-product when the spec has product notes or per-product values: accept all, refuse one, record failure.
    - Synthetic products come from the spec's offer rules (one product per `latest` band × floor rule kind) and the OpenAPI item fields.
  - **Expected ledger from the spec only:**
    - the outcome row whose `on` holds the state the scenario drives, or the special path's pair;
    - promise dates from `builder/selfcheck_calendar.py`, the spec calendar helper moved from `tests/now_calendar.py`. It is written apart from `offer_check.py`, so code is checked against the spec rules, not against itself;
    - notes from `closing.product_notes`.
  - **Checks per scenario:**
    - `end_call` reached;
    - exactly one `close_call`, and it is the last tool call;
    - the ledger matches;
    - no rejected typed write;
    - no dead end (a step where the scenario's input finds no route, or a code step loop);
    - at most one spoken message per closing turn.
  - **Coverage check:** every non-default outcome row is reached by at least one scenario. A row no scenario can reach is a spec problem (F-065 at run time).
  - **Classification:**
    - *spec* problems (an unreachable row, a value or state that has no route) carry a spec path (`outcomes[i]`, `opening.who_answered_options`, ...) and go to repair;
    - everything else (a wrong ledger on a reachable row, a rejected write, a dead end in builder steps) is a *builder* problem: a trace warning, never a repair.
- **`extract.py`:** `extract_spec(..., self_check=None, deadline=None)`.
  - After the normal validation loop, `self_check(parsed)` returns the spec problems.
  - If there are any, and there is time before `deadline`, the owning groups get one repair message per round (it names the scenario and the step), and the normal checks run again.
  - At most 2 rounds. If a repaired reply breaks the normal checks, the last good spec is kept. Still failing → kept, with warnings. The build never stops for this.
- **`build.py`:**
  - The self-check runs after rendering in every mode (`--print`, `--validate`, save, `--spec`); with `--spec` there is no repair.
  - Trace lines:
    - `self_check: scenario=<id> result=pass|fail kind=spec|builder reason=...`;
    - `self_check_summary: scenarios=N pass=N fail=N spec=N builder=N seconds=S`;
    - `self_check_repair: round=R groups=... problems=N`.
  - Time guard: no repair round once 20 minutes of the build have passed.
  - `tools/submission_check.py` only reads known keys; a test checks that a trace with the new lines still passes.
- **Tests:** `Session` (multi_ready) and `SpecCalendar` (now_calendar) become imports from the builder modules; the existing tests keep their behaviour.

**Split proposal (CTO decides):** I build the simulator, checks, integration and repair loop (one coherent piece). claude-dev2 could take two pieces later:
- (a) more scenario families (hangup states, turn limit, revise at the read-back, callback unclear answers);
- (b) moving the remaining test walkers (`test_multi_step.walk`, `test_closing_speech.spoken_per_turn`) onto `builder/selfcheck.py`.

## Implementation

### New modules

**`builder/selfcheck.py`**
- `holds` / `fits` / `code_of`: the platform's reading of conditions and typed writes.
- `Bank`: plays the tools from the OpenAPI shapes and the spec's field names.
  - Scripted ok values per tool: the promise tool by the `@record` role; the others by name.
  - Identity answers right or wrong, with the mock bank's fixed number of wrong answers (`BANK_WRONG_ANSWERS`).
  - It records every tool call in order.
- `Simulator`: one whole call from `initial_node`.
  - It runs code (`exec` with `vars` only; `json` is not pre-loaded, as on the platform), api steps and the model's tool call. The arguments are stored as `<tool>_args.<field>`, as in the kit docs.
  - It enters global special-path steps (also the per-step entries `special_<id>_at_<step>`), follows `__previous__`, and applies the typed-write rule after every code step.
- Scenario generation, only from the spec:
  - opening close values and unclear;
  - identity: attempts used up; one wrong answer then right (inside `promise`);
  - promise;
  - offers: not a business day, after the deadline, below the floor, over the full amount, invalid-offer limit;
  - record failure;
  - each negotiation close value (with the band's persuasion count when attempts exist);
  - third party: each close value, callback inside the window, outside the window until giving up;
  - each special path: close (and, with a tool, the tool failing) and return;
  - multi-product when the spec has notes or per-product values: accept all, refuse one, record failure.
- Synthetic products: one per deadline band and floor rule, using the field names from the spec.
- **Expected ledger:**
  - the outcome row of the call-end state (or the special path's pair; an unmapped tool failure uses the promise-failure row, F-065);
  - promises from `selfcheck_calendar`;
  - notes from the spec's note rule.
- **Checks:**
  - `end_call` reached;
  - exactly one close call, and it is the last tool call;
  - outcome/reason, promises, notes;
  - no rejected typed write;
  - no dead end or loop, and no code step that raises;
  - at most one spoken message in the closing turn;
  - the persuasion count.
- **Reach:** a row with no `on` state that no scenario ends with is a **spec** problem (`outcomes[i]`) and goes to repair. If only a returning path with a tool names it, it is a builder warning (risk 5). Every other failure is a **builder** problem.
- `Report`: `trace_lines()` and `repair_messages()`; each message names the scenario and the step.

**`builder/selfcheck_calendar.py`**
- `SpecCalendar` moved here from `tests/now_calendar.py`; the tests import it from here.
- Added `first_allowed`, ISO dates in `resolve`, and amount rules with `value`/`share` (the synthetic spec's floor is `share` 0.5).
- It is independent of `offer_check.py`.

### Changes to existing files

**`builder/extract.py`**
- The validation round is now a function, `validate(last)`.
- After a valid spec: `self_check(parsed)` gives problems → `selfcheck<N>:<group>` repair calls (at most `MAX_SELF_CHECK_ROUNDS` = 2) → validate again with last-round softness.
- If the repair breaks other checks: the replies are restored and the previous spec is kept (`self_check_repair: … rejected`).
- Past `deadline`: `skipped: time guard`. A self-check error never stops the extraction.

**`builder/build.py`**
- `_self_check_problems` is the extraction hook (it renders with the same tools as the build).
- `_trace_self_check` runs after rendering in every mode (`--print`, `--validate`, save, `--spec`). It writes the `self_check:` and `self_check_summary:` lines, plus one `warning` line if spec or builder problems are left.
- Time guard: no self-check repair after 20 minutes of the build (`SELF_CHECK_REPAIR_SECONDS`).

**Tests now use the builder simulator:**
- `tests/test_multi_ready.Session` now runs on `Simulator` + `Bank` (`run_code`, `run_api`, `holds`).
- `test_offer_amount_reset.fits` and `tests/now_calendar.SpecCalendar` come from the builder.

## Finding (builder bug found by the self-check)

**`third_party_close_check` (F-064 guard, `builder/callback.py`, claude-dev2) used `json.loads` without `import json`.**
- The kit docs say `json` "can be imported"; they do not say it is pre-loaded. So in the sandbox this step would raise `NameError` before routing.
- The self-check caught it in every third-party close scenario: the call never reached `close_call`.
- I added one line (`import json` at the top of the generated code). This is claude-dev2's file; they are idle, the fix is minimal, and I am flagging it here.
- The earlier live trace (`brief-a.log`, 12:24 run) had `self_test: case=third_party_close result=platform_error reason=close step entered but no close_call event visible`. That may be the same cause; it needs a live check.
- **UAT proposal (new number):** "Third-party close guard: code without `import json`; the call does not close". Cause: the code step uses a module it does not import. Fix: import. Status: fixed offline, live check open.

I found no other code step or hook that uses `json` without importing it (all fixtures scanned).

## Results

`python3 -m unittest`: 472 tests OK, 35 of them new in `tests/test_selfcheck.py`.
- Fixtures and recorded extractions (11 specs, 14–33 scenarios each): every scenario passes except the known gaps:
  - **AB-FRESH risk 5** (`spec-brief-b`, `brief-ab-extracted*`): the `paid` and `no_promise/dispute` rows are named only by a returning per-product path, and the closing does not derive the outcome from the notes. These are builder warnings, not repair.
  - **REPRO 13:00 (`brief-a-repro-1300`):** `no_promise/hardship` cannot be reached, a spec problem → repair.
- Live specs under `traces/` (not tests):
  - all pass;
  - `f041-a` also has the hardship gap (spec problem, as the F-065 review found);
  - `f040-changed`, `f041-changed` and `t006b-changed-a` need the changed OpenAPI and were not rendered here.
- Mutations: a broken route, a missing model tool, a close step without a tool, a code step that raises, two spoken lines at the close, and a wrong expected ledger are all caught.
- Timing: the self-check of the four A+B specs takes under 10 s together (about 0.5 s per spec); Brief A about 0.2 s. The whole suite takes about 32 s (it was 18 s).
- Leak test green (`selfcheck.py` added to the file-scoped allowance for the schema keyword `"type"`).

## Limits and next steps (proposals)

**Not played yet:**
- hangup states, turn limit;
- revise at the read-back;
- unclear or need-time callback answers;
- account failure;
- several special paths in one call.

Rows mapped only by such states count as reached (they have an `on` state), so they are not sent to repair.

**The expected ledger is spec-level, not brief-level.** If the spec itself is wrong but consistent (a wrong reason in a row), the self-check cannot see it; that needs layer 2 (chat).

**Split proposal for claude-dev2:**
- (a) the scenario families above;
- (b) move `test_multi_step.walk` and `test_closing_speech.spoken_per_turn` onto `builder/selfcheck.py`;
- (c) a `submission_check` line that checks the `self_check_summary` format (`tools/` is not my area).

**Live check (with approval):** a fresh Brief A/A+B build. The trace should show `self_check_summary` with `spec=0` (A+B: builder=2, risk 5). Then a third-party close chat (the `json` fix).

No Freya, no model call, no commit, no env.sh.

## Fix (review T-010)

Review: `reviews/T-010-review.md` (fixes needed). All six points are fixed. `python3 -m unittest`: **484 tests OK** (12 new in `tests/test_selfcheck.py`), about 42 s.

**(1) MEDIUM: extraction is checked against the waiting step (`Simulator.extract`).**
- `turn` writes only names the waiting step declares in its `extraction_schema`, and only values that `fits` the field.
- Anything else is not written and becomes the BUILDER problem `<step> cannot extract <name>=<value>`.
- `tool_turn` does the same for the tool: a choice outside the parameter's enum, or an argument the tool does not have, is reported.
- What this changed: a spoken-only special step was sent a `None` choice; now it gets an empty turn. No fixture or live spec gained a failure.
- Tests:
  - the reviewer's mutation, with the refusal field removed from every step, fails with `negotiate cannot extract …`;
  - a value removed from the opening enum is BUILDER, not SPEC.

**(2) MEDIUM: calendar `next`/`keep`, and more than one `now`.**
- `SpecCalendar.deadline` now handles all three values:
  - `previous` moves back to a business day;
  - `next` moves forward;
  - `keep` leaves the day;
  - a business-day count already ends on a business day.
- Tests: each of the three modes with the deadline on a weekend, and again on a holiday. The reviewer's probe (spec-synthetic on 2026-10-26) now passes.
- **My choice:** in the build (no `now` given), the scenarios run for the build's own `now` plus two moments from the spec's own calendar (`check_nows`):
  - the last business day before a non-business day (a Friday on a Saturday-Sunday weekend);
  - the business day before a spec holiday (the next one, else the latest listed).
- **Why:** these are exactly the dates where the rules differ (moving a date, a deadline across a weekend or holiday). Logging `now=` alone would only explain a date-dependent failure afterwards, not prevent it.
- **Cost:** about 3× the play time, roughly 0.5–1.6 s per spec. The four A+B specs still take under 10 s (the test still checks this).
- **Trace:**
  - all results are listed for the build's `now`;
  - for the extra moments only the failures are listed, as `<id>@<date>`;
  - the summary now ends with `now=… extra_nows=…`;
  - `scenarios=` counts every play.
- With an explicit `now` (the tests) only that moment runs.
- Repair messages are de-duplicated by spec path, so the same problem at two moments is sent once.

**(3) MEDIUM: a self-check repair must not add anything.**
- After a self-check repair, the spec is accepted only if:
  - the normal checks pass;
  - there is no new warning (compared as a set, not a count, so a fixed warning cannot hide a new one);
  - the next self-check has no problem at a spec path that was not there before.
- Otherwise the replies are restored and the previous spec is kept.
- Logs:
  - `self_check_repair: round=N accepted warnings=A->B problems=C->D`;
  - `… rejected: the repaired reply breaks other checks | adds a warning at <path> | adds self-check problem(s) at <path>; the previous spec is kept (warnings=…, problems=…)`.
- The self-check of the accepted spec is reused for the next round, so there is no extra run.
- Tests:
  - a repair that fixes the hardship row but has an instruction-style goodbye: 1→1 warnings, but the warning is new, so it is rejected;
  - a repair after which the self-check reports a second path is rejected;
  - the 13:00 repair is accepted with `warnings=1->0 problems=1->0`.

**(4) Dead end on a routed spec value becomes SPEC.**
- Each scenario turn that carries a spec value also carries its spec path: `opening.close_values[i]`, `opening.<key>_values[0]`, `negotiation.close_values[i]` / `product_end_values[i]`, `third_party.close_values[i]`, `confirmation.intent_values[i]`.
- If the step extracted the value correctly and still has no route for it, the result is SPEC with that path, and it goes to repair.
- If the step could not extract the value (point 1), the step is at fault, so it stays BUILDER.
- Test: removing the opening route for a close value gives SPEC `opening.close_values[0]` and a repair message for that path.

**Spec problems still not detected (layer 1 cannot see them):**
- Rows mapped to call-end states the scenarios do not play: hangup, turn limit, account failure, unclear or need-time callback answers, revise at the read-back. They count as reached because they have an `on` state.
- A spec that is consistent but wrong compared with the brief (a wrong reason, amount or day count in a row). The expected ledger comes from the spec itself; this needs layer 2 (chat).
- A missing value: a who-answered or intent value the brief names but the spec left out. No scenario plays it, so no dead end appears. Only the coverage check sees it.
- Several special paths in one call, and a special path at a step other than its first `available_in` step.
- Products other than the synthetic ones (one per deadline band and floor rule). Rules on other product fields are not played.
- **Repeat-repair note:** an unreachable row can now be repaired twice, through the normal reach check (up to 2 rounds) and the self-check (up to 2 rounds). That is bounded and harmless, but it costs model calls. Making the self-check skip the paths the normal rounds already tried is a possible follow-up.

**(5) LOW: environment fidelity.**
- **Imports:** code steps and hooks run with a restricted `__import__`.
  - `json`, `re` and `datetime` are allowed; any other module is recorded as `<where> imports <module> (the platform allows json, re, datetime)`.
  - Test: `import os` in the closing code is caught; `json`, `re` and `datetime` are not reported.
- **Transitions:** `route` reports a step with more than one transition to the same target (the platform merges them with OR, so the rendered order is lost). It is reported once per step.
  - Test: an appended `always` transition to the same target is caught.
- **`BANK_WRONG_ANSWERS`:** the comment now says it is a simulator parameter (the kit's mock bank), not policy. The workflow routes on the `attempts_left` the bank returns, so a bank with another limit only changes how many wrong answers a scenario plays.

**(6) LOW: time guard.**
- `SELF_CHECK_REPAIR_SECONDS` is now 15 minutes.
- In addition, a self-check round is skipped if `now + the slowest repair round so far` would pass the deadline. The estimate covers both the normal repair rounds and the self-check rounds.
- Test: a fake clock where each round takes 60 s; at 240 s with a 270 s deadline the round is skipped. Without the estimate it would run.

**Also:**
- the `SandboxDownTests` docstring in `tests/test_record_loop.py` now says F-067;
- no other file in `builder/` or `tests/` cites the sandbox entry as F-065 (the remaining F-065 mentions are the reachability work);
- the `F-065` mention inside the F-067 entry of `docs/UAT-FINDINGS.md` is the CTO's text, and I did not touch it.

**Re-run on the specs (build mode, three moments):**
- fixtures: unchanged; only the known gaps fail (AB-FRESH risk 5 as BUILDER, the 13:00 hardship row as SPEC);
- live `traces/*.spec.json`: `f041-a` has the hardship row (SPEC); `ab-fresh` and `f040-b` have risk 5 (BUILDER); all others pass.

No Freya, no model call, no commit, no env.sh.

## Follow-up (re-review notes)

The re-review is in `reviews/T-010-review.md` (merge edilebilir). Notes A–C are fixed; D needs no change. `python3 -m unittest`: **488 tests OK**, 4 of them new, about 48 s.

**A. A dead end on a routed spec value stays BUILDER unless the spec itself is inconsistent.**
- The builder renders a route for every spec value. So if a step has no route for such a value, that is a builder fault, and it is never sent to the model.
- A new function, `route_inconsistency(spec, spec_path)`, makes the dead end SPEC only when the spec's own lists disagree. It reads only the spec. Each section has one list of the values its step extracts, and the lists that route those values:
  - opening: `who_answered_options`, routed by `identity_values`, `third_party_values`, `stay_values` and `close_values`;
  - negotiation: `intent_values`, routed by `confirm_values` and `close_values`;
  - third_party: `intent_values`, routed by `close_values`;
  - confirmation: `intent_values`, routed by `revise_values`.
- `product_end_values` and `attempt_values` only mark values that are already in a route list, so they may overlap with it.
- Two cases count as inconsistent:
  - a routed value is missing from the section's values list, so the step's extraction enum cannot hold it. This is now SPEC even though the extraction fails, because the cause is the spec;
  - one value appears in two route lists of the same section.
- No fixture spec has either inconsistency (all lists were scanned).
- Tests:
  - the reviewer's mutation: removing the negotiation transition for a close value is BUILDER with no repair message. The same holds for the opening;
  - a close value removed from `who_answered_options` is SPEC with path `opening.close_values[0]`, and a repair message is sent;
  - a value in both `stay_values` and `close_values` is reported as an inconsistency.

**B. A reworded warning at the same path is not new.**
- Warnings are now counted per path. A repair is rejected only if some path ends up with more warnings than before.
- The rejection log names that path: `adds a warning at <path>`.
- Test: the goodbye at `special_paths[1].say` stays an instruction but in different words (a "talks about the customer" warning becomes a "starts with 'Say'" warning). The repair is accepted with `warnings=2->1 problems=1->0`.
- The earlier test still rejects a new warning at a new path.

**C. The time guard has a default estimate.**
- `DEFAULT_REPAIR_ROUND_SECONDS` is 90 s. The guard uses it until a repair round (normal or self-check) has been measured, then the slowest measured round.
- Test with a stopped clock: 60 s before the deadline, the round is skipped; 100 s before, it runs.

**D. A build on a weekend.** No change. The build's own `now` is always played, so a weekend build plays the weekend. The extra moments add a Friday and a holiday eve.

No Freya, no model call, no commit, no env.sh.
