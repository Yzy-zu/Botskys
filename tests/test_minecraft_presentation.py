import unittest

from botsky.domains.minecraft import render


class MinecraftPresentationTest(unittest.TestCase):
    def test_mods_are_human_readable_and_include_unambiguous_command(self):
        result = render(
            {
                "world": "survival",
                "mods": [
                    {
                        "name": "Mapas",
                        "enabled": True,
                        "type": "plugin",
                        "version": "1.2",
                        "uuid": "abc-123",
                    }
                ],
            },
            "mods",
        )
        self.assertIn("Mundo: survival", result)
        self.assertIn("Mapas: configurado · plugin · v1.2", result)
        self.assertIn('/mc mod desactivar "abc-123"', result)
        self.assertNotIn("ID: abc-123", result)
        self.assertIn("Carga en juego: desconocida", result)
        self.assertNotIn("{", result)

    def test_mods_warn_on_missing_details_and_empty_or_truncated_results(self):
        result = render(
            {"mods": [{"name": "X", "missing": True, "version_mismatch": True}]}, "mods"
        )
        self.assertIn("falta ID/UUID", result)
        self.assertIn("paquete ausente", result)
        self.assertIn("versión discordante", result)
        self.assertIn("tipo o versión no informados", result)
        self.assertIn("No se recibió una lista", render({}, "mods"))
        self.assertIn("lista truncada", render({"mods": ["x"] * 101}, "mods"))

    def test_mod_mutations_and_restart_do_not_claim_game_load(self):
        enabled = render({"name": "Mapa", "changed": True}, "enable_mod")
        self.assertIn("Activación de Mapa: cambió", enabled)
        self.assertIn("Requiere /mc reiniciar", enabled)
        self.assertIn("Carga en juego no confirmada", enabled)
        disabled = render({"name": "Mapa", "changed": False}, "disable_mod")
        self.assertIn("Desactivación de Mapa: ya estaba así", disabled)
        self.assertIn("si había cambios pendientes", disabled)
        restart = render({"status": "accepted"}, "restart")
        self.assertIn("solo la aceptación del puente", restart)
        self.assertIn("no la disponibilidad posterior", restart)

    def test_base_packs_are_grouped_and_duplicate_uuid_uses_folder(self):
        result = render(
            {
                "active_world": "laboratorio",
                "installed": [
                    {
                        "name": "resourcePack.vanilla_server.name",
                        "pack_id": "base-1",
                        "folder": "base",
                        "pack_type": "resource",
                        "version": [1, 0, 0],
                        "active": True,
                    },
                    {
                        "name": ".vanilla.name",
                        "pack_id": "base-2",
                        "folder": "base2",
                        "pack_type": "resource",
                        "version": [1, 0, 0],
                        "active": True,
                    },
                    {
                        "name": "custom",
                        "pack_id": "same-id",
                        "folder": "custom-behavior",
                        "pack_type": "behavior",
                        "version": [2, 0, 1],
                        "active": True,
                    },
                    {
                        "name": "custom",
                        "pack_id": "same-id",
                        "folder": "custom-resource",
                        "pack_type": "resource",
                        "version": [2, 0, 1],
                        "active": False,
                    },
                ],
            },
            "mods",
        )
        self.assertIn("Paquetes base del servidor: 2", result)
        self.assertEqual(result.count("Paquetes base del servidor"), 1)
        self.assertIn("comportamiento · v2.0.1", result)
        self.assertIn("recursos · v2.0.1", result)
        self.assertIn('"custom-behavior"', result)
        self.assertIn('"custom-resource"', result)
        self.assertNotIn("vanilla_server", result)

    def test_loaded_observation_and_dependency_versions_are_not_overstated(self):
        result = render(
            {
                "installed": [
                    {
                        "name": "Addon",
                        "pack_id": "addon-id",
                        "folder": "addon-folder",
                        "pack_type": "behavior",
                        "version": [3, 1, 0],
                        "configured": False,
                        "loaded": True,
                        "dependencies": [{"uuid": "required-id", "version": [1, 2, 3]}],
                    },
                    {
                        "name": "Unknown load",
                        "pack_id": "unknown-id",
                        "folder": "unknown-folder",
                        "pack_type": "resource",
                        "version": [1, 0, 0],
                        "configured": True,
                        "loaded": False,
                    },
                ]
            },
            "mods",
        )
        self.assertIn("pendiente de reinicio; aún cargado", result)
        self.assertIn("Requiere: required-id@1.2.3", result)
        self.assertIn("Unknown load: configurado", result)
        self.assertNotIn("no cargado", result)


if __name__ == "__main__":
    unittest.main()
