#!/usr/bin/env python3
"""
compare_directional_trend.py — parity check: TradingView export vs the Python directional-trend engine.

Purpose
-------
Prove engines/directional_trend/ produces the same five JARVIS direction rows as mpc_jarvis.pine, on
real candles. Each bar's timestamp + OHLC is fed through DirectionalTrend and the snapshot is diffed
against the dt_* columns plotted by indicators/engines/directional_trend_export.pine.

What is compared (per bar, once both sides have a value)
--------------------------------------------------------
  * dt_w_state / dt_w_desc, dt_d_state / dt_d_desc — the weekly and daily bias.
  * dt_h4_dir / dt_h4_ev, dt_m15_dir / dt_m15_ev   — 4H and 15m structure + event.
  * dt_m1_dir / dt_m1_ev                            — only on a 1-minute export.

A bar where Python still says CANNOT KNOW (warm-up) is skipped and counted, never compared as
neutral. Every field must be compared on at least --min-bars bars, or the run FAILS: a gate that
compared nothing would otherwise pass.

NON-REPAINTING (the liquidity-engine decision, Aaron 2026-07-05)
----------------------------------------------------------------
Both sides read the higher timeframes' last CLOSED candle only; the export mirrors this with
`[1]` + lookahead_on. See the engine's docstring.

Warm-up
-------
TradingView's higher-timeframe series carry history from before the chart's first bar; Python starts
cold and throws its first partial period away. Structure converges once both sides have seen the
same swings, so the early bars can disagree for a reason that is not a defect. Use --warmup to skip
them; the tool prints the last mismatching bar to help pick it. ⚠ Report the warm-up you used next to
the verdict — a large one hides real disagreement.

Usage
-----
    python3 engines/directional_trend/tools/compare_directional_trend.py export.csv
    python3 engines/directional_trend/tools/compare_directional_trend.py export.csv --warmup 2000

Exit 0 if every compared field matches on every warm bar, 1 otherwise. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_ENGINES = Path(__file__).resolve().parents[2]
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

from directional_trend import DirectionalTrend  # noqa: E402
from gate_common import drop_live_final_bar  # noqa: E402

FIELDS = [
    "dt_w_state",
    "dt_w_desc",
    "dt_d_state",
    "dt_d_desc",
    "dt_h4_dir",
    "dt_h4_ev",
    "dt_m15_dir",
    "dt_m15_ev",
    "dt_m1_dir",
    "dt_m1_ev",
]
_SECONDS_CEILING = 10**11


def _num(s):
    s = (s or "").strip()
    if s == "" or s.lower() in ("na", "nan"):
        return None
    try:
        return int(round(float(s)))
    except ValueError:
        return None


def _to_ms(raw):
    raw = (raw or "").strip()
    if raw.lstrip("-").isdigit():
        v = int(raw)
        return v * 1000 if v < _SECONDS_CEILING else v
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _python_row(snap):
    def bias(r):
        return (None, None) if r is None else (r.direction, r.desc_code)

    def struct(r):
        return (None, None) if r is None else (r.direction, r.event)

    w, d = bias(snap.weekly), bias(snap.daily)
    h4, m15, m1 = struct(snap.h4), struct(snap.m15), struct(snap.m1)
    return dict(zip(FIELDS, (*w, *d, *h4, *m15, *m1)))


def _stamp(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("csv", type=Path)
    ap.add_argument(
        "--warmup", type=int, default=0, help="skip this many leading bars before comparing"
    )
    ap.add_argument(
        "--min-bars",
        type=int,
        default=200,
        help="each field must be compared on at least this many bars",
    )
    ap.add_argument("--show", type=int, default=10, help="print up to this many mismatches")
    args = ap.parse_args(argv)

    with open(args.csv, newline="") as f:
        reader = csv.DictReader(f)
        header = {h.lower().strip(): h for h in reader.fieldnames or []}
        rows = list(reader)
    for need in ("time", "open", "high", "low", "close"):
        if need not in header:
            raise SystemExit(f"ERROR: column {need!r} missing. Header: {list(header.values())}")
    missing = [fld for fld in FIELDS if fld not in header]
    if missing:
        raise SystemExit(
            f"ERROR: export lacks {missing} - was directional_trend_export.pine on the chart?"
        )
    rows = drop_live_final_bar(sorted(rows, key=lambda r: _to_ms(r[header["time"]])))

    times = [_to_ms(r[header["time"]]) for r in rows]
    step = Counter(b - a for a, b in zip(times, times[1:])).most_common(1)[0][0] // 60_000
    print(
        f"export: {len(rows)} bars at {step}m, {_stamp(times[0])} → {_stamp(times[-1])}; warm-up {args.warmup}"
    )
    eng = DirectionalTrend(step)

    compared, cold, bad = Counter(), Counter(), Counter()
    shown, last_bad = 0, None
    for i, (r, ts) in enumerate(zip(rows, times)):
        snap = eng.update(
            ts,
            float(r[header["open"]]),
            float(r[header["high"]]),
            float(r[header["low"]]),
            float(r[header["close"]]),
        )
        if i < args.warmup:
            continue
        py = _python_row(snap)
        for fld in FIELDS:
            pv, tv = py[fld], _num(r[header[fld]])
            if tv is None:
                continue
            if pv is None:
                cold[fld] += 1
                continue
            compared[fld] += 1
            if pv != tv:
                bad[fld] += 1
                last_bad = (i, ts)
                if shown < args.show:
                    print(f"  MISMATCH bar {i} {_stamp(ts)} {fld}: python {pv}  pine {tv}")
                    shown += 1

    print(f"\n{'field':<12}{'compared':>10}{'mismatch':>10}{'cold (py warm-up)':>20}")
    failed = False
    for fld in FIELDS:
        if step != 1 and fld.startswith("dt_m1_"):
            print(f"{fld:<12}{'—':>10}{'—':>10}{'n/a: needs a 1m export':>20}")
            continue
        flag = ""
        if compared[fld] < args.min_bars:
            flag, failed = f"  🔴 compared on fewer than {args.min_bars} bars", True
        elif bad[fld]:
            failed = True
        print(f"{fld:<12}{compared[fld]:>10}{bad[fld]:>10}{cold[fld]:>20}{flag}")
    if last_bad:
        print(
            f"\nlast mismatch at bar {last_bad[0]} ({_stamp(last_bad[1])}) - a --warmup past it would hide it"
        )
    print("\nPASS" if not failed else "\nFAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
