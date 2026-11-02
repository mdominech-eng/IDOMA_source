import unittest

from idoma_v2.services.voice import is_wake_phrase, normalise_wake_text, strip_wake_prefix


class WakePhraseTests(unittest.TestCase):
    def test_accepts_requested_phrase(self):
        self.assertTrue(is_wake_phrase("Hey IDOMA"))

    def test_accepts_italian_and_vosk_variants(self):
        self.assertTrue(is_wake_phrase("Ehi i doma"))
        self.assertTrue(is_wake_phrase("hei idioma"))

    def test_accepts_vosk_dropping_hey(self):
        self.assertTrue(is_wake_phrase("idoma"))

    def test_does_not_wake_on_ordinary_idioma(self):
        self.assertFalse(is_wake_phrase("parliamo di un idioma italiano"))
        self.assertFalse(is_wake_phrase("idioma"))

    def test_normalises_accents_and_spacing(self):
        self.assertEqual(normalise_wake_text("HÉY, IDOMA!"), "hey idoma")

    def test_removes_wake_phrase_before_command(self):
        self.assertEqual(strip_wake_prefix("Hey IDOMA, apri Spotify"), "apri Spotify")

    def test_removes_vosk_variant_before_command(self):
        self.assertEqual(strip_wake_prefix("Ehi i doma cerca il PDF della tesi"), "cerca il PDF della tesi")

    def test_bare_wake_word_leaves_no_command(self):
        self.assertEqual(strip_wake_prefix("IDOMA"), "")


if __name__ == "__main__":
    unittest.main()
