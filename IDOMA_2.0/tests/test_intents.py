import unittest
from unittest.mock import patch
from types import SimpleNamespace
from idoma_v2.services.assistant import _fallback_open_target, _looks_like_open_request, _detect_desktop_action

class GenericIntentTests(unittest.TestCase):
    def test_natural_language_pc_suffix(self):
        self.assertTrue(_looks_like_open_request("Per favore, puoi aprire TikTok sul mio computer?"))
        action, payload = _fallback_open_target("Per favore, puoi aprire TikTok sul mio computer?")
        self.assertEqual(action, "open_target")
        self.assertEqual(payload["target"], "TikTok")

    def test_polite_filler_before_target(self):
        action, payload = _fallback_open_target("puoi aprire un attimo spotify?")
        self.assertEqual(action, "open_target")
        self.assertEqual(payload["target"], "spotify")

    def test_polite_filler_after_target(self):
        action, payload = _fallback_open_target("mi apri Spotify un secondo, per favore?")
        self.assertEqual(action, "open_target")
        self.assertEqual(payload["target"], "Spotify")

    def test_ai_extracted_entity_wins_over_literal_fallback(self):
        answer = '{"action":"open_target","target":"Spotify","target_type":"app","url":null}'
        with patch("idoma_v2.services.assistant.ask_ai", return_value=SimpleNamespace(content=answer)):
            action, payload = _detect_desktop_action("puoi aprire un attimo spotify?")
        self.assertEqual(action, "open_target")
        self.assertEqual(payload["target"], "Spotify")

    def test_generic_target_not_hardcoded(self):
        action, payload = _fallback_open_target("Mi apri Discord nel browser?")
        self.assertEqual(action, "open_target")
        self.assertEqual(payload["target"], "Discord")

    def test_natural_language_navigation(self):
        action, payload = _fallback_open_target("Vorrei andare su YouTube")
        self.assertEqual(action, "open_target")
        self.assertEqual(payload["target"], "YouTube")

    def test_app_phrase(self):
        action, payload = _fallback_open_target("Puoi avviare l’app di Telegram per favore?")
        self.assertEqual(action, "open_target")
        self.assertEqual(payload["target"], "Telegram")

    def test_direct_url(self):
        action, payload = _fallback_open_target("Apri https://example.com")
        self.assertEqual(action, "open_target")
        self.assertEqual(payload["target_type"], "website")
        self.assertEqual(payload["url"], "https://example.com")

    def test_non_open_request(self):
        self.assertFalse(_looks_like_open_request("Mi racconti cos'è TikTok?"))

    def test_generic_parser_fallback_when_ai_returns_none(self):
        with patch("idoma_v2.services.assistant.ask_ai", return_value=SimpleNamespace(content='{"action":"none"}')):
            action, payload = _detect_desktop_action("Per favore, apri Spotify sul mio computer")
        self.assertEqual(action, "open_target")
        self.assertEqual(payload["target"], "Spotify")

if __name__ == "__main__":
    unittest.main()
