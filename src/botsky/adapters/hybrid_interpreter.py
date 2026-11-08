"""Intérprete híbrido resiliente: Gemini como protagonista con colchón Cloudflare."""

import logging
import time

from .cloudflare_interpreter import InterpreterError

logger = logging.getLogger(__name__)


class HybridInterpreter:
    provider_name = "hybrid"

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
            started = time.monotonic()
            try:
                result = await self.primary.propose(messages, tools)
                self.last_metrics = getattr(self.primary, "last_metrics", None)
                self.active_provider = "primary"
                return result
            except InterpreterError as exc:
                primary_ms = int((time.monotonic() - started) * 1000)
                self.active_provider = "fallback"
                err_str = str(exc)
                if (
                    err_str in ("rate_limited", "service_unavailable", "transport_error", "auth_error")
                    or err_str.startswith("provider_http_")
                ):
                    self.cooldown_until = time.monotonic() + self.cooldown_seconds
                error_code = getattr(exc, "code", err_str)
                http_status = getattr(exc, "http_status", None)
                if http_status is None and err_str.startswith("provider_http_"):
                    try:
                        http_status = int(err_str.split("_")[-1])
                    except ValueError:
                        pass
                logger.warning(
                    "event=interpreter_fallback stage=frontend.decide primary_provider=%s error_code=%s http_status=%s duration_ms=%d",
                    getattr(self.primary, "provider_name", "primary"),
                    error_code,
                    http_status,
                    primary_ms,
                )
            except TimeoutError:
                primary_ms = int((time.monotonic() - started) * 1000)
                self.cooldown_until = time.monotonic() + self.cooldown_seconds
                self.active_provider = "fallback"
                logger.warning(
                    "event=interpreter_fallback stage=frontend.decide primary_provider=%s error_code=timeout http_status=None duration_ms=%d",
                    getattr(self.primary, "provider_name", "primary"),
                    primary_ms,
                )

        self.active_provider = "fallback"
        result = await self.fallback.propose(messages, tools)
        self.last_metrics = getattr(self.fallback, "last_metrics", None)
        return result
