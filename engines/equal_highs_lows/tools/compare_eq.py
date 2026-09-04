#!/usr/bin/env python3
"""
compare_eq.py — parity check: TradingView Pine export vs Python Equal Highs/Lows engine.

Purpose
-------
Prove the Python engine in equal_highs_lows/ produces the same EQH/EQL levels as the source-of-truth
"EQUAL HIGHS / LOWS" block in mpc_jarvis.pine, on real candles. It runs EqualHighsLowsEngine on the
same candles the Pine build saw and diffs its output against the px_eq* columns the Pine build plotted.

What is compared (per bar, after --warmup)
------------------------------------------
  * px_eq_tol            against ev.tolerance              (ATR(50)×mult equality band — tolerance-compared)
  * px_eq_ph / px_eq_pl  against ev.pivot_high / ev.pivot_low   (strict price pivots confirmed this bar; na-aware)
  * px_eqh_new / px_eql_new against the level PRICE formed this bar (na when none formed)
  * px_eqh_cnt / px_eql_cnt against len(ev.active_eqh) / len(ev.active_eql)   (exact counts)
  * px_eqh_0..5 / px_eql_0..5 against ev.active_eqh[i] / ev.active_eql[i]      (the active-level prices,
    oldest→newest slots; na past the count)

Data lineup
-----------
Export ONE CSV from TradingView with indicators/engines/eq_export.pine on the chart (chart menu → Export chart
data), with showEq ON. Each row carries the candle (fed to Python) and the Pine EQ engine's state.
Both sides come from the same file, so there is no data-source mismatch. Set --pivot-len / --atr-mult /
--max-levels to match the Pine inputs (defaults 2 / 0.1 / 6 = the mpc defaults). Six slots per side
assume the default eqMax=6; raise --max-levels only if the Pine input was raised (extra slots won't
export past six).

Warmup
------
The Pine export usually begins at a non-zero bar_index (TradingView had history before the export
window), so its ATR is already warm and it may already hold active EQ levels (and a prior pivot in
eqPrevPh/eqPrevPl) from before the window. The cold-started Python engine (ATR seeds from row 0; no
prior pivots or levels) converges once its Wilder ATR settles and the off-window levels it can't see
have all been mitigated. Use --warmup to skip those early bars; the tool prints the last mismatching
bar to help you pick it.

Usage
-----
    python3 equal_highs_lows/tools/compare_eq.py path/to/eq_export.csv
    python3 equal_highs_lows/tools/compare_eq.py eq_export.csv --warmup 400

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

from equal_highs_lows import EqualHighsLowsEngine

# ── column groups ──
PRICE_FIELDS = (["px_eq_tol", "px_eq_ph", "px_eq_pl", "px_eqh_new", "px_eql_new"]
                + [f"px_eqh_{i}" for i in range(6)]
                + [f"px_eql_{i}" for i in range(6)])          # price/tolerance scale, tol-compared, na-aware
COUNT_FIELDS = ["px_eqh_cnt", "px_eql_cnt"]                    # active-level counts, exact
ALL_FIELDS = PRICE_FIELDS + COUNT_FIELDS


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
                f"Make sure indicators/engines/eq_export.pine is the build on the chart and that you "
                f"exported via 'Export chart data'."
            )
        return None

    cols = {k: find(k) for k in ("open", "high", "low", "close")}
    cols["time"] = find("time", required=False)
    for f in ALL_FIELDS:
        cols[f] = find(f)
    return cols


def _python_row(ev):
    """Map the Python EQ events + live state to each px_eq* column value."""
    eqh_new = next((l.price for l in ev.formed if l.is_high), None)
    eql_new = next((l.price for l in ev.formed if not l.is_high), None)
    row = {
        "px_eq_tol": ev.tolerance,
        "px_eq_ph": ev.pivot_high,
        "px_eq_pl": ev.pivot_low,
        "px_eqh_new": eqh_new,
        "px_eql_new": eql_new,
        "px_eqh_cnt": float(len(ev.active_eqh)),
        "px_eql_cnt": float(len(ev.active_eql)),
    }
    for i in range(6):
        row[f"px_eqh_{i}"] = ev.active_eqh[i] if i < len(ev.active_eqh) else None
        row[f"px_eql_{i}"] = ev.active_eql[i] if i < len(ev.active_eql) else None
    return row


def _values_match(field, py_val, pine_val, tol):
    if field in COUNT_FIELDS:
        # a missing Pine cell is 0 active levels.
        if pine_val is None:
            pine_val = 0.0
        if py_val is None:
            py_val = 0.0
        return int(round(py_val)) == int(round(pine_val))
    # price/tolerance fields: na-aware absolute tolerance.
    if py_val is None and pine_val is None:
        return True
    if py_val is None or pine_val is None:
        return False
    return abs(py_val - pine_val) <= tol


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
    ap.add_argument("csv", help="CSV exported from TradingView with eq_export.pine on the chart")
    ap.add_argument("--pivot-len", type=int, default=2, help="must match the Pine eqPivotLen (default 2)")
    ap.add_argument("--atr-mult", type=float, default=0.1, help="must match the Pine eqAtrMult (default 0.1)")
    ap.add_argument("--max-levels", type=int, default=6, help="must match the Pine eqMax (default 6, per side)")
    ap.add_argument("--tolerance", type=float, default=1e-2, help="abs tolerance for price/tolerance fields (default 1e-2, covers CSV rounding)")
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

    eng = EqualHighsLowsEngine(pivot_len=args.pivot_len, atr_mult=args.atr_mult, max_levels=args.max_levels)

    total = 0
    per_field_mismatch = {fld: 0 for fld in ALL_FIELDS}
    detailed = []
    last_mismatch_bar = None

    for i, row in enumerate(rows):
        h = _num(row[cols["high"]])
        l = _num(row[cols["low"]])
        c = _num(row[cols["close"]])
        if None in (h, l, c):
            continue

        ev = eng.update(i, h, l, c)
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
    print(f"\nCompared {total} bars from {path.name}  "
          f"(pivot_len={args.pivot_len}, atr_mult={args.atr_mult}, max_levels={args.max_levels}, tol={args.tolerance})")
    print("-" * 72)
    if not any(per_field_mismatch.values()):
        print("✓ EQ PARITY: every compared field matched on every bar. Python engine == Pine source.")
        return 0

    print("MISMATCHES BY FIELD:")
    for fld in ALL_FIELDS:
        n = per_field_mismatch[fld]
        if n:
            print(f"  {fld:<12} {n} bar(s)")
    print("-" * 72)
    print(f"Last mismatching bar: {last_mismatch_bar}  "
          f"(if all mismatches are early, re-run with --warmup {(last_mismatch_bar or 0) + 1})")
    print(f"First {len(detailed)} mismatching bar(s) (row index, time, field: python vs pine):")
    for idx, tval, ms in detailed:
        print(f"  bar {idx}  {tval}")
        for fld, pv, pinev in ms:
            print(f"      {fld:<12} python={pv!r:<16} pine={pinev!r}")
    print("-" * 72)
    print("Tip: mismatches confined to early bars = warmup (Pine's ATR was already warm and it may hold "
          "active EQ levels and a prior pivot from before the export window; the cold-started Python "
          "engine converges once its ATR settles and those off-window levels have been mitigated). "
          "Persistent mismatches after a clean run = a real logic gap to fix against mpc_jarvis.pine.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
