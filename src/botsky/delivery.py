"""Entrega por partes: reservar antes de enviar, nunca repetir una parte incierta."""

import asyncio

from .contracts import DeliveryAck


def is_optional_part(part):
    return "reaction" in part.payload


def classify_ack(ack):
    if not isinstance(ack, DeliveryAck):
        raise ValueError("invalid_ack")
    if ack.accepted is False:
        return "failed", "delivery_rejected", None
    if ack.accepted is True and isinstance(ack.message_id, str) and ack.message_id:
        return "accepted", None, ack.message_id
    raise ValueError("ambiguous_ack")


def deliver(store, receipt_id, settings, transport, clock, *, retry_failed=False):
    accepted = 0
    while claimed := store.claim_part(receipt_id, settings, clock(), retry_failed=retry_failed):
        part, revision = claimed
        try:
            state, code, provider_id = classify_ack(transport.send(part))
        except Exception:
            state, code, provider_id = "uncertain", "delivery_uncertain", None
        store.finish_part(part, revision, settings, state, provider_id, code, clock())
        if state == "accepted" and part.payload.get("reaction") != "":
            accepted += 1
        elif not is_optional_part(part):
            break
    return accepted


async def deliver_async(store, receipt_id, settings, transport, clock):
    """Mismo CAS/recibos para transporte asíncrono; cancelación conserva incertidumbre."""
    accepted = 0
    while claimed := store.claim_part(receipt_id, settings, clock()):
        part, revision = claimed
        state, code, provider_id = "uncertain", "delivery_uncertain", None
        try:
            state, code, provider_id = classify_ack(await transport.send(part))
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            store.finish_part(part, revision, settings, state, provider_id, code, clock())
        if state == "accepted" and part.payload.get("reaction") != "":
            accepted += 1
        elif not is_optional_part(part):
            break
    return accepted
