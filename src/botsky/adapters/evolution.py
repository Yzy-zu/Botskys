"""Transporte Evolution explícito: webhook durable, medios acotados, un POST por parte."""

import hashlib
import json
import mimetypes
import os
from dataclasses import replace
from uuid import uuid4

import httpx

from .. import access, ingress
from ..artifacts import INPUT_BYTES, ArtifactProblem
from ..contracts import CommandContext, DeliveryAck, Result, canonical
from ..engines.media_stream import Base64JSONWriter, StreamMediaError, json_file_body
from ..local_files import private_directory
from .evolution_normalize import _content, normalize
from .messenger import MessageError, Messenger


class EvolutionTransport:
    def __init__(self, app, config, http):
        self.app, self.settings, self.http = app, app.settings, http
        self.api = Messenger(
            config.get("base_url"), config.get("instance"), config.get("api_key"), client=http
        )
        if not self.api.available or self.settings.transport != "evolution":
            raise ValueError("evolution_configuration_required")
        self.instance = config["instance"]
        from urllib.parse import quote

        self.instance_path = quote(self.instance, safe="")
        self.delivery_enabled = (
            app.operations.document["delivery"]["send"]
            if app.operations
            else config.get("delivery_enabled", False) is True
        )

    def enqueue(self, payload):
        found = normalize(payload, self.settings, self.instance, self.app.clock())
        if found is None:
            return {"ignored": True}
        incoming, record, size = found
        # Stable normalized content excludes volatile webhook/server metadata.
        raw = {
            "incoming": {
                "text": incoming.text,
                "scope": [incoming.scope.actor, incoming.scope.chat, incoming.scope.is_group],
                "source_ms": incoming.source_ms,
                "historical": incoming.historical,
                "quote": incoming.quoted_message_id,
                "mentions": incoming.mentioned_ids,
            },
            "record": record,
            "size": size,
        }
        fingerprint = hashlib.sha256(canonical(raw).encode()).hexdigest()
        # Retain only fields required to normalize again, not display names or API keys.
        saved = {
            "event": "messages.upsert",
            "instance": self.instance,
            "data": {
                k: payload["data"][k]
                for k in ("key", "message", "messageTimestamp", "contextInfo", "historical", "type")
                if k in payload["data"]
            },
        }
        with self.app.store.transaction() as db:
            prior = db.execute(
                "SELECT fingerprint,epoch FROM transport_inbox WHERE id=?", (incoming.id,)
            ).fetchone()
            if prior:
                if prior["fingerprint"] != fingerprint or prior["epoch"] != self.settings.epoch:
                    raise ValueError("transport_message_conflict")
                return {"receipt_id": incoming.id, "duplicate": True}
            count = db.execute(
                "SELECT count(*) FROM transport_inbox WHERE state='pending'"
            ).fetchone()[0]
            if count >= 128:
                raise OverflowError("transport_queue_full")
            db.execute(
                "INSERT INTO transport_inbox VALUES(?,?,?,?,?,?,'pending',NULL,?)",
                (
                    incoming.id,
                    self.settings.instance,
                    self.settings.account,
                    self.settings.epoch,
                    fingerprint,
                    canonical(saved),
                    incoming.received_ms,
                ),
            )
        return {"receipt_id": incoming.id, "duplicate": False}

    async def receive_pending(self, limit=8, *, media=None):
        with self.app.store.transaction() as db:
            rows = db.execute(
                "SELECT * FROM transport_inbox WHERE instance=? AND account=? AND epoch=? AND state='pending' ORDER BY received_ms LIMIT 128",
                (self.settings.instance, self.settings.account, self.settings.epoch),
            ).fetchall()
        processed = 0
        for row in rows:
            if processed >= limit:
                break
            staged = None
            code, state = None, "admitted"
            try:
                incoming, record, size = normalize(
                    json.loads(row["payload"]), self.settings, self.instance, row["received_ms"]
                )
                if media is not None and bool(record) != media:
                    continue
                processed += 1
                context = CommandContext(
                    incoming.id,
                    incoming.instance,
                    incoming.account,
                    incoming.scope,
                    self.settings.epoch,
                    0,
                )
                with self.app.store.transaction() as db:
                    prior = db.execute(
                        "SELECT attachments_json FROM inbox WHERE id=?", (incoming.id,)
                    ).fetchone()
                if prior:
                    incoming = replace(incoming, attachments=tuple(json.loads(prior[0])))
                elif (
                    record
                    and not ingress.freshness(incoming, self.settings, self.app.clock())
                    and not access.authorize("friend", context, self.settings)
                ):
                    if size is not None and size > INPUT_BYTES:
                        raise ArtifactProblem("input_size")
                    staged = await self.download(record)
                if staged:
                    # Store.admit has its own transaction. The runtime serializes ingestion;
                    # a crash after register is harmless and recovered via source identity.
                    with self.app.store.transaction() as db:
                        existing = db.execute(
                            "SELECT id FROM artifacts WHERE instance=? AND account=? AND actor=? AND chat=? AND is_group=? AND epoch=? AND source_message_id=? AND origin='incoming' AND state='active' ORDER BY created_ms LIMIT 1",
                            (*context.scope_key, incoming.message_id),
                        ).fetchone()
                        if existing:
                            identifier = existing[0]
                            staged.path.unlink(missing_ok=True)
                        else:
                            identifier = self.app.artifacts.register(
                                db, staged, context, incoming.message_id, self.app.clock()
                            )
                    incoming = replace(incoming, attachments=(identifier,))
                receipt = self.app.receive(incoming, execute=False)
                if receipt.state == "rejected":
                    state, code = "rejected", receipt.result.code if receipt.result else "rejected"
            except ArtifactProblem as exc:
                state, code = "rejected", exc.code
            except ValueError, httpx.HTTPError, StreamMediaError, TimeoutError:
                state, code = "rejected", "transport_media_unavailable"
            if (
                code
                and not prior
                and not ingress.freshness(incoming, self.settings, self.app.clock())
                and not access.authorize("friend", context, self.settings)
            ):
                self.app.store.admit(
                    incoming,
                    self.settings,
                    lambda c, db: (
                        None,
                        Result(
                            "failed",
                            code,
                            "No pude recuperar un adjunto válido. Vuelve a adjuntarlo y envía el comando de nuevo.",
                        ),
                        "completed",
                    ),
                )
            with self.app.store.transaction() as db:
                db.execute(
                    "UPDATE transport_inbox SET state=?,error_code=?,payload='' WHERE id=? AND state='pending'",
                    (state, code, row["id"]),
                )
        return processed

    async def download(self, record):
        directory = private_directory(self.settings.root, "private/ingress")
        target = directory / (uuid4().hex + ".tmp")
        try:
            with target.open("xb") as stream:
                target.chmod(0o600)
                decoder = Base64JSONWriter(stream, INPUT_BYTES)
                async with self.http.stream(
                    "POST",
                    self.api.base_url + "/chat/getBase64FromMediaMessage/" + self.instance_path,
                    headers={"apikey": self.api._key},
                    json={"message": record, "convertToMp4": False},
                    timeout=300,
                    follow_redirects=False,
                ) as response:
                    if not 200 <= response.status_code < 300:
                        raise ValueError("media_unavailable")
                    async for chunk in response.aiter_bytes(192 * 1024):
                        decoder.feed(chunk)
                    decoder.finish()
            staged = self.app.artifacts.stage(target)
            kind = _content(record["message"])[2]
            formats = {
                "image": {"jpg", "png", "webp"},
                "sticker": {"webp"},
                "audio": {"ogg", "mp3", "aac", "wav", "flac", "mp4"},
                "video": {"mp4", "webm"},
            }
            if kind in formats and staged.format not in formats[kind]:
                staged.path.unlink(missing_ok=True)
                raise ArtifactProblem("media_signature_mismatch")
            return staged
        finally:
            target.unlink(missing_ok=True)

    async def send(self, part):
        c, s = part.context, self.settings
        if not self.delivery_enabled or (c.instance, c.account, c.epoch) != (
            s.instance,
            s.account,
            s.epoch,
        ):
            return DeliveryAck(False)
        if self.app.operations and not self.app.operations.delivers(c.scope.chat):
            return DeliveryAck(False)
        if not part.artifacts:
            try:
                return DeliveryAck(True, await self.api.send(c.scope.chat, "text", text=part.text))
            except MessageError as exc:
                if not exc.uncertain:
                    return DeliveryAck(False)
                raise
        if len(part.artifacts) != 1 or part.text:
            return DeliveryAck(False)
        identifier = part.artifacts[0]
        with self.app.store.transaction() as db:
            row = self.app.artifacts.owned(
                db,
                identifier,
                c,
                self.app.clock(),
                holder=f"delivery-{part.receipt_id}-{part.position}",
            )
            result = db.execute(
                "SELECT result_json FROM inbox WHERE id=?", (part.receipt_id,)
            ).fetchone()
            result_code = json.loads(result[0]).get("code") if result and result[0] else ""
        path = self.app.artifacts.path(identifier)
        digest = hashlib.sha256()
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
            size = 0
            while block := stream.read(192 * 1024):
                digest.update(block)
                size += len(block)
        if size != row["size"] or digest.hexdigest() != row["sha256"]:
            return DeliveryAck(False)
        fmt = row["format"]
        kind = (
            "image"
            if fmt in ("jpg", "jpeg", "png", "webp")
            else "video"
            if fmt == "mp4" and size <= 64 * 1024 * 1024
            else "audio"
            if fmt in ("mp3", "ogg") and size <= 16 * 1024 * 1024
            else "document"
        )
        body = {
            "number": c.scope.chat,
            "mediatype": kind,
            "fileName": "botsky." + fmt,
            "mimetype": mimetypes.guess_type("output." + fmt)[0] or "application/octet-stream",
        }
        endpoint, field = "sendMedia", "media"
        if fmt == "webp" and result_code in ("sticker_created", "reaction_ready"):
            if size > 100 * 1024:
                return DeliveryAck(False)
            endpoint, field, body = "sendSticker", "sticker", {"number": c.scope.chat}
        elif fmt == "ogg" and result_code == "voice_ready":
            if size > 10 * 1024 * 1024:
                return DeliveryAck(False)
            endpoint, field, body = (
                "sendWhatsAppAudio",
                "audio",
                {"number": c.scope.chat, "encoding": False},
            )
        content = json_file_body(body, path, field=field)
        try:
            async with self.http.stream(
                "POST",
                self.api.base_url + "/message/" + endpoint + "/" + self.instance_path,
                headers={"apikey": self.api._key, "Content-Type": "application/json"},
                content=content,
                timeout=300,
                follow_redirects=False,
            ) as response:
                if 400 <= response.status_code < 500 and response.status_code != 409:
                    return DeliveryAck(False)
                if not 200 <= response.status_code < 300:
                    raise MessageError("delivery_uncertain")
                data = bytearray()
                async for block in response.aiter_bytes():
                    data.extend(block)
                    if len(data) > 65536:
                        raise MessageError("invalid_ack")
                result = json.loads(data)
                provider_id = result.get("key", {}).get("id")
                if not isinstance(provider_id, str) or not 0 < len(provider_id) <= 256:
                    raise MessageError("invalid_ack")
                return DeliveryAck(True, provider_id)
        finally:
            await content.aclose()
