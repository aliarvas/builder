# T-003 — Hardening: tolerant OpenAPI, tool triggers, readable tool results

**Owner:** codex-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

## Goal

Small, independent fixes that every later step needs. No new nodes yet (that is T-004). See `docs/ARCHITECTURE.md` "Messy inputs".

## Scope

1. **Tolerant OpenAPI (review N1, N2).** A hidden tool file must never crash the build.
   - `type` given as a list: take the non-null type, add `nullable: true` only if the dry run accepts it (otherwise mention it in the description).
   - Missing `type`: use `string` (or the enum's value type) and write a `warning:` line to the trace. Continue.
   - Wrap any unexpected parsing error per field: skip that field's constraint, keep the field, warn. Only a missing server URL or an unreadable file stops the build.
   - Schema keys the Freya dry run has not been shown to accept (`pattern`, `nullable`, `allOf`/`oneOf`/`anyOf`, `minLength`, `maxLength`, ...) move into the field `description` in plain words, not into the schema. Keep in the schema only `type`, `description`, `enum`, `default`, `items`, `properties`, `required`. (CTO will run one approved dry run later to see if more keys can stay.)
   - Path-item `parameters`: warn and ignore instead of failing.
2. **Tool descriptions with triggers (review 11).** Build each tool description from the OpenAPI summary plus a generic trigger sentence: "CALL this tool to <summary>. Saying you did it is not enough." No tool-specific wording in code; the sentence is the same template for all tools.
3. **Baked-name collision check (review 11).** If a model-filled field name equals a call variable or another variable known at node entry, rename the placeholder (e.g. `{{<tool>_<field>}}`) so the model still sees the field. Test it.
4. **Readable tool results.** Add a generic `post_process_code` to every `api_call` tool, following `build-the-builder-v2/docs/tools-and-code.md`:
   - wrapped in `try/except`, no `{{` `}}`, `isinstance` checks;
   - removes `header`;
   - adds `result["data"]["what_to_do_next"]`: if `ok` is false or the HTTP status is not 2xx, a sentence saying the action was NOT carried out and must not be reported as done; otherwise a sentence saying the action succeeded and the agent must now speak to the customer or call the next tool.
   - Generic text only, no tool names or brief values.
5. **Prompt rule.** Append to the system prompt (in `builder/prompts.py` after T-002): one tool call per message; after every tool result, speak or call the next tool; never claim an action succeeded unless the tool result says so.
6. **UAT.** If you observe any failure while working, add an F-xxx entry to `docs/UAT-FINDINGS.md`.

## Tests (offline, stdlib `unittest`)

- OpenAPI with list types, missing types, `allOf`, path parameters, unknown keys: build succeeds, warnings recorded, schema contains only allowed keys.
- Collision: a body field named like a call variable that is not meant to be baked keeps a model-visible placeholder.
- Post-hook code: `compile()` succeeds, contains no `{{`/`}}`, and executed against sample envelopes (ok true, ok false, HTTP 500, missing data) never raises and writes the right `what_to_do_next`.
- Existing tests stay green; `docs/PROMPTS.md` regenerated if prompts changed.

## Constraints

Python 3.10+, stdlib only. No Freya requests of any kind. No commit. Do not read `env.sh`. No brief values in code or prompts.

## Done when

`python3 -m unittest` passes; `--print` for Brief A works; short report listing what changed and which schema keys were moved to descriptions.
