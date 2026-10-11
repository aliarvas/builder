# T-040 (FINAL, urgent): read the final case folder (md, docx, pdf, xlsx) and the new CLI

**Owner:** claude-dev · **Deadline:** as early as possible. The final opens at 20:00 Istanbul and closes at 23:00.

## New facts (organizer page, 11 Oct)

- **Input:** the final is ONE case, a zip. It holds bank documents in Markdown, Word, PDF and Excel. Read BRIEF.md first; README.md says what each document is. The zip also holds the bank's test customers, 6 sample conversations and a service contract.
- **Command:** the sample command is now `python3 builder/build.py {case_folder} {mock_url}`. Our old contract was `{brief_path...} {tool_api_path}`.
- **Tools:** the agent may call ONLY our own mock (`mock_url`), which we deploy before the run.

## What to build (generic; the content is unknown)

1. **CLI.** `build.py` accepts both:
   - the old form (brief files plus an OpenAPI path);
   - the new form: one directory plus a URL (`http(s)://…`).

   Detect the form by argument type: an existing directory, and an argument that starts with http.
2. **The folder.** Collect every document recursively, in a stable order:
   - BRIEF.md first, README.md second, then the rest by path.
   - Skip hidden files and `__MACOSX`.
3. **Readers, standard library only:**
   - **`.md`, `.txt`, `.csv`, `.json`, `.yaml`:** read as text.
   - **`.docx`:** `zipfile` + `word/document.xml`. Paragraphs, with tables as rows joined by ` | `.
   - **`.xlsx`:** `zipfile`, `xl/sharedStrings.xml`, `xl/workbook.xml` + `xl/worksheets/sheet*.xml`. Output each sheet name and its rows as CSV-like lines; handle shared strings, inline strings and numbers.
   - **`.pdf`:** send it to Claude as a native `document` content block (base64, `media_type` `application/pdf`) in the extraction calls. The Anthropic Messages API supports this. Keep a text note "[PDF: name]" in the source list.
   - **Unknown binary:** skip it with a trace warning.
4. **Source labels.** Each document is labelled with its file name, so evidence quotes keep working (provenance).
5. **The tool contract.** Find the OpenAPI/JSON contract in the folder if there is one.
   - If the service contract is a document rather than OpenAPI, the builder derives an OpenAPI 3 JSON for the seven tools, with an extraction call constrained to the document.
   - Set `servers[0].url` to `mock_url`.
   - Write the derived file into the trace directory.
6. **Test customers and sample conversations.** Detect them, by file name and/or content, and pass them to extraction as reference material only.
7. **Tests:**
   - a synthetic folder with a .docx and an .xlsx (build them in the test with `zipfile`), a fake PDF (check the block is built; no model call);
   - both CLI forms;
   - the leak test.

## Constraints

- No Freya, no commit, no env.sh.
- Keep `builder/freya.py` identical to the kit.
- Report: `tasks/T-040-report.md`.
