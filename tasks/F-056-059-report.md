# F-056 / F-059 report: one spoken message in the closing turn; transfer line only after the tool

**Owner:** claude (second developer) · **Findings:** `docs/UAT-FINDINGS.md` F-056 and F-059 (from `tasks/LIVE-AUDIT-report.md`, PUB-09 v13).
**Not done:** no Freya request, no commit, no env.sh. F-060 (`offer_check.py`) was not touched; it belongs to claude-dev.

## 1. UAT findings

F-056, F-057, F-058, F-059 and F-060 were added to `docs/UAT-FINDINGS.md` in the existing format, above F-055 with the newest first.
- **F-057 and F-058** are marked [TO-CONFIRM, platform].
- **F-060** is open, with owner "offer check", and marked [HYPOTHESIS].
- **F-056 and F-059** are "fixed offline (not committed), retest pending (PUB-09)".

## 2. F-056: exactly one spoken message in the closing turn

The old shape of a closing special path:

```
special step (spoke the path line) → [api step] → closing → closing_say (spoke the closing sentence)
```

That is two messages in one turn. The platform ends the turn at the first one, so the next message resumes before the close. In PUB-09 the two lines were also identical.

The new shape:

```
special step (silent) → [silent api step] → closing → closing_say (one message)
```

`closing` now builds the closing sentence as **path line + closing sentence**:
- If one already contains the other, it is said only once. In PUB-09 the result is "I will connect you with a colleague who can help you with this. Thank you for your time. Goodbye.", said once.
- The path line is added only when the derived state is that path's own state (`special:<id>`). For a tool path, that state is set only when the tool returned ok.
- When a recorded promise wins the outcome row (`wins_over_promise` false), the line of a path without a tool is still said, before the promise sentence. The old special step said it in that case too.
- F-050 still holds: no tts on any api step. All the new steps are code steps or silent steps. `closing_say` (a code step with tts after an api step) is the form that already worked live in PUB-09.

## 3. F-059: transfer line only after the tool says ok

- **Before the tool:** nothing is said. The customer's turn has a single message, so a neutral line is not needed.
- **Tool ok:** `closing_say` says the line, for example "I will connect you…" or, for hardship, "I am sorry to hear that. I will connect you with our customer support team now. …".
- **Tool failed:** the state is `special_tool_failed`, and the path line is never said. The close says plainly "I am sorry, I could not complete that request right now." (new prompt `SPECIAL_TOOL_FAILED_SAY`), then the closing sentence. If the spec has its own outcome row for `special_tool_failed`, only that row's sentence is said.
- **Brief A failure close** (from the stored spec): "I am sorry, I could not complete that request right now. Thank you for your time. Goodbye."

## Changes

| File | Change |
|---|---|
| `builder/workflow.py` | `_special_nodes.action`: closing paths with no tool and with an engine tool are silent code steps. The unused `_said` marker was replaced by `special_result_<id>_started`. Return paths are unchanged. `_closing_code`: new `FIRST_LINES` table (path lines and the failure line), `join_lines`, and the rule described above. |
| `builder/prompts.py`, `docs/PROMPTS.md` | New `SPECIAL_TOOL_FAILED_SAY`; the doc was regenerated. |
| `docs/UAT-FINDINGS.md` | F-056 to F-060. |
| `tests/test_closing_speech.py` (new, 8 tests) | See below. |
| `tests/test_multi_step.py` | `test_special_path_shapes_follow_the_tool`: the closing special steps are now expected to be silent (only this one test was changed). |
| `tests/test_spoken_text.py` | The `spoken_texts` helper reads the `TABLE` and `FIRST_LINES` blocks, so the path lines are still checked by the F-047 instruction detector. |

The new tests run on all three fixtures:
- A structural walk: no spoken step reaches `closing` through passthrough steps only (`closing_say` is the only exception).
- Closing special steps and their api steps are silent.
- Tool ok: the line is said exactly once, at the start of the closing sentence.
- Tool failed: the line is never said, and the sentence starts with the plain failure line.
- A spec row for `special_tool_failed` replaces the builder line.
- An identical line and closing sentence, or a line contained in the closing sentence, is said once (the PUB-09 shape).
- The line of a path without a tool is kept when a recorded promise wins.
- Other states get no special line.

On the code before this change, 20 subtests of the new file fail; on the new code all pass. I checked this by running them against the HEAD `workflow.py`/`prompts.py` in a scratch copy.

## Results

- `python3 -m unittest tests.test_closing_speech`: 8/8 OK.
- Full suite `python3 -m unittest discover -s tests`: **335/335 OK**. This includes claude-dev's current uncommitted F-060 tests.
- `git diff --check`: clean.
- Replay with `traces/brief-a.spec.json` and the current code:
  - Restructuring ok → `transferred/restructuring`, line said once.
  - Restructuring failed → plain failure line, the transfer line is not said.
  - Hardship ok → sympathy plus the transfer sentence in one message.
  - Already paid → one sentence.
  - The restructuring and already-paid global steps are `silent`.

## Open notes

1. **Return paths with an engine tool** (for example an `add_note` path that returns) still speak their line before the tool. I left them out on purpose, because putting the line after the tool needs one more step before `__previous__`, and that return hop has no live evidence. They are not a closing turn, so they are outside F-056. The honesty risk of F-059 applies to them too. No Brief A path has this shape.
2. **Closing path whose tool needs the model** (`_model_tool_special` with `then=close`): the prompt says the line after ok, and `closing_say` now also says it. That would be a duplicate. No current fixture or extracted spec has this shape. If one appears, give the prompt "say nothing", like the engine-tool paths.
3. **Live form [TO-CONFIRM]:** a silent global code step as the entry of a special path. The `_model_tool_special` entries use the same form, but have not run live yet. Retest PUB-09 (restructuring) and one transfer failure if possible.
4. **Failure outcome:** a failed transfer closes with the default row (Brief A: `no_promise/refused`), as before. The F-059 change only fixes what is said.
5. **Docs:** `docs/ARCHITECTURE.md:66` says "Each path speaks its fixed line". It should now say "a closing path's line is said by `closing_say` after the tool". This is for the next docs sync (not one of my files in this task).
6. F-057 and F-058 are still open on the platform side. F-056 removes the PUB-09 trigger of F-057.

## Fix (review `reviews/F-056-059-review.md`, finding 1)

**Finding.** A closing path whose tool the model fills still spoke twice in the closing turn. The fixture is the tagged A+B extraction: `hardship_declined`, `then = close`, `add_note`. The model's prompt told it to say the path's line after ok, and then `closing_say` said the same line again. My open note 2 was wrong: this shape is in `tests/fixtures/extract/brief-ab-extracted-tagged.json` and in `brief-ab-extracted.json`.

**Change.**
- New prompt `SPECIAL_CLOSE_TOOL_TASK_TEMPLATE` (`builder/prompts.py`, docs regenerated). It says:
  - "Call the available tool once. Fill only the fields it asks for, from this call. If a field is not known yet, ask only for it and call no tool."
  - "When you call the tool, say nothing before or after it: the next step speaks to the customer. Never say that anything was recorded or completed."
  - It does not contain the path's line.
- `workflow.py`: the new helper `_model_tool_task(path)` picks this template for `then = close`, and the old one (line after ok) for `then = return`. It is used in both places where the model fills a special path's tool: `_model_tool_special`, and the `_go` step of a path that has an ask.
- `closing_say` then says the line once, after ok, as for the engine-tool paths. On failure, the plain failure line is said and the path line never is (unchanged).

**Why the step keeps its `llm` entry (not `silent`).** The kit (`docs/workflow-format.md`, "Entry behaviour") says a `silent` entry makes a non-passthrough step wait for the user. The model would then call the tool only after the next customer message, which leaves dead air. Live evidence that a route on the tool result comes before the step's own text:
- PUB-01 v10, identity turn "4471": `verify_identity` → route to `account`, no identity text.
- PUB-07 v13, confirm turn: `create_promise` → closing chain, no `confirm_record` text.

The remaining risk is the model writing words before it calls the tool. This is a prompt rule only: **[TO-CONFIRM] live** with a note-taking close path.

**Structural test** (`tests/test_closing_speech.py`, as asked).
- `test_at_most_one_spoken_step_per_customer_turn_from_a_closing_entry` walks from every global special entry to `end_call`. It covers the 3 fixtures plus 3 extracted specs (v11, A+B, tagged A+B).
- The walk stays inside the special-path steps and the closing chain, and counts the speaking steps per customer turn:
  - a tts entry, or a conversation with an `llm` or default entry;
  - a conversation step either speaks and waits (a new turn after it), or, if it has tools, routes on the tool result in the same turn. It counts as silent in that turn only if its task carries the "say nothing" rule.
- Limit: at most 1 per turn. Each fixture must have at least one entry that reaches `end_call`.
- `test_model_filled_closing_tool_step_says_nothing_with_the_tool` (tagged A+B): the task carries the rule and not the line, and the closing sentence says the line exactly once.
- Without the prompt change (checked in a scratch copy), 9 subtests fail. Every `special_hardship_declined_at_*` entry in both A+B extractions reaches 2 spoken steps in one turn.

**Results.** `tests.test_closing_speech` 10/10. Full suite **339/339 OK**; this includes claude-dev's uncommitted F-060 work, which I did not touch. `git diff --check` clean. No Freya request, no commit, no env.sh.

**Still open.**
- Return paths (`then = return`) keep their old behaviour, as in open note 1.
- The reviewer's observation is not part of this task: in the tagged extraction every close path line became the generic fallback ("Thank you for letting me know."). Check the next real extraction for it.
