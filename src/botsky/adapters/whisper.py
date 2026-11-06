# Portado técnico de Zhana 7e12d54; contrato Botsky, sin runtime antiguo.
"""Bounded Groq Whisper transcription; the caller owns the HTTP client."""

import asyncio
import json
import math
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from botsky.adapters.provider_results import audio_result
from botsky.contracts import Result


class WhisperProvider:
    def __init__(
        self, client: httpx.AsyncClient, key: str, model: str = "whisper-large-v3-turbo"
    ) -> None:
        self._client = client
        self._key = key
        self._model = model
        self._cooldown_until = 0.0

    @property
    def available(self) -> bool:
        return bool(self._key.strip())

    async def transcribe(self, path: Path) -> Result:
        if not self.available:
            return audio_result("failed", {}, error_code="audio_unavailable")
        if time.monotonic() < self._cooldown_until:
            return audio_result("failed", {}, error_code="rate_limited")
        try:
            async with asyncio.timeout(300):
                with path.open("rb") as audio:
                    async with self._client.stream(
                        "POST",
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self._key}"},
                        data={
                            "model": self._model,
                            "response_format": "verbose_json",
                            "temperature": "0",
                        },
                        files={"file": ("audio.flac", audio, "audio/flac")},
                        timeout=300,
                        follow_redirects=False,
                    ) as response:
                        if response.status_code == 429:
                            value = response.headers.get("retry-after", "60")
                            try:
                                delay = float(value)
                                if not math.isfinite(delay):
                                    raise ValueError
                            except ValueError:
                                try:
                                    delay = (
                                        parsedate_to_datetime(value) - datetime.now(UTC)
                                    ).total_seconds()
                                except ValueError, TypeError, OverflowError:
                                    delay = 60
                            self._cooldown_until = max(
                                self._cooldown_until, time.monotonic() + max(0, delay)
                            )
                            return audio_result("failed", {}, error_code="rate_limited")
                        if response.status_code >= 500:
                            return audio_result("failed", {}, error_code="provider_unavailable")
                        if response.status_code != 200:
                            return audio_result("failed", {}, error_code="provider_error")
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > 2 * 1024 * 1024:
                                return audio_result("failed", {}, error_code="invalid_response")
                            body.extend(chunk)
            result = json.loads(body)
            value = result["text"]
            if not isinstance(value, str):
                raise ValueError
            if len(value) > 100000:
                return audio_result("failed", {}, error_code="audio_too_large")
            segments = result.get("segments")
            # Only discard text when every returned segment explicitly indicates no speech.
            no_speech = (
                isinstance(segments, list)
                and bool(segments)
                and all(
                    isinstance(s, dict)
                    and isinstance(s.get("no_speech_prob"), (float, int))
                    and not isinstance(s["no_speech_prob"], bool)
                    and s["no_speech_prob"] >= 0.95
                    for s in segments
                )
            )
            if not value.strip() or no_speech:
                return audio_result("empty", {"text": "", "truncated": False})
            return audio_result("ok", {"text": value, "truncated": False})
        except httpx.TransportError, TimeoutError, OSError:
            return audio_result("failed", {}, error_code="provider_unavailable")
        except ValueError, TypeError, KeyError, UnicodeError:
            return audio_result("failed", {}, error_code="invalid_response")
