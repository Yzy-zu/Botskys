"""Política audiovisual propia: datos cerrados, congelados y sin descubrimiento."""

import copy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from botsky.call_policy import CallPolicy
from botsky.config import Settings

OWNER = "525511112222@s.whatsapp.net"
GROUP = "123456789012345@g.us"


class CallPolicyTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = Settings(
            self.root,
            "lab",
            "own",
            1,
            self.root / "private/test.sqlite3",
            1793988000000,
            OWNER,
            frozenset(),
            frozenset({GROUP}),
        )
        self.document = {
            "version": 1,
            "instance": "lab",
            "account": "own",
            "epoch": 1,
            "owner": OWNER,
            "actors": [OWNER],
            "privateChats": [OWNER],
            "groups": [{"id": GROUP, "name": "Laboratorio sintético", "maxParticipants": 8}],
            "features": {"agenda": True, "incoming": False, "live": True, "outgoing": True},
            "schedule": {"timeZone": "America/Mexico_City", "startHour": 8, "endHour": 23},
        }

    def test_policy_snapshot_does_not_change_with_caller_mutations(self):
        policy = CallPolicy.build(self.document, self.settings)
        revision = policy.revision
        self.document["features"]["incoming"] = True
        returned = policy.document
        returned["features"]["live"] = False
        self.assertFalse(policy.document["features"]["incoming"])
        self.assertTrue(policy.document["features"]["live"])
        self.assertEqual(policy.revision, revision)

    def test_unknown_fields_implicit_actors_and_automatic_incoming_are_rejected(self):
        invalid = []
        for key, value in [
            ("version", True),
            ("epoch", 2),
            ("account", "foreign"),
            ("actors", ["525533334444@s.whatsapp.net"]),
            ("privateChats", [OWNER, OWNER]),
            ("actors", ["5215511112222@s.whatsapp.net"]),
        ]:
            doc = copy.deepcopy(self.document)
            doc[key] = value
            invalid.append(doc)
        doc = copy.deepcopy(self.document)
        doc["features"]["incoming"] = True
        invalid.append(doc)
        doc = copy.deepcopy(self.document)
        doc["ownerAnyGroup"] = True
        invalid.append(doc)
        for document in invalid:
            with self.subTest(document=document), self.assertRaises(ValueError):
                CallPolicy.build(document, self.settings)

    def test_settings_accept_only_explicit_calls_table_and_create_no_runtime(self):
        config = self.root / "config.toml"
        text = f'''instance = "lab"
account = "own"
epoch = 1
database = "private/test.sqlite3"
activation_at = "2026-11-06T18:00:00Z"
owner = "{OWNER}"
friends = []
allowed_groups = ["{GROUP}"]
[calls]
version = 1
instance = "lab"
account = "own"
epoch = 1
owner = "{OWNER}"
actors = ["{OWNER}"]
privateChats = ["{OWNER}"]
groups = [{{id = "{GROUP}", name = "Laboratorio sintético", maxParticipants = 8}}]
[calls.features]
agenda = true
incoming = false
live = true
outgoing = true
[calls.schedule]
timeZone = "America/Mexico_City"
startHour = 8
endHour = 23
'''
        config.write_text(text)
        settings = Settings.load(config)
        self.assertEqual(
            settings.calls.revision, CallPolicy.build(self.document, self.settings).revision
        )
        self.assertFalse((self.root / "private").exists())
