"""Vistas previas reales de dominio propio; efectos externos solo dobles."""

from unittest import IsolatedAsyncioTestCase, TestCase

import test_admin
import test_packs
from PIL import Image, ImageDraw

from botsky.adapters.local import CollectingTransport
from botsky.contracts import Result
from botsky.presentation.domains import present


class OfferPresentationTest(IsolatedAsyncioTestCase):
    asyncSetUp = test_packs.PacksTest.asyncSetUp
    incoming = test_packs.PacksTest.incoming
    receive = test_packs.PacksTest.receive
    rows = test_packs.PacksTest.rows
    result = test_packs.PacksTest.result

    async def test_pack_offer_keeps_cost_private_delivery_and_confirm_token_without_charging(self):
        self.receive("/daily")
        offer = self.receive("/pack comprar sintetico")
        before = self.rows("SELECT balance FROM wallets WHERE actor=?", ("alice",))[0]["balance"]
        transport = CollectingTransport()
        self.app.deliver(offer.id, transport)
        text = "\n".join(part.text for part in transport.parts)
        for phrase in (
            "150 XP",
            "visualización única",
            "privado",
            "No he cobrado",
            "Rechazo conocido",
            "incertidumbre",
            "/pack confirmar " + offer.result.data["purchase_id"],
        ):
            self.assertIn(phrase.lower(), text.lower())
        self.assertEqual(
            self.rows("SELECT balance FROM wallets WHERE actor=?", ("alice",))[0]["balance"], before
        )
        self.assertEqual(self.transport.calls, [])

    async def test_coop_preview_is_actual_censored_image_and_requires_whole_composition(self):
        # Reemplazar únicamente activos del fixture propio por un patrón fino.
        for file in (self.root / "private/gallery/originals").glob("*.png"):
            image = Image.new("RGB", (64, 64))
            draw = ImageDraw.Draw(image)
            for y in range(64):
                for x in range(64):
                    draw.point((x, y), fill="white" if (x + y) % 2 else "black")
            image.save(file)
        receipt = self.receive("/coop crear sintetico 100", chat="group", is_group=True)
        await self.app.jobs.run_pending()
        result = self.result(receipt)
        self.assertEqual(result.code, "coop_preview")
        preview = self.app.artifacts.path(result.data["artifacts"][0])
        with Image.open(preview) as image:
            image.load()
            self.assertEqual(image.format, "JPEG")
            self.assertLess(image.getextrema()[0][1] - image.getextrema()[0][0], 100)
        first, rev = self.app.store.claim_part(receipt.id, self.settings, self.now)
        self.assertTrue(first.artifacts)
        self.app.store.finish_part(
            first, rev, self.settings, "accepted", "censored-image", None, self.now
        )
        challenge = result.data["challenge_id"]
        self.assertEqual(
            self.rows("SELECT state FROM cooperachas WHERE id=?", (challenge,))[0]["state"],
            "publishing",
        )
        transport = CollectingTransport()
        self.app.deliver(receipt.id, transport)
        text = "\n".join(p.text for p in transport.parts)
        for phrase in (
            "100 XP",
            "80%",
            "100%",
            "foto original",
            "10 minutos",
            "/coop aportar " + challenge + " 50",
        ):
            self.assertIn(phrase, text)
        self.assertEqual(
            self.rows("SELECT state FROM cooperachas WHERE id=?", (challenge,))[0]["state"], "open"
        )
        self.assertEqual(self.transport.calls, [])


class NuclearPresentationTest(IsolatedAsyncioTestCase):
    asyncSetUp = test_admin.AdminTest.asyncSetUp
    incoming = test_admin.AdminTest.incoming
    receive = test_admin.AdminTest.receive
    rows = test_admin.AdminTest.rows
    result = test_admin.AdminTest.result
    command = test_admin.AdminTest.command

    async def test_nuclear_preview_is_not_a_confirmation_and_keeps_scope_cost_and_protection(self):
        self.app.nuclear_enabled = True
        receipt, result = await self.command("/admin nuclear-preparar")
        transport = CollectingTransport()
        self.app.deliver(receipt.id, transport)
        text = "\n".join(p.text for p in transport.parts)
        for phrase in (
            "5000 XP",
            "2 miembros",
            "Dueño",
            "administradores",
            "Sin cargo",
            "/admin nuclear-confirmar " + result.data["draft_id"],
            "/admin nuclear-cancelar " + result.data["draft_id"],
        ):
            self.assertIn(phrase, text)
        self.assertEqual(self.groups.calls, [])
        self.assertEqual(
            self.rows("SELECT count(*) AS n FROM xp_entries WHERE kind='nuclear'"), [{"n": 0}]
        )


class OperationalPresentationTest(TestCase):
    def test_minecraft_worlds_config_and_backup_never_show_raw_json_or_assume_game_load(self):
        worlds = present(
            Result(
                "ok",
                "minecraft_completed",
                "raw",
                {
                    "action": "worlds",
                    "response": {"worlds": [{"name": "Mundo *literal*", "active": True}]},
                },
            )
        )
        self.assertEqual(worlds.data["native_tables"][0]["rows"], [["Mundo *literal*", "Sí"]])
        self.assertIn("Mundo establecido", worlds.text)
        backup = present(
            Result(
                "ok",
                "minecraft_completed",
                "raw",
                {
                    "action": "backup",
                    "response": {"backup": "fixture.tar.gz", "bytes": 1024, "files": 2},
                },
            )
        )
        self.assertIn("Datos incluidos: 1.00 KiB", backup.text)
        self.assertIn("Respaldo creado", backup.text)
        self.assertNotIn("{", backup.text)
        config = present(
            Result(
                "ok",
                "minecraft_completed",
                "raw",
                {
                    "action": "config",
                    "response": {"properties": {"gamemode": "creative", "level-name": "Mundo"}},
                },
            )
        )
        self.assertIn(["Modo de juego", "creative"], config.data["native_tables"][0]["rows"])
        self.assertNotIn("{", config.text)
