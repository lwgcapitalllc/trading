#!/usr/bin/env python3
"""nogap_ishift_audit.py — do the no-gap setups pay if a 1-minute INTERNAL shift is the entry?

Aaron's question (2026-09-15), after a live LONG died as "No FVG in zone": *"when price is in the
tradable zone and there is no fair-value gap, the last confirmation available is a 1-minute
internal shift of structure in the direction of the trade. If it prints, that's the entry. I need
you to measure that."*

The population is `miss_audit.py`'s code 3 — every confluence present, price tagged the
0.5-0.886 band, no gap to rest on — collected by the SAME replay `nogap_scalp_audit.py` uses, so
the two tools measure the same setups (rule 11). For each one:

    WATCH    from the open of the 15m bar that tagged the band to the close of the bar it died
    TRIGGER  the first 1m bar whose internal change of character points the trade's way AND
             closes inside the 0.5-0.886 band
    ENTRY    that 1m bar's close
    STOP     the 0.886 fib — the bot's structural stop (Aaron, 2026-09-15; the tight stop comes
             later and is BLOCKED, see below)
    VOID     price closing through the 0.886 before any trigger kills the watch — no trade

The BASELINE is the same setups entered the way every earlier audit did it — a limit at the 0.618
filled on the same 1m tape — and walked by the SAME exit code. The difference between the two
rows is the whole answer: does the print SELECT winners, or is it a later entry on a losing pool?

⚠ **A SCREEN, NOT A PORTFOLIO.** Each setup is walked alone with no position slot. The report
counts triggers that land while a shipped trade is open, because with one slot those do not add
to the book, they queue in front of it (Run 12).
⚠ **Exits are a fixed-R grid plus a 48h mark, not the runner's ladder.** The runner cannot be
replayed on an entry the strategy has no code for. The best-excursion column is exit-free and is
the number to read first.
⚠ **The internal shift has no Pine counterpart**, so no parity gate covers it — every figure here
is a lab finding.
⚠ **The bear internal shift reports the WRONG broken level about 22 times in 25**
(`strategies/python/sos_fade/CLAUDE.md`). Only the fact that it fired is read here, which is
unaffected; a stop under the shift leg is NOT measurable until that is fixed in the engine.
⚠ **Both frames are read from one broker's cache** (`--broker-dir`), never mixed.

Usage:
    python3 backtest/tools/nogap_ishift_audit.py
    python3 backtest/tools/nogap_ishift_audit.py --start 2020-01-01 --end 2026-08-06
"""

from __future__ import annotations

import argparse
import sys
import time as _time
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.tools.nogap_scalp_audit import (  # noqa: E402
    _COST_PRICE,
    _intrabar_targets_first,
    _rollovers_between,
    _swap_price_per_night,
    collect,
)

_TARGETS = (0.5, 1.0, 1.5, 2.0, 3.0, 5.0)
_MIN_MS = 60_000
_M15_MS = 15 * _MIN_MS


def _load(cache_dir: Path, symbol: str, tf: str, start: str, end: str):
    from backtest.data.cache import BarCache

    df = BarCache(cache_dir).load(symbol, tf)
    return df.loc[start:end]


class Tape1m:
    def __init__(self, df):
        self.o = df["open"].to_numpy()
        self.h = df["high"].to_numpy()
        self.l = df["low"].to_numpy()
        self.c = df["close"].to_numpy()
        self.t = df.index.values.astype("datetime64[ms]").astype("int64")
        self.n = len(self.o)


def internal_shifts(tape: Tape1m, major_length: int):
    """One continuous pass, so every setup sees a fully warmed engine. `+1`/`-1`/`0` per bar."""
    from strategies.python.sos_fade.secondary import InternalShift1m

    feed = InternalShift1m(major_length=major_length)
    out = np.zeros(tape.n, dtype=np.int8)
    o, h, l, c = tape.o, tape.h, tape.l, tape.c
    for i in range(tape.n):
        s = feed.update(i, o[i], h[i], l[i], c[i])
        if s.new_bull:
            out[i] = 1
        elif s.new_bear:
            out[i] = -1
    return out


def _in_band(px, a, b):
    return min(a, b) <= px <= max(a, b)


def trigger(tape, shifts, s):
    """`(idx, entry, stop)`, `"void"` or None. Scan runs zone-bar open -> death-bar close."""
    lo = np.searchsorted(tape.t, s.time_ms, "left")
    hi = np.searchsorted(tape.t, _death_ms(s), "left")
    half, stop = s.level(0.5), s.level(0.886)
    d = s.dir
    for i in range(lo, min(hi, tape.n)):
        if (tape.c[i] - stop) * d <= 0:
            return "void"
        if shifts[i] == d and _in_band(tape.c[i], half, stop):
            return i, float(tape.c[i]), stop
    return None


def limit_fill(tape, s, ratio=0.618):
    lo = np.searchsorted(tape.t, s.time_ms, "left")
    hi = np.searchsorted(tape.t, _death_ms(s), "left")
    e, stop = s.level(ratio), s.level(0.886)
    for i in range(lo, min(hi, tape.n)):
        if (s.dir > 0 and tape.l[i] <= e) or (s.dir < 0 and tape.h[i] >= e):
            return i, e, stop
    return None


_DEATH: dict = {}


def _death_ms(s):
    return _DEATH[id(s)]


def walk(tape, d, i0, entry, stop, target_r, horizon_min):
    """Net R of one trade. Exits are live from the bar AFTER the entry bar (one-bar delay)."""
    risk = abs(entry - stop)
    tgt = None if target_r is None else entry + d * target_r * risk
    end = min(i0 + horizon_min, tape.n - 1)
    mfe = 0.0
    exit_px, exit_i = None, end
    for i in range(i0 + 1, end + 1):
        hit_s = (tape.l[i] <= stop) if d > 0 else (tape.h[i] >= stop)
        hit_t = tgt is not None and ((tape.h[i] >= tgt) if d > 0 else (tape.l[i] <= tgt))
        if hit_s and hit_t:
            up_first = _intrabar_targets_first(tape.o[i], tape.h[i], tape.l[i])
            fav_first = up_first if d > 0 else not up_first
            exit_px = tgt if fav_first else stop
        elif hit_t:
            exit_px = tgt
        elif hit_s:
            exit_px = stop
        if exit_px is not None:
            exit_i = i
            if exit_px == tgt:
                mfe = max(mfe, target_r)
            break
        fav = (tape.h[i] - entry) if d > 0 else (entry - tape.l[i])
        mfe = max(mfe, fav / risk)
    if exit_px is None:
        exit_px = tape.c[end]
    gross = (exit_px - entry) * d / risk
    nights = _rollovers_between(int(tape.t[i0]), int(tape.t[exit_i]))
    net = gross - _COST_PRICE / risk + nights * _swap_price_per_night(d) / risk
    return net, mfe, exit_px == stop


def _row(label, trades, tape, horizon):
    n = len(trades)
    if not n:
        print(f"  {label:<34} no trades")
        return
    mfes = [walk(tape, d, i, e, st, None, horizon)[1] for d, i, e, st in trades]
    risks = [abs(e - st) for d, i, e, st in trades]
    print(
        f"  {label:<34} n={n:<4} median stop ${np.median(risks):6.2f}   "
        f"best reach before stop: median {np.median(mfes):.2f}R  "
        f">=1R {sum(m >= 1 for m in mfes) / n:5.1%}  >=2R {sum(m >= 2 for m in mfes) / n:5.1%}"
    )
    cells = []
    for tr in (*_TARGETS, None):
        rs = [walk(tape, d, i, e, st, tr, horizon)[0] for d, i, e, st in trades]
        name = "48h mark" if tr is None else f"{tr:g}R"
        cells.append(f"{name} {sum(rs):+7.1f}R ({np.mean(rs):+.2f})")
    for k in range(0, len(cells), 4):
        print("      " + "   ".join(cells[k : k + 4]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2026-08-06")
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--broker-dir", default=str(_ROOT / "backtest/cache/VantageMarkets_Demo"))
    ap.add_argument(
        "--major-length",
        type=int,
        default=15,
        help="1m structure pivot length — the feed's own default",
    )
    ap.add_argument("--horizon-min", type=int, default=48 * 60)
    ap.add_argument("--min-stop-pct", type=float, default=0.08)
    args = ap.parse_args(argv)
    cdir = Path(args.broker_dir)

    df15 = _load(cdir, args.symbol, "M15", args.start, args.end)
    df1 = _load(cdir, args.symbol, "M1", args.start, args.end)
    print(f"15m {len(df15):,} bars {df15.index[0]} -> {df15.index[-1]}")
    print(f" 1m {len(df1):,} bars {df1.index[0]} -> {df1.index[-1]}")
    per_day = df1.groupby(df1.index.year).size() / df15.groupby(df15.index.year).size() / 15
    print(
        " 1m density vs 15m (1.00 = complete): "
        + "  ".join(f"{y} {v:.2f}" for y, v in per_day.items()),
        flush=True,
    )

    setups, shipped, no_geo, _ = collect(df15, args.warmup, {})
    t15 = df15.index.values.astype("datetime64[ms]").astype("int64")
    for s in setups:
        _DEATH[id(s)] = int(t15[min(s.d_idx, len(t15) - 1)]) + _M15_MS
    print(f"no-gap setups: {len(setups)}  (no geometry: {no_geo})   shipped trades: {len(shipped)}")

    tape = Tape1m(df1)
    t0 = _time.time()
    shifts = internal_shifts(tape, args.major_length)
    print(
        f"1m internal shifts: {int((shifts != 0).sum()):,} over {tape.n:,} bars "
        f"({_time.time() - t0:.0f}s)",
        flush=True,
    )

    fired, base, void, none, floor, busy = [], [], 0, 0, 0, 0
    for s in setups:
        f = limit_fill(tape, s)
        if f and abs(f[1] - f[2]) >= f[1] * args.min_stop_pct / 100:
            base.append((s.dir, *f))
        r = trigger(tape, shifts, s)
        if r == "void":
            void += 1
        elif r is None:
            none += 1
        elif abs(r[1] - r[2]) < r[1] * args.min_stop_pct / 100:
            floor += 1
        else:
            fired.append((s.dir, *r))
            if any(t.entry_ms <= tape.t[r[0]] < t.exit_ms for t in shipped):
                busy += 1

    n = len(setups)
    print("\nFIRE RATE")
    print(
        f"  shift printed in the band      {len(fired) + floor:>4}  {(len(fired) + floor) / n:.1%}"
    )
    print(f"  price closed through the stop  {void:>4}  {void / n:.1%}")
    print(f"  never printed before it died   {none:>4}  {none / n:.1%}")
    print(f"  refused, stop under the floor  {floor:>4}")
    print(f"  fired while a shipped trade was open: {busy}")
    print(f"  longs {sum(d > 0 for d, *_ in fired)}  shorts {sum(d < 0 for d, *_ in fired)}")

    print("\nRESULT, net of costs (total R, mean per trade in brackets)")
    _row("1m internal shift entry", fired, tape, args.horizon_min)
    _row("baseline: limit at 0.618", base, tape, args.horizon_min)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
