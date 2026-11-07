"""Presentación natural sobre hechos y bloques de producto; nunca reescribe literales."""
from dataclasses import replace

from . import Block, Document, attach_document

# Solo instrucciones tipadas next_action del producto. No se buscan patrones en
# el mensaje final, párrafos de contenido, notas, enlaces o archivos del usuario.
NEXT_ACTIONS = {
    '/dl elegir ': 'Responde con el número del video que quieres descargar.',
    'Título y autor completos: /dl detalle ': 'Para ver los datos completos, di «dime más del segundo», indicando su número.',
    '/drive elegir ': 'Responde con el número del archivo que quieres recuperar.',
    '/recado enviar ': 'Responde «sí, envíalo» a esta vista previa.',
    '/pack confirmar ': 'Responde «confirma la compra» a esta oferta.',
    '/admin nuclear-confirmar ': 'Responde «confirma la acción nuclear» a esta vista previa.',
    '/admin nuclear-cancelar ': 'Para descartarla, responde «cancela la acción nuclear».',
    '/notas ': 'Di «siguiente página de notas» para continuar.',
    '/ruleta entrar ': 'Di «quiero entrar en esta ruleta».',
    '/ruleta jugar ': 'Di «inicia esta ruleta».',
    '/coop aportar ': 'Di cuánto quieres aportar; por ejemplo, «aporta 50 XP a este reto».',
    '/hh estado ': 'Di «cómo va esta hora feliz».',
    '/hh reclamar ': 'Responde «reclama este premio».',
    '/clip poner ': 'Di «reproduce este clip».',
    '/mc estado': 'Di «cómo está Minecraft».',
}

MESSAGES = {
    'pdf_session_busy': 'El PDF ya se está preparando. Puedes preguntar cómo va o pedir cancelar la sesión.',
    'pdf_session_empty': 'La sesión PDF está vacía. Adjunta un archivo y pídeme añadirlo.',
    'pdf_session_exists': 'Ya tienes un PDF abierto. Puedes añadir archivos, terminarlo o cancelar la sesión.',
    'voice_source_unavailable': 'No hay texto propio exacto disponible para leer. Escribe el texto que quieres convertir a voz.',
    'ai_quote_unavailable': 'La cita ya no está disponible en este ámbito. Copia aquí el texto que quieres consultar.',
    'note_filter_required': 'No hay una búsqueda propia vigente. Indica de nuevo qué texto quieres buscar en tus notas.',
    'request_ambiguous': 'Hay varios encargos pendientes. Responde al mensaje del encargo que quieres consultar o cancelar.',

    'pdf_session_missing': 'Primero pídeme iniciar un PDF y adjunta los archivos que quieres reunir.',
    'retry_preview_required': 'Pide revisar el reenvío de ese PDF y recibe la vista previa antes de confirmar.',
    'attachment_required': 'Adjunta el archivo aquí o responde al mensaje que lo contiene. Conservaré esta petición durante 15 minutos.',
    'selection_ambiguous': 'Hay varias listas vigentes. Responde al mensaje de la lista que quieres e indica el número de opción.',
    'download_view_unavailable': 'La lista venció o ya no está disponible. Pídeme buscar de nuevo.',
    'drive_view_unavailable': 'La lista de archivos ya no está disponible. Pídeme buscar de nuevo.',
    'previous_download_missing': 'No hay una descarga propia disponible en este chat. Adjunta el archivo de nuevo.',
    'confirmation_unavailable': 'La vista previa no está disponible, no es tuya o venció. Pide una nueva.',
    'message_preview_required': 'Primero prepara y recibe la vista previa del recado. Después responde «sí, envíalo».',
    'message_preview_expired': 'El borrador venció. Prepara el recado de nuevo para revisarlo antes de enviar.',
    'bot_paused': 'Botsky está en pausa en este chat. El dueño puede pedir «reanuda Botsky».',
    'bot_disabled': 'Botsky está apagado en este chat. El dueño puede pedir «reanuda Botsky».',
    'invalid_proposal': 'No pude resolver esa petición con los datos disponibles. Indica qué quieres hacer; si eliges algo de una lista, responde a esa lista.',
}


def adapt(result):
    if result.code == 'voice_catalog':
        return replace(result, text='Voces: ' + ', '.join(result.data['voices']) + '.\nDi, por ejemplo, «lee este texto con voz mexicana».')
    if result.code in ('pdf_session_started', 'pdf_sources_added'):
        return replace(result, text=f"PDF abierto con {result.data['sources']} archivos. Puedes adjuntar otro y pedir añadirlo, decir «termina el PDF» o «cancela la sesión».")
    if result.code in MESSAGES:
        return replace(result, text=MESSAGES[result.code], data={k:v for k,v in result.data.items() if k != 'document'})
    if result.code == 'delivery_retry_preview':
        return attach_document(result, Document((Block('heading', 'Reenviar PDF'),
            Block('paragraph', f"Se reenviarán {result.data.get('part_count', 'las')} partes fallidas o inciertas del PDF."),
            Block('notice', 'Reenviar una parte incierta podría duplicarla. Se conserva el resultado del motor; no se repetirá la conversión.'),
            Block('paragraph', 'Responde «sí, reenvía esas partes» a esta vista previa para confirmar.'))))
    if result.code == 'memory_delete_preview':
        return attach_document(result, Document((Block('heading', 'Borrar recuerdos'),
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
        blocks.append(block)
    return attach_document(result, Document(tuple(blocks)))
