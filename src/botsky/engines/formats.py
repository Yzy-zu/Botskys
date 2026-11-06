# Componente técnico adaptado de Zhana 7e12d54, document_formats.py.
# Origen, decisiones y límites en docs/portados/motores-origen.json.
"""Closed document conversion catalogue and compatible source families."""

from typing import Literal

DocumentTarget = Literal[
    "pdf",
    "docx",
    "doc",
    "odt",
    "rtf",
    "xlsx",
    "xls",
    "ods",
    "csv",
    "pptx",
    "ppt",
    "odp",
    "txt",
    "png",
    "jpg",
    "webp",
    "json",
    "html",
    "md",
]
FORMAT_TARGETS = {
    "pdf": ("pdf", "application/pdf"),
    "png": ("image", "image/png"),
    "jpg": ("image", "image/jpeg"),
    "webp": ("image", "image/webp"),
    "json": ("json", "application/json"),
    "html": ("html", "text/html"),
    "md": ("markdown", "text/markdown"),
    "docx": ("writer", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "doc": ("writer", "application/msword"),
    "odt": ("writer", "application/vnd.oasis.opendocument.text"),
    "rtf": ("writer", "application/rtf"),
    "xlsx": ("spreadsheet", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "xls": ("spreadsheet", "application/vnd.ms-excel"),
    "ods": ("spreadsheet", "application/vnd.oasis.opendocument.spreadsheet"),
    "csv": ("spreadsheet", "text/csv"),
    "pptx": (
        "presentation",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
    "ppt": ("presentation", "application/vnd.ms-powerpoint"),
    "odp": ("presentation", "application/vnd.oasis.opendocument.presentation"),
    "txt": ("text", "text/plain"),
}
ALIASES = {
    "word": "docx",
    "documento": "docx",
    "excel": "xlsx",
    "powerpoint": "pptx",
    "texto": "txt",
    "jpeg": "jpg",
    "markdown": "md",
}


def normalize_target(value: str) -> str:
    name = value.strip().lower().removeprefix(".")
    return ALIASES.get(name, name)


NEW_CONVERSION_ROUTES = {
    ("png", "jpg"),
    ("jpg", "png"),
    ("png", "webp"),
    ("webp", "png"),
    ("jpg", "webp"),
    ("webp", "jpg"),
    ("png", "pdf"),
    ("jpg", "pdf"),
    ("webp", "pdf"),
    ("tiff", "pdf"),
    ("pdf", "png"),
    ("pdf", "jpg"),
    ("csv", "json"),
    ("json", "csv"),
    ("json", "xlsx"),
    ("xlsx", "json"),
    ("docx", "html"),
    ("html", "docx"),
    ("docx", "md"),
    ("md", "html"),
}

VARIETY_ROUTES = NEW_CONVERSION_ROUTES


def supports_plan(source: str, target: str) -> bool:
    if (source, target) in NEW_CONVERSION_ROUTES or (source == "txt" and target == "html"):
        return True
    legacy = {
        "pdf",
        "docx",
        "doc",
        "odt",
        "rtf",
        "xlsx",
        "xls",
        "ods",
        "csv",
        "pptx",
        "ppt",
        "odp",
        "txt",
    }
    if source == "txt" and target == "json":
        return True
    if source in {"json", "html"} and target in {"txt", "pdf"}:
        return True
    if source == "md" and target in {"txt", "pdf", "docx", "doc", "odt", "rtf"}:
        return True
    if source not in legacy or target not in legacy:
        return False
    sf, tf = FORMAT_TARGETS[source][0], FORMAT_TARGETS[target][0]
    return (
        source == target
        or target in ("pdf", "txt")
        or sf == tf
        or (sf == "pdf" and tf in ("writer", "spreadsheet", "presentation"))
        or (sf == "text" and tf in ("writer", "spreadsheet"))
    )


def present_conversion_note(target: str) -> str:
    if target in ("docx", "doc", "odt", "rtf"):
        return "Si el origen es PDF, la edición y el diseño pueden variar."
    if target in ("xlsx", "xls", "ods", "csv"):
        return "Si el origen es PDF, se extraen tablas detectadas; revisa los datos."
    if target in ("pptx", "ppt", "odp"):
        return "Si el origen es PDF, las páginas se representan como imágenes en diapositivas."
    return ""


def conversion_notice(source: str, target: str, actual_suffix: str = "") -> str:
    notices = []
    if source in ("json", "html") and target in ("txt", "pdf"):
        notices.append("El contenido se presenta como texto plano, sin interpretar su formato.")
    family = FORMAT_TARGETS.get(target, ("", ""))[0]
    if source == "pdf" and family == "writer":
        notices.append("El texto editable y el diseño pueden diferir del PDF original.")
    elif source == "pdf" and family == "spreadsheet":
        notices.append(
            "Se recuperan tablas detectadas; no se recuperan fórmulas y debes revisar los datos."
        )
    elif source == "pdf" and family == "presentation":
        notices.append("Cada página se presenta como imagen; su texto no se puede editar.")
    if target == "csv":
        notices.append(
            "Las fórmulas usan el valor guardado, si existe; los textos con aspecto de fórmula se neutralizan."
        )
        if actual_suffix.lstrip(".") == "zip":
            notices.append("Cada hoja está en un CSV dentro del ZIP.")
    if target == "txt" and source in ("xlsx", "xls", "ods"):
        notices.append("Las fórmulas usan el valor guardado, si existe.")
    if target in ("jpg", "pdf") and source in ("png", "webp", "tiff"):
        notices.append("La transparencia se reemplaza por fondo blanco.")
    if source == "pdf" and target in ("png", "jpg") and actual_suffix.lstrip(".") == "zip":
        notices.append("Cada página está en una imagen dentro del ZIP.")
    if (source, target) in {("csv", "json"), ("json", "csv"), ("json", "xlsx"), ("xlsx", "json")}:
        notices.append(
            "Se convierten datos tabulares simples; las fórmulas usan su valor guardado, si existe."
        )
    if (source, target) in {("json", "xlsx"), ("html", "docx")}:
        notices.append("Los caracteres no admitidos por XML se representan como códigos \\uXXXX.")
    if (source, target) in {
        ("docx", "html"),
        ("html", "docx"),
        ("docx", "md"),
        ("md", "html"),
        ("txt", "html"),
    }:
        notices.append("Se conserva el contenido básico; el diseño y las imágenes pueden variar.")
    return " ".join(notices)
