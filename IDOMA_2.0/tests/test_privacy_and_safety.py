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


import tempfile
from pathlib import Path
import idoma_v2.db as db


class DesktopTaskLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, "DB_PATH", Path(self.tmp.name) / "idoma.sqlite3")
        self.db_patch.start()
        db.init_db()

    def tearDown(self):
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_desktop_action_returns_without_waiting_for_windows(self):
        with patch.object(assistant, "agent_is_online", return_value=True):
            with patch.object(assistant, "detect_additional_tool", return_value=("open_folder", {"folder": "documents"})):
                result = assistant.process_message("Apri la cartella Documenti")
        self.assertTrue(result["pending"])
        self.assertIn("task_id", result)
        messages = db.get_messages(result["conversation_id"])
        self.assertIn("Ti aggiornerò qui", messages[-1]["content"])

    def test_messages_include_pending_task_state_for_reopened_conversation(self):
        conversation = assistant.new_conversation()
        task_id = db.queue_agent_task("open_folder", {"folder": "documents"})
        message_id = db.save_message(conversation["id"], "assistant", "Operazione in corso")
        db.link_agent_task_message(task_id, message_id)
        item = db.get_messages(conversation["id"])[-1]
        self.assertEqual(item["agent_task_id"], task_id)
        self.assertEqual(item["agent_task_status"], "queued")

    def test_stale_running_task_is_requeued_after_a_crash(self):
        task_id = db.queue_agent_task("open_folder", {"folder": "documents"})
        first_claim = db.claim_agent_task()
        self.assertEqual(first_claim["id"], task_id)
        with db.connection() as conn:
            conn.execute(
                "UPDATE idoma2_agent_tasks SET updated_at=? WHERE id=?",
                ("2000-01-01T00:00:00+00:00", task_id),
            )
        second_claim = db.claim_agent_task()
        self.assertEqual(second_claim["id"], task_id)

    def test_task_completion_updates_pending_chat_message(self):
        conversation = assistant.new_conversation()
        task_id = db.queue_agent_task("open_folder", {"folder": "documents"})
        message_id = db.save_message(conversation["id"], "assistant", "Operazione in corso")
        db.link_agent_task_message(task_id, message_id)
        db.finish_agent_task(task_id, "Aperta la cartella Documenti.", True)
        messages = db.get_messages(conversation["id"])
        self.assertEqual(messages[-1]["content"], "Fatto: Aperta la cartella Documenti.")

    def test_linking_after_fast_completion_updates_pending_message(self):
        conversation = assistant.new_conversation()
        task_id = db.queue_agent_task("open_folder", {"folder": "documents"})
        message_id = db.save_message(conversation["id"], "assistant", "Operazione in corso")
        db.finish_agent_task(task_id, "Aperta la cartella Documenti.", True)
        db.link_agent_task_message(task_id, message_id)
        messages = db.get_messages(conversation["id"])
        self.assertEqual(messages[-1]["content"], "Fatto: Aperta la cartella Documenti.")


class DesktopActionSafetyTests(unittest.TestCase):
    def test_negated_app_open_does_not_call_ai_or_open(self):
        with patch.object(assistant, "ask_ai", side_effect=AssertionError("AI must not be called")):
            self.assertIsNone(assistant._detect_desktop_action("Non aprire Spotify"))

    def test_negated_folder_and_document_requests_are_not_routed(self):
        self.assertIsNone(detect_additional_tool("Non aprire la cartella Documenti"))
        self.assertIsNone(detect_additional_tool("Non cercare il PDF della tesi"))


if __name__ == "__main__":
    unittest.main()
