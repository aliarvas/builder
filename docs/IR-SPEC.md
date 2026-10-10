# Intermediate Representation Specification

**Owner:** Typed contracts, provenance and validation invariants  
**Read when:** Editing schemas, extractor output, tool binding or validation

The IR is the provider-neutral contract between brief analysis and Freya rendering. Examples are internal sketches, not Freya payloads.

## Core records

### `AgentSpec`

- `schema_version`, `source_hash`, `compiler_version`
- `persona`, language, call purpose, opening and closing wording rules
- `rules`: list of `SourcedRule`
- `tools`: list of `ToolDescriptor` (from OpenAPI)
- `flow`: states and transitions
- `outcomes`: values accepted by the close/record tools, with their reasons and the rule that selects each (outcome table)
- `parameters`: typed tables extracted from the brief and passed to generated code, never written into builder code: calendar (business-day definition, holidays), bands (e.g. by days late) with deadlines and attempt counts, amount floors and bounds, identity questions with attempt limits, callback window, queue names
- `unresolved`: ambiguities and conflicts left open

### `SourcedRule`

- Stable rule ID and typed kind (identity check, disclosure limit, allowed payment date, forbidden action, closing, escalation, ...).
- Normalized value (dates, amounts, code values, windows).
- `source_excerpt` and location in the brief.
- `origin`: `explicit`, `inferred` or `fallback`. An inference or fallback is never presented as an explicit bank instruction.
- `supersedes`: IDs of rules it overrides (memo over policy, later over earlier) and why.
- `enforcement`: `platform_guard`, `code_guard`, `prompt` or `test_only` (see [`COLLECTIONS-POLICY.md`](COLLECTIONS-POLICY.md)).

### `ToolDescriptor`

- Name, purpose, HTTP method/path, input and output schema, required fields, enum values, side-effect flag. All taken from the supplied OpenAPI file.
- Which flow states may call it, and its preconditions.

### `Parameters`

Typed data the generated code nodes read at call time. Each entry carries a `SourcedRule` reference, so a wrong number can be traced to the brief sentence it came from. Values are normalized (ISO dates, numbers) at extraction time; text such as "the 12th business day" is stored as a rule with a count and unit, evaluated by generic code against `now`.

### Flow

- Entry state, states, allowed transitions, transition conditions (based on tool results or collected data), terminal states with an outcome.
- Likely baseline: identity check -> account/product discussion -> promise or refusal -> close. `[HYPOTHESIS]` Actual states come from the brief.

## Invariants

- Every rule has provenance. No rule exists without a source excerpt or an explicit `inferred`/`fallback` origin.
- Every tool a rule or state needs resolves to a descriptor in the OpenAPI file.
- Every enum or code used at render time exists in the OpenAPI file or the brief; none are invented. An outcome/reason pair used by `close_call` must appear in the brief's outcome table.
- A memo or later document that changes a rule produces a `supersedes` link; the older value is not used.
- A side effect is never reported as done without the tool result confirming it.
- Every terminal state maps to an allowed outcome; all states are reachable.
- Conflicting rules are resolved by a documented order, or block the build with a clear error, or use a documented safe fallback.
- No bank name, balance, date, holiday or offer is hardcoded in builder code.
- No secrets in the IR or trace.

## Versioning

Store schema version, source hash and creation time with each IR. Schema changes are explicit; an old IR is never silently reinterpreted.
