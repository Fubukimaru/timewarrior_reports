# Timewarrior reports

Three Timewarrior extensions provide a pie chart, calendar grid and terminal Gantt chart. They
require Python 3.10+ and Timewarrior. No Python packages are needed.

## Install

From the project directory:

```bash
./install.sh
```

The installer copies the report launchers and Python modules to
`~/.timewarrior/extensions`. Rerun it to update them. To use another extensions
directory, set `TIMEWARRIOR_EXTENSIONS_DIR` when running the installer.
The `timew-tags` command is installed to `~/.local/bin`; ensure that directory
is on your `PATH`, or set `TIMEWARRIOR_REPORTS_BIN_DIR` to another directory.

## Run

```bash
timew report pie_chart :week :color
timew report calendar_grid :week :color
timew report calendar_grid :month :color
timew report gantt_chart :month
timew report pie_chart :lastweek
timew report calendar_grid 2026-10-26 - 2026-11-02
timew report calendar_grid :week work
timew-tags :week meeting coding
timew-tags pie_chart 2026-01-01 - 2026-12-30 code read meeting
timew-tags 2026-10-26 - 2026-11-02 meeting coding
timew-tags from 2026-10-26 for 3days -- meeting 'project work'
```

`timew-tags` reports each requested tag independently, including intervals with
other tags. It defaults to `:week` when no range is given. For multiword ranges
other than `START - END` or `START to END`, put `--` between the range and tags.
Quote tags containing spaces. A matching interval with multiple requested tags
contributes to each tag, while the matching-time total counts it once. Intervals
tagged `fundae` or `deporte` count only for those tags when explicitly requested.
Add `pie_chart` before the range for a chart of the individual tag totals; its
slices include overlapping time in each matching tag.
The existing reports and their native Timewarrior tag filters are unchanged.

Timewarrior supplies the selected range and interval data to the extensions. A
finite date range is required. The weekly work target is fixed at 35 hours:
Monday through Friday each contribute 7 hours, weekends contribute zero, and
holidays are not deducted.

## Reports

The Gantt chart prints one timeline per local day. Each cell represents 30
elapsed minutes from midnight. Task markers match the legend, `.` means idle,
and `*` means multiple tasks shared the slot. Totals use actual durations.

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
