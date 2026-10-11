# DOCS-sync-2 review

**Reviewer:** claude-reviewer · **Scope:** `git diff` of `docs/ARCHITECTURE.md`, `docs/FREYA-INTEGRATION.md`, `docs/EVALUATION-AND-TESTING.md`; `tasks/DOCS-sync-2-report.md`. The F-061/062 placeholders (`[product notes]`, `product_notes.py`, `test_product_notes.py`) are left out on purpose.
**Method:** offline. I checked each new claim against the working tree: the rendered graph (steps, entries, targets, tts placement), the generated closing code (failure lines on five specs), the record tool's pre-hook, `callback.py`, `spec.py`, the retry settings, `tasks/LIVE-AUDIT-report.md` (the version 13 row), `docs/UAT-FINDINGS.md` (labels and statuses) and `STARTER-KIT-FACTS.md`. `python3 -m unittest`: 373 OK. No Freya, no model, no edits.

## Decision: **düzeltme gerekli** (small): mostly accurate, but one table is broken, two statements are stale or too absolute, and three claims need a qualifier or a `[TO-CONFIRM]`

## What matches the code (checked)

- **Skeleton block.** Every step and arrow I rendered from `spec-brief-a.json` is in the block: `callback_check` → `callback_book | closing | third_party_ask`; `check_offer` → `confirm_record | closing | offer_say`; `offer_say` / `revise_ask` as twins of `negotiate`; `confirm_record` (no tool) → `record_next | revise_ask`; `record_next` → `record_promise | closing`; `record_promise` silent api; `confirmation_progress`; `closing_say` the only tts code step; `close_attempt` → `close_record` → `end_call`.
- **Failure lines.** `special_tool_failed` and `promise_failed` fallbacks and the generic-goodbye rule match `_closing_code` (I ran the closing code on five specs: a spoken row is said alone; an instruction-style row gets "I am sorry, I could not record every promise." / "…could not complete that request right now." first).
- **Record loop.** The hook prefix writes `promise_record_number` into the body before the values hook (I executed the hook with eight inputs); `spec.py` rejects a confirmation with no value outside `revise_values`; `maxRetries 0` on `callback_book` and `record_promise`; the loop stops at the first exhausted product; `callback_failed` rule. The `offer_check.py` row (sentinel `-1.0`, enums reset with `none`) matches F-052/F-060.
- **Version 13 row** matches `LIVE-AUDIT` (PUB-07 ledger pass with judge risk, PUB-02 fail with the wrong callback year, PUB-09 ledger pass with the doubled line and a second `close_call`), including the false-positive note on `ledger.ok: true`.
- **Open live checks `[TO-CONFIRM]`** cover the right forms (callback in two messages, `offer_say`, the closing special path with its silent global entry and a forced transfer failure, a silent model-filled tool step, routing on the extracted yes, the long record chain, F-057/F-058). F-058 carries its label.
- Nothing contradicts `STARTER-KIT-FACTS.md` or the kit.

## Findings

### 1. MEDIUM — the version 13 row is detached from the results table (`EVALUATION-AND-TESTING.md`)

A blank line sits between the version 12 row and the new row, so the new row renders as plain text, not as a table row. Remove the blank line (the `ledger.ok` note can follow after the table).

### 2. MEDIUM — "A path with `then=return` speaks its fixed line on entry" is true only for some paths (`ARCHITECTURE.md`, "Who speaks when")

Three shapes exist in the code: a path without a tool speaks the line on entry (a conversation step with tts); a path with an engine tool speaks it on entry **before** the tool runs (a code step with tts; `_special_nodes`, `path.then != "close"`), which is exactly the F-059 honesty problem still open for return paths (the F-056/059 report calls it open note 1; no current spec has the shape); a path with a model-filled tool says the line only after ok, from the prompt. Say this in the paragraph, and mark the engine-tool return shape as a known limit. As written, a reader will believe F-059 applies to every path.

### 3. MEDIUM — "exactly one spoken message" is stated as fact, but one shape depends on a prompt rule (`ARCHITECTURE.md`)

"The closing turn has exactly one spoken message" holds by construction for no-tool and engine-tool closing paths (my walk: one speaking step per customer turn). For a closing path whose tool the model fills, it holds only if the model obeys "say nothing before or after the tool" (F-056 re-review: residual risk). The live-check list has it, but the paragraph should say "by construction, except a model-filled closing tool, which is a prompt rule `[TO-CONFIRM]`".

### 4. LOW-MEDIUM — stale statements next to the new text

- `ARCHITECTURE.md` line 42 and the version 12 row in `EVALUATION-AND-TESTING.md` still say "F-051 (open)" and "Evidence is two chat results only". The code fixed F-051 (commits 657e6a6 and 12d9226, F-052), PUB-07 on version 13 passed the ledger, and there are now three more chat runs in the log. `UAT-FINDINGS.md` still shows F-051 as `open`; update it to "fixed offline (committed), retest pending" and edit both doc lines (the report left them on purpose; they now contradict the new version 13 row).
- Test count: the doc says 370; the suite now runs 373 (re-count at commit time; the doc already says so).

### 5. LOW — `FREYA-INTEGRATION.md`: where `tts` appears

The new list says `tts` appears on conversation entries and on the code step `closing_say`. The code can also put `tts` on the **code** entry of a returning engine-tool path (the case in finding 2). Add "(or the code entry of a returning engine-tool path; none in the current specs)". The claim "no `api_request` step speaks" is correct (I scanned four specs: the only non-conversation tts step is `closing_say`).

### 6. LOW — the F-057 mechanism is written as fact (`FREYA-INTEGRATION.md`, platform behaviour)

"…resumed as a branch…, the close was forgotten, the agent spoke again, and the end-of-call tool sent a second `close_call`" mixes the observed events (verified in the trace) with the cause. `UAT-FINDINGS.md` labels the root cause `[TO-CONFIRM, platform]`. Keep the observed sequence as verified and attach the label to "why the state was lost".

### 7. LOW — `third_party` "no tool" omits the fallback

The skeleton says `third_party` has no tool (F-055). If the callback tool has no recognisable date and time body fields, the builder keeps the model-filled tool and writes a warning (`callback_nodes` returns None). One clause in the skeleton or the `callback.py` row is enough.

## Short summary for the CTO

Fix 1 (table) and the qualifiers in 2 and 3 first; 4 to 7 are one-line edits. The code claims I could test (graph, closing lines, hook, retries, validation, the version 13 row) are correct.


---

## Re-review (Fix 1–7)

**Method:** offline; read the new diff of the three docs, checked the table lines and the F-051 status, the two commit ids, and re-ran the suite (373 OK). `git diff --check` on `docs/` is clean. No Freya, no model, no edits.

### Decision: **merge edilebilir** (one LOW qualifier)

1. **Table fixed.** Rows for version 12 and version 13 are now consecutive (lines 122 and 123); the `ledger.ok` note follows the table.
2. **Return-path shapes fixed.** "Who speaks when" lists the three shapes (no tool: spoken on entry; engine tool: a code step speaks before the tool, marked as a known limit with F-059 still open and no current spec having it; model-filled tool: said after ok by the prompt), matching `_special_nodes`.
3. **"One spoken message" qualified** in ARCHITECTURE: by construction for no-tool and engine-tool closing paths, a prompt rule `[TO-CONFIRM]` for a model-filled closing tool. The shorter bullet in `FREYA-INTEGRATION.md` ("the closing turn has one spoken message") has no qualifier; add "(see ARCHITECTURE, Who speaks when)" or the same clause. LOW.
4. **Stale lines fixed.** The "Evidence" paragraph now lists versions 5/10/11/12/13 and says F-051 was fixed in code since and PUB-07 and PUB-09 passed the ledger on version 13; the version 12 row no longer says "(open)"; `UAT-FINDINGS.md` F-051 reads "fixed offline (657e6a6, F-052 follow-up 12d9226)", and both commits exist (`git log`). Test count 373 matches.
5. **tts list fixed.** The list now includes the code entry of a returning engine-tool path (none in the current specs) and names the tool-less return path; "no `api_request` step speaks" stays true.
6. **F-057 fixed.** The observed sequence is listed as observed; why the state is lost, and whether the judge's simulation can send a message after the goodbye, carry `[TO-CONFIRM, platform]`, consistent with the UAT label.
7. **`third_party` fallback fixed** in the skeleton and the `callback.py` row.

The product-notes placeholders stay as agreed (F-061/062 is now implemented: document it in the next sync).
