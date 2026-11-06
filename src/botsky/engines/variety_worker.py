# Componente técnico adaptado de Zhana 7e12d54, variety_worker.py.
# Origen, decisiones y límites en docs/portados/motores-origen.json.
"""Offline bounded image, table and text conversions for the document sandbox."""

import csv
import html
import importlib
import io
import json
import math
import os
import re
import stat
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, NoReturn

INPUT_LIMIT = 100_000_000
OUTPUT_LIMIT = 2_000_000_000
TEXT_LIMIT = 1024 * 1024
CELL_LIMIT = 100_000
IMAGE_LIMIT = 2_000_000_000


class WorkerError(Exception):
    pass


def fail(code: str) -> NoReturn:
    raise WorkerError(code)


def read_input(path: Path) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= INPUT_LIMIT:
                fail("input_size")
            data = f.read(INPUT_LIMIT + 1)
        if len(data) > INPUT_LIMIT:
            fail("input_size")
        return data
    except OSError:
        fail("invalid_document")


def raster(source: bytes, origin: str, target: str) -> tuple[bytes, list[str]]:
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = 16_000_000
    image = Image.open(io.BytesIO(source))
    if image.format != {"jpg": "JPEG", "png": "PNG", "webp": "WEBP", "tiff": "TIFF"}[origin]:
        fail("invalid_document")
    if getattr(image, "n_frames", 1) != 1:
        fail("unsupported_document")
    if max(image.size) > 4096 or image.width * image.height > 16_000_000:
        fail("document_image_limit")
    image.load()
    normalized = ImageOps.exif_transpose(image)
    if normalized.mode not in ("RGB", "RGBA"):
        has_alpha = "A" in normalized.getbands() or "transparency" in normalized.info
        normalized = normalized.convert("RGBA" if has_alpha else "RGB")
    if target in ("jpg", "pdf"):
        # White background is deterministic for transparent images.
        rgba = normalized.convert("RGBA")
        background = Image.new("RGB", normalized.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        output_image = background
    else:
        output_image = normalized
    output = io.BytesIO()
    output_image.save(
        output, format={"jpg": "JPEG", "png": "PNG", "webp": "WEBP", "pdf": "PDF"}[target]
    )
    return output.getvalue(), []


def pdf_images(source: bytes, target: str) -> tuple[bytes, list[str]]:
    pdfium = importlib.import_module("pypdfium2")
    pdf = pdfium.PdfDocument(io.BytesIO(source))
    if not 1 <= len(pdf) <= 500:
        fail("document_pages")
    total = 0
    images = []
    for index in range(len(pdf)):
        page = pdf[index]
        width, height = page.get_size()
        if width <= 0 or height <= 0:
            fail("invalid_document")
        image = page.render(scale=min(2, 2000 / max(width, height))).to_pil()
        total += image.width * image.height * 4
        if total > IMAGE_LIMIT:
            fail("document_image_limit")
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="PNG" if target == "png" else "JPEG")
        images.append((f"pagina-{index + 1:03d}.{target}", buf.getvalue()))
        if sum(len(data) for _, data in images) > OUTPUT_LIMIT:
            fail("output_size")
        page.close()
    pdf.close()
    if len(images) == 1:
        return images[0][1], []
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in images:
            archive.writestr(name, data)
    return result.getvalue(), ["multiple_pages_zip"]


def safe(value: object) -> object:
    if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def pairs_unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            fail("document_invalid_table")
        result[key] = value
    return result


def xml_text(value: str) -> str:
    """Represent XML-incompatible code points visibly rather than dropping data."""
    return "".join(
        char
        if ord(char) in (9, 10, 13)
        or 0x20 <= ord(char) <= 0xD7FF
        or 0xE000 <= ord(char) <= 0xFFFD
        or 0x10000 <= ord(char) <= 0x10FFFF
        else f"\\u{ord(char):04X}"
        for char in value
    )


def rows_validate(
    rows: object, *, numeric_headers: bool = False
) -> tuple[list[str], list[list[Any]]]:
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or not rows:
        fail("document_invalid_table")
    if all(isinstance(row, dict) for row in rows):
        headers = list(rows[0])
        if not all(set(row) == set(headers) for row in rows):
            fail("document_invalid_table")
        values = [[row[header] for header in headers] for row in rows]
    elif all(isinstance(row, list) for row in rows):
        headers = rows[0]
        values = rows[1:]
        if not all(len(row) == len(headers) for row in values):
            fail("document_invalid_table")
    else:
        fail("document_invalid_table")
    if numeric_headers:
        headers = [
            str(h)
            if isinstance(h, (int, float))
            and not isinstance(h, bool)
            and (not isinstance(h, float) or math.isfinite(h))
            else h
            for h in headers
        ]
    if (
        not headers
        or any(not isinstance(h, str) or not h.strip() for h in headers)
        or len(set(headers)) != len(headers)
    ):
        fail("document_invalid_table")
    if len(headers) * (len(values) + 1) > CELL_LIMIT:
        fail("document_cell_limit")
    if any(
        not isinstance(v, (str, int, float, bool, type(None)))
        or (isinstance(v, float) and not math.isfinite(v))
        for row in values
        for v in row
    ):
        fail("document_invalid_table")
    if sum(len(str(v).encode("utf-8")) for row in [headers, *values] for v in row) > TEXT_LIMIT:
        fail("document_text_limit")
    return headers, values


def table_convert(source: bytes, origin: str, target: str) -> tuple[bytes, list[str]]:
    notes: list[str] = []
    if origin == "csv":
        text = source.decode("utf-8-sig")
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        headers, values = rows_validate(
            list(csv.reader(io.StringIO(text, newline=""), dialect=dialect))
        )
    elif origin == "json":
        parsed = json.loads(
            source.decode("utf-8-sig"),
            object_pairs_hook=pairs_unique,
            parse_constant=lambda _: fail("document_invalid_table"),
        )
        headers, values = rows_validate(parsed)
    else:
        from openpyxl import load_workbook

        book = load_workbook(io.BytesIO(source), read_only=True, data_only=True, keep_links=False)
        if len(book.worksheets) != 1:
            fail("document_invalid_table")
        raw = []
        count = 0
        for xlsx_row in book.worksheets[0].iter_rows(values_only=True):
            count += len(xlsx_row)
            if count > CELL_LIMIT:
                fail("document_cell_limit")
            raw.append(
                [
                    v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
                    for v in xlsx_row
                ]
            )
        book.close()
        headers, values = rows_validate(raw, numeric_headers=True)
        notes.append("cached_values_only")
    if target == "json":
        data = [dict(zip(headers, row, strict=True)) for row in values]
        return json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8"), notes
    if target == "csv":
        out = io.StringIO(newline="")
        writer = csv.writer(out, lineterminator="\r\n")
        writer.writerow([safe(h) for h in headers])
        writer.writerows([[safe(v) for v in row] for row in values])
        return out.getvalue().encode("utf-8-sig"), notes
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    if sheet is None:
        fail("invalid_document")
    normalized_headers = [xml_text(header) for header in headers]
    if len(set(normalized_headers)) != len(normalized_headers):
        fail("document_invalid_table")
    for row in [normalized_headers, *values]:
        sheet.append([safe(xml_text(v) if isinstance(v, str) else v) for v in row])
    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue(), notes


def docx_markup(source: bytes, target: str) -> tuple[bytes, list[str]]:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(io.BytesIO(source))
    parts = []
    for block in doc.iter_inner_content():
        if isinstance(block, Paragraph):
            text = block.text
            match = re.fullmatch(r"Heading ([1-6])", block.style.name if block.style else "")
            if target == "html":
                tag = f"h{match.group(1)}" if match else "p"
                parts.append(f"<{tag}>{html.escape(text)}</{tag}>")
            else:
                escaped = re.sub(r"([\\`*_{}\[\]()#+.!|>-])", r"\\\1", text)
                parts.append(("#" * int(match.group(1)) + " " if match else "") + escaped)
        elif isinstance(block, Table):
            for row in block.rows:
                cells = [cell.text for cell in row.cells]
                if target == "html":
                    parts.append("<p>" + " | ".join(html.escape(c) for c in cells) + "</p>")
                else:
                    parts.append(" | ".join(c.replace("|", "\\|") for c in cells))
        if sum(len(p.encode("utf-8")) for p in parts) > TEXT_LIMIT:
            fail("document_text_limit")
    result = "\n\n".join(parts)
    if not result.strip():
        fail("document_no_text")
    if target == "html":
        result = (
            '<!doctype html><html><head><meta charset="utf-8"></head><body>\n'
            + result
            + "\n</body></html>"
        )
    return result.encode("utf-8"), ["basic_text_only"]


class SafeHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocked = 0
        self.text = ""
        self.blocks: list[tuple[str, str]] = []
        self.kind = "p"

    def flush(self) -> None:
        text = self.text.strip()
        if text:
            self.blocks.append((self.kind, text))
        self.text = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "iframe", "object", "svg", "template"):
            self.blocked += 1
        elif not self.blocked and tag in (
            "p",
            "div",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "tr",
            "br",
        ):
            self.flush()
            self.kind = tag
        elif not self.blocked and tag in ("td", "th") and self.text:
            self.text += "\t"

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "iframe", "object", "svg", "template") and self.blocked:
            self.blocked -= 1
        elif not self.blocked and tag in (
            "p",
            "div",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "tr",
        ):
            self.flush()
            self.kind = "p"

    def handle_data(self, data: str) -> None:
        if not self.blocked:
            self.text += data


def text_convert(source: bytes, origin: str, target: str) -> tuple[bytes, list[str]]:
    if origin == "docx":
        return docx_markup(source, target)
    text = source.decode("utf-8-sig")
    if len(text.encode("utf-8")) > TEXT_LIMIT:
        fail("document_text_limit")
    if origin == "md":
        markdown = importlib.import_module("markdown_it").MarkdownIt("commonmark", {"html": False})
        markdown.disable(["image"])
        return (
            '<!doctype html><html><head><meta charset="utf-8"></head><body>\n'
            + markdown.render(text)
            + "</body></html>"
        ).encode("utf-8"), ["basic_text_only"]
    from docx import Document

    parser = SafeHTML()
    parser.feed(text)
    parser.flush()
    if not parser.blocks:
        fail("document_no_text")
    doc = Document()
    for kind, value in parser.blocks:
        value = xml_text(value)
        if re.fullmatch(r"h[1-6]", kind):
            doc.add_heading(value, level=int(kind[1]))
        else:
            doc.add_paragraph(value)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue(), ["basic_text_only"]


ROUTES = {
    "png_to_jpg",
    "jpg_to_png",
    "png_to_webp",
    "webp_to_png",
    "jpg_to_webp",
    "webp_to_jpg",
    "png_to_pdf",
    "jpg_to_pdf",
    "webp_to_pdf",
    "tiff_to_pdf",
    "pdf_to_png",
    "pdf_to_jpg",
    "csv_to_json",
    "json_to_csv",
    "json_to_xlsx",
    "xlsx_to_json",
    "docx_to_html",
    "html_to_docx",
    "docx_to_md",
    "md_to_html",
}


def run(
    action: str, source_path: str | Path, output_path: str | Path
) -> dict[str, str | list[str]]:
    source_path, output_path = Path(source_path), Path(output_path)
    if action not in ROUTES:
        fail("unsupported_conversion")
    if (
        source_path.parent.resolve() != output_path.parent.resolve()
        or source_path.name == output_path.name
        or output_path.exists()
        or output_path.is_symlink()
    ):
        fail("invalid_document")
    source = read_input(source_path)
    origin, target = action.split("_to_")
    if origin in ("png", "jpg", "webp", "tiff"):
        data, notes = raster(source, origin, target)
    elif origin == "pdf":
        data, notes = pdf_images(source, target)
    elif origin in ("csv", "json", "xlsx"):
        data, notes = table_convert(source, origin, target)
    else:
        data, notes = text_convert(source, origin, target)
    if not data or len(data) > OUTPUT_LIMIT:
        fail("output_size")
    fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return {"output": output_path.name, "notes": notes}


def main() -> int:
    try:
        if len(sys.argv) != 4:
            fail("unsupported_conversion")
        print(json.dumps(run(*sys.argv[1:]), separators=(",", ":")))
    except WorkerError as exc:
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
