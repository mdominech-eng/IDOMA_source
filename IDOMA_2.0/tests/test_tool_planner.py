import unittest
from idoma_v2.services.tool_planner import detect_additional_tool, tool_catalog


class DesktopToolPlannerTests(unittest.TestCase):
    def test_open_documents_folder(self):
        self.assertEqual(detect_additional_tool("Puoi aprire un attimo la cartella Documenti?"),
                         ("open_folder", {"folder": "documents"}))

    def test_open_downloads_folder(self):
        self.assertEqual(detect_additional_tool("Aprimi la cartella Download per favore"),
                         ("open_folder", {"folder": "downloads"}))

    def test_search_file_by_name(self):
        action, payload = detect_additional_tool("Per favore, trovami il file curriculum nei Documenti")
        self.assertEqual(action, "search_files")
        self.assertIn("curriculum", payload["query"].casefold())
        self.assertEqual(payload["location"], "documents")

    def test_search_pdf(self):
        action, payload = detect_additional_tool("Cerca il PDF della tesi")
        self.assertEqual(action, "search_files")
        self.assertTrue(payload["query"])

    def test_pc_status(self):
        self.assertEqual(detect_additional_tool("Quanto spazio disponibile ho sul disco?"),
                         ("pc_status", {}))

    def test_regular_conversation_is_not_tool(self):
        self.assertIsNone(detect_additional_tool("Mi spieghi cos'è una cartella di Windows?"))

    def test_negated_folder_command_is_not_executed(self):
        self.assertIsNone(detect_additional_tool("Non aprire la cartella Documenti"))

    def test_negated_search_command_is_not_executed(self):
        self.assertIsNone(detect_additional_tool("Non cercare il PDF della tesi"))

    def test_tool_catalog_is_generic(self):
        names = {item["name"] for item in tool_catalog()}
        self.assertTrue({"open_target", "search_files", "open_folder", "open_path", "pc_status"}.issubset(names))
        self.assertNotIn("spotify", names)


if __name__ == "__main__":
    unittest.main()
