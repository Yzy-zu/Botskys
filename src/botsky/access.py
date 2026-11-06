"""Autoridad backend independiente del contenido de comandos y de Gemini."""

from .contracts import Result


def authorize(permission, context, settings):
    scope = context.scope
    if permission not in {"public", "friend", "owner", "call_authorized"}:
        return Result(
            "failed", "unknown_permission", "La política de esta acción no está disponible."
        )
    if (
        context.instance != settings.instance
        or context.account != settings.account
        or context.epoch != settings.epoch
    ):
        return Result("failed", "stale_scope", "El ámbito o la época ya no están vigentes.")
    if scope.is_group and scope.chat not in settings.allowed_groups:
        return Result("failed", "group_denied", "Este grupo no está habilitado.")
    if permission == "public":
        return None
    if scope.actor != settings.owner and scope.actor not in settings.friends:
        return Result(
            "failed", "actor_denied", "Tu identidad no está autorizada para esta herramienta."
        )
    if permission == "owner" and scope.actor != settings.owner:
        return Result("failed", "owner_required", "Esta acción está reservada al dueño verificado.")
    if permission == "call_authorized" and (
        settings.calls is None or not settings.calls.allows(context)
    ):
        return Result(
            "failed", "call_not_configured", "Las llamadas todavía no están configuradas en Botsky."
        )
    return None
