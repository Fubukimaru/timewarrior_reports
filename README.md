# Timewarrior visual report

A dependency-free Python CLI with a time totals table, terminal pie chart, calendar
grid, and working-week coverage. The current default is **35 hours/week**;
use `--weekly-hours 37.5` for a 37.5-hour week. Requires Python 3.10+ and Timewarrior
when reading live data. JSON files can be reported without Timewarrior installed.

## Run

From this directory:

```bash
python3 timew_report.py                      # This week (Monday to Monday)
python3 timew_report.py lastweek --details   # Last week, including each interval
python3 timew_report.py month
python3 timew_report.py today
python3 timew_report.py --from 2026-10-26 --to 2026-11-02
python3 timew_report.py week --tag work
python3 timew_report.py --view calendar week
python3 timew_report.py --view calendar month --color always
```

`--to` is **exclusive**: the example includes October 26 through November 1.
Local system time is used; override it with `--timezone Europe/Madrid` or `TZ`.
Repeated `--tag` options require every supplied tag. When filtering, “untracked”
is the difference between the target and the **filtered** tracked time.

Optional install in a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/timew-report lastweek
```

## Working schedule and grouping

- Each Monday–Friday contributes one fifth of the weekly target (7 hours with the
  current default); weekends contribute zero. Holidays and leave are not deducted.
  Change the schedule with `--weekly-hours 37.5` or `--weekly-hours 40`.
- The target covers the **whole selected period**, including future weekdays in
  the current week or month. “Untracked” means remaining target hours, not a list
  of gaps in a daily calendar. It does not assume particular office hours.
- All tracked time in the period counts toward the target, including weekend time.
- `untracked = max(target − tracked, 0)`. Extra time is displayed as “Over target”.
- Percentages and pie slices use `max(target, tracked)` as their denominator.
- Each distinct complete tag combination gets one row, so an interval with multiple
  tags is counted once. Untagged intervals use `untagged`. Use
  `--group-by annotation` to group by annotation, with tags as the fallback.
- `--details` in the pie view lists each interval and its duration. Intervals are clipped to the
  selected range; running timers stop at the current instant. Overlapping
  intervals are rejected to prevent double counting.
- Subday ranges from the extension prorate the weekday target by the fraction of
  the local calendar day selected. Date and DST calculations use timezone rules.
- Calculations use seconds; displayed durations round to the nearest minute.

Color is automatic on terminals, with a gray untracked slice. Redirected output
and `NO_COLOR` use numbered pie slices matching the table. Override with
`--color always` or `--color never`.

## Preview with sample data

```bash
python3 timew_report.py --input examples/week.json \
  --from 2026-10-26 --to 2026-11-02 --timezone Europe/Madrid --weekly-hours 37.5 --details
```

The sample contains 15 hours of development, 3 hours of meetings and 2 hours of
planning. Against 37.5 hours, **17 hours 30 minutes are untracked (46.7%)**.

You can also report exported data:

```bash
timew export :week | python3 timew_report.py --input -
```

JSON input carries no period metadata. Set the matching period or `--from`/`--to`
when reading a file or pipe; otherwise the current week is used.

## Calendar grid

`--view calendar` draws Monday–Sunday cells, with additional rows for longer
periods. Each day fills from the bottom with task colors proportional to duration;
the remaining daily target is gray. Task colors stay consistent across the period.
With colors disabled, task numbers match the legend and `.` means untracked.
Each tile has 30 blocks, so small tasks can round to zero blocks; totals retain
their full durations. The grid is 78 terminal columns wide.

The footer shows tracked/target as `H:MM/H:MM`. A `+` beside the date indicates daily
overtime. Weekend days without tracked time show `off`; days outside the requested
period are blank. Intervals crossing midnight split across their local calendar days.
Tiles show daily distribution, rather than particular times of day.

The summary's `Untracked` is the remaining target over the whole period, as in the
pie chart. `Daily gaps` adds each day's missing hours; `Daily overtime` adds each
day's extra hours, including weekend work. An extra hour on Monday reduces the
period's remaining target, while Tuesday's tile still shows Tuesday's own gap.

Sample:

```bash
python3 timew_report.py --view calendar --input examples/week.json \
  --from 2026-10-26 --to 2026-11-02 --timezone Europe/Madrid --color always
```

## Use as Timewarrior extensions

The executables `pie_chart` and `calendar_grid` read Timewarrior's extension protocol,
including the selected range. From the project directory, symlink them into your
Timewarrior extensions directory:

```bash
mkdir -p ~/.timewarrior/extensions
ln -s "$PWD/pie_chart" ~/.timewarrior/extensions/pie_chart
ln -s "$PWD/calendar_grid" ~/.timewarrior/extensions/calendar_grid
timew report pie_chart :week :color
timew report calendar_grid :week :color
timew report calendar_grid :month :color
timew report pie_chart :lastweek
timew report calendar_grid 2026-10-26 - 2026-11-02
timew report calendar_grid :week work
```

`pie_chart` replaces the former `timew_visual` launcher (sometimes installed as
`visual.py`). Replace any old symlink pointing to that launcher with `pie_chart`.

Both extensions honor Timewarrior's resolved color setting, even though Timewarrior
captures its output. Force color on or off with:

```bash
timew report pie_chart :week :color
timew report calendar_grid :week :nocolor
```

`NO_COLOR` also disables automatic extension colors.

Use the extension directory shown by `timew extensions` if your installation uses
a different location. Keep this project directory in place: the launcher imports
the adjacent Python module. A finite date range is required. The extension uses
the current default 35-hour schedule; use the standalone CLI for customization and
individual interval details. No personal tracking data or configuration is changed.

The integration follows the official [extension API](https://timewarrior.net/docs/api/),
[report interface](https://timewarrior.net/reference/timew-report.1/), and
[export interface](https://timewarrior.net/reference/timew-export.1/).

## Verify

```bash
python3 -m unittest discover -s tests -v
```

The integration test uses a temporary Timewarrior database. If Timewarrior is
unavailable, that test is skipped; the calculation tests still run.
