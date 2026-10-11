# Freya Integration

**Owner:** Freya boundary, verified provider behavior and adapter  
**Read when:** Touching authentication, workflow payloads, agent lifecycle, simulations or provider errors

Facts and the API table are in [`STARTER-KIT-FACTS.md`](STARTER-KIT-FACTS.md). The workflow JSON itself is specified in `build-the-builder-v2/docs/workflow-format.md` and `tools-and-code.md`; follow those, do not paraphrase them here.

## Where Freya is called `[VERIFIED: code, commit d5f6af1]`

| Step | Code | What it does |
|---|---|---|
| Dry run | `build.py` -> `freya.validate_workflow(slot, workflow)` | `POST /api/v2/workflow?dryRun=true`. Runs in `--validate` and before every save; the platform's rejection text becomes the build error. |
| Save | `slots.save_with_slot_check` -> `freya.save_workflow` | If the slot's stored workflow returns 404, the stale entry is dropped and a new workflow is created (F-005). Otherwise the workflow is updated in place. The slot map is `.freya-agents.json` (git-ignored). |
| Model setting | kit `update_workflow` | After the update the kit reads the platform-filled `agent_config` and sets `llmConfig` to the kit's `AGENT_LLM`. The builder itself never sends `agent_config`. |
| Publish | `build._ensure_published_version` | Publishes the newest version if it is not published, reads the versions back and fails if it is still unpublished. The version number goes to the trace (`published_version`). |
| Export | `freya.export_workflow` | Writes `submission/<slot>.workflow.json` before the self-test, so a failing self-test never blocks the artifact. |
| Self-test | `freya_chat.chat_message` / `get_call` / `end_chat` | Bounded chat turns against the published workflow (see [`EVALUATION-AND-TESTING.md`](EVALUATION-AND-TESTING.md)). |

- `builder/freya.py` is byte-identical to the kit's `freya.py`. Additions live in `freya_chat.py` (it reuses the kit's `URL`, `HEADERS` and error format) and `slots.py`.
- Besides `build.py` and `freya_chat.py` (which takes the kit's `URL` and `HEADERS`), no module imports `freya`. `--print` makes no Freya call.
- Keys: `FREYA_API_KEY`, `FREYA_BANK_TEAM_KEY` and `ANTHROPIC_API_KEY` come only from the environment. `run_trace.py` masks their values and the `fak_…` / `sk-ant-…` patterns in every trace line. The builder never uses the bank team key; only the kit's `run_cases.py` does.
- A save without `FREYA_API_KEY` stops before any request with a clear error.

## What the renderer sends `[VERIFIED: code + tests]`

These are the kit format rules as the renderer applies them. The trace proves the first rule for every run (`sent_agent_config: absent`, `sent_nulls: 0`), and `tools/submission_check.py` checks those two lines.

- No `agent_config`, no `null`. Node `name` equals its key.
- Tools come from the OpenAPI file (`tools_from_openapi.py`): `$ref` and `allOf` are resolved, enums and required fields are kept, and constraints the format cannot hold move into descriptions. Call variables (`customer_id`, …) are baked as `{{variable}}` defaults. Model-filled fields keep no variable of the same name.
- Fixed arguments use `default`, never `const`. Tool-specific values (outcome, reason, product id) are baked or filled by a pre-hook, not by the model, where the spec provides them.
- Values the model must not type are filled by code:
  - the callback date and time: `callback_check` resolves them, and `callback_book` sends `{{callback_date}}` / `{{callback_time}}` (F-055);
  - the promise's product: `record_next` picks it, and the `record_promise` hook writes `promise_record_number` into the body before the values hook (F-063).
- Spoken lines (F-050, F-056):
  - `tts` appears only on conversation-step entries (the twins `offer_say`, `revise_ask`, `third_party_ask`, the ask of a special path, a returning special path without a tool), on the code step `closing_say`, and on the code entry of a returning special path with an engine tool (none in the current specs);
  - no `api_request` step speaks;
  - the closing turn has one spoken message.
- `response_mapping` sits on the tool for `tools` and on the node for `pre_actions`; paths start with `data.`. Booleans are tested as both `"true"` and `"True"`.
- Every tool has the `post_process_code` hook that normalizes `data.ok` and writes `what_to_do_next` (see [`ARCHITECTURE.md`](ARCHITECTURE.md), "Messy inputs").
- Retries:
  - Every tool except `get_account` has `maxRetries: 0` (write tools and also `verify_identity`, `schedule_callback` in `callback_book`, `create_promise` in `record_promise`); the flow decides any retry.
  - A promise is retried per product up to the spec's `confirmation.max_attempts_per_product`: `confirmation_progress` -> `record_next` takes the same product again.
  - The first product whose attempts are used up ends the loop, and later products are not tried (F-063 decision).
  - A failed callback booking closes the call as `callback_failed`.
  - `close_call` is retried once when it did not return ok (`close_attempt` -> `close_record`, at most two sends).
  - `get_account` runs as a pre-action with `maxRetries: 1`.
- `close_call_on_hangup` is a workflow-level lifecycle tool (`alwaysRunsAt: ["end_of_call"]`). Its pre-hook blanks the URL when the closing chain already sent `close_call`, so one call never records two closes. Otherwise it derives the outcome from call state.
- Code steps and hooks contain no `{{ }}`, read and write only `vars`, are wrapped in `try/except`, and are generated from spec data (`offer_check.py`, `workflow.py`).
- Every path reaches `end_call`; passthrough nodes end with an `always` transition. One transition per target (`group_transitions_by_target`, T-005c).
- Nothing in the workflow calls a service other than the bank tool API.

## Verified platform behavior (from our runs)

Details and causes are in [`UAT-FINDINGS.md`](UAT-FINDINGS.md).

- The chat route can return 503/504 on a turn that was in fact processed (F-023). The self-test reads the call record before resending.
- In chat, routing right after a tool result can be suppressed (F-021), and `end_call` is deferred: a later message resumes the conversation (F-031). The self-test stops sending after the call ends.
- The platform's default `agent_config` has Turkish STT/TTS and inserts a Turkish wait filler on slow passthrough steps (F-043).
- A `tts` `on_enter` on a passthrough `api_request` step followed by more passthrough steps made the turn return 502 and roll the call back to `identity`, although the tools had run (F-050, confirmed by experiment). So the `account` step is silent again, and the identity step says the wait line in its last message after the answers matched. Live on version 12: no 502 at the end of identity, but the Turkish filler still appeared once during a slow turn (F-051 run).
- A 5xx turn can keep its tool calls but lose the node and variables (F-049). `identity_check` lets a replayed turn leave identity when it is already verified, and the self-test reports such a turn as `platform_error` without resending.
- The exported file always contains a platform-filled `agent_config` and `null` defaults (T-008 review). Only the sent definition is checked for them.
- A code step's write that does not fit the variable's extraction type (`""` for an enum or a float) is rejected (`validation_errors`), and the old value stays (F-052). Resets use `none` and the amount sentinel (F-060).
- Observed on version 13 (PUB-09, PUB-02; F-056, F-057):
  - a turn with two spoken messages was recorded as finished at the first one;
  - a message after the goodbye resumed as a branch (`isBranch: true`) from that message, or from the previous turn after a lost 5xx response;
  - the call variables were those of that earlier point, and the agent spoke again;
  - at hang-up the end-of-call tool sent a second `close_call`, which the bank refused but which shows in the ledger.

  Why the state is lost on a branch, and whether the judge's simulation can send a message after the goodbye, is `[TO-CONFIRM, platform]`.
- `[TO-CONFIRM]` In that branched state a global path matched from a global step that its `excluded_nodes` lists (F-058).

### Open live checks `[TO-CONFIRM]`

Forms built offline since version 13 that have not run on Freya yet:
- `callback_check` -> `callback_book`, including a day and a time given in separate messages (PUB-02, F-055).
- `offer_say` speaking the check result and the negotiate calendar (PUB-07, F-053/F-054).
- A closing special path:
  - its silent global code entry, with the line said only by `closing_say` (PUB-09, F-056/F-059);
  - a forced transfer failure;
  - a model-filled closing tool step staying silent with its tool call.
- `confirm_record` routing on the extracted yes before the model speaks (F-063).
- The record loop's long passthrough chain in one turn (three products plus the closing chain; PUB-11).
- Whether a message after the goodbye can reach the judge's simulation (F-057), and `excluded_nodes` on global steps (F-058).

## Testing through Freya

Every Freya action needs approval (AGENTS.md). The order is chat first, voice only after chat passes.

- Single chat turns: `POST /api/v2/chat/message` (no queue). The builder's own self-test uses this route.
- Scored practice runs: the kit's `tools/run_cases.py <agent_id> --brief A|B` (simulations, one at a time per workspace).
- Debug: `freya.get_call(call_id)["messages"]`, specifically the `node_enter`, `route_evaluated` (with `variable_table`) and `function_call_start` / `function_call_complete` events.

## Vertical slice `[VERIFIED: done]`

1. 2026-10-10: kit baseline (one node, brief as prompt) scored 6/10 on Brief A.
2. `builder/build.py` reads tools from the OpenAPI file and creates, publishes and exports a workflow end to end (T-001). The latest local live run is the official command on Brief A (2026-10-10 20:39 UTC, published version 12, 193 s, extraction + save + publish + export + 3 self-test cases: 2 pass, 1 `platform_error`): `traces/brief-a.log`, `traces/brief-a.spec.json`, `submission/brief-a.workflow.json`. `traces/` and `submission/` are **not committed yet**, so a fresh clone does not have these files. `traces/<slot>.log` is overwritten by the next run on the same slot; copy it, or use a new `--slot`, right after a run that serves as evidence.
3. The structured pipeline above replaced the single-step agent. `--single-step` still exists as the legacy path.

## Safe behavior

When a critical rule cannot be expressed safely in the Freya format, the builder fails the build with a precise error (`SpecError`: unknown tool, missing contract field, invalid spec) or uses a documented safe fallback (the global prompt). It never claims enforcement stronger than the platform gives, and never fabricates an agent ID, API success or test result. A rule placed only in a prompt is marked as such in the trace (`rule_placement`).
