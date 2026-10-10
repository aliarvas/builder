# Agent Factory — Development Guide

## Goal

Build a program (the **builder**) that reads a bank collections brief plus an OpenAPI tool file and automatically creates a working phone agent (a workflow) on Freya. Competition: "Build the Builder" (Freya x Y Combinator). The deliverable is the builder, not a hand-made agent.

Run contract: `python3 builder/build.py {brief_path} {tool_api_path}`

This is the only document every development agent must read. Read the linked documents only when the current task needs them.

## Source-of-truth order

1. Official hackathon page, rules and starter kit (`build-the-builder-v2/`). If they differ, the newer kit wins.
2. `docs/STARTER-KIT-FACTS.md`: verified facts distilled from (1).
3. Topic owner documents listed below.
4. `docs/REFERENCE-NOTES.md`.

If sources conflict, the higher one wins. Do not silently reconcile: record the verified fact in `STARTER-KIT-FACTS.md` and follow it.

Status labels:

- `[VERIFIED]`: confirmed by the official page, kit, API response or a live test.
- `[HYPOTHESIS]`: a design choice that still needs evidence.
- `[TO-CONFIRM]`: must be checked against the kit or live Freya behavior.

## Priorities

1. **Never hardcode a brief.** Hidden briefs are unseen. No rule, holiday date, value or outcome name from any brief may appear in code or prompts.
2. **Prove the vertical slice first.** `brief -> agent on Freya -> practice case run` before any sophistication.
3. **All-or-nothing scoring.** A case passes only if outcome (bank ledger), policy (judge) and honesty (judge) all pass, three runs in a row. Optimize for correctness, not fluent dialogue.
4. **Honesty.** Never let the agent claim something was recorded when the tool call failed.
5. **Stay inside limits.** 30 minutes per brief including self-tests, update the workflow in place (cap is 10 per the page, 200 per the kit), only the bank's tool API, fixed phone-agent model, `agent_config` omitted. Python 3.10+, standard library.
6. **Traceable and reproducible.** Every builder run writes a trace. A fresh checkout must reproduce the result with one command.
7. **Log every failure as a finding.** When the builder or an agent it built fails, record why in [`docs/UAT-FINDINGS.md`](docs/UAT-FINDINGS.md): symptom, root cause, fix, status. Words, not code. This is our UAT data.

## Do not build

- A dashboard or UI.
- A local phone-agent runtime, STT or TTS (calls are text-based).
- Model fine-tuning or a model router.
- A generic multi-agent framework.
- Anything that edits an agent by hand after the builder ran.

## Reading map

- Facts from the competition and platform (read this first): [`docs/STARTER-KIT-FACTS.md`](docs/STARTER-KIT-FACTS.md)
- Scope and CLI behavior: [`docs/PROJECT-OVERVIEW.md`](docs/PROJECT-OVERVIEW.md)
- Modules and repository structure: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Schemas, provenance, validation: [`docs/IR-SPEC.md`](docs/IR-SPEC.md)
- Any Freya-facing change: [`docs/FREYA-INTEGRATION.md`](docs/FREYA-INTEGRATION.md)
- Collections behavior and guardrails: [`docs/COLLECTIONS-POLICY.md`](docs/COLLECTIONS-POLICY.md)
- Tests, practice cases, optimization: [`docs/EVALUATION-AND-TESTING.md`](docs/EVALUATION-AND-TESTING.md)
- Recording a failure and its cause: [`docs/UAT-FINDINGS.md`](docs/UAT-FINDINGS.md)
- Before declaring work complete or submitting: [`docs/DEFINITION-OF-DONE.md`](docs/DEFINITION-OF-DONE.md)
- Deferred ideas, not required: [`docs/REFERENCE-NOTES.md`](docs/REFERENCE-NOTES.md)

## Kit location

The starter kit is in `build-the-builder-v2/` (README, `docs/workflow-format.md`, `docs/tools-and-code.md`, `docs/api.md`, `freya.py`, practice briefs and cases). Read its workflow docs before touching rendering code.

## Kickoff rule

When the starter kit arrives, update `docs/STARTER-KIT-FACTS.md` with only facts supported by official docs, sample code, API responses or live smoke tests. Keep each topic in its owner document; elsewhere, link instead of repeating.
