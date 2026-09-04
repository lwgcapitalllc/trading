#!/usr/bin/env python3
"""
compare_sessions.py — parity check: TradingView Pine export vs Python sessions engine.

Purpose
-------
Prove the Python engine in sessions/ produces the same session / kill-zone / NY-range clock output
as the source-of-truth blocks in mpc_jarvis.pine, on real candles. It feeds each bar's timestamp
(+ high/low) through SessionEngine and diffs the result against the px_* columns the Pine build in
indicators/engines/sessions_export.pine plotted, bar by bar.

What is compared (per bar, after --warmup)
------------------------------------------
  * Flags (0/1): px_in_asia / px_in_london / px_in_ny, px_in_kz1..3, px_in_nyr_window /
    px_in_nyr_extend, px_new_day, px_weekday.
  * Running session extremes (tolerance, na-aware): px_asia_high/low, px_london_high/low,
    px_ny_high/low — the persisted per-session high/low every bar (proves reset timing + expansion).
  * NY opening range (tolerance, na-aware): px_nyr_high / px_nyr_low.

Data lineup
-----------
Export ONE CSV from TradingView with indicators/engines/sessions_export.pine on the chart (chart menu →
Export chart data). Each row carries the candle's timestamp + OHLC (fed to Python) and the Pine
engine's px_* outputs (compared against). Both sides come from the same file, so there is no
data-source mismatch.

Use a 5-minute chart to validate ALL 18 fields. Everything except the NY opening range is
timeframe-agnostic, so a coarser export still checks 14 of them — pass --skip-nyr and the report
names what it did not cover. A coarser export is in fact the better test of the session WINDOWS,
because ~20k bars of 15m spans a DST changeover and 20k bars of 5m may not.

Warmup
------
The Pine `var` session extremes (asiaHigh, ...) and the NY range persist from before the export
window, so Pine may open already holding a value while Python starts cold (na). The clock flags do
not need warmup — they are pure functions of the bar's timestamp — but the extremes converge only
once each session has opened fresh inside the window. Use --warmup to skip the early bars; the tool
prints the last mismatching bar to help pick it. If the ONLY mismatches are on Sunday-evening /
weekend bars, Pine's session day default is weekday-only — see the NOTE in sessions/engine.py.

Usage
-----
    python3 sessions/tools/compare_sessions.py path/to/sessions_export.csv
    python3 sessions/tools/compare_sessions.py sessions_export.csv --warmup 300

Exit 0 if every compared field matches on every warm bar, 1 otherwise. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sessions import SessionEngine

# ── column groups ──
FLAG_FIELDS = [
    "px_in_asia", "px_in_london", "px_in_ny",
    "px_in_kz1", "px_in_kz2", "px_in_kz3",
    "px_in_nyr_window", "px_in_nyr_extend",
    "px_new_day", "px_weekday",
]
PRICE_FIELDS = [
    "px_asia_high", "px_asia_low",
    "px_london_high", "px_london_low",
    "px_ny_high", "px_ny_low",
    "px_nyr_high", "px_nyr_low",
]
ALL_FIELDS = FLAG_FIELDS + PRICE_FIELDS

# The NY opening range is the ONE part of this engine that is not timeframe-agnostic: Pine reads it
# off a 5-minute `request.security`, while Python only ever sees the bar it is fed. On a 5m export
# those are the same candle; on anything coarser they are not, and these four fields mismatch for a
# reason that is not a bug. --skip-nyr drops them, and the report then states they went unchecked.
NYR_FIELDS = ["px_in_nyr_window", "px_in_nyr_extend", "px_nyr_high", "px_nyr_low"]
_NYR_MAX_BAR_SECONDS = 300

# threshold below which a positive integer timestamp is seconds, not milliseconds
_SECONDS_CEILING = 10 ** 11


def _num(s):
    if s is None:
        return None
    s = s.strip()
    if s == "" or s.lower() in ("na", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_ms(raw):
    """Epoch milliseconds (UTC) from a TradingView time cell — accepts epoch seconds, epoch millis,
    or an ISO 8601 string."""
    raw = (raw or "").strip()
    if raw.lstrip("-").isdigit():
        v = int(raw)
        return v * 1000 if v < _SECONDS_CEILING else v
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _bar_seconds(rows, cols):
    """The export's bar interval, as the most common gap between consecutive timestamps.

    The MODE, not the mean or the min — a session break, a weekend or a data hole would drag an
    average anywhere, and a duplicate timestamp would drag the min to 0. Returns None if the times
    can't be read, in which case the caller simply doesn't warn.
    """
    tcol = cols.get("time")
    if not tcol or len(rows) < 3:
        return None
    gaps = {}
    prev = None
    for r in rows:
        try:
            t = _to_ms(r.get(tcol))
        except Exception:
            return None
        if prev is not None and t > prev:
            g = (t - prev) // 1000
            gaps[g] = gaps.get(g, 0) + 1
        prev = t
    return max(gaps, key=gaps.get) if gaps else None


def _resolve_columns(header):
    lower = {h.lower().strip(): h for h in header}

    def find(name, required=True):
        col = lower.get(name)
        if col is None and required:
            raise SystemExit(f"ERROR: column {name!r} not found in export. Header: {header}")
        return col

    cols = {"time": find("time"), "high": find("high"), "low": find("low")}
    for fld in ALL_FIELDS:
        cols[fld] = find(fld)
    return cols


def _load_rows(path, cols):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    tcol = cols["time"]
    keys = []
    for r in rows:
        try:
            keys.append(_to_ms(r.get(tcol)))
        except Exception:
            keys.append(None)
    if all(k is not None for k in keys) and keys != sorted(keys):
        rows = [r for _, r in sorted(zip(keys, rows), key=lambda p: p[0])]
    return rows


def _python_row(engine, ev):
    row = {
        "px_in_asia": 1 if ev.in_asia else 0,
        "px_in_london": 1 if ev.in_london else 0,
        "px_in_ny": 1 if ev.in_ny else 0,
        "px_in_kz1": 1 if ev.in_kz1 else 0,
        "px_in_kz2": 1 if ev.in_kz2 else 0,
        "px_in_kz3": 1 if ev.in_kz3 else 0,
        "px_in_nyr_window": 1 if ev.in_ny_range_window else 0,
        "px_in_nyr_extend": 1 if ev.in_ny_range_extend else 0,
        "px_new_day": 1 if ev.is_new_day else 0,
        "px_weekday": 1 if ev.is_weekday else 0,
        "px_nyr_high": ev.ny_range_high,
        "px_nyr_low": ev.ny_range_low,
    }
    for name, hi, lo in (("Asia", "px_asia_high", "px_asia_low"),
                         ("London", "px_london_high", "px_london_low"),
                         ("NY", "px_ny_high", "px_ny_low")):
        rng = engine.current_range(name)
        row[hi] = rng.high if rng else None
        row[lo] = rng.low if rng else None
    return row


def _values_match(field, py_val, pine_val, tol):
    if py_val is None and pine_val is None:
        return True
    if py_val is None or pine_val is None:
        return False
    if field in FLAG_FIELDS:
        return int(round(py_val)) == int(round(pine_val))
    return abs(py_val - pine_val) <= tol


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="CSV exported from TradingView with sessions_export.pine on the chart")
    ap.add_argument("--tolerance", type=float, default=1e-6, help="abs tolerance for price fields (default 1e-6)")
    ap.add_argument("--max-report", type=int, default=30, help="how many mismatching bars to print")
    ap.add_argument("--warmup", type=int, default=0, help="skip the first N bars in the report (still fed to the engine)")
    ap.add_argument("--skip-nyr", action="store_true",
                    help="don't compare the 4 NY-opening-range fields (they need a <=5m export; see NYR_FIELDS)")
    args = ap.parse_args(argv)

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"ERROR: file not found: {path}")

    with open(path, newline="") as f:
        header = next(csv.reader(f))
    cols = _resolve_columns(header)
    rows = _load_rows(path, cols)

    bar_seconds = _bar_seconds(rows, cols)
    fields = [f for f in ALL_FIELDS if f not in NYR_FIELDS] if args.skip_nyr else list(ALL_FIELDS)
    if not args.skip_nyr and bar_seconds is not None and bar_seconds > _NYR_MAX_BAR_SECONDS:
        print(f"WARNING: this export is on a {bar_seconds // 60}-minute chart. The NY opening range is a "
              f"<=5m feature (Pine reads a 5m security, Python sees only the bar it is fed), so "
              f"{', '.join(NYR_FIELDS)} will mismatch for a reason that is not a bug.\n"
              f"         Re-run with --skip-nyr to check the other {len(ALL_FIELDS) - len(NYR_FIELDS)} "
              f"fields, and validate the range itself on a separate 5m export.\n")

    engine = SessionEngine()

    total = 0
    per_field_mismatch = {fld: 0 for fld in fields}
    detailed = []
    last_mismatch_bar = None

    for i, row in enumerate(rows):
        h = _num(row[cols["high"]])
        l = _num(row[cols["low"]])
        if None in (h, l):
            continue
        ts_ms = _to_ms(row[cols["time"]])

        ev = engine.update(i, ts_ms, h, l)
        py = _python_row(engine, ev)
        total += 1

        if i < args.warmup:
            continue

        bar_mismatches = []
        for fld in fields:
            pine_val = _num(row[cols[fld]])
            if not _values_match(fld, py[fld], pine_val, args.tolerance):
                per_field_mismatch[fld] += 1
                bar_mismatches.append((fld, py[fld], pine_val))
        if bar_mismatches:
            last_mismatch_bar = i
            if len(detailed) < args.max_report:
                detailed.append((i, row[cols["time"]], bar_mismatches))

    skipped = "" if not args.skip_nyr else (
        f"\nNOT CHECKED: {', '.join(NYR_FIELDS)} — the NY opening range is a <=5m feature and this run "
        f"skipped it. It is NOT covered by this result; validate it on a 5m export.")

    mismatched_fields = {f: n for f, n in per_field_mismatch.items() if n}
    print(f"Compared {total} bars ({args.warmup} warmup skipped) across {len(fields)} fields.")
    if not mismatched_fields:
        print("PARITY OK — every field matches on every warm bar." + skipped)
        return 0

    print(f"MISMATCH — {sum(mismatched_fields.values())} field-mismatches; last at bar {last_mismatch_bar}.")
    print("Per-field mismatch counts:")
    for fld, n in sorted(mismatched_fields.items(), key=lambda p: -p[1]):
        print(f"  {fld}: {n}")
    print(f"\nFirst {len(detailed)} mismatching bar(s) (row index, time, field: python vs pine):")
    for idx, t, bar_fields in detailed:
        for fld, pv, xv in bar_fields:
            print(f"  bar {idx} @ {t}  {fld}: {pv} vs {xv}")
    if set(mismatched_fields) <= set(NYR_FIELDS) and bar_seconds is not None and bar_seconds > _NYR_MAX_BAR_SECONDS:
        print(f"\nEvery mismatching field is a NY-opening-range field on a {bar_seconds // 60}-minute "
              f"export — expected, not a bug. Re-run with --skip-nyr and validate the range on 5m.")
    print(skipped)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
