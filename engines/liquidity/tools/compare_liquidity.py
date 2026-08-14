#!/usr/bin/env python3
"""
compare_liquidity.py — parity check: TradingView Pine export vs Python liquidity engine.

Purpose
-------
Prove the Python engine in liquidity/ produces the same liquidity levels as the source-of-truth
blocks in mpc_assistant.pine, on real candles. It feeds each bar (timestamp + OHLC) through
LiquidityEngine and diffs the current active-level prices + mitigation flags against the px_* columns
the Pine build in indicators/engines/liquidity_export.pine plotted, bar by bar.

What is compared (per bar, after --warmup)
------------------------------------------
  * Level prices (tolerance, na-aware): px_pdh/pdl, px_pwh/pwl, px_pwc, px_h4h/h4l,
    px_asia_h/l, px_london_h/l, px_ny_h/l — the active level's frozen price (na until it forms).
    (The MONTHLY level PMH/PML was removed from the source and the engine on 2026-07-09.)
  * Mitigation flags (0/1): the *_mit column for each of the above (PWC has none — never mitigated).
  * Boundary rolls (0/1): px_day_roll / px_week_roll / px_h4_roll — where each HTF period turns over.
    These are the CALIBRATION signal: if they mismatch, --htf-tz / --htf-rollover do not match this
    chart's "D"/"W"/"240" session boundary (see Calibration below).

NON-REPAINTING (Aaron's decision, 2026-07-05)
---------------------------------------------
Both sides use the PREVIOUS completed period only — never a future-peeking `request.security(high)`.
The export mirrors this with `high[1]/low[1]/close[1]`; the engine reconstructs it from the stream.
So the level values here are the real, live, non-repainting ones a bot would actually trade.

Calibration
-----------
TradingView's daily/weekly/H4 bars align to the instrument's exchange session, which is broker
dependent. For XAUUSD that is usually a 17:00-New-York roll, i.e.
`--htf-tz America/New_York --htf-rollover 17`. If px_*_roll or the level prices mismatch on otherwise
warm bars, sweep --htf-rollover (and/or --htf-tz) until px_day_roll matches, then the prices follow.
The winning pair is the LiquidityEngine default; bake it in once confirmed. Run with
hide_mitigated_on_new_day=False (the export drops that drawing-only tidy; it is unit-tested).

Data lineup
-----------
Export ONE CSV from TradingView with indicators/engines/liquidity_export.pine on the chart (chart menu →
Export chart data), on the same timeframe you pass here (e.g. VANTAGE_XAUUSD, 5m or 15m). Each row
carries the candle's timestamp + OHLC (fed to Python) and the Pine engine's px_* outputs (compared
against). Both sides come from the same file, so there is no data-source mismatch.

Warmup
------
A level is na until its first full period completes inside the export window, and if the chart had
history before the window Pine's HTF security may already hold a value while Python starts cold. Use
--warmup to skip the early bars; the tool prints the last mismatching bar to help pick it.

Usage
-----
    python3 liquidity/tools/compare_liquidity.py path/to/liquidity_export.csv
    python3 liquidity/tools/compare_liquidity.py liquidity_export.csv --htf-rollover 17 --warmup 400

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

from liquidity import LiquidityEngine
from liquidity.engine import _key_day, _key_h4, _key_week
from sessions.engine import _resolve_tz

# px_<col> : level name in LiquidityLevel.name  (price columns)
# (The MONTHLY level PMH/PML was removed from the source and the engine on 2026-07-09.)
PRICE_BY_NAME = {
    "px_pdh": "PDH",
    "px_pdl": "PDL",
    "px_pwh": "PWH",
    "px_pwl": "PWL",
    "px_pwc": "PWC",
    "px_h4h": "H4 H",
    "px_h4l": "H4 L",
    "px_asia_h": "Asia H",
    "px_asia_l": "Asia L",
    "px_london_h": "London H",
    "px_london_l": "London L",
    "px_ny_h": "NY H",
    "px_ny_l": "NY L",
}
# px_<col> : level name  (mitigation flag columns — PWC has none)
MIT_BY_NAME = {
    "px_pdh_mit": "PDH",
    "px_pdl_mit": "PDL",
    "px_pwh_mit": "PWH",
    "px_pwl_mit": "PWL",
    "px_h4h_mit": "H4 H",
    "px_h4l_mit": "H4 L",
    "px_asia_h_mit": "Asia H",
    "px_asia_l_mit": "Asia L",
    "px_london_h_mit": "London H",
    "px_london_l_mit": "London L",
    "px_ny_h_mit": "NY H",
    "px_ny_l_mit": "NY L",
}
ROLL_FIELDS = ["px_day_roll", "px_week_roll", "px_h4_roll"]

PRICE_FIELDS = list(PRICE_BY_NAME)
MIT_FIELDS = list(MIT_BY_NAME)
ALL_FIELDS = PRICE_FIELDS + MIT_FIELDS + ROLL_FIELDS

_SECONDS_CEILING = 10**11


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
    raw = (raw or "").strip()
    if raw.lstrip("-").isdigit():
        v = int(raw)
        return v * 1000 if v < _SECONDS_CEILING else v
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _resolve_columns(header, roll_optional=True):
    lower = {h.lower().strip(): h for h in header}

    def find(name, required=True):
        col = lower.get(name)
        if col is None and required:
            raise SystemExit(f"ERROR: column {name!r} not found in export. Header: {header}")
        return col

    cols = {
        "time": find("time"),
        "open": find("open", False),
        "high": find("high"),
        "low": find("low"),
        "close": find("close"),
    }
    for fld in PRICE_FIELDS + MIT_FIELDS:
        cols[fld] = find(fld)
    for fld in ROLL_FIELDS:  # roll pulses are a calibration aid — optional
        cols[fld] = find(fld, not roll_optional)
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


class _RollWatcher:
    """Mirror the engine's period-key logic so the tool can emit its own day/week/month/H4 roll
    pulses for the calibration comparison — independent of which features are enabled."""

    def __init__(self, htf_tz, rollover):
        from datetime import timedelta

        self._tz = _resolve_tz(htf_tz)
        self._shift = timedelta(hours=(24 - (rollover % 24)) % 24)
        self._keys = {"day": None, "week": None, "h4": None}
        self._fns = {"day": _key_day, "week": _key_week, "h4": _key_h4}

    def pulses(self, ts_ms):
        local = (
            datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).astimezone(self._tz)
            + self._shift
        )
        out = {}
        for k, fn in self._fns.items():
            key = fn(local)
            out[k] = 1 if (self._keys[k] is not None and key != self._keys[k]) else 0
            self._keys[k] = key
        return {"px_day_roll": out["day"], "px_week_roll": out["week"], "px_h4_roll": out["h4"]}


def _python_row(active, roll_pulses):
    by_name = {lvl.name: lvl for lvl in active}
    row = {}
    for fld, name in PRICE_BY_NAME.items():
        lvl = by_name.get(name)
        row[fld] = lvl.price if lvl else None
    for fld, name in MIT_BY_NAME.items():
        lvl = by_name.get(name)
        row[fld] = (1 if lvl.mitigated else 0) if lvl else None
    row.update(roll_pulses)
    return row


def _values_match(field, py_val, pine_val, tol):
    if py_val is None and pine_val is None:
        return True
    if py_val is None or pine_val is None:
        return False
    if field in PRICE_FIELDS:
        return abs(py_val - pine_val) <= tol
    return int(round(py_val)) == int(round(pine_val))  # mit + roll flags


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "csv", help="CSV exported from TradingView with liquidity_export.pine on the chart"
    )
    ap.add_argument(
        "--htf-tz",
        default="America/New_York",
        help="timezone the day/week/month/H4 boundary is cut in (default America/New_York)",
    )
    ap.add_argument(
        "--htf-rollover",
        type=int,
        default=18,
        help="local hour the HTF session OPENS (XAUUSD = 18:00 NY, the validated default)",
    )
    ap.add_argument(
        "--tolerance",
        type=float,
        default=1e-6,
        help="abs tolerance for price fields (default 1e-6)",
    )
    ap.add_argument("--max-report", type=int, default=30, help="how many mismatching bars to print")
    ap.add_argument(
        "--warmup",
        type=int,
        default=0,
        help="skip the first N bars in the report (still fed to the engine)",
    )
    args = ap.parse_args(argv)

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"ERROR: file not found: {path}")

    with open(path, newline="") as f:
        header = next(csv.reader(f))
    cols = _resolve_columns(header)
    rows = _load_rows(path, cols)

    engine = LiquidityEngine(
        htf_timezone=args.htf_tz,
        htf_rollover_hours=args.htf_rollover,
        hide_mitigated_on_new_day=False,
    )
    watcher = _RollWatcher(args.htf_tz, args.htf_rollover)
    compared_fields = [f for f in ALL_FIELDS if cols.get(f) is not None]

    total = 0
    per_field_mismatch = {fld: 0 for fld in compared_fields}
    detailed = []
    last_mismatch_bar = None

    for i, row in enumerate(rows):
        h = _num(row[cols["high"]])
        l = _num(row[cols["low"]])
        c = _num(row[cols["close"]])
        if None in (h, l, c):
            continue
        ts_ms = _to_ms(row[cols["time"]])

        ev = engine.update(i, ts_ms, h, l, c)
        py = _python_row(ev.active, watcher.pulses(ts_ms))
        total += 1

        if i < args.warmup:
            continue

        bar_mismatches = []
        for fld in compared_fields:
            pine_val = _num(row[cols[fld]])
            if not _values_match(fld, py[fld], pine_val, args.tolerance):
                per_field_mismatch[fld] += 1
                bar_mismatches.append((fld, py[fld], pine_val))
        if bar_mismatches:
            last_mismatch_bar = i
            if len(detailed) < args.max_report:
                detailed.append((i, row[cols["time"]], bar_mismatches))

    mismatched_fields = {f: n for f, n in per_field_mismatch.items() if n}
    print(
        f"Compared {total} bars ({args.warmup} warmup skipped) across {len(compared_fields)} fields "
        f"[htf-tz={args.htf_tz} rollover={args.htf_rollover}h]."
    )
    if not mismatched_fields:
        print("PARITY OK — every field matches on every warm bar.")
        return 0

    print(
        f"MISMATCH — {sum(mismatched_fields.values())} field-mismatches; last at bar {last_mismatch_bar}."
    )
    print("Per-field mismatch counts:")
    for fld, n in sorted(mismatched_fields.items(), key=lambda p: -p[1]):
        print(f"  {fld}: {n}")
    print(f"\nFirst {len(detailed)} mismatching bar(s) (row index, time, field: python vs pine):")
    for idx, t, fields in detailed:
        for fld, pv, xv in fields:
            print(f"  bar {idx} @ {t}  {fld}: {pv} vs {xv}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
