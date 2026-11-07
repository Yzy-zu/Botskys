"""Familias de comunidad: reglas y consentimiento explícitos antes del efecto."""

from . import Block, Document, attach_document


def present(result, zone):
    from .domains import STATES, date_time, tabular

    data, code = result.data, result.code
    if code == "pack_offer" and "category" in data:
        return attach_document(
            result,
            Document(
                (
                    Block("heading", "Oferta de pack"),
                    Block("literal", "Categoría: " + data["category"]),
                    Block(
                        "paragraph",
                        f"Precio: {data['price']} XP · {data['min_photos']}–{data['max_photos']} fotos (mínimo 3 según stock). Visualización única en tu privado.",
                    ),
                    Block(
                        "notice",
                        "No he cobrado. Rechazo conocido devuelve su parte; incertidumbre la conserva sin reenviar. Vence: "
                        + date_time(data["expires_ms"], zone),
                    ),
                    Block("next_action", "/pack confirmar " + data["purchase_id"]),
                )
            ),
        )
    if code == "pack_status":
        return tabular(
            result,
            "Entrega de pack",
            ("Foto", "Estado", "XP"),
            [
                (p["position"] + 1, STATES.get(p["state"], p["state"]), p["cost"])
                for p in data["parts"]
            ],
            intro=f"Precio: {data['price']} XP · Devuelto: {data['refund']} XP · {STATES.get(data['state'], data['state'])}",
            footer="La entrega aceptada por el servicio no acredita lectura. Las partes inciertas no se reenvían automáticamente.",
        )
    if code == "roulette_board" and "bet" in data:
        identifier = data["room_id"]
        blocks = [
            Block("heading", "Ruleta · sala abierta"),
            Block(
                "paragraph",
                f"Apuesta: {data['bet']} XP por persona · {data['players']}/6 participantes; se necesitan al menos 2.",
            ),
            Block(
                "notice",
                "Una persona elegida recibe expulsión de 20 minutos; si se permiten administradores, su degradación es permanente. Dueño y bots protegidos; administradores protegidos por defecto. El resto comparte el pozo redondeado hacia abajo.",
            ),
            Block(
                "notice",
                "Para expulsión se enviará invitación por privado tras 20 minutos, sujeto a identidad/número verificados y privado disponible. Una entrega o acción incierta no se repite.",
            ),
            Block(
                "paragraph",
                "Asientos: "
                + (", ".join("#" + str(seat) for seat in data["seats"]) or "Sin participantes"),
            ),
            Block(
                "notice",
                "Al entrar después de recibir estas reglas aceptas la apuesta, el efecto y el aviso privado.",
            ),
            Block("next_action", "/ruleta entrar " + identifier),
            Block("next_action", "/ruleta jugar " + identifier),
        ]
        return attach_document(result, Document(tuple(blocks)))
    if code in ("nuclear_status",):
        return tabular(
            result,
            "Estado de operación nuclear",
            ("Estado de destinatarios", "Cantidad"),
            [(STATES.get(state, state), count) for state, count in data["counts"].items()],
            intro=f"Coste: {data['cost']} XP · {STATES.get(data['state'], data['state'])}",
            footer="Una parte incierta conserva su estado y no se repite. No se restauran participantes por cambiar la presentación.",
        )
    if code == "nuclear_preview":
        identifier = data["draft_id"]
        return attach_document(
            result,
            Document(
                (
                    Block("heading", "Vista previa nuclear"),
                    Block(
                        "paragraph",
                        f"Se seleccionaron {data['count']} miembros no administradores elegibles de este grupo. Coste: {data['cost']} XP si se confirma.",
                    ),
                    Block(
                        "notice",
                        "Se expulsará a los miembros elegibles verificados. Dueño, bots y administradores están protegidos. Sin cargo ni expulsiones todavía. La vista caduca en 5 minutos.",
                    ),
                    Block("next_action", "/admin nuclear-confirmar " + identifier),
                    Block("next_action", "/admin nuclear-cancelar " + identifier),
                )
            ),
        )
    if code in ("admin_completed", "admin_failed", "admin_uncertain") and data.get("action"):
        labels = {
            "kick": "Expulsar",
            "ban": "Bloquear",
            "promote": "Promover a administrador",
            "demote": "Retirar administración",
            "mute": "Solo administradores pueden enviar",
            "unmute": "Todos pueden enviar",
            "lock": "Restringir cambios del grupo",
            "unlock": "Permitir cambios del grupo",
        }
        status = (
            "Aceptado por el servicio"
            if code == "admin_completed"
            else "Rechazado"
            if code == "admin_failed"
            else "Resultado incierto"
        )
        blocks = [
            Block("heading", "Administración"),
            Block(
                "paragraph",
                labels.get(data["action"], "Acción administrativa")
                + " · "
                + data.get("target_label", "Destino verificado"),
            ),
            Block(
                "notice",
                status
                + ". No se repite una acción incierta. La aceptación no acredita percepción humana.",
            ),
        ]
        return attach_document(result, Document(tuple(blocks)))
    if code == "coop_preview" and "target" in data:
        return attach_document(
            result,
            Document(
                (
                    Block("heading", "Cooperacha · previa censurada"),
                    Block("literal", "Categoría: " + data["category"]),
                    Block(
                        "paragraph",
                        f"Meta: {data['target']} XP. Cada persona aporta solo de su propio saldo. Vence 10 minutos después de aceptar esta vista completa.",
                    ),
                    Block(
                        "notice",
                        "Al completar se publica la foto original en este grupo. Al vencer se devuelve 80% por persona, redondeado hacia abajo; cancelación o fallo conocido 100%; entrega incierta retiene el saldo sin reenviar.",
                    ),
                    Block("next_action", "/coop aportar " + data["challenge_id"] + " 50"),
                )
            ),
        )
    if code == "happy_started" and "duration_seconds" in data:
        return attach_document(
            result,
            Document(
                (
                    Block("heading", "Hora feliz"),
                    Block(
                        "paragraph",
                        f"Duración: {data['duration_seconds']} s desde la entrega completa de este aviso. 20 XP por mensaje normal del grupo; packs a 75 XP cuando estén disponibles.",
                    ),
                    Block("next_action", "/hh estado " + data["event_id"]),
                )
            ),
        )
    if code == "happy_drop_announced":
        return attach_document(
            result,
            Document(
                (
                    Block("heading", "AirDrop · 500 XP"),
                    Block(
                        "notice",
                        "Gana la primera reclamación posterior a la entrega de este aviso.",
                    ),
                    Block("next_action", "/hh reclamar " + data["drop_id"]),
                )
            ),
        )
    return result
