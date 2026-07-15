#!/usr/bin/env python3
"""
compare_fvg.py — parity check: TradingView Pine export vs Python fair-value-gap engine.

Purpose
-------
Prove the Python engine in fair_value_gaps/ produces the same gaps as the source-of-truth FVG block
in mpc_assistant.pine, on real candles. It runs FairValueGapEngine on the same candles the Pine build
saw and diffs its output against the px_fvg_* columns the Pine build plotted.

What is compared (per bar, after --warmup)
------------------------------------------
  * The active gap arrays, slot by slot (slot 1 = oldest): px_fvg_top_1..6 / px_fvg_bot_1..6 against
    active[k].top / .bottom, and px_fvg_bull_1..6 against active[k].is_bullish (1/0). Matching the
    ordered arrays every bar proves formation, mitigation AND FIFO eviction all at once.
  * px_fvg_count against len(active).
  * px_fvg_formed / px_fvg_mit against the count of gaps formed / mitigated this bar (localisers).

Data lineup
-----------
Export ONE CSV from TradingView with indicators/fvg_export.pine on the chart (chart menu → Export
chart data). Each row carries the candle (fed to Python) and the Pine FVG engine's outputs. Both
sides come from the same file, so there is no data-source mismatch. Set --max-count / --threshold-pct
to match the Pine inputs (defaults 6 / 0.1 = the mpc defaults — max_count 6 and a hardcoded
0.1%-of-price gap floor).

Warmup
------
The Pine export usually begins at a non-zero bar_index (TradingView had history before the export
window), so the Pine engine may already hold gaps whose displacement began off-window. The
cold-started Python engine can't know them; they flush out as they are closed past or FIFO-evicted. Use --warmup to
skip those early bars; the tool prints the last mismatching bar to help you pick it.

Usage
-----
    python3 fair_value_gaps/tools/compare_fvg.py path/to/fvg_export.csv
    python3 fair_value_gaps/tools/compare_fvg.py fvg_export.csv --max-count 6 --warmup 50

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

from fair_value_gaps import FairValueGapEngine

_MAX_SLOTS = 6  # mpc fvgMaxCount default; fvg_export.pine plots 6 slots

# ── column groups ──
TOP_FIELDS = [f"px_fvg_top_{k}" for k in range(1, _MAX_SLOTS + 1)]
BOT_FIELDS = [f"px_fvg_bot_{k}" for k in range(1, _MAX_SLOTS + 1)]
PRICE_FIELDS = TOP_FIELDS + BOT_FIELDS                    # tolerance-compared, na-aware
BULL_FIELDS = [f"px_fvg_bull_{k}" for k in range(1, _MAX_SLOTS + 1)]  # 1/0 state, na-aware
COUNT_FIELDS = ["px_fvg_count"]
PULSE_FIELDS = ["px_fvg_formed", "px_fvg_mit"]
STATE_FIELDS = BULL_FIELDS + COUNT_FIELDS + PULSE_FIELDS  # integer-compared, na-aware

ALL_FIELDS = PRICE_FIELDS + STATE_FIELDS


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
                f"Make sure indicators/fvg_export.pine is the build on the chart and that you "
                f"exported via 'Export chart data'."
            )
        return None

    cols = {k: find(k) for k in ("open", "high", "low", "close")}
    cols["time"] = find("time", required=False)
    for f in ALL_FIELDS:
        cols[f] = find(f)
    return cols


def _python_row(ev):
    """Map the Python FVG events to each px_fvg_* column value."""
    row = {}
    for slot, (tf, bf, bull) in enumerate(zip(TOP_FIELDS, BOT_FIELDS, BULL_FIELDS)):
        g = ev.active[slot] if slot < len(ev.active) else None
        row[tf] = g.top if g else None
        row[bf] = g.bottom if g else None
        row[bull] = (1.0 if g.is_bullish else 0.0) if g else None
    row["px_fvg_count"] = float(len(ev.active))
    row["px_fvg_formed"] = float(len(ev.formed))
    row["px_fvg_mit"] = float(len(ev.mitigated))
    return row


def _values_match(field, py_val, pine_val, tol):
    if field in PRICE_FIELDS:
        if py_val is None and pine_val is None:
            return True
        if py_val is None or pine_val is None:
            return False
        return abs(py_val - pine_val) <= tol
    # state fields. bull slots are na when the slot is empty (both sides None -> match); counts /
    # pulses have no na — a missing Pine cell is 0.
    if field in BULL_FIELDS:
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
    ap.add_argument("csv", help="CSV exported from TradingView with fvg_export.pine on the chart")
    ap.add_argument("--max-count", type=int, default=6, help="must match the Pine fvgMaxCount (default 6)")
    ap.add_argument("--threshold-pct", type=float, default=0.1, help="must match the Pine fvgThreshPct (default 0.1 = 0.1%% of price)")
    ap.add_argument("--tolerance", type=float, default=1e-6, help="abs tolerance for price fields (default 1e-6)")
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

    fvg = FairValueGapEngine(max_count=args.max_count, threshold_pct=args.threshold_pct)

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

        ev = fvg.update(i, o, h, l, c)
        py = _python_row(ev)
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
    print(f"\nCompared {total} bars from {path.name}  (max_count={args.max_count}, threshold_pct={args.threshold_pct}, tol={args.tolerance})")
    print("-" * 72)
    if not any(per_field_mismatch.values()):
        print("✓ FVG PARITY: every compared field matched on every bar. Python FVG engine == Pine source.")
        return 0

    print("MISMATCHES BY FIELD:")
    for fld in ALL_FIELDS:
        n = per_field_mismatch[fld]
        if n:
            print(f"  {fld:<20} {n} bar(s)")
    print("-" * 72)
    print(f"Last mismatching bar: {last_mismatch_bar}  "
          f"(if all mismatches are early, re-run with --warmup {(last_mismatch_bar or 0) + 1})")
    print(f"First {len(detailed)} mismatching bar(s) (row index, time, field: python vs pine):")
    for idx, tval, ms in detailed:
        print(f"  bar {idx}  {tval}")
        for fld, pv, pinev in ms:
            print(f"      {fld:<20} python={pv!r:<12} pine={pinev!r}")
    print("-" * 72)
    print("Tip: mismatches confined to early bars = warmup (a gap whose displacement began before "
          "the export window still lingering in Pine's arrays). Persistent mismatches after a clean "
          "run of bars = a real logic gap to fix against mpc_assistant.pine.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
