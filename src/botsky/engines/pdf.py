# Componente técnico adaptado de Zhana 7e12d54, pdf_operations.py.
# Origen, decisiones y límites en docs/portados/motores-origen.json.
"""Bounded, isolated PDF assembly and page selection."""

import asyncio
import json
import tempfile
import uuid
from pathlib import Path

from .documents import DocumentEngine, _copy_output, _kind
from .limits import DOCUMENT_INPUT_BYTES, DOCUMENT_PROCESS_SECONDS, PDF_TOTAL_BYTES
from .process import MediaError, run_process

MAX_INPUT = DOCUMENT_INPUT_BYTES
MAX_TOTAL = PDF_TOTAL_BYTES


class PdfOperationError(MediaError):
    pass


class PdfOperations:
    def __init__(self, root: Path) -> None:
        self.engine = DocumentEngine(root)
        self.root = self.engine.root
        self.work = self.engine.work
        self.artifacts = self.engine.artifacts

    async def available(self) -> bool:
        try:
            with tempfile.TemporaryDirectory(prefix="document-", dir=self.work) as temp:
                await run_process(
                    self.engine._sandbox(
                        Path(temp), ["/usr/bin/python3", "-c", "import pypdf,PIL"]
                    ),
                    5,
                )
            return True
        except MediaError, OSError:
            return False

    async def assemble(self, inputs: list[bytes]) -> Path:
        if not 1 <= len(inputs) <= 20:
            raise PdfOperationError("pdf_source_count")
        return await self._execute(inputs, "assemble", "")

    async def extract(self, data: bytes, pages: str) -> Path:
        if not isinstance(pages, str) or not pages or len(pages) > 1000:
            raise PdfOperationError("pdf_invalid_pages")
        return await self._execute([data], "extract", pages)

    async def _execute(self, inputs: list[bytes], action: str, pages: str) -> Path:
        if (
            any(not item or len(item) > MAX_INPUT for item in inputs)
            or sum(map(len, inputs)) > MAX_TOTAL
        ):
            raise PdfOperationError("input_size")
        sources = []
        for index, data in enumerate(inputs):
            try:
                kind = _kind(data)
            except MediaError as exc:
                raise PdfOperationError("unsupported_document") from exc
            if kind not in ("pdf", "png", "jpg", "webp", "tiff") or (
                action == "extract" and kind != "pdf"
            ):
                raise PdfOperationError("unsupported_document")
            sources.append({"name": f"source-{index}.{kind}", "kind": kind})
        try:
            async with asyncio.timeout(DOCUMENT_PROCESS_SECONDS):
                return await self._run(inputs, sources, action, pages)
        except TimeoutError as exc:
            raise PdfOperationError("conversion_timeout") from exc
        except MediaError as exc:
            if isinstance(exc, PdfOperationError):
                raise
            raise PdfOperationError("conversion_failed") from exc

    async def _run(
        self, inputs: list[bytes], sources: list[dict[str, str]], action: str, pages: str
    ) -> Path:
        with tempfile.TemporaryDirectory(prefix="document-", dir=self.work) as temp:
            directory = Path(temp)
            (directory / "tmp").mkdir(mode=0o700)
            for data, item in zip(inputs, sources, strict=True):
                (directory / item["name"]).write_bytes(data)
            (directory / "request.json").write_text(
                json.dumps({"action": action, "sources": sources, "pages": pages})
            )
            script = Path(__file__).with_name("pdf_ops_worker.py")
            (directory / "worker.py").write_bytes(script.read_bytes())
            raw = await self.engine._run(directory, ["/usr/bin/python3", "/work/worker.py"])
            try:
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ValueError
            except (ValueError, UnicodeDecodeError) as exc:
                raise PdfOperationError("conversion_failed") from exc
            code = result.get("error")
            if code:
                allowed = {
                    "invalid_document",
                    "protected_pdf",
                    "pdf_invalid_pages",
                    "document_pages",
                    "document_image_limit",
                    "output_size",
                }
                raise PdfOperationError(code if code in allowed else "conversion_failed")
            output = directory / "result.pdf"
            destination = self.artifacts / f"{uuid.uuid4().hex}.pdf"
            _copy_output(output, destination)
            return destination
