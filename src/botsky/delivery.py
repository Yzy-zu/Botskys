"""Entrega por partes: reservar antes de enviar, nunca repetir una parte incierta."""

from .contracts import DeliveryAck


def deliver(store, receipt_id, settings, transport, clock, *, retry_failed=False):
    accepted = 0
    while claimed := store.claim_part(receipt_id, settings, clock(), retry_failed=retry_failed):
        part, revision = claimed
        try:
            ack = transport.send(part)
            if not isinstance(ack, DeliveryAck):
                raise ValueError("ACK inválido")
            if ack.accepted is False:
                state, code, provider_id = "failed", "delivery_rejected", None
            elif ack.accepted is True and isinstance(ack.message_id, str) and ack.message_id:
                state, code, provider_id = "accepted", None, ack.message_id
            else:
                raise ValueError("ACK ambiguo")
        except Exception:
            state, code, provider_id = "uncertain", "delivery_uncertain", None
        store.finish_part(part, revision, settings, state, provider_id, code, clock())
        if state != "accepted":
            break
        accepted += 1
    return accepted
