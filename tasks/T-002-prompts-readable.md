# T-002 — Prompts in one module, mirrored to a readable Markdown file

**Owner:** codex-dev · **Reviewer:** claude-reviewer · **Approver:** CTO

## Goal

Every prompt text the builder uses lives in code, in one place. The user (not a Python developer) can read all of them in `docs/PROMPTS.md`. The Markdown file is generated from the code and a test fails if it is out of date, so the two never drift apart.

## Scope

1. **`builder/prompts.py`**: the single home of every prompt string.
   - Move the phone agent's `system_prompt` and the `task_message` template out of `builder/workflow.py` into named constants or small functions here. Behaviour and output must stay identical (same rendered workflow for the same inputs).
   - Each prompt has: a constant name, a one-line purpose, who receives it (`phone agent` or `builder model`), and the text. Runtime parts (brief text, tool list, etc.) are shown as clear placeholders such as `{brief_text}`, filled by a render function.
   - Future prompts (per-step prompts, builder-LLM prompts) must be added here, not inline elsewhere. Add a one-line comment at the top of the module saying so.
2. **Generator**: `python3 -m builder.prompts` (or `builder/prompts.py --write-doc`) writes `docs/PROMPTS.md`:
   - Header: "Generated from `builder/prompts.py`. Do not edit by hand; edit the code and regenerate."
   - One section per prompt: name, purpose, receiver, where it is used (file and node), then the text in a fenced block with placeholders visible.
   - Deterministic output (stable order, no timestamps), so the test can compare it.
3. **Test** (`tests/`, stdlib `unittest`, offline): generating the doc gives exactly the committed `docs/PROMPTS.md`. Failure message tells how to regenerate.
4. **AGENTS.md reading map**: one line linking `docs/PROMPTS.md` ("All prompts, generated from `builder/prompts.py`"). No other doc changes.

## Constraints

- Python 3.10+, standard library only.
- No brief values in prompts (AGENTS.md priority 1). Placeholders only.
- No network, no Freya save, no simulation. Do not commit.
- Keep `python3 -m unittest` green; the existing vertical-slice tests must pass unchanged.

## Done when

- `python3 -m unittest` passes.
- `docs/PROMPTS.md` exists and lists the phone agent's system prompt and task message.
- `--print` output for Brief A is byte-identical to before the change.
- Short report: files changed, how to regenerate the doc.
