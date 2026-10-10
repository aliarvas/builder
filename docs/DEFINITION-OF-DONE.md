# Definition of Done

**Owner:** Completion and submission gates  
**Read when:** Finishing a milestone or preparing the submission

Mark an item only with a test result, artifact or verified official rule. This is a checklist, not a design document.

## Contract

- [ ] `python3 builder/build.py {brief} {tool_api}` runs end to end with no manual step.
- [ ] A Freya workflow is created or updated in place, published, and exported with `freya.export_workflow`.
- [ ] Runs finish well under 30 minutes per brief, including self-tests.
- [ ] Only the bank's tool API is used by the phone agent; the phone-agent model is unchanged and `agent_config` is omitted.
- [ ] Runs on Python 3.10+ from a fresh checkout; keys come from environment variables only.

## Generality

- [ ] No rule, date, value, holiday or outcome name from any specific brief in code or prompts.
- [ ] Works on a brief with a different layout and a different tool API (synthetic tests).
- [ ] Handles an override memo, a code list and tables without crashing.
- [ ] Tool field names and enums come from the OpenAPI file.
- [ ] Every step's dialogue prompt is within 500 to 1,500 tokens (builder check, reported in the trace).

## Safety and honesty

- [ ] No debt details before identity verification, where the brief requires it.
- [ ] Promises recorded only after read-back and confirmation; correct product, date and amount, once.
- [ ] The agent never claims a record that the tool did not confirm.
- [ ] Prompt-only rules are not described as guarantees.
- [ ] No API keys in the repo, traces or logs.

## Evidence

- [ ] Practice-case baseline and final scores recorded; no regression versus the baseline.
- [ ] Static and unit tests pass.
- [ ] Each run has a trace: start/end time, every model call (model and one-line purpose), Freya IDs with step and tool counts, self-tests.

## Submission (before Sun 20:00 UTC)

- [ ] Builder run on each hidden brief; one agent per brief; traces kept.
- [ ] Exports committed, e.g. `submission/hidden-1.workflow.json`, `traces/hidden-1.log`.
- [ ] Fresh checkout reproduces the run from the committed commit.
- [ ] Form sent with `team`, `repo`, `commit`, `run_command`, `workflows`, `traces`.
- [ ] No agent edited after its run.

## Done means

An unseen brief and tool file go in, and a working, policy-configured Freya agent plus its trace come out, reproducibly, with no hand edits.
