# Componente técnico adaptado de Zhana 7e12d54, media_edit.py.
# Origen, decisiones y límites en docs/portados/motores-origen.json.
"""Local, bounded media conversions; input files are always borrowed."""

import asyncio
import json
import math
import os
import shutil
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from .limits import MEDIA_DURATION_SECONDS, MEDIA_INPUT_BYTES, MEDIA_PROCESS_SECONDS
from .process import MediaError, run_process

MAX_BYTES = MEDIA_INPUT_BYTES


def _demuxer(data: bytes) -> str:
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "mov"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "matroska"
    if data.startswith(b"OggS"):
        return "ogg"
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "wav"
    if data.startswith(b"fLaC"):
        return "flac"
    if data.startswith(b"ID3"):
        return "mp3"
    if len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0:
        return "aac" if data[1] & 0xF6 == 0xF0 else "mp3"
    raise MediaError("unsupported_media")


def _input_args(source: Path, demuxer: str) -> list[str]:
    return [
        "-protocol_whitelist",
        "file,pipe",
        "-format_whitelist",
        demuxer,
        *(["-enable_drefs", "0", "-use_absolute_path", "0"] if demuxer == "mov" else []),
        "-f",
        demuxer,
        "-i",
        str(source),
    ]


async def _probe(source: Path, demuxer: str) -> dict:
    try:
        result = await run_process(
            [
                "ffprobe",
                "-v",
                "error",
                *_input_args(source, demuxer),
                "-show_entries",
                "format=duration:stream=index,codec_type,codec_name,width,height:stream_tags=language",
                "-of",
                "json",
            ],
            15,
        )
        info = json.loads(result)
        if not isinstance(info.get("streams"), list):
            raise ValueError
        return info
    except (ValueError, TypeError, KeyError, MediaError) as exc:
        raise MediaError("invalid_media") from exc


@dataclass(frozen=True)
class MediaOptions:
    container: str = "mp4"
    quality: str = "standard"
    start_seconds: float = 0
    end_seconds: float | None = None
    subtitle_language: str | None = None

    def __post_init__(self):
        if self.container not in ("mp3", "mp4", "webm", "srt") or self.quality not in (
            "small",
            "standard",
            "high",
        ):
            raise MediaError("invalid_options")
        for value in (self.start_seconds, self.end_seconds):
            if value is not None and (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not 0 <= value <= MEDIA_DURATION_SECONDS
            ):
                raise MediaError("invalid_range")
        if self.end_seconds is not None and self.end_seconds <= self.start_seconds:
            raise MediaError("invalid_range")
        if (
            self.subtitle_language not in (None, "es", "en")
            or self.subtitle_language
            and self.container != "srt"
        ):
            raise MediaError("invalid_options")


class MediaEditor:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.work = self.root / "work"
        self.artifacts = self.root / "artifacts"
        for directory in (self.root, self.work, self.artifacts):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)

    async def available(self) -> bool:
        return all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe", "prlimit"))

    def sweep(self) -> None:
        for path in self.work.glob("edit-*"):
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)

    async def convert(self, data: bytes, options: MediaOptions) -> Path:
        if not data or len(data) > MEDIA_INPUT_BYTES:
            raise MediaError("input_size")
        try:
            async with asyncio.timeout(MEDIA_PROCESS_SECONDS):
                return await self._convert(data, options)
        except TimeoutError:
            raise MediaError("conversion_timeout") from None

    async def convert_file(self, path: Path, options: MediaOptions) -> Path:
        try:
            async with asyncio.timeout(MEDIA_PROCESS_SECONDS):
                return await self._convert(path, options)
        except TimeoutError:
            raise MediaError("conversion_timeout") from None

    async def _convert(self, data: bytes | Path, options: MediaOptions) -> Path:
        max_output = MAX_BYTES
        workspace = Path(tempfile.mkdtemp(prefix="edit-", dir=self.work))
        try:
            source = workspace / "input"
            if isinstance(data, Path):
                try:
                    fd = os.open(data, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                    with os.fdopen(fd, "rb") as stream:
                        info_stat = os.fstat(stream.fileno())
                        if (
                            not stat.S_ISREG(info_stat.st_mode)
                            or not 0 < info_stat.st_size <= MAX_BYTES
                        ):
                            raise MediaError("input_size")
                        demuxer = _demuxer(stream.read(4096))
                        stream.seek(0)
                        with source.open("xb") as target:
                            copied = 0
                            while block := stream.read(192 * 1024):
                                copied += len(block)
                                if copied > MAX_BYTES:
                                    raise MediaError("input_size")
                                target.write(block)
                                await asyncio.sleep(0)
                except OSError as exc:
                    raise MediaError("input_unavailable") from exc
            else:
                demuxer = _demuxer(data)
                source.write_bytes(data)
            source.chmod(0o600)
            info = await _probe(source, demuxer)
            try:
                duration = float(info["format"]["duration"])
                if not math.isfinite(duration) or not 0 < duration <= MEDIA_DURATION_SECONDS:
                    raise ValueError
            except (KeyError, ValueError, TypeError) as exc:
                raise MediaError("duration_limit") from exc
            if options.start_seconds >= duration or (
                options.end_seconds is not None and options.end_seconds > duration
            ):
                raise MediaError("invalid_range")
            streams = info["streams"]
            for stream in streams:
                if stream.get("codec_type") == "video":
                    width, height = stream.get("width"), stream.get("height")
                    if (
                        not isinstance(width, int)
                        or not isinstance(height, int)
                        or min(width, height) < 1
                        or max(width, height) > 4096
                        or width * height > 16_000_000
                    ):
                        raise MediaError("video_dimensions")
            audio = any(s.get("codec_type") == "audio" for s in streams)
            video = any(s.get("codec_type") == "video" for s in streams)
            output = workspace / f"output.{options.container}"
            args = [
                "prlimit",
                f"--fsize={max_output}",
                "--",
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-threads",
                "1",
                "-filter_threads",
                "1",
                *_input_args(source, demuxer),
            ]
            if options.container == "srt":
                if options.start_seconds or options.end_seconds is not None:
                    raise MediaError("subtitle_clip_unsupported")
                aliases = {"es": {"es", "spa"}, "en": {"en", "eng"}}
                subtitle = next(
                    (
                        s
                        for s in streams
                        if s.get("codec_type") == "subtitle"
                        and s.get("codec_name")
                        in {"subrip", "ass", "ssa", "webvtt", "mov_text", "text"}
                        and (
                            options.subtitle_language is None
                            or s.get("tags", {}).get("language", "").lower()
                            in aliases[options.subtitle_language]
                        )
                    ),
                    None,
                )
                if subtitle is None:
                    raise MediaError("subtitles_unavailable")
                args += ["-map", f"0:{subtitle['index']}", "-c:s", "srt", "-f", "srt", str(output)]
            else:
                if options.container == "mp3" and not audio:
                    raise MediaError("audio_unavailable")
                if options.container in {"mp4", "webm"} and not video:
                    raise MediaError("video_unavailable")
                if options.start_seconds:
                    args += ["-ss", str(options.start_seconds)]
                if options.end_seconds is not None:
                    args += ["-t", str(options.end_seconds - options.start_seconds)]
                bitrate = {"small": "64k", "standard": "128k", "high": "192k"}[options.quality]
                if options.container == "mp3":
                    args += ["-map", "0:a:0", "-vn", "-c:a", "libmp3lame", "-b:a", bitrate]
                else:
                    height = 360 if options.quality == "small" else 720
                    width = 640 if options.quality == "small" else 1280
                    args += [
                        "-map",
                        "0:v:0",
                        "-map",
                        "0:a:0?",
                        "-vf",
                        f"scale=w='min({width},iw)':h='min({height},ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
                        "-pix_fmt",
                        "yuv420p",
                    ]
                    if options.container == "mp4":
                        args += [
                            "-c:v",
                            "libx264",
                            "-preset",
                            "veryfast",
                            "-c:a",
                            "aac",
                            "-movflags",
                            "+faststart",
                        ]
                    else:
                        args += [
                            "-c:v",
                            "libvpx-vp9",
                            "-deadline",
                            "realtime",
                            "-cpu-used",
                            "6",
                            "-c:a",
                            "libopus",
                        ]
                    args += [
                        "-crf",
                        {"small": "35", "standard": "28", "high": "22"}[options.quality],
                        "-threads",
                        "1",
                        "-b:a",
                        bitrate,
                    ]
                    if options.quality == "small":
                        args += ["-b:v", "500k"]
                    elif options.container == "webm":
                        args += ["-b:v", "0"]
                args += ["-sn", "-dn", str(output)]
            try:
                await run_process(args, MEDIA_PROCESS_SECONDS)
            except MediaError as exc:
                if output.exists() and output.stat().st_size >= max_output:
                    raise MediaError("output_size") from exc
                if exc.code == "process_timeout":
                    raise
                raise MediaError("conversion_failed") from exc
            if not output.is_file() or not 0 < output.stat().st_size <= max_output:
                raise MediaError("output_size")
            if options.container == "srt":
                try:
                    text = output.read_text(encoding="utf-8")
                    if " --> " not in text:
                        raise ValueError
                except (UnicodeError, ValueError) as exc:
                    raise MediaError("invalid_output") from exc
            else:
                out_demuxer = {"mp3": "mp3", "mp4": "mov", "webm": "matroska"}[options.container]
                out = await _probe(output, out_demuxer)
                try:
                    actual_duration = float(out["format"]["duration"])
                    requested_duration = (options.end_seconds or duration) - options.start_seconds
                    # Container and codec frame boundaries can add a little padding.
                    if (
                        not math.isfinite(actual_duration)
                        or abs(actual_duration - requested_duration) > 0.3
                    ):
                        raise ValueError
                except (KeyError, ValueError, TypeError) as exc:
                    raise MediaError("invalid_output") from exc
                codecs = {s.get("codec_name") for s in out["streams"]}
                expected = {"mp3": {"mp3"}, "mp4": {"h264"}, "webm": {"vp9"}}[options.container]
                if not expected <= codecs or (
                    audio
                    and options.container != "mp3"
                    and ({"mp4": "aac", "webm": "opus"}[options.container] not in codecs)
                ):
                    raise MediaError("invalid_output")
                for s in out["streams"]:
                    if s.get("codec_type") == "video" and (
                        s.get("width", 0) > 1280 or s.get("height", 0) > 720
                    ):
                        raise MediaError("invalid_output")
            output.chmod(0o600)
            artifact = self.artifacts / f"{uuid.uuid4().hex}.{options.container}"
            output.replace(artifact)
            return artifact
        finally:
            shutil.rmtree(workspace, ignore_errors=True)
