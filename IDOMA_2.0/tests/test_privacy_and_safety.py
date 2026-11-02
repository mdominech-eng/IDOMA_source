import unittest
from unittest.mock import patch

from idoma_v2.providers import router
from idoma_v2.services import assistant
from idoma_v2.services.tool_planner import detect_additional_tool


class ProviderPrivacyTests(unittest.TestCase):
    def test_cloud_is_not_called_when_opt_in_is_disabled(self):
        with patch.object(router, "ALLOW_CLOUD", False), \
             patch.object(router, "_ask_ollama", side_effect=router.ProviderUnavailable("offline")), \
             patch.object(router, "_ask_cloud") as cloud:
            with self.assertRaises(router.ProviderUnavailable):
                router.ask_ai([{"role": "user", "content": "test"}])
            cloud.assert_not_called()

    def test_cloud_can_be_used_only_after_explicit_opt_in(self):
        expected = router.AIResponse("ok", "cloud", "test-model")
        with patch.object(router, "ALLOW_CLOUD", True), \
             patch.object(router, "PREFER_LOCAL", True), \
             patch.object(router, "_ask_ollama", side_effect=router.ProviderUnavailable("offline")), \
             patch.object(router, "_ask_cloud", return_value=expected) as cloud:
            result = router.ask_ai([{"role": "user", "content": "test"}])
            self.assertEqual(result.provider, "cloud")
            cloud.assert_called_once()


class DesktopActionSafetyTests(unittest.TestCase):
    def test_negated_app_open_does_not_call_ai_or_open(self):
        with patch.object(assistant, "ask_ai", side_effect=AssertionError("AI must not be called")):
            self.assertIsNone(assistant._detect_desktop_action("Non aprire Spotify"))

    def test_negated_folder_and_document_requests_are_not_routed(self):
        self.assertIsNone(detect_additional_tool("Non aprire la cartella Documenti"))
        self.assertIsNone(detect_additional_tool("Non cercare il PDF della tesi"))

    def test_model_generated_url_is_ignored(self):
        parsed = assistant._parse_action_json(
            '{"action":"open_target","target":"Google","target_type":"website",'
            '"url":"https://example-phishing.invalid"}'
        )
        self.assertEqual(parsed["target"], "Google")
        self.assertIsNone(parsed["url"])


if __name__ == "__main__":
    unittest.main()
