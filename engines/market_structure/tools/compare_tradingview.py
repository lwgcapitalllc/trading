#!/usr/bin/env python3
"""
compare_tradingview.py — parity check: TradingView Pine export vs Python StructureEngine.

Purpose
-------
Prove the Python port in market_structure/ produces the same structure as the validated Pine
source, on real candles, before trusting it for live trading. It does this by running BOTH
engines on the *exact same* candles and diffing their output bar by bar.

How the data lines up
---------------------
You export ONE CSV from TradingView (chart menu → Export chart data) with the
`indicators/engines/structure_engine_export.pine` build on the chart. That CSV contains, in each row:
  - the candle: open/high/low/close  (this is what we feed into the Python engine)
  - the Pine engine's output columns:  px_ash, px_asl, px_dir, px_lch, px_lcl,
    px_bull_bos, px_bear_bos, px_bull_sos, px_bear_sos, px_new_sh, px_new_sl,
    px_i_sw, px_i_mode, px_i_bull_break, px_i_bear_break
  - (newer export builds also add the break-leg columns px_bull_bos_high/low/h_ago/l_ago +
    bear mirror; these are compared when present and simply skipped for older CSVs that lack them)
Because both sides come from the SAME file, there is no data-source mismatch and no timestamp
alignment problem — we compare row against row. We feed the OHLC columns into the Python engine
and compare its output against the px_* columns in the same row.

Usage
-----
    python market_structure/tools/compare_tradingview.py path/to/export.csv
    python market_structure/tools/compare_tradingview.py export.csv --major-length 15 \
        --tolerance 1e-6 --max-report 40

Exit code 0 if every bar matches, 1 if any mismatch (CI-friendly).

Only depends on the standard library.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Repo root on sys.path so `market_structure` imports whether run from anywhere.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from market_structure import Bar, StructureEngine

# px_ columns that carry a PRICE (compared with a float tolerance; may be blank/na).
PRICE_FIELDS = ["px_ash", "px_asl", "px_lch", "px_lcl", "px_i_sw"]
# px_ columns that carry a small INTEGER state (compared exactly).
INT_FIELDS = ["px_dir", "px_i_mode"]
# px_ columns that are a 0/1 event pulse (compared exactly).
PULSE_FIELDS = [
    "px_bull_bos",
    "px_bear_bos",
    "px_bull_sos",
    "px_bear_sos",
    "px_new_sh",
    "px_new_sl",
    "px_i_bull_break",
    "px_i_bear_break",
]
ALL_FIELDS = PRICE_FIELDS + INT_FIELDS + PULSE_FIELDS

# OPTIONAL break-leg columns — only present in CSVs exported from the newer export build. Old
# exports lack them and are still fully validated on every field they DO carry. Prices compare
# with a float tolerance; the *_ago columns are "bars ago" integers (compared exactly), which is
# how the export makes bar locations comparable across Pine's absolute bar_index vs the engine's
# 0-based row index. See structure_engine_export.pine for the matching plot() calls.
LEG_PRICE_FIELDS = ["px_bull_bos_high", "px_bull_bos_low", "px_bear_bos_high", "px_bear_bos_low"]
LEG_AGO_FIELDS = [
    "px_bull_bos_h_ago",
    "px_bull_bos_l_ago",
    "px_bear_bos_h_ago",
    "px_bear_bos_l_ago",
]
OPTIONAL_FIELDS = LEG_PRICE_FIELDS + LEG_AGO_FIELDS


def _num(s):
    """Parse a CSV cell to float, or None for blank / na / NaN."""
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
    """
    Map the logical names we need (open/high/low/close/time + each px_*) to the actual CSV
    header strings. TradingView usually names plot columns exactly by their plot title, but
    can prefix them with the indicator name — so we match case-insensitively by exact name
    first, then by 'endswith', then by 'contains'.
    """
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
                f"Make sure the structure_engine_export.pine build is the one on the chart "
                f"and that you exported via 'Export chart data'."
            )
        return None

    cols = {k: find(k) for k in ("open", "high", "low", "close")}
    cols["time"] = find("time", required=False)
    for f in ALL_FIELDS:
        cols[f] = find(f)
    present_optional = []
    for f in OPTIONAL_FIELDS:
        col = find(f, required=False)
        if col is not None:
            cols[f] = col
            present_optional.append(f)
    return cols, present_optional


def _python_row(engine, ev, bar_index):
    """Compute the Python engine's equivalent of each px_* column, end-of-bar."""
    ash = engine.active_swing_high
    asl = engine.active_swing_low
    lch = engine.last_confirmed_high
    lcl = engine.last_confirmed_low
    isw = engine.internal_swing
    e, n = ev.external, ev.internal

    def ago(loc):
        # Match the export's "bars ago" encoding; None (na) except on the break bar.
        return None if loc is None else float(bar_index - loc)

    return {
        "px_ash": ash.price if ash else None,
        "px_asl": asl.price if asl else None,
        "px_dir": float(engine.dir),
        "px_lch": lch.price if lch else None,
        "px_lcl": lcl.price if lcl else None,
        "px_bull_bos": 1.0 if e.bull_bos else 0.0,
        "px_bear_bos": 1.0 if e.bear_bos else 0.0,
        "px_bull_sos": 1.0 if e.bull_sos else 0.0,
        "px_bear_sos": 1.0 if e.bear_sos else 0.0,
        "px_new_sh": 1.0 if e.new_swing_high else 0.0,
        "px_new_sl": 1.0 if e.new_swing_low else 0.0,
        "px_i_sw": isw.price if isw else None,
        "px_i_mode": float(engine.internal_mode),
        # Pine's int_bull_break/int_bear_break fire for BOTH iBOS and iSOS — combine to match.
        "px_i_bull_break": 1.0 if (n.bull_bos or n.bull_sos) else 0.0,
        "px_i_bear_break": 1.0 if (n.bear_bos or n.bear_sos) else 0.0,
        # Optional break-leg columns (only compared when present in the CSV).
        "px_bull_bos_high": e.bull_bos_high,
        "px_bull_bos_low": e.bull_bos_low,
        "px_bear_bos_high": e.bear_bos_high,
        "px_bear_bos_low": e.bear_bos_low,
        "px_bull_bos_h_ago": ago(e.bull_bos_h_loc),
        "px_bull_bos_l_ago": ago(e.bull_bos_l_loc),
        "px_bear_bos_h_ago": ago(e.bear_bos_h_loc),
        "px_bear_bos_l_ago": ago(e.bear_bos_l_loc),
    }


def _values_match(field, py_val, pine_val, tol):
    if field in PRICE_FIELDS or field in LEG_PRICE_FIELDS:
        if py_val is None and pine_val is None:
            return True
        if py_val is None or pine_val is None:
            return False
        return abs(py_val - pine_val) <= tol
    # int / pulse fields: treat a missing Pine cell as 0 only for pulses, exact otherwise
    if pine_val is None:
        pine_val = 0.0 if field in PULSE_FIELDS else pine_val
    if py_val is None or pine_val is None:
        return py_val == pine_val
    return int(round(py_val)) == int(round(pine_val))


def _load_rows(path, cols):
    """Read all rows, sort oldest→newest by time if a parseable time column exists."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))

    tcol = cols.get("time")
    if tcol:

        def tkey(r):
            raw = (r.get(tcol) or "").strip()
            if raw.isdigit():
                return int(raw)
            try:
                # tolerate trailing Z / offset
                from datetime import datetime

                return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
            except Exception:
                return None

        keys = [tkey(r) for r in rows]
        if all(k is not None for k in keys) and keys != sorted(keys):
            rows = [r for _, r in sorted(zip(keys, rows), key=lambda p: p[0])]
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "csv", help="CSV exported from TradingView with structure_engine_export.pine on the chart"
    )
    ap.add_argument(
        "--major-length", type=int, default=15, help="must match the Pine build (default 15)"
    )
    ap.add_argument(
        "--tolerance",
        type=float,
        default=1e-6,
        help="abs tolerance for price fields (default 1e-6)",
    )
    ap.add_argument(
        "--max-report", type=int, default=30, help="how many mismatching bars to print in detail"
    )
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
    cols, present_optional = _resolve_columns(header)
    rows = _load_rows(path, cols)

    compare_fields = ALL_FIELDS + present_optional

    engine = StructureEngine(major_length=args.major_length)

    total = 0
    per_field_mismatch = {fld: 0 for fld in compare_fields}
    detailed = []

    for i, row in enumerate(rows):
        o = _num(row[cols["open"]])
        h = _num(row[cols["high"]])
        l = _num(row[cols["low"]])
        c = _num(row[cols["close"]])
        if None in (o, h, l, c):
            continue  # skip incomplete rows (e.g. a trailing live/blank bar)

        ev = engine.update(Bar(index=i, open=o, high=h, low=l, close=c))
        py = _python_row(engine, ev, i)
        total += 1

        if i < args.warmup:
            continue

        bar_mismatches = []
        for fld in compare_fields:
            pine_val = _num(row[cols[fld]])
            if not _values_match(fld, py[fld], pine_val, args.tolerance):
                per_field_mismatch[fld] += 1
                bar_mismatches.append((fld, py[fld], pine_val))

        if bar_mismatches and len(detailed) < args.max_report:
            tval = row[cols["time"]] if cols.get("time") else ""
            detailed.append((i, tval, bar_mismatches))

    # ── Report ──
    print(
        f"\nCompared {total} bars from {path.name}  (major_length={args.major_length}, tol={args.tolerance})"
    )
    if present_optional:
        print(f"Break-leg columns found and checked: {', '.join(present_optional)}")
    else:
        print(
            "Break-leg columns not in this CSV (older export) — skipped; all other fields checked."
        )
    print("-" * 72)
    any_mismatch = any(per_field_mismatch.values())
    if not any_mismatch:
        print("✓ PARITY: every field matched on every bar. Python engine == Pine source.")
        return 0

    print("MISMATCHES BY FIELD:")
    for fld in compare_fields:
        n = per_field_mismatch[fld]
        if n:
            print(f"  {fld:<18} {n} bar(s)")
    print("-" * 72)
    print(f"First {len(detailed)} mismatching bar(s) (row index, time, field: python vs pine):")
    for idx, tval, ms in detailed:
        print(f"  bar {idx}  {tval}")
        for fld, pv, pinev in ms:
            print(f"      {fld:<18} python={pv!r:<12} pine={pinev!r}")
    print("-" * 72)
    print(
        "Tip: a small cluster of mismatches at ONE bar that then resync is usually a boundary/"
        "tie-break edge case; persistent divergence after a bar means a real logic gap."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
