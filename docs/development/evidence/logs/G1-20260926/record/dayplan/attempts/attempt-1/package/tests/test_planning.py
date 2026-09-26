"""Supplementary checks on reading, fitting and reporting a pasted list."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app_code.planning import (  # noqa: E402
    fit_items,
    hours_or_fail,
    read_items,
    write_plan_text,
)


class ReadTests(unittest.TestCase):
    def test_common_formats_and_estimate(self):
        items = read_items(
            "Review budget - 1.5h\nStandup - 0:30\nClear inbox - 45m\nTidy desk"
        )
        self.assertEqual(
            items[:3],
            [
                {"name": "Review budget", "duration_minutes": 90, "estimated": False},
                {"name": "Standup", "duration_minutes": 30, "estimated": False},
                {"name": "Clear inbox", "duration_minutes": 45, "estimated": False},
            ],
        )
        self.assertEqual(items[3]["name"], "Tidy desk")
        self.assertTrue(items[3]["estimated"])
        self.assertGreater(items[3]["duration_minutes"], 0)

    def test_bullets_brackets_and_hour_minute_mix(self):
        items = read_items("- Ship update (2h 15m)\n1. Reply to Sam 20 mins\n\n")
        self.assertEqual(
            items,
            [
                {"name": "Ship update", "duration_minutes": 135, "estimated": False},
                {"name": "Reply to Sam", "duration_minutes": 20, "estimated": False},
            ],
        )


class FitTests(unittest.TestCase):
    def test_normal_run(self):
        result = fit_items(
            read_items(
                "Finish client report - 90m\nClear inbox - 30m\n"
                "Build deck - 2h\nCall supplier - 15m"
            ),
            4,
        )
        self.assertEqual(
            [(p["name"], p["duration_minutes"], p["running_minutes"]) for p in result["plan"]],
            [
                ("Finish client report", 90, 90),
                ("Clear inbox", 30, 120),
                ("Build deck", 120, 240),
            ],
        )
        self.assertEqual(result["total_minutes"], 240)
        self.assertEqual(result["short_by_minutes"], 15)
        self.assertEqual(
            [(w["name"], w["duration_minutes"]) for w in result["wont_fit"]],
            [("Call supplier", 15)],
        )

    def test_big_item_set_aside_smaller_fits(self):
        result = fit_items(
            read_items("Write proposal - 90m\nRecord video - 1h\nSend two emails - 20m"), 2
        )
        self.assertEqual(
            [(p["name"], p["running_minutes"]) for p in result["plan"]],
            [("Write proposal", 90), ("Send two emails", 110)],
        )
        self.assertEqual(result["total_minutes"], 110)
        self.assertEqual(result["wont_fit"][0]["name"], "Record video")
        self.assertEqual(result["short_by_minutes"], 60)

    def test_total_never_exceeds_and_nothing_dropped(self):
        items = read_items("A - 3h\nB - 30m\nC - 2h\nD - 10m")
        result = fit_items(items, 1)
        self.assertLessEqual(result["total_minutes"], 60)
        self.assertEqual(len(result["plan"]) + len(result["wont_fit"]), len(items))


class HoursTests(unittest.TestCase):
    def test_missing_hours_is_refused(self):
        with self.assertRaises(ValueError):
            hours_or_fail(None)
        with self.assertRaises(ValueError):
            hours_or_fail(0)


class ReportTests(unittest.TestCase):
    def test_plan_text_names_times_total_and_shortfall(self):
        text = write_plan_text(
            [
                {"name": "Finish client report", "duration_minutes": 90, "running_minutes": 90},
                {"name": "Clear inbox", "duration_minutes": 30, "running_minutes": 120},
                {"name": "Build deck", "duration_minutes": 120, "running_minutes": 240},
            ],
            [{"name": "Call supplier", "duration_minutes": 15}],
            4,
        )
        self.assertIn("1. Finish client report - 1h 30m", text)
        self.assertIn("Total planned: 4h of 4h available.", text)
        self.assertIn("Won't fit today:", text)
        self.assertIn("Call supplier - needs 15m", text)
        self.assertIn("Short by 15m", text)

    def test_estimates_are_labelled(self):
        text = write_plan_text(
            [{"name": "Tidy desk", "duration_minutes": 30, "running_minutes": 30, "estimated": True}],
            [],
            1,
        )
        self.assertIn("estimated", text)
        self.assertIn("Everything on the list fits today.", text)


if __name__ == "__main__":
    unittest.main()
