"""Imagen estática, sticker, OCR/QR. Contenido extraído nunca vuelve al router."""

import base64
import binascii
import json
import os
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from .image_validation import _image_codec, validate_image
from .process import MediaError, run_process


async def image_source(path: Path):
    data = path.read_bytes()
    if not 0 < len(data) <= 10 * 1024 * 1024:
        raise MediaError("input_size")
    codec = _image_codec(data)
    await validate_image(path, codec)
    return codec


async def sticker(path: Path, directory: Path):
    codec = await image_source(path)
    output = directory / "sticker.webp"
    await run_process(
        [
            "prlimit",
            "--fsize=102400",
            "--",
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-protocol_whitelist",
            "file,pipe",
            "-max_pixels",
            "16000000",
            "-threads",
            "1",
            "-filter_threads",
            "1",
            "-f",
            "image2",
            "-c:v",
            codec,
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            "scale=512:512:force_original_aspect_ratio=decrease,format=rgba,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000",
            "-c:v",
            "libwebp",
            "-threads",
            "1",
            "-quality",
            "75",
            "-f",
            "webp",
            str(output),
        ],
        30,
    )
    if not output.is_file() or not 0 < output.stat().st_size <= 102400:
        raise MediaError("invalid_output")
    raw = await run_process(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-f",
            "image2",
            "-show_entries",
            "stream=width,height,codec_name",
            "-of",
            "json",
            str(output),
        ],
        15,
    )
    try:
        info = json.loads(raw)["streams"][0]
        if (info["codec_name"], info["width"], info["height"]) != ("webp", 512, 512):
            raise ValueError
    except ValueError, IndexError, KeyError, TypeError:
        raise MediaError("invalid_output") from None
    output.chmod(0o600)
    return output


def printable(text):
    return "".join(
        c for c in text if not unicodedata.category(c).startswith("C") or c in "\n\t"
    ).strip()


async def read_image(path: Path, mode: str, directory: Path):
    codec = await image_source(path)
    normalized = directory / "normalized.png"
    await run_process(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-protocol_whitelist",
            "file,pipe",
            "-max_pixels",
            "16000000",
            "-threads",
            "1",
            "-filter_threads",
            "1",
            "-f",
            "image2",
            "-c:v",
            codec,
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-c:v",
            "png",
            "-threads",
            "1",
            "-f",
            "image2",
            str(normalized),
        ],
        30,
    )
    if mode == "text":
        languages = (await run_process(["tesseract", "--list-langs"], 10)).decode().splitlines()
        if not {"spa", "eng"} <= set(languages):
            raise MediaError("ocr_languages_unavailable")
        raw = await run_process(
            ["tesseract", str(normalized), "stdout", "-l", "spa+eng", "--psm", "3"],
            30,
            env=dict(os.environ, OMP_THREAD_LIMIT="1"),
        )
        text = printable(raw.decode("utf-8"))
        return text[:6000], {"truncated": len(text) > 6000}
    if mode != "qr":
        raise MediaError("invalid_image_mode")
    raw = await run_process(
        ["zbarimg", "--quiet", "--xml", str(normalized)], 20, allowed_returncodes=(0, 4)
    )
    if not raw.strip():
        return "", {"symbols": []}
    try:
        if len(raw) > 65536 or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            raise ValueError
        document = ET.fromstring(raw)
        values = []
        for node in document.iter("{http://zbar.sourceforge.net/2008/barcode}symbol"):
            if node.attrib.get("type") != "QR-Code":
                continue
            data = node.find("{http://zbar.sourceforge.net/2008/barcode}data")
            if data is None:
                continue
            text = data.text or ""
            if data.attrib.get("format") == "base64":
                text = base64.b64decode(text, validate=True).decode("utf-8")
            text = printable(text)
            if text and text not in values:
                values.append(text)
    except ValueError, ET.ParseError, binascii.Error, UnicodeError:
        raise MediaError("invalid_qr_output") from None
    return "\n".join(values)[:6000], {"symbols": values[:20]}
