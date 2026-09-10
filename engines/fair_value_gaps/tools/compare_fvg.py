#!/usr/bin/env python3
"""
compare_fvg.py — parity check: TradingView Pine export vs Python fair-value-gap engine.

Purpose
-------
Prove the Python engine in fair_value_gaps/ produces the same gaps as the source-of-truth FVG block
in mpc_jarvis.pine, on real candles. It runs FairValueGapEngine on the same candles the Pine build
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
columns existed; their defaults are the engine's, read from it (mpc's sub-15m row).

Note the minimum-gap floor is timeframe-split in mpc and in the export (0.0 below 15m, higher at
15m and above), so `cfg_fvg_thresh` differs between a 5m and a 15m export of the same build. That is
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
from fair_value_gaps import engine as _fvg  # the defaults, typed once in the engine
from gate_common import drop_live_final_bar  # noqa: E402

# 🔴 THE EXPORT COMES IN TWO SHAPES AND THE TOOL MUST NOT PRETEND THEY COVER THE SAME THING.
#
#   MODERN  (2026-09-10 onward)  18 slots per array + a packed direction mask + WHOLE-ARRAY
#           aggregates. The aggregates are what make a gap list LONGER than the slots visible:
#           they run to array.size(), so a gap in slot 19 still moves a compared number.
#   LEGACY  10 slots + one direction column each. No aggregates, so ANY gap past slot 10 is
#           invisible — and that is not hypothetical. MEASURED on the committed golden export:
#           the live list reaches 17 and exceeds 10 on 52.2% of bars, every one of which the diff
#           reported green while never looking at gaps 11 and up.
#
# ⚠ The old guard here asked whether `cfg_fvg_maxcount` exceeded the slot count. That question
#   stopped meaning anything on 2026-08-03, when a gap became able to be EXEMPT from the cap — the
#   live total is bounded by the EQ engine from that day on, not by the input, so the guard was
#   checking a number that no longer bounds the thing it was protecting. It passed happily on an
#   export where half the bars were under-checked. **A guard whose premise has expired is worse
#   than no guard: it reads as coverage.**
_MODERN_SLOTS = 18
_LEGACY_SLOTS = 10

_AGG_FIELDS = ["px_fvg_topsum", "px_fvg_botsum"]           # tolerance-compared, whole array
_COUNT_FIELDS = ["px_fvg_count", "px_fvg_formed", "px_fvg_mit"]


def _field_groups(modern):
    """The comparable columns for this export's shape, plus how each is compared."""
    slots = _MODERN_SLOTS if modern else _LEGACY_SLOTS
    tops = [f"px_fvg_top_{k}" for k in range(1, slots + 1)]
    bots = [f"px_fvg_bot_{k}" for k in range(1, slots + 1)]
    price = tops + bots + (_AGG_FIELDS if modern else [])
    if modern:
        # One packed column: bit k set when slot k+1 is bullish. Exact in float64 to 2**18.
        state = ["px_fvg_bullmask", "px_fvg_bulltotal"] + _COUNT_FIELDS
        bull = []
    else:
        bull = [f"px_fvg_bull_{k}" for k in range(1, slots + 1)]
        state = bull + _COUNT_FIELDS
    return {
        "slots": slots,
        "tops": tops,
        "bots": bots,
        "price": price,
        "bull": bull,
        "state": state,
        "all": price + state,
    }


# Filled in by main() once the export's shape is known; the comparison helpers read them.
GROUPS = _field_groups(modern=True)


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
    for f in GROUPS["all"]:
        cols[f] = find(f)
    # The entry-band columns exist only in fvg_zone_export.pine. Absent = the plain harness, and the
    # band exemption is then OFF on both sides rather than guessed at.
    for f in ("px_fvgzone_lo", "px_fvgzone_hi", "px_fvgzone_dir",
              "px_fibband_lo", "px_fibband_hi", "px_fibband_dir"):
        cols[f] = find(f, required=False)
    return cols


def _python_row(ev):
    """Map the Python FVG events to each px_fvg_* column value, in this export's shape."""
    row = {}
    for slot, (tf, bf) in enumerate(zip(GROUPS["tops"], GROUPS["bots"])):
        g = ev.active[slot] if slot < len(ev.active) else None
        row[tf] = g.top if g else None
        row[bf] = g.bottom if g else None
    if GROUPS["bull"]:
        for slot, bull in enumerate(GROUPS["bull"]):
            g = ev.active[slot] if slot < len(ev.active) else None
            row[bull] = (1.0 if g.is_bullish else 0.0) if g else None
    else:
        mask = 0.0
        for slot, g in enumerate(ev.active[: GROUPS["slots"]]):
            if g.is_bullish:
                mask += 2.0 ** slot
        row["px_fvg_bullmask"] = mask
        row["px_fvg_bulltotal"] = float(sum(1 for g in ev.active if g.is_bullish))
        # Whole-array sums: the only thing that can see a gap past the last plotted slot.
        row["px_fvg_topsum"] = float(sum(g.top for g in ev.active))
        row["px_fvg_botsum"] = float(sum(g.bottom for g in ev.active))
    row["px_fvg_count"] = float(len(ev.active))
    row["px_fvg_formed"] = float(len(ev.formed))
    row["px_fvg_mit"] = float(len(ev.mitigated))
    return row


def _values_match(field, py_val, pine_val, tol, agg_tol=None):
    if field in _AGG_FIELDS:
        # A sum of up to ~18 four-figure prices. Compared on its own tolerance because it is an
        # ACCUMULATION - the per-price tolerance is the wrong scale for it, and tightening a sum to
        # 1e-6 makes the gate go red on the CSV's own formatting rather than on the engine.
        if py_val is None and pine_val is None:
            return True
        if py_val is None or pine_val is None:
            return False
        return abs(py_val - pine_val) <= (agg_tol if agg_tol is not None else tol)
    if field in GROUPS["price"]:
        if py_val is None and pine_val is None:
            return True
        if py_val is None or pine_val is None:
            return False
        return abs(py_val - pine_val) <= tol
    # state fields. bull slots are na when the slot is empty (both sides None -> match); counts /
    # pulses have no na — a missing Pine cell is 0.
    if field in GROUPS["bull"]:
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
                        ("eq_max", "cfg_eq_max"), ("eq_exempt", "cfg_eq_exempt"),
                        ("zone_exempt", "cfg_fvg_exemptzone")):
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
    ap.add_argument("--max-count", type=int, default=_fvg.DEFAULT_MAX_COUNT,
                    help="fallback if the export has no cfg_fvg_maxcount column (default %(default)s)")
    ap.add_argument("--threshold-pct", type=float, default=_fvg.DEFAULT_THRESHOLD_PCT,
                    help="fallback if the export has no cfg_fvg_thresh column (default %(default)s)")
    ap.add_argument("--require-close", action="store_true", default=_fvg.DEFAULT_REQUIRE_CLOSE,
                    help="fallback if the export has no cfg_fvg_requireclose column (default %(default)s)")
    ap.add_argument("--tolerance", type=float, default=1e-6, help="abs tolerance for price fields (default 1e-6)")
    ap.add_argument("--agg-tolerance", type=float, default=1e-3,
                    help="abs tolerance for the whole-array SUM columns (default 1e-3) - a sum of "
                         "~18 four-figure prices needs a different scale from one price")
    ap.add_argument("--max-report", type=int, default=30, help="how many mismatching bars to print")
    ap.add_argument("--warmup", type=int, default=0, help="skip the first N bars in the report (still fed to the engine)")
    ap.add_argument("--include-last-bar", action="store_true",
                    help="compare the export's FINAL row too. Off by default because that row is "
                         "TradingView's live, still-forming bar - see the note in main()")
    args = ap.parse_args(argv)

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"ERROR: file not found: {path}")

    with open(path, newline="") as f:
        header = next(csv.reader(f))

    # Which harness produced this file? Decided from the COLUMNS, never from a flag - an export
    # cannot be argued into a shape it does not have.
    global GROUPS
    modern = any(h.strip().lower().endswith("px_fvg_bullmask") for h in header)
    GROUPS = _field_groups(modern=modern)

    cols = _resolve_columns(header)
    rows = _load_rows(path, cols)

    # The live final bar is dropped by the shared rule - see engines/gate_common.py for why it
    # cannot be decided from the clock, and why it is not the same test as compare_candles.py's
    # trailing-blank trim. It fired HERE first: one bar in 20,188, on both harnesses, identically.
    dropped_last = not args.include_last_bar and len(rows) > 1
    if dropped_last:
        rows = drop_live_final_bar(rows)

    # The export carries its own settings as cfg_* columns (constant every bar) so parity survives any
    # Pine input tweak — never a hardcoded guess. Read them when present; else fall back to the CLI.
    cfg = _read_cfg(header, rows)
    max_count = int(cfg["maxcount"]) if cfg.get("maxcount") is not None else args.max_count
    threshold_pct = cfg["thresh"] if cfg.get("thresh") is not None else args.threshold_pct
    require_close = bool(round(cfg["requireclose"])) if cfg.get("requireclose") is not None else args.require_close
    cfg_src = "export cfg_* columns" if cfg else "CLI args (no cfg_* columns in export)"


    # EQ coupling (mpc eqExemptFvg): when the export carries the cfg_eq_* columns AND the exemption is
    # on, run the EQ engine alongside and feed its active levels + tolerance into the FVG cap each bar.
    eq_exempt = cfg.get("eq_exempt") is not None and bool(round(cfg["eq_exempt"]))
    eq = None
    if eq_exempt:
        from equal_highs_lows import EqualHighsLowsEngine
        # 🔴 An export that turns the exemption ON must say which levels it drew. This fell back to
        # 2 / 0.1 / 6 - the equal-level settings before 2026-09-09 - for a file recording the switch
        # but not the settings, which no harness here has ever written: an eighth copy of three
        # numbers, still on the old values a day after the other seven moved. A guess about what an
        # export ran is the one thing a gate may not make, so it refuses.
        missing = [k for k in ("eq_pivotlen", "eq_atrmult", "eq_max") if cfg.get(k) is None]
        if missing:
            raise SystemExit(
                "ERROR: the export turns the EQ exemption ON but carries no "
                + ", ".join("cfg_" + k for k in missing)
                + " - re-export off the current harness."
            )
        eq = EqualHighsLowsEngine(
            pivot_len=int(cfg["eq_pivotlen"]),
            atr_mult=cfg["eq_atrmult"],
            max_levels=int(cfg["eq_max"]),
        )
    eq_note = f", EQ-exempt ON (pivot={int(cfg['eq_pivotlen'])}, mult={cfg['eq_atrmult']})" if eq_exempt else ""

    # ── The fib ENTRY-BAND exemption (mpc fvgExemptZone). Only fvg_zone_export.pine can carry it:
    #    the band is the live fib's 0.382-0.886, recomputed every bar, so it is not an input and the
    #    plain harness has no fib in it. Absent columns = exemption OFF on both sides, which is what
    #    every consumer of this engine runs today. ──
    zone_cols_present = cols.get("px_fvgzone_dir") is not None
    zone_exempt = zone_cols_present and (
        cfg.get("zone_exempt") is None or bool(round(cfg["zone_exempt"]))
    )
    zone_note = ", ENTRY-BAND exemption ON" if zone_exempt else ""

    fvg = FairValueGapEngine(max_count=max_count, threshold_pct=threshold_pct, require_close=require_close)

    # ── COVERAGE, measured off this export rather than assumed. ──
    # A legacy export has no whole-array aggregate, so every gap past the last plotted slot is
    # invisible to the diff. Count those bars and SAY SO on every run: a green that covered 48% of
    # the bars must not print the same line as one that covered all of them.
    blind_bars = 0
    if not modern:
        ccol = cols["px_fvg_count"]
        for i, r in enumerate(rows):
            if i < args.warmup:
                continue
            v = _num(r.get(ccol))
            if v is not None and v > GROUPS["slots"]:
                blind_bars += 1

    total = 0
    per_field_mismatch = {fld: 0 for fld in GROUPS["all"]}
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
        # The band the Pine cap ACTUALLY CONSUMED on this bar. Exported as the value it held
        # BEFORE the fib block moved it, so no off-by-one can hide inside this tool - the lag is
        # checked separately below against the published band.
        zone_lo = zone_hi = None
        zone_dir = 0
        if zone_exempt:
            zone_lo = _num(row[cols["px_fvgzone_lo"]])
            zone_hi = _num(row[cols["px_fvgzone_hi"]])
            zd = _num(row[cols["px_fvgzone_dir"]])
            zone_dir = int(round(zd)) if zd is not None else 0
        ev = fvg.update(i, o, h, l, c, eq_levels=eq_levels, eq_tol=eq_tol,
                        zone_lo=zone_lo, zone_hi=zone_hi, zone_dir=zone_dir)
        py = _python_row(ev)
        total += 1

        if i < args.warmup:
            continue

        bar_mismatches = []
        for fld in GROUPS["all"]:
            pine_val = _num(row[cols[fld]])
            if not _values_match(fld, py[fld], pine_val, args.tolerance, args.agg_tolerance):
                per_field_mismatch[fld] += 1
                bar_mismatches.append((fld, py[fld], pine_val))

        if bar_mismatches:
            last_mismatch_bar = i
            if len(detailed) < args.max_report:
                tval = row[cols["time"]] if cols.get("time") else ""
                detailed.append((i, tval, bar_mismatches))

    # ── The one-bar lag, checked rather than asserted in a comment ──
    # In mpc the FVG block runs ~800 lines ABOVE the fib block, so the cap can only ever see the
    # PREVIOUS bar's band. That is deliberate there and it is the single easiest thing for a port to
    # get wrong, because both readings look reasonable and only one matches the chart. The zone
    # harness exports the band twice - as CONSUMED and as PUBLISHED - so the relation is testable:
    # consumed[i] must equal published[i-1] on every bar.
    lag_note = ""
    if zone_exempt and cols.get("px_fibband_dir") is not None:
        bad_lag = 0
        for i in range(1, len(rows)):
            for used, pub in (("px_fvgzone_lo", "px_fibband_lo"),
                              ("px_fvgzone_hi", "px_fibband_hi"),
                              ("px_fvgzone_dir", "px_fibband_dir")):
                a = _num(rows[i][cols[used]])
                b = _num(rows[i - 1][cols[pub]])
                if a is None and b is None:
                    continue
                if a is None or b is None or abs(a - b) > args.tolerance:
                    bad_lag += 1
                    break
        if bad_lag:
            lag_note = (f"\n🔴 LAG SELF-TEST FAILED on {bad_lag} bar(s): the band the cap consumed is "
                        f"not the previous bar's published band.\n   Either the FVG block moved BELOW "
                        f"the fib block in fvg_zone_export.pine, or the export is stale. The harness "
                        f"is wrong before the engine is.")
        else:
            lag_note = "\n✓ LAG SELF-TEST: the cap consumed the PREVIOUS bar's band on every bar (mpc's own ordering)."

    # ── Report ──
    shape = f"{GROUPS['slots']} slots" + (" + whole-array sums" if modern else ", NO whole-array sums")
    print(f"\nCompared {total} bars from {path.name}  (max_count={max_count}, threshold_pct={threshold_pct}, "
          f"require_close={require_close}{eq_note}{zone_note}, tol={args.tolerance})  [config from {cfg_src}]")
    print(f"Export shape: {shape}")
    if not modern:
        pct = (blind_bars / max(total - args.warmup, 1)) * 100
        print(f"🔴 PARTIAL COVERAGE: this is a LEGACY export with no whole-array aggregate, so any gap "
              f"past slot {GROUPS['slots']} is invisible to this diff.")
        print(f"   {blind_bars} of {max(total - args.warmup, 1)} compared bars ({pct:.1f}%) hold a longer "
              f"list than that. Re-export from the current indicators/engines/fvg_export.pine to close it.")
    if lag_note:
        print(lag_note.lstrip("\n"))
    print("-" * 72)
    if not any(per_field_mismatch.values()):
        if lag_note.startswith("\n🔴"):
            return 1
        print("✓ FVG PARITY: every compared field matched on every bar. Python FVG engine == Pine source.")
        if not modern:
            print("⚠ ...on the columns this export carries. See the PARTIAL COVERAGE line above.")
        return 0

    print("MISMATCHES BY FIELD:")
    for fld in GROUPS["all"]:
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
          "run of bars = a real logic gap to fix against mpc_jarvis.pine.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
