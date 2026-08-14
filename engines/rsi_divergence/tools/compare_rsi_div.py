#!/usr/bin/env python3
"""
compare_rsi_div.py — parity check: TradingView Pine export vs Python RSI-divergence engine.

Purpose
-------
Prove the Python engine in rsi_divergence/ produces the same RSI, RSI pivots and regular-divergence
signals as the source-of-truth "RSI DIVERGENCE" block in mpc_assistant.pine, on real candles. It runs
RsiDivergenceEngine on the same candles the Pine build saw and diffs its output against the px_div_*
columns the Pine build plotted.

What is compared (per bar, after --warmup)
------------------------------------------
  * px_div_rsi   against ev.rsi                      (the Wilder RSI value — tolerance-compared)
  * px_div_pl    against ev.pivot_low_rsi            (RSI pivot low confirmed this bar — na-aware)
  * px_div_ph    against ev.pivot_high_rsi           (RSI pivot high confirmed this bar — na-aware)
  * px_div_bull  against 1/0: a BULLISH divergence confirmed this bar (pulse)
  * px_div_bear  against 1/0: a BEARISH divergence confirmed this bar (pulse)
  * px_div_bull_active / px_div_bear_active against ev.bull_active / ev.bear_active (0/1 state)
  * px_div_bull_age / px_div_bear_age against (i - last_bull|bear_bar) — the age of the most recent
    divergence's pivot. Ages are index DIFFERENCES, so they are invariant to Pine's absolute
    bar_index vs Python's 0-based row index; na when no divergence has fired yet.

Data lineup
-----------
Export ONE CSV from TradingView with indicators/engines/rsi_div_export.pine on the chart (chart menu → Export
chart data), with showDiv ON. Each row carries the candle (fed to Python) and the Pine divergence
engine's outputs. Both sides come from the same file, so there is no data-source mismatch. Set
--rsi-len / --pivot-len / --oversold / --overbought / --valid-bars to match the Pine inputs (defaults
14 / 5 / 25 / 75 / 100 = the mpc defaults).

Warmup
------
The Pine export usually begins at a non-zero bar_index (TradingView had history before the export
window), so its RSI is already warm and it may already hold prior RSI pivots / a divergence off-window.
The cold-started Python engine (RSI IIR seeds from row 0; no prior pivots) converges as its Wilder RMA
settles and it establishes its own in-window pivots. Use --warmup to skip those early bars; the tool
prints the last mismatching bar to help you pick it.

Usage
-----
    python3 rsi_divergence/tools/compare_rsi_div.py path/to/rsi_div_export.csv
    python3 rsi_divergence/tools/compare_rsi_div.py rsi_div_export.csv --warmup 150

Exit 0 if every compared field matches on every bar past warmup, 1 otherwise. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from rsi_divergence import RsiDivergenceEngine

# ── column groups ──
RSI_FIELDS = ["px_div_rsi", "px_div_pl", "px_div_ph"]                 # RSI-scale, tolerance, na-aware
PULSE_FIELDS = ["px_div_bull", "px_div_bear"]                         # 0/1 this-bar pulses
FLAG_FIELDS = ["px_div_bull_active", "px_div_bear_active"]            # 0/1 live-confluence state
AGE_FIELDS = ["px_div_bull_age", "px_div_bear_age"]                   # index differences, na-aware
INT_FIELDS = PULSE_FIELDS + FLAG_FIELDS + AGE_FIELDS

ALL_FIELDS = RSI_FIELDS + INT_FIELDS


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


def _resolve_columns(header):
    """Match logical names to CSV header strings (exact, then endswith, then contains)."""
    norm = {h.strip().lower(): h for h in header}

    def find(name, required=True):
        key = name.lower()
        if key in norm:
            return norm[key]
        for low, orig in norm.items():
            if low.endswith(key):
                return orig
        for low, orig in norm.items():
            if key in low:
                return orig
        if required:
            raise SystemExit(
                f"ERROR: column '{name}' not found in CSV header.\n"
                f"Header was: {header}\n"
                f"Make sure indicators/engines/rsi_div_export.pine is the build on the chart and that you "
                f"exported via 'Export chart data'."
            )
        return None

    cols = {k: find(k) for k in ("open", "high", "low", "close")}
    cols["time"] = find("time", required=False)
    for f in ALL_FIELDS:
        cols[f] = find(f)
    return cols


def _python_row(ev, i, state):
    """Map the Python divergence events to each px_div_* column value.

    `state` carries last_bull_bar / last_bear_bar (updated from ev.detected) so the ages mirror the
    Pine lastBull|BearDivBar exactly.
    """
    bull_pulse = any(d.is_bullish for d in ev.detected)
    bear_pulse = any(not d.is_bullish for d in ev.detected)
    for d in ev.detected:
        if d.is_bullish:
            state["last_bull_bar"] = d.pivot_bar
        else:
            state["last_bear_bar"] = d.pivot_bar

    row = {
        "px_div_rsi": ev.rsi,
        "px_div_pl": ev.pivot_low_rsi,
        "px_div_ph": ev.pivot_high_rsi,
        "px_div_bull": 1.0 if bull_pulse else 0.0,
        "px_div_bear": 1.0 if bear_pulse else 0.0,
        "px_div_bull_active": 1.0 if ev.bull_active else 0.0,
        "px_div_bear_active": 1.0 if ev.bear_active else 0.0,
        "px_div_bull_age": None if state["last_bull_bar"] is None else float(i - state["last_bull_bar"]),
        "px_div_bear_age": None if state["last_bear_bar"] is None else float(i - state["last_bear_bar"]),
    }
    return row


def _values_match(field, py_val, pine_val, tol):
    if field in RSI_FIELDS:
        if py_val is None and pine_val is None:
            return True
        if py_val is None or pine_val is None:
            return False
        return abs(py_val - pine_val) <= tol
    if field in AGE_FIELDS:
        # na-aware integer difference: both empty -> match; one empty -> mismatch.
        if py_val is None and pine_val is None:
            return True
        if py_val is None or pine_val is None:
            return False
        return int(round(py_val)) == int(round(pine_val))
    # pulses / flags: a missing Pine cell is 0.
    if pine_val is None:
        pine_val = 0.0
    if py_val is None:
        py_val = 0.0
    return int(round(py_val)) == int(round(pine_val))


def _load_rows(path, cols):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    tcol = cols.get("time")
    if tcol:
        def tkey(r):
            raw = (r.get(tcol) or "").strip()
            if raw.isdigit():
                return int(raw)
            try:
                from datetime import datetime
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
            except Exception:
                return None
        keys = [tkey(r) for r in rows]
        if all(k is not None for k in keys) and keys != sorted(keys):
            rows = [r for _, r in sorted(zip(keys, rows), key=lambda p: p[0])]
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="CSV exported from TradingView with rsi_div_export.pine on the chart")
    ap.add_argument("--rsi-len", type=int, default=14, help="must match the Pine divRsiLen (default 14)")
    ap.add_argument("--pivot-len", type=int, default=5, help="must match the Pine divPivotLen (default 5)")
    ap.add_argument("--oversold", type=float, default=25.0, help="must match the Pine divOS (default 25)")
    ap.add_argument("--overbought", type=float, default=75.0, help="must match the Pine divOB (default 75)")
    ap.add_argument("--valid-bars", type=int, default=100, help="must match the Pine divValidBars (default 100)")
    ap.add_argument("--tolerance", type=float, default=1e-2, help="abs tolerance for RSI-value fields (default 1e-2, covers CSV rounding)")
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

    div = RsiDivergenceEngine(rsi_len=args.rsi_len, pivot_len=args.pivot_len,
                              oversold=args.oversold, overbought=args.overbought,
                              valid_bars=args.valid_bars)

    total = 0
    per_field_mismatch = {fld: 0 for fld in ALL_FIELDS}
    detailed = []
    last_mismatch_bar = None
    state = {"last_bull_bar": None, "last_bear_bar": None}

    for i, row in enumerate(rows):
        o = _num(row[cols["open"]])
        h = _num(row[cols["high"]])
        l = _num(row[cols["low"]])
        c = _num(row[cols["close"]])
        if None in (h, l, c):
            continue

        ev = div.update(i, h, l, c)
        py = _python_row(ev, i, state)
        total += 1

        if i < args.warmup:
            continue

        bar_mismatches = []
        for fld in ALL_FIELDS:
            pine_val = _num(row[cols[fld]])
            if not _values_match(fld, py[fld], pine_val, args.tolerance):
                per_field_mismatch[fld] += 1
                bar_mismatches.append((fld, py[fld], pine_val))

        if bar_mismatches:
            last_mismatch_bar = i
            if len(detailed) < args.max_report:
                tval = row[cols["time"]] if cols.get("time") else ""
                detailed.append((i, tval, bar_mismatches))

    # ── Report ──
    print(f"\nCompared {total} bars from {path.name}  "
          f"(rsi_len={args.rsi_len}, pivot_len={args.pivot_len}, os={args.oversold}, ob={args.overbought}, "
          f"valid_bars={args.valid_bars}, tol={args.tolerance})")
    print("-" * 72)
    if not any(per_field_mismatch.values()):
        print("✓ RSI-DIV PARITY: every compared field matched on every bar. Python engine == Pine source.")
        return 0

    print("MISMATCHES BY FIELD:")
    for fld in ALL_FIELDS:
        n = per_field_mismatch[fld]
        if n:
            print(f"  {fld:<22} {n} bar(s)")
    print("-" * 72)
    print(f"Last mismatching bar: {last_mismatch_bar}  "
          f"(if all mismatches are early, re-run with --warmup {(last_mismatch_bar or 0) + 1})")
    print(f"First {len(detailed)} mismatching bar(s) (row index, time, field: python vs pine):")
    for idx, tval, ms in detailed:
        print(f"  bar {idx}  {tval}")
        for fld, pv, pinev in ms:
            print(f"      {fld:<22} python={pv!r:<14} pine={pinev!r}")
    print("-" * 72)
    print("Tip: mismatches confined to early bars = warmup (Pine's RSI was already smoothed and it "
          "may hold an off-window pivot/divergence; the cold-started Python engine converges once its "
          "Wilder RMA settles and it establishes its own in-window pivots). Persistent mismatches "
          "after a clean run = a real logic gap to fix against mpc_assistant.pine.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
