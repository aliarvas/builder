# F-056 / F-059 review — one message in the closing turn, transfer line only after the tool

**Reviewer:** claude-reviewer · **Scope:** `workflow.py` (`_special_nodes.action`, `_closing_code`, `FIRST_LINES`, `join_lines`), `SPECIAL_TOOL_FAILED_SAY`, `tests/test_closing_speech.py`, the F-056..F-060 entries in `docs/UAT-FINDINGS.md`. claude-dev's F-060 (`offer_check.py`) not reviewed.
**Method:** offline. I rendered the four specs (A, A+B, the version 11 extraction, the tagged A+B extraction), walked the graph from every special-path entry to `end_call` or the next customer wait and counted speaking steps, ran the generated `closing` code with synthetic results (ok, failed, spec row present), scanned for `tts` on non-conversation steps, and read the code. `python3 -m unittest`: 335 OK. No Freya, no model, no edits.

## Decision: **düzeltme gerekli** (one MEDIUM shape the report calls "not present", but it is in the tagged A+B extraction; the rest is correct)

## Finding

### 1. MEDIUM — a closing path whose tool needs the model still speaks twice, and says the same line twice (`workflow.py` `_model_tool_special`, then `closing_say`)

The report (open note 2) says no fixture or extracted spec has a closing path with a model-filled tool. `tests/fixtures/extract/brief-ab-extracted-tagged.json` has one: `hardship_declined` (`then = close`, tool `add_note`, global entries `special_hardship_declined_at_negotiate / _offer_say / _revise_ask / _confirm_record` and the conversation step `special_hardship_declined`).
- The conversation step's prompt says: "Only if the tool result says ok true, say exactly: Thank you for letting me know." The step exits to `closing` on the tool result, **in the same turn**.
- `closing` now also prepends the path's own line (`FIRST_LINES` has `("special:hardship_declined", "Thank you for letting me know.")`).
- I ran the closing code with `special_result_hardship_declined = true`: sentence = "Thank you for letting me know. Thank you for your time. Goodbye." So the customer hears the model's line, and then the same line again inside the closing message, in the same turn. That is the F-056 shape again (two messages, the platform ends the turn at the first, the next message resumes before the close), and an identical line twice.
Hidden briefs with a note-taking close path (a very natural shape: "if the customer declines, add a note and end the call") will land here.
**Fix:** for `then = close` model-tool paths, the conversation step must say nothing after ok (prompt: "Do not say anything after the tool; the closing step speaks"), or be given `on_enter: silent` plus the same wording rule, exactly as the engine-tool closing paths are. `closing_say` already says the line only on the ok state and says the plain failure line otherwise. Add a structural test the existing one cannot make: for every closing special entry in every fixture, the number of speaking steps (a conversation step with an llm/tts entry, or a tts code step) on the way to `end_call` is at most one **per customer turn**; the current test only looks for spoken steps reached by passthrough steps, and the conversation step is not passthrough, so it passes.

## What I verified (no change needed)

- **One message per closing turn on the other shapes.** Walking from each closing entry to `end_call`: no-tool paths (`already_paid`, `dispute`, `hardship_declined` without a tool): 1 speaking step (`closing_say`); engine-tool paths (`restructuring`, `human`, `human_request`, `hardship_support`): 1 (`closing_say`). Paths with an `ask` (human, hardship support): the ask (tts) is one message in one turn, and `closing_say` comes in the **next** turn after the customer says proceed; the walk shows 2 only because it did not stop at the customer's reply.
- **Return paths (`__previous__`) were not broken (F-053 dead-air rule).** Those paths still speak their line on entry or through the model, and the `_done` hops return to `negotiate`, `offer_say`, `revise_ask` or `confirm_record`, which all speak on entry. The ask paths' "stay" exit returns to a speaking source too. No silent return was introduced.
- **No pretended success.** The transfer line appears only on the state `special:<id>`, which is derived from the tool result being true. A failed or blanked tool gives `special_tool_failed`: closing says "I am sorry, I could not complete that request right now." and the closing sentence. A spec row for that state replaces the builder line (condition `chosen[0] != state or state != 'special_tool_failed'` checked: with a row only the row sentence; without a row the failure line plus the default sentence). I ran ok/failed with synthetic results: ok → "…Thank you for your time. Goodbye."; failed → default close without the transfer line.
- **Duplicates collapse:** `join_lines` says a line once when it already contains, or is contained in, the closing sentence (the PUB-09 shape). The line of a no-tool path stays when a recorded promise wins the outcome row. Other states get no extra line.
- **F-050:** no `tts` on any `api_request` step in the four specs; the only non-conversation `tts` step is `closing_say` (a code step, the form seen working live). The new special entries are silent code steps and silent api steps.
- **No brief value in code or prompts.** The lines in `FIRST_LINES` come from the spec (`path.say.text`, after the spoken-text fallback), the failure line is a generic prompt constant, and the leak test passes. One observation, not a defect of this task: in the tagged A+B extraction every close path's line has become the generic fallback "Thank you for letting me know." (the extracted text was an instruction), so `restructuring` and `human_request` also say that instead of a transfer sentence. The version 11 extraction in the real run keeps real lines; the next extraction should be checked for it.
- **UAT entries F-056..F-060** are in the existing format, newest first; statuses ("fixed offline, retest pending") and the [TO-CONFIRM, platform] labels on F-057/F-058 are right.
- The report's open notes 1 (engine-tool return paths still speak before the tool; none in the fixtures) and 3 (silent global code entry is not yet live-proven) are accurate and fairly labelled. The `ARCHITECTURE.md:66` sentence ("Each path speaks its fixed line") needs the docs sync, as the report says.

## Live checks

PUB-09 (restructuring, one message, the transfer line only after ok) and one forced transfer failure (the plain failure line, no transfer claim). Add a note-taking close path run if the tagged-style shape appears in a real extraction.


---

## Re-review (Fix: model-tool closing paths say nothing with the tool)

**Method:** offline. I rendered the tagged and untagged A+B extractions and the A+B fixture, listed every step of each closing path with its entry type, tools and rule, ran the generated `closing` code with the tool result true and false, read the new template and the structural test's walk, and checked the kit's entry rule. `python3 -m unittest`: 339 OK. No Freya, no model, no edits.

### Decision: **merge edilebilir**, with one residual risk that only the live run can settle

- **Finding 1 fixed.** `special_hardship_declined` (`then = close`, `add_note`, model-filled) now uses `SPECIAL_CLOSE_TOOL_TASK_TEMPLATE`: "Call the available tool once… If a field is not known yet, ask only for it and call no tool. When you call the tool, say nothing before or after it: the next step speaks to the customer. Never say that anything was recorded or completed." The path's line is no longer in that prompt. With the result true the closing code gives "Thank you for letting me know. Thank you for your time. Goodbye." (the line once, spoken by `closing_say`); with the result false it gives the plain default close without the path line. Both A+B extractions have this shape and both are covered. `then = return` paths keep the old template (the line only after ok), which is right: nothing else speaks there.
- **The `llm` entry stays, and the reasoning holds.** The kit's entry table says a `silent` entry on a non-passthrough step waits for the user (`workflow-format.md` line 161), so a silent step would call the tool only after the next customer message: dead air. The developer's two live observations (a route on the tool result comes before the step's own text) support using the same-turn route. The `ask` variants (`_go` steps) and the entry code steps (`special_..._at_<source>`, silent code steps) are unchanged and consistent.
- **The structural test is sound.** It walks from every global special entry through the special-path steps and the closing chain to `end_call`, counts the speaking steps per customer turn (a tts entry, or a conversation entry; a tool-bearing conversation counts as speaking in its tool turn unless its task carries the "say nothing" rule), requires at least one entry per fixture that reaches `end_call`, and covers three fixtures plus three extracted specs. The second test checks the prompt has the rule, does not contain the line, and the closing sentence contains the line exactly once. The developer reports 9 subtests failing without the prompt change; the earlier shape was exactly what my first review found.

### Residual risk (not a blocker)

The "say nothing" rule is a prompt instruction. If the model writes words before the tool call, the customer hears two messages again (the model's words, then `closing_say`), and the turn can end at the first. Nothing in the render can prevent that, and the report labels it `[TO-CONFIRM]` live. Keep the live check on a note-taking close path (the tagged-style shape): one message in the closing turn, the line said once, and a forced tool failure giving only the plain failure line. If it fails live, the stronger fix is to take the model out of that tool's call (bake the note text from the spec in a code step, as the engine-tool paths do) rather than add more prompt words.

UAT: F-056 "fixed offline, retest pending" stays correct.
