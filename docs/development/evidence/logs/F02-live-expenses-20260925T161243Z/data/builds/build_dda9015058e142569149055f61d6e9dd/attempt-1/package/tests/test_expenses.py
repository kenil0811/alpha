"""Supplementary tests for the summarize_expenses action."""

import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
)

from expenses import summarize_expenses  # noqa: E402


class SummarizeExpensesTests(unittest.TestCase):
    def test_groups_by_category(self):
        self.assertEqual(
            summarize_expenses(
                lines=(
                    "2026-09-03 groceries 42.50\n"
                    "2026-09-04 fuel 61.10\n"
                    "2026-09-05 groceries 7.25"
                )
            ),
            {"totals": {"groceries": 49.75, "fuel": 61.1}, "overall": 110.85, "ignored": 0},
        )

    def test_ignores_unparsable_and_blank_lines(self):
        self.assertEqual(
            summarize_expenses(
                lines="not a line\n2026-09-06 coffee 3.40\n\n2026-09-07 coffee 3.6"
            ),
            {"totals": {"coffee": 7.0}, "overall": 7.0, "ignored": 1},
        )

    def test_empty_input(self):
        self.assertEqual(
            summarize_expenses(lines=""),
            {"totals": {}, "overall": 0.0, "ignored": 0},
        )

    def test_rejects_impossible_dates_and_bad_shapes(self):
        cases = [
            "2026-13-45 coffee 3.40",
            "2026-09-06 two words 3.40",
            "2026-09-06 coffee",
            "2026-09-06 coffee abc",
            "26-09-06 coffee 3.40",
        ]
        for line in cases:
            with self.subTest(line=line):
                self.assertEqual(
                    summarize_expenses(lines=line),
                    {"totals": {}, "overall": 0.0, "ignored": 1},
                )

    def test_totals_are_exact_and_half_up(self):
        result = summarize_expenses(
            lines="2026-09-01 a 0.1\n2026-09-01 a 0.2\n2026-09-02 b 1.005"
        )
        self.assertEqual(result["totals"], {"a": 0.3, "b": 1.01})
        self.assertEqual(result["overall"], 1.31)
        self.assertEqual(result["ignored"], 0)

    def test_many_small_amounts_do_not_drift(self):
        lines = "\n".join("2026-09-01 snacks 0.10" for _ in range(30))
        self.assertEqual(
            summarize_expenses(lines=lines),
            {"totals": {"snacks": 3.0}, "overall": 3.0, "ignored": 0},
        )

    def test_accepts_extra_spacing_and_signed_amounts(self):
        self.assertEqual(
            summarize_expenses(lines="  2026-09-01   refund   -5.00  \n2026-09-02 refund 7"),
            {"totals": {"refund": 2.0}, "overall": 2.0, "ignored": 0},
        )


if __name__ == "__main__":
    unittest.main()
