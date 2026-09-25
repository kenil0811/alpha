"""Supplementary checks for the summarize_expenses action."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from expenses import summarize_expenses  # noqa: E402


class SummarizeExpensesTest(unittest.TestCase):
    def test_acceptance_examples(self):
        cases = [
            (
                "2026-09-03 groceries 42.50\n2026-09-04 fuel 61.10\n"
                "2026-09-05 groceries 7.25",
                {
                    "totals": {"groceries": 49.75, "fuel": 61.1},
                    "overall": 110.85,
                    "ignored": 0,
                },
            ),
            (
                "not a line\n2026-09-06 coffee 3.40\n\n2026-09-07 coffee 3.6",
                {"totals": {"coffee": 7.0}, "overall": 7.0, "ignored": 1},
            ),
            ("", {"totals": {}, "overall": 0.0, "ignored": 0}),
        ]
        for lines, expected in cases:
            with self.subTest(lines=lines):
                self.assertEqual(summarize_expenses(lines=lines), expected)

    def test_extra_spaces_and_trailing_whitespace(self):
        result = summarize_expenses(lines="2026-01-02   rent    900  \n")
        self.assertEqual(result, {"totals": {"rent": 900.0}, "overall": 900.0, "ignored": 0})

    def test_blank_lines_are_not_ignored_lines(self):
        result = summarize_expenses(lines="\n   \n\t\n")
        self.assertEqual(result["ignored"], 0)

    def test_malformed_entries_are_counted(self):
        result = summarize_expenses(
            lines=(
                "2026-13-01 food 5.00\n"       # impossible month
                "2026-02-30 food 5.00\n"       # impossible day
                "26-09-03 food 5.00\n"         # not an ISO date
                "2026-09-03 two words 5.00\n"  # category is not a single word
                "2026-09-03 food\n"            # missing amount
                "2026-09-03 food 5.00 extra\n" # trailing junk
                "2026-09-03 food five\n"       # amount is not decimal
            )
        )
        self.assertEqual(result, {"totals": {}, "overall": 0.0, "ignored": 7})

    def test_rounding_is_exact_to_cents(self):
        result = summarize_expenses(
            lines="2026-03-01 a 0.1\n2026-03-01 a 0.2\n2026-03-02 b 1.005"
        )
        self.assertEqual(result["totals"]["a"], 0.3)
        self.assertEqual(result["totals"]["b"], 1.01)
        self.assertEqual(result["overall"], 1.31)

    def test_negative_amounts_are_accepted(self):
        result = summarize_expenses(lines="2026-04-01 refund -12.00\n2026-04-01 refund 20.00")
        self.assertEqual(result, {"totals": {"refund": 8.0}, "overall": 8.0, "ignored": 0})


if __name__ == "__main__":
    unittest.main()
