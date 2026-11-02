import os
os.environ.setdefault("IDOMA_API_TOKEN", "test-token-for-unit-tests")
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import idoma_v2.db as db
from idoma_v2.services import assistant
from idoma_v2.services.fast_actions import calculate_if_expression


class FastCalculationTests(unittest.TestCase):
    def test_plain_multiplication_uses_local_calculator(self):
        self.assertEqual(calculate_if_expression("2000x2"), "Risultato: 4000")

    def test_natural_language_prefix_and_decimal_comma(self):
        self.assertEqual(calculate_if_expression("Quanto fa 12,5 x 2?"), "Risultato: 25")

    def test_parentheses_and_precedence(self):
        self.assertEqual(calculate_if_expression("(10 + 2) * 3"), "Risultato: 36")

    def test_zero_division_is_not_reported_as_success(self):
        self.assertIsNone(calculate_if_expression("10 / 0"))

    def test_arbitrary_text_is_not_treated_as_math(self):
        self.assertIsNone(calculate_if_expression("apri Spotify"))


class FastCalculatorRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(db, "DB_PATH", Path(self.tmp.name) / "idoma.sqlite3")
        self.db_patch.start()
        db.init_db()

    def tearDown(self):
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_chat_calculation_bypasses_the_language_model(self):
        with patch.object(assistant, "ask_ai", side_effect=AssertionError("LLM should not be called")):
            result = assistant.process_message("2000x2")
        self.assertEqual(result["reply"], "Risultato: 4000")
        self.assertEqual(result["model"], "python-calculator")


if __name__ == "__main__":
    unittest.main()
