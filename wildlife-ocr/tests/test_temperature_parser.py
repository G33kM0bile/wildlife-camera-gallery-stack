import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from temperature_parser import parse_temperature_pair


class TemperatureParserTests(unittest.TestCase):
    def test_normal_footer(self):
        text = "SUNTEK CAM000 2026/09/25 15:23:32 10°C/50°F 100%"
        self.assertEqual(
            parse_temperature_pair(text, start=text.index("10°C")),
            (10, 50),
        )

    def test_missing_degree_and_unit_symbols(self):
        self.assertEqual(parse_temperature_pair("2026/09/24 04:14:36 6/42 @ 100%"), (6, 42))

    def test_degree_symbol_read_as_trailing_digit(self):
        self.assertEqual(parse_temperature_pair("2026/09/24 06:33:39 67/42 @ 100%"), (6, 42))
        self.assertEqual(parse_temperature_pair("2026/09/20 05:30:26 87/46 F 100%"), (8, 46))

    def test_fahrenheit_unit_read_as_trailing_digit(self):
        self.assertEqual(parse_temperature_pair("2026/09/24 19:21:48 9/485 @ 100%"), (9, 48))

    def test_other_ocr_glyphs_between_values(self):
        self.assertEqual(parse_temperature_pair("2026/09/19 16:02:44 26°%/78F 100%"), (26, 78))
        self.assertEqual(parse_temperature_pair("2026/09/22 03:26:46 10TC/50F 100%"), (10, 50))
        self.assertEqual(parse_temperature_pair("2026/09/25 04:57:31 6€/42F 100%"), (6, 42))

    def test_date_is_not_treated_as_temperature(self):
        self.assertIsNone(parse_temperature_pair("2026/09/25 14:48:01 OCR failed"))

    def test_inconsistent_pair_is_rejected(self):
        self.assertIsNone(parse_temperature_pair("2026/09/25 14:48:01 67/120 100%"))


if __name__ == "__main__":
    unittest.main()
