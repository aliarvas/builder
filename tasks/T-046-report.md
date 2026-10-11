# T-046: generic mode (the documents decide the workflow)

**Constraints kept:** no commit, no env.sh, no real model call; the tests use a fake model.

**Tests:** `python3 -m unittest`: **705 OK**, which includes:
- the leak test;
- the PROMPTS.md check, with the doc regenerated;
- the T-047 tests from claude-dev2.

## Command

```bash
python3 builder/build.py ~/Desktop/final-case/case https://<mock>.workers.dev     # full: build, validate, save, publish, self-test, export
python3 builder/build.py --print --slot final ~/Desktop/final-case/case https://<mock>    # model calls, no Freya
```

**Which path runs:**
- A case folder (or zip) followed by a URL now runs **generic mode by default**.
- `--collections` brings back the old spec renderer for a case folder.
- `--generic` forces generic mode.
- The old form (brief files + OpenAPI) is unchanged.

**Slot:** the default slot is the folder name (`case`). I recommend `--slot final`, so the export lands in `submission/final.workflow.json` and the trace in `traces/final.log`, matching the names in BRIEF.

## How it works (`builder/generic.py`)

1. **Documents:** the T-040 reader. It now also reads `.eml`, `.html` and `.xml` as text, for the mail threads.
2. **Contract** (1 call):
   - the bank's own services as OpenAPI 3, with path, method, parameters and body, and every response by HTTP status;
   - **check:** every literal path segment and every field name must be written in the documents; otherwise 1 repair round;
   - `servers[0].url` is set to the mock URL;
   - written to `traces/<slot>.openapi.json` and `traces/<slot>.contract.json`.
3. **Design** (1 call): steps, spoken rules in the call's language, extraction fields, transitions, tools and edge cases. Written to `traces/<slot>.design.json`.
4. **Render** (1 call): the Freya workflow JSON, in the kit's format.
5. **Local validation (`validate`) and repair:** up to **3 rounds**. Each round sends the exact problems and takes back **only the changed nodes** (a patch with `nodes` / `global_nodes` / `top`), so it does not regenerate the whole workflow.

   | Area | What is checked |
   |---|---|
   | Node shape | node kinds; `initial_node`; an `end_call` node with the right `terminal` |
   | Routing | transition targets exist (`__previous__` allowed); condition shapes and operators |
   | Global nodes | they have `condition` and `description`; plain nodes have neither (nor `excluded_nodes`) |
   | Node types | `tools` only on conversation nodes, `pre_actions` only on api/code nodes; a passthrough node ends with `always` |
   | Extraction | `none` is the last enum value |
   | Tools | every api tool URL is the mock URL plus a path and method of the contract |
   | Paths | every node is reachable and can reach `end_call` |
   | Code loops | loops of code steps exit on engine counters (T-035) |
   | Variables | variables used in conditions and in `{{…}}` are set somewhere (test_variables, extraction, response mapping, code write, or an engine variable) |

   Before each check, `clean` removes `agent_config` and nulls, and sets each node's name to its key. If problems remain after the last round, the version with the fewest problems ships, with a trace warning.
6. **Freya:**
   - dry-run validation; a rejection goes back to the model as a repair (at most 2 rounds);
   - `save_with_slot_check` (update in place);
   - publish;
   - the agent model `experimental-5` comes from `freya.py`, unchanged; no `agent_config`.
7. **Self-test (T-047, claude-dev2):** `generic_selftest.self_test_loop(case, workflow, save, repair, trace, model=client, chat=freya_chat, deadline=start+25 min, workflow_id=…)`.
   - `save` validates, saves and publishes.
   - `repair(problems, workflow=None)` calls `generic.repair`.
   - The workflow it returns is the live one, and that is what gets exported.
8. **Export:** `submission/<slot>.workflow.json`.
   - **The trace** records every model call, `case_document`, `contract`, `design`, each validation round, Freya validation, `self_test_summary` and `build_seconds`.

**The prompts** (`prompts.py`, `GENERIC_*`, 6 of them) are generic.
- They carry the platform rules learned live: the call's language and amounts with their currency, honesty, never asking for call variables, tool and routing rules, `none` last, a goodbye exit everywhere, `__previous__`, guarded code loops, `max_node_turns` with a target, and no null or `agent_config`.
- They contain no case content.
- The documents and both kit docs go in one cached prefix, together with the PDF attachments.

**Interface for T-047:**
- `generic.build(case, mock_url, trace, client=None) -> (workflow, contract)`
- `generic.repair(case, workflow, problems, trace, client=None, contract=None) -> workflow`
- `generic.validate(workflow, contract, mock_url) -> list[str]`

## Tests (`tests/test_t046_generic.py`, 8)

- **Validation:** a good workflow is clean. A broken one names the missing target, the `description` on a plain node, the tool path missing from the contract, and `agent_config`. An undefined variable and an unguarded loop are caught.
- **Contract check:** a path segment not written in the documents is caught.
- **Patch merge:** a patch replaces only the nodes it names.
- **Full loop with a fake model:** contract → design → render (broken) → repair_1 → clean.
  - The repair request contains the exact problems.
  - The first message has a cache mark.
- **`repair` with outside problems** (self-test failures).
- **CLI:** `--print` on a case folder runs generic mode end to end and prints the workflow.
- **T-040 test updated:** the collections CLI test now passes `--collections`.

## Risks (live)

1. **Render size and time.** A large workflow can reach ~20–40k output tokens. The client has 48000 tokens and a 600 s timeout per call. Repairs send only patches, so they are short.
   - **Rough time:** contract ~1–2 min, design ~2–3 min, render ~4–8 min, repairs ~1–2 min each.
   - **If it is too slow:** turn off the design step (render straight from the documents). That is a small change.
2. **Contract check strictness:** if the integration document writes a field differently from its examples, the check repairs once and then ships with a trace warning. It does not stop the build.
3. **Variable check:** an engine variable that my list does not know could be flagged as never set. That would cost one useless repair; it does not stop the build.
4. **The folder is still filling** (only BRIEF.md and the flow PDF so far). The reader skips the code files under `cloudflare-mock/` with a warning, and mails as `.eml`/`.html` are read as text.
5. **Not run live:** no real model call and no Freya call so far. **First step:** `--print --slot final` on the full folder, then look at `traces/final.*.json` and the validation lines.

## Update: the full case folder arrived (reader only, no model call)

Read with `read_case`: 16 documents. The only skips are `worker.js` and `wrangler.toml` under `cloudflare-mock/` (code, with a warning).

Three generic fixes in `case_folder.py`:
1. **A reference file over 20,000 characters is cut, with a trace warning.** `test-customers.json` was 707k characters (~176k tokens) and alone filled the context. The whole case is now **~165k characters (~41k tokens)**, plus ~18k tokens of kit docs, all in the cache.
2. **A meeting transcript is policy, not reference.**
   - `transcript` was removed from the reference words: meetings record decisions.
   - The speaker-label rule now counts only agent/assistant/bot/customer/caller labels.
   - Reference now means: `example-scenarios.md`, the test customers and the example response.
3. **The root BRIEF.md and README.md come first.** Before, a nested `cloudflare-mock/README.md` came before the root README.

`python3 -m unittest`: 708 OK.
