# T-052: generic:render hit the 48000 output limit

**Constraints and tests:** no commit, no env.sh, no Freya, no model call. `python3 -m unittest`: **719 OK** (7 new tests in `tests/test_t046_generic.py`, class `T052Tests`).

**Live failure (`traces/final.failed.log`, 21:15–21:24):**
- contract: 54 s, 9.9k output tokens;
- design: 146 s, **20.9k** tokens, 43 steps (the prompt asked for ~6k);
- render: 372 s, cut at **48000** output tokens. Build stopped after 572 s.
- Streaming worked: there was no timeout this time.

## Changes

1. **Continuation (`builder/llm.py`):** when `stop_reason=max_tokens`, `complete()` continues the reply at most **2** times (`MAX_CONTINUATIONS`) and joins the parts into one `LLMResult` (tokens and time summed).
   - The continuation sends the text so far as an **assistant prefill**, trailing whitespace trimmed because the API refuses it. That whitespace is put back unless the continuation starts with its own.
   - **If the model rejects a prefill (HTTP 400):** it switches once to the text as an assistant turn plus a user note ("continue exactly where you stopped…"), and a repeated tail (20+ characters) is dropped. This is written to the trace as a warning.
   - Each part is logged as `<purpose>_continue_N`.
   - Still cut after 2 continuations: `LLMError`, as before.
2. **Limits:** `complete(..., max_tokens=, continuations=)` per call.
   - **render:** `max_tokens=64000` (`RENDER_MAX_TOKENS`) plus continuations. That is up to about 192k output tokens.
   - **If the model refuses 64000 (a 400 that mentions max_tokens):** it falls back to 48000 once; the continuations make up the rest.
   - **design:** `max_tokens=8000`, **no continuation** (`DESIGN_MAX_TOKENS`).
     - If it is cut, the model is asked once for a much shorter design (about 5000 tokens).
     - If it is cut again, the design is skipped and the render works from the documents (same as `--no-design`), with a trace warning.
   - Other calls (contract, repairs) keep 48000 plus continuations.
3. **Prompts (`builder/prompts.py`, `docs/PROMPTS.md` regenerated):**
   - **Design:** under 6000 tokens; over 8000 is cut and thrown away. Short phrases. Rules that hold in many steps are written once. Required sentences once. No copied text. Steps that differ only in wording are merged.
   - **Render:** rules that hold in every step (tone, honesty, language, privacy, amounts and dates) go **once in the global `system_prompt`**. Each task_message holds only what is particular to its step: short instructions plus the exact required sentences. No copying of design or document wording. No comments, unused keys, or empty lists.

## Time estimate (about 195 tokens/s)

| Step | Estimate |
|---|---|
| contract | ~1 min |
| design | ≤ 8k tokens, ~40 s |
| render | ~25–40k tokens, ~2.5–3.5 min; if it is cut, each continuation adds ~3–5 min |

The build should leave enough of the 30 minutes for repairs and self-tests.

## Command

```bash
python3 builder/build.py --slot final ~/Desktop/final-case/case https://freya-final-mock.cf-smoke.workers.dev
```

## Risks

- **Prefill support:** I could not check whether Sonnet 5.5 accepts an assistant prefill without a model call. A rejection falls back automatically.
- **A cut in the middle of the JSON:** the continuation joins the raw text. If the joined text is not valid JSON, the existing `render_retry` asks once more.

## Update after the 21:30 build (status ok, 1389 s)

**What the trace showed:**
- The fallback worked: the prefill was **rejected** (HTTP 400), so the run switched to the user note.
- The render took 480 + 441 + 69 s, for **141k** output tokens. Its real content was only about **25k** tokens; the rest was a run of blank characters.
- **Evidence:** the input tokens of `continue_1` show that the first 64000-token part held only ~1k tokens once trimmed.
- The design was cut at 8000 tokens twice, most likely for the same reason. It then fell back to rendering from the documents.

**Fix:**
- `_read_stream` stops reading after **2000 blank characters in a row** (stop reason `whitespace_run`).
  - If the text so far is one whole JSON value, the reply counts as finished.
  - Otherwise it is continued like a reply cut at the output limit.
- `GENERIC_SYSTEM` now asks for compact JSON, with no indentation and no blank lines.
- 2 new tests.

**Expected effect:** the render takes about 2–3 minutes instead of about 16, and the design fits in 8000 tokens.

**Self-test, 8 of 8 errors:** `POST /api/v2/chat/message -> 504` on the first turn, after 28–43 s.
- The opening runs several silent steps in one turn: cards.list → code → balance → email → code. The kit notes that a long turn can return 504.
- Part of it was probably the pre_action body problem (T-053): the calls did not start and the turn went to end_fail.
- After T-053, a single chat turn is needed to check this (Freya approval).
