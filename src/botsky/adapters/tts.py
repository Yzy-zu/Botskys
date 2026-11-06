"""Edge TTS conserva proveedor/perfiles comprobados; activación explícita y binario propio."""

import sys
from pathlib import Path

from ..engines.process import MediaError


class EdgeTTS:
    def __init__(self, *, enabled=False, edge_binary=None):
        self.enabled = enabled
        self.edge_binary = str(edge_binary or Path(sys.executable).parent / "edge-tts")

    async def synthesize(self, text, voice, effect, directory):
        if not self.enabled:
            raise MediaError("tts_not_configured")
        from ..engines.speech import SpeechEngine

        return await SpeechEngine(directory / "speech", self.edge_binary).synthesize(
            text, voice, effect
        )
