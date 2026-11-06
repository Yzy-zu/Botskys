# Portado técnico de Zhana 7e12d54; contrato Botsky, sin runtime antiguo.
"""Bounded local audio extraction for Groq Whisper."""

import json
import math
import shutil
import sys
import uuid
from array import array
from pathlib import Path

from botsky.adapters.provider_results import audio_result
from botsky.contracts import Result

from ..adapters.whisper import WhisperProvider
from .limits import TRANSCRIPTION_SECONDS
from .process import MediaError, run_process

_MAX_BYTES = 10 * 1024 * 1024


def _format(data: bytes) -> str:
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "wav"
    if data.startswith(b"OggS"):
        return "ogg"
    if data.startswith(b"fLaC"):
        return "flac"
    if data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "mp3"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "mov"
    if data.startswith(b"\x1a\x45\xdf\xa3") and b"\x42\x82\x84webm" in data[:4096]:
        return "matroska"
    raise MediaError("invalid_audio")


class AudioTranscriber:
    def __init__(self, root: Path, whisper: WhisperProvider) -> None:
        self.root = root.resolve()
        self.work = self.root / "work"
        for directory in (self.root, self.work):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
        self.whisper = whisper

    async def available(self) -> bool:
        return bool(
            all(shutil.which(tool) for tool in ("ffmpeg", "ffprobe", "prlimit"))
            and self.whisper.available
        )

    def sweep(self) -> None:
        for path in self.work.iterdir():
            if not path.name.startswith("audio-") or path.is_symlink() or not path.is_dir():
                continue
            identifier = path.name.removeprefix("audio-")
            try:
                if uuid.UUID(hex=identifier).hex == identifier:
                    shutil.rmtree(path)
            except ValueError:
                pass

    async def transcribe(self, data: bytes) -> Result:
        if not data or len(data) > _MAX_BYTES:
            return audio_result(
                "failed", {}, error_code="audio_too_large" if data else "invalid_audio"
            )
        try:
            fmt = _format(data)
        except MediaError:
            return audio_result("failed", {}, error_code="invalid_audio")
        workspace = self.work / f"audio-{uuid.uuid4().hex}"
        workspace.mkdir(mode=0o700)
        try:
            if not await self.available():
                return audio_result("failed", {}, error_code="audio_unavailable")
            source = workspace / "input"
            source.write_bytes(data)
            source.chmod(0o600)
            common = [
                "-protocol_whitelist",
                "file,pipe",
                "-max_pixels",
                "16000000",
                "-threads",
                "1",
                "-f",
                fmt,
            ]
            if fmt == "mov":
                common.extend(["-enable_drefs", "0", "-use_absolute_path", "0"])
            raw = await run_process(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    *common,
                    "-show_entries",
                    "format=duration:stream=codec_type,duration",
                    "-of",
                    "json",
                    str(source),
                ],
                180,
            )
            try:
                info = json.loads(raw)
                streams = info["streams"]
                if not isinstance(streams, list):
                    raise ValueError
                if not any(s.get("codec_type") == "audio" for s in streams):
                    return audio_result("failed", {}, error_code="no_audio")
                durations = [float(info["format"]["duration"])]
                durations += [
                    float(s["duration"]) for s in streams if s.get("duration") not in (None, "N/A")
                ]
                if any(not math.isfinite(d) or d <= 0 for d in durations):
                    raise ValueError
                if max(durations) > TRANSCRIPTION_SECONDS:
                    return audio_result("failed", {}, error_code="audio_too_long")
            except ValueError, TypeError, KeyError, AttributeError:
                return audio_result("failed", {}, error_code="invalid_audio")
            output = workspace / "audio.flac"
            await run_process(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-nostdin",
                    *common,
                    "-i",
                    str(source),
                    "-map",
                    "0:a:0",
                    "-t",
                    str(TRANSCRIPTION_SECONDS + 1),
                    "-vn",
                    "-sn",
                    "-dn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-threads",
                    "1",
                    "-c:a",
                    "flac",
                    "-f",
                    "flac",
                    str(output),
                ],
                180,
            )
            if not output.is_file() or not 0 < output.stat().st_size <= 25_000_000:
                return audio_result("failed", {}, error_code="audio_too_large")
            output.chmod(0o600)
            # Decode at most 1201 seconds; this also verifies the actual decoded duration.
            pcm = workspace / "samples.pcm"
            await run_process(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-nostdin",
                    "-threads",
                    "1",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-f",
                    "flac",
                    "-i",
                    str(output),
                    "-t",
                    str(TRANSCRIPTION_SECONDS + 1),
                    "-f",
                    "s16le",
                    "-acodec",
                    "pcm_s16le",
                    str(pcm),
                ],
                180,
            )
            size = pcm.stat().st_size
            if size > TRANSCRIPTION_SECONDS * 16000 * 2:
                return audio_result("failed", {}, error_code="audio_too_long")
            if not size or size % 2:
                return audio_result("failed", {}, error_code="invalid_audio")
            samples = array("h")
            samples.frombytes(pcm.read_bytes())
            if sys.byteorder != "little":
                samples.byteswap()
            # -50 dBFS peak means all samples have magnitude at most 103.
            if all(abs(sample) <= 103 for sample in samples):
                return audio_result("empty", {"text": "", "truncated": False})
            return await self.whisper.transcribe(output)
        except MediaError as exc:
            code = {
                "process_unavailable": "audio_unavailable",
                "process_timeout": "audio_timeout",
            }.get(exc.code, "invalid_audio")
            return audio_result("failed", {}, error_code=code)
        except OSError, ValueError, UnicodeError:
            return audio_result("failed", {}, error_code="audio_failed")
        finally:
            shutil.rmtree(workspace, ignore_errors=True)
