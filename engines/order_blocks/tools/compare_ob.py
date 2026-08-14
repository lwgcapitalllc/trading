#!/usr/bin/env python3
"""
compare_ob.py — parity check: TradingView Pine export vs Python order-block engine.

Purpose
-------
Prove the Python engine in order_blocks/ produces the same order blocks as the source-of-truth OB
blocks in mpc_assistant.pine, on real candles. It feeds OrderBlockEngine the same candles the Pine
build saw and diffs its output against the px_ob_* columns the Pine build plotted.

REBUILT 2026-07-31 alongside the engine. It used to run market_structure -> StructureSnapshot ->
OrderBlockEngine, because every block was born on a structure break. The mpc rework commented out
all four structure-creation sites, so the engine is STANDALONE now and this tool feeds it raw OHLC.
The px_i_break_origin_ago column went with it.

CONFIG COMES FROM THE EXPORT. ob_export.pine plots `cfg_ob_*` columns and this tool builds the
Python engine FROM them, so parity survives a Pine input tweak instead of silently diffing two
different configurations. Run it with NO config flags; the flags below are fallbacks for an export
taken before those columns existed.

What is compared (per bar, after --warmup)
------------------------------------------
  * The active OB arrays, slot by slot (slot 1 = oldest): px_ob_bull_top_1..10 / px_ob_bull_bot_1..10
    and the bear mirror, against active_bull[k]/active_bear[k].top/.bottom. This is the PRIMARY
    signal — matching the ordered arrays every bar proves creation, mitigation, expiry AND FIFO
    eviction all at once.
  * px_ob_bull_count / px_ob_bear_count against len(active_bull) / len(active_bear).
  * px_ob_bull_created / px_ob_bear_created / px_ob_bull_mit / px_ob_bear_mit against the count of
    created / mitigated OBs this bar (secondary localisers). NOTE the Pine lumps age-expiry into its
    delete without counting it as a mitigation, so the Python `expired` list is deliberately NOT
    added to px_ob_*_mit — an aged-out block shows up as an array-slot change only.

Data lineup
-----------
Export ONE CSV from TradingView with indicators/engines/ob_export.pine on the chart (chart menu → Export
chart data). Each row carries the candle (fed to Python) and the Pine OB engine's outputs. Both
sides come from the same file, so there is no data-source mismatch.

Warmup
------
The Pine export usually begins at a non-zero bar_index (TradingView had history before the export
window), so the Pine engine is already "warm" while Python starts cold: Pine's arrays open holding
blocks whose anchor candles are off-screen, and those only flush as they mitigate or FIFO out. ATR
also needs 14 bars and both sources read ~12-15 bars back. Use --warmup to skip those early bars;
the tool prints the last mismatching bar to help you pick it.

A persistent-level engine cannot be parity-checked on a window whose price never revisits the
pre-window extreme — the ghost blocks never mitigate. That was the 2026-07-19 lesson from EQ/FVG;
if warmup never clears, re-export WIDER rather than raising --warmup further.

Usage
-----
    python3 engines/order_blocks/tools/compare_ob.py path/to/ob_export.csv --warmup 300

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

from order_blocks import OrderBlockEngine

_MAX_SLOTS = 10  # mpc maxActiveOB default; ob_export.pine plots 10 slots per direction

# ── column groups ──
BULL_TOP = [f"px_ob_bull_top_{k}" for k in range(1, _MAX_SLOTS + 1)]
BULL_BOT = [f"px_ob_bull_bot_{k}" for k in range(1, _MAX_SLOTS + 1)]
BEAR_TOP = [f"px_ob_bear_top_{k}" for k in range(1, _MAX_SLOTS + 1)]
BEAR_BOT = [f"px_ob_bear_bot_{k}" for k in range(1, _MAX_SLOTS + 1)]
PRICE_FIELDS = BULL_TOP + BULL_BOT + BEAR_TOP + BEAR_BOT  # tolerance-compared, na-aware

COUNT_FIELDS = ["px_ob_bull_count", "px_ob_bear_count"]
PULSE_FIELDS = ["px_ob_bull_created", "px_ob_bear_created", "px_ob_bull_mit", "px_ob_bear_mit"]
INT_FIELDS = COUNT_FIELDS + PULSE_FIELDS  # integer-compared, na-aware

ALL_FIELDS = PRICE_FIELDS + INT_FIELDS

# Config columns the export carries, mapped to OrderBlockEngine kwargs. Missing ones fall back to
# the matching CLI flag (see main), which is what makes a pre-cfg export still checkable.
CFG_COLUMNS = {
    "cfg_ob_maxactive": ("max_active", int),
    "cfg_ob_bodyonly": ("body_only", lambda v: bool(round(v))),
    "cfg_ob_maxage": ("max_age", int),
    "cfg_ob_maxatr": ("max_atr", float),
    "cfg_ob_dupeoverlap": ("dupe_overlap", float),
    "cfg_ob_dispmult": ("disp_mult", float),
    "cfg_ob_pushmult": ("push_mult", float),
    "cfg_ob_turnwait": ("turn_wait", int),
    "cfg_ob_pushwait": ("push_wait", int),
}


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
                f"Make sure indicators/engines/ob_export.pine is the build on the chart and that you "
                f"exported via 'Export chart data'."
            )
        return None

    cols = {k: find(k) for k in ("open", "high", "low", "close")}
    cols["time"] = find("time", required=False)
    for f in ALL_FIELDS:
        cols[f] = find(f)
    for f in CFG_COLUMNS:
        cols[f] = find(f, required=False)
    return cols


def _python_row(oe):
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
    return row


def _values_match(field, py_val, pine_val, tol):
    if field in PRICE_FIELDS:
        if py_val is None and pine_val is None:
            return True
        if py_val is None or pine_val is None:
            return False
        return abs(py_val - pine_val) <= tol
    # integer fields (counts / pulses). A missing Pine cell for a pulse/count means 0.
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
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("csv", help="CSV exported from TradingView with ob_export.pine on the chart")
    ap.add_argument(
        "--max-active",
        type=int,
        default=10,
        help="fallback if the export has no cfg_ob_maxactive column (Pine default 10)",
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
        help="skip the first N bars in the report (still fed to the engines)",
    )
    args = ap.parse_args(argv)

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"ERROR: file not found: {path}")

    with open(path, newline="") as f:
        header = next(csv.reader(f))
    cols = _resolve_columns(header)
    rows = _load_rows(path, cols)

    # Configure the engine FROM the export where it can, so a Pine tweak cannot silently make this
    # a comparison of two different configurations.
    cfg = {"max_active": args.max_active}
    cfg_from_export = {}
    for col, (kwarg, cast) in CFG_COLUMNS.items():
        if not cols.get(col):
            continue
        raw = next((_num(r[cols[col]]) for r in rows if _num(r[cols[col]]) is not None), None)
        if raw is not None:
            cfg[kwarg] = cast(raw)
            cfg_from_export[kwarg] = cfg[kwarg]
    if cfg_from_export:
        print(
            "Config read from the export: "
            + ", ".join(f"{k}={v}" for k, v in sorted(cfg_from_export.items()))
        )
    else:
        print(
            "WARNING: this export carries no cfg_ob_* columns (taken before 2026-07-31). "
            "Falling back to engine defaults + --max-active; a mismatch may just be a config gap."
        )
    ob = OrderBlockEngine(**cfg)

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

        oe = ob.update(i, o, h, l, c)
        py = _python_row(oe)
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
    print(
        f"\nCompared {total} bars from {path.name}  "
        f"(max_active={cfg.get('max_active')}, tol={args.tolerance})"
    )
    print("-" * 72)
    if not any(per_field_mismatch.values()):
        print(
            "✓ OB PARITY: every compared field matched on every bar. Python OB engine == Pine source."
        )
        return 0

    print("MISMATCHES BY FIELD:")
    for fld in ALL_FIELDS:
        n = per_field_mismatch[fld]
        if n:
            print(f"  {fld:<24} {n} bar(s)")
    print("-" * 72)
    print(
        f"Last mismatching bar: {last_mismatch_bar}  "
        f"(if all mismatches are early, re-run with --warmup {(last_mismatch_bar or 0) + 1})"
    )
    print(f"First {len(detailed)} mismatching bar(s) (row index, time, field: python vs pine):")
    for idx, tval, ms in detailed:
        print(f"  bar {idx}  {tval}")
        for fld, pv, pinev in ms:
            print(f"      {fld:<24} python={pv!r:<12} pine={pinev!r}")
    print("-" * 72)
    print(
        "Tip: mismatches confined to early bars = warmup (ATR still seeding, or a pre-window block "
        "still lingering in Pine's arrays). Persistent mismatches after a clean run of bars = a "
        "real logic gap to fix against mpc_assistant.pine. If warmup NEVER clears, re-export a "
        "WIDER window rather than raising --warmup — a block price never returns to cannot "
        "mitigate, so a ghost from before the window can sit in Pine's array for ever."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
