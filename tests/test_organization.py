"""R5: SQLite y scheduler local; datos sintéticos, sin mensajes ni proveedores remotos."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from PIL import Image

from botsky.adapters.local import CollectingTransport, LocalAdapter
from botsky.app import Application
from botsky.config import Settings
from botsky.contracts import Result


class OrganizationTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = int(datetime.fromisoformat("2026-11-06T15:00:00+00:00").timestamp() * 1000)
        self.settings = Settings(
            self.root,
            "org-lab",
            "local",
            1,
            self.root / "private/test.sqlite3",
            self.now - 1000,
            "owner",
            frozenset({"alice", "bob"}),
            frozenset({"group"}),
        )
        self.app = Application(self.settings, clock=lambda: self.now)
        self.adapter = LocalAdapter(self.settings, lambda: self.now)
        self.sequence = 0

    def incoming(self, text, *, actor="alice", chat="private", **kw):
        self.sequence += 1
        return self.adapter.incoming(str(self.sequence), actor, chat, text, **kw)

    def receive(self, text, **kw):
        return self.app.receive(self.incoming(text, **kw))

    def rows(self, sql, params=()):
        db = self.app.store.connect()
        try:
            return [dict(r) for r in db.execute(sql, params)]
        finally:
            db.close()

    def result(self, identifier):
        return Result.from_json(
            self.rows("SELECT result_json FROM inbox WHERE id=?", (identifier,))[0]["result_json"]
        )

    def test_memory_literal_ownership_correction_confirmation_stale_and_no_id_reuse(self):
        first = self.receive("/mem guardar --tipo preferencia -- Cable EXACTO; /daily")
        identifier = first.result.data["memory_id"]
        self.assertEqual(
            self.receive("/mem listar").result.data["items"][0]["text"], "Cable EXACTO; /daily"
        )
        self.assertEqual(
            self.receive("/mem olvidar " + str(identifier), actor="bob").result.code,
            "memory_not_found",
        )
        preview = self.receive("/mem borrar-todo")
        confirmation = preview.result.data["confirmation_id"]
        self.assertEqual(
            self.receive("/confirmar " + confirmation).result.code, "confirmation_unavailable"
        )
        self.app.deliver(preview.id, CollectingTransport())
        self.receive("/mem corregir " + str(identifier) + " reemplazo")
        self.assertEqual(
            self.receive("/confirmar " + confirmation).result.code, "confirmation_stale"
        )
        preview = self.receive("/mem borrar-todo")
        confirmation = preview.result.data["confirmation_id"]
        self.app.deliver(preview.id, CollectingTransport())
        self.assertEqual(
            self.receive("/confirmar " + confirmation, actor="bob").result.code,
            "confirmation_unavailable",
        )
        self.assertEqual(self.receive("/confirmar " + confirmation).result.code, "memories_deleted")
        self.assertEqual(self.receive("/mem listar").result.data["total"], 0)
        new = self.receive("/mem guardar dato nuevo").result.data["memory_id"]
        self.assertGreater(new, identifier)
        self.assertEqual(
            self.receive("/mem olvidar " + str(identifier)).result.code, "memory_not_found"
        )

    def test_reminder_absolute_interval_restart_tick_and_uncertain_without_repeat(self):
        incoming = self.incoming("/recordar en 10m Cable azul")
        first = self.app.receive(incoming)
        self.assertEqual(first.result.data["due_ms"], self.now + 600000)
        self.assertTrue(self.app.receive(incoming).duplicate)
        self.assertEqual(self.app.scheduler.tick(), [])
        self.now += 600000
        restarted = Application(self.settings, clock=lambda: self.now)
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda _: restarted.scheduler.tick(), range(2)))
        self.assertEqual(sum(len(c) for c in claims), 1)
        identifier = next(c[0] for c in claims if c)
        self.assertEqual(
            self.rows("SELECT origin FROM inbox WHERE id=?", (identifier,))[0]["origin"], "internal"
        )

        class Timeout:
            def send(self, part):
                raise TimeoutError()

        restarted.deliver(identifier, Timeout())
        self.assertEqual(self.rows("SELECT state FROM reminders")[0]["state"], "uncertain")
        self.assertEqual(restarted.scheduler.tick(), [])
        self.assertEqual(restarted.deliver(identifier, CollectingTransport(), retry_failed=True), 0)
        absolute = self.receive("/recordar el 2026-11-07 18:30 pedido literal")
        self.assertEqual(absolute.result.code, "reminder_created")
        self.assertIn("Ciudad de México", absolute.result.text)
        self.assertEqual(
            self.receive("/recordar el 2028-01-01 10:00 fuera").result.code, "invalid_reminder_date"
        )

    def test_reminder_cancel_scope_archive_and_outage_does_not_replay_expired(self):
        first = self.receive("/recordar en 30s uno")
        number = first.result.data["reminder_id"]
        self.assertEqual(
            self.receive("/recordatorio cancelar " + str(number), actor="bob").result.code,
            "reminder_not_found",
        )
        self.assertEqual(
            self.receive("/recordatorio archivar " + str(number)).result.code,
            "reminder_still_pending",
        )
        self.assertEqual(
            self.receive("/recordatorio cancelar " + str(number)).result.code, "reminder_cancelled"
        )
        self.assertEqual(
            self.receive("/recordatorio archivar " + str(number)).result.code, "reminder_archived"
        )
        self.receive("/recordar en 30s vencido")
        self.now += 631000
        self.assertEqual(self.app.scheduler.tick(), [])
        self.assertEqual(
            self.rows("SELECT state FROM reminders WHERE text='vencido'")[0]["state"], "expired"
        )

    def test_poll_full_options_delivered_publication_ownership_and_monotonic_votes(self):
        group = {"chat": "group", "is_group": True}
        created = self.receive('/encuesta crear "¿Qué hora?" "A las dos" "A las tres"', **group)
        identifier = created.result.data["poll_id"]
        self.assertEqual(created.result.data["options"], ["A las dos", "A las tres"])
        self.assertEqual(
            self.receive("/encuesta votar " + str(identifier) + " 1", **group).result.code,
            "poll_not_published",
        )
        self.app.deliver(created.id, CollectingTransport())
        older = self.app.admit(self.incoming("/encuesta votar " + str(identifier) + " 1", **group))
        self.receive("/encuesta votar " + str(identifier) + " 2", **group)
        self.app.process(older.id)
        self.assertEqual(self.rows("SELECT choice FROM poll_votes")[0]["choice"], 2)
        self.receive("/encuesta votar " + str(identifier) + " 1", actor="bob", **group)
        result = self.receive("/encuesta resultados " + str(identifier), **group)
        self.assertEqual(result.result.data["participants"], 2)
        self.assertEqual(
            self.receive("/encuesta cerrar " + str(identifier), actor="bob", **group).result.code,
            "poll_author_required",
        )
        self.receive("/encuesta cerrar " + str(identifier), **group)
        self.assertEqual(
            self.receive("/encuesta votar " + str(identifier) + " 1", **group).result.code,
            "poll_closed",
        )
        self.assertEqual(
            self.receive("/encuesta resultados " + str(identifier), chat="different").result.code,
            "poll_not_found",
        )

    def test_school_task_owner_complete_file_explicit_share_and_grant_revocation(self):
        group = {"chat": "group", "is_group": True}
        path = self.root / "school.png"
        Image.new("RGB", (16, 16), "white").save(path)
        incoming = self.app.attach_local(
            self.incoming(
                "/tarea crear --fecha 2026-11-07 --materia Mate --adjunto resolver ejercicio",
                **group,
            ),
            path,
        )
        created = self.app.receive(incoming)
        self.assertEqual(created.result.code, "school_task_created")
        identifier = created.result.data["task_id"]
        task = self.rows("SELECT * FROM school_tasks")[0]
        self.assertIsNone(task["due_time"])
        self.assertEqual(
            self.receive("/tarea completar " + str(identifier), actor="bob", **group).result.code,
            "task_not_found",
        )
        shared = self.receive("/tarea archivo " + str(identifier), actor="bob", **group)
        self.assertEqual(shared.result.code, "task_attachment")
        transport = CollectingTransport()
        self.assertEqual(self.app.deliver(shared.id, transport), 2)
        self.assertEqual(transport.parts[-1].artifacts, (task["artifact_id"],))
        self.assertEqual(
            self.receive(
                "/tarea archivo " + str(identifier), actor="bob", chat="other"
            ).result.code,
            "task_not_found",
        )
        self.assertEqual(
            self.receive("/tarea completar " + str(identifier), **group).result.code,
            "school_task_completed",
        )
        self.assertEqual(
            self.receive("/tarea borrar " + str(identifier), **group).result.code,
            "school_task_deleted",
        )
        self.assertEqual(self.rows("SELECT * FROM school_asset_grants"), [])
        self.assertEqual(
            self.receive("/tarea archivo " + str(identifier), actor="bob", **group).result.code,
            "task_not_found",
        )

    def test_school_owner_schedule_overlap_and_daily_digest_no_duplicates(self):
        group = {"chat": "group", "is_group": True}
        command = "/horario agregar --materia Mate --dia 5 --inicio 10:00 --fin 11:00"
        self.assertEqual(self.receive(command, **group).result.code, "owner_required")
        self.assertEqual(
            self.receive(command, actor="owner", **group).result.code, "school_lesson_created"
        )
        self.assertEqual(
            self.receive(command, actor="owner", **group).result.code, "school_lesson_overlap"
        )
        self.assertEqual(
            len(self.receive("/horario listar --dia 5", **group).result.data["items"]), 1
        )
        self.assertEqual(
            self.receive("/escuela resumen configurar si --hora 09:00", **group).result.code,
            "owner_required",
        )
        configured = self.receive(
            "/escuela resumen configurar si --hora 09:00", actor="owner", **group
        )
        self.assertEqual(configured.result.code, "school_digest_status")
        claims = self.app.scheduler.tick()
        self.assertEqual(len(claims), 1)
        self.assertIn("Mate", self.result(claims[0]).text)
        self.assertEqual(self.app.scheduler.tick(), [])
        self.receive("/escuela resumen configurar no", actor="owner", **group)
        self.assertEqual(self.app.deliver(claims[0], CollectingTransport()), 0)
        self.assertEqual(self.receive("/escuela resumen estado", **group).result.data["enabled"], 0)

    def test_pending_notice_expiry_pause_and_sent_receipt_are_preserved(self):
        self.receive("/recordar en 30s caducará")
        self.now += 30000
        notice = self.app.scheduler.tick()[0]
        self.assertEqual(
            self.receive("/bot pausa 15", actor="owner").result.code, "bot_mode_updated"
        )
        transport = CollectingTransport()
        self.assertEqual(self.app.deliver(notice, transport), 0)
        self.now += 601000
        self.receive("/bot reanudar", actor="owner")
        self.assertEqual(self.app.deliver(notice, transport), 0)
        self.assertEqual(self.rows("SELECT state FROM reminders")[0]["state"], "expired")
        self.assertEqual(transport.parts, [])
        self.receive("/recordar en 30s entregado")
        self.now += 30000
        notice = self.app.scheduler.tick()[0]
        self.assertEqual(self.app.deliver(notice, transport), 1)
        self.now += 601000
        self.assertEqual(self.app.deliver(notice, transport), 0)
        self.assertEqual(
            self.rows("SELECT state FROM reminders WHERE text='entregado'")[0]["state"], "sent"
        )

    def test_memory_filter_pagination_and_reminder_closed_filter(self):
        for i in range(21):
            self.receive("/mem guardar --tipo dato hecho " + str(i))
        self.receive("/mem guardar --tipo preferencia preferencia separada")
        page = self.receive("/mem listar --tipo dato --pagina 2").result
        self.assertEqual(page.data["total"], 21)
        self.assertEqual(len(page.data["items"]), 1)
        self.assertEqual(page.data["items"][0]["text"], "hecho 20")
        self.assertEqual(
            self.receive("/mem listar --tipo dato --pagina 3").result.code, "page_out_of_range"
        )
        reminder = self.receive("/recordar en 30s filtro").result.data["reminder_id"]
        self.receive("/recordatorio cancelar " + str(reminder))
        self.assertEqual(self.receive("/recordatorios").result.data["total"], 0)
        self.assertEqual(self.receive("/recordatorios --cerradas").result.data["total"], 1)

    def test_digest_delivery_rechecks_current_owner(self):
        from dataclasses import replace

        self.receive(
            "/escuela resumen configurar si --hora 09:00",
            actor="owner",
            chat="group",
            is_group=True,
        )
        notice = self.app.scheduler.tick()[0]
        settings = replace(self.settings, owner="bob", friends=frozenset({"alice", "owner"}))
        restarted = Application(settings, clock=lambda: self.now)
        self.assertEqual(restarted.deliver(notice, CollectingTransport()), 0)

    def test_reserved_reminder_cancel_and_permission_revocation_prevent_transport(self):
        from dataclasses import replace

        first = self.receive("/recordar en 30s revocado").result.data["reminder_id"]
        self.now += 30000
        notice = self.app.scheduler.tick()[0]
        denied = Application(
            replace(self.settings, friends=frozenset({"bob"})), clock=lambda: self.now
        )
        self.assertEqual(denied.deliver(notice, CollectingTransport()), 0)
        self.assertEqual(
            self.receive("/recordatorio cancelar " + str(first)).result.code, "reminder_cancelled"
        )
        self.assertEqual(self.app.deliver(notice, CollectingTransport()), 0)
        self.assertEqual(self.app.scheduler.tick(), [])

    def test_status_catalog_task_listing_and_lesson_delete_keep_data_scoped(self):
        self.assertEqual(self.receive("/bot estado").result.code, "bot_status")
        self.assertIn("/notas", self.receive("/ayuda notas").result.text)
        self.assertEqual(self.receive("/voces").result.code, "voice_catalog")
        self.receive(
            "/tarea crear --materia Historia --fecha 2026-12-01 --hora 12:00 Texto literal",
            actor="owner",
            chat="group",
            is_group=True,
        )
        listing = self.receive("/tareas", chat="group", is_group=True)
        self.assertEqual(len(listing.result.data["items"]), 1)
        self.assertIn("Historia · Texto literal", listing.result.text)
        self.assertIn("2026-12-01 12:00", listing.result.text)
        self.assertIn("Ciudad de México · pendiente", listing.result.text)
        created = self.receive(
            "/horario agregar --materia Mate --dia 5 --inicio 10:00 --fin 11:00",
            actor="owner",
            chat="group",
            is_group=True,
        )
        identifier = created.result.data["lesson_id"]
        denied = self.receive("/horario borrar " + str(identifier), chat="group", is_group=True)
        self.assertEqual(denied.result.code, "owner_required")
        deleted = self.receive(
            "/horario borrar " + str(identifier), actor="owner", chat="group", is_group=True
        )
        self.assertEqual(deleted.result.code, "school_lesson_deleted")
        self.assertEqual(
            self.receive("/horario listar", chat="group", is_group=True).result.data["items"], []
        )
