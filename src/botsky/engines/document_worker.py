# Componente técnico adaptado de Zhana 7e12d54, document_worker.py.
# Origen, decisiones y límites en docs/portados/motores-origen.json.
"""Bounded, offline document transforms, invoked inside the document sandbox.

Input and output are files in the same sandbox workspace; stdout contains only
machine-readable status codes, never extracted document contents.
"""

import csv
import importlib
import io
import json
import os
import re
import stat
import sys
import zipfile
from pathlib import Path
from typing import NoReturn

INPUT_LIMIT = 100_000_000
OUTPUT_LIMIT = 2_000_000_000
TEXT_LIMIT = 1024 * 1024
CELL_LIMIT = 100_000
PAGE_LIMIT = 500
IMAGE_LIMIT = 2_000_000_000


class DocumentWorkerError(Exception):
    """An intentionally non-sensitive error code."""


def fail(code: str) -> NoReturn:
    raise DocumentWorkerError(code)


def input_file(path: Path) -> io.BytesIO:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= INPUT_LIMIT:
                fail("input_size")
            data = stream.read(INPUT_LIMIT + 1)
        if len(data) > INPUT_LIMIT:
            fail("input_size")
        return io.BytesIO(data)
    except OSError:
        fail("invalid_document")


def safe_text(value: object) -> str:
    value = str(value)
    # Leading whitespace/control characters can hide spreadsheet formula triggers.
    if value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def check_text(total: int, value: object) -> int:
    total += len(str(value).encode("utf-8"))
    if total > TEXT_LIMIT:
        fail("document_text_limit")
    return total


def table_value(value: str | None) -> str | int | float | None:
    if value is None:
        return None
    text = value.strip()
    if (
        re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:[.,][0-9]{1,2})?", text)
        and sum(c.isdigit() for c in text) <= 15
    ):
        return float(text.replace(",", ".")) if "." in text or "," in text else int(text)
    return safe_text(value)


def pdf_to_xlsx(source: io.BytesIO, output: Path) -> list[str]:
    import pdfplumber
    from openpyxl import Workbook

    book = Workbook()
    active = book.active
    if active is None:
        fail("invalid_document")
    book.remove(active)
    count = total = 0
    with pdfplumber.open(source) as pdf:
        if not 1 <= len(pdf.pages) <= PAGE_LIMIT:
            fail("document_pages")
        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                candidates = page.extract_tables(
                    {
                        "vertical_strategy": "text",
                        "horizontal_strategy": "text",
                        "min_words_vertical": 3,
                        "min_words_horizontal": 1,
                    }
                )
                tables = []
                for candidate in candidates:
                    rows = [
                        row
                        for row in candidate
                        if row and any(cell and cell.strip() for cell in row)
                    ]
                    if len(rows) >= 3 and all(
                        sum(bool(cell and cell.strip()) for cell in row) >= 2 for row in rows
                    ):
                        tables.append(rows)
            for table in tables:
                if not table or not any(any(cell for cell in row) for row in table if row):
                    continue
                sheet = book.create_sheet(f"Tabla {len(book.worksheets) + 1}")
                for row in table:
                    for value in row or []:
                        count += 1
                        if count > CELL_LIMIT:
                            fail("document_cell_limit")
                        if value is not None:
                            total = check_text(total, value)
                    values = [table_value(v) for v in (row or [])]
                    sheet.append(values)
                    for cell in sheet[sheet.max_row]:
                        if isinstance(cell.value, str):
                            cell.data_type = "s"
    if not book.worksheets:
        fail("document_no_tables")
    book.save(output)
    return ["pdf_tables"]


def csv_to_xlsx(source: io.BytesIO, output: Path) -> list[str]:
    """Import CSV cells as data, neutralizing formula-like text without losing numbers."""
    from openpyxl import Workbook

    try:
        text = source.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        fail("invalid_document")
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    book = Workbook()
    sheet = book.active
    if sheet is None:
        fail("invalid_document")
    count = total = 0
    for row in csv.reader(io.StringIO(text, newline=""), dialect=dialect):
        values: list[str | int | float | None] = []
        for value in row:
            count += 1
            if count > CELL_LIMIT:
                fail("document_cell_limit")
            total = check_text(total, value)
            values.append(table_value(value))
        sheet.append(values)
        # openpyxl recognizes strings beginning with '=' as formulas unless forced to text.
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    book.save(output)
    return []


def pdf_to_docx(source: io.BytesIO, output: Path) -> list[str]:
    import pdfplumber
    from docx import Document

    document = Document()
    total = 0
    found = False
    with pdfplumber.open(source) as pdf:
        if not 1 <= len(pdf.pages) <= PAGE_LIMIT:
            fail("document_pages")
        for index, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            total = check_text(total, text)
            if index:
                document.add_page_break()
            for line in text.splitlines():
                document.add_paragraph(line)
            found |= bool(text.strip())
    if not found:
        fail("document_no_text")
    document.save(str(output))
    return ["pdf_text_layout_changed"]


def pdf_to_pptx(source: io.BytesIO, output: Path) -> list[str]:
    pdfium = importlib.import_module("pypdfium2")
    from pptx import Presentation

    pdf = pdfium.PdfDocument(source)
    if not 1 <= len(pdf) <= PAGE_LIMIT:
        fail("document_pages")
    presentation = Presentation()
    total = 0
    for page in pdf:
        width, height = page.get_size()
        if width <= 0 or height <= 0:
            fail("invalid_document")
        scale = min(2, 2000 / max(width, height))
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil()
        total += image.width * image.height * 4
        if total > IMAGE_LIMIT:
            fail("document_image_limit")
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        sw, sh = presentation.slide_width, presentation.slide_height
        if sw is None or sh is None:
            fail("invalid_document")
        factor = min(sw / width, sh / height)
        w, h = int(width * factor), int(height * factor)
        slide.shapes.add_picture(buf, (sw - w) // 2, (sh - h) // 2, width=w, height=h)
        page.close()
    presentation.save(str(output))
    return ["pdf_page_images"]


def xlsx_to_csv(source: io.BytesIO, output: Path) -> list[str]:
    from openpyxl import load_workbook

    book = load_workbook(source, read_only=True, data_only=True, keep_links=False)
    if not book.worksheets:
        fail("invalid_document")
    count = total = 0
    files = []
    for index, sheet in enumerate(book.worksheets, 1):
        text = io.StringIO(newline="")
        writer = csv.writer(text, lineterminator="\r\n")
        for row in sheet.iter_rows(values_only=True):
            result: list[object] = []
            for value in row:
                count += 1
                if count > CELL_LIMIT:
                    fail("document_cell_limit")
                if value is None:
                    result.append("")
                elif isinstance(value, str):
                    total = check_text(total, value)
                    result.append(safe_text(value))
                else:
                    total = check_text(total, value)
                    result.append(value)
            writer.writerow(result)
            if text.tell() > OUTPUT_LIMIT:
                fail("output_size")
        files.append((f"hoja-{index}.csv", text.getvalue().encode("utf-8-sig")))
    if len(files) == 1:
        output.write_bytes(files[0][1])
    else:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in files:
                archive.writestr(name, data)
    book.close()
    return ["multiple_sheets_zip"] if len(files) > 1 else []


def office_to_txt(source: io.BytesIO, output: Path, suffix: str) -> list[str]:
    lines: list[str] = []
    total = count = 0

    def add(value: object) -> None:
        nonlocal total, count
        count += 1
        if count > CELL_LIMIT:
            fail("document_cell_limit")
        value = str(value or "")
        total = check_text(total, value)
        lines.append(value)

    if suffix == ".docx":
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = Document(source)
        for block in doc.iter_inner_content():
            if isinstance(block, Paragraph):
                add(block.text)
            elif isinstance(block, Table):
                for row in block.rows:
                    add("\t".join(cell.text for cell in row.cells))
    elif suffix == ".xlsx":
        from openpyxl import load_workbook

        book = load_workbook(source, read_only=True, data_only=True, keep_links=False)
        for sheet in book.worksheets:
            add(sheet.title)
            for row in sheet.iter_rows(values_only=True):
                add("\t".join("" if value is None else str(value) for value in row))
        book.close()
    elif suffix == ".pptx":
        from pptx import Presentation

        presentation = Presentation(source)
        for slide in presentation.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    add(shape.text_frame.text)
                if shape.has_table:
                    for row in shape.table.rows:
                        add("\t".join(cell.text for cell in row.cells))
            if slide.has_notes_slide:
                add(slide.notes_slide.notes_text_frame.text)
    else:
        fail("unsupported_document")
    if not any(line.strip() for line in lines):
        fail("document_no_text")
    output.write_text("\n".join(lines), encoding="utf-8")
    return []


def run(
    action: str, source_path: str | Path, output_path: str | Path
) -> dict[str, str | list[str]]:
    source_path, output_path = Path(source_path), Path(output_path)
    if (
        source_path.parent.resolve() != output_path.parent.resolve()
        or source_path.name == output_path.name
    ):
        fail("invalid_document")
    if output_path.exists() or output_path.is_symlink():
        fail("invalid_document")
    source = input_file(source_path)
    try:
        if action == "pdf_to_xlsx":
            notes = pdf_to_xlsx(source, output_path)
        elif action == "csv_to_xlsx":
            notes = csv_to_xlsx(source, output_path)
        elif action == "pdf_to_docx":
            notes = pdf_to_docx(source, output_path)
        elif action == "pdf_to_pptx":
            notes = pdf_to_pptx(source, output_path)
        elif action == "xlsx_to_csv":
            notes = xlsx_to_csv(source, output_path)
        elif action == "office_to_txt":
            notes = office_to_txt(source, output_path, source_path.suffix.lower())
        else:
            fail("unsupported_conversion")
        if not output_path.is_file() or output_path.stat().st_size > OUTPUT_LIMIT:
            fail("output_size")
        os.chmod(output_path, 0o600)
        return {"output": output_path.name, "notes": notes}
    except Exception:
        output_path.unlink(missing_ok=True)
        raise


def main() -> int:
    try:
        if len(sys.argv) != 4:
            fail("unsupported_conversion")
        result = run(*sys.argv[1:])
        print(json.dumps(result, separators=(",", ":")))
    except DocumentWorkerError as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        return 1
    except MemoryError:
        print('{"error":"document_resources"}')
        return 1
    except Exception:
        print('{"error":"invalid_document"}')
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
