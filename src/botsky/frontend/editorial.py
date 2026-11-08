"""Metadatos naturales propios; el registro conserva contratos y autoridad."""
from botsky.commands.editorial import FAMILIES, FIELD_LABELS

VARIANTS = {
    'read_image.run': 'Extraer texto con OCR o leer el contenido de un QR como datos, según la variante.',
    'make_voice.verbatim': 'Leer literalmente el texto, la cita o la última respuesta según la variante; no componer un guion.',
    'download_media.url': 'Descargar el enlace explícito en el formato de esta variante; SRT extrae subtítulos completos.',
    'manage_pack.buy': 'Preparar compra por categoría o confirmar una oferta publicada por su ID según esta variante.',
    'manage_reminder.create': 'Programar un aviso relativo en segundos o en fecha/hora local concreta según esta variante.',
    'audiovisual.clip.volume': 'Ajustar volumen absoluto o modificarlo en la dirección indicada por las constantes de esta variante.',
    'manage_pdf.start': 'Iniciar sesión de ensamblaje PDF con archivos adjuntos.',
    'manage_pdf.add': 'Añadir archivos o páginas a una sesión PDF activa.',
    'manage_school.add_task': 'Registrar una tarea escolar con fecha límite y materia.',
    'manage_school.set_lesson': 'Añadir una clase al horario semanal en día y hora específicos.',
    'manage_poll.create': 'Crear una encuesta con opciones y pregunta explícitas.',
    'manage_admin.warn': 'Emitir una advertencia a un miembro del grupo.',
    'manage_admin.kick': 'Expulsar a un miembro no administrador del grupo.',
    'manage_admin.ban': 'Bloquear a un miembro del grupo.',
    'manage_minecraft.start': 'Arrancar el servidor de Minecraft configurado.',
    'manage_minecraft.stop': 'Detener el servidor de Minecraft.',
    'manage_minecraft.backup': 'Crear un respaldo del mundo y datos de Minecraft.',
}

SUMMARIES = {
    "conversation.respond": "Preguntar o analizar un archivo con IA; el modelo responde como contenido sin ejecutar acciones.",
    "convert_document.run": "Convertir un documento adjunto o citado al formato especificado.",
    "save_note.run": "Guardar un fragmento de texto o apunte en las notas de este chat.",
    "find_notes.run": "Buscar notas guardadas por palabra clave o ver el listado paginado.",
    "make_sticker.run": "Crear un sticker de WhatsApp a partir de una foto, imagen o video adjunto.",
    "send_sticker.run": "Enviar un sticker predefinido de la galería de reacciones.",
    "read_image.run": "Escanear una imagen para extraer su texto (OCR) o leer un código QR.",
    "edit_media.run": "Recortar, cambiar formato o extraer audio de un video o archivo multimedia.",
    "make_voice.catalog": "Consultar las voces disponibles para notas de voz.",
    "make_voice.compose": "Generar una nota de voz con guion redactado por IA.",
    "make_voice.verbatim": "Convertir texto literal a nota de voz con la voz elegida.",
    "transcribe_media.run": "Transcribir un archivo de audio o video a texto o generar su resumen.",
    "search_web.run": "Buscar información en la web mediante el motor de búsqueda.",
    "manage_reminder.create": "Programar un recordatorio con aviso en una fecha, hora o plazo relativo.",
    "manage_reminder.list": "Consultar la lista de recordatorios activos en este chat.",
    "manage_reminder.cancel": "Cancelar un recordatorio programado pendiente.",
    "manage_reminder.archive": "Archivar o descartar un recordatorio.",
    "manage_school.add_task": "Registrar una tarea o trabajo escolar con materia y fecha de entrega.",
    "manage_school.list_tasks": "Ver la lista de tareas escolares pendientes o completadas.",
    "manage_school.complete_task": "Marcar una tarea escolar como terminada.",
    "manage_school.delete_task": "Eliminar una tarea escolar.",
    "manage_school.set_lesson": "Agregar una clase al horario escolar con día y horas.",
    "manage_school.list_schedule": "Consultar el horario escolar semanal.",
    "manage_school.delete_lesson": "Quitar una clase del horario escolar.",
    "manage_school.configure_digest": "Configurar la hora del resumen diario de tareas escolares.",
    "manage_school.status_digest": "Consultar el estado del resumen escolar diario.",
    "manage_school.get_attachment": "Recuperar el archivo adjunto de una tarea escolar.",
    "manage_poll.create": "Crear una encuesta grupal con pregunta y opciones.",
    "manage_poll.vote": "Emitir un voto en una encuesta activa.",
    "manage_poll.results": "Ver los resultados actuales de una encuesta.",
    "manage_poll.close": "Cerrar una encuesta para no admitir más votos.",
    "manage_drive.search": "Buscar archivos en tu cuenta de Google Drive.",
    "manage_drive.choose": "Descargar un archivo encontrado en Google Drive.",
    "manage_drive.save": "Guardar un archivo adjunto en Google Drive.",
    "manage_drive.capacity": "Consultar el espacio disponible en Google Drive.",
    "manage_messages.prepare": "Preparar un recado o mensaje para contactos verificados.",
    "manage_messages.send": "Confirmar y enviar un recado preparado.",
    "manage_messages.status": "Consultar el estado de entrega de un recado.",
    "manage_messages.cancel": "Cancelar un recado pendiente.",
    "manage_messages.contacts": "Ver la lista de contactos verificados para recados.",
    "manage_economy.daily": "Reclamar la recompensa diaria de XP.",
    "manage_economy.balance": "Ver tu saldo de puntos XP y nivel.",
    "manage_economy.top": "Ver la tabla de clasificación de mejores jugadores por XP.",
    "manage_blackjack.start": "Iniciar una nueva partida de Blackjack con apuesta de XP.",
    "manage_blackjack.join": "Unirse a una partida de Blackjack activa.",
    "manage_blackjack.deal": "Repartir las cartas para comenzar la partida.",
    "manage_blackjack.hit": "Pedir otra carta en tu turno de Blackjack.",
    "manage_blackjack.stand": "Plantarse con la mano actual de Blackjack.",
    "manage_blackjack.double": "Doblar la apuesta en Blackjack y recibir una sola carta.",
    "manage_blackjack.status": "Ver el estado actual de la mesa de Blackjack.",
    "manage_blackjack.cancel": "Cancelar la partida de Blackjack y recuperar la apuesta.",
    "manage_roulette.create": "Crear una sala de ruleta rusa con apuesta de XP.",
    "manage_roulette.join": "Entrar a una sala de ruleta activa.",
    "manage_roulette.play": "Iniciar la ronda de ruleta con los participantes.",
    "manage_roulette.status": "Ver el estado y participantes de la ruleta.",
    "manage_roulette.cancel": "Cancelar la sala de ruleta antes de iniciar.",
    "manage_pack.catalog": "Ver el catálogo de paquetes de fotos disponibles.",
    "manage_pack.buy": "Comprar un paquete de fotos con puntos XP.",
    "manage_pack.status": "Ver el estado de entrega de tu compra de pack.",
    "manage_cooperacha.start": "Crear un reto de cooperacha grupal para desbloquear una foto.",
    "manage_cooperacha.contribute": "Aportar puntos XP a la meta de una cooperacha.",
    "manage_cooperacha.status": "Ver el avance y recaudación de la cooperacha.",
    "manage_cooperacha.cancel": "Cancelar una cooperacha propia abierta.",
    "manage_happy_hour.start": "Iniciar un evento de Hora Feliz con doble XP.",
    "manage_happy_hour.stop": "Finalizar la Hora Feliz antes de tiempo.",
    "manage_happy_hour.status": "Ver el tiempo restante y bonificaciones de la Hora Feliz.",
    "manage_happy_hour.rain": "Activar una lluvia de puntos XP para el grupo.",
    "manage_happy_hour.airdrop": "Lanzar un premio AirDrop en el chat para el más rápido.",
    "manage_happy_hour.claim": "Reclamar el premio AirDrop activo.",
    "make_prank.run": "Generar un mensaje de broma inofensivo para el chat.",
    "manage_admin.warn": "Emitir una advertencia a un miembro del grupo.",
    "manage_admin.unwarn": "Retirar una advertencia previa a un miembro.",
    "manage_admin.warnings": "Consultar las advertencias activas en el grupo.",
    "manage_admin.kick": "Expulsar a un participante del grupo.",
    "manage_admin.ban": "Bloquear o banear a un participante del grupo.",
    "manage_admin.unban": "Desbloquear o desbanear a un participante.",
    "manage_admin.promote": "Promover a un miembro a administrador del grupo.",
    "manage_admin.demote": "Degradar o quitar el rol de administrador a un miembro.",
    "manage_admin.mute": "Silenciar el grupo para que solo administradores envíen mensajes.",
    "manage_admin.unmute": "Permitir que todos los miembros puedan enviar mensajes.",
    "manage_admin.lock": "Restringir la edición de información del grupo a administradores.",
    "manage_admin.unlock": "Permitir que cualquier miembro edite la información del grupo.",
    "manage_admin.xp_grant": "Otorgar puntos XP administrativos a un usuario.",
    "manage_admin.xp_remove": "Descontar puntos XP administrativos a un usuario.",
    "manage_admin.nuclear_prepare": "Preparar la expulsión masiva nuclear de miembros no administradores.",
    "manage_admin.nuclear_confirm": "Confirmar y ejecutar la acción nuclear en el grupo.",
    "manage_admin.nuclear_cancel": "Cancelar la acción nuclear preparada.",
    "manage_minecraft.status": "Consultar el estado de salud y conexión del servidor de Minecraft.",
    "manage_minecraft.players": "Ver los jugadores conectados actualmente en Minecraft.",
    "manage_minecraft.worlds": "Listar los mundos disponibles en el servidor de Minecraft.",
    "manage_minecraft.config": "Ver la configuración y propiedades del servidor de Minecraft.",
    "manage_minecraft.start": "Iniciar el servidor de Minecraft.",
    "manage_minecraft.stop": "Detener el servidor de Minecraft.",
    "manage_minecraft.restart": "Reiniciar el servidor de Minecraft.",
    "manage_minecraft.backup": "Crear un respaldo del servidor de Minecraft.",
    "manage_minecraft.mods": "Listar los mods instalados en Minecraft.",
    "manage_minecraft.enable_mod": "Activar un mod en el servidor de Minecraft.",
    "manage_minecraft.disable_mod": "Desactivar un mod en el servidor de Minecraft.",
    "manage_minecraft.console": "Enviar un comando a la consola del servidor de Minecraft.",
    "manage_minecraft.discover": "Ejecutar diagnóstico de recursos del servidor de Minecraft.",
    "manage_minecraft.recover": "Intentar recuperar el servidor de Minecraft.",
    "control_call.start": "Iniciar una llamada de voz o video con Botsky.",
    "control_call.status": "Ver el estado de la llamada actual.",
    "control_call.hangup": "Finalizar o colgar la llamada actual.",
    "control_call.cancel": "Cancelar la llamada en preparación.",
    "audiovisual.clip.list": "Ver la lista de clips de audio y video disponibles.",
    "audiovisual.clip.play": "Reproducir un clip multimedia durante la llamada.",
    "audiovisual.clip.pause": "Pausar la reproducción del clip actual.",
    "audiovisual.clip.resume": "Reanudar la reproducción del clip pausado.",
    "audiovisual.clip.stop": "Detener la reproducción del clip.",
    "audiovisual.clip.replay": "Repetir el clip desde el principio.",
    "audiovisual.clip.next": "Pasar al siguiente clip en la cola.",
    "audiovisual.clip.volume": "Ajustar el volumen de reproducción de clips.",
    "audiovisual.avatar.background": "Cambiar el fondo del avatar durante la llamada.",
    "audiovisual.avatar.expression": "Cambiar la expresión facial del avatar.",
    "audiovisual.avatar.gesture": "Hacer que el avatar realice un gesto corporal.",
    "audiovisual.avatar.blush": "Activar o desactivar el rubor del avatar.",
    "audiovisual.agenda.list": "Consultar la agenda de llamadas programadas.",
    "audiovisual.agenda.create": "Programar una llamada futura con fecha y hora.",
    "audiovisual.agenda.update": "Reprogramar la fecha u hora de una llamada.",
    "audiovisual.agenda.cancel": "Cancelar una llamada programada en la agenda.",
    "core.help": "Consultar la ayuda de comandos o capacidades de Botsky.",
    "core.estado": "Ver el estado de los procesos y encargos en curso.",
    "core.cancelar": "Cancelar un encargo o proceso en segundo plano.",
    "core.confirmar": "Confirmar una acción pendiente que requiere autorización.",
    "download_media.search": "Buscar videos en plataformas admitidas y mostrar opciones.",
    "download_media.choose": "Descargar un video o audio de una búsqueda previa por su número.",
    "download_media.url": "Descargar un video, audio o subtítulos directamente desde un enlace.",
    "download_media.inspect": "Ver los detalles y metadatos completos de una opción de video.",
    "download_media.previous": "Reutilizar y convertir el último archivo descargado.",
    "manage_memory.remember": "Guardar un recuerdo o dato relevante para este chat.",
    "manage_memory.list": "Consultar los recuerdos guardados en este chat.",
    "manage_memory.correct": "Corregir el texto de un recuerdo existente.",
    "manage_memory.forget": "Borrar un recuerdo específico por su identificador.",
    "manage_memory.forget_all": "Borrar todos los recuerdos almacenados de este chat.",
    "manage_conversation.status": "Ver el estado y configuración actual de Botsky en este chat.",
    "manage_conversation.mode": "Cambiar el modo operativo de Botsky en este chat.",
    "manage_conversation.pause": "Pausar temporalmente las respuestas de Botsky en este chat.",
    "manage_conversation.resume": "Reanudar la atención de Botsky tras una pausa.",
    "manage_pdf.start": "Iniciar una sesión de creación de documento PDF.",
    "manage_pdf.add": "Añadir imágenes o documentos a la sesión PDF activa.",
    "manage_pdf.finish": "Finalizar y generar el documento PDF ensamblado.",
    "manage_pdf.extract": "Extraer páginas específicas de un documento PDF.",
    "manage_pdf.cancel": "Cancelar la sesión PDF en curso sin generar archivo.",
    "manage_pdf.retry": "Reintentar el envío de partes pendientes de un PDF.",
}


def description(spec):
    title, purpose = FAMILIES[spec.family]
    action = ' '.join(spec.path)
    summary = spec.summary or SUMMARIES.get(spec.operation) or purpose
    text = f'{title}: {action}. {summary}'
    if spec.operation in VARIANTS:
        text += ' ' + VARIANTS[spec.operation]
    if spec.constants:
        text += ' Variante fija: ' + ', '.join(f'{k}={v}' for k, v in spec.constants) + '.'
    if spec.attachment:
        text += ' Requiere archivo propio adjunto o citado disponible.'
    if spec.confirmation != 'none':
        text += ' Conserva la previa y confirmación específicas del backend.'
    return text


def field_description(field):
    text = FIELD_LABELS.get(field.name, field.name.replace('_', ' '))
    if field.kind in ('duration', 'seconds'):
        text += '; número de segundos'
    if field.kind == 'date':
        text += '; fecha local AAAA-MM-DD calculada con fecha/zona del host'
    if field.kind == 'clock':
        text += '; hora local HH:MM de 24 horas'
    if field.kind == 'text' or field.tail:
        text += '; conserva literalmente el contenido solicitado'
    if field.kind == 'id':
        text += '; referencia real verificada por el host, nunca inventada'
    return text


def reference_fields(spec):
    return [f.name for f in spec.fields if f.kind == 'id' or f.name in ('choice', 'target_ref')]
