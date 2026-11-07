"""Metadatos locales medidos bajo el supervisor/prlimit; sin acceso a proveedores."""

import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def inspect(path):
    suffix = path.suffix.lower()
    facts = {"bytes": path.stat().st_size, "extension": suffix.removeprefix(".")}
    if suffix == ".pdf":
        from pypdf import PdfReader

        with path.open("rb") as stream:
            pdf = PdfReader(stream, strict=False)
            if pdf.is_encrypted:
                facts["pages_status"] = "encrypted"
            else:
                facts["pages"] = len(pdf.pages)
    elif suffix in (".xlsx", ".ods", ".pptx", ".zip"):
        with zipfile.ZipFile(path) as archive:
            if suffix == ".xlsx":
                name = "xl/workbook.xml"
                if archive.getinfo(name).file_size > 1024 * 1024:
                    return facts
                raw = archive.read(name)
                if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
                    return facts
                facts["sheets"] = len(ET.fromstring(raw).findall(".//{*}sheet"))
            elif suffix == ".pptx":
                facts["slides"] = sum(
                    name.startswith("ppt/slides/slide")
                    and name.endswith(".xml")
                    and "/" not in name[len("ppt/slides/") :]
                    for name in archive.namelist()
                )
            elif suffix == ".zip":
                facts["files"] = sum(not item.is_dir() for item in archive.infolist())
    elif suffix in (".png", ".jpg", ".jpeg", ".webp"):
        from PIL import Image

        with Image.open(path) as image:
            facts["width"], facts["height"] = image.size
    return facts


if __name__ == "__main__":
    try:
        print(json.dumps(inspect(Path(sys.argv[1])), separators=(",", ":")))
    except Exception:
        print('{"status":"unavailable"}')
