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

### F-018: Leakage test treated required routing vocabulary as brief data

- **Date:** 2026-10-10
- **Brief / case:** T-004-fix offline source-leakage test
- **Run:** Local `python3 -m unittest discover -s tests -v`; no Freya request
- **Symptom:** One of 48 tests failed after fixtures gained `available_in` and `then`, reporting mandated step names and the `close`/`return` routing enum as leaked brief values.
- **Root cause:** The leakage allowlist had not been extended for the new spec's framework-level routing vocabulary.
- **Category:** other
- **Fix / lesson:** Explicitly distinguish task-mandated graph/schema vocabulary from fixture policy content while retaining the numeric product-limit regression assertion.
- **Status:** fixed (pending CTO commit)
- **Retest:** Enhanced leakage checks and full offline suite passed (48/48).

### F-017: Prompt documentation was stale during T-003-fix test run

- **Date:** 2026-10-10
- **Brief / case:** T-003-fix offline prompt documentation test
- **Run:** Local `python3 -m unittest discover -s tests -v`; no Freya request
- **Symptom:** One of 44 tests failed because the checked-in prompt catalog did not yet include the newly extracted hook and tool-description messages.
- **Root cause:** The test suite was run after changing `builder/prompts.py` but before running its deterministic documentation generator.
- **Category:** other
- **Fix / lesson:** Regenerate `docs/PROMPTS.md` immediately after prompt catalog changes, before the full suite.
- **Status:** fixed (pending CTO commit)
- **Retest:** Prompt documentation regenerated; full offline suite passed (44/44).

### F-016: Generated post-hook failed to compile after prompt extraction

- **Date:** 2026-10-10
- **Brief / case:** T-003-fix offline compile check
- **Run:** Local `python3 -m py_compile builder/*.py tests/*.py`; no Freya request
- **Symptom:** The generated generic post-hook caused a Python syntax error before the test suite could start.
- **Root cause:** Prompt text was inserted with an outer f-string while the hook source itself contained a literal empty dictionary; its braces were interpreted as an empty f-string expression.
- **Category:** other
- **Fix / lesson:** Generate hook source with token replacement rather than an outer f-string, so hook syntax and Freya placeholders cannot be reinterpreted.
- **Status:** fixed (pending CTO commit)
- **Retest:** Hook and all builder modules compile; full offline suite passed (44/44).

### F-015: Literal leakage scan confused framework words with brief constants

- **Date:** 2026-10-10
- **Brief / case:** T-004 offline source leakage test
- **Run:** Local `python3 -m unittest discover -s tests -v`; no Freya request
- **Symptom:** The new leakage test reported two embedded brief values even though one was a task-mandated workflow step name and the other was the builder trace's failure status.
- **Root cause:** The first scanner compared literal text without distinguishing required framework vocabulary from brief-derived policy values.
- **Category:** other
- **Fix / lesson:** Keep the scan strict for fixture content while explicitly exempting only task-mandated graph and trace vocabulary in addition to OpenAPI values and fixed tool names.
- **Status:** fixed (pending CTO commit)
- **Retest:** Literal scan and full offline suite passed (42/42); no Freya request was made.

### F-014: Multi-step renderer used three invalid workflow field shapes

- **Date:** 2026-10-10
- **Brief / case:** T-004 offline format audit against the kit workflow documentation
- **Run:** Local source/fixture inspection; no Freya request
- **Symptom:** The first rendered skeleton represented extraction as an object instead of an array, placed an entry API response mapping inside its pre-action instead of on the node, and encoded a tool-call transition as a condition operator.
- **Root cause:** The renderer followed generic JSON-schema conventions and shorthand assumptions instead of the exact Freya shapes documented for extraction, pre-actions, and tool-call transitions.
- **Category:** platform
- **Fix / lesson:** Assert the exact documented wire shapes offline: extraction entries use `name` and `enum_values`, entry-call mappings live on the node, passthrough metadata is explicit, and `is_tool_call` is a transition flag.
- **Status:** fixed (pending CTO commit)
- **Retest:** Exact wire-shape assertions and the full offline suite passed (41/41); no Freya request was made.

### F-013: Prompt catalog expansion made the documentation tests stale

- **Date:** 2026-10-10
- **Brief / case:** T-004 offline unit suite, prompt documentation tests
- **Run:** Local `python3 -m unittest discover -s tests -v`; no Freya request
- **Symptom:** Two prompt documentation tests failed after the multi-step prompt templates were added: the generated document no longer matched the checked-in file, and an old test still expected exactly two prompt sections.
- **Root cause:** The prompt catalog was expanded without regenerating its deterministic Markdown mirror or updating the count assertion to reflect a variable-size catalog.
- **Category:** other
- **Fix / lesson:** Regenerate the prompt documentation whenever the catalog changes and test the catalog entries rather than a historical fixed count.
- **Status:** fixed (pending CTO commit)
- **Retest:** Prompt documentation was regenerated; catalog-aware assertion and full offline suite passed (41/41).

### F-012: No closing record when the customer hangs up

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-07, CTO chat test (call ended from the customer side)
- **Run:** T-001 builder, workflow `b0bdd6e6-3b68-48ae-a319-ac7dc1cf06f9`, customer `c_7b974eed-824`
- **Symptom:** The ledger has no outcome at all: the closing tool never ran because the customer ended the call before the agent closed it.
- **Root cause:** The closing tool is only a model tool inside the conversation step. Nothing runs it when the call ends another way.
- **Category:** tool-call
- **Fix / lesson:** Make sure an outcome is recorded on every path, including customer hang-up (for example an end-of-call lifecycle step with an outcome computed from call state). Must not double-record when the agent already closed.
- **Status:** open
- **Retest:** -

### F-011: Deadline computed with the wrong band; holiday rule not applied

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-07 (vague period, then a holiday), CTO chat test
- **Run:** T-001 builder, workflow `b0bdd6e6-3b68-48ae-a319-ac7dc1cf06f9`, customer `c_7b974eed-824`
- **Symptom:** The customer was in the early band, but the agent applied the late band's shorter deadline. When the customer named a day that is a bank holiday, the agent did not offer the next business day; it insisted on the wrong "latest date" twice. No promise recorded. Same failure family as F-003, seen again with the T-001 builder.
- **Root cause:** The model chose the band and counted business days from prose rules. It picked the wrong row of the band table and skipped the holiday logic.
- **Category:** date-logic
- **Fix / lesson:** Band, deadline, holiday and "next business day" must come from code using the account result and the extracted calendar; the prompt only receives the finished dates (T-005).
- **Status:** open
- **Retest:** -

### F-010: Identity check replayed a wrong answer, blamed a "technical issue" and read the account early

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-03 (three wrong answers), CTO chat test
- **Run:** T-001 builder, workflow `b0bdd6e6-3b68-48ae-a319-ac7dc1cf06f9`, customer `c_e53e8ad2-b07`
- **Symptom:** After a wrong date of birth the agent moved on to the next question as if it had passed. It then sent the same wrong answer again on its own, without the customer saying it, which burned an attempt. It told the customer there was "a technical issue" (untrue: the answer was wrong). It called the account tool twice before verification (bank refused). The call ended after the customer's second wrong answer instead of the third. Ledger failed: account tool called before verification.
- **Root cause:** The model ignored negative tool results (known platform behavior with bare results), had the account tool available during identity, and tracked attempts from memory.
- **Category:** routing / honesty
- **Fix / lesson:** Identity step with only the identity tool; a post-hook that states plainly "answer wrong, N attempts left, ask again / end"; leave the step on the tool's verified or no-attempts-left result; never let the model resend an answer the customer did not give in this turn.
- **Status:** open (post-hook part in T-003, step structure in T-004)
- **Retest:** -

### F-009: Identity tool called again after identity was already verified

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-01 (happy path), CTO chat test via `/api/v2/chat/message`
- **Run:** T-001 builder, workflow `b0bdd6e6-3b68-48ae-a319-ac7dc1cf06f9`, customer `c_d25a971b-5c4`
- **Symptom:** After both answers were verified (`all_verified` true) the agent called the identity tool a third time with the date of birth. No visible harm in this case, but it wastes a turn and, with a wrong answer, could burn an attempt.
- **Root cause:** One step holds all tools; nothing removes the identity tool once verification is complete. The model repeated the call on its own.
- **Category:** routing
- **Fix / lesson:** Separate identity step that is left on `all_verified` from the tool result, so the identity tool is no longer available afterwards (T-004).
- **Status:** open
- **Retest:** -

### F-008: Promise tool first called with an invented product id

- **Date:** 2026-10-10
- **Brief / case:** Brief A, PUB-01 (happy path), CTO chat test
- **Run:** T-001 builder, workflow `b0bdd6e6-3b68-48ae-a319-ac7dc1cf06f9`, customer `c_d25a971b-5c4`
- **Symptom:** The first promise call sent the product's spoken name ("credit card ending ...") as the product id and the bank answered `unknown product_id`. The agent silently called the account tool again and retried with the right id; the second call succeeded. The ledger passed, but the practice check "promise tool called exactly once" would fail in a judged run, and in the tool-failure case (first promise call fails on purpose) the wasted call changes the retry logic.
- **Root cause:** The product id is a free, model-filled string. The kit warns about exactly this: ids come from the account result and must be given to the model or filled by code.
- **Category:** tool-call
- **Fix / lesson:** Fill the product id deterministically: map the account result to variables and offer the model a choice by index or an enum of the returned ids, or set the id in a pre-hook. Never let the model type an id.
- **Status:** open
- **Retest:** -

### F-007: Moved string constraint was rendered with JSON quotes

- **Date:** 2026-10-10
- **Brief / case:** T-003 offline tests (`test_kit_openapi_produces_seven_tools_with_schema_details`, `test_local_ref_is_resolved`)
- **Run:** Local `python3 -m unittest`; no Freya run
- **Symptom:** Two tests failed because a string-valued OpenAPI constraint moved into a field description appeared with JSON quotes instead of plain readable text.
- **Root cause:** The generic constraint formatter serialized every value as JSON, including simple strings.
- **Category:** other
- **Fix / lesson:** Render scalar strings directly while retaining deterministic JSON rendering for structured constraint values.
- **Status:** fixed (pending CTO commit)
- **Retest:** Full offline suite passed (29/29); both affected OpenAPI description tests passed.

### F-006: Builder entry point failed when imported as a package

- **Date:** 2026-10-10
- **Brief / case:** T-001 review (`python3 -c "import builder.build"`; no practice case)
- **Run:** `reviews/T-001-review.md` finding 1; local check, no Freya run
- **Symptom:** `ModuleNotFoundError: No module named 'freya'`. The CLI worked only as `python3 builder/build.py`; the unit tests passed anyway because they never imported `build.py`. `builder/trace.py` also shadows the standard library `trace` module when the script directory is first on `sys.path`.
- **Root cause:** Flat imports (`import freya`, `from trace import ...`) depended on the script directory being on `sys.path`; no test exercised `main()`.
- **Category:** other
- **Fix / lesson:** Do not name modules after standard library modules. Add a test that calls `main([... "--print"])` so the entry point is covered, not only the helper modules.
- **Status:** fixed (T-001 commit)
- **Retest:** Package import succeeded; direct `main([... "--print"])` coverage and the full offline suite passed (21/21).

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
