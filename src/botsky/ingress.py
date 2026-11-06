"""Política de frescura. Los metadatos proceden del adaptador, nunca del texto."""

from .contracts import Result


def freshness(incoming, settings, now):
    if (
        incoming.transport != settings.transport
        or incoming.instance != settings.instance
        or incoming.account != settings.account
    ):
        return Result("failed", "wrong_instance", "Entrada fuera de la instancia configurada.")
    if incoming.historical or incoming.source_ms < settings.activation_ms:
        return Result("failed", "before_cutoff", "Mensaje histórico: no se ejecuta.")
    if now - incoming.source_ms > settings.max_age_seconds * 1000:
        return Result("failed", "stale_message", "Mensaje vencido: vuelve a enviar el comando.")
    if incoming.source_ms - now > settings.max_future_seconds * 1000:
        return Result("failed", "future_message", "La hora del mensaje no es admisible.")
    return None
