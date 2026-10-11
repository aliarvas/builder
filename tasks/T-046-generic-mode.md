# T-046 (FINAL, critical path): generic builder mode, where the documents decide the workflow

**Owner:** claude-dev (stop T-043) · **Deadline:** a working end-to-end build by about 21:15 Istanbul. The final closes at 23:00.

## Why

The final case is NOT collections. It is a Turkish credit-card statement-debt info line:
- find the card;
- read the debt in TRY, USD, EUR and GBP, and the due date;
- move the statement cut-off week;
- e-mail the statement;
- transfer to a human for payment or a person.

The services are the bank's own. They are described in an integration document in the folder; they are NOT our seven collections tools. Call variables: `customerNumber` (8 digits, never asked) and `now` (Istanbul time).

The case is in `~/Desktop/final-case/case/`; files are still arriving. Do not copy anything from it into the code (rule): the mode must be generic.

Our spec-based renderer only knows collections, so it cannot express this.

## What to build: `builder/generic.py`, used by `build.py`

**When generic mode runs.** In the case-folder form (`{case_folder} {mock_url}`), and with the `--generic` flag. The old collections form stays unchanged.

1. **Documents.** Reuse T-040's `case_folder` reader: md, docx, xlsx, PDF attachments, roles and labels.
2. **Tool contract.** One model call: from the documents, derive the bank's services. For each service:
   - the path, the method, the request fields (types, enums) and the response fields, including the HTTP status codes;
   - an OpenAPI 3 JSON with `servers[0].url = mock_url`.

   Check that every path and field name appears verbatim in the documents. Write it to the trace.
3. **Design.** One model call:
   - **Inputs:** the documents (the flow drawing PDF is attached) and the kit's `docs/workflow-format.md` and `docs/tools-and-code.md` (the platform's own format, not case content).
   - **Output:** a JSON design. It lists the steps (conversation, api_request, code, end_call), each step's purpose, its spoken rules (in the call's language, which the documents give), its variables, its transitions, and the tools with their mappings.
   - **Rules the design must follow:** answers to every branch of the flow; the honesty rules; never claim an action without a tool success.
4. **Render.** The model writes the Freya workflow JSON from the design, using the exact format of the kit docs. Then:
   - **Local validation:** node kinds, transitions point to real nodes, variables used are defined, tools match the contract, globals have `condition` and `description`, and no `description` or `condition` on plain nodes.
   - **Repair:** up to 3 rounds; pass the model the exact errors.
5. **Save.** Through `builder/freya.py`, the same as now:
   - update in place via `slots.py`;
   - phone-agent model `experimental-5`;
   - omit `agent_config`;
   - publish;
   - a Freya validation error goes back to the model for a repair round.
6. **Export** to `submission/<slot>.workflow.json`, with the trace (every model call, design, contract, validation results).
7. **Time budget:** the whole build stays under 20 minutes. Use `llm.py` (claude-sonnet-5-5, 48000 tokens) and the prompt cache for the documents.

## Notes

- The workflow's tools must call `mock_url` paths exactly as in the contract.
- Speak the documents' language (Turkish). Read amounts with their currency.
- Reuse what we learned. These are generic patterns, and some belong in the design prompt as platform rules:
  - the goodbye exit at every conversation step;
  - code cycles guarded by engine counters;
  - routing order (own transitions first, then globals);
  - the extraction enum with `none` last;
  - the `__previous__` return.

## Tests

- Offline: a synthetic folder with a fake model (no network). The design → workflow → validate → repair loop, and local validation catching broken references.
- `python3 -m unittest` green; the leak test applies to the new prompts too (no case values).

## Constraints

- No commit and no env.sh. The CTO runs the live build; you may run `--print` with a fake model only.
- claude-dev2 does the self-test loop (T-047) on top of your entry point. Agree an interface: `generic.build(inputs, mock_url, trace) -> workflow, contract`.
- Report: `tasks/T-046-report.md`.
