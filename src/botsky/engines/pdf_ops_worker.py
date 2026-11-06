# Componente técnico adaptado de Zhana 7e12d54, pdf_ops_worker.py.
# Origen, decisiones y límites en docs/portados/motores-origen.json.
"""Isolated PDF assembly and page selection worker."""

import io
import json
import re
import sys
from pathlib import Path
from typing import NoReturn

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter

MAX_PAGES = 500
MAX_OUTPUT = 2_000_000_000


class PdfWorkerError(Exception):
    pass


def fail(code: str) -> NoReturn:
    raise PdfWorkerError(code)


def select_pages(value: str, count: int) -> list[int]:
    if len(value) > 1000 or not re.fullmatch(
        r"\s*\d+\s*(?:-\s*\d+\s*)?(?:,\s*\d+\s*(?:-\s*\d+\s*)?)*", value
    ):
        fail("pdf_invalid_pages")
    indices: list[int] = []
    seen: set[int] = set()
    for part in value.split(","):
        bounds = [int(number.strip()) for number in part.split("-")]
        first, last = bounds[0], bounds[-1]
        if first < 1 or last < first or last > count:
            fail("pdf_invalid_pages")
        for page in range(first, last + 1):
            if page in seen:
                fail("pdf_invalid_pages")
            seen.add(page)
            indices.append(page - 1)
    return indices


def pdf_reader(data: bytes) -> PdfReader:
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            fail("protected_pdf")
        if len(reader.pages) < 1:
            fail("invalid_document")
        return reader
    except PdfWorkerError:
        raise
    except Exception as exc:
        raise PdfWorkerError("invalid_document") from exc


def image_pdf(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if (
                image.format not in ("PNG", "JPEG", "WEBP", "TIFF")
                or getattr(image, "n_frames", 1) != 1
                or image.width > 4096
                or image.height > 4096
                or image.width * image.height > 16_000_000
            ):
                fail("document_image_limit")
            normalized = ImageOps.exif_transpose(image)
            if normalized.mode in ("RGBA", "LA") or "transparency" in normalized.info:
                rgba = normalized.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                normalized = background
            else:
                normalized = normalized.convert("RGB")
            output = io.BytesIO()
            normalized.save(output, format="PDF")
            return output.getvalue()
    except PdfWorkerError:
        raise
    except Exception as exc:
        raise PdfWorkerError("invalid_document") from exc


def run() -> None:
    request = json.loads(Path("/work/request.json").read_text())
    sources = request["sources"]
    writer = PdfWriter()
    count = 0
    for item in sources:
        data = Path("/work/" + item["name"]).read_bytes()
        if item["kind"] != "pdf":
            data = image_pdf(data)
        reader = pdf_reader(data)
        if len(reader.pages) > MAX_PAGES:
            fail("document_pages")
        selection = (
            select_pages(request["pages"], len(reader.pages))
            if request["action"] == "extract"
            else list(range(len(reader.pages)))
        )
        count += len(selection)
        if count > MAX_PAGES:
            fail("document_pages")
        for index in selection:
            writer.add_page(reader.pages[index])
    output = Path("/work/result.pdf")
    with output.open("xb") as stream:
        writer.write(stream)
    if output.stat().st_size > MAX_OUTPUT:
        fail("output_size")


def main() -> int:
    try:
        run()
        print('{"ok":true}')
        return 0
    except PdfWorkerError as exc:
        print(json.dumps({"error": str(exc)}))
    except Exception:
        print('{"error":"invalid_document"}')
    return 1


if __name__ == "__main__":
    sys.exit(main())
