"""Microtexto de fallos desde códigos estables; diagnóstico conserva código aparte."""

ERRORS = {
    "source_access_denied": "La fuente rechazó el acceso a ese video. Prueba otro resultado.",
    "source_client_unavailable": "No es posible descargar contenido de esta fuente por el momento. Intenta con otro enlace o plataforma.",
    "source_network_failed": "Hubo un problema de conexión al obtener el video. Por favor, inténtalo de nuevo en unos momentos.",
    "source_failed": "No fue posible descargar este video. Por favor, elige otra opción de la lista o intenta con otro enlace.",
    "job_timeout": "El proceso tardó más de lo esperado y se detuvo. Por favor, intenta de nuevo con un archivo más ligero o breve.",
    "source_rate_limited": "La fuente limitó las consultas. Espera antes de intentarlo de nuevo o usa otro enlace admitido.",
    "source_auth_required": "Ese contenido requiere acceso que Botsky no tiene. Usa otro enlace público admitido.",
    "source_content_unavailable": "El contenido no está disponible en esa fuente. Comprueba el enlace o elige otro resultado.",
    "source_format_unavailable": "El video no está disponible en ese formato. Puedes pedirlo en MP4 de video o como audio MP3.",
    "source_verification_required": "La fuente exige una verificación que no pude completar. Puedes probar otro enlace público admitido.",
    "adult_sources_disabled": "Esa fuente no está habilitada en Botsky.",
    "unsupported_url": "Este enlace no es compatible. Puedes enviarme enlaces de YouTube u otras fuentes admitidas.",
    "gemini_quota": "El asistente de inteligencia artificial está temporalmente ocupado. Las funciones de notas, descargas y archivos siguen funcionando con normalidad.",
    "gemini_not_configured": "El asistente conversacional no está disponible en este momento. Las herramientas de notas y conversión continúan activas.",
    "web_unavailable": "El buscador web no respondió a tiempo. Por favor, repite tu búsqueda en un momento.",
    "downloads_not_configured": "Las descargas remotas no están configuradas. Puedes adjuntar un archivo para editarlo.",
    "tts_not_configured": "La función de notas de voz no está habilitada en este momento.",
    "asr_not_configured": "La transcripción de audio no está habilitada en este momento.",
    "input_size": "El archivo supera el tamaño admitido para esta operación. Consulta la ayuda del comando.",
    "invalid_media": "No pude leer un audio o video válido. Revisa el archivo y adjúntalo de nuevo.",
    "unsupported_media": "Ese formato no es compatible. Puedes enviarme archivos en formato MP4, MP3, WAV o WebM.",
    "qr_not_found": "No encontré ningún código QR legible en esta foto. Asegúrate de que esté bien enfocada e iluminada.",
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
    text = "No pude completar tu solicitud en este momento. Inténtalo de nuevo o dime qué necesitas para orientarte."
    return text + (" Consulta /ayuda " + topic + "." if topic else "")
