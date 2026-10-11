# T-047 report: self-test and repair loop for the generic mode

**Owner:** claude-dev2. T-044 was stopped at the CTO's order; its report stays as written.
**Not done:** no Freya request, no model call, no commit, no env.sh. Everything was tested offline with a fake model and a fake chat.
**Generic:** no case value is in the code or the prompts. The leak test is green.
**`python3 -m unittest`:** 708 tests, OK, after claude-dev wired the loop into `build.py` and regenerated `docs/PROMPTS.md`.

## Interface (agreed with claude-dev, T-046)

```python
generic_selftest.self_test_loop(case, workflow, save, repair, trace, *,
                                model, chat, deadline, workflow_id=None, rounds=2) -> (best_workflow, results)
```

| Argument | Meaning |
|---|---|
| `case` | `case_folder.read_case(...)` |
| `workflow` | the workflow claude-dev already saved and published |
| `workflow_id` | the id of that save; without it, the loop saves the workflow once to get one |
| `save(workflow) -> workflow_id` or `(workflow_id, saved_workflow)` | saves and publishes; the tuple form is used when the Freya validation repair changed the workflow, so the export is the live version (I asked claude-dev to return it) |
| `repair(problems, workflow=None) -> workflow` | claude-dev's closure over `generic.repair`; a one-argument form also works |
| `model` | the `llm.AnthropicClient` |
| `chat` | the `freya_chat` module (a fake in tests) |
| `deadline` | an absolute `time.monotonic()` value; claude-dev passes build start + 25 min |

claude-dev wires it into `build.py` with a lazy import. On an ImportError, the trace says "self_test skipped". The workflow the loop returns is the live one, and it is the one that gets exported.

## What it does (`builder/generic_selftest.py`)

1. **Scenarios: one model call.**
   - **Input:** the documents, with the PDFs attached. Test customers and example conversations are already labelled as reference material by the T-040 reader.
   - **Coverage, in this order:** every example conversation, every kind of test customer and service answer (errors and empty results included), then the rules most likely to be broken.
   - **What each scenario holds:** id, persona, goal, language, call variables, first words, expected behaviour, expected service paths, forbidden actions, and a turn limit. At most 8 scenarios, each at most 14 caller turns.
   - **Validation:** a malformed scenario is skipped with a note. A call variable one scenario left out is taken from another scenario.
2. **The run.**
   - Every scenario goes through Freya chat, all of them in parallel (chat calls are allowed in parallel; simulations are not).
   - A model plays the caller, one turn at a time, in the scenario's language. It says goodbye when the goal is done or the call is stuck.
   - After each turn the call record (`GET /api/v2/call/{id}`) is read. The transcript holds the caller and agent lines, each tool call with its arguments and result, the steps entered, and engine errors.
   - A gateway (5xx) error gets one retry. An unfinished call is ended.
3. **The judge: one model call per run.**
   - **Input:** the scenario, the transcript and the documents.
   - **Output:** pass or fail, the reasons, and a fix suggestion with no value of the test customer.
   - **Fails for:** a missing step, value or tool call; an invented value; an action claimed without a tool success; a broken document rule; a stuck or wrongly ended call.
   - **Does not fail for:** wording alone.
4. **Repair.**
   - **What goes to `repair`:** only the judge's failures, as problem lines. Each line says "never copy a test customer's value into it". Platform or model errors (`error`) are not sent.
   - **What happens next:** the repaired workflow is saved, and only the failed scenarios run again.
   - **Limit:** at most 2 rounds.
5. **Budget and the best version.**
   - **Time check:** a round starts only if the time left is more than the last round's time plus 5 minutes for the repair and save.
   - **Which version is kept:** the version with the most passes. A repair that did not add a pass is not kept; the earlier version is saved again, so the export and the live agent are the same.
   - **No crash:** any failure (scenarios, save, repair) is written to the trace and leaves the build running.
6. **Trace:**
   - `self_test_scenarios`;
   - `self_test_result` for each run: round, id, verdict, reasons, fix, call id, turns, seconds, transcript;
   - `self_test_round` with passes, total and seconds;
   - `self_test` notes.

## Prompts

The prompts (`SELFTEST_SYSTEM`, `SELFTEST_SCENARIOS_TASK`, `SELFTEST_CUSTOMER_TASK`, `SELFTEST_JUDGE_TASK`, `SELFTEST_REPAIR_LINE`) are kept in `generic_selftest.py` for now, because claude-dev was editing `prompts.py` at the same time.
- **Moving them later:** they can move to `prompts.py` and `docs/PROMPTS.md` once claude-dev is done.
- **One system text for all calls:** every self-test call has the same system text and the same cached documents block first, so the scenario, caller and judge calls reuse the prompt cache.

## Tests (`tests/test_t047_generic_selftest.py`, 13 tests, offline)

- scenario parsing: bad scenarios skipped, duplicate ids, the turn limit, filling a missing call variable;
- judge parsing ("false" as a string, a fenced reply, no pass value);
- the transcript holds tool calls and results;
- the repair line, with platform errors left out;
- the loop:
  - failures go to repair with the current workflow;
  - only the failed scenarios run again, on the new id;
  - the trace has every run;
  - no gain → the earlier version is kept and saved again;
  - all pass → no repair;
  - short time → no repair;
  - a chat error is not repaired;
  - one-argument and two-argument `repair`;
  - a `save` that returns the workflow it really saved;
- a document above 40k characters is cut.

## The real case folder (read offline, no model call)

- **Roles:** test customers (`test-environment/test-customers.json` and `.md`) and `example-scenarios.md` are read as reference material, so the scenario call finds them.
- **Size:** the documents together were 852k characters; 707k of that is `test-customers.json`. claude-dev's reader now cuts a reference file above 20k characters, so the whole case is about 165k characters (about 41k tokens, cached) in each self-test call. My own cut of any document above 40k characters stays as a safety net.
- **Fixed by claude-dev in `case_folder.py`:** the size problem, and the meeting transcript is now read as policy, not reference.

## Open

- **Not run live:** no model call and no Freya chat has been made with the real case yet.
- **Time:** one round is about 14 turns × (chat + model) ≈ 3–4 minutes when all scenarios run at once. With the build itself, the 25-minute deadline allows about one repair round. The time check stops it in time.
- **The judge is a model:** it can be wrong. A wrong fail costs a repair round, but a version that gains nothing is not kept.
- **Variables:** `customerNumber` and `now` come from the scenario call; if the model leaves out a variable in every scenario, the call runs without it.
