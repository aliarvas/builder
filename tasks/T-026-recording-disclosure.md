# T-026: Recording disclosure in the present tense; "recorded" only after a successful action

**Owner:** next fix round · **Reviewer:** claude-reviewer · **Approver:** CTO

## Why

A live PUB-10 run failed on the judge check "agent does not say 'recorded' before a successful call". The only early "recorded" was the opening disclosure "this call is recorded". That disclosure is required by the brief, which asks the agent to say *that* the call is recorded; it does not give the words.

Banking calls in general follow one convention:
- **The disclosure describes the present state:** "we are recording this call", or "calls are recorded for quality and security".
- **"Recorded" as a result is said only after an action succeeded:** "your promise has been recorded".

## What to build (generic, no brief value)

1. **A fixed builder rule for spoken disclosures.** Apply it wherever the builder renders the opening line or its instruction (opening `on_enter`, the opening prompt, the re-ask):
   - Say the recording disclosure in the present continuous: "we are recording this call". Never use the past participle "recorded" in it.
   - The rule applies only to the disclosure. It does not change the meaning the brief asks for.
2. **A global honesty line, if not already present:** "Use the word 'recorded' only for an action whose tool returned success in this call."
   - Check the existing honesty lines first so the same thing is not said twice.
   - Watch the prompt budget: negotiate is already about 1680 tokens.
3. **Grammar.** The rendered English must be correct and natural. Examples:
   - "I am Freya Bank's digital assistant, and we are recording this call."
   - "This is a digital assistant calling from <bank>; we are recording this call."

   Avoid broken forms such as "this call is recording".
4. **Spoken-text check (`spoken.py` or the opening render).** If an extracted opening line that is spoken as is (`tts`) contains "is recorded" or "being recorded" for the call, rewrite only that clause to "we are recording this call". Rewrite only when the clause is clearly the call-recording disclosure; otherwise leave the line and write a trace warning.

## Tests

- Every fixture and recorded extraction:
  - the rendered opening has no "recorded" before any tool result;
  - the opening still discloses the recording, as a phrase with "recording".
- Brief A live spec: the opening line is rewritten correctly, with correct grammar.
- Leak test green.
- `python3 -m unittest`.

## Constraints

No Freya, no model call, no commit, no `env.sh`. Write the report to `tasks/T-026-report.md`.
