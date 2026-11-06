"""Casos de contrato: el parser no necesita transporte, DB ni modelo."""

import json
import socket
from dataclasses import replace
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from botsky.commands.lexer import SyntaxProblem, next_token
from botsky.commands.registry import Registry
from botsky.commands.router import CommandError, Router


class CommandsTest(TestCase):
    def setUp(self):
        self.router = Router()

    def parse(self, text):
        return self.router.parse(text)

    def error(self, text, code=None):
        with self.assertRaises(CommandError) as ctx:
            self.parse(text)
        if code:
            self.assertEqual(ctx.exception.code, code)
        return ctx.exception

    def test_all_declared_examples_route_to_their_exact_spec_without_io(self):
        with (
            patch.object(socket, "socket", side_effect=AssertionError("red prohibida")),
            patch("builtins.open", side_effect=AssertionError("archivos prohibidos")),
        ):
            for spec in self.router.registry.specs:
                with self.subTest(command=spec.command):
                    parsed = self.parse(spec.sample)
                    self.assertEqual(parsed.spec, spec)
                    self.assertEqual(parsed.canonical(), self.parse(spec.sample).canonical())

    def test_aliases_case_and_data_preserve_meaningful_case(self):
        left = self.parse(" \t/DESCARGAR MP4 https://www.youtube.com/watch?v=AbCDEfgHI12")
        right = self.parse("/dl mp4 https://www.youtube.com/watch?v=AbCDEfgHI12")
        self.assertEqual(left.canonical(), right.canonical())
        self.assertTrue(left.arguments["url"].endswith("AbCDEfgHI12"))
        self.assertEqual(self.parse("/CONV PDF").arguments["target"], "pdf")
        self.assertEqual(
            self.parse("/WEB Python site:python.org").arguments["query"], "Python site:python.org"
        )

    def test_literal_tail_preserves_quotes_newlines_shell_and_option_like_content(self):
        literal = 'comprar --pan; && $(id) `hola`\n/nota guardar "otra"  \\n'
        parsed = self.parse("/nota guardar -- " + literal)
        self.assertEqual(parsed.arguments["text"], literal)
        offset = len("/nota guardar -- ")
        self.assertEqual(parsed.spans["text"], ((offset, offset + len(literal)),))
        self.assertEqual(self.parse("/nota guardar " + literal).arguments["text"], literal)
        self.assertEqual(self.parse("/voz -- crear poema").spec.original_action, "verbatim")
        self.assertEqual(self.parse("/voz crear poema").spec.original_action, "compose")
        self.assertEqual(self.parse('/voz "sin cerrar').arguments["text"], '"sin cerrar')

    def test_text_final_stops_option_parsing(self):
        parsed = self.parse("/notas --pagina 2 cable --pagina 3")
        self.assertEqual(dict(parsed.arguments), {"page": 2, "query": "cable --pagina 3"})
        self.error("/notas --desconocida 2", "unknown_option")
        self.error("/notas --pagina 2 --pagina 3 cable", "duplicate_option")
        self.error("/notas --pagina", "missing_option_value")
        self.error("/llamar --video si", "extra_argument")
        self.error("/nota guardar --", "missing_field")

    def test_quotes_and_escapes_for_multiple_fields(self):
        p = self.parse('/encuesta crear "¿Qué hora?" "A las \\"dos\\"" \'Tres\\\\cuatro\'')
        self.assertEqual(p.arguments["question"], "¿Qué hora?")
        self.assertEqual(p.arguments["options"], ('A las "dos"', "Tres\\cuatro"))
        raw = '  "a \\"b\\""'
        tok = next_token(raw, 0)
        self.assertEqual((tok.value, tok.start, tok.end), ('a "b"', 2, len(raw)))
        with self.assertRaises(SyntaxProblem):
            next_token('"sin cerrar', 0)
        self.error("/encuesta crear pregunta una", "missing_values")
        self.error(
            "/encuesta crear pregunta " + " ".join(str(i) for i in range(11)), "too_many_values"
        )

    def test_noncommands_and_unknown_never_route_by_similarity(self):
        for text in (
            "hola /nota guardar uno",
            "> /nota guardar uno",
            "```\n/saldo\n```",
            "https://example.com/saldo",
            "2",
            "sí",
            "@Botsky descarga esto",
            "",
        ):
            self.assertIsNone(self.parse(text))
        err = self.error("/sald", "unknown_command")
        self.assertIn("vuelve a enviarlo", str(err))
        self.error("/nota borrar texto", "unknown_action")
        self.error('/"saldo"', "invalid_command")

    def test_strict_numbers_enums_ranges_and_no_shell_operators(self):
        for command in (
            "/notas --pagina 0",
            "/notas --pagina true",
            "/notas --pagina 1.0",
            "/notas --pagina -1",
            "/notas --pagina 10001",
            "/bj iniciar 19",
            "/ruleta crear 1001",
            "/clip volumen NaN",
            "/clip volumen inf",
            "/clip volumen 1e-2",
            "/pdf extraer 2-1",
            "/pdf extraer 501",
            "/llamar --duracion 4s",
            "/editar mp7",
        ):
            self.error(command, "invalid_field")
        for command in (
            "/saldo ; /daily",
            "/saldo && /daily",
            "/saldo\n/daily",
            "/saldo $(id)",
            "/saldo `id`",
        ):
            self.error(command)
        p = self.parse("/llamar --duracion 10m --video")
        self.assertIs(type(p.arguments["max_seconds"]), int)
        self.assertEqual(p.arguments["max_seconds"], 600)
        self.assertIs(p.arguments["video"], True)
        self.assertIs(type(self.parse("/notas --pagina 2").arguments["page"]), int)
        self.assertEqual(
            self.parse("/editar mp4 --desde 00:00:01.5 --hasta 3").arguments["start_seconds"], 1.5
        )

    def test_incompatible_fields_and_precise_errors(self):
        for command in (
            "/editar mp4 --idioma es",
            "/dl buscar srt --hasta 5 consulta",
            "/dl anterior srt --desde 1",
            "/editar mp4 --desde 3 --hasta 2",
            "/admin xp-dar 1",
            "/admin xp-dar --objetivo ref --cuenta 1 1",
            "/escuela resumen configurar si",
            "/escuela resumen configurar no --hora 12:00",
            "/horario agregar --materia Mate --dia 1 --inicio 13:00 --fin 12:00",
            "/recado preparar --para Amiga --fuente cita texto",
            "/llamada programar 2026-12-01 12:00 --tema Hola --audio ID_REAL",
        ):
            err = self.error(command, "incompatible_fields")
            self.assertIsNotNone(err.field)
            self.assertIn("Uso:", err.reply)
            self.assertIn("Ejemplo:", err.reply)
        err = self.error("/dl mp4", "missing_field")
        self.assertEqual(err.field, "url")
        self.assertIn("/dl mp4", err.reply)
        self.error("/recordar el 2026-02-30 12:00 hola", "invalid_field")
        self.error("/recordar el 2026-12-01 24:00 hola", "invalid_field")
        self.error("/recordar el mañana 12:00 hola", "invalid_field")
        self.error("/recordar en 1.5h hola", "invalid_field")
        self.error("/recado preparar --para Amiga,Amiga hola", "invalid_field")

    def test_registry_rejects_collisions_and_output_has_no_authority(self):
        specs = self.router.registry.specs
        with self.assertRaises(ValueError):
            Registry([specs[0], specs[0]], aliases={})
        with self.assertRaises(ValueError):
            Registry(specs, aliases={"saldo": "daily"})
        with self.assertRaises(ValueError):
            Registry(specs, aliases={"x": "absent"})
        with self.assertRaises(ValueError):
            Registry([replace(specs[0], fields=specs[0].fields * 2)], aliases={})
        parsed = self.parse("/nota guardar dato")
        self.assertNotIn("actor", parsed.arguments)
        self.assertNotIn("permission", parsed.arguments)
        with self.assertRaises(TypeError):
            parsed.arguments["actor"] = "owner"

    def test_adapted_fields_preserve_explicit_selection_and_complete_options(self):
        self.assertEqual(self.parse('/clip poner --nombre "Mi Clip"').arguments["query"], "Mi Clip")
        self.error("/clip poner", "incompatible_fields")
        self.error("/clip poner ID_REAL --nombre otro", "incompatible_fields")
        self.error('/encuesta crear "Hora" "Dos" "Ｄos"', "incompatible_fields")
        self.assertEqual(
            self.parse('/buscar --terminos "Python,docs" Python site:python.org').arguments[
                "required_terms"
            ],
            ("Python", "docs"),
        )
        self.assertEqual(self.parse("/hh estado EVENTO_REAL").arguments["event_id"], "EVENTO_REAL")
        self.assertEqual(self.parse("/voz --voz peruano Hola").arguments["voice"], "peruano")

    def test_catalog_actions_are_accounted_for_and_help_is_generated(self):
        catalog = json.loads(Path("docs/inventario/catalog.json").read_text())
        internal = {
            ("conversation", "ask"),
            ("conversation", "silent"),
            ("manage_conversation", "cancel"),
        }
        accounted = {(s.family, s.original_action) for s in self.router.registry.specs} | internal
        for tool in catalog:
            actions = tool["parameters"]["properties"].get("action", {}).get("enum", [])
            if not actions:
                self.assertIn(tool["name"], {s.family for s in self.router.registry.specs})
            for action in actions:
                self.assertIn((tool["name"], action), accounted)
        self.assertEqual(self.router.registry.help("conv"), self.router.registry.help("convertir"))
        self.assertIn("adjunto o cita exacta", self.router.registry.help("convertir"))
        self.assertIn("--pagina", self.router.registry.help("notas"))
        self.assertIn("attachment_id", json.dumps(catalog))
        self.assertNotIn("attachment_id", self.router.registry.help("convertir"))
