from unittest import TestCase

from botsky.contracts import Result
from botsky.presentation.domains import present


class AVPresentationTest(TestCase):
    def test_status_retains_reason_connection_time_and_measured_duration(self):
        result = Result(
            "ok",
            "call_status",
            "raw",
            {
                "call": {
                    "state": "ended",
                    "connectedAt": 1793962800000,
                    "endedAt": 1793962895000,
                    "reason": "duration_limit",
                }
            },
        )
        text = present(result).text
        self.assertIn("1:35", text)
        self.assertIn("America/Mexico_City", text)
        self.assertIn("Se alcanzó la duración permitida", text)
        self.assertIn("no acredita escucha", text)
        self.assertNotIn("duration_limit", text)

    def test_volume_uses_observed_value_and_preserves_deferred_message(self):
        result = Result(
            "ok",
            "av_control_applied",
            "Volumen para el siguiente clip.",
            {
                "success": True,
                "presentation_family": "clip",
                "presentation_action": "volume",
                "clip": {"state": "ended", "volume": 0.37, "name": "Clip *literal*"},
            },
        )
        text = present(result).text
        self.assertIn("37 %", text)
        self.assertIn("siguiente clip", text)
        self.assertNotIn("100 %", text)
        self.assertEqual(result.data["clip"]["volume"], 0.37)

    def test_agenda_uses_configured_timezone_even_when_service_zone_is_invalid(self):
        result = Result(
            "ok",
            "agenda_list",
            "raw",
            {
                "schedules": [
                    {
                        "id": "schedule-reference",
                        "dueAt": 1793962800000,
                        "state": "pending",
                        "live": True,
                        "maxSeconds": 95,
                        "timeZone": "INVALID_ZONE",
                    }
                ]
            },
        )
        shown = present(result)
        row = shown.data["native_tables"][0]["rows"][0]
        self.assertIn("America/Mexico_City", row[1])
        self.assertIn("En vivo · 95 s", row[2])
        self.assertNotIn("INVALID_ZONE", shown.text)
