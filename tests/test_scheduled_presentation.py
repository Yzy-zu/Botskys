"""Avisos propios materializados: texto literal y resúmenes sin corte silencioso."""

from unittest import TestCase

import test_organization

from botsky.adapters.local import CollectingTransport


class ScheduledPresentationTest(TestCase):
    setUp = test_organization.OrganizationTest.setUp
    incoming = test_organization.OrganizationTest.incoming
    receive = test_organization.OrganizationTest.receive
    rows = test_organization.OrganizationTest.rows
    result = test_organization.OrganizationTest.result

    def test_reminder_notice_keeps_literal_and_timezone_without_executing_its_content(self):
        source = "*Aviso* /daily\n/nota guardar NO"
        self.receive("/recordar en 1m " + source)
        self.now += 60000
        receipt = self.app.scheduler.tick()[0]
        transport = CollectingTransport()
        self.app.deliver(receipt, transport)
        text = "".join(p.text for p in transport.parts)
        self.assertIn("```\n" + source + "\n```", text)
        self.assertIn("America/Mexico_City", text)
        self.assertEqual(self.rows("SELECT * FROM notes"), [])
        self.assertEqual(self.rows("SELECT * FROM xp_entries"), [])

    def test_school_digest_retains_long_included_tasks_and_declares_twenty_of_twenty_one(self):
        group = {"chat": "group", "is_group": True}
        for i in range(21):
            created = self.receive(
                f"/tarea crear --fecha 2026-11-07 TAREA_{i}: " + ("contenido literal " * 50),
                **group,
            )
            self.assertEqual(created.result.code, "school_task_created")
        configured = self.receive(
            "/escuela resumen configurar si --hora 09:00", actor="owner", **group
        )
        self.assertEqual(configured.result.code, "school_digest_status")
        self.now += 86400000
        emitted = self.app.scheduler.tick()
        self.assertEqual(len(emitted), 1)
        result = self.result(emitted[0])
        self.assertGreater(len(result.text), 6000)
        self.assertIn("TAREA_19", result.text)
        self.assertIn("20 de 21", result.text)
        self.assertNotIn("TAREA_20:", result.text)
        self.assertIn("/tareas", result.text)
        self.assertEqual(self.app.scheduler.tick(), [])
