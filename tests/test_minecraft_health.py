from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from botsky.adapters.minecraft import MinecraftConfig, MinecraftRemote


class HealthTest(IsolatedAsyncioTestCase):
    async def test_start_requires_game_readiness_and_never_repeats_failed_start(self):
        backend = MinecraftRemote(
            MinecraftConfig("fixture", "fixture", "/srv/fixture", "/srv/worker.py")
        )
        backend._request = AsyncMock(
            side_effect=[
                {"status": "ok", "requires_healthcheck": True},
                {"status": "ok", "game_status": "failed"},
            ]
        )
        result = await backend.change("start")
        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(
            [call.args[0] for call in backend._request.call_args_list], ["start", "status"]
        )
        backend._request = AsyncMock(
            side_effect=[
                {"status": "ok", "requires_healthcheck": True},
                {"status": "ok", "game_status": "ready"},
            ]
        )
        self.assertTrue((await backend.change("restart"))["verified"])
