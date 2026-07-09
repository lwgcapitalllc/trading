#!/usr/bin/env python3
"""
compare_fib.py — parity check: TradingView Pine export vs Python Structure fib.

Purpose
-------
Prove the Python fibs in fibonacci/ (Structure + Sniper + Macro) produce the same level events as
the source-of-truth fibs in mpc_assistant.pine, on real candles. It runs the REAL pipeline —
market_structure's StructureEngine feeds a StructureSnapshot into StructureFib, SniperFib and
MacroFib — on the same candles the Pine build saw, and diffs their output against the px_fib_* /
px_sniper_* / px_macro_* columns the Pine build plotted.

Data lineup
-----------
Export ONE CSV from TradingView with indicators/fib_export.pine on the chart (chart menu →
Export chart data). Each row carries the candle (fed to Python) and the Pine fibs' outputs:
  Structure: px_fib_active, px_fib_dir, px_fib_origin,
             px_fib_<lvl>_price and px_fib_<lvl>_touch for lvl in E1..E4, 100, TP1..TP5
  Sniper:    px_sniper_active, px_sniper_dir, px_sniper_top, px_sniper_bot,
             px_sniper_created, px_sniper_confirmed, px_sniper_zone_active
  Macro:     px_macro_active/dir/locked/visible/new_cycle/extended, px_macro_top, px_macro_bot,
             px_macro_<lvl>_price and px_macro_<lvl>_touch for lvl in E1..E4, LL, TP1, TP2, HH
Both sides come from the same file, so there is no data-source mismatch. The Macro fib only runs
on <=5m in Pine, so export on a <=5m chart to validate it (Structure + Sniper validate on any TF).

Warmup
------
The Pine export usually begins at a non-zero bar_index (TradingView had history before the export
window), so the Pine engines are already "warm" while the Python engines start cold. The fib needs
BOTH the structure to converge AND the first full fib leg to start inside the window before it can
match (a leg whose 0.618 was hit before the window is latched in Pine but not in Python). Use
--warmup to skip those early bars; the tool prints the last mismatching bar to help you pick it.

Usage
-----
    python3 fibonacci/tools/compare_fib.py path/to/fib_export.csv
    python3 fibonacci/tools/compare_fib.py fib_export.csv --major-length 15 --warmup 300

Exit 0 if every compared bar matches, 1 otherwise. Standard library only.
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
from fibonacci import InternalFib, MacroFib, SniperFib, StructureFib, StructureSnapshot

# Column suffix -> Python level name (see fib_export.pine plot titles). TP4 (-0.270) and TP5
# (-0.618) were dropped in the 2026-07-08 mpc_assistant.pine re-paste.
_LVL = [
    ("e1", "E1"), ("e2", "E2"), ("e3", "E3"), ("e4", "E4"), ("100", "1.0"),
    ("tp1", "TP1"), ("tp2", "TP2"), ("tp3", "TP3"),
]
# Macro fib level suffix -> Python level name.
_MACRO_LVL = [
    ("e1", "E1"), ("e2", "E2"), ("e3", "E3"), ("e4", "E4"), ("ll", "LL"),
    ("tp1", "TP1"), ("tp2", "TP2"), ("hh", "HH"),
]
# Internal fib: same 8 levels as the Structure fib, but the export carries TOUCH pulses only (no
# per-level price columns — they'd push the harness past TradingView's 64-plot limit). The touch
# pulses validate the geometry indirectly (a touch fires exactly when price crosses a level).
_IFIB_LVL = [
    ("e1", "E1"), ("e2", "E2"), ("e3", "E3"), ("e4", "E4"), ("100", "1.0"),
    ("tp1", "TP1"), ("tp2", "TP2"), ("tp3", "TP3"),
]

# ── Structure fib columns ──
FIB_PRICE_FIELDS = [f"px_fib_{sfx}_price" for sfx, _ in _LVL]
TOUCH_FIELDS = [f"px_fib_{sfx}_touch" for sfx, _ in _LVL]

# ── Sniper fib columns ──
SNIPER_PRICE_FIELDS = ["px_sniper_top", "px_sniper_bot"]
SNIPER_PULSE_FIELDS = ["px_sniper_active", "px_sniper_created", "px_sniper_confirmed", "px_sniper_zone_active"]

# ── Macro fib columns ──
MACRO_PRICE_FIELDS = [f"px_macro_{sfx}_price" for sfx, _ in _MACRO_LVL] + ["px_macro_top", "px_macro_bot"]
MACRO_TOUCH_FIELDS = [f"px_macro_{sfx}_touch" for sfx, _ in _MACRO_LVL]
MACRO_PULSE_FIELDS = MACRO_TOUCH_FIELDS + [
    "px_macro_active", "px_macro_locked", "px_macro_visible", "px_macro_new_cycle", "px_macro_extended",
]

# ── Internal fib columns (touch pulses + state only, no price columns) ──
IFIB_TOUCH_FIELDS = [f"px_ifib_{sfx}_touch" for sfx, _ in _IFIB_LVL]
IFIB_PULSE_FIELDS = IFIB_TOUCH_FIELDS + ["px_ifib_active", "px_ifib_reset_active"]

PRICE_FIELDS = FIB_PRICE_FIELDS + SNIPER_PRICE_FIELDS + MACRO_PRICE_FIELDS
PULSE_FIELDS = (
    TOUCH_FIELDS + ["px_fib_active", "px_fib_origin", "px_fib_reset_active"]
    + SNIPER_PULSE_FIELDS + MACRO_PULSE_FIELDS + IFIB_PULSE_FIELDS
)
DIR_FIELDS = ["px_fib_dir", "px_sniper_dir", "px_macro_dir", "px_ifib_dir"]
ALL_FIELDS = PRICE_FIELDS + PULSE_FIELDS + DIR_FIELDS

# The Structure fib columns are required (except px_fib_reset_active, added in the 2026-07-08
# re-sync — optional so older exports still validate); Sniper, Macro and Internal columns are all
# optional so this tool still runs against an older export made before those plots existed.
STRUCT_FIELDS = FIB_PRICE_FIELDS + TOUCH_FIELDS + ["px_fib_active", "px_fib_origin", "px_fib_dir"]
STRUCT_OPT_FIELDS = ["px_fib_reset_active"]
SNIPER_FIELDS = SNIPER_PRICE_FIELDS + SNIPER_PULSE_FIELDS + ["px_sniper_dir"]
MACRO_FIELDS = MACRO_PRICE_FIELDS + MACRO_PULSE_FIELDS + ["px_macro_dir"]
IFIB_FIELDS = IFIB_PULSE_FIELDS + ["px_ifib_dir"]


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
                f"Make sure indicators/fib_export.pine is the build on the chart and that you "
                f"exported via 'Export chart data'."
            )
        return None

    cols = {k: find(k) for k in ("open", "high", "low", "close")}
    cols["time"] = find("time", required=False)
    for f in STRUCT_FIELDS:
        cols[f] = find(f)                     # required
    for f in STRUCT_OPT_FIELDS + SNIPER_FIELDS + MACRO_FIELDS + IFIB_FIELDS:
        cols[f] = find(f, required=False)     # optional (older / higher-TF exports lack these)
    return cols


def _python_row(fib_ev, sniper_ev, macro_ev, ifib_ev):
    """Map the Python fib events to each px_fib_* / px_sniper_* / px_macro_* / px_ifib_* value."""
    active = fib_ev.active
    touched_names = {t.level for t in fib_ev.touched}
    row = {
        "px_fib_active": 1.0 if active else 0.0,
        "px_fib_origin": 1.0 if fib_ev.origin_changed else 0.0,
        "px_fib_reset_active": 1.0 if fib_ev.reset_active else 0.0,
        "px_fib_dir": float(fib_ev.direction) if active else None,
    }
    for sfx, name in _LVL:
        row[f"px_fib_{sfx}_price"] = fib_ev.levels.get(name) if active else None
        row[f"px_fib_{sfx}_touch"] = 1.0 if name in touched_names else 0.0

    # Sniper fib. active == a zone exists; top/dir are na until then (matches the Pine plots).
    sn_active = sniper_ev.active
    row["px_sniper_active"] = 1.0 if sn_active else 0.0
    row["px_sniper_created"] = 1.0 if sniper_ev.created else 0.0
    row["px_sniper_confirmed"] = 1.0 if sniper_ev.confirmed else 0.0
    row["px_sniper_zone_active"] = 1.0 if sniper_ev.zone_active else 0.0
    row["px_sniper_dir"] = float(sniper_ev.direction) if sn_active else None
    row["px_sniper_top"] = sniper_ev.zone_top if sn_active else None
    row["px_sniper_bot"] = sniper_ev.zone_bot if sn_active else None

    # Macro fib. active == levels currently computed (visible + locked + range>0).
    m_active = macro_ev.active
    macro_touched = {t.level for t in macro_ev.touched}
    row["px_macro_active"] = 1.0 if m_active else 0.0
    row["px_macro_locked"] = 1.0 if macro_ev.locked else 0.0
    row["px_macro_visible"] = 1.0 if macro_ev.visible else 0.0
    row["px_macro_new_cycle"] = 1.0 if macro_ev.new_cycle else 0.0
    row["px_macro_extended"] = 1.0 if macro_ev.extended else 0.0
    row["px_macro_dir"] = float(macro_ev.direction) if m_active else None
    row["px_macro_top"] = macro_ev.top if m_active else None
    row["px_macro_bot"] = macro_ev.bot if m_active else None
    for sfx, name in _MACRO_LVL:
        row[f"px_macro_{sfx}_price"] = macro_ev.levels.get(name) if m_active else None
        row[f"px_macro_{sfx}_touch"] = 1.0 if name in macro_touched else 0.0

    # Internal fib. active == an internal leg is seeded; touch pulses only (no price columns).
    i_active = ifib_ev.active
    ifib_touched = {t.level for t in ifib_ev.touched}
    row["px_ifib_active"] = 1.0 if i_active else 0.0
    row["px_ifib_reset_active"] = 1.0 if ifib_ev.reset_active else 0.0
    row["px_ifib_dir"] = float(ifib_ev.direction) if i_active else None
    for sfx, name in _IFIB_LVL:
        row[f"px_ifib_{sfx}_touch"] = 1.0 if name in ifib_touched else 0.0
    return row


def _values_match(field, py_val, pine_val, tol):
    if field in PRICE_FIELDS or field in DIR_FIELDS:
        if py_val is None and pine_val is None:
            return True
        if py_val is None or pine_val is None:
            return False
        if field in DIR_FIELDS:
            return int(round(py_val)) == int(round(pine_val))
        return abs(py_val - pine_val) <= tol
    # pulse fields: a missing Pine cell is 0
    if pine_val is None:
        pine_val = 0.0
    if py_val is None:
        return False
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
    ap.add_argument("csv", help="CSV exported from TradingView with fib_export.pine on the chart")
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

    have_sniper = any(cols.get(fld) is not None for fld in SNIPER_FIELDS)
    have_macro = any(cols.get(fld) is not None for fld in MACRO_FIELDS)
    have_ifib = any(cols.get(fld) is not None for fld in IFIB_FIELDS)
    # The Macro fib only runs on <=5m in Pine; a higher-TF export carries the columns but they are
    # never active. Only compare Macro if the export actually exercised it (px_macro_active hits 1).
    macro_col = cols.get("px_macro_active")
    macro_exercised = have_macro and macro_col is not None and any(_num(r.get(macro_col)) == 1.0 for r in rows)

    # Only compare fields the CSV carries; drop Macro fields on an export that never exercised it.
    compare_fields = [
        fld for fld in ALL_FIELDS
        if cols.get(fld) is not None and not (fld in MACRO_FIELDS and not macro_exercised)
    ]

    engine = StructureEngine(major_length=args.major_length)
    fib = StructureFib()
    sniper = SniperFib()
    macro = MacroFib()
    ifib = InternalFib()

    total = 0
    per_field_mismatch = {fld: 0 for fld in compare_fields}
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
        fib_ev = fib.update(h, l, snap)
        sniper_ev = sniper.update(h, l, snap)
        macro_ev = macro.update(i, h, l, c, snap)
        ifib_ev = ifib.update(i, h, l, snap)
        py = _python_row(fib_ev, sniper_ev, macro_ev, ifib_ev)
        total += 1

        if i < args.warmup:
            continue

        bar_mismatches = []
        for fld in compare_fields:
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
    parts = ["Structure"]
    if have_sniper:
        parts.append("Sniper")
    if macro_exercised:
        parts.append("Macro")
    if have_ifib:
        parts.append("Internal")
    scope = " + ".join(parts)
    notes = []
    if not have_sniper:
        notes.append("Sniper columns absent")
    if have_macro and not macro_exercised:
        notes.append("Macro present but never active — export on <=5m to check it")
    elif not have_macro:
        notes.append("Macro columns absent")
    if not have_ifib:
        notes.append("Internal fib columns absent")
    if notes:
        scope += "  (" + "; ".join(notes) + ")"
    print(f"\nCompared {total} bars from {path.name}  (major_length={args.major_length}, tol={args.tolerance})")
    print(f"Scope: {scope}")
    print("-" * 72)
    if not any(per_field_mismatch.values()):
        print(f"✓ FIB PARITY: every compared field matched on every bar. Python fibs == Pine source ({scope}).")
        return 0

    print("MISMATCHES BY FIELD:")
    for fld in compare_fields:
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
            print(f"      {fld:<20} python={pv!r:<12} pine={pinev!r}")
    print("-" * 72)
    print("Tip: fib mismatches confined to early bars = warmup (structure not yet converged, or a "
          "leg that began before the export window). Persistent mismatches after a clean run of "
          "bars = a real logic gap to fix against mpc_assistant.pine.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
