"""Ficción explícita, sin búsqueda ni contacto a terceros."""

import hashlib

from ..contracts import Result


def execute(context, args):
    label = args.get("label") or "Personaje ficticio"
    if (
        not 0 < len(label) <= 40
        or not any(c.isalpha() for c in label)
        or not all(c.isalpha() or c in " -" for c in label)
    ):
        return Result(
            "needs_input",
            "prank_invalid_label",
            "Usa una etiqueta ficticia de letras, espacios o guiones, sin identificadores.",
        )
    texts = (
        "El club imaginario de patitos nombró a {label} inspector de charcos.",
        "El comité inventado de tostadoras concedió a {label} una medalla por sus siestas.",
        "El registro ficticio de calcetines reservó una nube de confeti para {label}.",
    )
    index = hashlib.sha256(context.receipt_id.encode()).digest()[0] % len(texts)
    return Result(
        "ok",
        "prank_fiction",
        "FICCIÓN · BROMA INOCUA\n"
        + texts[index].format(label=label)
        + "\nDominio de ejemplo: patitos.invalid. No investigué a nadie ni envié nada a terceros.\nFIN DE FICCIÓN",
    )
