"""Imagen estática, sticker, OCR/QR. Contenido extraído nunca vuelve al router."""

import base64
import binascii
import json
import os
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageSequence

from .image_validation import _image_codec, validate_image
from .process import MediaError, run_process


async def image_source(path: Path):
    data = path.read_bytes()
    if not 0 < len(data) <= 10 * 1024 * 1024:
        raise MediaError("input_size")
    codec = _image_codec(data)
    await validate_image(path, codec)
    return codec


async def add_sticker_metadata(file: Path) -> None:
    payload = json.dumps(
        {
            "sticker-pack-id": "botsky",
            "sticker-pack-name": "Botsky",
            "sticker-pack-publisher": "Botsky",
            "emojis": [],
        }
    ).encode("utf-8")
    header = bytearray(
        [0x49, 0x49, 0x2A, 0, 8, 0, 0, 0, 1, 0, 0x41, 0x57, 7, 0, 0, 0, 0, 0, 0x16, 0, 0, 0]
    )
    header[14:18] = len(payload).to_bytes(4, "little")
    exif_data = bytes(header) + payload

    exif_file = file.with_suffix(".exif")
    exif_file.write_bytes(exif_data)
    try:
        await run_process(
            ["webpmux", "-set", "exif", str(exif_file), str(file), "-o", str(file)],
            15,
        )
    finally:
        exif_file.unlink(missing_ok=True)


async def _convert_animated_webp(source: Path, output: Path) -> Path:
    try:
        with Image.open(source) as im:
            if not getattr(im, "is_animated", False) or getattr(im, "n_frames", 1) <= 1:
                raise MediaError("unsupported_image")
            width, height = im.size
            if width == 512 and height == 512 and source.stat().st_size <= 500000:
                output.write_bytes(source.read_bytes())
                await add_sticker_metadata(output)
                output.chmod(0o600)
                return output

            frames = []
            durations = []
            for frame in ImageSequence.Iterator(im):
                durations.append(frame.info.get("duration", 100))
                f = frame.convert("RGBA")
                f.thumbnail((512, 512), Image.Resampling.LANCZOS)
                canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
                offset = ((512 - f.width) // 2, (512 - f.height) // 2)
                canvas.paste(f, offset)
                frames.append(canvas)
            if not frames:
                raise MediaError("invalid_output")
            for q in (60, 40, 25, 15):
                if output.exists():
                    output.unlink()
                frames[0].save(
                    output,
                    save_all=True,
                    append_images=frames[1:],
                    format="WEBP",
                    loop=0,
                    duration=durations,
                    quality=q,
                    method=6,
                )
                if output.is_file() and 0 < output.stat().st_size <= 500000:
                    await add_sticker_metadata(output)
                    with Image.open(output) as verified:
                        if verified.format == "WEBP" and verified.size == (512, 512):
                            output.chmod(0o600)
                            return output
            raise MediaError("invalid_output")
    except MediaError:
        raise
    except Exception as exc:
        raise MediaError("invalid_image") from exc


async def sticker(path: Path, directory: Path):
    if not path.is_file():
        raise MediaError("input_size")
    size = path.stat().st_size
    if not 0 < size <= 100_000_000:
        raise MediaError("input_size")
    directory.mkdir(parents=True, exist_ok=True)

    is_static = False
    static_codec = None
    if size <= 10 * 1024 * 1024:
        try:
            data = path.read_bytes()
            static_codec = _image_codec(data)
            await validate_image(path, static_codec)
            is_static = True
        except MediaError as exc:
            if exc.code in ("image_dimensions", "invalid_image"):
                raise

    if is_static:
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
                static_codec,
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
        await add_sticker_metadata(output)
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
        except (ValueError, IndexError, KeyError, TypeError):
            raise MediaError("invalid_output") from None
        output.chmod(0o600)
        return output

    try:
        data_head = path.read_bytes()[:12] if size >= 12 else b""
    except OSError:
        raise MediaError("invalid_image")
    if data_head.startswith(b"RIFF") and data_head[8:12] == b"WEBP":
        return await _convert_animated_webp(path, directory / "sticker.webp")

    try:
        probe = await run_process(
            [
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_entries",
                "stream=codec_name,codec_type,width,height",
                "-of",
                "json",
                str(path),
            ],
            15,
        )
        streams = json.loads(probe).get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        if not video_stream:
            raise MediaError("unsupported_media")
        width = int(video_stream["width"])
        height = int(video_stream["height"])
        if width <= 0 or height <= 0:
            raise MediaError("invalid_media")
    except MediaError:
        raise
    except Exception as exc:
        raise MediaError("invalid_media") from exc

    scale = "scale=512:512:force_original_aspect_ratio=decrease,format=rgba,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000"
    profiles = [[60, 15], [40, 12], [25, 10], [15, 8], [10, 6]]
    output = directory / "sticker.webp"
    for quality, fps in profiles:
        if output.exists():
            output.unlink()
        try:
            await run_process(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-y",
                    "-filter_threads",
                    "1",
                    "-i",
                    str(path),
                    "-an",
                    "-vf",
                    f"fps={fps},{scale},format=bgra",
                    "-c:v",
                    "libwebp_anim",
                    "-q:v",
                    str(quality),
                    "-compression_level",
                    "4",
                    "-threads",
                    "2",
                    "-loop",
                    "0",
                    str(output),
                ],
                60,
            )
            if not output.is_file() or output.stat().st_size == 0:
                continue
            await add_sticker_metadata(output)
            if output.stat().st_size <= 500000:
                with Image.open(output) as img:
                    if (
                        img.format == "WEBP"
                        and img.size == (512, 512)
                        and getattr(img, "is_animated", False)
                    ):
                        output.chmod(0o600)
                        return output
        except MediaError:
            continue
    raise MediaError("invalid_output")


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
    text = "\n".join(values)
    return text[:6000], {"symbols": values[:20], "truncated": len(text) > 6000 or len(values) > 20}
