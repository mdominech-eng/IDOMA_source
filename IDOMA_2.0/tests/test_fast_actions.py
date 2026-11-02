import unittest

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


if __name__ == "__main__":
    unittest.main()
