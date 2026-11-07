"""Microtexto de fallos desde códigos estables; diagnóstico conserva código aparte."""

ERRORS = {
    "job_timeout": "La preparación superó el tiempo disponible. No se entregó un resultado nuevo.",
    "source_rate_limited": "La fuente limitó las consultas. Espera antes de intentarlo de nuevo o usa otro enlace admitido.",
    "source_auth_required": "Ese contenido requiere acceso que Botsky no tiene. Usa otro enlace público admitido.",
    "source_content_unavailable": "El contenido no está disponible en esa fuente. Comprueba el enlace o elige otro resultado.",
    "source_format_unavailable": "La fuente no ofrece el formato solicitado. Consulta /ayuda dl para elegir otro formato.",
    "source_verification_required": "La fuente exige una verificación que no pude completar. Puedes probar otro enlace público admitido.",
    "adult_sources_disabled": "Esa fuente no está habilitada en Botsky.",
    "unsupported_url": "El enlace no está admitido para esta operación. Consulta /ayuda dl.",
    "gemini_quota": "La generación de contenido no está disponible por el límite del proveedor. Las herramientas locales siguen disponibles.",
    "gemini_not_configured": "La generación de contenido no está configurada. Puedes seguir usando las herramientas locales.",
    "web_unavailable": "No pude consultar el buscador. No lo interpreto como una búsqueda sin resultados.",
    "downloads_not_configured": "Las descargas remotas no están configuradas. Puedes adjuntar un archivo para editarlo.",
    "tts_not_configured": "La generación de voz no está configurada.",
    "asr_not_configured": "La transcripción no está configurada.",
    "input_size": "El archivo supera el tamaño admitido para esta operación. Consulta la ayuda del comando.",
    "invalid_media": "No pude leer un audio o video válido. Revisa el archivo y adjúntalo de nuevo.",
    "unsupported_media": "Ese tipo de audio o video no está admitido. Consulta /ayuda editar.",
    "qr_not_found": "No pude decodificar un QR. Esto no demuestra que la imagen no contenga uno.",
}


def job_error(code, operation):
    if code in ERRORS:
        return ERRORS[code]
    topics = {
        "download_media": "dl",
        "search_web": "buscar",
        "make_sticker": "sticker",
        "send_sticker": "reaccion",
        "edit_media": "editar",
        "read_image": "ocr",
        "make_voice": "voz",
        "transcribe_media": "transcribir",
        "conversation": "ia",
        "convert_document": "convertir",
        "manage_pdf": "pdf",
        "manage_drive": "drive",
    }
    topic = topics.get(operation.split(".")[0])
    text = "No pude completar esta preparación. No se entregó un resultado nuevo."
    return text + (" Consulta /ayuda " + topic + "." if topic else "")
