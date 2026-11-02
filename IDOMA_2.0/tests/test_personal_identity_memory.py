import os
os.environ.setdefault("IDOMA_API_TOKEN", "test-token-for-unit-tests")
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import idoma_v2.db as db
from idoma_v2.services import assistant
from idoma_v2.services.memory import (
    parse_personal_memory_instruction, remember_personal_fact, personal_name_from_memory,
    remember_general_personal_fact, personal_device_from_memory,
)


class PersonalIdentityMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, "DB_PATH", Path(self.tmp.name) / "idoma.sqlite3")
        self.db_patch.start()
        db.init_db()

    def tearDown(self):
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_parse_natural_name_instruction(self):
        parsed = parse_personal_memory_instruction("Ricorda che mi chiamo marco")
        self.assertEqual(parsed[:2], ("nome", "Marco"))

    def test_remember_name_and_retrieve_without_ai(self):
        self.assertTrue(remember_personal_fact("Ricorda che mi chiamo Marco"))
        self.assertEqual(personal_name_from_memory(), "Marco")
        self.assertEqual(assistant._personal_name_question("Come mi chiamo?"), True)

    def test_memory_button_phrase_is_intercepted_as_memory_command(self):
        reply = assistant._special_memory_command("Mostrami cosa ricordi di me usando il comando /memoria.")
        self.assertIn("Non trovo ancora ricordi", reply)
        self.assertIsNotNone(reply)

    def test_memory_natural_request_is_intercepted(self):
        remember_personal_fact("Ricorda che mi chiamo Marco")
        reply = assistant._special_memory_command("Cosa ricordi di me?")
        self.assertIn("nome: Marco", reply)

    def test_old_explicit_instruction_in_chat_history_is_recovered(self):
        conversation = assistant.new_conversation()
        db.save_message(conversation["id"], "user", "Ricorda che mi chiamo Marco")
        with patch.object(assistant, "ask_ai", side_effect=AssertionError("AI should not be called")):
            result = assistant.process_message("Come mi chiamo?", conversation["id"])
        self.assertEqual(result["reply"], "Ti chiami Marco.")
        self.assertEqual(result["provider"], "local")

    def test_first_screen_memory_shortcut_uses_literal_command(self):
        html = (Path(__file__).parents[1] / "idoma_v2" / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-prompt="/memoria"', html)

    def test_memory_command_does_not_open_a_website(self):
        with patch.object(assistant, "_detect_desktop_action", side_effect=AssertionError("desktop opener should not run")):
            result = assistant.process_message("Mostrami cosa ricordi di me usando il comando /memoria.")
        self.assertIn("memoria personale", result["reply"].casefold())

    def test_legacy_memory_name_can_be_recovered(self):
        db.add_legacy_memory("Mi chiamo Marco", "test")
        self.assertEqual(personal_name_from_memory(db.get_legacy_memories()), "Marco")

    def test_forgotten_name_is_not_resurrected_from_chat_history(self):
        conversation = assistant.new_conversation()
        db.save_message(conversation["id"], "user", "Ricorda che mi chiamo Marco")
        assistant.process_message("/dimentica Marco", conversation["id"])
        result = assistant.process_message("Come mi chiamo?", conversation["id"])
        self.assertIn("Non ho ancora memorizzato", result["reply"])
        self.assertIsNone(personal_name_from_memory(db.get_legacy_memories(100)))

    def test_explicitly_remembering_again_restores_a_forgotten_name(self):
        conversation = assistant.new_conversation()
        db.save_message(conversation["id"], "user", "Ricorda che mi chiamo Marco")
        assistant.process_message("/dimentica Marco", conversation["id"])
        assistant.process_message("/ricorda mi chiamo Marco", conversation["id"])
        result = assistant.process_message("Come mi chiamo?", conversation["id"])
        self.assertEqual(result["reply"], "Ti chiami Marco.")

    def test_structured_memory_context_is_relevant_to_the_question(self):
        from idoma_v2.services.memory import structured_memory_context
        db.save_memory_fact("file_alias", "curriculum", "CB", ["CV"])
        db.save_memory_fact("personal", "nome", "Marco", ["nome"])
        context = structured_memory_context("Dove si trova il mio curriculum?", 10)
        self.assertEqual(context, ["curriculum: CB (alias: CV)"])

    def test_general_device_memory_is_saved_and_retrieved_without_ai(self):
        saved = assistant.process_message("Ricorda che ti scrivo da un Lenovo Ideapad Flex 5")
        self.assertIn("Lenovo IdeaPad Flex 5", saved["reply"])
        self.assertEqual(saved["model"], "memory")
        with patch.object(assistant, "ask_ai", side_effect=AssertionError("AI should not be called")):
            result = assistant.process_message("Che computer uso?")
        self.assertEqual(result["reply"], "Usi un Lenovo IdeaPad Flex 5.")
        self.assertEqual(personal_device_from_memory(), "Lenovo IdeaPad Flex 5")

    def test_generic_explicit_memory_instruction_is_not_sent_to_ai(self):
        with patch.object(assistant, "ask_ai", side_effect=AssertionError("AI should not be called")):
            result = assistant.process_message("Ricorda che preferisco risposte concise")
        self.assertIn("Ho salvato nella memoria personale", result["reply"])
        self.assertIn("preferisco risposte concise", " ".join(x["content"] for x in db.get_legacy_memories(20)))


if __name__ == "__main__":
    unittest.main()
