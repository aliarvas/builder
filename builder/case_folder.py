"""T-040: the final's input, one case folder (or its zip) and the URL of our own mock.

The folder holds the bank's documents in Markdown, Word, PDF and Excel, a README saying what
each is, test customers, sample conversations and a service contract. This module turns it
into what the extraction already takes: labelled text documents (the file name is the label,
so source excerpts keep their provenance), PDF files as native document blocks for the
builder model, and an OpenAPI document whose server is the mock URL. Standard library only.
"""

from __future__ import annotations

import base64
import datetime
import json
import re
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree

TEXT_SUFFIXES = (".md", ".markdown", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml", ".eml", ".html", ".htm", ".xml")
BRIEF_NAME = "brief.md"
README_NAME = "readme.md"
# Words in a file name that mark example material: test customers and sample calls. A plain
# "customer" is not one ("customer-contact-policy" is policy); "customers" or "test" is.
# A meeting transcript is not one: meetings record decisions (T-046, the final's pack).
REFERENCE_WORDS = ("conversation", "sample", "example", "test", "customers")
# A reference document longer than this is cut (the final's test-customer file was 700 KB, about
# 175k tokens): the rest of the context must still fit and stay fast.
REFERENCE_CHAR_LIMIT = 20000
# Words that mark the service contract.
CONTRACT_WORDS = ("contract", "openapi", "swagger", "api", "tool", "service", "endpoint")
PDF_MEDIA_TYPE = "application/pdf"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class CaseFolderError(ValueError):
    """The case folder cannot be read."""


@dataclass
class CaseDocument:
    name: str                    # path relative to the case folder: the source label
    kind: str                    # file suffix without the dot
    text: str
    role: str = "policy"         # policy | reference | contract
    pdf: bytes | None = None


@dataclass
class Case:
    folder: Path
    documents: list[CaseDocument]
    openapi: dict[str, Any] | None
    openapi_source: str          # the file it came from, "derived", or ""
    warnings: list[str] = field(default_factory=list)

    def text_documents(self) -> list[tuple[str, str]]:
        """(label, text) in reading order, for the extraction context and the evidence checks."""
        result = []
        for item in self.documents:
            text = item.text
            if item.role == "reference":
                text = REFERENCE_NOTE + "\n\n" + text
            result.append((item.name, text))
        return result

    def attachments(self) -> list[dict[str, Any]]:
        """PDF files as native document blocks for the builder model."""
        return [pdf_block(item.name, item.pdf) for item in self.documents if item.pdf]


REFERENCE_NOTE = ("[Reference material: example customers or sample conversations. Use it only to understand "
                  "the policy documents; never take a rule, value or outcome from it alone.]")


def pdf_block(name: str, data: bytes) -> dict[str, Any]:
    return dict(type="document", title=name,
                source=dict(type="base64", media_type=PDF_MEDIA_TYPE, data=base64.b64encode(data).decode("ascii")))


# ---------------------------------------------------------------------------
# The folder
# ---------------------------------------------------------------------------

def unpack(path: Path, into: Path) -> Path:
    """A zip is unpacked into ``into`` (skipping unsafe names); a folder is used as it is."""
    if path.is_dir():
        return path
    if path.suffix.lower() != ".zip" or not path.is_file():
        raise CaseFolderError(f"{path}: not a folder or a .zip file")
    into.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            parts = Path(member.filename).parts
            if member.is_dir() or not parts or ".." in parts or Path(member.filename).is_absolute():
                continue
            target = into.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))
    return into


def case_files(folder: Path) -> list[Path]:
    """Every file under ``folder``, without hidden files and ``__MACOSX``: BRIEF.md first,
    README.md second, then the rest by path."""
    files = []
    for path in folder.rglob("*"):
        relative = path.relative_to(folder).parts
        if not path.is_file() or any(part.startswith(".") or part == "__MACOSX" for part in relative):
            continue
        files.append(path)

    def order(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        depth = len(path.relative_to(folder).parts)
        rank = 0 if name == BRIEF_NAME and depth == 1 else 1 if name == README_NAME and depth == 1 else 2
        return rank, str(path.relative_to(folder)).lower()

    return sorted(files, key=order)


def read_case(folder: Path, mock_url: str) -> Case:
    """Read every document; find the OpenAPI contract if there is one (its server set to
    ``mock_url``). A contract that is a document, not OpenAPI, is left for ``derive_openapi``."""
    if not folder.is_dir():
        raise CaseFolderError(f"{folder}: not a folder")
    documents: list[CaseDocument] = []
    warnings: list[str] = []
    openapi: dict[str, Any] | None = None
    openapi_source = ""
    for path in case_files(folder):
        name = str(path.relative_to(folder))
        suffix = path.suffix.lower()
        data = path.read_bytes()
        try:
            if suffix == ".json":
                text = data.decode("utf-8-sig")
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict) and ("openapi" in parsed or "swagger" in parsed) and isinstance(
                        parsed.get("paths"), dict):
                    if openapi is None:
                        openapi, openapi_source = parsed, name
                    documents.append(CaseDocument(name, "json", text, "contract"))
                    continue
                documents.append(CaseDocument(name, "json", text, role_of(name, text)))
            elif suffix in TEXT_SUFFIXES:
                text = data.decode("utf-8-sig", errors="replace")
                documents.append(CaseDocument(name, suffix[1:], text, role_of(name, text)))
            elif suffix == ".docx":
                text = read_docx(data)
                documents.append(CaseDocument(name, "docx", text, role_of(name, text)))
            elif suffix == ".xlsx":
                text = read_xlsx(data)
                documents.append(CaseDocument(name, "xlsx", text, role_of(name, text)))
            elif suffix == ".pdf":
                text = pdf_text(data)
                label = f"[PDF: {name}; the file itself is attached to this request as a document]"
                documents.append(CaseDocument(name, "pdf", label + ("\n\n" + text if text else ""),
                                              role_of(name, text), pdf=data))
            else:
                warnings.append(f"{name}: skipped (unknown file type {suffix or 'without suffix'})")
        except (zipfile.BadZipFile, ElementTree.ParseError, KeyError, UnicodeDecodeError) as exc:
            warnings.append(f"{name}: could not be read ({type(exc).__name__}: {exc}); skipped")
    if not documents:
        raise CaseFolderError(f"{folder}: no readable document")
    if openapi is not None:
        openapi = with_server(openapi, mock_url)
    for item in documents:
        if item.role == "reference" and len(item.text) > REFERENCE_CHAR_LIMIT:
            cut = len(item.text) - REFERENCE_CHAR_LIMIT
            item.text = item.text[:REFERENCE_CHAR_LIMIT] + f"\n[... {cut} more characters of this reference file left out]\n"
            warnings.append(f"{item.name}: reference file cut to {REFERENCE_CHAR_LIMIT} characters ({cut} left out)")
    return Case(folder, documents, openapi, openapi_source, warnings)


def role_of(name: str, text: str) -> str:
    """reference (test customers, sample conversations), contract, or policy."""
    lowered = Path(name).name.lower()
    stem = re.sub(r"[^a-z]+", " ", lowered)
    if lowered in (BRIEF_NAME, README_NAME):
        return "policy"
    if any(re.search(r"\b" + word + r"s?\b", stem) for word in CONTRACT_WORDS[:2]) or "contract" in stem:
        return "contract"
    if any(re.search(r"\b" + word + r"s?\b", stem) for word in REFERENCE_WORDS) or re.search(r"\btest\w*", stem):
        return "reference"
    # A transcript: most non-empty lines start with a speaker label.
    lines = [line for line in text.splitlines() if line.strip()]
    speakers = [line for line in lines if re.match(r"\s*\**(agent|assistant|bot|customer|caller)\**\s*:", line, re.I)]
    if len(lines) >= 4 and len(speakers) * 2 >= len(lines):
        return "reference"
    return "policy"


def with_server(document: dict[str, Any], mock_url: str) -> dict[str, Any]:
    """The contract with ``servers[0].url`` set to the mock: the agent calls only our mock."""
    result = json.loads(json.dumps(document))
    servers = [item for item in result.get("servers") or [] if isinstance(item, dict)]
    result["servers"] = [{**(servers[0] if servers else {}), "url": mock_url.rstrip("/")}, *servers[1:]]
    return result


# ---------------------------------------------------------------------------
# Word
# ---------------------------------------------------------------------------

def read_docx(data: bytes) -> str:
    """Paragraphs in order; a table as rows of cells joined by " | "."""
    with zipfile.ZipFile(_bytes_file(data)) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    body = root.find(W + "body")
    lines: list[str] = []
    for child in list(body if body is not None else []):
        if child.tag == W + "p":
            lines.append(_paragraph(child))
        elif child.tag == W + "tbl":
            for row in child.iter(W + "tr"):
                cells = [" ".join(_paragraph(p) for p in cell.iter(W + "p")).strip() for cell in row.findall(W + "tc")]
                lines.append(" | ".join(cells))
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def _paragraph(paragraph: ElementTree.Element) -> str:
    parts = []
    for node in paragraph.iter():
        if node.tag == W + "t":
            parts.append(node.text or "")
        elif node.tag == W + "tab":
            parts.append("\t")
        elif node.tag in (W + "br", W + "cr"):
            parts.append("\n")
    text = "".join(parts)
    style = paragraph.find(f"{W}pPr/{W}pStyle")
    level = re.match(r"heading\s*(\d)", (style.get(W + "val") or "").lower()) if style is not None else None
    if level and text.strip():
        return "#" * min(6, int(level.group(1))) + " " + text
    if paragraph.find(f"{W}pPr/{W}numPr") is not None and text.strip():
        return "- " + text
    return text


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

BUILTIN_DATE_FORMATS = set(range(14, 23)) | {45, 46, 47}


def read_xlsx(data: bytes) -> str:
    """Each sheet: "## Sheet: <name>" and its rows as comma-separated lines. Shared strings,
    inline strings, booleans and numbers; a number in a date format becomes YYYY-MM-DD (and
    HH:MM when it has a time)."""
    with zipfile.ZipFile(_bytes_file(data)) as archive:
        names = set(archive.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            for item in ElementTree.fromstring(archive.read("xl/sharedStrings.xml")).findall(S + "si"):
                shared.append("".join(node.text or "" for node in item.iter(S + "t")))
        dates = _date_styles(archive.read("xl/styles.xml")) if "xl/styles.xml" in names else set()
        sheets = _sheet_paths(archive, names)
        out: list[str] = []
        for title, path in sheets:
            if path not in names:
                continue
            out.append(f"## Sheet: {title}")
            root = ElementTree.fromstring(archive.read(path))
            for row in root.iter(S + "row"):
                values: dict[int, str] = {}
                for cell in row.findall(S + "c"):
                    column = _column(cell.get("r") or "")
                    if column is None:
                        column = len(values)
                    values[column] = _cell_text(cell, shared, dates)
                if any(value.strip() for value in values.values()):
                    width = max(values) + 1
                    out.append(",".join(_csv(values.get(index, "")) for index in range(width)))
            out.append("")
    return "\n".join(out).strip() + "\n"


def _sheet_paths(archive: zipfile.ZipFile, names: set[str]) -> list[tuple[str, str]]:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    targets = {}
    if "xl/_rels/workbook.xml.rels" in names:
        for rel in ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels")).iter(PR + "Relationship"):
            target = rel.get("Target") or ""
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            targets[rel.get("Id")] = target
    result = []
    for index, sheet in enumerate(workbook.iter(S + "sheet"), start=1):
        path = targets.get(sheet.get(R + "id")) or f"xl/worksheets/sheet{index}.xml"
        result.append((sheet.get("name") or f"Sheet{index}", path))
    return result


def _date_styles(styles_xml: bytes) -> set[int]:
    root = ElementTree.fromstring(styles_xml)
    custom = {}
    formats = root.find(S + "numFmts")
    for item in list(formats if formats is not None else []):
        code = re.sub(r'"[^"]*"|\[[^\]]*\]', "", item.get("formatCode") or "").lower()
        custom[int(item.get("numFmtId") or 0)] = bool(re.search(r"[dmy]", code)) and "0.0" not in code
    result = set()
    xfs = root.find(S + "cellXfs")
    for index, xf in enumerate(list(xfs if xfs is not None else [])):
        number = int(xf.get("numFmtId") or 0)
        if number in BUILTIN_DATE_FORMATS or custom.get(number):
            result.add(index)
    return result


def _column(reference: str) -> int | None:
    letters = re.match(r"[A-Z]+", reference)
    if not letters:
        return None
    value = 0
    for letter in letters.group(0):
        value = value * 26 + ord(letter) - 64
    return value - 1


def _cell_text(cell: ElementTree.Element, shared: list[str], dates: set[int]) -> str:
    kind = cell.get("t") or "n"
    raw = cell.find(S + "v")
    value = raw.text if raw is not None and raw.text is not None else ""
    if kind == "s":
        return shared[int(value)] if value.isdigit() and int(value) < len(shared) else ""
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(S + "t"))
    if kind == "b":
        return "TRUE" if value == "1" else "FALSE"
    if kind in ("str", "e"):
        return value
    if not value:
        return ""
    try:
        number = float(value)
    except ValueError:
        return value
    if int(cell.get("s") or 0) in dates:
        return _excel_date(number)
    return str(int(number)) if number.is_integer() else repr(number)


def _excel_date(serial: float) -> str:
    moment = datetime.datetime(1899, 12, 30) + datetime.timedelta(days=serial)
    if serial < 1:  # a time of day only
        return moment.strftime("%H:%M")
    if abs(serial - int(serial)) < 1e-9:
        return moment.date().isoformat()
    return moment.strftime("%Y-%m-%d %H:%M")


def _csv(value: str) -> str:
    return '"' + value.replace('"', '""') + '"' if any(mark in value for mark in ',"\n') else value


# ---------------------------------------------------------------------------
# PDF: the file goes to the model; the text found here only helps the evidence checks
# ---------------------------------------------------------------------------

def pdf_text(data: bytes) -> str:
    """Best-effort text of a simple PDF (Flate or plain content streams, Tj/TJ strings). Empty
    when none is found; the model reads the attached file itself."""
    chunks = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        stream = match.group(1)
        try:
            stream = zlib.decompress(stream)
        except zlib.error:
            pass
        lines = []
        for block in re.findall(rb"BT(.*?)ET", stream, re.S):
            parts = []
            for item in re.finditer(rb"\((?:\\.|[^\\)])*\)\s*Tj|\[(.*?)\]\s*TJ|(T\*|Td|TD|')", block, re.S):
                token = item.group(0)
                if token.endswith(b"Tj"):
                    parts.append(_pdf_string(token[:token.rindex(b")") + 1]))
                elif token.endswith(b"TJ"):
                    parts.append("".join(_pdf_string(s) for s in re.findall(rb"\((?:\\.|[^\\)])*\)", item.group(1) or b"")))
                elif parts:
                    parts.append("\n")
            line = "".join(parts).strip()
            if line:
                lines.append(line)
        if lines:
            chunks.append("\n".join(lines))
    text = "\n".join(chunks)
    printable = sum(ch.isprintable() or ch in "\n\t" for ch in text)
    return text if text and printable >= 0.9 * len(text) else ""


def _pdf_string(raw: bytes) -> str:
    body = raw[1:-1]
    body = re.sub(rb"\\([nrtbf()\\])", lambda m: {b"n": b"\n", b"r": b"", b"t": b"\t", b"b": b"", b"f": b"",
                                                   b"(": b"(", b")": b")", b"\\": b"\\"}[m.group(1)], body)
    body = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 255]), body)
    return body.decode("latin-1")


def _bytes_file(data: bytes):
    import io
    return io.BytesIO(data)


# ---------------------------------------------------------------------------
# A contract that is a document: derive the OpenAPI file
# ---------------------------------------------------------------------------

def contract_documents(case: Case) -> list[CaseDocument]:
    """The documents that describe the tools: the contract ones, else every document."""
    found = [item for item in case.documents if item.role == "contract"]
    if not found:
        found = [item for item in case.documents
                 if any(word in re.sub(r"[^a-z]+", " ", item.name.lower()).split() for word in CONTRACT_WORDS)]
    return found or list(case.documents)


def check_derived(document: Any, sources: str) -> list[str]:
    """Problems of a derived OpenAPI document: shape, and every tool name and field written in
    the contract documents (nothing invented)."""
    from .tools_from_openapi import OpenAPIError, tools_from_openapi

    if not isinstance(document, dict) or not isinstance(document.get("paths"), dict) or not document["paths"]:
        return ["the reply is not an OpenAPI object with paths"]
    problems = []
    try:
        tools_from_openapi(document, warnings=[])
    except OpenAPIError as exc:
        problems.append(f"the tool reader rejects it: {exc}")
    plain = sources.lower()
    for path, item in document["paths"].items():
        name = str(path).strip("/")
        if name.lower() not in plain:
            problems.append(f"tool {name!r} is not written in the contract documents")
        body = (((item.get("post") or {}).get("requestBody") or {}).get("content") or {}).get("application/json") or {}
        for field_name in ((body.get("schema") or {}).get("properties") or {}):
            if str(field_name).lower() not in plain:
                problems.append(f"field {name}.{field_name} is not written in the contract documents")
    return problems


def derive_openapi(case: Case, mock_url: str, complete: Callable[[str, list[dict[str, Any]]], str],
                   attempts: int = 2) -> tuple[dict[str, Any], list[str]]:
    """Ask the builder model for an OpenAPI 3 document of the tools the contract documents
    describe, check it against them, repair once. Returns (document, remaining problems)."""
    from .llm import text_block
    from .prompts import CONTRACT_DERIVE_SYSTEM, CONTRACT_DERIVE_TASK, CONTRACT_DERIVE_REPAIR

    sources = contract_documents(case)
    text = "\n\n".join(f"## Document: {item.name}\n\n{item.text}" for item in sources)
    content: list[dict[str, Any]] = [pdf_block(item.name, item.pdf) for item in sources if item.pdf]
    content += [text_block(text), text_block(CONTRACT_DERIVE_TASK.text)]
    messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
    document: dict[str, Any] = {}
    problems = ["no reply"]
    plain = "\n".join(item.text for item in case.documents)
    for _ in range(max(1, attempts)):
        reply = complete(CONTRACT_DERIVE_SYSTEM.text, messages)
        messages.append({"role": "assistant", "content": reply or "(empty reply)"})
        try:
            parsed = json.loads(_json_object(reply))
        except (ValueError, json.JSONDecodeError) as exc:
            parsed, problems = None, [f"the reply was not one JSON object ({exc})"]
        if parsed is not None:
            problems = check_derived(parsed, plain)
            document = parsed
            if not problems:
                break
        messages.append({"role": "user", "content": CONTRACT_DERIVE_REPAIR.text.replace(
            "{problems}", "\n".join("- " + item for item in problems))})
    if document:
        document = with_server(document, mock_url)
    return document, problems


def _json_object(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the reply")
    return text[start:end + 1]
