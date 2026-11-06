"""Entrega por partes: reservar antes de enviar, nunca repetir una parte incierta."""

import asyncio

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


async def deliver_async(store, receipt_id, settings, transport, clock):
    """Mismo CAS/recibos para transporte asíncrono; cancelación conserva incertidumbre."""
    accepted = 0
    while claimed := store.claim_part(receipt_id, settings, clock()):
        part, revision = claimed
        state, code, provider_id = "uncertain", "delivery_uncertain", None
        try:
            ack = await transport.send(part)
            if not isinstance(ack, DeliveryAck):
                raise ValueError("invalid_ack")
            if ack.accepted is False:
                state, code = "failed", "delivery_rejected"
            elif ack.accepted is True and isinstance(ack.message_id, str) and ack.message_id:
                state, code, provider_id = "accepted", None, ack.message_id
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            store.finish_part(part, revision, settings, state, provider_id, code, clock())
        if state != "accepted":
            break
        accepted += 1
    return accepted
