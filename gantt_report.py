"""Terminal timeline with half-hour cells measured from local midnight."""
from collections import defaultdict
from datetime import timedelta
from math import ceil
from string import ascii_lowercase, ascii_uppercase, digits

from timew_report import OUT_OF_WORK_LABEL, boundary, duration, paint


def render_gantt(groups, entries, start, end, zone, color):
    out_of_work = sum(s for label, s in groups if label == OUT_OF_WORK_LABEL)
    groups = [(label, s) for label, s in groups if label != OUT_OF_WORK_LABEL]
    step = timedelta(minutes=30)
    symbols = digits[1:] + ascii_uppercase + ascii_lowercase
    indices = {label: i for i, (label, _) in enumerate(groups)}

    def marker(i):
        return paint(symbols[i] if i < len(symbols) else "+", i, color)

    cells = defaultdict(dict)
    daily = defaultdict(float)
    for entry in entries:
        if entry.label == OUT_OF_WORK_LABEL:
            continue
        a = entry.start
        while a < entry.end:
            day = a.astimezone(zone).date()
            midnight = boundary(day, zone)
            b = min(entry.end, boundary(day + timedelta(days=1), zone))
            for slot in range((a - midnight) // step, ceil((b - midnight) / step)):
                i = indices[entry.label]
                previous = cells[day].get(slot, i)
                cells[day][slot] = i if previous == i else -1
            daily[day] += (b - a).total_seconds()
            a = b

    lines = ["TIMEWARRIOR · GANTT CHART",
             f"Total tracked: {duration(sum(s for _, s in groups))}",
             "Each cell = 30 minutes since local midnight; . idle, * multiple tasks.",
             "", "Date        00          06          12          18       "]
    day = start.astimezone(zone).date()
    while boundary(day, zone) < end:
        midnight = boundary(day, zone)
        following = boundary(day + timedelta(days=1), zone)
        row = []
        for slot in range(ceil((following - midnight) / step)):
            i = cells[day].get(slot)
            left = midnight + slot * step
            if left >= end or left + step <= start:
                row.append(" ")
            else:
                row.append("." if i is None else "*" if i == -1 else marker(i))
        lines.append(f"{day}  {''.join(row)}  {duration(daily[day])}")
        day += timedelta(days=1)
    lines += ["", "Tasks"]
    lines.extend(f"{marker(i)}  {label}  {duration(seconds)}"
                 for i, (label, seconds) in enumerate(groups))
    if not groups:
        lines.append("No tracked intervals.")
    if out_of_work:
        lines.append(f"Out from work: {duration(out_of_work)}")
    return "\n".join(lines)
