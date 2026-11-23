#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
EXTENSIONS_DIR=${TIMEWARRIOR_EXTENSIONS_DIR:-"$HOME/.timewarrior/extensions"}

mkdir -p "$EXTENSIONS_DIR"
install -m 755 "$SCRIPT_DIR/pie_chart" "$EXTENSIONS_DIR/pie_chart"
install -m 755 "$SCRIPT_DIR/calendar_grid" "$EXTENSIONS_DIR/calendar_grid"
install -m 755 "$SCRIPT_DIR/gantt_chart" "$EXTENSIONS_DIR/gantt_chart"
install -m 644 "$SCRIPT_DIR/gantt_report.py" "$EXTENSIONS_DIR/gantt_report.py"
install -m 644 "$SCRIPT_DIR/timew_report.py" "$EXTENSIONS_DIR/timew_report.py"

printf 'Installed pie_chart, calendar_grid and gantt_chart to %s\n' "$EXTENSIONS_DIR"
