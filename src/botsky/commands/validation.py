"""Restricciones cruzadas compartidas por comandos y peticiones nativas."""
import unicodedata

def validate_arguments(spec, args):
    from .router import CommandError
    def reject(field, reason):
        raise CommandError("incompatible_fields", reason, field=field, spec=spec)

    if args.get("end_seconds") is not None and args["end_seconds"] <= args.get(
        "start_seconds", 0
    ):
        reject("end_seconds", "El final debe ser posterior al inicio.")
    if args.get("container") == "srt" and (
        args.get("start_seconds", 0) != 0 or args.get("end_seconds") is not None
    ):
        reject("end_seconds", "SRT extrae subtítulos completos; no admite recorte.")
    if args.get("subtitle_language") and args.get("container") != "srt":
        reject("subtitle_language", "El idioma solo se usa con formato srt.")
    if spec.family == "manage_poll" and spec.original_action == "create":
        options = args["options"]
        if len({unicodedata.normalize("NFKC", v.strip()).casefold() for v in options}) != len(
            options
        ):
            reject("options", "Las opciones de la encuesta deben ser distintas.")
    if spec.family == "audiovisual.clip" and spec.original_action == "play":
        if ("clip_id" in args) == ("query" in args):
            reject("clip_id", "Indica exactamente ID del catálogo o --nombre TEXTO.")
    if spec.family == "manage_admin" and spec.original_action in ("xp_grant", "xp_remove"):
        if ("target" in args) == ("account_id" in args):
            reject("target", "Indica exactamente --objetivo REF o --cuenta ID.")
    if spec.original_action == "configure_digest":
        if bool(args.get("enabled")) != ("digest_time" in args):
            reject("digest_time", "La activación exige --hora HH:MM; al desactivar se omite.")
    if spec.original_action == "set_lesson" and args["end_time"] <= args["start_time"]:
        reject("end_time", "La clase debe terminar después del inicio.")
    if spec.family == "manage_messages" and spec.original_action == "prepare":
        if args["source"] == "cita" and "text" in args:
            reject(
                "text", "Con --fuente cita se usa exclusivamente el texto de la cita exacta."
            )
        if args["source"] == "actual" and "text" not in args and not args.get("attach"):
            reject("text", "Falta el texto literal o un adjunto solicitado.")
    if spec.family == "audiovisual.agenda" and spec.original_action == "create":
        if args.get("audio_id") and args.get("live_request"):
            reject("audio_id", "Audio preparado y conversación Live son modos excluyentes.")
        if args.get("end_after_audio") and not args.get("audio_id"):
            reject("end_after_audio", "Terminar tras audio requiere un audio preparado propio.")
