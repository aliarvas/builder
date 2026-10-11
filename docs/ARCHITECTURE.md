# Technical Architecture

**Owner:** Components, dependencies and repository boundaries  
**Read when:** Adding modules, changing data flow or deciding where code belongs

## Rule

Only the extractor interprets brief text; everything brief-specific is spec data produced at run time. The spec, renderer and offer code never import the Freya client. Only `build.py` (and the chat wrapper `freya_chat.py`, used by the self-test) talks to Freya. Builder code contains no brief value; `tests/test_multi_step.py` scans every string literal in `builder/` against the fixture specs.

## Pipeline `[VERIFIED: code, commit d5f6af1; official run version 12]`

```text
python3 builder/build.py <brief...> <openapi.json>
  load inputs, hash them into the trace                          build.py
  -> extract spec (model)                                         extract.py, llm.py, prompts.py, spoken.py
       4 parallel section calls -> code checks (incl. spoken text) -> repair (<= 2 rounds)
       -> coverage call -> one targeted re-ask -> traces/<slot>.spec.json
  -> parse + validate spec                                        spec.py
  -> tools from OpenAPI (fields, enums, baked call variables)     tools_from_openapi.py
  -> render multi-step workflow + prompt budget plan              workflow.py, offer_check.py, spoken.py
  -> trace: steps, tools per step, prompt estimates, rule placements,
            sent_agent_config / sent_nulls
  -> dry-run validate -> save (slot check) -> publish -> export   build.py, slots.py, freya.py
  -> self-test (chat, bounded)                                    selftest.py, freya_chat.py
  -> trace finish (status, end time, total duration)              run_trace.py
offline, after the run: tools/submission_check.py <trace> <export>
```

Each stage returns typed data or raises. Input, OpenAPI and spec errors exit with code 2; any other error exits 1. Both write `traces/<slot>.failed.log`.

Modes: `--print` stops before Freya and prints the workflow JSON. `--validate` runs only the dry run. `--spec <file>` uses a written spec instead of extraction, with no model call. `--single-step` is the legacy one-node agent with no spec. `--no-self-test` exists for development only. `--slot` names the workflow slot; the default is the brief file stems joined with `+`.

## Core design idea `[VERIFIED by chat tests; see UAT-FINDINGS]`

Prompts alone were unreliable: the kit's one-node baseline failed on tool discipline, attempt counting and date arithmetic (Results log in [`EVALUATION-AND-TESTING.md`](EVALUATION-AND-TESTING.md)). So the builder splits work:

- **Model (in the workflow):** understanding speech, empathy, wording.
- **Generated code steps and hooks:** date arithmetic, amount bounds, attempt counters, outcome selection, read-back text, argument baking. The code is generic; the numbers, calendars and tables are spec data embedded as JSON.
- **Graph:** one step per stage. Tools are exposed only where they may be used. Transitions route on tool results.
- **Lifecycle tool:** the closing chain records at most one successful close; a failed `close_call` is retried once. An end-of-call tool records the close when the call ends before the chain ran.

Evidence is chat results scored on the ledger only (Results log in [`EVALUATION-AND-TESTING.md`](EVALUATION-AND-TESTING.md)): PUB-03 (version 5) and PUB-01 (version 10, extracted spec) passed. F-001, F-003 and F-004 are fixed in code and still to be retested live. PUB-07 failed on version 11 on a platform rollback (F-050) and on version 12 on F-051 (fixed in code since). On version 13, PUB-07 and PUB-09 passed the ledger and PUB-02 failed on the callback year (F-055, fixed offline since). A full 13-case scored run of the current builder is still open.

## Phone agent skeleton `[VERIFIED: rendered from tests/fixtures/spec-brief-a.json, working tree after b2ebfa8 with F-063]`

`workflow.py` (`build_spec_workflow`) renders a fixed, domain-generic skeleton. Node names are framework vocabulary; every rule text, value, outcome code and calendar comes from the spec.

```text
opening (conv)            introduction (only here, F-048); who answered -> identity_check | third_party | opening_unclear -> opening_reask
identity_check (code)     already verified (a replayed turn, F-049) -> account; otherwise -> identity
third_party (conv)        no tool (F-055); extraction copies the person's day and time words -> callback_check | closing
                          (if the callback tool has no recognisable date and time fields: model-filled tool + warning)
callback_check (code)     resolves day and time against `now` and the spec calendar, checks the spec's callback
                          window; keeps a day given alone across turns -> callback_book | closing (give up) | third_party_ask
third_party_ask (conv)    twin of third_party; speaks {{callback_message}} (outside window / unclear / need the time)
callback_book (api)       silent; schedule_callback with the checked date and time -> closing
identity (conv)           verify_identity only; attempts counted from tool results; says the wait line after the
                          last answer is verified -> account | closing
account (api)             get_account runs as a pre-action (maxRetries 1); silent (a tts line here broke the turn, F-050)
offer_setup (code)        products -> per-product facts, spoken names, spoken calendar `calendar_text` (F-054)
negotiate (conv)          debt and proposal, dates only from calendar_text -> check_offer | confirm_record | closing
check_offer (code)        date/amount/business-day/next-weekday rules -> verdict, alternative -> confirm_record | closing | offer_say
offer_say (conv)          twin of negotiate; speaks {{offer_message}} (the check result, F-053), then negotiates
revise_ask (conv)         twin of negotiate; fixed line asking for the new date or amount
confirm_record (conv)     one read-back, one clear yes; no tool -> record_next | revise_ask (F-063)
record_next (code)        next accepted product not yet recorded -> record_promise | closing
record_promise (api)      silent; create_promise for that product (hook fills id, date, amount) -> confirmation_progress
confirmation_progress     per-product attempt limit; ok -> next product, failure -> retry or stop -> record_next | closing
[product notes]           F-061/F-062 per-product refusal and note loop: to be documented with that task
closing (code)            close state derived from call variables -> outcome/reason and the one closing sentence
closing_say (code, tts)   the only spoken step of the closing turn -> close_attempt -> close_record (api, close_call;
                          one retry if not ok) -> end_call
global special paths      e.g. dispute / already paid / human; a closing path is silent until closing_say
close_call_on_hangup      workflow-level tool, alwaysRunsAt end_of_call; skipped if the chain already sent close_call
```

Special paths come from `spec.special_paths` and become global nodes, limited to their source steps (`source_steps`). If a path has a tool, the engine runs it as a pre-action (`api_request`); a tool that needs a value from the conversation, such as which product, runs in a conversation step (`_model_tool_special`). The path exits on the tool result, never on the model saying it is done (T-005b). A path with `then=close` goes to `closing`; `then=return` goes back to the step it came from. A failed tool on a closing path goes to `close_special_tool_failed`.

**Who speaks when.** A path with `then=return` has three shapes:
- without a tool, it speaks its line on entry (a conversation step with tts);
- with an engine tool, a code step speaks the line on entry, **before** the tool runs. This is a known limit: the F-059 honesty problem is still open for this shape, and no current spec has it;
- with a model-filled tool, the line is said only after ok, by the prompt.

A path with `then=close` says nothing itself (F-056/F-059). Its steps are silent code and api steps, and a model-filled tool step is told to say nothing with the tool call. `closing` then builds one sentence: the path's line, then the outcome row's sentence (said once if one contains the other). The line is used only on the state that the tool's ok sets, so a transfer is never announced before it happened. Fallback lines are added before the sentence when the chosen row does not say the failure itself, either because it is not the state's own row or because its text is only the generic goodbye (an empty or instruction-style row, F-047):
- `special_tool_failed`: "I am sorry, I could not complete that request right now."
- `promise_failed` (for example when another promise was recorded and the promise row wins): "I am sorry, I could not record every promise." (F-063).

The lines are the `FIRST_LINES` table in the closing code. So the closing turn has one spoken message. This holds by construction for no-tool and engine-tool closing paths. For a closing path whose tool the model fills, it depends on the prompt rule "say nothing before or after the tool" `[TO-CONFIRM]`. Two messages in one turn made the platform end the turn at the first one, and the next message resumed before the close (F-056, F-057).

| Work | Owner |
|---|---|
| Speech, understanding, empathy, wording | phone-agent model |
| Attempt counters, date and amount checks, callback date and window, which product to record, outcome selection, read-back and closing text | code steps and hooks |
| Which tool is available when; that the closing tool always runs | workflow graph + end-of-call tool |

## Spec (the IR) `[VERIFIED: code]`

`spec.py` holds the typed, versioned spec (`spec_version` 1). Sections: `agent`, `opening`, `third_party`, `identity`, `account`, `negotiation`, `confirmation`, `offer`, `outcomes`, `special_paths`, `closing`, `global_rules`.

- Each `Rule` has `text`, `source` (the brief excerpt it came from) and an optional `enforced_by` tag. The tag is one of `offer_dates`, `business_days`, `offer_amounts`, `weekday_reading`, `invalid_offer_limit`, `identity_attempts` or `closing_outcome`.
- `parse_spec` rejects missing, mistyped or contradictory fields with a `SpecError` that names the path.
- Field names inside the spec (identity selector, product id, outcome and reason fields) must exist in the OpenAPI contract. They are checked during extraction and rendering.

## Messy inputs `[VERIFIED: code; live extraction on brief A, A+B and the raw/changed test briefs]`

**Brief (builder time), `extract.py`:**

1. Four extraction calls run in parallel (`opening_identity`, `flow`, `offer`, `outcomes`). Each gets the whole brief and the tool contract. They return a small intermediate JSON shape: routes and outcome pairs instead of state names, so no call depends on another.
2. Code validates each group, merges them and validates the merged spec. Validation covers `parse_spec`, the tool contract, brief values (dates and numbers must appear in the brief) and a dry render. Only the errors go back to the call that owns the failing section, for at most `MAX_REPAIR_ROUNDS = 2` rounds. If errors remain, `ExtractionError` is raised and the candidate is written to `traces/<slot>.spec.failed.json`.
3. Coverage: the brief is split into items. One call maps each item to a spec path or marks it not relevant. Missing items get one targeted follow-up call. An addition that would break validation is dropped and traced (`coverage_rejected`). Items still unmapped are traced (`coverage_unmapped`) and printed as a warning.
4. The model never does arithmetic. It copies counts, units and conditions; code evaluates them.

**Where a rule ends up:** (1) code that enforces it, when its `enforced_by` check is available for this spec (`enforcement_available`); (2) the prompt of the step it belongs to (`RULE_STEPS`); (3) the global `system_prompt` (global and closing rules, or shared rules moved there by the budget plan). Every rule's placement is a `rule_placement` trace line; extraction also traces `rule_tiers`.

**Tool responses (call time):** every OpenAPI tool gets a `post_process_code` hook (`tools_from_openapi.py`). It removes headers and normalizes `data`. It sets `data.ok = False` on an HTTP error, an error status, an `error` field, a missing `ok` or non-dict data. It writes a `what_to_do_next` line (failure / false fields / ok / unclear), and it never raises. The agent gets customer facts only from tools.

## Components `[VERIFIED: code]`

| Module | Role |
|---|---|
| `builder/build.py` | CLI, wires the stages, writes trace lines, dry run / save / publish (`_ensure_published_version`) / export, runs the self-test. No policy logic. |
| `builder/llm.py` | Anthropic Messages client over stdlib `urllib`; pinned model; one transport retry; prompt caching of the shared context. |
| `builder/prompts.py` | Every prompt and fixed agent line; rendered to [`PROMPTS.md`](PROMPTS.md). |
| `builder/extract.py` | Brief -> spec (parallel calls, checks, repair, coverage). The only place brief text is interpreted. |
| `builder/spec.py` | Spec dataclasses, `load_spec` / `parse_spec`, close-state vocabulary. |
| `builder/tools_from_openapi.py` | OpenAPI POST operations -> Freya `api_call` tools (enums, required, `$ref`/`allOf`, call variables baked, post-hook); `tool_contract` for extraction checks. |
| `builder/workflow.py` | Spec + tools -> workflow JSON; closing chain, hang-up tool, special paths, prompt budget plan (`RulePlan`). |
| `builder/spoken.py` | Spoken-text check (F-047): finds text that addresses the agent instead of the customer ("Thank the customer and say goodbye."). Extraction sends such fields to repair; the renderer replaces what is left with a generic line and writes a `warning: spoken_fallback …` trace line. |
| `builder/offer_check.py` | Generated Python for `offer_setup` (facts, `calendar_text`), `check_offer` (verdict and the spoken `offer_message`), the promise values hook and the spoken read-back. Reads and writes only `vars`, never raises. It resets typed variables only with values the platform accepts: enums with `none` (F-052), the float amount with the sentinel `-1.0`, which is never read as an amount (F-060). |
| `builder/callback.py` | F-055: callback extraction fields, `callback_check` code (day and time words -> date and time, window check, bounded re-asks, give-up close value), `third_party_ask` and `callback_book`. If the callback tool has no recognisable date and time body fields, it is not applied: `third_party` keeps the model-filled tool and a warning is written. |
| `builder/record_loop.py` | F-063: `record_next` code, the silent `record_promise` step (the product number comes from `promise_record_number`, read by a hook prefix), and the record values (every confirmation value that is not a revise value; `spec.py` requires at least one). |
| `builder/product_notes.py` | F-061/F-062 (per-product refusal and notes): to be documented with that task. |
| `builder/selftest.py` | Post-publish chat checks generated from the spec (see [`EVALUATION-AND-TESTING.md`](EVALUATION-AND-TESTING.md)). |
| `builder/freya.py` | The kit client, byte-identical to `build-the-builder-v2/freya.py`. |
| `builder/freya_chat.py` | Chat message / call record / end-chat calls with timeouts, reusing the kit's URL and headers. |
| `builder/slots.py` | `save_with_slot_check`: drops a stale slot whose workflow was deleted, then `freya.save_workflow` (F-005). |
| `builder/run_trace.py` | Plain-text trace; masks env secret values, `fak_…` and `sk-ant-…`; writes `total_duration_seconds`, `status`, `end_utc`. |
| `tools/submission_check.py` | Offline check of one trace + export (+ spec) against the kit's submission rules. |
| `tools/compare_spec.py` | Compares an extracted spec with a written one (development). |

## Repository shape

```text
builder/      the builder (modules above); python3 builder/build.py ...
tools/        offline helpers: submission_check.py, compare_spec.py
tests/        unittest suites; fixtures/ (specs, synthetic OpenAPI, extraction replies); briefs/ (raw-a, changed-a)
traces/       <slot>.log, <slot>.spec.json per run (print/validate/failed logs are git-ignored)
submission/   <slot>.workflow.json exports
docs/ tasks/ reviews/   design, task briefs and reports, reviews
build-the-builder-v2/   the kit (reference; not imported)
```

## Dependency rules `[VERIFIED: imports]`

- `spec.py` imports nothing from the builder. `workflow.py`, `offer_check.py`, `extract.py` and `tools_from_openapi.py` never import `freya`.
- `freya.py` stays identical to the kit; additions go in `freya_chat.py` / `slots.py`.
- Standard library only, Python 3.10+; no SDK.

## Builder model `[VERIFIED: code + live run T-006]`

- Anthropic Messages API over `urllib`. The key comes from `ANTHROPIC_API_KEY`, is read at call time and is never logged.
- `EXTRACTION_MODEL = "claude-sonnet-5-5"`, pinned in `llm.py`, and written to the trace for every call (`model_call: model=… purpose=… duration_seconds=…`).
- No temperature is sent: the pinned model rejected it ("temperature is deprecated for this model", T-006). If a 400 response names temperature, the client drops it and resends. `max_tokens` 16000, timeout 300 s, one retry on 408/429/5xx/529 or a transport error.
- Output is JSON checked by code (not a schema API); invalid output goes through the repair rounds above.

## Constraints that shape the design

- **Prompt budget** `[VERIFIED: code, T-009]`. Every conversation step is estimated as characters/4 of `system_prompt` + `task_message` + its tool descriptions (`workflow_prompt_estimates`). The target is 1,200 tokens and the hard limit 1,500. A step over the target first leaves out rules whose `enforced_by` check the code performs. Next, duplicate sentences are removed. Last, rules shared by several steps move to the global prompt. No rule is cut. Over the hard limit the build does not stop (T-009b, commit d5f6af1): the workflow ships with every rule and a `budget_exceeded_but_shipped` trace line and warning. In the official version 12 run the budget stages brought `negotiate` from ~1586 to ~1208 tokens: still over the target, but under the limit. Per-step estimates are `prompt_estimate` trace lines.
- **Time:** 30 minutes per brief including self-tests. Extraction calls run in parallel; the self-test has a 6-minute budget. The official version 12 run took 193 s in total (extraction 103.5 s, 3 self-test cases ~84 s).
- **Reproducibility:** pinned model name, spec saved per run, no hidden state needed. `save_workflow` keeps its slot map in the git-ignored `.freya-agents.json`. A fresh checkout creates one new workflow on its first run and updates it in place afterwards.
- **Send rules:** the builder never sends `agent_config` or `null`. The trace proves this with `sent_agent_config: absent` and `sent_nulls: 0`. The kit's `update_workflow` then sets the platform-filled `agent_config.llmConfig` to the kit model.
