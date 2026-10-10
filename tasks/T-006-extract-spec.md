# T-006 — Extract the spec from the brief (no hand-written spec)

**Owner:** claude-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

## Why

Today the agent is built from a hand-written spec (`--spec tests/fixtures/spec-brief-a.json`). Hidden briefs arrive Sunday 17:00 UTC; the builder must produce the spec itself from `brief + OpenAPI`, within the 30-minute budget, reproducibly. This is the step that decides the score.

Read first: `AGENTS.md`, `docs/ARCHITECTURE.md` ("Messy inputs", "Builder model"), `docs/IR-SPEC.md`, `docs/COLLECTIONS-POLICY.md`, `builder/spec.py` (the contract: whatever it accepts is the target), the three fixtures in `tests/fixtures/`, both practice briefs, `build-the-builder-v2/tools/openapi.json`, `tasks/T-005b-report.md` … `T-005e-report.md` (spec fields added since T-004).

## Design

New module `builder/extract.py` (plus a small `builder/llm.py` client).

1. **Client:** Anthropic Messages API over stdlib `urllib`. Key from the `ANTHROPIC_API_KEY` environment variable, never logged or written anywhere. Model name pinned in one place (default `claude-sonnet-5-5`), temperature 0. Every call goes to the trace: purpose, model, input/output tokens, duration. One retry on transport errors.
2. **Extraction in sections, not one giant call.** The spec has sections (agent, opening, third_party, identity, account, offer/negotiation, confirmation, special_paths, outcomes/closing, global_rules). Group them into a few calls that can run **in parallel** (threads), each with the whole brief, the relevant OpenAPI enums and the JSON shape of its sections. Each rule carries a `source` excerpt from the brief.
3. **Validate with code, then repair.** Merge the sections and run `spec.load`/validation plus extra checks: values in OpenAPI enums, every call-end state mapped in the outcome table, outcome/reason pairs allowed by `close_call`, dates parse, numbers parse, holiday dates valid, identity fields in the enum, later documents overriding earlier ones marked (memo over policy). On errors, send only the errors and the failing section back to the model (at most 2 repair rounds). Arithmetic (business days, deadlines) is never done by the model; it only extracts rule data.
4. **Coverage check.** One call (or code + one call) lists every brief sentence or table row and maps it to a spec path or "not relevant". Unmapped relevant sentences get one targeted re-ask. The trace lists unmapped items.
5. **Output:** `traces/<slot>.spec.json` (the extracted spec, committed with the submission trace) and the normal build continues with it. `build.py` without `--spec` now extracts; `--spec` keeps working for tests and comparisons.
6. **Failure:** if validation still fails after repairs, the build stops with a clear error listing the failing fields (never a silent partial agent).

## Prompts

Extraction prompts live in `builder/prompts.py` and appear in `docs/PROMPTS.md`. Generic: no practice-brief values, no outcome names, no holiday dates. They describe the spec fields and the collections domain, and ask for source excerpts.

## Tests

- **Offline (default `python3 -m unittest`):** a fake client returns recorded responses; the pipeline merges, validates, runs repair on a deliberately broken response, and produces a valid spec. Parallel calls, trace lines (no key), failure path.
- **Comparison tool** `tools/compare_spec.py <extracted> <fixture>`: field-by-field diff that ignores wording and reports values that matter (identity fields and order, outcome table, offer rules, calendar, special paths, sentences present).
- **Live runs are done by the CTO**, not by you: write the exact commands in the report. Anthropic calls are allowed for the CTO; Freya calls still need user approval.

## Constraints

Python 3.10+, stdlib only. No Freya requests. No commit. Do not read `env.sh` and never print the key. No brief values in `builder/`. Total extraction time target: under 5 minutes per brief. Record failures in `docs/UAT-FINDINGS.md`. Report in `tasks/T-006-report.md`: design, call plan (how many calls, which in parallel), validation and repair rules, coverage method, the live-run commands, open questions.
