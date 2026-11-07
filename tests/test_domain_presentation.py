"""Contenido y planes enriquecidos a partir de hechos sintéticos de dominio."""

from unittest import TestCase

import test_organization

from botsky.adapters.local import CollectingTransport
from botsky.contracts import Result
from botsky.presentation.domains import filename, present, size


class DomainPresentationTest(TestCase):
    setUp = test_organization.OrganizationTest.setUp
    incoming = test_organization.OrganizationTest.incoming
    receive = test_organization.OrganizationTest.receive
    rows = test_organization.OrganizationTest.rows

    def parts(self, receipt):
        transport = CollectingTransport()
        self.app.deliver(receipt.id, transport)
        return transport.parts

    def test_real_sqlite_reminder_schedule_and_poll_table_payloads(self):
        self.app.store.native_tables_enabled = True
        self.receive("/recordar en 10m Texto literal /daily")
        reminders = self.receive("/recordatorios")
        parts = self.parts(reminders)
        table = next(p for p in parts if p.kind == "table")
        self.assertEqual(table.payload["rows"][0][3], "Texto literal /daily")
        self.assertIn("America/Mexico_City", table.payload["rows"][0][1])
        self.assertIn("600", str(reminders.result.data["items"][0]["due_ms"] - self.now))
        self.receive(
            "/horario agregar --materia Matemáticas --dia 1 --inicio 08:00 --fin 09:00",
            actor="owner",
        )
        schedule = self.receive("/horario listar", actor="owner")
        table = next(p for p in self.parts(schedule) if p.kind == "table")
        self.assertEqual(table.payload["rows"][0][1:], ["Lunes", "08:00–09:00", "Matemáticas"])
        poll = self.receive('/encuesta crear "¿Hora?" "Dos *literal*" "Tres"')
        self.parts(poll)
        results = self.receive("/encuesta resultados " + str(poll.result.data["poll_id"]))
        parts = self.parts(results)
        self.assertEqual(parts[0].text, "¿Hora?")
        table = next(p for p in parts if p.kind == "table")
        self.assertEqual(table.payload["rows"][0], ["1", "Dos *literal*", "0"])
        self.assertIn("0 participantes", parts[-1].text)

    def test_drive_units_full_fields_native_and_fallback_are_equivalent(self):
        result = Result(
            "needs_input",
            "drive_choices",
            "raw",
            {
                "view_id": "private-reference",
                "choices": [{"name": "archivo*literal*.pdf", "size": 1024}],
            },
        )
        shown = present(result)
        self.assertIn("1.00 KiB (1024 bytes)", shown.text)
        self.assertEqual(
            shown.data["native_tables"][0]["rows"][0],
            ["1", "archivo*literal*.pdf", "1.00 KiB (1024 bytes)"],
        )
        self.assertIn("/drive elegir NUMERO", shown.text)
        quota = present(
            Result(
                "ok",
                "drive_capacity",
                "raw",
                {"quota": {"limit": 2000000000, "usage": 1000000000, "usageInDrive": None}},
            )
        )
        self.assertIn("1.00 GB (1000000000 bytes)", quota.text)
        self.assertIn("Desconocido", quota.text)
        self.assertIn("compartida", quota.text)
        self.assertEqual(size(None), "Desconocido")
        self.assertEqual(filename("../secreto/Nombre: vídeo?.mp4", "mp3"), "Nombre vídeo.mp3")

    def test_large_cells_never_lose_text_or_dates_to_force_native_table(self):
        text = "*literal* /daily\n" * 400
        result = Result(
            "ok",
            "organization_list",
            "raw",
            {
                "items": [{"id": 1, "due_ms": self.now, "state": "uncertain", "text": text}],
                "page": 1,
                "pages": 1,
                "total": 1,
                "list_kind": "reminders",
            },
        )
        shown = present(result)
        self.assertIn(text, shown.text)
        self.assertIn("America/Mexico_City", shown.text)
        self.assertIn("incierto", shown.text)
        self.assertNotIn("native_tables", shown.data)
        self.assertEqual(result.text, "raw")
