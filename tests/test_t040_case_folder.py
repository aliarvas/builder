"""T-040: the final's case folder (Markdown, Word, Excel, PDF) and the new CLI form.

The folder is synthetic and built here: a .docx and an .xlsx made with ``zipfile``, a small
PDF, a README, test customers, a sample conversation and a contract. No model call: the
extraction and the contract derivation get fake clients."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

from builder import build, case_folder
from builder.case_folder import (
    PDF_MEDIA_TYPE, REFERENCE_NOTE, case_files, check_derived, derive_openapi, read_case, read_docx, read_xlsx,
    unpack,
)

MOCK = "https://mock.example.invalid/v1"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

CONTRACT = {
    "openapi": "3.0.3", "info": {"title": "t", "version": "1"},
    "servers": [{"url": "https://somewhere.invalid"}],
    "paths": {"/lookup_member": {"post": {
        "requestBody": {"content": {"application/json": {"schema": {
            "type": "object", "properties": {"member_key": {"type": "string"}}, "required": ["member_key"]}}}},
        "responses": {"200": {"description": "ok", "content": {"application/json": {"schema": {
            "type": "object", "properties": {"ok": {"type": "boolean"}}}}}}}}}},
}


def docx(paragraphs, table=()):
    def para(text, style=""):
        props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        return f"<w:p>{props}<w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>"
    body = "".join(para(*item) if isinstance(item, tuple) else para(item) for item in paragraphs)
    if table:
        rows = "".join("<w:tr>" + "".join(f"<w:tc>{para(cell)}</w:tc>" for cell in row) + "</w:tr>" for row in table)
        body += f"<w:tbl>{rows}</w:tbl>"
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return out.getvalue()


def xlsx(sheets):
    """sheets: [(name, rows)]; a row is a list of str (shared), int/float (number),
    ("date", serial) (number in a date style) or ("inline", text)."""
    shared: list[str] = []
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        listed, rels = [], []
        for index, (name, rows) in enumerate(sheets, start=1):
            listed.append(f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>')
            rels.append(f'<Relationship Id="rId{index}" Type="worksheet" Target="worksheets/sheet{index}.xml"/>')
            cells_xml = []
            for r, row in enumerate(rows, start=1):
                cells = []
                for c, value in enumerate(row):
                    ref = chr(65 + c) + str(r)
                    if isinstance(value, tuple) and value[0] == "date":
                        cells.append(f'<c r="{ref}" s="1"><v>{value[1]}</v></c>')
                    elif isinstance(value, tuple):
                        cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{value[1]}</t></is></c>')
                    elif isinstance(value, str):
                        shared.append(value)
                        cells.append(f'<c r="{ref}" t="s"><v>{len(shared) - 1}</v></c>')
                    else:
                        cells.append(f'<c r="{ref}"><v>{value}</v></c>')
                cells_xml.append(f'<row r="{r}">{"".join(cells)}</row>')
            archive.writestr(f"xl/worksheets/sheet{index}.xml",
                             f'<worksheet xmlns="{S_NS}"><sheetData>{"".join(cells_xml)}</sheetData></worksheet>')
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{S_NS}" xmlns:r="{R_NS}"><sheets>{"".join(listed)}</sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels",
                         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                         + "".join(rels) + "</Relationships>")
        archive.writestr("xl/sharedStrings.xml", f'<sst xmlns="{S_NS}">' + "".join(
            f"<si><t>{text}</t></si>" for text in shared) + "</sst>")
        archive.writestr("xl/styles.xml", f'<styleSheet xmlns="{S_NS}"><cellXfs count="2"><xf numFmtId="0"/>'
                                          '<xf numFmtId="14"/></cellXfs></styleSheet>')
    return out.getvalue()


def pdf(text):
    stream = zlib.compress(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1"))
    return (b"%PDF-1.4\n1 0 obj << /Length " + str(len(stream)).encode() + b" /Filter /FlateDecode >>\nstream\n"
            + stream + b"\nendstream\nendobj\n%%EOF\n")


def make_case(root: Path, contract=True):
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# Case\nWhat each document is.\n", encoding="utf-8")
    (root / "BRIEF.md").write_text("# Brief\nRead the documents.\n", encoding="utf-8")
    (root / "policy").mkdir()
    (root / "policy" / "calling-rules.docx").write_bytes(docx(
        [("Calling rules", "Heading1"), "Ask two questions.", "A callback is from 09:15 to 16:45."],
        table=[["Outcome", "When"], ["closed_ok", "a pledge was logged"]]))
    (root / "policy" / "calendar.xlsx").write_bytes(xlsx([
        ("Holidays", [["Date", "Name"], [("date", 46346), "Founders day"], [("date", 46381), ("inline", "Year end")]]),
        ("Limits", [["Band", "Days", "Attempts"], ["early", 10, 2], ["late", 5.5, 1]]),
    ]))
    (root / "policy" / "letter.pdf").write_bytes(pdf("Promises need a clear yes."))
    (root / "test-customers.csv").write_text("name,postcode\nA,X1\n", encoding="utf-8")
    (root / "sample-conversation-1.md").write_text("Agent: hi\nCustomer: hello\nAgent: who\nCustomer: me\n",
                                                   encoding="utf-8")
    (root / ".DS_Store").write_bytes(b"\0\1")
    (root / "__MACOSX").mkdir()
    (root / "__MACOSX" / "x.md").write_text("junk", encoding="utf-8")
    (root / "image.png").write_bytes(b"\x89PNG")
    if contract:
        (root / "service-contract.json").write_text(json.dumps(CONTRACT), encoding="utf-8")
    else:
        (root / "service-contract.md").write_text(
            "Tool lookup_member takes member_key (string). Returns ok.\n", encoding="utf-8")
    return root


class ReaderTests(unittest.TestCase):
    def test_docx_paragraphs_headings_and_table_rows(self):
        text = read_docx(docx([("Rules", "Heading2"), "Line one."], table=[["a", "b"], ["c", "d"]]))
        self.assertEqual("## Rules\nLine one.\na | b\nc | d", text.strip())

    def test_xlsx_sheets_shared_inline_numbers_and_dates(self):
        text = read_xlsx(xlsx([("Days", [["Date", "Note"], [("date", 46346), ("inline", "closed")], [3, 2.5]])]))
        self.assertEqual("## Sheet: Days\nDate,Note\n2026-11-20,closed\n3,2.5", text.strip())

    def test_pdf_text_is_found_and_the_file_is_attached(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = read_case(make_case(Path(tmp) / "case"), MOCK)
        item = next(doc for doc in case.documents if doc.kind == "pdf")
        self.assertIn("[PDF: policy/letter.pdf", item.text)
        self.assertIn("Promises need a clear yes.", item.text)
        block = case.attachments()[0]
        self.assertEqual(("document", PDF_MEDIA_TYPE, "policy/letter.pdf"),
                         (block["type"], block["source"]["media_type"], block["title"]))
        self.assertTrue(block["source"]["data"])


class FolderTests(unittest.TestCase):
    def test_order_roles_skips_and_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = make_case(Path(tmp) / "case")
            names = [str(path.relative_to(folder)) for path in case_files(folder)]
            case = read_case(folder, MOCK)
        self.assertEqual(["BRIEF.md", "README.md"], names[:2])
        self.assertNotIn(".DS_Store", names)
        self.assertFalse(any("__MACOSX" in name for name in names))
        roles = {doc.name: doc.role for doc in case.documents}
        self.assertEqual("reference", roles["test-customers.csv"])
        self.assertEqual("reference", roles["sample-conversation-1.md"])
        self.assertEqual("policy", roles["policy/calling-rules.docx"])
        self.assertEqual("contract", roles["service-contract.json"])
        self.assertEqual("service-contract.json", case.openapi_source)
        self.assertEqual(MOCK, case.openapi["servers"][0]["url"])
        self.assertTrue(any("image.png" in warning for warning in case.warnings))
        labelled = dict(case.text_documents())
        self.assertTrue(labelled["test-customers.csv"].startswith(REFERENCE_NOTE))
        self.assertIn("09:15", labelled["policy/calling-rules.docx"])
        self.assertIn("2026-11-20", labelled["policy/calendar.xlsx"])

    def test_a_zip_is_unpacked(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = make_case(Path(tmp) / "case")
            archive = Path(tmp) / "case.zip"
            with zipfile.ZipFile(archive, "w") as out:
                for path in folder.rglob("*"):
                    if path.is_file():
                        out.write(path, "case/" + str(path.relative_to(folder)))
                out.writestr("../escape.md", "no")
            unpacked = unpack(archive, Path(tmp) / "out")
            case = read_case(unpacked, MOCK)
            self.assertFalse((Path(tmp) / "escape.md").exists())
        self.assertEqual("case/BRIEF.md", case.documents[0].name)


class DeriveTests(unittest.TestCase):
    def test_a_document_contract_is_derived_checked_and_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = read_case(make_case(Path(tmp) / "case", contract=False), MOCK)
        self.assertIsNone(case.openapi)
        invented = json.loads(json.dumps(CONTRACT))
        invented["paths"]["/lookup_member"]["post"]["requestBody"]["content"]["application/json"]["schema"][
            "properties"]["guessed_field"] = {"type": "string"}
        replies = iter([json.dumps(invented), json.dumps(CONTRACT)])
        seen = []

        def complete(system, messages):
            seen.append(messages[-1]["content"])
            return next(replies)

        document, problems = derive_openapi(case, MOCK, complete)
        self.assertEqual([], problems)
        self.assertEqual(MOCK, document["servers"][0]["url"])
        self.assertIn("guessed_field", seen[-1])  # the repair named the invented field
        self.assertIn("is not written", "\n".join(check_derived(invented, "lookup_member member_key")))


class CliTests(unittest.TestCase):
    def run_build(self, argv, tmp):
        captured = {}

        def fake_extract(documents, document, slot, trace, deadline=None, attachments=None):
            captured.update(documents=documents, document=document, attachments=attachments)
            raise build.BuilderInputError("stop after the inputs (test)")

        with mock.patch.object(build, "_extract", fake_extract), mock.patch("os.getcwd", return_value=tmp):
            code = build.main(["--print", "--slot", "t040-test", *argv])
        return code, captured

    def test_both_forms_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = make_case(Path(tmp) / "case")
            self.assertTrue(build.case_form([str(folder), MOCK]))
            self.assertFalse(build.case_form([str(folder / "BRIEF.md"), str(folder / "service-contract.json")]))
            self.assertFalse(build.case_form([str(folder), "service-contract.json"]))

    def test_the_case_form_reaches_extraction_with_labels_pdf_and_mock(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = make_case(Path(tmp) / "case")
            _, captured = self.run_build([str(folder), MOCK], tmp)
        labels = [name for name, _ in captured["documents"]]
        self.assertEqual(["BRIEF.md", "README.md"], labels[:2])
        self.assertIn("policy/calendar.xlsx", labels)
        self.assertEqual(MOCK, captured["document"]["servers"][0]["url"])
        self.assertEqual(1, len(captured["attachments"]))

    def test_the_old_form_still_works(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            _, captured = self.run_build([str(root / "build-the-builder-v2/briefs/brief-a.md"),
                                          str(root / "build-the-builder-v2/tools/openapi.json")], tmp)
        self.assertEqual(["brief-a.md"], [name for name, _ in captured["documents"]])
        self.assertEqual([], captured["attachments"])


if __name__ == "__main__":
    unittest.main()
