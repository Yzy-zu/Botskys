# Componente técnico adaptado de Zhana 7e12d54, media.py.
# Origen, decisiones y límites en docs/portados/motores-origen.json.
import json
from pathlib import Path

from .process import MediaError, run_process


def _image_codec(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        # Reject APNG, including malformed chunk layouts.
        pos = 8
        while pos + 12 <= len(data):
            size = int.from_bytes(data[pos : pos + 4], "big")
            end = pos + 12 + size
            if end > len(data):
                raise MediaError("invalid_image")
            kind = data[pos + 4 : pos + 8]
            if kind == b"acTL":
                raise MediaError("unsupported_image")
            pos = end
            if kind == b"IEND":
                return "png"
        raise MediaError("invalid_image")
    if data.startswith(b"\xff\xd8\xff"):
        return "mjpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        end = int.from_bytes(data[4:8], "little") + 8
        if end != len(data):
            raise MediaError("invalid_image")
        pos = 12
        while pos + 8 <= end:
            kind = data[pos : pos + 4]
            size = int.from_bytes(data[pos + 4 : pos + 8], "little")
            pos += 8 + size + (size & 1)
            if pos > end:
                raise MediaError("invalid_image")
            if kind in (b"ANIM", b"ANMF"):
                raise MediaError("unsupported_image")
        if pos != end:
            raise MediaError("invalid_image")
        return "webp"
    raise MediaError("unsupported_image")


async def validate_image(source: Path, codec: str) -> None:
    probe = await run_process(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-max_pixels",
            "16000000",
            "-threads",
            "1",
            "-f",
            "mjpeg" if codec == "mjpeg" else "image2",
            "-count_frames",
            "-show_entries",
            "stream=width,height,codec_name,nb_read_frames",
            "-of",
            "json",
            str(source),
        ],
        15,
    )
    try:
        stream = json.loads(probe)["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
        if stream["codec_name"] != codec:
            raise ValueError
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise MediaError("invalid_image") from exc
    if width < 1 or height < 1:
        raise MediaError("invalid_image")
    if max(width, height) > 4096 or width * height > 16_000_000:
        raise MediaError("image_dimensions")
    try:
        frames = int(stream["nb_read_frames"])
    except (KeyError, ValueError, TypeError) as exc:
        raise MediaError("invalid_image") from exc
    if frames < 1:
        raise MediaError("invalid_image")
    if frames != 1:
        raise MediaError("unsupported_image")
