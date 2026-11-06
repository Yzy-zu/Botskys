from unittest import TestCase

from botsky.domains.contacts import Contact, Directory


class ContactsTest(TestCase):
    def test_explicit_aliases_dedup_and_no_partial_or_fuzzy_resolution(self):
        alice = Contact("Amiga", "123456789@s.whatsapp.net", ("Alicia",))
        directory = Directory((alice,))
        self.assertEqual(directory.resolve(("ＡＭＩＧＡ", " Alicia ")), (alice,))
        for names in (("Ami",), ("Amiga", "desconocida"), ("123456789",)):
            with self.assertRaises(ValueError):
                directory.resolve(names)
        self.assertNotIn(alice.target, repr(alice))
        with self.assertRaises(ValueError):
            Directory((alice, Contact("Otra", "987654321@s.whatsapp.net", ("amiga",))))

    def test_directory_change_invalidates_preview_fingerprint(self):
        before = Directory((Contact("Amiga", "123456789@s.whatsapp.net"),))
        after = Directory((Contact("Amiga", "987654321@s.whatsapp.net"),))
        self.assertNotEqual(before.fingerprint(("Amiga",)), after.fingerprint(("Amiga",)))
        self.assertEqual(Directory().contacts, ())
        with self.assertRaises(ValueError):
            Contact("Nombre\ncontrol", "123456789@s.whatsapp.net")
