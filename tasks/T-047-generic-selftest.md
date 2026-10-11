# T-047 (FINAL): self-test and repair loop for the generic mode

**Owner:** claude-dev2 (stop T-044) · Read `tasks/T-046-generic-mode.md` first; claude-dev builds the generic mode at the same time.

## What to build (generic)

1. **Test material from the folder.**
   - The test customers (`test-environment/test-customers.json` or `.md`) and the example conversations (`example-scenarios.md`). Detect them by role, like T-040.
   - One model call turns them into test scenarios: the customer persona, the goal, the turns, and the expected agent behaviour and tool calls.
   - These are the bank's own test customers. Use them only at build time for testing; never copy them into the workflow.
2. **Run the scenarios against the saved agent through Freya chat** (web calls, as our current self-tests do).
   - A model plays the customer from the scenario, in the documents' language.
   - Call variables: `customerNumber` from the test customer, and `now` from the scenario (or a sensible default).
   - Collect the transcript and the tool events from the call record (`GET /api/v2/call/{id}`).
3. **Judge.** One model call per run, against the scenario's expected behaviour and the documents' rules: pass/fail and reasons.
4. **Repair.** The failures go back to the design/workflow model (T-046's repair entry) for one or two rounds, then a re-save and a re-run of the failed scenarios only.
5. **Budget.**
   - Run the scenarios in parallel where Freya allows (chat calls are fine; simulations are one at a time).
   - The whole build stays under 30 minutes. Stop repairing when the time is short, and keep the best version (the most passing).
6. **Trace:** every scenario, its call id, the verdict and the reasons.

## Tests

- Offline, with a fake Freya client and a fake model: scenario parsing, the judge parse, and that the repair is called with the failures.
- `python3 -m unittest` green; the leak test.

## Constraints

- No commit and no env.sh; the CTO runs live.
- Report: `tasks/T-047-report.md`.
