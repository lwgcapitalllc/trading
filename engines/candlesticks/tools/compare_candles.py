#!/usr/bin/env python3
"""
compare_candles.py — parity check: TradingView Pine export vs the Python candlestick engine.

Purpose
-------
Prove the Python engine in `candlesticks/` fires the same fifteen patterns, on the same bars, as the
source-of-truth `indicators/candle_sticks.pine`. It replays CandlestickEngine over the candles the
Pine build itself saw and diffs its per-bar detections against the `px_*` flag columns that build
plotted.

What is compared (every bar past --warmup)
------------------------------------------
  * one 0/1 column per pattern — `px_doji`, `px_bear_harami`, … `px_inv_hammer` — against whether
    that key appears in this bar's `ev.detected`.

That IS the whole decision stream: this source has no state machine, so a bar's fifteen booleans are
its entire output. There is nothing else to check and nothing that can be right "on average".

`px_lower` (`ta.lowest(10)[1]`) is read as a DIAGNOSTIC only and never fails the run: it is the one
intermediate `bullBelt` depends on, so when a belt mismatches this tool can say whether the two sides
disagreed about the ten-bar low or about the rule that reads it.

Config comes FROM the export
----------------------------
`cfg_trend` and `cfg_doji_size` are read out of the CSV and used to build the engine. The tool
REFUSES an export that lacks them rather than falling back to the Python defaults — a run configured
by a guess proves the two sides agree about a setting neither of them was necessarily using, which
is how a green gate ends up meaning nothing (see `indicators/CLAUDE.md`, the `execRunnerTrail` and
`eqExemptFvg` incidents).

Exercise check
--------------
A green run over a window where a pattern never fired says NOTHING about that pattern. The report
therefore prints a per-pattern hit count on BOTH sides and names every pattern that fired zero times,
because "agreed on all 20,000 bars" and "neither side ever entered this branch" look identical from
the exit code. Read that list before believing the gate.

Data lineup
-----------
Export ONE CSV from TradingView with `indicators/candle_sticks_export.pine` on the chart (chart menu
→ Export chart data). Each row carries the candle (fed to Python) and that bar's Pine flags, so both
sides come from one file and there is no data-source mismatch.

Warmup
------
Ten of the fifteen rules read `open[trend]`, and `bullBelt` reads a ten-bar low, so neither side can
fire them on the first bars of the export. Both sides are cold in the same way here (unlike the
stateful engines, this one carries no history in from before the window), so warmup should not be
needed — if it is, that is a finding rather than a nuisance.

Usage
-----
    python3 candlesticks/tools/compare_candles.py "path/to/export.csv"
    python3 candlesticks/tools/compare_candles.py export.csv --warmup 20

Exit 0 if every pattern column matches on every bar past warmup, 1 otherwise. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_ENGINES_ROOT = Path(__file__).resolve().parents[2]
if str(_ENGINES_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINES_ROOT))

from candlesticks import PATTERN_KEYS, CandlestickEngine

# logical pattern key -> the export column that carries it. Keys are the registry's, so a pattern
# added to the engine with no column here fails loudly below instead of quietly going unchecked.
PATTERN_COLUMNS = {
    "doji": "px_doji",
    "bearish_harami": "px_bear_harami",
    "bullish_harami": "px_bull_harami",
    "bearish_engulfing": "px_bear_eng",
    "bullish_engulfing": "px_bull_eng",
    "piercing_line": "px_piercing",
    "bullish_belt": "px_bull_belt",
    "bullish_kicker": "px_bull_kick",
    "bearish_kicker": "px_bear_kick",
    "hanging_man": "px_hanging_man",
    "evening_star": "px_evening_star",
    "morning_star": "px_morning_star",
    "shooting_star": "px_shooting_star",
    "hammer": "px_hammer",
    "inverted_hammer": "px_inv_hammer",
}

_missing_cols = [k for k in PATTERN_KEYS if k not in PATTERN_COLUMNS]
if _missing_cols:      # pragma: no cover - import-time guard
    raise SystemExit(
        f"ERROR: this harness has no export column for {_missing_cols}. A pattern with no column is "
        f"a pattern the gate silently never checks — add the plot to candle_sticks_export.pine and "
        f"the mapping here in the same commit."
    )

CFG_TREND = "cfg_trend"
CFG_DOJI = "cfg_doji_size"
DIAG_LOWER = "px_lower"

# ── Boundary ties ────────────────────────────────────────────────────────────────────
# Several of these rules compare two quantities that come out EXACTLY EQUAL in decimal on
# real price data, and every one of them is a strict/non-strict comparison where the tie
# decides the answer:
#
#   doji           |o-c| <= (h-l)*dojiSize     measured tie: 0.26 vs 0.26
#   invHammer      h-l   >  3*|o-c|            measured tie: 3.96 vs 3.96
#   shootingStar   h-max(o,c) >= 3*|o-c|       measured tie: 5.43 vs 5.43
#
# In exact arithmetic the answer is defined; in BINARY float it is not, because neither
# side is representable and the two implementations accumulate different last-bit error.
# So Pine and Python can legitimately land on opposite sides of a rule they both compute
# correctly. This is the same class of thing engines/vwap/ already carries a 1e-6 relative
# tolerance for.
#
# ⚠ IT IS NOT SWEPT UNDER A TOLERANCE, BECAUSE A TOLERANCE ON THE FLAG WOULD ALSO SWALLOW
# REAL LOGIC BUGS — a 0/1 column has no "close enough". Each mismatch is instead CLASSIFIED
# by asking whether the decision is stable: re-run the rule with every price in the window
# nudged by ±_TIE_EPS, one at a time, and see whether the answer flips. A decision that a
# 1e-6 nudge can flip was sitting on the boundary; a real rule difference is robust to it,
# because prices tick in whole cents and every threshold here is built from them.
_TIE_EPS = 1e-6            # absolute, on a ~4,000 instrument = 2.5e-10 relative, 1e-4 of a tick
_TIE_CLASSIFY_CAP = 500    # above this, stop classifying and SAY so (never silently)


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
                f"Make sure indicators/candle_sticks_export.pine is the build on the chart and that "
                f"you exported via 'Export chart data'."
            )
        return None

    cols = {k: find(k) for k in ("open", "high", "low", "close")}
    cols["time"] = find("time", required=False)
    for col in PATTERN_COLUMNS.values():
        cols[col] = find(col)
    cols[DIAG_LOWER] = find(DIAG_LOWER, required=False)
    # cfg_* are REQUIRED. See the module docstring: configuring the engine from a guess makes the
    # gate agree about a setting the Pine may not have been running.
    cols[CFG_TREND] = find(CFG_TREND)
    cols[CFG_DOJI] = find(CFG_DOJI)
    return cols


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


def _drop_forming_tail(rows, cols):
    """Trim TradingView's still-forming live bar, which exports with every plotted series blank.

    A trailing run of rows whose pattern columns are ALL empty is the live bar (and any bar the
    export cut short); a blank row in the MIDDLE is not, and is refused rather than skipped — only a
    trailing run can be a live bar, and quietly dropping an interior one would hide a real hole in
    the export. Same rule as compare_bos.py's `_drop_forming_tail`.
    """
    flag_cols = [cols[c] for c in PATTERN_COLUMNS.values()]

    def blank(row):
        return all(_num(row.get(c)) is None for c in flag_cols)

    end = len(rows)
    while end > 0 and blank(rows[end - 1]):
        end -= 1
    for i in range(end):
        if blank(rows[i]):
            raise SystemExit(
                f"ERROR: row {i} has no pattern values but is not at the end of the file. Only a "
                f"TRAILING blank run can be the still-forming live bar; a blank row in the middle "
                f"means the export is holed and the comparison would be meaningless."
            )
    dropped = len(rows) - end
    if dropped:
        print(f"note: dropped {dropped} trailing blank row(s) — TradingView's still-forming live bar.")
    return rows[:end]


def _read_config(rows, cols):
    """Read cfg_trend / cfg_doji_size off the export, and REFUSE if they disagree across bars."""
    trends = {_num(r[cols[CFG_TREND]]) for r in rows}
    dojis = {_num(r[cols[CFG_DOJI]]) for r in rows}
    trends.discard(None)
    dojis.discard(None)
    if len(trends) != 1 or len(dojis) != 1:
        raise SystemExit(
            f"ERROR: the config columns are not constant across the export "
            f"(cfg_trend={sorted(trends)}, cfg_doji_size={sorted(dojis)}). They are plain inputs and "
            f"cannot change mid-run, so this file did not come from one build at one setting."
        )
    return int(round(trends.pop())), dojis.pop()


def _fired_at(bars, idx, trend, doji_size, warm):
    """Replay a fresh engine over the `warm` bars ending at `idx` and return what fired there."""
    eng = CandlestickEngine(trend=trend, doji_size=doji_size)
    ev = None
    for j in range(max(0, idx - warm), idx + 1):
        ev = eng.update(j, *bars[j])
    return set(ev.keys) if ev else set()


def _is_boundary_tie(bars, idx, key, trend, doji_size):
    """Is this decision sitting on an exact boundary, i.e. can a 1e-6 nudge flip it?

    Nudges EVERY price of EVERY bar in the rule's own history window, one at a time, in both
    directions. Exhaustive rather than clever: a tie can live in the current bar, in bar [1] or
    [2], in `open[trend]`, or in the ten lows behind `ta.lowest(10)[1]`, and guessing which would
    be a way of classifying only the ties already thought of.

    Returns False when there is not enough history to replay the bar cleanly — an unclassifiable
    mismatch is reported as REAL, because the reassuring answer must not be the default.
    """
    warm = max(trend, 10) + 2
    if idx < warm:
        return False
    base = key in _fired_at(bars, idx, trend, doji_size, warm)
    for b in range(max(0, idx - warm), idx + 1):
        for f in range(4):
            for delta in (_TIE_EPS, -_TIE_EPS):
                nudged = list(bars)
                bar = list(nudged[b])
                bar[f] += delta
                nudged[b] = tuple(bar)
                if (key in _fired_at(nudged, idx, trend, doji_size, warm)) != base:
                    return True
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="CSV exported from TradingView with candle_sticks_export.pine on the chart")
    ap.add_argument("--warmup", type=int, default=0,
                    help="skip the first N bars in the report (still fed to the engine)")
    ap.add_argument("--max-report", type=int, default=30, help="how many mismatching bars to print")
    ap.add_argument("--strict-ties", action="store_true",
                    help="fail on boundary ties too (default: report them loudly, do not fail)")
    args = ap.parse_args(argv)

    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"ERROR: file not found: {path}")

    with open(path, newline="") as f:
        header = next(csv.reader(f))
    cols = _resolve_columns(header)
    rows = _drop_forming_tail(_load_rows(path, cols), cols)
    if not rows:
        raise SystemExit("ERROR: the export has no usable rows.")

    trend, doji_size = _read_config(rows, cols)
    eng = CandlestickEngine(trend=trend, doji_size=doji_size)

    total = 0
    py_hits = {k: 0 for k in PATTERN_KEYS}
    pine_hits = {k: 0 for k in PATTERN_KEYS}
    bars = []
    raw_mismatches = []          # (bar index, key, py_on, pine_on)

    for i, row in enumerate(rows):
        o = _num(row[cols["open"]])
        h = _num(row[cols["high"]])
        l = _num(row[cols["low"]])
        c = _num(row[cols["close"]])
        if None in (o, h, l, c):
            continue

        bars.append((o, h, l, c))
        ev = eng.update(i, o, h, l, c)
        fired = set(ev.keys)
        total += 1

        if i < args.warmup:
            continue
        for key in PATTERN_KEYS:
            pine_raw = _num(row[cols[PATTERN_COLUMNS[key]]])
            pine_on = bool(pine_raw) and int(round(pine_raw)) == 1
            py_on = key in fired
            py_hits[key] += int(py_on)
            pine_hits[key] += int(pine_on)
            if py_on != pine_on:
                raw_mismatches.append((i, key, py_on, pine_on))

    # ── Classify every mismatch: boundary tie, or a real rule difference? ──
    classified, ties, real = 0, [], []
    for (i, key, py_on, pine_on) in raw_mismatches:
        if classified >= _TIE_CLASSIFY_CAP:
            real.append((i, key, py_on, pine_on))       # unclassified counts as REAL, never as a tie
            continue
        classified += 1
        (ties if _is_boundary_tie(bars, i, key, trend, doji_size) else real).append(
            (i, key, py_on, pine_on))

    per_field_real = {k: 0 for k in PATTERN_KEYS}
    for (_, key, _, _) in real:
        per_field_real[key] += 1
    per_field_tie = {k: 0 for k in PATTERN_KEYS}
    for (_, key, _, _) in ties:
        per_field_tie[key] += 1

    compared = max(0, total - args.warmup)
    print(f"\nCompared {compared} bars from {path.name}  "
          f"(cfg_trend={trend}, cfg_doji_size={doji_size}, warmup={args.warmup})")
    print("-" * 78)

    # ── Exercise check. Print it on a PASS as well as a fail: the whole point is that a green run
    #    over a window a pattern never entered proves nothing about that pattern. ──
    print("HITS PER PATTERN (python / pine):")
    never = []
    for key in PATTERN_KEYS:
        print(f"  {key:<20} {py_hits[key]:>6} / {pine_hits[key]:<6}")
        if py_hits[key] == 0 and pine_hits[key] == 0:
            never.append(key)
    if never:
        print(f"\n⚠ NEVER FIRED ON EITHER SIDE — this run says NOTHING about: {', '.join(never)}")
        print("  A pattern that did not occur is not a pattern that was checked. Export a longer or "
              "different window, or read the gate as covering the rest only.")
    print("-" * 78)

    def _dump(label, items):
        print(f"{label} ({len(items)}):")
        for idx, key, py_on, pine_on in items[:args.max_report]:
            tval = rows[idx][cols["time"]] if cols.get("time") else ""
            print(f"  bar {idx:<7} {tval:<14} {key:<20} python={int(py_on)}  pine={int(pine_on)}")
        if len(items) > args.max_report:
            print(f"  … {len(items) - args.max_report} more not shown (raise --max-report)")

    if classified >= _TIE_CLASSIFY_CAP:
        print(f"⚠ Stopped classifying after {_TIE_CLASSIFY_CAP} mismatches; the remaining "
              f"{len(raw_mismatches) - _TIE_CLASSIFY_CAP} are counted as REAL, not as ties.")
        print("-" * 78)

    if ties:
        # Reported on a PASS as well as a fail. A tie is a fact about this export that a reader
        # needs, and burying it behind a green exit code is how it stops being one.
        print("BOUNDARY TIES — the two sides sit either side of an EXACTLY EQUAL comparison.")
        print("These are float representation, not a rule difference: a ±1e-6 nudge flips the")
        print("Python answer, i.e. the decision was on the line. See _TIE_EPS in this file.")
        for key in PATTERN_KEYS:
            if per_field_tie[key]:
                print(f"  {key:<20} {per_field_tie[key]} bar(s)")
        _dump("  ties", ties)
        print("-" * 78)

    if not real:
        verdict = "✓ CANDLESTICK PARITY: every pattern column matched on every bar."
        if ties:
            verdict = (f"✓ CANDLESTICK PARITY: no rule differences. "
                       f"{len(ties)} boundary tie(s) out of {compared * len(PATTERN_KEYS):,} "
                       f"comparisons, listed above.")
            if args.strict_ties:
                print("--strict-ties: failing on the boundary ties above.")
                return 1
        print(verdict + " Python engine == Pine source.")
        return 0

    print("REAL MISMATCHES BY PATTERN (a nudge does NOT flip these — a rule difference):")
    for key in PATTERN_KEYS:
        if per_field_real[key]:
            print(f"  {key:<20} {per_field_real[key]} bar(s)")
    print("-" * 78)
    last_real = real[-1][0]
    print(f"Last real mismatching bar: {last_real}  "
          f"(if all are early, re-run with --warmup {last_real + 1})")
    _dump("First real mismatching bar(s)", real)
    print("-" * 78)
    print("Tip: a `bullish_belt` mismatch is the one worth reading first — check px_lower in the "
          "CSV, which separates 'the two sides disagree about ta.lowest(10)[1]' from 'they disagree "
          "about the belt rule'. Mismatches confined to the first ~max(trend, 10) bars are the "
          "history guard; anything later is a real logic gap to fix against "
          "indicators/candle_sticks.pine.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
