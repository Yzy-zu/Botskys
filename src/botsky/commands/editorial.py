"""Nombres y descripciones editoriales; el registro sigue siendo el catálogo único."""

FAMILIES = {
    "core": ("Ayuda y control", "Consulta ayuda, sigue tus encargos y cancela lo pendiente."),
    "manage_conversation": (
        "Modo de Botsky",
        "Consulta el modo y controla las pausas de este chat.",
    ),
    "conversation": (
        "Inteligencia artificial",
        "Pregunta o analiza un archivo; el contenido no ejecuta comandos.",
    ),
    "download_media": (
        "Videos y descargas",
        "Busca videos, elige una opción o descarga desde un enlace admitido.",
    ),
    "search_web": ("Búsqueda web", "Consulta candidatos con términos y fuentes explícitos."),
    "save_note": ("Guardar nota", "Guarda texto literal propio en este chat."),
    "find_notes": ("Buscar notas", "Consulta tus notas con filtro y páginas."),
    "manage_memory": (
        "Memoria",
        "Guarda, consulta, corrige o retira recuerdos explícitos de este chat.",
    ),
    "send_sticker": ("Reacciones", "Envía un sticker del catálogo disponible."),
    "make_sticker": ("Crear sticker", "Convierte una imagen adjunta o citada en sticker."),
    "read_image": ("Lectura de imagen", "Extrae texto o QR como datos; no los ejecuta."),
    "edit_media": (
        "Editar audio y video",
        "Convierte un archivo y conserva los límites o recortes pedidos.",
    ),
    "convert_document": (
        "Convertir documentos",
        "Convierte un adjunto; informa las limitaciones del formato final.",
    ),
    "manage_pdf": (
        "Documentos PDF",
        "Reúne archivos, extrae páginas y controla una sesión PDF propia.",
    ),
    "make_voice": ("Voz", "Lee texto literal o compone un guion antes de generar la voz elegida."),
    "transcribe_media": (
        "Transcribir",
        "Obtén texto literal, resumen o ambos desde audio o video.",
    ),
    "manage_reminder": (
        "Recordatorios",
        "Programa y consulta avisos propios con fecha y zona explícitas.",
    ),
    "manage_school": (
        "Escuela y horario",
        "Organiza tareas, adjuntos, clases y resúmenes del ámbito autorizado.",
    ),
    "manage_poll": (
        "Encuestas",
        "Publica una pregunta, vota y consulta resultados con opciones completas.",
    ),
    "manage_drive": (
        "Archivos de Drive",
        "Busca en tu ámbito, recupera un archivo o guarda un adjunto.",
    ),
    "manage_messages": (
        "Recados",
        "Prepara una vista previa para contactos verificados y confirma su envío.",
    ),
    "manage_economy": (
        "XP",
        "Consulta saldo, reservas, daily y clasificación de cuentas de Botsky.",
    ),
    "manage_blackjack": (
        "Blackjack",
        "Juega con apuestas de XP, turnos publicados y cartas visibles.",
    ),
    "manage_roulette": (
        "Ruleta",
        "Consulta coste y consecuencias antes de entrar o iniciar una sala.",
    ),
    "manage_pack": ("Packs", "Consulta categorías, stock y precio antes de confirmar una compra."),
    "manage_cooperacha": (
        "Cooperachas",
        "Consulta la previa censurada y aporta solo de tu propio saldo.",
    ),
    "manage_happy_hour": (
        "Hora feliz",
        "Consulta eventos y reclama un AirDrop con su referencia publicada.",
    ),
    "make_prank": ("Broma ficticia", "Crea una broma inocua; no investiga ni contacta a nadie."),
    "manage_admin": (
        "Administración",
        "Opera sobre objetivos verificados; conserva las confirmaciones sensibles.",
    ),
    "manage_minecraft": (
        "Minecraft",
        "Consulta salud y paquetes o solicita cambios observables del servidor.",
    ),
    "control_call": ("Llamadas", "Inicia o controla una llamada autorizada en este chat."),
    "audiovisual.clip": (
        "Clips",
        "Consulta clips y controla reproducción y volumen durante una llamada autorizada.",
    ),
    "audiovisual.avatar": (
        "Avatar",
        "Aplica un fondo, expresión o gesto disponible durante una llamada autorizada.",
    ),
    "audiovisual.agenda": (
        "Agenda de llamadas",
        "Programa una llamada con fecha, zona, modo y duración explícitos.",
    ),
}

FIELD_LABELS = {
    "live_request": "tema",
    "max_seconds": "duración",
    "duration_seconds": "duración",
    "view_id": "referencia de lista",
    "choice": "número de opción",
    "audio_id": "audio preparado",
    "source": "fuente",
    "target": "objetivo",
    "target_ref": "destino verificado",
    "account_id": "cuenta",
    "required_terms": "términos obligatorios",
    "container": "formato",
    "start_seconds": "inicio",
    "end_seconds": "final",
    "requested_seconds": "duración aproximada",
    "include_closed": "incluir cerrados",
    "subtitle_language": "idioma de subtítulos",
    "time": "hora",
    "date": "fecha",
}
