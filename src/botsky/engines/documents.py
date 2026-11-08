# Componente técnico adaptado de Zhana 7e12d54, documents.py.
# Origen, decisiones y límites en docs/portados/motores-origen.json.
"""Private, bounded document conversion using local tools."""

import asyncio
import csv
import importlib
import io
import json
import os
import re
import shutil
import stat
import sys
import sysconfig
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

SANDBOX_PYTHON = str(Path(sys.executable).resolve())

from .formats import (
    FORMAT_TARGETS,
    VARIETY_ROUTES,
    normalize_target,
    supports_plan,
)
from .limits import (
    DOCUMENT_INPUT_BYTES,
    DOCUMENT_OUTPUT_BYTES,
    DOCUMENT_PAGES,
    DOCUMENT_PROCESS_SECONDS,
)
from .process import MediaError, run_process

INPUT_LIMIT = DOCUMENT_INPUT_BYTES
OUTPUT_LIMIT = DOCUMENT_OUTPUT_BYTES
EXPANDED_LIMIT = 1_000_000_000


class DocumentError(MediaError):
    """Stable document error code; no file content or tool output is exposed."""


def _read_output(path: Path) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise DocumentError("invalid_document")
            if info.st_size > OUTPUT_LIMIT:
                raise DocumentError("output_size")
            data = stream.read(OUTPUT_LIMIT + 1)
            if len(data) > OUTPUT_LIMIT:
                raise DocumentError("output_size")
            return data
    except OSError as exc:
        raise DocumentError("invalid_document") from exc


def _output_header(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= OUTPUT_LIMIT:
            raise DocumentError("output_size")
        return stream.read(4096)


def _copy_output(source: Path, destination: Path) -> None:
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    created = False
    try:
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= OUTPUT_LIMIT:
                raise DocumentError("output_size")
            out = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            created = True
            with os.fdopen(out, "wb") as target:
                total = 0
                while block := stream.read(192 * 1024):
                    total += len(block)
                    if total > OUTPUT_LIMIT:
                        raise DocumentError("output_size")
                    target.write(block)
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise


def present_document_error(code: str) -> str:
    """Translate stable codes without exposing file contents or subprocess details."""
    messages = {
        "pdf_total_size": "La colección supera el límite total de 2 GB.",
        "source_asset_missing": "No tengo una copia válida del archivo. Vuelve a enviarlo o inicia una colección nueva.",
        "pdf_invalid_pages": "Indica páginas válidas sin repetir, por ejemplo 1-3,5, dentro del PDF.",
        "pdf_source_count": "Puedes unir entre 1 y 20 PDFs o imágenes.",
        "input_size": "El documento debe ocupar como máximo 100 MB y no estar vacío.",
        "output_size": "El resultado supera el límite de envío de 2 GB.",
        "document_pages": "El PDF debe tener entre 1 y 500 páginas.",
        "document_invalid_table": "Necesito una tabla de datos simple y regular para esta conversión.",
        "document_no_tables": "No encontré tablas extraíbles en el PDF.",
        "document_text_limit": "El texto supera el límite de esta conversión.",
        "document_cell_limit": "La hoja supera el límite de celdas de esta conversión.",
        "document_image_limit": "El PDF supera el límite de imágenes de esta conversión.",
        "document_no_text": "No encontré texto extraíble. Si es un escaneo, necesitas OCR.",
        "protected_pdf": "El PDF está protegido; envía una copia sin protección.",
        "invalid_or_protected_pdf": "No pude abrir el PDF; puede estar dañado o protegido.",
        "invalid_document": "El documento está dañado o no se puede abrir.",
        "unsupported_document": "Ese formato no está disponible para esta conversión.",
        "unsupported_target": "Ese formato de salida no está disponible.",
        "unsupported_conversion": "No puedo convertir entre esas familias de documentos.",
        "document_archive_limit": "El documento supera el límite de contenido descomprimido.",
        "document_unsafe": "El documento contiene macros o elementos no admitidos.",
        "document_external_link": "El documento contiene referencias externas no admitidas.",
        "conversion_timeout": "La conversión tardó demasiado; prueba con un documento más simple.",
        "document_resources": "La conversión agotó los recursos disponibles; prueba con un documento más simple.",
        "conversion_failed": "No pude convertir el documento o iniciar el entorno seguro.",
    }
    return messages.get(code, "No pude convertir el documento.")


def _kind(data: bytes) -> str:
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"{\\rtf"):
        return "rtf"
    if data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        try:
            olefile = importlib.import_module("olefile")
            with olefile.OleFileIO(io.BytesIO(data)) as ole:
                names = {"/".join(x).lower() for x in ole.listdir()}
                if any("vba/" in x or "_vba_project" in x or "macros/" in x for x in names):
                    raise DocumentError("document_unsafe")
                for marker, kind in (
                    ("worddocument", "doc"),
                    ("workbook", "xls"),
                    ("book", "xls"),
                    ("powerpoint document", "ppt"),
                ):
                    if marker in names:
                        return kind
        except ImportError as exc:
            raise DocumentError("conversion_failed") from exc
        except OSError as exc:
            raise DocumentError("invalid_document") from exc
        raise DocumentError("unsupported_document")
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > 10_000 or sum(e.file_size for e in entries) > EXPANDED_LIMIT:
                    raise DocumentError("document_archive_limit")
                names = set()
                for entry in entries:
                    name = entry.filename
                    path = PurePosixPath(name)
                    if (
                        name in names
                        or path.is_absolute()
                        or ".." in path.parts
                        or "\\" in name
                        or entry.flag_bits & 1
                    ):
                        raise DocumentError("invalid_document")
                    names.add(name)
                    lower = name.lower()
                    if (
                        "vbaproject" in lower
                        or "macros/" in lower
                        or "scripts/" in lower
                        or "externallinks/" in lower
                    ):
                        raise DocumentError("document_unsafe")
                    if lower.endswith((".rels", ".xml")):
                        content = archive.read(entry)
                        if (
                            re.search(rb'TargetMode\s*=\s*["\']External["\']', content, re.I)
                            or re.search(
                                rb'(?:href|src)\s*=\s*["\'](?:https?|ftp|file):', content, re.I
                            )
                            or b"<!DOCTYPE" in content.upper()
                        ):
                            raise DocumentError("document_external_link")
                if "[Content_Types].xml" in names:
                    types = archive.read("[Content_Types].xml").lower()
                    if b"macroenabled" in types or b"template" in types:
                        raise DocumentError("document_unsafe")
                    for part, suffix in (
                        ("word/document.xml", "docx"),
                        ("xl/workbook.xml", "xlsx"),
                        ("ppt/presentation.xml", "pptx"),
                    ):
                        if part in names:
                            return suffix
                if "mimetype" in names and "content.xml" in names:
                    mime = archive.read("mimetype")
                    for label, suffix in (
                        (b"text", "odt"),
                        (b"spreadsheet", "ods"),
                        (b"presentation", "odp"),
                    ):
                        if mime == b"application/vnd.oasis.opendocument." + label:
                            return suffix
        except (zipfile.BadZipFile, RuntimeError, OSError, ValueError) as exc:
            raise DocumentError("invalid_document") from exc
        raise DocumentError("unsupported_document")
    try:
        text = data.decode("utf-8-sig")
        if "\x00" in text or any(ord(c) < 32 and c not in "\n\r\t\f" for c in text):
            raise ValueError
        stripped = text.lstrip()
        if stripped.startswith(("{", "[")):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, (dict, list)):
                    return "json"
            except ValueError, RecursionError:
                pass
        if re.search(
            r"(?is)^\s*(?:<!doctype\s+html|<html(?:\s|>)|<(?:body|head|p|div|section|table|ul|ol|h[1-6])(?:\s|>))",
            text,
        ):
            return "html"
        if re.search(r"(?m)^\s{0,3}(?:#{1,6}\s+\S|```|(?:[-*+] |\d+\. )\S)", text):
            return "md"
        sample = text[:65536]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            rows = list(csv.reader(io.StringIO(sample), dialect))
            if (
                len(rows) >= 2
                and len(rows[0]) >= 2
                and all(len(row) == len(rows[0]) for row in rows)
            ):
                return "csv"
        except csv.Error:
            pass
        return "txt"
    except UnicodeDecodeError as exc:
        raise DocumentError("unsupported_document") from exc
    except ValueError as exc:
        raise DocumentError("unsupported_document") from exc


class DocumentEngine:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.work = self.root / "work"
        self.artifacts = self.root / "artifacts"
        for directory in (self.root, self.work, self.artifacts):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)

    def _sandbox(self, directory: Path, argv: list[str]) -> list[str]:
        # Only system binaries/data and this job are visible. No host /tmp, home or sockets.
        command = [
            "bwrap",
            "--die-with-parent",
            "--unshare-net",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            "--cap-drop",
            "ALL",
            "--tmpfs",
            "/",
            "--ro-bind",
            "/usr",
            "/usr",
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/bin",
            "/bin",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--dir",
            "/etc",
            "--ro-bind",
            "/etc/ld.so.cache",
            "/etc/ld.so.cache",
            "--ro-bind",
            "/etc/fonts",
            "/etc/fonts",
            "--ro-bind",
            "/etc/libreoffice",
            "/etc/libreoffice",
            "--tmpfs",
            "/tmp",
            "--bind",
            str(directory),
            "/work",
            "--chdir",
            "/work",
            "--clearenv",
            "--setenv",
            "PATH",
            "/usr/bin:/bin",
            "--setenv",
            "HOME",
            "/work",
            "--setenv",
            "TMPDIR",
            "/work/tmp",
            "--setenv",
            "LC_ALL",
            "C",
            "--setenv",
            "SAL_USE_VCLPLUGIN",
            "svp",
        ]
        if Path("/lib64").exists():
            command += ["--ro-bind", "/lib64", "/lib64"]
        if argv and argv[0] in ("/usr/bin/python3", SANDBOX_PYTHON):
            argv = [SANDBOX_PYTHON, *argv[1:]]
            base_prefix = str(Path(sys.base_prefix).resolve())
            if not base_prefix.startswith("/usr"):
                command += ["--ro-bind", base_prefix, base_prefix]
            paths = sysconfig.get_paths()
            purelib = paths["purelib"]
            platlib = paths["platlib"]
            pypath = "/packages"
            command += ["--ro-bind", purelib, "/packages"]
            if platlib != purelib and Path(platlib).exists():
                command += ["--ro-bind", platlib, "/platpackages"]
                pypath = "/packages:/platpackages"
            command += ["--setenv", "PYTHONPATH", pypath]
        return command + ["--", *argv]

    async def available(self) -> bool:
        if not all(
            shutil.which(tool)
            for tool in ("libreoffice", "pdfinfo", "pdftotext", "prlimit", "bwrap")
        ):
            return False
        try:
            with tempfile.TemporaryDirectory(prefix="document-", dir=self.work) as temp:
                await run_process(
                    self._sandbox(
                        Path(temp),
                        [
                            SANDBOX_PYTHON,
                            "-c",
                            "import docx,openpyxl,pptx,pdfplumber,pypdfium2,olefile,PIL,markdown_it;from PIL import Image",
                        ],
                    ),
                    5,
                )
        except MediaError, OSError:
            return False
        return True

    def sweep(self) -> None:
        for path in self.work.glob("document-*"):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)

    async def convert(self, data: bytes, target: str) -> Path:
        if not data or len(data) > INPUT_LIMIT:
            raise DocumentError("input_size")
        target = normalize_target(target)
        if target not in FORMAT_TARGETS:
            raise DocumentError("unsupported_target")
        kind = _kind(data)
        if not supports_plan(kind, target):
            raise DocumentError("unsupported_conversion")
        try:
            async with asyncio.timeout(DOCUMENT_PROCESS_SECONDS):
                return await self._convert(data, kind, target)
        except TimeoutError as exc:
            raise DocumentError("conversion_timeout") from exc
        except MediaError as exc:
            if isinstance(exc, DocumentError):
                raise
            if exc.code == "process_timeout":
                raise DocumentError("conversion_timeout") from exc
            raise DocumentError("conversion_failed") from exc

    async def _run(self, directory: Path, argv: list[str]) -> bytes:
        return await run_process(
            [
                "prlimit",
                f"--fsize={OUTPUT_LIMIT}",
                "--as=4294967296",
                f"--cpu={DOCUMENT_PROCESS_SECONDS}",
                "--",
                *self._sandbox(directory, argv),
            ],
            DOCUMENT_PROCESS_SECONDS,
            allowed_returncodes=(0, 1) if argv[0] in ("/usr/bin/python3", SANDBOX_PYTHON) else (0,),
        )

    async def _pdf_check(self, pdf: Path) -> None:
        try:
            info = (await self._run(pdf.parent, ["pdfinfo", "/work/" + pdf.name])).decode(
                "utf-8", "replace"
            )
        except MediaError as exc:
            if exc.code == "process_timeout":
                raise DocumentError("conversion_timeout") from exc
            raise DocumentError("invalid_or_protected_pdf") from exc
        encrypted = re.search(r"^Encrypted:\s*(\S+)", info, re.M)
        pages = re.search(r"^Pages:\s*(\d+)", info, re.M)
        if not encrypted or encrypted.group(1).lower() != "no":
            raise DocumentError("protected_pdf")
        if not pages or not 0 < int(pages.group(1)) <= DOCUMENT_PAGES:
            raise DocumentError("document_pages")

    async def _convert(self, data: bytes, kind: str, target: str) -> Path:
        with tempfile.TemporaryDirectory(prefix="document-", dir=self.work) as temp:
            directory = Path(temp)
            (directory / "tmp").mkdir(mode=0o700)
            (directory / "out").mkdir(mode=0o700)
            source_kind = (
                "csv"
                if kind == "txt"
                and (FORMAT_TARGETS[target][0] == "spreadsheet" or target == "json")
                else kind
            )
            if (kind == "md" and target != "html") or (
                kind in ("json", "html") and target in ("txt", "pdf")
            ):
                source_kind = "txt"
            source = directory / f"input.{source_kind}"
            source.write_bytes(data)
            source.chmod(0o600)
            profile = directory / "profile"
            user = profile / "user"
            user.mkdir(parents=True, mode=0o700)
            profile.chmod(0o700)
            (user / "registrymodifications.xcu").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="UpdateLinks" oor:op="fuse"><value>0</value></prop></item>
</oor:items>""",
                encoding="utf-8",
            )

            async def office(
                input_path: Path, output_kind: str, *, pdf_import: bool = False
            ) -> Path:
                argv = ["libreoffice", "-env:UserInstallation=file:///work/profile", "--headless"]
                if pdf_import:
                    argv.append("--infilter=writer_pdf_import")
                argv += [
                    "--convert-to",
                    output_kind,
                    "--outdir",
                    "/work/out",
                    "/work/" + input_path.name,
                ]
                await self._run(directory, argv)
                result = directory / "out" / (input_path.stem + "." + output_kind)
                _output_header(result)
                return result

            async def worker(
                action: str, input_path: Path, suffix: str, *, variety: bool = False
            ) -> Path:
                script = Path(__file__).with_name(
                    "variety_worker.py" if variety else "document_worker.py"
                )
                (directory / "worker.py").write_bytes(script.read_bytes())
                output_path = directory / ("result." + suffix)
                result = await self._run(
                    directory,
                    [
                        SANDBOX_PYTHON,
                        "/work/worker.py",
                        action,
                        "/work/" + input_path.name,
                        "/work/" + output_path.name,
                    ],
                )
                try:
                    report = json.loads(result)
                except (ValueError, UnicodeDecodeError) as exc:
                    raise DocumentError("conversion_failed") from exc
                if not isinstance(report, dict):
                    raise DocumentError("conversion_failed")
                error = report.get("error")
                if error:
                    allowed = {
                        "document_invalid_table",
                        "document_pages",
                        "input_size",
                        "unsupported_conversion",
                        "unsupported_document",
                        "document_no_tables",
                        "document_no_text",
                        "document_text_limit",
                        "document_cell_limit",
                        "document_image_limit",
                        "document_resources",
                        "invalid_document",
                        "output_size",
                    }
                    raise DocumentError(error if error in allowed else "conversion_failed")
                _output_header(output_path)
                return output_path

            if kind == "pdf":
                await self._pdf_check(source)
            if kind == target and target != "csv":
                output = source
            elif kind == "csv" and target == "xlsx":
                output = await worker("csv_to_xlsx", source, "xlsx")
            elif (kind, target) in VARIETY_ROUTES or (kind == "txt" and target in ("html", "json")):
                source_kind = ("md" if target == "html" else "csv") if kind == "txt" else kind
                output = await worker(source_kind + "_to_" + target, source, target, variety=True)
                if target == "pdf":
                    await self._pdf_check(output)
            elif target == "txt":
                if kind == "pdf":
                    output = directory / "extracted.txt"
                    await self._run(
                        directory,
                        [
                            "pdftotext",
                            "-enc",
                            "UTF-8",
                            "/work/" + source.name,
                            "/work/extracted.txt",
                        ],
                    )
                    if not _read_output(output).strip():
                        raise DocumentError("document_no_text")
                elif kind in ("txt", "csv", "md", "json", "html"):
                    output = source
                else:
                    family = FORMAT_TARGETS[kind][0]
                    modern = {"writer": "docx", "spreadsheet": "xlsx", "presentation": "pptx"}[
                        family
                    ]
                    input_path = source
                    if kind != modern:
                        produced = await office(source, modern)
                        input_path = directory / ("intermediate." + modern)
                        _copy_output(produced, input_path)
                    output = await worker("office_to_txt", input_path, "txt")
            elif kind == "pdf" and FORMAT_TARGETS[target][0] in (
                "writer",
                "spreadsheet",
                "presentation",
            ):
                family = FORMAT_TARGETS[target][0]
                intermediate_kind = {
                    "writer": "docx",
                    "spreadsheet": "xlsx",
                    "presentation": "pptx",
                }[family]
                output = await worker("pdf_to_" + intermediate_kind, source, intermediate_kind)
                if target == "csv":
                    output = await worker("xlsx_to_csv", output, "csv")
                elif target != intermediate_kind:
                    output = await office(output, target)
            elif target == "csv":
                spreadsheet = source
                if kind != "xlsx":
                    produced = await office(source, "xlsx")
                    spreadsheet = directory / "intermediate.xlsx"
                    _copy_output(produced, spreadsheet)
                output = await worker("xlsx_to_csv", spreadsheet, "csv")
            else:
                output = await office(source, target)
                if target == "pdf":
                    pdf_copy = directory / "intermediate.pdf"
                    _copy_output(output, pdf_copy)
                    await self._pdf_check(pdf_copy)
            output_data = _output_header(output)
            suffix = (
                "zip"
                if target in ("csv", "png", "jpg") and output_data.startswith(b"PK\x03\x04")
                else target
            )
            destination = self.artifacts / f"{uuid.uuid4().hex}.{suffix}"
            _copy_output(output, destination)
            return destination


def detect_document_format(data: bytes) -> str:
    return _kind(data)
