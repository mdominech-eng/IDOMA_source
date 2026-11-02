import os
os.environ.setdefault("IDOMA_API_TOKEN", "test-token-for-unit-tests")
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from idoma_v2.services.memory import parse_memory_instruction
from idoma_v2.services.tool_planner import detect_additional_tool
import idoma_v2.db as db
from idoma_v2 import desktop_agent


class PersonalMemoryTests(unittest.TestCase):
    def test_natural_curriculum_alias_instruction(self):
        parsed = parse_memory_instruction("Ricorda che il mio curriculum si chiama CB")
        self.assertEqual(parsed[0], "curriculum")
        self.assertEqual(parsed[1], "CB")
        self.assertIn("cv", parsed[2])

    def test_when_i_say_cv_mean_cb(self):
        parsed = parse_memory_instruction("Quando dico CV intendo CB")
        self.assertEqual(parsed[:2], ("curriculum", "CB"))

    def test_slash_association(self):
        parsed = parse_memory_instruction("/associa curriculum = CB")
        self.assertEqual(parsed[:2], ("curriculum", "CB"))

    def test_structured_fact_is_searchable_without_touching_legacy_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(db, "DB_PATH", Path(tmp) / "test.sqlite3"):
                db.init_db()
                db.save_memory_fact("file_alias", "curriculum", "CB", ["curriculum", "cv"])
                self.assertEqual(db.find_memory_aliases("curriculum"), ["CB"])
                self.assertEqual(db.find_memory_aliases("CV"), ["CB"])
                self.assertEqual(db.find_memory_aliases("tesi"), [])


class WindowsFolderIntentTests(unittest.TestCase):
    def test_pictures_and_gallery(self):
        self.assertEqual(detect_additional_tool("Apri la cartella Immagini"), ("open_folder", {"folder": "pictures"}))
        self.assertEqual(detect_additional_tool("Mi apri la galleria?"), ("open_folder", {"folder": "pictures"}))

    def test_music_and_video(self):
        self.assertEqual(detect_additional_tool("Apri Musica"), ("open_folder", {"folder": "music"}))
        self.assertEqual(detect_additional_tool("Apri la cartella Video"), ("open_folder", {"folder": "videos"}))

    def test_curriculum_search_query_is_clean(self):
        action, payload = detect_additional_tool("Aprimi il curriculum")
        self.assertEqual(action, "search_files")
        self.assertEqual(payload["query"], "curriculum")

    def test_short_alias_matches_whole_filename_token_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CB.pdf").write_text("curriculum", encoding="utf-8")
            (root / "Marco_CB_2026.docx").write_text("curriculum", encoding="utf-8")
            (root / "XCBX.pdf").write_text("unrelated", encoding="utf-8")
            with patch.object(desktop_agent, "_user_roots", return_value={"documents": root}):
                result = desktop_agent._search_files({"query": "curriculum", "location": "all", "aliases": ["CB"]})
            self.assertIn("CB.pdf", result)
            self.assertIn("Marco_CB_2026.docx", result)
            self.assertNotIn("XCBX.pdf", result)

    def test_open_file_uses_unique_exact_alias_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "CB.pdf"
            target.write_text("curriculum", encoding="utf-8")
            (root / "XCBX.pdf").write_text("unrelated", encoding="utf-8")
            with patch.object(desktop_agent, "_user_roots", return_value={"documents": root}), \
                 patch.object(desktop_agent.os, "startfile", create=True) as startfile:
                result = desktop_agent._search_files({"query": "curriculum", "location": "all", "aliases": ["CB"], "open_first": True})
            startfile.assert_called_once_with(str(target))
            self.assertIn("Ho aperto il file CB.pdf", result)


class ProtocolSafetyTests(unittest.TestCase):
    def test_registered_protocols_are_allowlisted(self):
        with patch.object(desktop_agent.os, "startfile", create=True) as startfile:
            self.assertTrue(desktop_agent._try_registered_protocol("spotify"))
            startfile.assert_called_once_with("spotify:")
        self.assertFalse(desktop_agent._try_registered_protocol("powershell"))
        self.assertFalse(desktop_agent._try_registered_protocol("file"))

    def test_open_url_rejects_external_http(self):
        with self.assertRaises(ValueError):
            desktop_agent.execute_task("open_url", {"url": "http://example.com"})

    def test_open_url_accepts_https_and_local_http(self):
        with patch.object(desktop_agent.webbrowser, "open") as open_browser:
            self.assertIn("Aperto", desktop_agent.execute_task("open_url", {"url": "https://example.com"}))
            self.assertIn("Aperto", desktop_agent.execute_task("open_url", {"url": "http://127.0.0.1:8000"}))
        self.assertEqual(open_browser.call_count, 2)


if __name__ == "__main__":
    unittest.main()
