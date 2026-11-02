import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("IDOMA_API_TOKEN", "test-token-for-unit-tests")

from idoma_v2.services.tool_planner import detect_additional_tool
from idoma_v2 import db, desktop_agent
from idoma_v2.server.main import AgentResult


class DocumentSearchIntentTests(unittest.TestCase):
    def test_topic_inside_document(self):
        action, payload = detect_additional_tool("Trova il documento in cui si parla del progetto iDOMA")
        self.assertEqual(action, "search_document_content")
        self.assertIn("idoma", payload["query"])

    def test_which_file_contains_phrase(self):
        action, payload = detect_additional_tool("In quale file avevo scritto PID controller?")
        self.assertEqual(action, "search_document_content")
        self.assertIn("pid", payload["query"])

    def test_filename_search_remains_separate(self):
        action, payload = detect_additional_tool("Cerca il PDF della tesi")
        self.assertEqual(action, "search_files")

    def test_plain_term_in_my_files_searches_document_content(self):
        for message in (
            "Trova sustainability nei miei file",
            "Cerca sustainability nei documenti",
            "Trova sustainability nei miei documenti",
        ):
            with self.subTest(message=message):
                action, payload = detect_additional_tool(message)
                self.assertEqual(action, "search_document_content")
                self.assertEqual(payload["query"], "sustainability")

    def test_where_did_i_write_term_searches_document_content(self):
        for message in (
            "Dove ho scritto sustainability nei miei file?",
            "In quali file ho scritto sustainability?",
        ):
            with self.subTest(message=message):
                action, payload = detect_additional_tool(message)
                self.assertEqual(action, "search_document_content")
                self.assertEqual(payload["query"], "sustainability")

    def test_inside_documents_phrase(self):
        action, payload = detect_additional_tool("Cerca all'interno dei documenti la parola sostenibilità")
        self.assertEqual(action, "search_document_content")
        self.assertIn("sostenibil", payload["query"])


class AgentResultValidationTests(unittest.TestCase):
    def test_document_search_result_over_2000_characters_is_accepted(self):
        response = AgentResult(task_id=1, result="x" * 5000, success=True)
        self.assertEqual(len(response.result), 5000)


class DocumentIndexTests(unittest.TestCase):
    def test_text_document_search_and_incremental_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            doc = folder / "appunti.txt"
            doc.write_text("Il progetto iDOMA utilizza un PID controller per la temperatura.\n", encoding="utf-8")
            db_path = folder / "idoma_test.sqlite3"
            with patch.object(db, "DB_PATH", db_path), patch.object(desktop_agent, "_user_roots", return_value={"documents": folder}):
                db.init_db()
                result = desktop_agent._search_document_content({"query": "PID controller", "location": "all"})
                self.assertIn("appunti.txt", result)
                self.assertIn("PID controller", result)
                result_again = desktop_agent._search_document_content({"query": "progetto iDOMA", "location": "all"})
                self.assertIn("1 già in cache", result_again)

    def test_extract_pdf_docx_xlsx_and_pptx(self):
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            canvas = None
        from docx import Document
        from openpyxl import Workbook
        from pptx import Presentation
        from pptx.util import Inches

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "test.pdf"
            if canvas is not None:
                c = canvas.Canvas(str(pdf))
                c.drawString(72, 720, "IDOMA recupero del calore")
                c.save()
            docx = folder / "test.docx"
            document = Document()
            document.add_paragraph("PID controller temperatura")
            document.save(docx)
            xlsx = folder / "test.xlsx"
            workbook = Workbook()
            workbook.active["A1"] = "Efficienza energetica"
            workbook.save(xlsx)
            pptx = folder / "test.pptx"
            presentation = Presentation()
            slide = presentation.slides.add_slide(presentation.slide_layouts[5])
            slide.shapes.title.text = "Sostenibilità iDOMA"
            presentation.save(pptx)

            if canvas is not None:
                self.assertIn("IDOMA recupero del calore", desktop_agent._extract_document_text(pdf))
            self.assertIn("PID controller temperatura", desktop_agent._extract_document_text(docx))
            self.assertIn("Efficienza energetica", desktop_agent._extract_document_text(xlsx))
            self.assertIn("Sostenibilità iDOMA", desktop_agent._extract_document_text(pptx))

    def test_document_index_upsert(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(db, "DB_PATH", Path(tmp) / "test.sqlite3"):
                db.init_db()
                db.upsert_indexed_document("C:/docs/test.txt", 1, 10, ".txt", "contenuto")
                item = db.get_indexed_document("C:/docs/test.txt")
                self.assertEqual(item["content"], "contenuto")
                self.assertEqual(len(db.list_indexed_documents()), 1)


if __name__ == "__main__":
    unittest.main()
