"""Read-only Timewarrior reporting, using only the Python standard library."""
import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

UTC = timezone.utc
COLORS = (33, 39, 75, 141, 205, 214, 118, 44)


def local_zone():
    name = os.environ.get("TZ", "").removeprefix(":")
    if name:
        return ZoneInfo(name)
    # Read zoneinfo rules, preserving DST across the selected period.
    with open("/etc/localtime", "rb") as source:
        return ZoneInfo.from_file(source)


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp needs a timezone: {value}")
    return parsed.astimezone(UTC)


def boundary(day, zone):
    return datetime.combine(day, time.min, zone).astimezone(UTC)


def period_bounds(period, today, zone):
    if period == "today":
        start, end = today, today + timedelta(days=1)
    elif period in ("week", "lastweek"):
        start = today - timedelta(days=today.weekday())
        if period == "lastweek":
            start -= timedelta(days=7)
        end = start + timedelta(days=7)
    else:
        start = today.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
    return boundary(start, zone), boundary(end, zone)


def expected_seconds(start, end, zone, weekly_hours):
    """Prorate each weekday by its local-day fraction, including across DST."""
    total = 0.0
    day = start.astimezone(zone).date()
    while boundary(day, zone) < end:
        left = boundary(day, zone)
        right = boundary(day + timedelta(days=1), zone)
        if day.weekday() < 5:
            fraction = max(0, (min(end, right) - max(start, left)).total_seconds())
            total += fraction / (right - left).total_seconds() * weekly_hours / 5 * 3600
        day += timedelta(days=1)
    return total


def safe_label(value):
    # Keep annotations and tags from injecting terminal control sequences.
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", str(value))


@dataclass
class Entry:
    label: str
    start: datetime
    end: datetime
    identifier: str

    @property
    def seconds(self):
        return (self.end - self.start).total_seconds()


def summarize(records, start, end, now, group_by):
    if not isinstance(records, list):
        raise ValueError("Expected a JSON array of Timewarrior intervals")
    entries = []
    totals = defaultdict(float)
    for record in records:
        left = timestamp(record["start"])
        right = timestamp(record["end"]) if record.get("end") else now
        if right < left:
            raise ValueError("An interval ends before it starts")
        left, right = max(left, start), min(right, end, now)
        if right <= left:
            continue
        tags = record.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError("Interval tags must be a list of strings")
        if group_by == "annotation":
            label = record.get("annotation") or ", ".join(sorted(set(tags))) or "untagged"
        else:
            label = ", ".join(sorted(set(tags))) or "untagged"
        label = safe_label(label)
        entry = Entry(label, left, right, safe_label(record.get("id", "-")))
        entries.append(entry)
        totals[label] += entry.seconds
    entries.sort(key=lambda entry: entry.start)
    previous_end = None
    for entry in entries:
        if previous_end is not None and entry.start < previous_end:
            raise ValueError("Overlapping intervals would count time twice; resolve them before reporting")
        previous_end = entry.end
    return sorted(totals.items(), key=lambda pair: (-pair[1], pair[0])), entries


def duration(seconds):
    minutes = int(seconds / 60 + 0.5)
    return f"{minutes // 60}h {minutes % 60:02d}m"


def paint(text, index, color):
    code = 240 if index == -1 else COLORS[index % len(COLORS)]
    return f"\033[38;5;{code}m{text}\033[0m" if color else text


def pie(slices, color):
    total = sum(value for _, value, _ in slices)
    if not total:
        return ["  (no time to chart)"]
    limits = []
    accumulated = 0.0
    for _, value, _ in slices:
        accumulated += value / total * math.tau
        limits.append(accumulated)
    rows = []
    radius = 6
    for y in range(-radius, radius + 1):
        row = "  "
        for x in range(-radius * 2, radius * 2 + 1):
            if (x / 2) ** 2 + y ** 2 > radius ** 2:
                row += " "
                continue
            angle = (math.atan2(x / 2, -y) + math.tau) % math.tau
            index = next((i for i, limit in enumerate(limits) if angle < limit), len(slices) - 1)
            symbol = str(index + 1) if index < 9 else chr(65 + (index - 9) % 26)
            row += paint("█" if color else symbol, slices[index][2], color)
        rows.append(row.rstrip())
    return rows


def render(groups, entries, start, end, zone, target, color, details=False):
    tracked = sum(value for _, value in groups)
    untracked = max(0, target - tracked)
    denominator = max(target, tracked)
    slices = [(name, value, index) for index, (name, value) in enumerate(groups)]
    slices.append(("untracked", untracked, -1))
    lines = ["TIMEWARRIOR · TIME DISTRIBUTION",
             f"Period: {start.astimezone(zone):%Y-%m-%d %H:%M %Z} → {end.astimezone(zone):%Y-%m-%d %H:%M %Z} (end exclusive)",
             f"Target: {duration(target)}  |  Tracked: {duration(tracked)}  |  Untracked: {duration(untracked)}"]
    if tracked > target:
        lines.append(f"Over target: {duration(tracked - target)}")
    lines += ["", "Distribution (share of the greater of target or tracked time)"]
    width = min(48, max(12, *(len(name) for name, _, _ in slices)))
    for index, (name, value, palette) in enumerate(slices):
        share = value / denominator if denominator else 0
        label = name if len(name) <= width else name[:width - 1] + "…"
        marker = str(index + 1) if index < 9 else chr(65 + (index - 9) % 26)
        bar = "█" * round(share * 24)
        lines.append(paint(f"{marker:>2}  {label:<{width}}  {duration(value):>9}  {share:6.1%}  {bar}", palette, color))
    lines.append("")
    lines.extend(pie(slices, color))
    if details:
        lines += ["", "Intervals (clipped to the period; running timers end at now)"]
        for entry in entries:
            lines.append(f"@{entry.identifier}  {entry.start.astimezone(zone):%Y-%m-%d %H:%M} → "
                         f"{entry.end.astimezone(zone):%Y-%m-%d %H:%M}  {duration(entry.seconds):>9}  {entry.label}")
        if not entries:
            lines.append("  No tracked intervals.")
    return "\n".join(lines)


def parser():
    result = argparse.ArgumentParser(description="Visual Timewarrior reports against a working-week target.")
    result.add_argument("period", nargs="?", choices=("week", "lastweek", "month", "today"), default="week")
    result.add_argument("--from", dest="start_date", type=date.fromisoformat, help="First date, inclusive (YYYY-MM-DD)")
    result.add_argument("--to", dest="end_date", type=date.fromisoformat, help="End date, exclusive (YYYY-MM-DD)")
    result.add_argument("--weekly-hours", type=float, default=35)
    result.add_argument("--timezone", help="IANA timezone, e.g. Europe/Madrid (default: system timezone)")
    result.add_argument("--tag", action="append", default=[], help="Filter by tag; repeat to require multiple tags")
    result.add_argument("--group-by", choices=("tags", "annotation"), default="tags")
    result.add_argument("--view", choices=("pie", "calendar"), default="pie", help="Report layout (default: pie)")
    result.add_argument("--details", action="store_true", help="Also list individual intervals")
    result.add_argument("--input", type=Path, help="Read a timew export JSON file; '-' reads stdin")
    result.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    result.add_argument("--extension", action="store_true", help="Read the Timewarrior extension protocol from stdin")
    return result


def main(argv=None):
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    try:
        zone = ZoneInfo(args.timezone) if args.timezone else local_zone()
        now = datetime.now(UTC)
        if not math.isfinite(args.weekly_hours) or args.weekly_hours <= 0:
            raise ValueError("--weekly-hours must be a positive finite number")
        if bool(args.start_date) != bool(args.end_date):
            raise ValueError("Use --from and --to together")
        config = {}
        if args.extension:
            header, payload = sys.stdin.read().split("\n\n", 1)
            config = dict(line.split(": ", 1) for line in header.splitlines() if ": " in line)
            if not config.get("temp.report.start") or not config.get("temp.report.end"):
                raise ValueError("Extension requires a finite period, e.g. timew report pie_chart :week")
            start, end = timestamp(config["temp.report.start"]), timestamp(config["temp.report.end"])
            records = json.loads(payload)
        else:
            start, end = (boundary(args.start_date, zone), boundary(args.end_date, zone)) if args.start_date else period_bounds(args.period, now.astimezone(zone).date(), zone)
            if start >= end:
                raise ValueError("The end date must be after the start date")
            if args.input:
                records = json.loads(sys.stdin.read() if str(args.input) == "-" else args.input.read_text())
            else:
                command = ["timew", "export", start.strftime("%Y%m%dT%H%M%SZ"), "-", end.strftime("%Y%m%dT%H%M%SZ"), *args.tag]
                exported = subprocess.run(command, capture_output=True, text=True, check=False)
                if exported.returncode:
                    raise ValueError(exported.stderr.strip() or exported.stdout.strip() or "Timewarrior export failed")
                records = json.loads(exported.stdout)
        if start >= end:
            raise ValueError("The end date must be after the start date")
        if args.tag:
            if not isinstance(records, list):
                raise ValueError("Expected a JSON array of Timewarrior intervals")
            records = [record for record in records if all(tag in record.get("tags", []) for tag in args.tag)]
        groups, entries = summarize(records, start, end, now, args.group_by)
        target = expected_seconds(start, end, zone, args.weekly_hours)
        # Timewarrior captures extension stdout, so isatty() is false even when
        # the parent is displaying the report in a terminal. Its protocol carries
        # the resolved color setting, including :color / :nocolor overrides.
        terminal_color = sys.stdout.isatty()
        if args.extension and "color" in config:
            terminal_color = config["color"].strip().lower() in ("on", "1", "yes", "y", "true")
        color = args.color == "always" or (args.color == "auto" and terminal_color and "NO_COLOR" not in os.environ)
        if args.view == "calendar":
            from calendar_report import render_calendar
            print(render_calendar(groups, entries, start, end, zone, args.weekly_hours, color))
        else:
            print(render(groups, entries, start, end, zone, target, color, args.details))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"timew-report: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
