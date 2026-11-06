"""Reporte de motores ASR traducido a Result de Botsky, sin autoridad ni despacho."""

from ..contracts import Result


def audio_result(status, data, error_code=None):
    return Result(
        status,
        error_code or ("asr_text" if status == "ok" else "asr_empty"),
        data.get("text", ""),
        data,
    )
