# Starter Kit and Competition Facts

**Owner:** Verified facts about the competition and the Freya platform  
**Sources:** Official page https://www.freyavoice.ai/hackathon (read 2026-10-10) and the starter kit in `build-the-builder-v2/` (README, `docs/`, `freya.py`, `tools/`, `briefs/`, `public-test-set.json`). Where they differ, the kit is newer and wins; the difference is listed in "Conflicts".

`[VERIFIED]` Kit version: `build-the-builder-v2/` holds **kit v3** (`VERSION` = 3, 10 October 2026) and is the current kit. The v1 kit folder was removed from the repo on 2026-10-10. Compared with v1, only the README and `examples/` changed: `minimal_builder.py` was replaced by `examples/base-agent.json` (2-step, 4-tool example agent), `examples/agent_builder.py` (Claude Agent SDK builder that writes `traces/<time>.jsonl`) and the skill `.claude/skills/build-phone-agent/SKILL.md`. `docs/`, `tools/`, `briefs/`, `freya.py` and `public-test-set.json` are identical. Submission and trace rules did not change.

Only facts here. Design choices live in the owner documents. Detail pages of the kit stay authoritative for the workflow format: `build-the-builder-v2/docs/workflow-format.md`, `tools-and-code.md`, `api.md`.

## Final format (organizer page update, read 2026-10-11 ~19:30 Istanbul; overrides older lines below)

- `[VERIFIED]` **The case.** The final is ONE case: Freya Bank's credit-card statement-debt line, **in Turkish**.
  - It opens Sunday 17:00 UTC (20:00 Istanbul) as one zip, on the Submit tab and by e-mail.
  - The closing time is unchanged: Sunday 20:00 UTC (23:00 Istanbul).
- `[VERIFIED]` **The zip.**
  - Bank documents in Markdown, Word, PDF and Excel. Read BRIEF.md first; README.md describes each document.
  - The bank's test customers and 6 sample conversations.
  - The scoring customers are hidden.
- `[VERIFIED]` **The mock.** We write and host the bank mock ourselves on Cloudflare Workers, from the service contract and the test customers.
  - It must be live before the builder runs, and must stay up until the results are out.
  - The agent may call only our mock. A wrong or unreachable mock fails those calls.
- `[VERIFIED]` **The command.** The sample command is now `python3 builder/build.py {case_folder} {mock_url}`. Our builder accepts both this form and `{brief_path...} {tool_api_path}` (T-040).
- `[VERIFIED]` **Submission.** One `submission.json` with these fields:
  - `team` and `members` (name, email);
  - `repo` and `commit`;
  - `run_command`;
  - `workflow` (one file) and `trace` (one file);
  - `mock_url`.

  One agent per team.
- `[VERIFIED]` **Scoring.**
  - The workflow is uploaded into the organizers' workspace, tested with unseen simulated customers, and inspected.
  - The criteria and weights are not published.
  - The trace is not scored, but an entry without one is not ranked.
- `[VERIFIED]` **Fixes after the opening.** Builder bug fixes are allowed after the final opens; nothing from the final case may be written into the code.

## Competition

- `[VERIFIED]` "Build the Builder", Freya x Y Combinator. Solo or team of two.
- `[VERIFIED]` Domain: debt collection by phone agent. Calls are English and text-based in the simulations.
- `[VERIFIED]` Terms: **brief** = the bank's specification; **builder** = our program; **phone agent** = a Freya workflow (steps/nodes, prompts, tools, conditional routes).

## Builder contract

- `[VERIFIED]` Run: `python3 builder/build.py {brief_path} {tool_api_path}`. Brief B builds on Brief A, so the sample builder takes several brief files; the final contract is one brief plus one tool API file per run.
- `[VERIFIED]` Output: a phone agent on Freya, exported with `freya.export_workflow(workflow_id, "<brief>.workflow.json")` and submitted. Organizers load the export into their own workspace, so the export is what is scored.
- `[VERIFIED]` No manual step; no hand edits to a created phone agent.
- `[VERIFIED]` Call variables always present: `customer_id`, `first_name`, `last_name`, `title`, `now` (current date-time such as `2026-10-14T11:00`; all date rules use it, never the real clock).
- `[VERIFIED]` Seven tools, names fixed: `verify_identity`, `get_account`, `create_promise`, `add_note`, `schedule_callback`, `transfer_to_agent`, `close_call`. In a final brief their fields and allowed values may change; each final brief ships its own tool API file.
- `[VERIFIED]` The bank API does not enforce the brief. It records a promise on a holiday or past a deadline without complaint.

## Kit contents (in `build-the-builder-v2/`)

`README.md`; `VERSION`; `briefs/brief-a.md` (47 rules, one product), `briefs/brief-b.md` (up to three products, builds on A); `tools/openapi.json`; `public-test-set.json` (13 cases); `examples/base-agent.json` (2-step example agent; 2/13 in the organizers' run); `examples/agent_builder.py` (Claude Agent SDK builder; needs `pip install claude-agent-sdk` and a Claude login or `ANTHROPIC_API_KEY`; default model `claude-opus-5-5`; 10/10 on Brief A in one organizer run); `.claude/skills/build-phone-agent/SKILL.md`; `freya.py`; `tools/run_cases.py`, `tools/score.py`; `docs/workflow-format.md`, `docs/tools-and-code.md`, `docs/api.md`; `env.example`.

## Environment

- `[VERIFIED]` Python 3.10 or newer, standard library only needed.
- `[VERIFIED]` Variables: `FREYA_API_KEY` (starts `fak_`), `FREYA_API_URL=https://staging-app.freyavoice.ai`, `FREYA_BANK_TEAM_KEY` (any secret of 16+ characters we choose, always the same). `FREYA_WORKSPACE_ID` optional.
- `[VERIFIED]` Every request needs a browser-like `User-Agent` (otherwise HTML `error code: 1010`). `freya.py` sets one.
- `[VERIFIED]` Responses are wrapped `{success, data: {message, result}}`; the payload is `data.result`. Workflow and call routes are singular, persona and simulation routes plural.

## Scoring

- `[VERIFIED]` A customer (case) is handled only if all three hold: **Outcome** (bank ledger: outcome/reason, every promise's product/amount/date, notes, callbacks, transfers all match), **Policy** (judge model on the transcript, against the checks listed for that customer), **Honesty** (judge model; e.g. never says a promise is recorded when the tool failed). No partial credit.
- `[VERIFIED]` Correct refusal counts (e.g. dispute: record no promise, close correctly).
- `[VERIFIED]` Hidden benchmark: 2 briefs x 30 customers, several calendar days, three runs each, all three must pass. Final score = cases passed / 60 (page).
- `[VERIFIED]` Tie-breakers in order: total promised amount on passing cases; shorter build time; earlier submission.
- `[VERIFIED]` One run can pass and the next fail for the same agent. One green run is a hint, not proof.

## Hidden (final) briefs

- `[VERIFIED]` Same kind of call, different rules: other numbers and limits, other identity questions, another outcome table, another calendar. One brief is a clean specification; the other is raw bank material (a mail, a policy extract, a memo that changes it, a code list).
- `[VERIFIED]` Final customers may have up to three products and talk like people: numbers in two parts, self-corrections, side talk, questions back, amounts and dates in words.
- `[VERIFIED]` After they open (Sun 17:00 UTC) we may fix builder bugs (e.g. crash on an unexpected table format). We may not write anything from a final brief into the builder: no rule, value, holiday date, name or outcome name.
- `[VERIFIED]` Run the builder once per final brief with no manual step. Submit the phone agents, code and trace. Several runs allowed; submit the agent of one run with that run's trace.

## Limits

- `[VERIFIED]` Builder run: 30 minutes per brief, including any test on its own agent.
- `[VERIFIED]` The phone agent runs on the model in `freya.py` (`AGENT_LLM`, provider and model `experimental-5`). Do not change it. The builder may use any model or coding agent; we pay.
- `[VERIFIED]` The phone agent may call only the bank's tool API. Code steps and hooks inside the workflow are allowed.
- `[VERIFIED]` One simulation at a time per workspace; ten customers take 3 to 11 minutes. A second run waits for the first.
- `[VERIFIED]` Update a workflow in place (`freya.save_workflow`). Workflow cap per workspace: see "Conflicts".
- `[VERIFIED]` One Freya key per team; no probing or load-testing. All data synthetic.

## Timeline (UTC) `[VERIFIED, page]`

Sat 10 Oct 10:00 kit and keys. Sun 17:00 hidden briefs open. Sun 20:00 submission closes. The three hours are for running the builder and fixing bugs, not for tuning to the new briefs.

## Submission `[VERIFIED, page]`

- Per final brief: the exported workflow JSON (committed) and a trace. Example paths: `submission/hidden-1.workflow.json`, `traces/hidden-1.log`.
- Form fields: `team`, `repo`, `commit`, `run_command`, `workflows` (path per brief), `traces` (path per brief). Send before 20:00 UTC to the address in the kit email.
- Trace (plain text, no fixed format, no API keys): start and end time; every model call (model and one-line purpose); what was created on Freya (workflow ID, agent ID, number of steps and tools); any test the builder ran on its own agent and the result. Optional: coding-agent session logs.
- Verification: top teams are rerun from the submitted commit on the same briefs and compared with the trace. A reviewer agent checks each trace against the code and the agent. Entries whose reruns score clearly lower are removed.

## Freya API surface used by the builder `[VERIFIED, kit api.md and freya.py]`

| Need | Call |
|---|---|
| Validate only | `POST /api/v2/workflow?dryRun=true` (body `{name, workflow}`) |
| Create | `POST /api/v2/workflow` -> `workflow.id`, `workflow.agentId` |
| Update | `PUT /api/v2/workflow/{id}` (body replaces everything) then publish a new version: `GET /api/v2/versions/workflow/{id}?workspaceId=`, `POST .../publish {versionId}`. An unpublished update is not simulated. |
| Read | `GET /api/v2/workflow/{id}?workspaceId=` |
| Fast chat check | `POST /api/v2/chat/message {workflowId, message, customerVariables, callId?}`; end with `POST /api/v2/chat/end` |
| Personas | `POST /api/v2/personas` |
| Simulation | `POST /api/v2/simulations` (mode `chat`, `customerVariablesMap`, models overrides), poll `GET /api/v2/simulations/{id}`, iterations and runs, `GET /api/v2/call/{callId}` for transcript and events |
| Bank practice ledger | `POST /v1/practice/sessions {case}`, `GET /v1/practice/ledger/{customer_id}` on the mock bank host with header `x-team-key` |

`freya.py` functions: `create_workflow`, `save_workflow(slot, workflow)` (stores ids in `.freya-agents.json`), `validate_workflow`, `update_workflow`, `export_workflow`, `create_personas`, `run_simulation`, `get_iteration`, `get_call`. Simulation customer and judge model: `gemini-3-flash-preview`.

## Workflow format essentials `[VERIFIED, kit workflow-format.md and tools-and-code.md]`

- Per turn the platform makes three model calls: extraction (fills variables), routing (picks a transition; does not see the dialogue prompt), dialogue (writes the reply or calls tools). Routing instructions in `task_message` do nothing.
- Top-level keys: `initial_node`, `nodes`, `global_nodes`, `system_prompt`, `test_variables`, `tools` (lifecycle), optional `context_variables` (unreliable). **Omit `agent_config`.** No `null` values anywhere.
- Node types: `conversation` (prompt + `tools` + `extraction_schema` + transitions), `api_request` and `code` (engine-run `pre_actions`, passthrough), `end_call` (terminal, farewell comes from the terminal's `spoken_message`).
- `tools` are kept only on conversation nodes; `pre_actions` only on `api_request`/`code`. The platform drops misplaced fields silently.
- Tool parameter values: a `default` with a literal or an already-set `{{var}}` is baked; a `{{var}}` default with no value at entry is filled by the model; `const` does not bake. Body fields are leaves under `body.properties`. Use `enum`s for known sets.
- Tool results land as `<tool>_response.data.<field>` (also `_args`, `_success_count`, `_failure_count`). Mapping paths start with `data.`. Booleans arrive as strings: test both `"true"` and `"True"`.
- Transitions: first match wins; deterministic operators (`equals`, `not_equals`, `greater_than`, `less_than`, `contains`, `is_set`, `is_not_set`, `always`) cost no model call; `matches_intent` uses the routing model. Top level is always `logic: or`; nest `and`. Routing reruns after a tool result, in the same turn. A node needs an `always` fallback; passthrough nodes must end with one.
- Code: `code_exec` snippets get a mutable `vars` dict (call variables included, e.g. `vars.get("now")`); only `json`, `re`, `datetime` verified. No `{{ }}` in code, never raise. Values written to `vars` resolve as `{{name}}` in later prompts. Do date arithmetic in code and give the model finished facts.
- Hooks on `api_call` tools: `pre_process_code` (edit `vars`/`config` before the call) and `post_process_code` (edit `result`, an envelope whose body is `result["data"]`). A `what_to_do_next` line added in a post-hook fixes the model going silent or ignoring a negative result after a tool call.
- Lifecycle tools in top-level `tools` with `config.alwaysRunsAt` (`start_of_call`, `end_of_call`) are engine-fired and hidden from the model.
- `max_node_turns` default 10; set `max_turn_transition`.

## Prompt size guidance `[VERIFIED: Freya guidance relayed by the user, 2026-10-10]`

- For chat, a prompt of **500 to 1,500 tokens** is ideal.
- `[TO-CONFIRM]` Scope: assumed to mean the dialogue prompt of one step (`system_prompt` + `role_message` + `task_message`), not the whole workflow and not the tool schemas.
- Measured: our T-001 agent has one step whose `task_message` is about 2,600 tokens (whole Brief A pasted in) plus about 1,600 tokens of tool schemas. Over the limit.

## Practice material

- `[VERIFIED]` `public-test-set.json`: 13 cases (PUB-01..10 for Brief A, PUB-11..13 for Brief B), all with `now` = `2026-10-14T11:00`. Each has identity answers, products, a customer script, `expected` bank records and `checks` for the judge. PUB-10 injects a fault (`create_promise` fails the first time).
- `[VERIFIED]` Families: happy path, third party, identity failure, dates (after deadline, vague then holiday), hardship, amounts (floor), already paid, restructuring, tool failure, multi-product (all, some, deadline differs).
- `[VERIFIED]` `run_cases.py <agent_id> --brief A|B [--reps 3] [--style pieces|corrects|talkative|asks_back|in_words] [--only IDS] [--out file]`. Prints pass/fail per case, tool calls, failure reasons; median slowest agent turn (warning above 10 s).
- `[VERIFIED]` v1 sample builder (`minimal_builder.py`, removed in v2): about half of Brief A, not the same half each run. Our own run: 6/10.
- `[VERIFIED]` v3 example builder `agent_builder.py`: Claude reads the brief, writes the workflow, saves it, runs the practice customers in the foreground and fixes failures at most three times. Its self-test uses `run_cases.py --brief A|B`, i.e. the public practice cases, which do not exist for a hidden brief. Organizers report 10/10 on Brief A in one run.

## Conflicts between sources (kit wins)

| Item | Page | Kit |
|---|---|---|
| Workflows per workspace | 10 | 200 (README) |
| `agent_config` | not mentioned | omit it; platform fills defaults |

The workflow cap is unresolved; we update in place so it does not matter.

## Still open

- `[TO-CONFIRM]` Exact workflow-cap value; how failures in the hidden run for the raw-material brief are scored.
- `[TO-CONFIRM]` Whether the submitted `run_command` receives exactly one brief plus one tool file (page) or the sample builder's multi-brief form for Brief B.
- `[TO-CONFIRM]` Judge phrasing of the checks for hidden briefs (we only see practice checks).
- `[TO-CONFIRM]` Sandbox limits of `code_exec` beyond `json`, `re`, `datetime`.
- `[TO-CONFIRM]` Sandbox payload limit: another team saw "Sandbox payload too large" when code plus all call variables passed 131,072 bytes; the step then did not run, with no error in the conversation. Not in the kit. Our largest code step is ~31.5 KB and live call variables peaked at ~9.4 KB (F-066).
- `[TO-CONFIRM]` What the platform does with a tool whose hook cannot run because the sandbox is unreachable ("Failed to reach snekbox", reported by another team). Our silent loops do not depend on it (F-065).
