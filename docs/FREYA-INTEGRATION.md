# Freya Integration

**Owner:** Freya boundary, verified provider behavior and adapter  
**Read when:** Touching authentication, workflow payloads, agent lifecycle, simulations or provider errors

Facts and the API table are in [`STARTER-KIT-FACTS.md`](STARTER-KIT-FACTS.md). The workflow JSON itself is specified in `build-the-builder/docs/workflow-format.md` and `tools-and-code.md`; follow those, do not paraphrase them here.

## Adapter responsibilities

- Render validated IR to the Freya workflow format and nothing else.
- `POST ...?dryRun=true` before saving; report the platform's rejection text.
- Save with create-then-update-in-place; always publish the new version (an unpublished update is not simulated). `freya.save_workflow` does both.
- Read the saved workflow back after saving when in doubt: the platform silently strips misplaced fields (`tools` outside conversation nodes, `pre_actions` outside action nodes).
- Export with `freya.export_workflow`.
- Keep `FREYA_API_KEY`, `FREYA_BANK_TEAM_KEY` out of logs, traces and the repo.
- Never change the phone-agent model. Omit `agent_config`.
- Normalize errors; separate retryable (timeouts, 5xx) from validation/auth errors.

The adapter must not read the brief, invent policy, or silently drop a critical rule the format cannot express.

## Format rules the renderer must obey (from the kit)

- No `null` values. Node `name` equals its key.
- Fixed values use `default`, never `const`. `customer_id` is baked from `{{customer_id}}`; other body fields have `default: "{{field}}"` with no variable of that name, so the model fills them. A model-filled field must not share a name with a variable already set on node entry.
- Give model-filled fields `enum`s from the OpenAPI file; add descriptions that say when to call the tool ("CALL it only after ...").
- `response_mapping` on the tool for `tools`, on the node for `pre_actions`; paths start with `data.`.
- Test booleans as both `"true"` and `"True"`, or map a string field.
- Every path reaches an `end_call` node; passthrough nodes end with an `always` transition; set `max_turn_transition` wherever `max_node_turns` is set.
- Code: no `{{ }}`, wrap in try/except, read inputs from `vars`, write finished text facts to `vars`.
- Write tools get `maxRetries: 0` at the tool level; retry decisions are made in the flow (a failed `create_promise` is retried once by the agent).
- Add a `post_process_code` hook with a `what_to_do_next` line where the model tends to go silent or ignore a negative result (identity answers, promise recording).
- Do not add anything to a node that calls services other than the bank tool API.

## Testing through Freya

- Fast single-turn check: `POST /api/v2/chat/message` (no queue). Note: the chat route may skip a code step that is the first node, so values computed there can be empty in chat but exist in simulations.
- Simulations: `freya.run_simulation` with personas; one at a time per workspace; budget the 30-minute builder limit.
- Debug a failure: `freya.get_call(call_id)["messages"]` and its `route_evaluated` / `function_call_*` events, including `variable_table`.

## First vertical slice

1. `cp env.example env.sh`, fill keys, `source env.sh`.
2. `python3 examples/minimal_builder.py briefs/brief-a.md`; note `agent_id`.
3. `python3 tools/run_cases.py <agent_id> --brief A`; record the baseline in `docs/EVALUATION-AND-TESTING.md` results.
4. Build `builder/build.py` reproducing the minimal builder but reading tools from the OpenAPI file, then export a workflow. This proves the contract end to end.
5. Only then add the structured pipeline.

## Safe behavior

When a critical rule cannot be expressed safely in the Freya format: fail the build with a precise error, or use a documented safe fallback. Never claim enforcement stronger than the platform gives. Never fabricate an agent ID, API success or test result.
