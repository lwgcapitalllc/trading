#!/usr/bin/env python3
"""
compare_ob.py — parity check: TradingView Pine export vs Python order-block engine.

Purpose
-------
Prove the Python engine in order_blocks/ produces the same order blocks as the source-of-truth OB
blocks in mpc_assistant.pine, on real candles. It runs the REAL pipeline — market_structure's
StructureEngine feeds a StructureSnapshot into OrderBlockEngine — on the same candles the Pine
build saw, and diffs their output against the px_ob_* columns the Pine build plotted.

What is compared (per bar, after --warmup)
------------------------------------------
  * The active OB arrays, slot by slot (slot 1 = oldest): px_ob_bull_top_1..6 / px_ob_bull_bot_1..6
    and the bear mirror, against active_bull[k]/active_bear[k].top/.bottom. This is the PRIMARY
    signal — matching the ordered arrays every bar proves creation, mitigation AND FIFO eviction
    all at once.
  * px_ob_bull_count / px_ob_bear_count against len(active_bull) / len(active_bear).
  * px_ob_bull_created / px_ob_bear_created / px_ob_bull_mit / px_ob_bear_mit against the count of
    created / mitigated OBs this bar (secondary localisers).
  * px_i_break_origin_ago against (bar_index - int_break_origin_loc) on internal-break bars — the
    one internal-structure field that had no prior export column.

Data lineup
-----------
Export ONE CSV from TradingView with indicators/ob_export.pine on the chart (chart menu → Export
chart data). Each row carries the candle (fed to Python) and the Pine OB engine's outputs. Both
sides come from the same file, so there is no data-source mismatch.

Warmup
------
The Pine export usually begins at a non-zero bar_index (TradingView had history before the export
window), so the Pine engine is already "warm" while Python starts cold. Structure must converge and
the first in-window break must form before the OBs can match. Use --warmup to skip those early
bars; the tool prints the last mismatching bar to help you pick it.

Usage
-----
    python3 order_blocks/tools/compare_ob.py path/to/ob_export.csv
    python3 order_blocks/tools/compare_ob.py ob_export.csv --major-length 15 --warmup 300

Exit 0 if every compared field matches on every bar, 1 otherwise. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from market_structure import Bar, StructureEngine
from order_blocks import OrderBlockEngine, StructureSnapshot

_MAX_SLOTS = 6  # mpc maxActiveOB default; ob_export.pine plots 6 slots per direction

# ── column groups ──
BULL_TOP = [f"px_ob_bull_top_{k}" for k in range(1, _MAX_SLOTS + 1)]
BULL_BOT = [f"px_ob_bull_bot_{k}" for k in range(1, _MAX_SLOTS + 1)]
BEAR_TOP = [f"px_ob_bear_top_{k}" for k in range(1, _MAX_SLOTS + 1)]
BEAR_BOT = [f"px_ob_bear_bot_{k}" for k in range(1, _MAX_SLOTS + 1)]
PRICE_FIELDS = BULL_TOP + BULL_BOT + BEAR_TOP + BEAR_BOT      # tolerance-compared, na-aware

COUNT_FIELDS = ["px_ob_bull_count", "px_ob_bear_count"]
PULSE_FIELDS = ["px_ob_bull_created", "px_ob_bear_created", "px_ob_bull_mit", "px_ob_bear_mit"]
ORIGIN_FIELD = "px_i_break_origin_ago"
INT_FIELDS = COUNT_FIELDS + PULSE_FIELDS + [ORIGIN_FIELD]     # integer-compared, na-aware

ALL_FIELDS = PRICE_FIELDS + INT_FIELDS


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
                f"Make sure indicators/ob_export.pine is the build on the chart and that you "
                f"exported via 'Export chart data'."
            )
        return None

    cols = {k: find(k) for k in ("open", "high", "low", "close")}
    cols["time"] = find("time", required=False)
    for f in ALL_FIELDS:
        cols[f] = find(f)
    return cols


def _python_row(i, oe, snap):
    """Map the Python OB events to each px_ob_* column value for bar index i."""
    row = {}
    for slot, (tf, bf) in enumerate(zip(BULL_TOP, BULL_BOT)):
        ob = oe.active_bull[slot] if slot < len(oe.active_bull) else None
        row[tf] = ob.top if ob else None
        row[bf] = ob.bottom if ob else None
    for slot, (tf, bf) in enumerate(zip(BEAR_TOP, BEAR_BOT)):
        ob = oe.active_bear[slot] if slot < len(oe.active_bear) else None
        row[tf] = ob.top if ob else None
        row[bf] = ob.bottom if ob else None

    row["px_ob_bull_count"] = float(len(oe.active_bull))
    row["px_ob_bear_count"] = float(len(oe.active_bear))
    row["px_ob_bull_created"] = float(sum(1 for o in oe.created if o.is_bullish))
    row["px_ob_bear_created"] = float(sum(1 for o in oe.created if not o.is_bullish))
    row["px_ob_bull_mit"] = float(sum(1 for o in oe.mitigated if o.is_bullish))
    row["px_ob_bear_mit"] = float(sum(1 for o in oe.mitigated if not o.is_bullish))
    # Pine emits (bar_index - int_break_origin_loc) only when an internal break set the origin.
    row[ORIGIN_FIELD] = float(i - snap.int_break_origin_loc) if snap.int_break_origin_loc is not None else None
    return row


def _values_match(field, py_val, pine_val, tol):
    if field in PRICE_FIELDS:
        if py_val is None and pine_val is None:
            return True
        if py_val is None or pine_val is None:
            return False
        return abs(py_val - pine_val) <= tol
    # integer fields (counts / pulses / origin). A missing Pine cell for a pulse/count is 0; for
    # the origin it is a genuine "no internal break this bar" → Python is also None there.
    if field == ORIGIN_FIELD:
        if py_val is None and pine_val is None:
            return True
        if py_val is None or pine_val is None:
            return False
        return int(round(py_val)) == int(round(pine_val))
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
    ap.add_argument("csv", help="CSV exported from TradingView with ob_export.pine on the chart")
    ap.add_argument("--major-length", type=int, default=15, help="must match the Pine build (default 15)")
    ap.add_argument("--tolerance", type=float, default=1e-6, help="abs tolerance for price fields (default 1e-6)")
    ap.add_argument("--max-report", type=int, default=30, help="how many mismatching bars to print")
    ap.add_argument("--warmup", type=int, default=0, help="skip the first N bars in the report (still fed to the engines)")
    args = ap.parse_args(argv)

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"ERROR: file not found: {path}")

    with open(path, newline="") as f:
        header = next(csv.reader(f))
    cols = _resolve_columns(header)
    rows = _load_rows(path, cols)

    engine = StructureEngine(major_length=args.major_length)
    ob = OrderBlockEngine()

    total = 0
    per_field_mismatch = {fld: 0 for fld in ALL_FIELDS}
    detailed = []
    last_mismatch_bar = None

    for i, row in enumerate(rows):
        o = _num(row[cols["open"]])
        h = _num(row[cols["high"]])
        l = _num(row[cols["low"]])
        c = _num(row[cols["close"]])
        if None in (o, h, l, c):
            continue

        ev = engine.update(Bar(index=i, open=o, high=h, low=l, close=c))
        snap = StructureSnapshot.from_engine(engine, ev)
        oe = ob.update(i, o, h, l, c, snap)
        py = _python_row(i, oe, snap)
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
    print(f"\nCompared {total} bars from {path.name}  (major_length={args.major_length}, tol={args.tolerance})")
    print("-" * 72)
    if not any(per_field_mismatch.values()):
        print("✓ OB PARITY: every compared field matched on every bar. Python OB engine == Pine source.")
        return 0

    print("MISMATCHES BY FIELD:")
    for fld in ALL_FIELDS:
        n = per_field_mismatch[fld]
        if n:
            print(f"  {fld:<24} {n} bar(s)")
    print("-" * 72)
    print(f"Last mismatching bar: {last_mismatch_bar}  "
          f"(if all mismatches are early, re-run with --warmup {(last_mismatch_bar or 0) + 1})")
    print(f"First {len(detailed)} mismatching bar(s) (row index, time, field: python vs pine):")
    for idx, tval, ms in detailed:
        print(f"  bar {idx}  {tval}")
        for fld, pv, pinev in ms:
            print(f"      {fld:<24} python={pv!r:<12} pine={pinev!r}")
    print("-" * 72)
    print("Tip: mismatches confined to early bars = warmup (structure not yet converged, or an OB "
          "whose leg began before the export window). Persistent mismatches after a clean run of "
          "bars = a real logic gap to fix against mpc_assistant.pine.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
