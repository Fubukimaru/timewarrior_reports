"""Calendar cells filled proportionally with each day's tasks and untracked time."""
from collections import defaultdict
from datetime import timedelta
import math

from timew_report import boundary, duration, expected_seconds, paint


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
    days = daily_totals(entries, start, end, zone)
    targets = {day: expected_seconds(max(start, boundary(day, zone)),
                                   min(end, boundary(day + timedelta(days=1), zone)),
                                   zone, weekly_hours) for day in days}
    tracked = sum(value for _, value in groups)
    target = sum(targets.values())
    gaps = sum(max(0, targets[day] - sum(totals.values())) for day, totals in days.items())
    overtime = sum(max(0, sum(totals.values()) - targets[day]) for day, totals in days.items())
    lines = ["TIMEWARRIOR · CALENDAR GRID",
             f"Period: {start.astimezone(zone):%Y-%m-%d %H:%M %Z} → {end.astimezone(zone):%Y-%m-%d %H:%M %Z} (end exclusive)",
             f"Target: {duration(target)}  |  Tracked: {duration(tracked)}  |  Untracked: {duration(max(0, target - tracked))}",
             f"Daily gaps: {duration(gaps)}  |  Daily overtime: {duration(overtime)}",
             "", "Each cell: task shares of daily target (or tracked time when over target).",
             "Gray / . = untracked; footer = tracked/target; + = over daily target.", ""]
    indices = {label: i for i, (label, _) in enumerate(groups)}
    width, rows = 10, 3
    empty = [" " * width] * (rows + 2)

    def cell(day):
        if day not in days:
            return empty
        totals = days[day]
        daily_tracked = sum(totals.values())
        missing = max(0, targets[day] - daily_tracked)
        slices = [(label, totals[label], indices[label]) for label, _ in groups if totals.get(label)]
        slices.append(("untracked", missing, -1))
        counts = allocate([value for _, value, _ in slices], width * rows)
        # Fill from the bottom, like a calendar tile accumulating work.
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
        # Unusually large daily targets remain readable outside the fixed cell.
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
    for index, (label, seconds) in enumerate(groups):
        lines.append(paint(f" {marker(index):>2}  {label}  {duration(seconds)}", index, color))
    lines.append(paint(f"  .  untracked (daily gaps)  {duration(gaps)}", -1, color))
    lines.append("Small tasks may round to zero blocks; all durations are included in the totals.")
    return "\n".join(lines)
