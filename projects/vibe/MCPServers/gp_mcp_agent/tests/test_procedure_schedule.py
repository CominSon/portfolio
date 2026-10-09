"""Тесты summarize_procedure_schedule."""

import unittest
from datetime import datetime, timedelta

from gp_mcp_agent.src.utils.procedure_schedule import (
    format_schedule_edge_label,
    format_weekdays_ru,
    summarize_procedure_schedule,
)


class ProcedureScheduleTest(unittest.TestCase):
    def test_inactive_after_30_days(self):
        old = datetime.now() - timedelta(days=45)
        rows = [
            {"date_start": old.strftime("%Y-%m-%d %H:%M:%S"), "date_end": old, "status": "DONE"},
        ]
        summary = summarize_procedure_schedule(rows)
        self.assertTrue(summary["inactive"])
        self.assertGreater(summary["days_since_last_run"], 30)
        self.assertIsNotNone(summary["last_run_at"])

    def test_active_recent_run(self):
        recent = datetime.now() - timedelta(days=2)
        rows = [
            {"date_start": recent.strftime("%Y-%m-%d %H:%M:%S"), "date_end": recent, "status": "DONE"},
        ]
        summary = summarize_procedure_schedule(rows)
        self.assertFalse(summary["inactive"])

    def test_schedule_label_ru_weekday_and_time(self):
        # фиксированные пн/вт/ср/чт/пт в ~06:15
        rows = []
        base = datetime(2026, 3, 2, 6, 15, 0)  # Monday
        for i in range(5):
            ds = base + timedelta(days=i)
            de = ds + timedelta(minutes=10)
            rows.append({
                "date_start": ds.strftime("%Y-%m-%d %H:%M:%S"),
                "date_end": de.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "DONE",
            })
        summary = summarize_procedure_schedule(rows)
        self.assertEqual(summary["weekdays_ru_label"], "пн–пт")
        self.assertEqual(summary["typical_start_time"], "06:15")
        self.assertEqual(summary["schedule_label"], "пн–пт 06:15")
        self.assertEqual(
            format_schedule_edge_label(summary),
            "пн–пт 06:15",
        )
        self.assertEqual(format_weekdays_ru([0, 1, 2, 3, 4]), "пн–пт")


if __name__ == "__main__":
    unittest.main()
