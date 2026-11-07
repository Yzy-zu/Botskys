"""Catálogo por variante y puente JSON directo al backend."""
from dataclasses import replace
from types import MappingProxyType

from botsky.commands.registry import Registry
from botsky.commands.router import ParsedCommand
from botsky.commands.validation import validate_arguments

from .editorial import description, field_description, reference_fields

URL_SOURCES = ('youtube', 'dailymotion', 'vimeo', 'facebook', 'instagram', 'tiktok', 'spotify', 'pornhub', 'xnxx')

SELECTIONS = {'download_media.choose', 'download_media.inspect', 'manage_drive.choose'}


def native_fields(spec):
    return tuple(replace(f, required=f.name == 'choice')
                 if spec.operation in SELECTIONS and f.name in ('choice', 'view_id')
                 else f for f in spec.fields)


def scalar(field, value):
    if field.kind in ('bool', 'flag'):
        if type(value) is not bool:
            raise ValueError('requiere booleano JSON')
        return value
    if field.kind in ('int', 'duration', 'float', 'seconds'):
        kinds = (int,) if field.kind in ('int', 'duration') else (int, float)
        if type(value) not in kinds:
            raise ValueError('requiere número JSON')
        # Duraciones nativas en segundos, sin sintaxis de unidades.
        return replace(field, kind='int' if field.kind == 'duration' else field.kind).convert(str(value))
    if field.kind in ('contacts', 'terms'):
        if not isinstance(value, list) or any(type(v) is not str or ',' in v for v in value):
            raise ValueError('requiere array de textos sin comas')
        return field.convert(','.join(value))
    if type(value) is not str:
        raise ValueError('requiere texto JSON')
    return field.convert(value)


def field_schema(f):
    kind = ('boolean' if f.kind in ('bool', 'flag') else
            'integer' if f.kind in ('int', 'duration') else
            'number' if f.kind in ('float', 'seconds') else 'string')
    schema = {'type': kind, 'description': field_description(f)}
    if kind == 'string':
        schema.update(minLength=1, maxLength=f.max_length)
    if f.choices:
        schema['enum'] = list(f.choices)
    for name, val in [('minimum', f.minimum), ('maximum', f.maximum)]:
        if val is not None:
            schema[name] = val
    if f.kind in ('contacts', 'terms'):
        schema = {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1,
                  'maxItems': f.max_items, 'uniqueItems': True}
    if f.repeated:
        schema = {'type': 'array', 'items': schema, 'minItems': f.min_items,
                  'maxItems': f.max_items}
    return schema


class Catalog:
    def __init__(self, registry=None):
        self.availability = {}
        self.search_sources = ('youtube', 'pornhub', 'xnxx', 'adult')
        self.url_sources = URL_SOURCES
        self.specs = {'.'.join(s.path): s for s in (registry or Registry()).specs}

    def configure_downloads(self, backend):
        enabled = backend is not None and getattr(backend, 'enabled', True) is True
        adult = enabled and getattr(backend, 'adult_sources_enabled', False) is True
        self.search_sources = ('youtube',) + (('pornhub', 'xnxx', 'adult') if adult else ()) if enabled else ()
        self.url_sources = tuple(s for s in URL_SOURCES if adult or s not in ('pornhub', 'xnxx')) if enabled else ()

    def fields(self, spec):
        return tuple(replace(f, required=True, default=None, choices=self.search_sources)
                     if spec.operation == 'download_media.search' and f.name == 'source' else f
                     for f in native_fields(spec))

    def describe(self):
        return [dict(action_key=key, operation=s.operation, description=description(s),
                     references=reference_fields(s),
                     availability={**self.availability.get(s.family, {}), **({'search_sources': self.search_sources, 'url_sources': self.url_sources} if s.family == 'download_media' else {})},
                     permission=s.permission, effect=s.effect, confirmation=s.confirmation,
                     attachment=s.attachment, constants=dict(s.constants),
                     parameters=dict(type='object', additionalProperties=False,
                                     properties={f.name: field_schema(f) for f in self.fields(s)},
                                     required=[f.name for f in self.fields(s) if f.required]))
                for key, s in self.specs.items()]

    def build(self, request):
        spec = self.specs[request.action_key]
        if type(request.arguments) is not dict:
            raise ValueError('arguments debe ser un objeto JSON')
        if spec.operation == 'download_media.search' and not self.search_sources:
            raise ValueError('download_search_disabled')
        fields = self.fields(spec)
        if set(request.arguments) - {f.name for f in fields}:
            raise ValueError('campos desconocidos o constantes no editables')
        args = dict(spec.constants)
        for f in fields:
            if f.name not in request.arguments:
                if f.required:
                    raise ValueError('falta ' + f.name)
                if f.default is not None:
                    args[f.name] = f.default
                continue
            value = request.arguments[f.name]
            if f.repeated:
                if type(value) is not list or not f.min_items <= len(value) <= f.max_items:
                    raise ValueError('cantidad de elementos inválida')
                args[f.name] = tuple(scalar(f, v) for v in value)
            else:
                args[f.name] = scalar(f, value)
        validate_arguments(spec, args)
        return ParsedCommand(spec, MappingProxyType(args), MappingProxyType({}))
