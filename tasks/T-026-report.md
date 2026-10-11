# T-026 report: the recording notice in the present tense; "recorded" only after a successful action

**Owner:** claude (claude-dev2 role) · **Task:** `tasks/T-026-recording-disclosure.md` · **UAT:** F-086.
**Not done:** no Freya request, no model call, no commit, no env.sh. Generic: no brief value in `builder/`; the leak test is green on my files.

## What changed

1. **The disclosure rule (`builder/spoken.py`, `present_recording_notice`).** A fixed rule rewrites only the call-recording clause of a spoken line to the present continuous, "we are recording this call".
   - **What it matches:**
     - "this / the / your / our (phone) call is / is being / will be recorded";
     - "calls are (being) recorded".
   - **Grammar:**
     - mid-sentence it stays lower case: "…, and we are recording this call.";
     - at the start of a sentence it gets a capital: "We are recording this call for quality and security.";
     - a purpose after the clause is kept.
   - **No broken forms:** "this call is recording" is never produced.
   - **When it does not rewrite:** a "recorded" that is not clearly the notice (for example "may be recorded", or "your details are recorded") is left as it is, and the build trace gets a warning `recording_notice agent.introduction: …`. A rewrite is the fixed rule, so it is not a warning.
2. **Where it applies (`builder/workflow.py`, `speakable_spec`).** The rule is applied to `agent.introduction`. That is the only place the builder renders the opening line:
   - the opening prompt ("Your first words … only once: <introduction>");
   - `opening_reask`, which never repeats it;
   - the opening has no tts line.

   The brief's meaning (that the call is recorded) is kept.
3. **One honesty line, not two (`MULTI_STEP_SYSTEM_PROMPT_TEMPLATE`).**
   - **Old sentence:** "never claim … a note or callback was recorded unless its tool returned ok true; never say a payment or promise was recorded unless create_promise returned ok true".
   - **New sentence:** "Never claim an action succeeded unless its tool returned ok true. Use the word "recorded" only for an action whose tool returned ok true in this call (a payment or promise: create_promise); for the recording notice say "we are recording this call"."
   - **Budget:** it is the system prompt, not a step prompt; negotiate is unchanged by this task.

**Brief A live line:**
- before: "I am a digital assistant calling from Freya Bank, and this call is recorded."
- after: "I am a digital assistant calling from Freya Bank, and we are recording this call."

## Tests

- **New** `tests/test_recording_notice.py` (4 tests):
  - every fixture spec and recorded extraction (10): the rendered opening line has no "recorded", it still says "recording" when the introduction mentioned it, and the system prompt has the honesty line;
  - the Brief A live line;
  - grammar cases (sentence start, purpose kept, after ";", "calls are recorded");
  - lines left alone, with the warning.
- **Changed:**
  - `tests/test_multi_step.py` and `tests/test_spoken_text.py` compare the opening against the rewritten introduction;
  - the system prompt assertion follows the new honesty sentence.
- **Render pin and `python3 -m unittest`:** see `tasks/T-028-report.md`. With my changes alone, 602 tests are OK. The shared tree is red only because of T-027 work in progress (claude-dev).

## Open

- A chat run (with approval) of PUB-10, to confirm the judge.
- An introduction like "this call may be recorded" is left as it is and only warned about. It is not the present state, and rewriting it would change its meaning.
