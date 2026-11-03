# Timewarrior reports

Two Timewarrior extensions provide a pie-chart report and a calendar grid. They
require Python 3.10+ and Timewarrior. No Python packages are needed.

## Install

From the project directory:

```bash
./install.sh
```

The installer copies both report launchers and their shared Python module to
`~/.timewarrior/extensions`. Rerun it to update them. To use another extensions
directory, set `TIMEWARRIOR_EXTENSIONS_DIR` when running the installer.

## Run

```bash
timew report pie_chart :week :color
timew report calendar_grid :week :color
timew report calendar_grid :month :color
timew report pie_chart :lastweek
timew report calendar_grid 2026-10-26 - 2026-11-02
timew report calendar_grid :week work
```

Timewarrior supplies the selected range and interval data to the extensions. A
finite date range is required. The weekly work target is fixed at 35 hours:
Monday through Friday each contribute 7 hours, weekends contribute zero, and
holidays are not deducted.

## Reports

The pie report summarizes work by complete tag combination. Untagged intervals
are grouped as `untagged`. The calendar grid shows each day's distribution, with
task colors consistent throughout the period and remaining target shown in gray.
The palette provides 32 distinct task colors before cycling. Color follows
Timewarrior's resolved setting; use `:color` or `:nocolor` to override it.
`NO_COLOR` also disables colors.

Intervals tagged `fundae` or `deporte` are grouped as “Out from work”. They are
excluded from work totals, target progress, and plots, but their total remains
visible in the textual summary. These tags are fixed for the extensions.

The reports use local timezone rules, including daylight-saving changes. Running
timers stop at the current instant, intervals are clipped to the selected period,
and overlapping intervals are rejected to prevent double counting.

The integration follows the official [extension API](https://timewarrior.net/docs/api/),
[report interface](https://timewarrior.net/reference/timew-report.1/), and
[export interface](https://timewarrior.net/reference/timew-export.1/).

## Verify

```bash
python3 -m unittest discover -s tests -v
```

The integration test uses a temporary Timewarrior database. If Timewarrior is
unavailable, that test is skipped.
