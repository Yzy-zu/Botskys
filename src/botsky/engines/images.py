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


def _animated_webp_durations(source: Path) -> list[int]:
    """Read true frame timings from RIFF ANMF; Pillow omits these on some versions."""
    data = source.read_bytes()
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise MediaError("invalid_image")
    if int.from_bytes(data[4:8], "little") + 8 != len(data):
        raise MediaError("invalid_image")
    durations = []
    pos = 12
    while pos + 8 <= len(data):
        kind = data[pos : pos + 4]
        size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        begin = pos + 8
        end = begin + size
        if end > len(data):
            raise MediaError("invalid_image")
        if kind == b"ANMF":
            if size < 16 or len(durations) >= 600:
                raise MediaError("invalid_image")
            durations.append(int.from_bytes(data[begin + 12 : begin + 15], "little"))
        pos = end + (size & 1)
    if pos != len(data) or len(durations) < 2:
        raise MediaError("invalid_image")
    return durations


async def _convert_animated_webp(source: Path, output: Path) -> Path:
    try:
        timings = _animated_webp_durations(source)
        with Image.open(source) as im:
            if not getattr(im, "is_animated", False) or im.n_frames != len(timings):
                raise MediaError("unsupported_image")
            width, height = im.size
            # Avoid a second lossy encode for an already compliant sticker.
            if (
                (width, height) == (512, 512)
                and source.stat().st_size <= 950000
                and all(ms >= 8 for ms in timings)
                and sum(timings) <= 10000
            ):
                output.write_bytes(source.read_bytes())
                await add_sticker_metadata(output)
                if output.stat().st_size <= 950000:
                    output.chmod(0o600)
                    return output

            frames = []
            durations = []
            elapsed_ms = 0
            last_frame_ms = 0
            # Limit to 10 seconds and approximately 12fps of frames kept in memory.
            for frame, frame_ms in zip(ImageSequence.Iterator(im), timings, strict=True):
                if elapsed_ms >= 10000:
                    break
                if not frames or elapsed_ms - last_frame_ms >= 80:
                    if durations:
                        durations[-1] = elapsed_ms - last_frame_ms
                    picture = frame.convert("RGBA")
                    picture.thumbnail((512, 512), Image.Resampling.LANCZOS)
                    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
                    canvas.paste(picture, ((512 - picture.width) // 2, (512 - picture.height) // 2))
                    frames.append(canvas)
                    durations.append(0)
                    last_frame_ms = elapsed_ms
                elapsed_ms += min(max(20, frame_ms), 10000 - elapsed_ms)
            if len(frames) < 2:
                raise MediaError("invalid_output")
            durations[-1] = elapsed_ms - last_frame_ms
            for quality in (88, 82, 76, 70):
                output.unlink(missing_ok=True)
                frames[0].save(
                    output,
                    save_all=True,
                    append_images=frames[1:],
                    format="WEBP",
                    loop=0,
                    duration=durations,
                    quality=quality,
                    method=6,
                )
                if output.is_file() and 0 < output.stat().st_size <= 950000:
                    await add_sticker_metadata(output)
                    if output.stat().st_size <= 950000:
                        with Image.open(output) as verified:
                            if (
                                verified.format == "WEBP"
                                and verified.size == (512, 512)
                                and getattr(verified, "is_animated", False)
                            ):
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
        # Try a high-quality still first. Include EXIF in the final 100KiB bound.
        for quality in (90, 82, 74):
            output.unlink(missing_ok=True)
            try:
                await run_process(
                    [
                        "prlimit",
                        "--fsize=1048576",
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
                        "scale=512:512:force_original_aspect_ratio=decrease:flags=lanczos,format=rgba,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000,setsar=1",
                        "-c:v",
                        "libwebp",
                        "-preset",
                        "picture",
                        "-threads",
                        "1",
                        "-quality",
                        str(quality),
                        "-f",
                        "webp",
                        str(output),
                    ],
                    30,
                )
            except MediaError:
                continue
            if output.is_file() and 0 < output.stat().st_size <= 102400:
                await add_sticker_metadata(output)
                if output.stat().st_size <= 102400:
                    break
        else:
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
        except (ValueError, IndexError, KeyError, TypeError):
            raise MediaError("invalid_output") from None
        output.chmod(0o600)
        return output

    try:
        with path.open("rb") as source_file:
            data_head = source_file.read(12)
    except OSError:
        raise MediaError("invalid_image")
    if data_head.startswith(b"RIFF") and data_head[8:12] == b"WEBP":
        if size > 10 * 1024 * 1024:
            raise MediaError("input_size")
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
                "stream=codec_name,codec_type,width,height,duration:format=duration",
                "-of",
                "json",
                str(path),
            ],
            15,
        )
        probe_data = json.loads(probe)
        streams = probe_data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        if not video_stream:
            raise MediaError("unsupported_media")
        width = int(video_stream["width"])
        height = int(video_stream["height"])
        if width <= 0 or height <= 0:
            raise MediaError("invalid_media")
        duration = 0.0
        try:
            duration = float(probe_data.get("format", {}).get("duration", 0))
        except (ValueError, TypeError):
            duration = 0.0
        if duration <= 0.0:
            try:
                duration = float(video_stream.get("duration", 0))
            except (ValueError, TypeError):
                duration = 0.0
    except MediaError:
        raise
    except Exception as exc:
        raise MediaError("invalid_media") from exc

    effective_duration = min(duration, 10.0) if duration > 0 else 10.0

    # Debanding with blur destroyed high-frequency detail in every clip.
    scale = (
        "scale=512:512:force_original_aspect_ratio=decrease:flags=lanczos,"
        "format=rgba,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000,setsar=1,format=yuva420p"
    )
    # Keep visual quality high. Shorten a difficult clip before heavily
    # quantizing all its frames to squeeze ten seconds below the byte limit.
    profile_candidates = (
        (10, 88, 12),
        (10, 82, 10),
        (10, 76, 8),
        (6, 88, 12),
        (6, 82, 10),
        (4, 88, 12),
        (4, 82, 10),
        (3, 76, 8),
    )
    profiles = []
    for max_seconds, quality, fps in profile_candidates:
        candidate = (min(effective_duration, float(max_seconds)), quality, fps)
        if candidate not in profiles:
            profiles.append(candidate)
    output = directory / "sticker.webp"
    for clip_seconds, quality, fps in profiles:
        if output.exists():
            output.unlink()
        try:
            await run_process(
                [
                    "prlimit",
                    "--fsize=2000000",
                    "--",
                    "ffmpeg",
                    "-v",
                    "error",
                    "-nostdin",
                    "-y",
                    "-filter_threads",
                    "1",
                    "-i",
                    str(path),
                    "-t",
                    str(clip_seconds),
                    "-an",
                    "-vf",
                    f"fps={fps},{scale}",
                    "-c:v",
                    "libwebp_anim",
                    "-preset",
                    "picture",
                    "-q:v",
                    str(quality),
                    "-compression_level",
                    "6",
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
            if output.stat().st_size <= 950000:
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
