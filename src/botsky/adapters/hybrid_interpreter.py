"""Intérprete híbrido resiliente: Gemini como protagonista con colchón Cloudflare."""

import logging
import time

from .cloudflare_interpreter import InterpreterError

logger = logging.getLogger(__name__)


class HybridInterpreter:
    def __init__(self, primary, fallback, *, cooldown_seconds: int = 60):
        self.primary = primary
        self.fallback = fallback
        self.cooldown_seconds = max(5, int(cooldown_seconds))
        self.cooldown_until = 0.0
        self.last_metrics = None
        self.active_provider = "primary"

    async def propose(self, messages, tools):
        now = time.monotonic()
        if now >= self.cooldown_until:
            try:
                result = await self.primary.propose(messages, tools)
                self.last_metrics = getattr(self.primary, "last_metrics", None)
                self.active_provider = "primary"
                return result
            except InterpreterError as exc:
                err_str = str(exc)
                if (
                    err_str in ("rate_limited", "service_unavailable", "transport_error", "auth_error")
                    or err_str.startswith("provider_http_")
                ):
                    self.cooldown_until = now + self.cooldown_seconds
                logger.warning(
                    "Intérprete primario (Gemini) falló con '%s'; recurriendo a respaldo Cloudflare.",
                    exc,
                )
            except TimeoutError:
                self.cooldown_until = now + self.cooldown_seconds
                logger.warning(
                    "Intérprete primario (Gemini) agotó tiempo de espera; recurriendo a respaldo Cloudflare.",
                )

        result = await self.fallback.propose(messages, tools)
        self.last_metrics = getattr(self.fallback, "last_metrics", None)
        self.active_provider = "fallback"
        return result
