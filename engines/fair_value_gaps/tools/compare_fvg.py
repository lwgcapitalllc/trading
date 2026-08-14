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
  * The active gap arrays, slot by slot (slot 1 = oldest): px_fvg_top_1..10 / px_fvg_bot_1..10 against
    active[k].top / .bottom, and px_fvg_bull_1..10 against active[k].is_bullish (1/0). Matching the
    ordered arrays every bar proves formation, mitigation AND FIFO eviction all at once.
  * px_fvg_count against len(active).
  * px_fvg_formed / px_fvg_mit against the count of gaps formed / mitigated this bar (localisers).

Data lineup
-----------
Export ONE CSV from TradingView with indicators/engines/fvg_export.pine on the chart (chart menu → Export
chart data). Each row carries the candle (fed to Python) and the Pine FVG engine's outputs. Both
sides come from the same file, so there is no data-source mismatch. The export's `cfg_fvg_*` columns
carry the Pine's own settings and are read automatically — run with NO config flags. The
--max-count / --threshold-pct / --require-close flags are FALLBACKS for an export taken before those
columns existed; their defaults are the mpc defaults (8 / 0.0 sub-15m / off).

Note the minimum-gap floor is timeframe-split in mpc and in the export (0.0 below 15m, 0.04 at 15m
and above), so `cfg_fvg_thresh` differs between a 5m and a 15m export of the same build. That is
correct, not drift — the column carries whatever the chart actually ran.

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

# fvg_export.pine plots this many slots per array, and its fvgMaxCount input is capped to match.
# It used to be 6 while the cap was 8, so the two newest gaps were live in Pine and never compared.
# If you widen the export, widen this in the SAME commit — the guard below refuses the mismatch
# rather than reporting a green that only covered part of the array.
_MAX_SLOTS = 10

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
                f"Make sure indicators/engines/fvg_export.pine is the build on the chart and that you "
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


def _read_cfg(header, rows):
    """Read the export's cfg_fvg_* settings (thresh / maxcount / requireclose) from the first data row.

    These plot columns are constant every bar, so one read is enough. Returns {} if the export carries
    no cfg columns (an older export) — the caller then falls back to CLI args. Matches column names by
    endswith so the TradingView-prefixed header ("Equal... : cfg_fvg_thresh") still resolves.
    """
    norm = {h.strip().lower(): h for h in header}

    def find(suffix):
        for low, orig in norm.items():
            if low.endswith(suffix):
                return orig
        return None

    out = {}
    for key, suffix in (("thresh", "cfg_fvg_thresh"), ("maxcount", "cfg_fvg_maxcount"),
                        ("requireclose", "cfg_fvg_requireclose"),
                        ("eq_pivotlen", "cfg_eq_pivotlen"), ("eq_atrmult", "cfg_eq_atrmult"),
                        ("eq_max", "cfg_eq_max"), ("eq_exempt", "cfg_eq_exempt")):
        col = find(suffix)
        if col is None:
            continue
        for r in rows:
            v = _num(r.get(col))
            if v is not None:
                out[key] = v
                break
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="CSV exported from TradingView with fvg_export.pine on the chart")
    ap.add_argument("--max-count", type=int, default=8, help="fallback if the export has no cfg_fvg_maxcount column (Pine default 8)")
    ap.add_argument("--threshold-pct", type=float, default=0.0, help="fallback if the export has no cfg_fvg_thresh column (Pine sub-15m default 0.0)")
    ap.add_argument("--require-close", action="store_true", help="fallback if the export has no cfg_fvg_requireclose column (Pine default off)")
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

    # The export carries its own settings as cfg_* columns (constant every bar) so parity survives any
    # Pine input tweak — never a hardcoded guess. Read them when present; else fall back to the CLI.
    cfg = _read_cfg(header, rows)
    max_count = int(cfg["maxcount"]) if cfg.get("maxcount") is not None else args.max_count
    threshold_pct = cfg["thresh"] if cfg.get("thresh") is not None else args.threshold_pct
    require_close = bool(round(cfg["requireclose"])) if cfg.get("requireclose") is not None else args.require_close
    cfg_src = "export cfg_* columns" if cfg else "CLI args (no cfg_* columns in export)"

    # A cap above the number of plotted slots means the export cannot describe its own state: gaps
    # past slot _MAX_SLOTS would be live in Pine and invisible here, so a green would be partial.
    if max_count > _MAX_SLOTS:
        raise SystemExit(
            f"ERROR: the export ran with fvgMaxCount={max_count} but fvg_export.pine plots only "
            f"{_MAX_SLOTS} slots per array, so gaps {_MAX_SLOTS + 1}..{max_count} are never exported "
            f"and could not be compared.\nWiden the px_fvg_top_/bot_/bull_ plots in "
            f"indicators/engines/fvg_export.pine and _MAX_SLOTS here to match, then re-export."
        )

    # EQ coupling (mpc eqExemptFvg): when the export carries the cfg_eq_* columns AND the exemption is
    # on, run the EQ engine alongside and feed its active levels + tolerance into the FVG cap each bar.
    eq_exempt = cfg.get("eq_exempt") is not None and bool(round(cfg["eq_exempt"]))
    eq = None
    if eq_exempt:
        from equal_highs_lows import EqualHighsLowsEngine
        eq = EqualHighsLowsEngine(
            pivot_len=int(cfg.get("eq_pivotlen") or 2),
            atr_mult=cfg.get("eq_atrmult") if cfg.get("eq_atrmult") is not None else 0.1,
            max_levels=int(cfg.get("eq_max") or 6),
        )
    eq_note = f", EQ-exempt ON (pivot={int(cfg.get('eq_pivotlen') or 2)}, mult={cfg.get('eq_atrmult')})" if eq_exempt else ""

    fvg = FairValueGapEngine(max_count=max_count, threshold_pct=threshold_pct, require_close=require_close)

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

        # Run EQ BEFORE FVG (the mpc order) and pass its post-update levels + tolerance into the cap.
        eq_levels = None
        eq_tol = 0.0
        if eq is not None:
            eq_ev = eq.update(i, h, l, c)
            eq_levels = eq_ev.active_eqh + eq_ev.active_eql
            eq_tol = eq_ev.tolerance
        ev = fvg.update(i, o, h, l, c, eq_levels=eq_levels, eq_tol=eq_tol)
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
    print(f"\nCompared {total} bars from {path.name}  (max_count={max_count}, threshold_pct={threshold_pct}, "
          f"require_close={require_close}{eq_note}, tol={args.tolerance})  [config from {cfg_src}]")
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
