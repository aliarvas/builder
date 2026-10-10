# Project Overview

**Owner:** Product scope and external behavior  
**Read when:** Changing the builder's purpose, input, output or top-level workflow

## Positioning `[VERIFIED: project owner, 2026-10-10]`

**Policy-aware banking collections voice-agent builder for Freya.**

- Vertical: financial services → banking → collections (late-payment phone agent). Not general-purpose, not insurance.
- The phone agent: confirms it is talking to the right customer, fetches the late accounts, negotiates date and amount, records payment promises, handles already-paid, dispute and hardship, schedules callbacks, transfers to a human when needed, records the call outcome in the bank's system.
- The builder is not tied to one bank: each collections brief (Bank A, Bank B, hidden brief) produces its own workflow.
- Out of scope now: a universal builder for every sector. Other verticals (insurance, customer service, sales) are a possible later extension (see [`REFERENCE-NOTES.md`](REFERENCE-NOTES.md)).

## Definition

Agent Factory is a policy-aware collections agent compiler. It reads a bank brief and an OpenAPI tool file, and creates a phone agent (a Freya workflow) with no human edits. Verified contract and limits: [`STARTER-KIT-FACTS.md`](STARTER-KIT-FACTS.md).

```text
brief + tool API (OpenAPI)
        |
        v
 extract rules (LLM, with source references)
        |
        v
 validate rules and tool bindings
        |
        v
 provider-neutral IR
        |
        v
 render Freya workflow  ->  create/update on Freya
        |
        v
 self-test on practice-style cases  ->  export + trace
```

## Input and output

- `[VERIFIED]` `python3 builder/build.py {brief_path} {tool_api_path}` (the kit's sample builder also accepts Brief A plus B together).
- `[VERIFIED]` Output: Freya phone agent, exported with `freya.export_workflow`; a trace of the run.
- `[VERIFIED]` Briefs vary: a clean specification, or raw material (mail, policy extract, a memo that changes the policy, a code list). Tool field names and allowed values vary per brief.

## MVP scope

1. Entry point `builder/build.py` that completes one run end to end.
2. Read the brief and the OpenAPI file; no assumption about brief layout beyond text.
3. Extract rules, allowed actions, prohibitions, dates and codes, each with a source excerpt.
4. Resolve overrides and conflicts (later memo over earlier policy) explicitly.
5. Bind to tools using only what the OpenAPI file defines.
6. Render a workflow: steps, prompts, per-step tools, conditional routes.
7. Create or update the workflow in place and publish it.
8. Self-test within the 30-minute budget; write the trace.

## Out of scope

- Telephony, STT/TTS, local agent runtime.
- Dashboard, SaaS UI, fine-tuning, model router.
- Anything specific to the two practice briefs that would not generalize.

## Success measure

`[VERIFIED]` Cases passed / 60 on hidden briefs, each case passing only if outcome, policy and honesty all pass in 3 of 3 runs. Tie-breakers: promised amount, shorter build time, earlier submission.

## Topic ownership

- Components: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Typed contracts: [`IR-SPEC.md`](IR-SPEC.md)
- Freya boundary: [`FREYA-INTEGRATION.md`](FREYA-INTEGRATION.md)
- Domain rules: [`COLLECTIONS-POLICY.md`](COLLECTIONS-POLICY.md)
- Evidence and scoring: [`EVALUATION-AND-TESTING.md`](EVALUATION-AND-TESTING.md)
- Completion gates: [`DEFINITION-OF-DONE.md`](DEFINITION-OF-DONE.md)
