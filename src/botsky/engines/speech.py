# Motor técnico adaptado de Zhana 7e12d54; sin Args ni modelo antiguo.
"""Explicit Edge TTS profiles and bounded, private speech synthesis."""

import asyncio
import json
import math
import os
import shutil
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from .process import MediaError, run_process

MAX_BYTES = 10 * 1024 * 1024
Voice = Literal[
    "botsky",
    "mexicana",
    "colombiana",
    "argentina",
    "espanola",
    "mexicano",
    "colombiano",
    "argentino",
    "espanol",
    "chileno",
    "venezolano",
    "peruano",
    "anime",
]
Effect = Literal["none", "robot", "radio", "ardilla", "demonio"]


@dataclass(frozen=True)
class VoiceProfile:
    voice: str
    rate: str = "+0%"
    pitch: str = "+0Hz"


PROFILES = MappingProxyType(
    {
        "botsky": VoiceProfile("es-MX-DaliaNeural"),
        "mexicana": VoiceProfile("es-MX-DaliaNeural"),
        "colombiana": VoiceProfile("es-CO-SalomeNeural"),
        "argentina": VoiceProfile("es-AR-ElenaNeural"),
        "espanola": VoiceProfile("es-ES-ElviraNeural"),
        "mexicano": VoiceProfile("es-MX-JorgeNeural"),
        "colombiano": VoiceProfile("es-CO-GonzaloNeural"),
        "argentino": VoiceProfile("es-AR-TomasNeural"),
        "espanol": VoiceProfile("es-ES-AlvaroNeural"),
        "chileno": VoiceProfile("es-CL-LorenzoNeural"),
        "venezolano": VoiceProfile("es-VE-SebastianNeural"),
        "peruano": VoiceProfile("es-PE-AlexNeural"),
        "anime": VoiceProfile("es-ES-ElviraNeural", "+10%", "+16Hz"),
    }
)

# Filters are fixed by code, never supplied by the model or user.
EFFECTS = MappingProxyType(
    {
        "none": "anull",
        "robot": "afftfilt=real='hypot(re,im)':imag=0",
        "radio": "highpass=f=300,lowpass=f=3400,acrusher=bits=8:mix=0.2",
        "ardilla": "asetrate=48000*1.3,aresample=48000,atempo=0.76923077",
        "demonio": "asetrate=48000*0.75,aresample=48000,atempo=1.33333333",
    }
)


class SpeechError(MediaError):
    """Stable error code without provider output or user content."""


class SpeechEngine:
    def __init__(self, root: Path, edge_binary: str = "edge-tts") -> None:
        self.edge_binary = edge_binary
        self.root = Path(root).resolve()
        self.work = self.root / "work"
        self.artifacts = self.root / "artifacts"
        for directory in (self.root, self.work, self.artifacts):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)

    async def available(self) -> bool:
        return all(
            shutil.which(tool) for tool in (self.edge_binary, "ffmpeg", "ffprobe", "prlimit")
        )

    async def synthesize(self, text: str, voice: str = "botsky", effect: str = "none") -> Path:
        if voice not in PROFILES or effect not in EFFECTS:
            raise SpeechError("profile_unavailable")
        if not await self.available():
            raise SpeechError("speech_unavailable")
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            raise SpeechError("speech_failed")
        if any(unicodedata.category(c) == "Cc" and c not in "\n\r\t" for c in text):
            raise SpeechError("speech_failed")
        ident = uuid.uuid4().hex
        work = self.work / f"speech-{ident}"
        artifact = self.artifacts / f"{ident}.ogg"
        work.mkdir(mode=0o700)
        text_file, mp3, ogg = work / "text.txt", work / "source.mp3", work / "result.ogg"
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        profile = PROFILES[voice]
        try:
            fd = os.open(text_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as out:
                out.write(text)
            async with asyncio.timeout(120):
                await run_process(
                    [
                        "prlimit",
                        f"--fsize={MAX_BYTES}",
                        "--",
                        self.edge_binary,
                        "--file",
                        str(text_file),
                        "--voice",
                        profile.voice,
                        "--rate",
                        profile.rate,
                        "--pitch",
                        profile.pitch,
                        "--write-media",
                        str(mp3),
                    ],
                    90,
                    env=env,
                )
                self._size(mp3)
                await self._duration(mp3, "mp3", env)
                await run_process(
                    [
                        "prlimit",
                        f"--fsize={MAX_BYTES}",
                        "--",
                        "ffmpeg",
                        "-nostdin",
                        "-v",
                        "error",
                        "-protocol_whitelist",
                        "file,pipe",
                        "-f",
                        "mp3",
                        "-i",
                        str(mp3),
                        "-vn",
                        "-map_metadata",
                        "-1",
                        "-af",
                        EFFECTS[effect],
                        "-c:a",
                        "libopus",
                        "-ar",
                        "48000",
                        "-ac",
                        "1",
                        "-b:a",
                        "32k",
                        "-f",
                        "ogg",
                        str(ogg),
                    ],
                    120,
                    env=env,
                )
                self._size(ogg)
                await self._duration(ogg, "ogg", env)
                ogg.chmod(0o600)
                os.replace(ogg, artifact)
            return artifact
        except TimeoutError as exc:
            raise SpeechError("speech_timeout") from exc
        except MediaError as exc:
            if isinstance(exc, SpeechError):
                raise
            if any(p.exists() and p.stat().st_size >= MAX_BYTES for p in (mp3, ogg)):
                raise SpeechError("output_size") from exc
            code = "speech_timeout" if exc.code == "process_timeout" else "speech_failed"
            raise SpeechError(code) from exc
        except OSError as exc:
            raise SpeechError("speech_failed") from exc
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @staticmethod
    def _size(path: Path) -> None:
        size = path.stat().st_size
        if size > MAX_BYTES:
            raise SpeechError("output_size")
        if size <= 0:
            raise SpeechError("speech_failed")

    async def _duration(self, path: Path, demuxer: str, env: dict[str, str]) -> None:
        result = await run_process(
            [
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-f",
                demuxer,
                "-i",
                str(path),
                "-show_entries",
                "format=duration",
                "-of",
                "json",
            ],
            15,
            env=env,
        )
        try:
            duration = float(json.loads(result)["format"]["duration"])
        except (ValueError, TypeError, KeyError) as exc:
            raise SpeechError("speech_failed") from exc
        if not math.isfinite(duration) or duration <= 0:
            raise SpeechError("speech_failed")
        if duration > 600:
            raise SpeechError("speech_too_long")
