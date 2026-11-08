"""Presentación natural sobre hechos y bloques de producto; nunca reescribe literales."""
import re
from dataclasses import replace

from . import Block, Document, attach_document

# Solo instrucciones tipadas next_action del producto. No se buscan patrones en
# el mensaje final, párrafos de contenido, notas, enlaces o archivos del usuario.
NEXT_ACTIONS = {
    '/dl elegir ': 'Responde con el número del video que quieres descargar.',
    'Título y autor completos: /dl detalle ': 'Para ver el enlace o datos completos, di «pásame el enlace del 1», indicando su número.',
    '/drive elegir ': 'Responde con el número del archivo que quieres recuperar.',
    '/recado enviar ': 'Responde «sí, envíalo» a esta vista previa.',
    '/pack confirmar ': 'Responde «confirma la compra» a esta oferta.',
    '/admin nuclear-confirmar ': 'Para confirmar la expulsión grupal, responde «confirma la acción nuclear».',
    '/admin nuclear-cancelar ': 'Para descartarla, responde «cancela la acción nuclear».',
    '/notas ': 'Di «siguiente página de notas» para continuar.',
    '/ruleta entrar ': 'Di «quiero entrar en esta ruleta».',
    '/ruleta jugar ': 'Di «inicia esta ruleta».',
    '/coop aportar ': 'Di cuánto quieres aportar; por ejemplo, «aporta 50 XP a este reto».',
    '/coop ': 'Di «cómo va esta cooperacha».',
    '/hh estado ': 'Di «cómo va esta hora feliz».',
    '/hh reclamar ': 'Responde «reclama este premio».',
    '/clip poner ': 'Di «reproduce este clip».',
    '/mc estado': 'Di «cómo está Minecraft».',
    '/tarea ': 'Indica el número de tarea para gestionarla.',
    '/recordatorio ': 'Indica qué recordatorio deseas crear o revisar.',
}

MESSAGES = {
    'pdf_session_busy': 'El PDF ya se está preparando. Puedes preguntar cómo va o pedir cancelar la sesión.',
    'pdf_session_empty': 'La sesión PDF está vacía. Adjunta un archivo y pídeme añadirlo.',
    'pdf_session_exists': 'Ya tienes un PDF abierto. Puedes añadir archivos, terminarlo o cancelar la sesión.',
    'voice_source_unavailable': 'No hay texto propio exacto disponible para leer. Escribe el texto que quieres convertir a voz.',
    'ai_quote_unavailable': 'No encontré el mensaje citado. Copia y pega aquí el fragmento que deseas consultar.',
    'note_filter_required': 'Dime qué palabra o asunto deseas buscar en tus notas.',
    'request_ambiguous': 'Hay varias solicitudes en curso. Por favor responde directamente al mensaje de la que deseas consultar o cancelar.',

    'pdf_session_missing': 'Primero pídeme iniciar un PDF y adjunta los archivos que quieres reunir.',
    'retry_preview_required': 'Pide revisar el reenvío de ese PDF y recibe la vista previa antes de confirmar.',
    'attachment_required': 'Adjunta el archivo aquí o responde al mensaje que lo contiene. Conservaré esta petición durante 15 minutos.',
    'selection_ambiguous': 'Hay varias listas vigentes. Responde al mensaje de la lista que quieres e indica el número de opción.',
    'download_view_unavailable': 'La lista venció o ya no está disponible. Pídeme buscar de nuevo.',
    'drive_view_unavailable': 'La lista de archivos ya no está disponible. Pídeme buscar de nuevo.',
    'previous_download_missing': 'No encontré un archivo previo en este chat. Por favor envíalo de nuevo.',
    'confirmation_unavailable': 'La confirmación ya venció o no corresponde a este chat. Solicita una nueva vista previa para continuar.',
    'message_preview_required': 'Primero prepara y recibe la vista previa del recado. Después responde «sí, envíalo».',
    'message_preview_expired': 'El borrador venció. Prepara el recado de nuevo para revisarlo antes de enviar.',
    'bot_paused': 'Botsky está en pausa en este chat. El dueño puede pedir «reanuda Botsky».',
    'bot_disabled': 'Botsky está apagado en este chat. El dueño puede pedir «reanuda Botsky».',
    'invalid_proposal': 'No entendí qué opción deseas. Responde directamente al mensaje del listado con el número correspondiente.',
}


def _clean_natural_block(text):
    text = re.sub(
        r"Vigencia máxima:\s*(\d+):(\d+)\s*desde la preparación\..*?Opciones\s*1[–-](\d+)\.",
        r"⏱️ _Opciones válidas por \1 min. Elige respondiendo del 1 al \3._",
        text,
    )
    text = re.sub(
        r"(\d+(?:\.\d+)?\s*(?:B|KiB|MiB|GiB|TiB|kB|MB|GB|TB))\s*\(\d+\s*bytes\)",
        r"\1",
        text,
    )

    def clean_date(match):
        y, m, d, H, M, S, tz = match.groups()
        hour = int(H)
        ampm = "a.m." if hour < 12 else "p.m."
        h12 = hour % 12 or 12
        return f"{d}/{m}/{y}, {h12:02d}:{M} {ampm}"

    text = re.sub(
        r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\s+·\s+([A-Za-z_/]+)",
        clean_date,
        text,
    )
    return text


EMOJI_HEADINGS = {
    'Videos': '🎬 Videos',
    'Notas': '📝 Notas',
    'Reenviar PDF': '📑 Reenviar PDF',
    'Borrar recuerdos': '🗑️ Borrar recuerdos',
    'Estado de Botsky': '🤖 Estado de Botsky',
    'Análisis de IA': '🧠 Análisis de IA',
    'Transcripción literal': '🎙️ Transcripción literal',
    'Resumen generado': '📋 Resumen generado',
    'Texto de imagen (OCR)': '🔍 Texto de imagen (OCR)',
    'Contenido QR': '📱 Contenido QR',
    'Top de XP': '🏆 Top de XP',
    'Falta el archivo': '📎 Falta el archivo',
    'Memoria actualizada': '🧠 Memoria actualizada',
    'Documento convertido': '📄 Documento convertido',
    'Audio o video convertido': '🎬 Audio o video convertido',
    'Descarga preparada': '📥 Descarga preparada',
    'PDF terminado': '📑 PDF terminado',
    'Páginas extraídas': '📑 Páginas extraídas',
    'Archivo de Drive': '💾 Archivo de Drive',
    'Archivo de tarea': '📎 Archivo de tarea',
}


def adapt(result):
    if result.code == 'voice_catalog':
        return replace(result, text='Voces: ' + ', '.join(result.data['voices']) + '.\nDi, por ejemplo, «lee este texto con voz mexicana».')
    if result.code in ('pdf_session_started', 'pdf_sources_added'):
        return replace(result, text=f"PDF abierto con {result.data['sources']} archivos. Puedes adjuntar otro y pedir añadirlo, decir «termina el PDF» o «cancela la sesión».")
    if result.code in MESSAGES:
        return replace(result, text=MESSAGES[result.code], data={k:v for k,v in result.data.items() if k != 'document'})
    if result.code == 'delivery_retry_preview':
        return attach_document(result, Document((Block('heading', '📑 Reenviar PDF'),
            Block('paragraph', f"Se reenviarán {result.data.get('part_count', 'las')} partes fallidas o inciertas del PDF."),
            Block('notice', 'Reenviar una parte incierta podría duplicarla. Se conserva el resultado del motor; no se repetirá la conversión.'),
            Block('paragraph', 'Responde «sí, reenvía esas partes» a esta vista previa para confirmar.'))))
    if result.code == 'memory_delete_preview':
        return attach_document(result, Document((Block('heading', '🗑️ Borrar recuerdos'),
            Block('notice', f"Se borrarán {result.data.get('count', 'todos los')} recuerdos de este ámbito."),
            Block('paragraph', 'Responde «sí, borra los recuerdos» a esta vista previa para confirmar.'))))
    document = result.data.get('document')
    if not document:
        return result
    blocks = []
    for item in document['blocks']:
        block = Block(**item)
        if block.kind == 'next_action':
            text = next((label for command, label in NEXT_ACTIONS.items() if block.text.startswith(command)), block.text)
            block = Block('paragraph', text)
        elif block.kind == 'heading':
            if block.text in EMOJI_HEADINGS:
                block = Block('heading', EMOJI_HEADINGS[block.text])
            elif block.text.startswith('Recordatorio ') and not block.text.startswith('🔔 '):
                block = Block('heading', f"🔔 {block.text}")
            elif block.text.startswith('Tarea ') and not block.text.startswith('📋 '):
                block = Block('heading', f"📋 {block.text}")
            else:
                block = Block('heading', _clean_natural_block(block.text))
        elif block.kind != 'literal':
            block = Block(block.kind, _clean_natural_block(block.text))
        blocks.append(block)
    return attach_document(result, Document(tuple(blocks)))
