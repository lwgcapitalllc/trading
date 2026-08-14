#!/usr/bin/env python3
"""
compare_vwap.py — parity check: TradingView Pine export vs Python VWAP engine.

Purpose
-------
Prove the Python engine in vwap/ produces the same session VWAP as the source-of-truth line in
mpc_assistant.pine (`vwapValue = ta.vwap(hlc3)`), on real candles. It feeds each bar
(timestamp + high/low/close + volume) through VwapEngine and diffs the running VWAP value + the
trading-day anchor pulse against the px_* columns the Pine build in indicators/engines/vwap_export.pine
plotted, bar by bar.

What is compared (per bar, after --warmup)
------------------------------------------
  * px_vwap        — the session VWAP value (tolerance, na-aware). This is the Pine-validated output.
  * px_vwap_anchor — the trading-day re-anchor pulse (0/1). This is the CALIBRATION signal: if it
    mismatches, --htf-tz / --htf-rollover do not match this chart's trading-day ("D") boundary.

Volume
------
The engine is FED the volume from the export's `px_volume` column (falling back to a native `volume`
column), so both sides use the identical volume series — no data-source mismatch. For XAUUSD this is
tick volume, which is exactly what Pine's ta.vwap reads.

Calibration
-----------
ta.vwap's default anchor is the start of the exchange trading day — the same "D" boundary the
liquidity engine calibrates. For XAUUSD that is 18:00 New York, i.e. the defaults
`--htf-tz America/New_York --htf-rollover 18`. If px_vwap_anchor mismatches, sweep --htf-rollover
(and/or --htf-tz) until it matches; the VWAP value follows.

Warmup
------
ta.vwap accumulates from the session anchor. If the chart carried history before the export window,
Pine's first (partial) session already holds pre-window volume while Python starts cold, so the
value diverges until the first full in-window trading-day anchor. Use --warmup to skip those early
bars; the tool prints the last mismatching bar to help pick it. The anchor pulse needs no warm-up
(it is a pure function of the timestamp).

Usage
-----
    python3 engines/vwap/tools/compare_vwap.py path/to/vwap_export.csv
    python3 engines/vwap/tools/compare_vwap.py vwap_export.csv --htf-rollover 18 --warmup 300

Exit 0 if every compared field matches on every warm bar, 1 otherwise. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from vwap import VwapEngine

PRICE_FIELDS = ["px_vwap"]
FLAG_FIELDS = ["px_vwap_anchor"]
ALL_FIELDS = PRICE_FIELDS + FLAG_FIELDS

# Relative tolerance for the cumulative VWAP value — 1 part per million. See _values_match: a running
# volume-weighted sum drifts at float-rounding level between Python and Pine, so the check is
# relative, not the exact-price match the frozen-level engines can use.
_REL_TOL = 1e-6

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
    raw = (raw or "").strip()
    if raw.lstrip("-").isdigit():
        v = int(raw)
        return v * 1000 if v < _SECONDS_CEILING else v
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _resolve_columns(header):
    lower = {h.lower().strip(): h for h in header}

    def find(name, required=True):
        col = lower.get(name)
        if col is None and required:
            raise SystemExit(f"ERROR: column {name!r} not found in export. Header: {header}")
        return col

    cols = {"time": find("time"),
            "high": find("high"), "low": find("low"), "close": find("close")}
    # volume input: prefer the explicit px_volume column, fall back to a native volume column
    cols["volume"] = find("px_volume", False) or find("volume", False)
    if cols["volume"] is None:
        raise SystemExit("ERROR: no volume column ('px_volume' or 'volume') found in export. "
                         f"Header: {header}")
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


def _values_match(field, py_val, pine_val, tol):
    if py_val is None and pine_val is None:
        return True
    if py_val is None or pine_val is None:
        return False
    if field in PRICE_FIELDS:
        # The VWAP is a CUMULATIVE volume-weighted sum over the whole session — thousands of bars by
        # late afternoon. Python's float64 and Pine's own accumulation drift apart at the float-
        # rounding level (~1 part per million: ~1e-4 on a ~4000 gold price, 100x under a 1-cent tick).
        # So use a RELATIVE tolerance, not the exact-price tolerance the frozen-level engines use.
        return math.isclose(py_val, pine_val, rel_tol=_REL_TOL, abs_tol=tol)
    return int(round(py_val)) == int(round(pine_val))    # flag fields (anchor pulse)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="CSV exported from TradingView with vwap_export.pine on the chart")
    ap.add_argument("--htf-tz", default="America/New_York", help="timezone the trading-day anchor is cut in (default America/New_York)")
    ap.add_argument("--htf-rollover", type=int, default=18, help="local hour the trading day OPENS (XAUUSD = 18:00 NY, the validated default)")
    ap.add_argument("--tolerance", type=float, default=1e-4, help="ABSOLUTE floor for the VWAP price; the primary check is relative (1e-6). Default 1e-4")
    ap.add_argument("--max-report", type=int, default=30, help="how many mismatching bars to print")
    ap.add_argument("--warmup", type=int, default=0, help="skip the first N bars in the report (still fed to the engine)")
    args = ap.parse_args(argv)

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"ERROR: file not found: {path}")

    with open(path, newline="") as f:
        header = next(csv.reader(f))
    cols = _resolve_columns(header)
    rows = _load_rows(path, cols)

    engine = VwapEngine(htf_timezone=args.htf_tz, htf_rollover_hours=args.htf_rollover)
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
        vol = _num(row[cols["volume"]])
        ts_ms = _to_ms(row[cols["time"]])

        ev = engine.update(i, ts_ms, h, l, c, vol)
        py = {"px_vwap": ev.value, "px_vwap_anchor": 1 if ev.anchored else 0}
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
    print(f"Compared {total} bars ({args.warmup} warmup skipped) across {len(compared_fields)} fields "
          f"[htf-tz={args.htf_tz} rollover={args.htf_rollover}h].")
    if not mismatched_fields:
        print("PARITY OK — every field matches on every warm bar.")
        return 0

    print(f"MISMATCH — {sum(mismatched_fields.values())} field-mismatches; last at bar {last_mismatch_bar}.")
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
