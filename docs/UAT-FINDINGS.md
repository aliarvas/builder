# UAT Findings

**Owner:** Every observed failure of the builder or of a phone agent it built, and why it happened.

This is a findings log, not code. Each entry records **why** the builder produced a wrong or failing agent, so the same mistake can be recognized and tested again later. Treat it as UAT data.

## Rule

- Every failure gets an entry: a failed practice case, a failed self-test, a rejected workflow, a wrong outcome, a policy or honesty failure, a timeout.
- Write the entry when the failure is understood, even if it is not fixed yet. Update its status when it is fixed.
- Describe behavior and cause in words. Do not paste code or whole transcripts; link to the trace, call ID or file instead.
- Never write brief-specific values here as rules for the builder (see AGENTS.md priority 1). Describe the general pattern.
- Newest entry on top. IDs never change: `F-001`, `F-002`, ...

## Entry template

```markdown
### F-000: <short title>

- **Date:** YYYY-MM-DD
- **Brief / case:** <brief, case ID or test name>
- **Run:** <trace file, workflow_id, agent_id, call_id>
- **Symptom:** what went wrong (outcome, policy or honesty; what the agent said or did)
- **Root cause:** why the builder produced this behavior (extraction, rendering, routing, prompt, tool mapping, Freya behavior, ...)
- **Category:** extraction | routing | tool-call | honesty | policy | date-logic | platform | timeout | other
- **Fix / lesson:** what changed in the builder, or what should change
- **Status:** open | fixed (commit) | won't fix (reason)
- **Retest:** result after the fix (e.g. 3/3 runs passed)
```

## Findings

### F-005: Saved workflow disappeared from the workspace

- **Date:** 2026-10-10
- **Brief / case:** setup check
- **Run:** workflow `50dafbaa-36d4-4ee8-babf-9c5ae30a906f` (created 11:12 UTC with the v1 sample builder)
- **Symptom:** Reading the workflow back returned 404 "Workflow not found". The workspace held only the organizers' "Freya Bank Collections Base (2 nodes)" workflow. The local slot file still pointed at the deleted ID, so the next `save_workflow` would have tried to update a workflow that no longer exists.
- **Root cause:** Most likely the organizers reset workspaces when they released kit v3 (the README says the base agent "is already in your workspace"). Not confirmed.
- **Category:** platform
- **Fix / lesson:** Never trust the local slot file alone. Before updating, check that the stored workflow ID still exists; if not, create a new one and say so in the trace. Stale slot file removed by hand.
- **Status:** open (builder check not yet implemented; slot file removed)
- **Retest:** -

### F-004: Agent said it would transfer but never called the transfer tool

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-09 (restructuring request)
- **Run:** v1 sample builder, simulation `22ed0aea-b13a-4726-ae14-e9fef445d3ab`
- **Symptom:** The judge passed the conversation, but the bank ledger had no transfer and no `close_call`. Outcome check failed.
- **Root cause:** One conversation node with all seven tools and the whole brief as prompt. The model announced the action in words and ended the turn without the tool call; nothing in the workflow forced the call.
- **Category:** tool-call
- **Fix / lesson:** Do not rely on the model to remember a required tool. Put the action in a step whose exit depends on the tool result, give tool descriptions an explicit "CALL it when ..." trigger, and make the closing tool impossible to skip.
- **Status:** open
- **Retest:** -

### F-003: Promise date ignored the holiday rule

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-07 (vague period, then a holiday)
- **Run:** v1 sample builder, simulation `22ed0aea-b13a-4726-ae14-e9fef445d3ab`
- **Symptom:** The customer named a bank holiday; the agent offered an earlier day instead of the next business day after the holiday. Wrong date recorded.
- **Root cause:** The model did calendar arithmetic itself from prose (business days, holidays, "next business day"). It got it wrong.
- **Category:** date-logic
- **Fix / lesson:** Compute dates in a code step from `now` and calendar data extracted from the brief; give the model finished facts (allowed dates, deadline, next business day).
- **Status:** open
- **Retest:** -

### F-002: Identity check ended early and account was read before verification

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-03 (three wrong answers)
- **Run:** v1 sample builder, simulation `22ed0aea-b13a-4726-ae14-e9fef445d3ab`
- **Symptom:** The agent stopped after one wrong answer and called `get_account` before both questions passed. Ledger and judge both failed.
- **Root cause:** Attempt counting and the "verify first" gate lived only in the prompt; the account tool was available from the first turn.
- **Category:** routing
- **Fix / lesson:** Keep the account tool out of the identity step; leave the identity step only on the tool's verified/failed result; count attempts from tool results, not from the model's memory.
- **Status:** open
- **Retest:** -

### F-001: Third party call ended without callback and without close

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-02 (a relative answers)
- **Run:** v1 sample builder, simulation `22ed0aea-b13a-4726-ae14-e9fef445d3ab`
- **Symptom:** Disclosure rules were respected, but no callback was scheduled and `close_call` was never called.
- **Root cause:** Same as F-004: required tool calls depended on the model's initiative in a single all-purpose step.
- **Category:** tool-call
- **Fix / lesson:** A dedicated third-party path whose exit requires the callback/close tool results.
- **Status:** open
- **Retest:** -
