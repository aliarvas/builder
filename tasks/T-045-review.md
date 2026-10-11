# T-045 review: 5f395ed, T-040 (case folder, CLI, derive_openapi) and T-041 (language, Turkish dates)

**Reviewer:** claude-reviewer. Offline only; no Freya, no env.sh, no code edited. Method: read `builder/case_folder.py`, `builder/language.py`, the `build.py` diff and `offer_check.TURKISH_DATES`; generated small docx/xlsx/pdf files and a case folder in the scratchpad and ran `read_xlsx`, `read_docx`, `pdf_text`, `read_case`; executed the generated Turkish date reader (`_prelude` for a Turkish spec) on about 100 phrases.

## Decision: **düzeltme gerekli** (3 HIGH that can end or poison a final build or call, 5 MEDIUM, LOW notes)

---

## HIGH

### 1. PDF documents: the builder cannot see their text, and one rejected PDF kills every extraction call
**Files:** `builder/case_folder.py:331-352` (`pdf_text`), `builder/extract.py:1307-1313` (`_Conversation`), `builder/llm.py:132-165` (`complete`).
- **The block format is right.** `{"type":"document","source":{"type":"base64","media_type":"application/pdf","data":...},"title":...}` is a valid Messages API document block, placed before the text blocks in the user turn.
- **Evidence checks run on text only.** The extraction's value checks are *errors*, not warnings, for: an outcome/reason pair "not found together in the documents", a day "does not appear in the documents", a number or an HH:MM that "does not appear" (`extract.py:406-430, 577`). They read the document text. `pdf_text` finds only plain `(…) Tj` and `[(…)] TJ` strings. I tested it: a Flate stream with `(Late fee is )-20(five)] TJ` is read; **`<0048004500> Tj` (hex glyph ids, which is how Word, Google Docs and most exporters write text) gives an empty string.** So for a typical PDF the document text is only the placeholder line, and any rule, date or number that exists only in the PDF fails the checks, goes to repair, and in the last round the field is dropped or the build ends with an invalid spec.
- **No fallback for a PDF the API refuses.** An encrypted or damaged PDF, more than 100 pages, or a request over the size limit returns HTTP 400. `complete()` raises `LLMError`; all five extraction groups carry the same blocks, so all fail and the build stops. Every group also re-sends every PDF (no cache mark on the document blocks themselves), so a large PDF multiplies tokens and time by the number of groups.
**Fix:**
1. For each PDF, one model call "transcribe the document's text verbatim" (the same infrastructure as `derive_openapi`, document block + a short task). Store the transcript as `CaseDocument.text`; then evidence checks and source excerpts work on it, and the PDF block is not needed in the five groups (so no repeated tokens, no 400 risk in the main calls).
2. If the transcription fails, or the text is empty: keep the PDF block, mark the document `unverifiable`, and turn the "does not appear in the documents" checks from errors into warnings for values the PDF could contain.
3. Before sending: check the `%PDF-` header, size below about 20 MB and no `/Encrypt`; on HTTP 400 mentioning the document, retry once without the blocks and log a warning.

### 2. A malformed cell or style crashes `read_case`, and with it the build
**File:** `builder/case_folder.py:127-145` (the `except` list), `:274-300`, `:303-312`.
The loop catches only `BadZipFile, ParseError, KeyError, UnicodeDecodeError`. I produced these uncaught: a date-styled cell with a very large serial (`99999999999`) or `INF` gives `OverflowError`; `s="x"` or a non-numeric `numFmtId` in `styles.xml` gives `ValueError`. `build.py` catches only `CaseFolderError, OSError`, so the exception becomes a traceback and no workflow is produced. One odd spreadsheet in the final bundle is enough.
**Fix:** `except Exception as exc:` around each file in `read_case` (keep the file as a warning), and `try/except` inside `_excel_date` returning the raw number.

### 3. Language code: a qualified language name silently turns a Turkish call into an English one
**File:** `builder/language.py:53-59` (`language_code`).
`language_code("Turkish")`, `"tr-TR"`, `"Türkçe"` give `tr`; **`"Turkish (Turkey)"`, `"Turkish, formal"`, `"formal Turkish"`, `"Türkçe (TR)"` give `en`.** The extraction only checks that `agent.language` is a non-empty string, so whatever the model writes is taken. With `en`: no translated lines, no Turkish date reader, no `apply_call_language`; the agent speaks English to a Turkish brief with Turkish customers.
**Fix:** match words: split the text into lowercase tokens and test each against `LANGUAGE_WORDS` (and `tr`/`en` prefixes of a hyphenated token). Add a trace warning when the brief text looks Turkish (the characters `ğşıİöüç` in more than a few percent of letters) and the code is `en`.

---

## MEDIUM

### 4. The Turkish date reader gives wrong dates for common phrases
**File:** `builder/offer_check.py` `TURKISH_DATES` (`turkish_date_text`, `resolve_offer_day`, `tr_number_words`). Run on the real generated code (today = 2026-10-14):

| Customer says | Reader gives | Should be |
|---|---|---|
| "yarın değil bugün" | **tomorrow (15 Oct)** | today |
| "pazartesi değil salı" | **Monday 19 Oct** | Tuesday |
| "bugün ödeyemem" ("I cannot pay today") | **today (14 Oct), accepted as an offer** | no date (a refusal; the same fault as T-036 case 4) |
| "bir cuma günü öderim" ("I'll pay on some Friday") | **2027-01-01** (`bir` read as day 1) | Friday 16 Oct |
| "iki cuma sonra" | **2027-04-02** | two Fridays later: ask |
| "pazarlık yapalım" ("let's bargain") | **Sunday 18 Oct** (`pazar*` read as the weekday) | none |
| "salı günü saat 5'te" | **2027-01-05** (the hour read as the day number) | Tuesday 20 Oct |
| "cuma 15'inde değil 16'sında" | 2027-01-15 | 16 Oct |
| "saat 3 gibi cuma" | 2027-09-03 | Friday |

Causes: (a) the negation words `değil` and `yok yok` are not handled (only the correction words are); (b) `bir`/`iki`… are converted to digits whenever a month or weekday name is present, even as article or count; (c) weekday and month names are matched as prefixes, so `pazar`, `salı`, `aralık` ("interval"), `mart`, `ocak` match inside other words (`pazarlık`, `aralık olarak`); (d) the English weekday fallback searches for "weekday + day number", so an hour next to a weekday becomes a far-future day (the **same fault exists in the English reader**: `"friday at 5"` → 2027-02-05, `"next friday at 3"` → 2027-09-03).
Most of these end in a "date too late" reply or a refusal-count rise, but "yarın değil bugün" and "pazartesi değil salı" book the wrong day **inside** the window.
**Fix (generic):** (1) a day word followed by `değil`/`olmaz`/`ödemem`/`ödeyemem` is removed (and the one after `değil` is taken); (2) convert `bir`/`iki`… only directly before a month name, or after one, not before a weekday; (3) match month and weekday names with a word end (`pazar` not followed by letters other than the known suffixes `ı|a|e|da|de|dan|…`); (4) in the weekday fallback (both languages) ignore a number that follows `at`/`saat`/`@` or precedes `pm|am|'te|'da` and require the number to be <= 31 *and* the weekday to agree, otherwise ask. Add the table above as a test.

### 5. Excel and Word content that is read wrongly
**File:** `case_folder.py:216-317` (`read_xlsx`, `_cell_text`), `:176-188` (`read_docx`).
- **Percentages and money formats.** A cell shown as `15 %` is read as `0.15` (I tested styles 9 and 10: `0.15,0.055`). A policy table with a rate, a fee percent or a discount percent reaches the model as a plain fraction without a sign. Fix: for number formats 9 and 10 (and custom formats with `%`) write `15%`.
- **Word content controls.** `read_docx` walks only direct children of `w:body`. Paragraphs inside `w:sdt/w:sdtContent` (content controls, tables of contents, form fields) are dropped: my test returned only "after" and lost the text inside the control. Fix: descend into `w:sdt/w:sdtContent` and `w:ins`/`w:smartTag` blocks the same way.
- **Nested tables** repeat the inner rows (`'A inner\ninner'`): minor noise.
- **Hidden sheets** (`state="hidden"`) are read like the visible ones and may hold superseded rules. Mark them `(hidden)` in the heading.
- **Text encoding.** `.md/.csv/.txt` are decoded as UTF-8 with replacement. A Windows-1254 (Turkish) or UTF-16 export decodes silently with `�` for `ş ı ğ` (I tested a cp1254 csv). The model sees corrupted words and verbatim excerpts no longer match. Fix: try UTF-8 strict, then a BOM check for UTF-16, then cp1254, and only then replacement.

### 6. No cap on the size of the material
**File:** `case_folder.py:Case.text_documents`, `extract.py` context build.
The test customers file and the sample conversations are reference material but are included in full in the context sent to **each** of the five groups. A customers table of a few thousand rows or long transcripts can grow the request past comfortable limits (cost, latency, the 30 minute budget). Fix: cap each reference document to a fixed number of characters (for example the first 20,000, with a line saying it was cut) and log the cut in the trace.

### 7. Document roles are guessed from file names
**File:** `case_folder.py:162-176` (`role_of`).
A policy document whose name contains `customers`, `test`, `example` or `sample` is demoted to "reference" ("never take a rule from it alone"), for example `03-customers-in-arrears.docx` or `sample-letters-policy.md`; the README, which the final says describes each document, is not used. A true sample conversation without these words in the name is caught only by the speaker-line heuristic. Fix: use the README's own lines (a table row or bullet that starts with the file name) as the first source for the role; keep the name heuristic as the fallback; log the roles in the trace (already done) and say in the builder's context which file is reference only (already done for those flagged).

### 8. `pdf_text` can run for tens of seconds
**File:** `case_folder.py:331-352`. The inner pattern `\[(.*?)\]\s*TJ` with `re.S` scans to the end of the text block for every `[` that has no `TJ` after it. A 240 KB content stream with many `[` took **48 s** in my test. Real text streams rarely look like that, but any other stream containing `BT`…`ET` can. Fix: bound the block length (skip blocks over 200 KB) or match `\[[^\]]*\]\s*TJ` with a negated class.

---

## LOW

- **`mock_url` as server.** `with_server` replaces `servers[0].url` with the mock URL without a path (`https://m.example.workers.dev`); the kit contract had `.../v1`. Our worker serves both `/v1/<tool>` and `/<tool>` (mock/core.js `normalizePath`), so the agent's calls work. If the final contract's paths are not prefixed and the real mock expects a prefix, the URL would be wrong; we own the mock, so this is only a note. A Swagger 2.0 file (`host`/`basePath`) is accepted by the `swagger` key test but `with_server` adds `servers`, which `tools_from_openapi` may not use; nothing in the kit suggests Swagger 2.
- **Stale unzip directory.** `_load_case` unzips into `traces/<slot>.case` and does not clear it. A second run with a different zip of the same name mixes old and new files. Remove the directory first. No size limit on members (zip bomb).
- **`derive_openapi`** returns the last parsed document even when `check_derived` still reports problems (only a trace warning). A derived tool whose name is written in the contract in prose ("Verify identity") fails the name check and is only warned; fine, but an invented field also passes. Acceptable for a time-boxed final; consider failing the build when a tool name is not in the documents, because a wrong tool name makes every call fail.
- **Language lines.** `translate_table` keeps the English line when a bracket placeholder (`[amount]`) is translated; a Turkish call then speaks that one line in English. The prompt could say "keep everything in `[ ]` and `{ }` exactly".
- **Self-check language.** `_self_check_problems` builds the workflow outside `spoken_language`, so it simulates English lines with the Turkish date code. It checks structure, not the words, so low risk.
- **`case_form`** requires exactly two arguments and an `http(s)://` second argument; a mock URL without a scheme falls back to the old form and fails with a message about brief files. Add a clear error when the first argument is a folder or zip and the second does not start with `http`.

## What I checked and found fine
- Zip unpacking skips `..` and absolute names; hidden files and `__MACOSX` are skipped; BRIEF.md then README.md come first, the rest sorted by path.
- xlsx: shared strings, inline strings, booleans, formula strings, date serials (date and time), relationship targets (relative and absolute), a missing relationship file, an empty sheet, wide columns: all read without error.
- docx: headings become `#`, lists `-`, tables rows `a | b`, deleted text (`w:delText`) is dropped, inserted text kept.
- Document block shape and position for the Messages API; `derive_openapi` sends the same block types.
- `CaseFolderError` and `OSError` become `BuilderInputError`; OpenAPI inside the folder is found by content, not name.
- The Turkish reader handles the main forms correctly: "16 Ekim", "on altı Ekim", "27 Ekim'de ödeyeceğim", "haftaya cuma", "gelecek hafta pazartesi", "yarın", "öbür gün", "14.10.2026", "30/10", "pazartesi, pardon salı", "yarın ödeyemem ama cuma öderim" (Friday), "ayın 20'sinde", "yirmi yedi Ekim"; vague forms ("bir hafta sonra", "ayın sonunda", "Eylül") return nothing and the check asks again.

## Order of work
1. Items 2 and 3 (minutes each), then item 1 (transcription call; most valuable if any rule lives in a PDF).
2. Item 4: negation, `bir/iki` before weekday, prefix matches, the hour-as-day fallback (fixes the English reader too).
3. Items 5, 6, 8 (small), then 7 and the LOW notes if time remains.

## Tests to add
- `read_case` on a folder with a bad xlsx cell, a content-control docx, a cp1254 csv, a hex-string PDF, a PDF with `/Encrypt`.
- `language_code` table with the qualified names above.
- The Turkish phrase table above, and the English `friday at 5`.
