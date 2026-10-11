# T-041 (FINAL, urgent): the agent speaks the brief's language (Turkish in the final)

**Owner:** claude-dev2 · The final opens at 20:00 Istanbul. The final case is a Turkish credit-card statement-debt line.

## Problem

Many lines the agent speaks are fixed English text in the builder:
- the read-back, closing, offer messages and revise lines;
- the goodbye and recording-notice lines;
- spoken dates ("Friday, 16 October") and number words.

The date reader in the generated code also knows only English month, weekday and number words. In Turkish every one of these is wrong.

## What to build (generic)

1. **The call language.**
   - Extraction returns `agent.language`, an ISO code such as `tr` or `en`, from the documents. The default is `en`.
   - The system prompt says "Speak only <language name>", plus the rule that a recorded word list stays in that language.
2. **Fixed spoken lines.**
   - Collect every customer-facing fixed template the builder renders (tts lines and code-built messages) into one table, with placeholders.
   - For a non-English language, translate the table at build time with ONE model call. Put the language and table in; get JSON back, with every placeholder kept exactly.
   - Validate the placeholders, and fall back to English per line if a check fails.
   - Cache the translation in the trace.
   - Leave the brief's own quoted lines as they are (they are already in the brief's language).
3. **Dates and numbers in the generated code**, picked by language:
   - **Turkish words:** months (Ocak … Aralık), weekdays (Pazartesi … Pazar), and relative words (bugün, yarın, öbür gün, haftaya, gelecek hafta).
   - **Turkish number words** (bir … otuz bir, yirmi altı …), and day-month order ("27 Ekim", "27 Ekim'de" with Turkish suffixes after an apostrophe).
   - **Spoken dates in Turkish:** "16 Ekim Cuma".
   - **Amounts:** "1.250,50" is read as 1250.50; say amounts plainly ("1250 TL" if the documents use TL).
   - English stays the default and unchanged.
4. **Extraction descriptions and intents** may stay in English. They tell the model how to classify; add "the customer may speak <language>".
5. **Self-check.** Run the spoken-date and offer families with Turkish phrases when the language is `tr`.
6. **Tests:**
   - a Turkish fixture (a copy of a fixture spec with `language: tr`);
   - the date reader table for Turkish phrases;
   - placeholders kept;
   - the English render pin unchanged;
   - the leak test.

## Constraints

- No Freya, no commit, no env.sh.
- claude-dev is doing T-040 (the input reader and CLI in `build.py`/`extract.py`) at the same time. Coordinate with them.
- Report: `tasks/T-041-report.md`.
