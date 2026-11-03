from datetime import date, datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import timew_report as report


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.zone = ZoneInfo("Europe/Madrid")
        self.start = report.boundary(date(2026, 10, 26), self.zone)
        self.end = report.boundary(date(2026, 11, 2), self.zone)
        self.now = datetime(2026, 11, 3, tzinfo=timezone.utc)

    def test_week_target_and_missing_time(self):
        records = json.loads(Path("examples/week.json").read_text())
        groups, _ = report.summarize(records, self.start, self.end, self.now)
        self.assertEqual(sum(value for _, value in groups), 20 * 3600)
        self.assertEqual(dict(groups)["Development"], 15 * 3600)
        target = report.expected_seconds(self.start, self.end, self.zone, 37.5)
        self.assertEqual(target, 37.5 * 3600)
        output = report.render(groups, self.start, self.end, self.zone, target, False)
        self.assertIn("Untracked: 17h 30m", output)
        self.assertIn("46.7%", output)
        self.assertNotIn("\033", output)

    def test_clipping_running_and_tag_combinations(self):
        records = [
            {"start": "20261025T220000Z", "end": "20261026T010000Z", "tags": ["b", "a"]},
            {"start": "20261101T220000Z", "tags": ["a", "b"]},
        ]
        groups, _ = report.summarize(records, self.start, self.end, self.now)
        self.assertEqual(groups, [("a, b", 3 * 3600)])
        groups, _ = report.summarize(records, self.start, self.end, report.timestamp("20261101T223000Z"))
        self.assertEqual(groups, [("a, b", 2.5 * 3600)])

    def test_weekday_proration_and_dst(self):
        for monday in (date(2026, 3, 23), date(2026, 10, 19)):
            start = report.boundary(monday, self.zone)
            end = report.boundary(monday + timedelta(days=7), self.zone)
            self.assertEqual(report.expected_seconds(start, end, self.zone, 37.5), 135000)
        weekend_start = report.boundary(date(2026, 10, 31), self.zone)
        self.assertEqual(report.expected_seconds(weekend_start, self.end, self.zone, 37.5), 0)
        midday = report.timestamp("20261026T110000Z")
        self.assertEqual(report.expected_seconds(self.start, midday, self.zone, 37.5), 3.75 * 3600)

    def test_empty_and_overtime(self):
        empty = report.render([], self.start, self.end, self.zone, 135000, False)
        self.assertIn("Untracked: 37h 30m", empty)
        overtime = report.render([("work", 40 * 3600)], self.start, self.end, self.zone, 135000, False)
        self.assertIn("Over target: 2h 30m", overtime)
        self.assertIn("Untracked: 0h 00m", overtime)
        self.assertIn("100.0%", overtime)
        self.assertIn("no time to chart", report.render([], self.start, self.end, self.zone, 0, False))

    def test_palette_has_at_least_32_unique_colors(self):
        self.assertGreaterEqual(len(report.COLORS), 32)
        self.assertEqual(len(set(report.COLORS[:32])), 32)
        self.assertEqual(report.COLORS[:len(report.BASE_COLORS)], report.BASE_COLORS)

    def test_overlap_rejected(self):
        records = [{"start": "20261026T080000Z", "end": "20261026T100000Z"},
                   {"start": "20261026T090000Z", "end": "20261026T110000Z"}]
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            report.summarize(records, self.start, self.end, self.now)

    def test_tag_and_terminal_controls(self):
        records = [{"start": "20261026T080000Z", "end": "20261026T090000Z", "tags": ["hello\n\033[2J"]}]
        groups, _ = report.summarize(records, self.start, self.end, self.now)
        self.assertNotIn("\033", groups[0][0])
        self.assertNotIn("\n", groups[0][0])

    def test_out_of_work_tags_are_reported_but_excluded_from_work_and_pie(self):
        records = [
            {"start": "20261026T070000Z", "end": "20261026T080000Z", "tags": ["fundae"]},
            {"start": "20261026T080000Z", "end": "20261026T100000Z", "tags": ["deporte", "personal"]},
            {"start": "20261026T100000Z", "end": "20261026T110000Z", "tags": ["fundraising"]},
        ]
        groups, _ = report.summarize(records, self.start, self.end, self.now)
        self.assertEqual(dict(groups), {"Out from work": 3 * 3600, "fundraising": 3600})
        output = report.render(groups, self.start, self.end, self.zone, 7.5 * 3600, False)
        self.assertIn("Tracked: 1h 00m  |  Untracked: 6h 30m", output)
        self.assertIn("Out from work: 3h 00m", output)
        self.assertNotIn("Out from work", output.split("Distribution", 1)[1])

    def test_out_of_work_only_does_not_create_work_pie_slices(self):
        groups, _ = report.summarize(
            [{"start": "20261026T070000Z", "end": "20261026T080000Z", "tags": ["fundae"]}],
            self.start, self.end, self.now)
        with patch.object(report, "pie", wraps=report.pie) as pie_renderer:
            output = report.render(groups, self.start, self.end, self.zone, 3600, False)
        self.assertIn("Tracked: 0h 00m  |  Untracked: 1h 00m", output)
        self.assertIn("Out from work: 1h 00m", output)
        self.assertEqual([name for name, _, _ in pie_renderer.call_args.args[0]], ["untracked"])

    def test_extension_protocol(self):
        payload = "temp.report.start: 20261025T230000Z\ntemp.report.end: 20261101T230000Z\n\n[]"
        with patch.dict(os.environ, {"TZ": "Europe/Madrid"}), \
             patch("sys.stdin", new=io.StringIO(payload)), \
             patch("sys.stdout", new=io.StringIO()) as output:
            self.assertEqual(report.run_extension("pie"), 0)
        self.assertIn("Untracked: 35h 00m", output.getvalue())

    def test_extension_color_setting_and_no_color(self):
        for setting, no_color, expected in (("on", False, True), ("off", False, False), ("on", True, False)):
            with self.subTest(setting=setting, no_color=no_color):
                payload = f"color: {setting}\ntemp.report.start: 20261025T230000Z\ntemp.report.end: 20261101T230000Z\n\n[]"
                environment = dict(os.environ)
                environment.pop("NO_COLOR", None)
                if no_color:
                    environment["NO_COLOR"] = "1"
                environment["TZ"] = "Europe/Madrid"
                with patch.dict(os.environ, environment, clear=True), patch("sys.stdin", new=io.StringIO(payload)), patch("sys.stdout", new=io.StringIO()) as output:
                    self.assertEqual(report.run_extension("pie"), 0)
                self.assertEqual("\033[" in output.getvalue(), expected)

    @unittest.skipUnless(shutil.which("timew"), "Timewarrior is not installed")
    def test_real_timewarrior_export_and_extension(self):
        # All Timewarrior operations use a disposable database, never personal data.
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ, TIMEWARRIORDB=directory, TZ="Europe/Madrid")
            extensions = Path(directory, "extensions")
            extensions.mkdir()
            extensions.joinpath("pie_chart").symlink_to(Path("pie_chart").resolve())
            extensions.joinpath("calendar_grid").symlink_to(Path("calendar_grid").resolve())
            imported = subprocess.run(["timew", "import", "examples/week.json"], env=environment, capture_output=True, text=True)
            self.assertEqual(imported.returncode, 0, imported.stderr)
            extension = subprocess.run(["timew", "pie_chart", "2026-10-26", "-", "2026-11-02"], env=environment, capture_output=True, text=True)
            self.assertEqual(extension.returncode, 0, extension.stderr)
            self.assertIn("Untracked: 15h 00m", extension.stdout)
            environment.pop("NO_COLOR", None)
            for hint, expected in ((":color", True), (":nocolor", False)):
                with self.subTest(hint=hint):
                    colored = subprocess.run(["timew", "report", "pie_chart", "2026-10-26", "-", "2026-11-02", hint], env=environment, capture_output=True, text=True)
                    self.assertEqual(colored.returncode, 0, colored.stderr)
                    self.assertEqual("\033[38;5;" in colored.stdout, expected)
                    calendar = subprocess.run(["timew", "report", "calendar_grid", "2026-10-26", "-", "2026-11-02", hint], env=environment, capture_output=True, text=True)
                    self.assertEqual(calendar.returncode, 0, calendar.stderr)
                    self.assertIn("CALENDAR GRID", calendar.stdout)
                    self.assertIn("5:00/", calendar.stdout)
                    self.assertEqual("\033[38;5;" in calendar.stdout, expected)

if __name__ == "__main__":
    unittest.main()
