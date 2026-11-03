"""Shared calculations and pie rendering for the Timewarrior report extensions."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
import colorsys
import json
import math
import os
import re
import sys
from zoneinfo import ZoneInfo

UTC = timezone.utc
BASE_COLORS = (33, 39, 75, 141, 205, 214, 118, 44)
OUT_OF_WORK_TAGS = ("fundae", "deporte")
OUT_OF_WORK_LABEL = "Out from work"
WEEKLY_HOURS = 35


def build_palette():
    levels = (0, 95, 135, 175, 215, 255)
    colors = list(BASE_COLORS)
    for step in range(360):
        rgb = colorsys.hsv_to_rgb(step / 360, 0.85, 0.95)
        channels = [min(range(6), key=lambda i: abs(levels[i] - round(channel * 255)))
                    for channel in rgb]
        color = 16 + 36 * channels[0] + 6 * channels[1] + channels[2]
        if color not in colors:
            colors.append(color)
        if len(colors) == 32:
            break
    return tuple(colors)


COLORS = build_palette()


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

    @property
    def seconds(self):
        return (self.end - self.start).total_seconds()


def summarize(records, start, end, now):
    if not isinstance(records, list):
        raise ValueError("Expected a JSON array of Timewarrior intervals")
    out_of_work_tags = set(OUT_OF_WORK_TAGS)
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
        if out_of_work_tags.intersection(tags):
            label = OUT_OF_WORK_LABEL
        else:
            label = ", ".join(sorted(set(tags))) or "untagged"
        label = safe_label(label)
        entry = Entry(label, left, right)
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


def render(groups, start, end, zone, target, color):
    work_groups = [(name, value) for name, value in groups if name != OUT_OF_WORK_LABEL]
    out_of_work = sum(value for name, value in groups if name == OUT_OF_WORK_LABEL)
    tracked = sum(value for _, value in work_groups)
    untracked = max(0, target - tracked)
    denominator = max(target, tracked)
    slices = [(name, value, index) for index, (name, value) in enumerate(work_groups)]
    slices.append(("untracked", untracked, -1))
    lines = ["TIMEWARRIOR · TIME DISTRIBUTION",
             f"Period: {start.astimezone(zone):%Y-%m-%d %H:%M %Z} → {end.astimezone(zone):%Y-%m-%d %H:%M %Z} (end exclusive)",
             f"Target: {duration(target)}  |  Tracked: {duration(tracked)}  |  Untracked: {duration(untracked)}"]
    if out_of_work:
        lines.append(f"Out from work: {duration(out_of_work)}")
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
    return "\n".join(lines)


def daily_totals(entries, start, end, zone):
    """Split intervals at local midnights, using UTC elapsed time across DST."""
    days = {}
    day = start.astimezone(zone).date()
    while boundary(day, zone) < end:
        days[day] = defaultdict(float)
        day += timedelta(days=1)
    for entry in entries:
        left, right = max(entry.start, start), min(entry.end, end)
        while left < right:
            day = left.astimezone(zone).date()
            midnight = boundary(day + timedelta(days=1), zone)
            stop = min(right, midnight)
            days[day][entry.label] += (stop - left).total_seconds()
            left = stop
    return days


def allocate(weights, size):
    """Largest-remainder rounding keeps each cell exactly the requested size."""
    total = sum(weights)
    if not total:
        return [0] * len(weights)
    exact = [weight / total * size for weight in weights]
    counts = [math.floor(value) for value in exact]
    remainder = size - sum(counts)
    order = sorted(range(len(weights)), key=lambda i: (-(exact[i] - counts[i]), i))
    for i in order[:remainder]:
        counts[i] += 1
    return counts


def marker(index):
    return str(index + 1) if index < 9 else chr(65 + (index - 9) % 26)


def clock(seconds):
    minutes = int(seconds / 60 + 0.5)
    return f"{minutes // 60}:{minutes % 60:02d}"


def render_calendar(groups, entries, start, end, zone, weekly_hours, color):
    work_groups = [(label, value) for label, value in groups if label != OUT_OF_WORK_LABEL]
    out_of_work = sum(value for label, value in groups if label == OUT_OF_WORK_LABEL)
    work_entries = [entry for entry in entries if entry.label != OUT_OF_WORK_LABEL]
    days = daily_totals(work_entries, start, end, zone)
    targets = {day: expected_seconds(max(start, boundary(day, zone)),
                                   min(end, boundary(day + timedelta(days=1), zone)),
                                   zone, weekly_hours) for day in days}
    tracked = sum(value for _, value in work_groups)
    target = sum(targets.values())
    gaps = sum(max(0, targets[day] - sum(totals.values())) for day, totals in days.items())
    overtime = sum(max(0, sum(totals.values()) - targets[day]) for day, totals in days.items())
    lines = ["TIMEWARRIOR · CALENDAR GRID",
             f"Period: {start.astimezone(zone):%Y-%m-%d %H:%M %Z} → {end.astimezone(zone):%Y-%m-%d %H:%M %Z} (end exclusive)",
             f"Target: {duration(target)}  |  Tracked: {duration(tracked)}  |  Untracked: {duration(max(0, target - tracked))}",
             f"Daily gaps: {duration(gaps)}  |  Daily overtime: {duration(overtime)}",
             "", "Each cell: task shares of daily target (or tracked time when over target).",
             "Gray / . = untracked; footer = tracked/target; + = over daily target.", ""]
    if out_of_work:
        lines.insert(4, f"Out from work: {duration(out_of_work)}")
    indices = {label: i for i, (label, _) in enumerate(work_groups)}
    width, rows = 10, 3
    empty = [" " * width] * (rows + 2)

    def cell(day):
        if day not in days:
            return empty
        totals = days[day]
        daily_tracked = sum(totals.values())
        missing = max(0, targets[day] - daily_tracked)
        slices = [(label, totals[label], indices[label]) for label, _ in work_groups if totals.get(label)]
        slices.append(("untracked", missing, -1))
        counts = allocate([value for _, value, _ in slices], width * rows)
        pixels = []
        for (_, _, index), count in zip(slices, counts):
            symbol = "." if index == -1 else marker(index)
            pixels.extend([paint("█" if color else symbol, index, color)] * count)
        if not pixels:
            pixels = [" "] * (width * rows)
        fill = ["".join(pixels[offset:offset + width]) for offset in range(0, width * rows, width)][::-1]
        footer = f"{clock(daily_tracked)}/{clock(targets[day])}"
        if not daily_tracked and not targets[day]:
            footer = "off"
        if len(footer) > width:
            footer = f"{clock(daily_tracked)} trk"
        heading = f"{day:%d %b}" + (" +" if daily_tracked > targets[day] else "")
        return [heading.ljust(width), *fill, footer[:width].ljust(width)]

    first = min(days)
    last = max(days)
    monday = first - timedelta(days=first.weekday())
    lines.append(" " + " ".join(name.center(width) for name in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")))
    border = "+" + "+".join("-" * width for _ in range(7)) + "+"
    lines.append(border)
    while monday <= last:
        cells = [cell(monday + timedelta(days=i)) for i in range(7)]
        for row in range(rows + 2):
            lines.append("|" + "|".join(column[row] for column in cells) + "|")
        lines.append(border)
        monday += timedelta(days=7)
    lines += ["", "Tasks (colors stay the same across all days)"]
    for index, (label, seconds) in enumerate(work_groups):
        lines.append(paint(f" {marker(index):>2}  {label}  {duration(seconds)}", index, color))
    lines.append(paint(f"  .  untracked (daily gaps)  {duration(gaps)}", -1, color))
    lines.append("Small tasks may round to zero blocks; all durations are included in the totals.")
    return "\n".join(lines)


def run_extension(view):
    try:
        if view not in ("pie", "calendar"):
            raise ValueError(f"Unknown report view: {view}")
        zone = local_zone()
        now = datetime.now(UTC)
        header, payload = sys.stdin.read().split("\n\n", 1)
        config = dict(line.split(": ", 1) for line in header.splitlines() if ": " in line)
        if not config.get("temp.report.start") or not config.get("temp.report.end"):
            raise ValueError("Extension requires a finite period")
        start, end = timestamp(config["temp.report.start"]), timestamp(config["temp.report.end"])
        if start >= end:
            raise ValueError("The end date must be after the start date")
        records = json.loads(payload)
        groups, entries = summarize(records, start, end, now)
        color = config.get("color", "").strip().lower() in ("on", "1", "yes", "y", "true")
        color = color and "NO_COLOR" not in os.environ
        if view == "calendar":
            print(render_calendar(groups, entries, start, end, zone, WEEKLY_HOURS, color))
        else:
            target = expected_seconds(start, end, zone, WEEKLY_HOURS)
            print(render(groups, start, end, zone, target, color))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"timew-report: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    print("Run this report through Timewarrior: timew report pie_chart or calendar_grid.", file=sys.stderr)
    raise SystemExit(2)
