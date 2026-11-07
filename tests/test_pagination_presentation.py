"""Los comandos de continuación conservan filtro/ámbito, incluso tras otra lista."""

from unittest import TestCase

import test_organization

from botsky.adapters.local import CollectingTransport
from botsky.presentation.domains import present


class PaginationPresentationTest(TestCase):
    setUp = test_organization.OrganizationTest.setUp
    incoming = test_organization.OrganizationTest.incoming
    receive = test_organization.OrganizationTest.receive
    rows = test_organization.OrganizationTest.rows

    def test_memory_and_closed_lists_keep_explicit_filters_on_next_page(self):
        for i in range(21):
            self.receive(f"/mem guardar --tipo preferencia Preferencia {i}")
        self.receive("/mem guardar --tipo hecho Hecho separado")
        found = self.receive("/mem listar --tipo preferencia")
        self.assertEqual(found.result.data["filters"], {"kind": "preferencia"})
        shown = present(found.result)
        command = "/mem listar --pagina 2 --tipo preferencia"
        self.assertIn(command, shown.text)
        following = self.receive(command)
        self.assertEqual(following.result.data["total"], 21)
        self.assertEqual(len(following.result.data["items"]), 1)
        for i in range(21):
            self.receive(f"/recordar en 10m Aviso {i}")
        found = self.receive("/recordatorios --cerradas")
        shown = present(found.result)
        self.assertIn("/recordatorios --pagina 2 --cerradas", shown.text)
        self.assertTrue(found.result.data["filters"]["include_closed"])

    def test_note_filter_is_explicit_even_after_a_different_delivered_search(self):
        for i in range(6):
            self.receive(f"/nota guardar Clave {i}")
        for i in range(6):
            self.receive(f"/nota guardar Otra {i}")
        filtered = self.receive("/notas Clave")
        self.app.deliver(filtered.id, CollectingTransport())
        another = self.receive("/notas Otra")
        self.app.deliver(another.id, CollectingTransport())
        command = "/notas --pagina 2 -- Clave"
        self.assertIn(command, present(filtered.result).text)
        next_page = self.receive(command)
        self.assertEqual(next_page.result.data["query"], "Clave")
        self.assertTrue(all("Clave" in row["text"] for row in next_page.result.data["items"]))
        self.assertEqual(next_page.result.data["total"], 6)
