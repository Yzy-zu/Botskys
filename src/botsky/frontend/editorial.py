"""Metadatos naturales propios; el registro conserva contratos y autoridad."""
from botsky.commands.editorial import FAMILIES, FIELD_LABELS

VARIANTS = {
    'read_image.run': 'Extraer texto con OCR o leer el contenido de un QR como datos, según la variante.',
    'make_voice.verbatim': 'Leer literalmente el texto, la cita o la última respuesta según la variante; no componer un guion.',
    'download_media.url': 'Descargar el enlace explícito en el formato de esta variante; SRT extrae subtítulos completos.',
    'manage_pack.buy': 'Preparar compra por categoría o confirmar una oferta publicada por su ID según esta variante.',
    'manage_reminder.create': 'Programar un aviso relativo en segundos o en fecha/hora local concreta según esta variante.',
    'audiovisual.clip.volume': 'Ajustar volumen absoluto o modificarlo en la dirección indicada por las constantes de esta variante.',
}


def description(spec):
    title, purpose = FAMILIES[spec.family]
    action = ' '.join(spec.path)
    text = f'{title}: {action}. {spec.summary or purpose}'
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
