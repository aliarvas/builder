# T-040: the final's case folder and the new CLI

No Freya, no model call (tests use fake clients), no commit, no env.sh. `builder/freya.py` is unchanged.

**Tests:**
- `tests/test_t040_case_folder.py`: 9 tests, all OK.
- Full suite: 668 tests. The only failure is the leak test on `'English'`. That literal is in claude-dev2's in-progress T-041 language work; I told them. My own leak (`'type'` in `pdf_block`) is fixed.
- `docs/PROMPTS.md` is regenerated.

## CLI (`builder/build.py`)

- **Two forms**, detected by argument type (`case_form`):
  - **New:** `python3 builder/build.py {case_folder|case.zip} {mock_url}`. The rule: exactly 2 arguments, the second starting with `http://` or `https://`, the first an existing folder or a `.zip`.
  - **Old:** `{brief_path...} {openapi_path}`, unchanged.
- **One input record for both:** `Inputs` (documents, contract, files for the trace, PDF attachments). `_extract` now takes the documents and attachments instead of the brief paths.
- **Slot:** the default slot comes from the folder name (or the zip's stem).
- **Trace lines:**
  - `input_form`;
  - one `case_document` line per file: name, kind, role, characters, and whether a PDF is attached;
  - `contract`, `contract_file`;
  - warnings for skipped files.

## The folder (`builder/case_folder.py`, standard library only)

- **Zip:** unpacked into `traces/<slot>.case/`. Unsafe names (`..`, absolute paths) are skipped.
- **Order:** every file found recursively. BRIEF.md first, README.md second (matched by base name, so a zip with a top folder works), then the rest by path. Hidden files and `__MACOSX` are skipped.
- **Readers:**

| Type | How it is read |
|---|---|
| `.md` `.txt` `.csv` `.tsv` `.json` `.yaml` | as text |
| `.docx` | `word/document.xml`: paragraphs, headings as `#`, list items as `- `, tables as rows of cells joined by ` | ` |
| `.xlsx` | each sheet as `## Sheet: <name>` and its rows as CSV-like lines (see below) |
| `.pdf` | sent to the model as a native `document` block (base64, `application/pdf`), plus a text entry (see below) |
| anything else | skipped, with a trace warning |

- **`.xlsx` details:**
  - reads shared strings, inline strings, booleans and numbers;
  - column positions are kept;
  - **a number in a date format becomes `YYYY-MM-DD`** (and `HH:MM` when it has a time). Holidays in Excel are usually stored this way; without it they would arrive as serial numbers.
- **`.pdf` details:**
  - the text entry is `[PDF: name; the file itself is attached…]`;
  - for simple PDFs it also includes the text found in the file (Flate streams, Tj/TJ). This text helps the evidence checks that look for values verbatim in the documents. The model reads the attached file.
  - The block goes first in every extraction group's first message (`extract_spec(..., attachments=...)`). The context's cache mark covers it.
- **Labels and roles:**
  - every document is labelled with its path in the folder, so the source excerpts keep their provenance;
  - **reference:** a file named like `test`, `customers`, `sample`, `conversation`, `transcript`, `dialog` or `example`, or text where most lines start with a speaker label. Plain "customer" is not enough, so `customer-contact-policy` stays policy. Its text starts with a note: use it only to understand the policy; never take a rule, value or outcome from it alone.
  - **contract:** a file named `contract`/`openapi`, or an OpenAPI JSON.
  - **policy:** everything else.

## The tool contract

**An OpenAPI JSON in the folder:** it is used, with `servers[0].url` set to the mock URL. Its other server entries are kept after it.

**A contract that is only a document:** `derive_openapi` makes one model call (prompts `CONTRACT_DERIVE_SYSTEM`, `CONTRACT_DERIVE_TASK` and `CONTRACT_DERIVE_REPAIR`). Its inputs are the contract documents (all documents if none is marked) and their PDFs.
- **Output shape:** the kit's shape: `POST /<tool>`, request schema with types, enums and required fields, and a 200 response schema.
- **`check_derived`:**
  - the builder's tool reader must accept it;
  - every tool name and request field must be written in the documents;
  - otherwise one repair round runs, naming each problem.

**Where it is written:** the contract used, in both cases, goes to `traces/<slot>.openapi.json` with the mock URL as server.

## Tests

- **docx:** headings, a paragraph and a table.
- **xlsx:** two sheets; shared and inline strings; numbers; a date cell read as `2026-11-20`.
- **pdf:** the text is found and the attachment block is built.
- **Folder:**
  - BRIEF/README first;
  - `.DS_Store`, `__MACOSX` and the PNG skipped, with a warning;
  - roles: test customers and the sample conversation as reference, the docx as policy, the JSON contract as contract;
  - the mock URL set; labels kept;
  - a zip with a top folder and a `../` entry: the entry is not written outside.
- **Derivation (fake model):** an invented field is caught, the repair names it, and the second reply passes.
- **CLI:**
  - both forms detected;
  - the case form reaches the extraction with labels, one PDF attachment and the mock server;
  - the old form unchanged.

## Not done or open

- **YAML contracts** are read as text. There is no YAML parser in the standard library, so a YAML OpenAPI file goes through derivation.
- **Test customers and sample conversations** go to the same extraction context as reference material. They are not used for the self-check yet. Turning them into self-check scenarios would be a separate task.
- **Not live-tested:** not on a real final zip, not with a real PDF through the API. The `document` block format follows the Messages API documentation. **First run:** `--print` on the zip, then check the trace's `case_document` and `contract` lines and the spec.
