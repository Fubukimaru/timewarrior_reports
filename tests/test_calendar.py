from datetime import date, datetime, timezone
import re
import unittest
from zoneinfo import ZoneInfo

import timew_report as report

allocate = report.allocate
daily_totals = report.daily_totals
render_calendar = report.render_calendar


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.zone = ZoneInfo("Europe/Madrid")
        self.start = report.boundary(date(2026, 10, 26), self.zone)
        self.end = report.boundary(date(2026, 11, 2), self.zone)
        self.now = datetime(2026, 11, 3, tzinfo=timezone.utc)

    def test_multiple_tasks_fill_same_day_and_keep_colors(self):
        records = [
            {"start": "20261026T080000Z", "end": "20261026T100000Z", "tags": ["Code"]},
            {"start": "20261026T100000Z", "end": "20261026T110000Z", "tags": ["Meetings"]},
            {"start": "20261027T080000Z", "end": "20261027T090000Z", "tags": ["Code"]},
        ]
        groups, entries = report.summarize(records, self.start, self.end, self.now)
        days = daily_totals(entries, self.start, self.end, self.zone)
        self.assertEqual(dict(days[date(2026, 10, 26)]), {"Code": 7200, "Meetings": 3600})
        plain = render_calendar(groups, entries, self.start, self.end, self.zone, 37.5, False)
        colored = render_calendar(groups, entries, self.start, self.end, self.zone, 37.5, True)
        self.assertIn("3:00/7:30", plain)
        self.assertIn("Daily gaps: 33h 30m", plain)
        self.assertIn("\033[38;5;33m█", colored)
        self.assertIn("\033[38;5;39m█", colored)
        # All cells remain aligned regardless of ANSI escape lengths.
        for line in re.sub(r"\x1b\[[0-9;]*m", "", colored).splitlines():
            if line.startswith(("|", "+")):
                self.assertEqual(len(line), 78)

    def test_midnight_and_dst_split(self):
        start = report.boundary(date(2026, 10, 24), self.zone)
        end = report.boundary(date(2026, 10, 27), self.zone)
        records = [{"start": "20261024T213000Z", "end": "20261026T003000Z", "tags": ["Long task"]}]
        _, entries = report.summarize(records, start, end, self.now)
        days = daily_totals(entries, start, end, self.zone)
        self.assertEqual(days[date(2026, 10, 24)]["Long task"], 1800)
        self.assertEqual(days[date(2026, 10, 25)]["Long task"], 25 * 3600)
        self.assertEqual(days[date(2026, 10, 26)]["Long task"], 1.5 * 3600)
        self.assertEqual(sum(sum(values.values()) for values in days.values()), entries[0].seconds)

    def test_daily_overtime_does_not_hide_other_days_gaps(self):
        records = [{"start": "20261026T060000Z", "end": "20261026T160000Z", "tags": ["Work"]}]
        groups, entries = report.summarize(records, self.start, self.end, self.now)
        output = render_calendar(groups, entries, self.start, self.end, self.zone, 37.5, False)
        self.assertIn("Untracked: 27h 30m", output)
        self.assertIn("Daily gaps: 30h 00m  |  Daily overtime: 2h 30m", output)
        self.assertIn("10:00/7:30", output)

    def test_out_of_work_tags_are_text_only_and_excluded_from_daily_target(self):
        records = [{"start": "20261026T070000Z", "end": "20261026T090000Z", "tags": ["fundae"]}]
        groups, entries = report.summarize(records, self.start, self.end, self.now)
        output = render_calendar(groups, entries, self.start, self.end, self.zone, 35, False)
        self.assertIn("Tracked: 0h 00m  |  Untracked: 35h 00m", output)
        self.assertIn("Out from work: 2h 00m", output)
        self.assertNotIn("  1  Out from work", output)
        grid_lines = [line for line in output.splitlines() if line.startswith("|")]
        self.assertTrue(all(row[1:11] == "." * 10 for row in grid_lines[1:4]))

    def test_empty_partial_week_and_weekend(self):
        start = report.boundary(date(2026, 10, 28), self.zone)
        end = report.boundary(date(2026, 11, 1), self.zone)
        output = render_calendar([], [], start, end, self.zone, 37.5, False)
        self.assertIn("28 Oct", output)
        self.assertNotIn("26 Oct", output)
        self.assertNotIn("01 Nov", output)
        self.assertIn("0:00/7:30", output)
        self.assertIn("off", output)
        self.assertIn("Untracked: 22h 30m", output)

    def test_month_grid_wraps_across_weeks_and_subday_target(self):
        start = report.boundary(date(2026, 10, 1), self.zone)
        end = report.boundary(date(2026, 11, 1), self.zone)
        output = render_calendar([], [], start, end, self.zone, 37.5, False)
        self.assertEqual(sum(line.startswith("+") for line in output.splitlines()), 6)
        self.assertIn("01 Oct", output)
        self.assertIn("31 Oct", output)
        midday = report.timestamp("20261026T110000Z")
        output = render_calendar([], [], self.start, midday, self.zone, 37.5, False)
        self.assertIn("Untracked: 3h 45m", output)

    def test_allocation_conserves_cell_size(self):
        self.assertEqual(allocate([1, 1, 1], 10), [4, 3, 3])
        self.assertEqual(allocate([0, 0], 30), [0, 0])
        self.assertEqual(sum(allocate([1, 7, 2, 0.001], 30)), 30)


if __name__ == "__main__":
    unittest.main()
