# T-041 report: the agent speaks the brief's language (Turkish in the final)

**Owner:** claude-dev2.
**Not done:** no Freya request, no commit, no env.sh. The model call I added runs only in a real build and was not run here.
**Generic:** the words are Turkish language words; no brief value. The leak test is green.
**`python3 -m unittest`:** 678 tests, OK. The English Brief A pin is unchanged.
**UAT:** F-101.

## What was built

1. **Call language (`builder/language.py`).**
   - **The language code.** `language_code(agent.language)` maps "Turkish", "tr", "Türkçe" and "tr-TR" to `tr`; English is the default.
     - The extraction already returns `agent.language` ("language of the call"), so `extract.py` is unchanged.
   - **Non-English calls (`apply_call_language` in `workflow.py`):**
     - the system prompt starts with "Speak only Turkish, also when the customer uses another language. Tool values, codes and the documents' word lists stay exactly as the documents give them.";
     - every extraction description ends with "The customer may speak Turkish.";
     - intents stay in English.
2. **Fixed spoken lines.**
   - **The table.** `spoken_definitions()` lists every definition whose receiver is "fixed spoken line", plus `ACCOUNT_WAIT_LINE`. That is 14 lines: offer messages, read-back line and item, revise and resume lines, closing and special fallbacks, callback lines, and the third-party re-ask.
   - **The translation.** `translate_table` makes ONE model call (`SPOKEN_TABLE_TRANSLATE_SYSTEM`) with JSON in and JSON out.
   - **Per-line checks.** A line is used only if:
     - it keeps the same placeholders (`{x}`, `{{x}}`, `[x]`);
     - it keeps the same line count;
     - for the offer messages, it keeps the `key:` prefixes.
     - Otherwise that line stays English, with a warning.
     - If the call fails, all lines stay English.
   - **Rendering.** `localized(table)` swaps the texts in while the workflow is rendered, then restores them.
   - **Trace.** The table is written to the trace (`spoken_lines`).
   - **Wiring.** `build.py` wraps the render in `spoken_language(spec, trace)`; claude-dev agreed to that edit. For English it does nothing and makes no model call.
   - **Brief lines.** The brief's own quoted lines are not touched.
3. **Dates and numbers in the generated code (`offer_check.py`, `TURKISH_DATES`).** This block is appended only for `tr`, so English code stays byte for byte the same.
   - **Reading:**
     - month and weekday names with suffixes ("Ekim'de", "Cumaya");
     - bugün, yarın, öbür gün / yarından sonra;
     - haftaya / gelecek hafta / önümüzdeki hafta, plus "gelecek <day>" and "bu <day>";
     - day numbers in words, including the softened stem ("yirmi yedi", "on dördü");
     - "27 Ekim'de" and "Ekim'in on altısı";
     - digit dates "16.10.2026" and "16/10";
     - "ayın 20'si".
   - **Correction and talkative rules:** corrections ("pardon", "yani", "aslında", …) and the pay word ("öde…") work as in T-034.
   - **Speaking:** "16 Ekim Cuma" (the year only when it differs); amounts as "637,50" or "1250".
   - **Amounts:** "1.250,50" already parsed to 1250.5.
4. **Self-check:** for `tr`, the spoken-date family also plays "16 Ekim", "16 Ekim'de" and "on altı Ekim" (`spoken_date_tr_*`).
5. **Tests (`tests/test_t041_turkish.py`, 10 tests):**
   - language codes;
   - the Turkish fixture (a copy of `brief-a-reference` with `language: Turkish`): system prompt and extraction note;
   - the English render has neither;
   - the date reader table (16 phrases);
   - Turkish speaking of dates and amounts;
   - the whole self-check on the Turkish fixture;
   - the translation keeps placeholders, otherwise the line stays English, and a failed call keeps English;
   - `localized` restores the texts;
   - English makes no model call.

## Open (not done in the time)

- **Product names are English.** They come from the bank data and the code: "credit card ending 1903" ("ending", the kind words, and the ordinal names "the first one"). The kind comes from the bank's English `type` value. A Turkish product name needs a table or the model.
- **Recording notice:** the T-026 rewrite and the system prompt's "say 'we are recording this call'" are English. The final brief's introduction will be Turkish; check the opening line on the first build.
- **Callback times in Turkish:** the third-party callback reader (`callback.py`) was not changed. "yarın saat on birde" will not be read.
- **No currency word:** amounts are said without "TL".
- **Not run live:** the translation call. Its quality and its time cost (about one model call, a few seconds) need the first real build.
- **Live (with approval):** a Turkish chat run of the final case.
