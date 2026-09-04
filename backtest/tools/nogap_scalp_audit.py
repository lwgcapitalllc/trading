#!/usr/bin/env python3
"""nogap_scalp_audit.py — what a SHORT-HOLD variant could take out of the setups the gap
requirement refuses.

Aaron's question (2026-08-23): the A+ runner is built to HOLD — it banks a little and rides the
rest for as long as the structure allows, which is why swap matters to it. The setups that reach
the 0.5-0.886 band with every other confluence present and NO fair-value gap to rest a limit on
are a different animal: he wants to know whether they can be taken for a fixed, small number of R
and closed the same session, at a lower risk per trade.

`miss_audit.py` already COUNTS them (code 3, "No FVG in zone" — 178 over 2020-01-01 -> 2026-08-06).
This tool takes those same setups and asks what they were WORTH under a short-hold rule set:

    1. FILL        how many of them price actually reached, at each candidate entry
    2. EXCURSION   how far each one ran, in R, before it hit its stop
    3. STOP        which fib the stop belongs on — measured, not inherited from the runner
    4. TARGET      the fixed R that maximises total R, and what it costs in hit rate
    5. BREAKEVEN   how far the trade must go before the stop comes to entry, and what that
                   protection is worth once it also stops trades that would have recovered
    6. LADDER      bank a fraction at a near target and run the rest

⚠ **THIS IS A SCREEN, NOT A PORTFOLIO.** Every setup is measured on its own, with no position
slot and no contention — so the totals are an UPPER BOUND for a bot that can hold one trade at a
time. `--one-slot` re-runs the winning rule sequentially (a setup arriving while an earlier one is
still open is skipped) and prints what contention costs. Read both. Run 12 is the standing reason:
with one slot an extra setup does not ADD to the book, it QUEUES in front of it.

⚠ **The entry is RECONSTRUCTED, not replayed.** The engine's own no-gap fallback rests a limit at
the 0.618 (`_entry_edges`, read when the gap requirement is off), and that is what this
reproduces — but from the fib geometry captured at the bar price entered the band, rather than by
running the order layer. That is what makes a stop/target/ladder grid affordable; the alternative
is one full replay per cell. **Before believing a cell, replay it**: the shipped path for that is
`exit_audit.py --set exec_req_fvg=False --set ...`.

⚠ **Costs are charged, and on a small target they are not a rounding error.** PU Prime ECN, gold:
$1.00/side/lot commission (= $0.02 of price per round turn on a 100oz lot) plus one $0.12 spread,
so ~$0.14 of price per trade. Against a $6 stop that is 2.3% of R before anything else happens.
Swap is charged per 17:00-NY rollover crossed at the measured -$79.60 long / +$30.25 short per lot
per night — which is the whole reason a short hold is being asked about.

⚠ **NOTHING exits on the fill bar — not the target and not the stop — and both halves are the
engine's own.** A buy limit is filled on the way DOWN, so that bar's high is the approach and not
the trade's move; crediting it would report a favourable excursion from before the position
existed (`Execution._open` seeds the running favourable extreme from the fill price for exactly
this reason). And an exit order placed at a bar's close is what the NEXT bar trades against — the
one-bar delay every fill model here is built on — so the same bar's low dipping past the stop does
not close the trade either. **The stop half was wrong here first and was caught by measurement,
not by reading**: with the stop live on the fill bar this walk killed a trade the engine ran 316
bars for +9.98R. See `scripts`-free check in the module's own validation note below.

⚠ **Intrabar order is the engine's assumption too** (`_intrabar_targets_first`): on a bar holding
both the stop and a target, whichever the open sits nearer is reached first. Imported, not
reimplemented.

Usage:
    python3 backtest/tools/nogap_scalp_audit.py
    python3 backtest/tools/nogap_scalp_audit.py --start 2020-01-01 --end 2026-08-06 --one-slot
    python3 backtest/tools/nogap_scalp_audit.py --horizon 96
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FIB = str(_ROOT / "engines" / "fibonacci")
if _FIB not in sys.path:
    sys.path.insert(0, _FIB)

from geometry import fib_level  # noqa: E402

from strategies.python.sos_fade.execution import (  # noqa: E402
    _intrabar_targets_first,
)

_NY = ZoneInfo("America/New_York")

# PU Prime ECN, XAUUSD — every figure MEASURED; provenance is in backtest/fills.py.
_COMMISSION_PER_SIDE_PER_LOT = 1.00
_CONTRACT_SIZE = 100.0
_SPREAD = 0.12
_SWAP_LONG_POINTS = -79.60
_SWAP_SHORT_POINTS = 30.25
_SWAP_DIGITS = 2
_TRIPLE_WEEKDAY = 2  # Wednesday books three nights on this broker's gold
_DAILY_CLOSE_HOUR_NY = 17

#: Round-turn cost in PRICE terms (per ounce), swap excluded. Commission is per side per lot, so
#: two sides on a 100oz lot is $2.00 over 100oz = $0.02; the spread is billed as one whole spread
#: per round turn (`Execution._charge_spread` bills half per side).
_COST_PRICE = 2 * _COMMISSION_PER_SIDE_PER_LOT / _CONTRACT_SIZE + _SPREAD


def _swap_price_per_night(direction: int) -> float:
    """One night's swap in PRICE per ounce, so it divides straight into R. Negative = charged."""
    pts = _SWAP_LONG_POINTS if direction > 0 else _SWAP_SHORT_POINTS
    return pts * _CONTRACT_SIZE * (10**-_SWAP_DIGITS) / _CONTRACT_SIZE


def _rollovers_between(entry_ms: int, exit_ms: int) -> int:
    """Nights booked between two instants — the engine's 17:00-NY boundary, Saturday skipped.

    Mirrors `Execution._last_rollover_before` rather than approximating with a calendar date
    change: the broker's day turns at 17:00 New York, so a trade opened 15:00 and closed 19:00 the
    same afternoon HAS crossed one, and Monday 18:00 -> Tuesday 16:00 has crossed none. The
    triple-swap weekday books three.
    """
    if exit_ms <= entry_ms:
        return 0
    start = datetime.fromtimestamp(entry_ms / 1000.0, tz=timezone.utc).astimezone(_NY)
    end = datetime.fromtimestamp(exit_ms / 1000.0, tz=timezone.utc).astimezone(_NY)
    nights, day = 0, start.date()
    while True:
        roll = datetime.combine(day, dtime(_DAILY_CLOSE_HOUR_NY), tzinfo=_NY)
        if roll > end:
            break
        if roll > start and day.weekday() != 5:
            nights += 3 if day.weekday() == _TRIPLE_WEEKDAY else 1
        day += timedelta(days=1)
    return nights


class Setup:
    """One code-3 miss, with the fib geometry it would have been entered against.

    `z_idx` is the bar price first tagged the 0.5-0.886 band, `d_idx` the bar the setup died. A
    limit only rests between them: the engine cancels a pending entry when the setup dies, so a
    fill after `d_idx` is a trade the bot would never have taken.
    """

    __slots__ = (
        "dir",
        "z_idx",
        "d_idx",
        "ash",
        "asl",
        "fdir",
        "time_ms",
        "arm_text",
        "swp",
        "div",
        "pool",
        "ob",
        "div_live",
    )

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def level(self, ratio: float) -> float:
        return fib_level(self.ash, self.asl, self.fdir, ratio)


def collect(df, warmup: int, blocks: dict, verbose: bool = True):
    """Replay A+ at its SHIPPED settings and return the code-3 misses with their geometry.

    The geometry is logged on EVERY bar and looked up afterwards by the miss's own
    `zone_time_ms`, rather than snapshotted inside the watch. A watch can open, tag the zone and
    die on the same bar, so anything hooked to the open/close pair loses the geometry for exactly
    the fastest setups — the ones a short-hold variant most wants to see.
    """
    from strategies.python.sos_fade import LAB_STRATEGY

    cfg = LAB_STRATEGY["config"](fill_model="bar", symbol="XAUUSD", exec_secondary=False)
    strat = LAB_STRATEGY["strategy"](config=cfg, initial_capital=10_000.0)
    ex = strat.execution
    geo: dict = {}
    _orig = ex._record_misses

    # The RAW arm flags, deliberately not the toggle-filtered ones. `exec_arm_div` ships OFF, so
    # the miss record's own `arm_text` can never say "Sweep + RSI div" — it reports the sources
    # the operator has switched ON. What armed the SETUP is a fact about the market and is the
    # split the engine's own no-gap note measures against (`_nogap_arm_ok`), so it has to be read
    # off the sequence.
    gates: dict = {"veto_l": {}, "veto_s": {}, "hour": {}}

    def _hooked(sig, seq, dec, long_edge, short_edge):
        gates["veto_l"][sig.index] = bool(dec.long_veto)
        gates["veto_s"][sig.index] = bool(dec.short_veto)
        gates["hour"][sig.index] = sig.ny_hour
        if sig.fibo_ash is not None and sig.fibo_asl is not None:
            geo[sig.time_ms] = (
                sig.index,
                sig.fibo_ash,
                sig.fibo_asl,
                sig.fibo_dir,
                bool(seq.sos_l_swp),
                bool(seq.sos_l_div),
                bool(seq.sos_s_swp),
                bool(seq.sos_s_div),
                sig.recent_ssl,
                sig.recent_bsl,
                bool(sig.bull_div_active),
                bool(sig.bear_div_active),
            )
        return _orig(sig, seq, dec, long_edge, short_edge)

    ex._record_misses = _hooked
    if verbose:
        print(f"replaying sos_fade at shipped settings (warmup {warmup}) ...", flush=True)
    strat.run(df, warmup=warmup)

    setups, no_geo = [], 0
    for m in strat.execution.misses:
        if m.index < warmup or m.code != 3:
            continue
        g = geo.get(m.zone_time_ms) if m.zone_time_ms is not None else None
        if g is None or g[3] != m.dir:
            no_geo += 1
            continue
        (z_idx, ash, asl, fdir, lswp, ldiv, sswp, sdiv, ssl, bsl, bull_div, bear_div) = g
        ob_l, ob_s = blocks.get(z_idx, (False, False))
        setups.append(
            Setup(
                dir=m.dir,
                z_idx=z_idx,
                d_idx=m.index,
                ash=ash,
                asl=asl,
                fdir=fdir,
                time_ms=m.zone_time_ms,
                arm_text=m.arm_text,
                swp=lswp if m.dir > 0 else sswp,
                div=ldiv if m.dir > 0 else sdiv,
                pool=(ssl if m.dir > 0 else bsl) or "none",
                ob=ob_l if m.dir > 0 else ob_s,
                div_live=bull_div if m.dir > 0 else bear_div,
            )
        )
    return setups, strat.execution.trades, no_geo, gates


def collect_blocks(df, warmup: int, verbose: bool = True) -> dict:
    """`{bar index: (block in the long band, block in the short band)}`, from a SECOND replay.

    🔴 **It needs its own replay and that is the whole point of this function.** The order-block
    engine is only built into the stack when the strategy's point-of-interest setting asks for
    something other than gaps (`SosFadeStrategy._engine_config`), and the shipped setting asks
    for gaps — so at shipped settings `obs_available` is False on every one of the 155,807 bars
    and every "is there a block here" question comes back False. MEASURED before this existed:
    the first version of this audit reported "no order block in the zone on any of the 146
    setups" off exactly that. **A registry nobody populated answers confidently and wrongly**,
    and the answer looked like a finding.

    The second pass is safe to JOIN to the first by bar index because the two things being read
    are independent of the setting that was changed: the order-block engine is standalone (plain
    OHLC in, since the 2026-07-31 re-port) and the fib band comes from the structure engine.
    Neither is downstream of which point of interest an entry rests on. What DOES move is the
    trade list — so nothing from this replay is used except where the blocks were.
    """
    from strategies.python.sos_fade import LAB_STRATEGY

    cfg = LAB_STRATEGY["config"](
        fill_model="bar", symbol="XAUUSD", exec_secondary=False, exec_poi_source="Either"
    )
    strat = LAB_STRATEGY["strategy"](config=cfg, initial_capital=10_000.0)
    ex = strat.execution
    _orig = ex._record_misses
    out: dict = {}
    seen = {"avail": 0}

    def _hooked(sig, seq, dec, long_edge, short_edge):
        if sig.obs_available:
            seen["avail"] += 1
        p2, p6 = sig.fibo_p2, sig.fibo_p6
        if p2 is not None and p6 is not None and sig.obs:
            ob_l = ob_s = False
            for top, bot, is_bull, _born in sig.obs:
                # The same overlap test `_entry_edges` applies to a gap: same band, same side.
                if is_bull and sig.fibo_dir == 1 and bot <= p2 and top >= p6:
                    ob_l = True
                if (not is_bull) and sig.fibo_dir == -1 and top >= p2 and bot <= p6:
                    ob_s = True
            if ob_l or ob_s:
                out[sig.index] = (ob_l, ob_s)
        return _orig(sig, seq, dec, long_edge, short_edge)

    ex._record_misses = _hooked
    if verbose:
        print("second pass with the order-block engine switched on ...", flush=True)
    strat.run(df, warmup=warmup)
    if seen["avail"] == 0:
        raise RuntimeError(
            "the order-block engine still produced nothing on any bar. Do NOT read the resulting "
            "zeros as 'no setup had a block' — that is the reading this function exists to stop."
        )
    if verbose:
        print(f"  blocks overlapped the band on {len(out):,} bars", flush=True)
    return out


# ── higher-timeframe trend ───────────────────────────────────────────────────────
#: The timeframes a trend filter would be built from, with the minutes each bar spans. The
#: 15-minute row is the setup's own stream and is here so "does the setup fade its own trend"
#: is asked the same way as the rest.
_TF_MINUTES = (
    ("15m", "15", 15),
    ("1h", "H1", 60),
    ("4h", "H4", 240),
    ("daily", None, 1440),
    ("weekly", None, 10080),
)


def trend_series(bars):
    """Per-bar trend from the CANONICAL structure engine: +1 after a bull break, -1 after a bear.

    Never a second trend definition. The engine that decides what a break is on the 15-minute
    stream is the engine that decides it on the weekly, so "the daily is bullish" means the same
    thing as "the 15-minute is bullish" and the two can be compared. 0 until the first break.
    """
    import sys as _sys

    _eng = str(_ROOT / "engines")
    if _eng not in _sys.path:
        _sys.path.insert(0, _eng)
    # Bare-name, public API only — the same way `command-center/` imports these. Never a second
    # implementation of a canonical engine.
    from market_structure import Bar, StructureEngine

    out, cur = [], 0
    eng = StructureEngine()
    o = bars["open"].to_numpy()
    h = bars["high"].to_numpy()
    lo = bars["low"].to_numpy()
    c = bars["close"].to_numpy()
    for i in range(len(o)):
        ev = eng.update(
            Bar(index=i, open=float(o[i]), high=float(h[i]), low=float(lo[i]), close=float(c[i]))
        )
        e = ev.external
        if e.bull_bos or e.bull_sos:
            cur = 1
        elif e.bear_bos or e.bear_sos:
            cur = -1
        out.append(cur)
    return out


def load_trends(symbol: str, start: str, end: str, m15, verbose: bool = True) -> dict:
    """`{name: list aligned to the 15-minute bars}` — each higher timeframe's trend, no lookahead.

    🔴 **The alignment is the whole correctness argument.** A higher-timeframe bar is stamped at
    its OPEN, so the bar covering a 15-minute setup has NOT CLOSED yet and its trend is not
    knowable at that moment. Every lookup here takes the last HTF bar whose close is at or before
    the 15-minute bar's open. Taking the covering bar instead would let a Friday setup read a
    weekly break that happened on the following Wednesday, and every filter built on it would
    grade beautifully and be unbuildable.

    Daily and weekly are RESAMPLED from the hourly bars rather than pulled, because the cache
    holds no daily or weekly series for this symbol. ⚠ They are resampled on the FEED's own
    calendar day, not the broker's 17:00-New-York roll, so a "daily" here is not exactly the
    daily candle the terminal draws. It is consistent across the whole window, which is what a
    trend filter needs, but do not quote it as the broker's daily.
    """
    from backtest.data.source import BarSource

    src = BarSource()
    h1 = src.load(symbol, "60", start, end)
    frames = {"15m": m15, "1h": h1, "4h": src.load(symbol, "240", start, end)}
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    frames["daily"] = h1.resample("1D").agg(agg).dropna()
    frames["weekly"] = h1.resample("1W").agg(agg).dropna()

    m15_ms = m15.index.values.astype("int64") // 1_000_000
    out: dict = {}
    for name, _key, minutes in _TF_MINUTES:
        f = frames[name]
        tr = trend_series(f)
        f_ms = f.index.values.astype("int64") // 1_000_000
        dur = minutes * 60_000
        aligned = []
        for t in m15_ms:
            # last bar whose CLOSE (open + duration) is at or before this 15-minute bar's open
            j = int(f_ms.searchsorted(t - dur, side="right")) - 1
            aligned.append(tr[j] if j >= 0 else 0)
        out[name] = aligned
        if verbose:
            print(f"  {name:<7} {len(f):>7,} bars", flush=True)
    return out


class Tape:
    """The bar arrays, plus the one reading off them every rule needs."""

    def __init__(self, df):
        self.o = df["open"].to_numpy()
        self.h = df["high"].to_numpy()
        self.l = df["low"].to_numpy()
        self.t = df.index.values.astype("int64") // 1_000_000
        self.n = len(self.o)

    def fav_first(self, i: int, direction: int) -> bool:
        """Does this bar reach the FAVOURABLE extreme first? The engine's assumption, mirrored.

        `_intrabar_targets_first` answers it for a LONG (high before low). A short's favourable
        extreme is the low, so the same reading inverts."""
        up_first = _intrabar_targets_first(self.o[i], self.h[i], self.l[i])
        return up_first if direction > 0 else not up_first


def fill(tape: Tape, s: Setup, entry_ratio: float, stop_ratio: float, min_stop_pct: float):
    """Where and when the resting limit would have filled — `(idx, entry, stop, risk)` or None.

    The scan starts ON the zone bar, not after it: the engine rests this limit from the SOS
    onward whatever price is doing, so the one-bar order delay was satisfied bars ago. It ends on
    the bar the setup died.

    `min_stop_pct` is the engine's own minimum-stop floor. A stop closer than that is REFUSED
    rather than shrunk — `qty = risk / dist` balloons the position on a tight stop, which is the
    hazard that guard exists for, and a variant that quietly ignores it is not the bot.
    """
    e, st = s.level(entry_ratio), s.level(stop_ratio)
    risk = abs(e - st)
    if risk <= 0:
        return None
    if min_stop_pct > 0 and risk < e * min_stop_pct / 100.0:
        return "floor"
    hi = min(s.d_idx, tape.n - 1)
    for i in range(s.z_idx, hi + 1):
        if s.dir > 0 and tape.l[i] <= e:
            return i, e, st, risk
        if s.dir < 0 and tape.h[i] >= e:
            return i, e, st, risk
    return None


def walk(
    tape: Tape,
    s: Setup,
    filled,
    horizon: int,
    target_r=None,
    be_at=None,
    tp1_r=None,
    tp1_pct=0.0,
    trail_r=None,
    time_bars=None,
):
    """Run ONE exit rule over ONE filled setup and report what happened.

    Every level is a PRICE; R is only a way of naming one. On the fill bar only the stop is live
    (see the module docstring). Breakeven and the trail arm off a bar's excursion AFTER that bar's
    exits — arming breakeven off the same high that would have filled the target is a rule reading
    its own future.
    """
    i0, e, st, risk = filled
    d = s.dir
    stop = st
    open_frac = 1.0
    realised_r = 0.0
    mfe_r = mae_r = 0.0
    banked = False
    tp1_px = e + d * tp1_r * risk if tp1_r else None
    tgt_px = e + d * target_r * risk if target_r else None
    last = min(i0 + horizon, tape.n - 1)
    exit_i, reason = last, "horizon"

    for i in range(i0, last + 1):
        hi, lo = tape.h[i], tape.l[i]
        entry_bar = i == i0
        fav = 0.0 if entry_bar else ((hi - e) / risk if d > 0 else (e - lo) / risk)
        adv = (lo - e) / risk if d > 0 else (e - hi) / risk
        mfe_r = max(mfe_r, fav)
        mae_r = min(mae_r, adv)

        # NOTHING exits on the fill bar, the stop included. An exit order placed at a bar's
        # close is what the NEXT bar trades against (the one-bar delay every fill model here is
        # built on), so a bar whose low dipped past the stop on its way INTO a buy limit does not
        # close the trade. MEASURED: with the stop live on the fill bar this walk killed a trade
        # the engine went on to run 316 bars for +9.98R, and two others like it.
        hit_stop = (not entry_bar) and ((lo <= stop) if d > 0 else (hi >= stop))
        hit_tp1 = (
            (not entry_bar)
            and tp1_px is not None
            and not banked
            and ((hi >= tp1_px) if d > 0 else (lo <= tp1_px))
        )
        hit_tgt = (
            (not entry_bar) and tgt_px is not None and ((hi >= tgt_px) if d > 0 else (lo <= tgt_px))
        )

        events = []
        if hit_tp1:
            events.append(("tp1", tp1_px))
        if hit_tgt:
            events.append(("target", tgt_px))
        events.sort(key=lambda ev: abs(ev[1] - e))  # nearer rung banks first
        if hit_stop:
            events = (
                (events + [("stop", stop)]) if tape.fav_first(i, d) else ([("stop", stop)] + events)
            )

        done = False
        for name, px in events:
            r = d * (px - e) / risk
            if name == "tp1":
                realised_r += r * tp1_pct
                open_frac -= tp1_pct
                banked = True
                continue
            realised_r += r * open_frac
            open_frac = 0.0
            exit_i, reason, done = i, name, True
            break
        if done:
            break

        if time_bars is not None and (i - i0) >= time_bars:
            # A CLOCK exit, so it fills at the next bar's open like every other market exit
            # here — not at this bar's close, which would let the rule pick its own price.
            px = tape.o[min(i + 1, tape.n - 1)]
            realised_r += d * (px - e) / risk * open_frac
            open_frac = 0.0
            exit_i, reason = i, "time"
            break

        if be_at is not None and fav >= be_at:
            stop = max(stop, e) if d > 0 else min(stop, e)
        if trail_r is not None and fav >= trail_r:
            peak = hi if d > 0 else lo
            cand = peak - d * trail_r * risk
            stop = max(stop, cand) if d > 0 else min(stop, cand)

    if open_frac > 1e-9:  # ran out of horizon still holding
        px = tape.o[min(exit_i + 1, tape.n - 1)]
        realised_r += d * (px - e) / risk * open_frac

    bars = exit_i - i0
    nights = _rollovers_between(int(tape.t[i0]), int(tape.t[exit_i]))
    cost_r = _COST_PRICE / risk
    swap_r = -_swap_price_per_night(d) * nights / risk
    return {
        "gross_r": realised_r,
        "net_r": realised_r - cost_r - swap_r,
        "cost_r": cost_r,
        "swap_r": swap_r,
        "mfe_r": mfe_r,
        "mae_r": mae_r,
        "bars": bars,
        "hours": bars * 0.25,
        "nights": nights,
        "reason": reason,
        "risk": risk,
        "i0": i0,
        "exit_i": exit_i,
        "dir": d,
    }


def _pct(n, total):
    return f"{100.0 * n / total:5.1f}%" if total else "    -"


def _q(vals, p):
    if not vals:
        return float("nan")
    xs = sorted(vals)
    return xs[max(0, min(len(xs) - 1, int(round(p * (len(xs) - 1)))))]


# ── report ───────────────────────────────────────────────────────────────────────
_ENTRIES = (0.5, 0.618, 0.702, 0.786)
_STOPS = (0.786, 0.886, 1.0, 1.13, 1.272)
_TARGETS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 8.0, 12.0)
_BES = (None, 0.25, 0.5, 0.75, 1.0, 1.5)
_LADDER_TP1 = (0.5, 0.75, 1.0)
_LADDER_PCT = (0.25, 0.5, 0.75)
_LADDER_RUN = (1.5, 2.0, 3.0, 5.0, 8.0)


def _fills(tape, setups, entry_ratio, stop_ratio, min_stop_pct):
    """Every setup's fill under one geometry, plus the two ways it can fail to produce a trade."""
    out, floored, unreached = [], 0, 0
    for s in setups:
        f = fill(tape, s, entry_ratio, stop_ratio, min_stop_pct)
        if f == "floor":
            floored += 1
        elif f is None:
            unreached += 1
        else:
            out.append((s, f))
    return out, floored, unreached


def _run(tape, fills, horizon, **rule):
    return [walk(tape, s, f, horizon, **rule) for s, f in fills]


def _tot(rs, key="net_r"):
    return sum(r[key] for r in rs)


def _gate_ok(gates, s: Setup, filled, no_late: bool, respect_veto: bool) -> bool:
    """The engine's own entry-side gates, applied at the bar the limit filled.

    These are read at the FILL, not at the setup's death, and that is the only reading that means
    anything: the final-hour rule and the divergence/extreme veto both refuse an ENTRY, so the
    question is what they said at the moment this trade would have opened. A code-3 miss never
    reached them (the gap check dies first), so nothing in the miss record answers this.
    """
    i = filled[0]
    if no_late:
        h = gates["hour"].get(i)
        if h is not None and 16 <= h < 18:
            return False
    if respect_veto and gates["veto_l" if s.dir > 0 else "veto_s"].get(i, False):
        return False
    return True


def _best_rule(tape, fills, horizon):
    """The best-scoring rule of every shape this tool knows, over one set of fills.

    Returns `(net_r, label, rule, results)`. A plain target, a target with the stop coming to
    entry, and a two-rung ladder are all searched together rather than reported as three separate
    winners, because the question being asked is what this pool is worth AT ALL — three tables
    with three different bests invites reading the largest of them as the answer.
    """
    best = None

    def _try(label, rule):
        nonlocal best
        res = _run(tape, fills, horizon, **rule)
        tot = _tot(res)
        if best is None or tot > best[0]:
            best = (tot, label, rule, res)

    for tr in _TARGETS:
        for be in _BES:
            _try(
                f"target {tr:.2f}R" + (f", breakeven at {be:.2f}R" if be else ""),
                dict(target_r=tr, be_at=be),
            )
    for t1 in _LADDER_TP1:
        for pc in _LADDER_PCT:
            for run_to in _LADDER_RUN:
                if run_to <= t1:
                    continue
                for be in (None, t1):
                    _try(
                        f"bank {pc:.0%} at {t1:.2f}R, runner {run_to:.2f}R"
                        + (f", breakeven at {be:.2f}R" if be else ""),
                        dict(target_r=run_to, tp1_r=t1, tp1_pct=pc, be_at=be),
                    )
    return best


def _depth_ratio(s: Setup, price: float) -> float:
    """A PRICE turned back into the fib ratio it sits on — the inverse of `fib_level`.

    0.0 is the swing extreme the leg ran to, 1.0 the leg's origin, so a bigger number is a deeper
    retrace on both sides. Written as the inverse of the canonical geometry rather than as a
    second convention, so a ratio here means exactly what a ratio means everywhere else.
    """
    rng = s.ash - s.asl
    if rng <= 0:
        return float("nan")
    return (s.ash - price) / rng if s.fdir == 1 else (price - s.asl) / rng


def _turn_depth(tape: Tape, s: Setup, filled, horizon: int, level_r: float = 1.0):
    """The DEEPEST fib ratio price reached before this trade first went `level_r` in favour.

    None when it never got there. This is the only non-circular way to ask which fib level the
    winners turn from: measuring the deepest point over the WHOLE hold would just report the stop
    for every loser and answer its own question.
    """
    i0, e, _st, risk = filled
    d = s.dir
    deepest = e
    for i in range(i0, min(i0 + horizon, tape.n - 1) + 1):
        if i > i0:
            fav = (tape.h[i] - e) / risk if d > 0 else (e - tape.l[i]) / risk
            if fav >= level_r:
                return _depth_ratio(s, deepest)
        px = tape.l[i] if d > 0 else tape.h[i]
        deepest = min(deepest, px) if d > 0 else max(deepest, px)
    return None


def _breakdown(title, buckets, base_n, base_hit1):
    """One feature's split, always against the pool's own base rate on the same line.

    A bucket is only interesting relative to the whole, and a table without the base rate printed
    beside it invites reading 45%% as good when the pool already does 38%%. `n` is printed for
    every row for the same reason — with 146 setups and a 38%% base rate, a bucket of 8 can read
    75%% on six coin flips.
    """
    print(f"\n   {title}")
    print(f"      {'':<22} {'n':>4} {'>=1R':>7} {'>=2R':>7} {'med best':>9} {'vs base':>8}")
    for name, rows in buckets:
        if not rows:
            continue
        n = len(rows)
        h1 = sum(1 for r in rows if r["mfe_r"] >= 1.0)
        h2 = sum(1 for r in rows if r["mfe_r"] >= 2.0)
        med = _q([r["mfe_r"] for r in rows], 0.5)
        delta = 100.0 * h1 / n - base_hit1
        print(f"      {name:<22} {n:>4} {_pct(h1, n)} {_pct(h2, n)} {med:>8.2f}R {delta:>+7.1f}pp")


def _session(hour: int) -> str:
    """New York hour -> the session a trader would name it. Boundaries are the engine's own
    working day (the broker rolls at 17:00 NY), not a chart's local time."""
    if 19 <= hour or hour < 3:
        return "Asia"
    if 3 <= hour < 7:
        return "London"
    if 7 <= hour < 12:
        return "New York am"
    if 12 <= hour < 17:
        return "New York pm"
    return "final hour"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2026-08-06")
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument(
        "--horizon",
        type=int,
        default=192,
        help="bars a trade may stay open before it is marked out at the next open "
        "(192 x 15m = 48h). The EXCURSION section is measured against this, so "
        "widening it can only raise the reported reach.",
    )
    ap.add_argument(
        "--min-stop-pct",
        type=float,
        default=0.08,
        help="the engine's minimum-stop floor, %% of price. 0 disables it.",
    )
    ap.add_argument(
        "--entry",
        type=float,
        default=0.618,
        help="the fib the limit rests on — 0.618 is the engine's own no-gap fallback",
    )
    ap.add_argument("--stop", type=float, default=0.886)
    ap.add_argument(
        "--pool",
        default="all",
        choices=("all", "both", "sweep"),
        help="which setups to measure: every one, only those armed by a sweep AND an "
        "RSI divergence, or only sweep-armed ones",
    )
    ap.add_argument(
        "--no-trends",
        dest="trends",
        action="store_false",
        help="skip the higher-timeframe trend pass (it loads and replays 4 more series)",
    )
    ap.add_argument(
        "--one-slot",
        action="store_true",
        help="also replay the best rule sequentially, one position at a time",
    )
    args = ap.parse_args(argv)

    from backtest.data.source import BarSource

    print(f"loading {args.symbol} {args.tf}m  {args.start} -> {args.end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, args.start, args.end)
    if df.empty:
        print("no bars — is the MT5 agent tunnel up on localhost:8766?")
        return 1
    print(f"  {len(df):,} bars  {df.index[0]} -> {df.index[-1]}", flush=True)

    trends = load_trends(args.symbol, args.start, args.end, df) if args.trends else {}
    blocks = collect_blocks(df, args.warmup)
    setups, aplus, no_geo, gates = collect(df, args.warmup, blocks)
    n_trades = len(aplus)
    n_all = len(setups)
    if args.pool == "both":
        setups = [x for x in setups if x.swp and x.div]
    elif args.pool == "sweep":
        setups = [x for x in setups if x.swp and not x.div]
    tape = Tape(df)
    W = 96

    print("\n" + "=" * W)
    print(
        f"NO-GAP SHORT-HOLD AUDIT   {args.symbol} {args.tf}m   "
        f"{df.index[0].date()} -> {df.index[-1].date()}"
    )
    print(
        f"  {len(setups)} setups reached the band with every confluence but the gap"
        + (f"  [pool: {args.pool}, of {n_all}]" if args.pool != "all" else "")
        + f"   ({n_trades} A+ trades in the same window)"
    )
    if no_geo:
        print(f"  ⚠ {no_geo} dropped — no fib geometry recorded at the zone-entry bar")
    print(
        f"  horizon {args.horizon} bars ({args.horizon * 0.25:.0f}h)   "
        f"minimum-stop floor {args.min_stop_pct}% of price   "
        f"costs ${_COST_PRICE:.2f}/round turn + swap"
    )
    print("=" * W)

    # ── 1. FILL ──────────────────────────────────────────────────────────────
    print("\n1. FILL — did price actually reach the limit before the setup died?")
    print(
        f"   {'entry':>7} {'stop':>7} {'risk $ (med)':>13} {'filled':>8} {'never got there':>16}"
        f" {'refused: stop too tight':>25}"
    )
    for er in _ENTRIES:
        for sr in _STOPS:
            if sr <= er:
                continue
            fs, floored, unreached = _fills(tape, setups, er, sr, args.min_stop_pct)
            if not fs and not floored:
                continue
            med = _q([f[3] for _, f in fs], 0.5) if fs else float("nan")
            print(
                f"   {er:>7.3f} {sr:>7.3f} {med:>13.2f} "
                f"{len(fs):>4} {_pct(len(fs), len(setups))} {unreached:>10} {floored:>18}"
            )

    base_fills, base_floor, base_unreached = _fills(
        tape, setups, args.entry, args.stop, args.min_stop_pct
    )

    # ── 2. EXCURSION ─────────────────────────────────────────────────────────
    rs = _run(tape, base_fills, args.horizon)  # no target: run to the stop or the horizon
    n = len(rs)
    print(
        f"\n2. EXCURSION — entry {args.entry}, stop {args.stop}, NO target: how far did "
        f"{n} filled setups run?"
    )
    print(f"   {'reached':>9} {'setups':>8} {'share':>8}   {'median hours to get there':>26}")
    for lvl in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 5.0):
        got = [r for r in rs if r["mfe_r"] >= lvl]
        hrs = _q(
            [_hours_to(tape, s, f, lvl) for (s, f), r in zip(base_fills, rs) if r["mfe_r"] >= lvl],
            0.5,
        )
        print(f"   {lvl:>8.2f}R {len(got):>8} {_pct(len(got), n)}   {hrs:>26.1f}")
    mfes = [r["mfe_r"] for r in rs]
    maes = [r["mae_r"] for r in rs]
    print(
        f"   best excursion   median {_q(mfes, 0.5):.2f}R   mean {sum(mfes) / n:.2f}R   "
        f"p75 {_q(mfes, 0.75):.2f}R   p90 {_q(mfes, 0.90):.2f}R"
    )
    print(
        f"   worst drawdown   median {_q(maes, 0.5):.2f}R   p10 {_q(maes, 0.10):.2f}R   "
        f"(stopped out: {sum(1 for r in rs if r['reason'] == 'stop')} of {n})"
    )

    # ── 2b. THE CONTROL ──────────────────────────────────────────────────────
    # A number about this pool means nothing on its own — the honest question is not "is 0.54R a
    # lot" but "is it what a setup WITH a gap does". Same walk, same bars, same R definition, run
    # over the A+ bot's own trades at the stop each was really sized against. Anything this
    # section and the one above disagree about is a fact about the gap, because nothing else
    # differs between them.
    ctrl = []
    for t in aplus:
        if t.stop_distance <= 0:
            continue
        st = t.entry_price - t.dir * t.stop_distance
        cs = Setup(
            dir=t.dir,
            z_idx=t.entry_index,
            d_idx=t.entry_index,
            ash=0.0,
            asl=0.0,
            fdir=t.dir,
            time_ms=t.entry_ms,
            arm_text="",
            swp=False,
            div=False,
        )
        ctrl.append(
            walk(tape, cs, (t.entry_index, t.entry_price, st, t.stop_distance), args.horizon)
        )
    print(
        f"\n2b. THE CONTROL — the same question asked of the {len(ctrl)} A+ trades that DID "
        f"have a gap"
    )
    print(f"   {'reached':>9} {'no gap':>16} {'gap (A+)':>16}")
    for lvl in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 5.0):
        a = sum(1 for r in rs if r["mfe_r"] >= lvl)
        b = sum(1 for r in ctrl if r["mfe_r"] >= lvl)
        print(f"   {lvl:>8.2f}R {a:>7} {_pct(a, len(rs))} {b:>7} {_pct(b, len(ctrl))}")
    cm = [r["mfe_r"] for r in ctrl]
    print(
        f"   best excursion   median {_q(cm, 0.5):.2f}R   mean {sum(cm) / len(cm):.2f}R   "
        f"p75 {_q(cm, 0.75):.2f}R   p90 {_q(cm, 0.90):.2f}R"
    )
    print(
        f"   stopped out      {sum(1 for r in ctrl if r['reason'] == 'stop')} of {len(ctrl)}"
        f"  ({_pct(sum(1 for r in ctrl if r['reason'] == 'stop'), len(ctrl)).strip()})"
        f"   vs {_pct(sum(1 for r in rs if r['reason'] == 'stop'), len(rs)).strip()} with no gap"
    )

    # ── 3+4. STOP x TARGET ───────────────────────────────────────────────────
    print("\n3. STOP x TARGET — total net R over every setup, banked in full at the target")
    print("   (each cell is a complete rule; the count under it is how many setups it traded)")
    best = None
    for sr in _STOPS:
        if sr <= args.entry:
            continue
        fs, _fl, _un = _fills(tape, setups, args.entry, sr, args.min_stop_pct)
        if not fs:
            continue
        print(
            f"\n   stop {sr:.3f}   {len(fs)} trades   "
            f"median risk ${_q([f[3] for _, f in fs], 0.5):.2f}"
        )
        print(
            f"      {'target':>7} {'hit%':>6} {'net R':>9} {'R/trade':>9} {'med hrs':>8}"
            f" {'overnight':>10} {'swap R':>8}"
        )
        for tr in _TARGETS:
            res = _run(tape, fs, args.horizon, target_r=tr)
            hits = sum(1 for r in res if r["reason"] == "target")
            tot = _tot(res)
            over = sum(1 for r in res if r["nights"] > 0)
            row = (sr, tr, tot, len(fs))
            if best is None or tot > best[2]:
                best = row
            print(
                f"      {tr:>6.2f}R {_pct(hits, len(res))} {tot:>9.1f} {tot / len(res):>9.3f}"
                f" {_q([r['hours'] for r in res], 0.5):>8.1f} {_pct(over, len(res))}"
                f" {-_tot(res, 'swap_r'):>8.1f}"
            )
    print(
        f"\n   BEST plain target: stop {best[0]:.3f} / target {best[1]:.2f}R "
        f"-> {best[2]:.1f}R over {best[3]} trades"
    )

    # ── 5. BREAKEVEN ─────────────────────────────────────────────────────────
    b_stop = best[0]
    fs, _fl, _un = _fills(tape, setups, args.entry, b_stop, args.min_stop_pct)
    print(
        f"\n4. BREAKEVEN — stop {b_stop:.3f}. Move the stop to entry once the trade is this far "
        f"ahead."
    )
    print(
        f"      {'target':>7}"
        + "".join(f"{('BE ' + (f'{b:.2f}R' if b else 'off')):>11}" for b in _BES)
    )
    be_best = None
    for tr in _TARGETS:
        cells = []
        for be in _BES:
            res = _run(tape, fs, args.horizon, target_r=tr, be_at=be)
            tot = _tot(res)
            cells.append(tot)
            if be_best is None or tot > be_best[2]:
                be_best = (tr, be, tot)
        print(f"      {tr:>6.2f}R" + "".join(f"{c:>11.1f}" for c in cells))
    print(
        f"\n   BEST with breakeven: target {be_best[0]:.2f}R, "
        f"breakeven at {be_best[1] if be_best[1] else 'off'} -> {be_best[2]:.1f}R"
    )

    # ── 6. LADDER ────────────────────────────────────────────────────────────
    print(
        f"\n5. LADDER — bank part of the position at a near rung, run the rest. stop {b_stop:.3f}"
    )
    print(
        f"      {'bank at':>8} {'size':>6} {'runner to':>10} {'BE':>6} {'net R':>9}"
        f" {'R/trade':>9} {'med hrs':>8} {'full stops':>11}"
    )
    lad_best = None
    for t1 in _LADDER_TP1:
        for pc in _LADDER_PCT:
            for run_to in _LADDER_RUN:
                if run_to <= t1:
                    continue
                for be in (None, t1):
                    res = _run(
                        tape, fs, args.horizon, target_r=run_to, tp1_r=t1, tp1_pct=pc, be_at=be
                    )
                    tot = _tot(res)
                    if lad_best is None or tot > lad_best[0]:
                        lad_best = (tot, t1, pc, run_to, be, res)
                    stops = sum(1 for r in res if r["reason"] == "stop")
                    print(
                        f"      {t1:>7.2f}R {pc:>5.0%} {run_to:>9.2f}R "
                        f"{('at ' + f'{be:.2f}R') if be else 'off':>6} {tot:>9.1f}"
                        f" {tot / len(res):>9.3f}"
                        f" {_q([r['hours'] for r in res], 0.5):>8.1f} {_pct(stops, len(res))}"
                    )
    print(
        f"\n   BEST ladder: bank {lad_best[2]:.0%} at {lad_best[1]:.2f}R, runner to "
        f"{lad_best[3]:.2f}R, breakeven {lad_best[4] or 'off'} -> {lad_best[0]:.1f}R"
    )

    # ── 6. WHAT ARMED IT ─────────────────────────────────────────────────────
    print("\n6. WHAT ARMED THE SETUP — the split the engine's own no-gap note is measured on")
    print("   (a sweep and an RSI divergence are the two stage-1 triggers; a setup can carry both)")
    pools = (
        ("all", lambda s: True),
        ("sweep AND divergence", lambda s: s.swp and s.div),
        ("sweep only", lambda s: s.swp and not s.div),
        ("divergence only", lambda s: s.div and not s.swp),
    )
    print(
        f"      {'pool':<22} {'setups':>7} {'filled':>7} {'best rule':<44} {'net R':>8}"
        f" {'R/trade':>8}"
    )
    for name, pred in pools:
        sub = [x for x in setups if pred(x)]
        if not sub:
            print(f"      {name:<22} {0:>7}")
            continue
        fs2, _fl, _un = _fills(tape, sub, args.entry, b_stop, args.min_stop_pct)
        if not fs2:
            print(f"      {name:<22} {len(sub):>7} {0:>7}")
            continue
        tot, label, _rule, res = _best_rule(tape, fs2, args.horizon)
        print(
            f"      {name:<22} {len(sub):>7} {len(fs2):>7} {label:<44} {tot:>8.1f}"
            f" {tot / len(fs2):>8.3f}"
        )

    # ── 6f. WHAT RISK IS SURVIVABLE ──────────────────────────────────────────
    # Everything above is in R, which is size-independent and therefore says NOTHING about what
    # per-trade risk this could carry. R totals add; equity compounds, and a run of losses at a
    # fat fraction is not recoverable by a later run of wins. So the sequence is replayed in trade
    # order at several fractions, which is the only form of the question that has an answer.
    #
    # ⚠ Still a SCREEN. One position at a time is assumed here (trades are taken in fill order and
    # an overlapping one is skipped), because a drawdown figure that let two positions run
    # concurrently would understate the worst case for a bot that cannot.
    keep2 = [
        (s0, f0) for s0, f0 in base_fills if s0.ob and not (10 <= gates["hour"].get(f0[0], -1) < 12)
    ]
    if keep2:
        res = _run(tape, keep2, args.horizon, target_r=2.0)
        res.sort(key=lambda r: r["i0"])
        seq, busy = [], -1
        for r in res:
            if r["i0"] <= busy:
                continue
            seq.append(r["net_r"])
            busy = r["exit_i"]
        streak = worst_streak = 0
        peak = run = worst_dd = 0.0
        for x in seq:
            run += x
            peak = max(peak, run)
            worst_dd = min(worst_dd, run - peak)
            streak = streak + 1 if x < 0 else 0
            worst_streak = max(worst_streak, streak)
        print(
            f"\n6f. WHAT PER-TRADE RISK THIS COULD CARRY — order block + not 10:00-12:00, "
            f"2R target, entry {args.entry}"
        )
        print(
            f"   {len(seq)} trades in sequence   total {sum(seq):+.1f}R   "
            f"worst losing streak {worst_streak}   worst drawdown {worst_dd:.1f}R"
        )
        print(f"      {'risk/trade':>11} {'end balance':>13} {'worst drawdown':>16}")
        for pct in (1.0, 2.5, 5.0, 10.0):
            eq, hi, dd = 1.0, 1.0, 0.0
            for x in seq:
                eq *= 1 + pct / 100.0 * x
                if eq <= 0:
                    eq = 0.0
                    break
                hi = max(hi, eq)
                dd = min(dd, eq / hi - 1)
            print(f"      {pct:>10.1f}% {eq:>12.2f}x {dd:>15.1%}")

    # ── 6b. THE CLOCK ────────────────────────────────────────────────────────
    print("\n6b. THE CLOCK — close the trade after N hours whatever it is doing")
    print(
        f"      {'hours':>7} {'no target':>11} {'+1.0R target':>13} {'+1.5R target':>13}"
        f" {'+2.0R target':>13} {'overnight':>10}"
    )
    for hrs in (1, 2, 4, 6, 8, 12, 18, 24, 36, 48):
        bars = int(hrs * 4)
        cells = []
        for tr in (None, 1.0, 1.5, 2.0):
            res = _run(tape, fs, args.horizon, target_r=tr, time_bars=bars)
            cells.append(_tot(res))
        res0 = _run(tape, fs, args.horizon, time_bars=bars)
        over = sum(1 for r in res0 if r["nights"] > 0)
        print(
            f"      {hrs:>7} "
            + "".join(f"{c:>13.1f}" for c in cells)
            + f" {_pct(over, len(res0)):>10}"
        )

    # ── 6c. WHAT THE WINNERS HAVE IN COMMON ──────────────────────────────────
    import datetime as _dt

    res_all = _run(tape, base_fills, args.horizon)
    base_n = len(res_all)
    base_hit1 = 100.0 * sum(1 for r in res_all if r["mfe_r"] >= 1.0) / base_n
    print(
        f"\n6c. WHAT SEPARATES THE ONES THAT WORK — {base_n} setups, "
        f"{base_hit1:.1f}% of them reach 1R"
    )
    print(
        "   ⚠ Every split below is univariate and the pool is small. A bucket under ~20 is a "
        "story, not a finding."
    )
    tagged = list(zip([s0 for s0, _f in base_fills], res_all, [f0 for _s, f0 in base_fills]))

    def _grp(keyfn, order=None):
        d: dict = {}
        for s0, r, f0 in tagged:
            d.setdefault(keyfn(s0, r, f0), []).append(r)
        keys = order or sorted(d)
        return [(k, d.get(k, [])) for k in keys]

    _breakdown(
        "WHICH POOL WAS SWEPT (read at the bar price entered the band)",
        _grp(lambda s0, r, f0: s0.pool),
        base_n,
        base_hit1,
    )
    _breakdown(
        "SESSION AT THE FILL",
        _grp(
            lambda s0, r, f0: _session(gates["hour"].get(f0[0], -1)),
            order=["Asia", "London", "New York am", "New York pm", "final hour"],
        ),
        base_n,
        base_hit1,
    )
    _breakdown(
        "HOUR OF DAY AT THE FILL (New York)",
        _grp(lambda s0, r, f0: f"{gates['hour'].get(f0[0], -1):02d}:00"),
        base_n,
        base_hit1,
    )
    _breakdown(
        "DAY OF WEEK",
        _grp(
            lambda s0, r, f0: _dt.datetime.utcfromtimestamp(int(tape.t[f0[0]]) / 1000).strftime(
                "%a"
            ),
            order=["Mon", "Tue", "Wed", "Thu", "Fri", "Sun"],
        ),
        base_n,
        base_hit1,
    )
    _breakdown(
        "DIRECTION", _grp(lambda s0, r, f0: "long" if s0.dir > 0 else "short"), base_n, base_hit1
    )
    _breakdown(
        "AN ORDER BLOCK IN THE ZONE INSTEAD OF A GAP",
        _grp(lambda s0, r, f0: "order block" if s0.ob else "nothing at all"),
        base_n,
        base_hit1,
    )
    _breakdown(
        "WHAT ARMED IT",
        _grp(
            lambda s0, r, f0: (
                "sweep + divergence"
                if (s0.swp and s0.div)
                else "sweep only"
                if s0.swp
                else "divergence only"
            )
        ),
        base_n,
        base_hit1,
    )
    _breakdown(
        "AN RSI DIVERGENCE STILL LIVE AT THE ZONE",
        _grp(lambda s0, r, f0: "live" if s0.div_live else "not live"),
        base_n,
        base_hit1,
    )
    _breakdown(
        "HOW BIG THE LEG WAS (1R in dollars)",
        _grp(
            lambda s0, r, f0: (
                "under $3"
                if f0[3] < 3
                else "$3-$6"
                if f0[3] < 6
                else "$6-$10"
                if f0[3] < 10
                else "over $10"
            )
        ),
        base_n,
        base_hit1,
    )
    _breakdown(
        "YEAR",
        _grp(lambda s0, r, f0: str(_dt.datetime.utcfromtimestamp(int(tape.t[f0[0]]) / 1000).year)),
        base_n,
        base_hit1,
    )

    # ── 6e. THE FIB LEVELS THEMSELVES ────────────────────────────────────────
    print("\n6e. THE FIB LEVELS — asked two ways, because they are two different questions")
    print("\n   (a) WHERE THE LIMIT RESTS. Same setups, same stop fib, only the entry moves.")
    print(
        f"      {'entry fib':<12} {'filled':>7} {'med 1R $':>9} {'>=1R':>7} {'>=2R':>7}"
        f" {'2R rule':>9}"
    )
    for er in _ENTRIES:
        fs2, _fl, _un = _fills(tape, setups, er, args.stop, args.min_stop_pct)
        if not fs2:
            continue
        res = _run(tape, fs2, args.horizon)
        h1 = sum(1 for r in res if r["mfe_r"] >= 1.0)
        h2 = sum(1 for r in res if r["mfe_r"] >= 2.0)
        r2 = _tot(_run(tape, fs2, args.horizon, target_r=2.0))
        print(
            f"      {er:<12.3f} {len(fs2):>7} {_q([f[3] for _, f in fs2], 0.5):>9.2f}"
            f" {_pct(h1, len(fs2))} {_pct(h2, len(fs2))} {r2:>9.1f}"
        )

    print("\n   (b) HOW DEEP PRICE WENT BEFORE IT TURNED. Deepest fib reached before the trade")
    print(
        "       first showed 1R, for the ones that got there. Entry fixed at "
        f"{args.entry}, stop {args.stop}."
    )
    depths = [(_turn_depth(tape, s0, f0, args.horizon), s0, f0) for s0, f0 in base_fills]
    turned = [(d0, s0, f0) for d0, s0, f0 in depths if d0 is not None]
    never = len(depths) - len(turned)
    bands = [
        ("shallower than 0.618", lambda d0: d0 < 0.618),
        ("0.618 - 0.702", lambda d0: 0.618 <= d0 < 0.702),
        ("0.702 - 0.786", lambda d0: 0.702 <= d0 < 0.786),
        ("0.786 - 0.886", lambda d0: 0.786 <= d0 < 0.886),
        ("past 0.886 and back", lambda d0: d0 >= 0.886),
    ]
    print(f"      {'turned from':<24} {'n':>4} {'share of the winners':>21}")
    for name, pred in bands:
        grp = [x for x in turned if pred(x[0])]
        print(f"      {name:<24} {len(grp):>4} {_pct(len(grp), len(turned)):>21}")
    print(
        f"      {'never reached 1R':<24} {never:>4}   ({_pct(never, len(depths)).strip()} "
        f"of all {len(depths)})"
    )

    # ── 6g. THE HIGHER-TIMEFRAME TREND ───────────────────────────────────────
    if trends:
        print("\n6g. TREND ALIGNMENT — the canonical structure engine run on each timeframe,")
        print("    read off the last bar that had CLOSED before the setup filled.")
        print("    ⚠ This is a FADE. 'with' means the higher timeframe was already going the way")
        print("      the trade wants; 'against' means the trade is fading that timeframe too.")
        for name, _k, _m in _TF_MINUTES:
            tr = trends[name]

            def _key(s0, r, f0, _tr=tr):
                v = _tr[f0[0]]
                return (
                    "with the trend"
                    if v == s0.dir
                    else "against the trend"
                    if v == -s0.dir
                    else "no trend yet"
                )

            _breakdown(
                f"{name.upper()} TREND",
                _grp(_key, order=["with the trend", "against the trend", "no trend yet"]),
                base_n,
                base_hit1,
            )

        def _agree_n(s0, f0):
            return sum(1 for nm in ("1h", "4h", "daily", "weekly") if trends[nm][f0[0]] == s0.dir)

        _breakdown(
            "HOW MANY OF 1h/4h/DAILY/WEEKLY AGREE WITH THE TRADE",
            _grp(lambda s0, r, f0: f"{_agree_n(s0, f0)} of 4"),
            base_n,
            base_hit1,
        )

    # ── 6d. STACKING THE FILTERS ─────────────────────────────────────────────
    # The univariate table says which single conditions look better than the pool. This asks the
    # only question that matters after it: does anything survive being stacked, and is what
    # survives still big enough to be a strategy. Filters are added CUMULATIVELY in the order
    # their single-variable edge was largest, so each row's cost in sample size is visible.
    print("\n6d. STACKING THEM — cumulative, strongest first. Does anything survive?")
    print(
        f"      {'filter added':<40} {'n':>4} {'>=1R':>7} {'1R rule':>9} {'2R rule':>9}"
        f" {'best short rule':>16}"
    )
    _stack = [
        ("(everything)", lambda s0, f0: True),
        ("an order block sits in the zone", lambda s0, f0: s0.ob),
        ("not 10:00-12:00 New York", lambda s0, f0: not (10 <= gates["hour"].get(f0[0], -1) < 12)),
        (
            "the daily trend is not against it",
            lambda s0, f0: not trends or trends["daily"][f0[0]] != -s0.dir,
        ),
        (
            "the 4h trend is not against it",
            lambda s0, f0: not trends or trends["4h"][f0[0]] != -s0.dir,
        ),
        ("1R under $10", lambda s0, f0: f0[3] < 10),
    ]
    keep = list(base_fills)
    for label, pred in _stack:
        keep = [(s0, f0) for s0, f0 in keep if pred(s0, f0)]
        if not keep:
            print(f"      {label:<40} {0:>4}")
            break
        res = _run(tape, keep, args.horizon)
        h1 = sum(1 for r in res if r["mfe_r"] >= 1.0)
        r1 = _tot(_run(tape, keep, args.horizon, target_r=1.0))
        r2 = _tot(_run(tape, keep, args.horizon, target_r=2.0))
        tot, blabel, _rule, _r = _best_rule(tape, keep, args.horizon)
        short = [x for x in (0.75, 1.0, 1.5, 2.0) for _ in (0,)]
        bs = max(
            (
                (_tot(_run(tape, keep, args.horizon, target_r=t, be_at=b)), t, b)
                for t in (0.75, 1.0, 1.5, 2.0)
                for b in _BES
            ),
            key=lambda x: x[0],
        )
        print(
            f"      {label:<40} {len(keep):>4} {_pct(h1, len(keep))} {r1:>9.1f} {r2:>9.1f}"
            f"   {bs[1]:.2f}R/BE {bs[2] if bs[2] else 'off'} = {bs[0]:.1f}R"
        )

    # ── 7. ENTRY GATES ───────────────────────────────────────────────────────
    print("\n7. ENTRY GATES — the two refusals the A+ bot already applies, read at the FILL bar")
    print(f"      {'gates':<38} {'trades':>7} {'best rule':<44} {'net R':>8}")
    for gname, no_late, veto in (
        ("none", False, False),
        ("no entry 16:00-18:00 New York", True, False),
        ("respect the divergence / RSI veto", False, True),
        ("both", True, True),
    ):
        fs2 = [(s0, f0) for s0, f0 in base_fills if _gate_ok(gates, s0, f0, no_late, veto)]
        if not fs2:
            continue
        tot, label, _rule, _res = _best_rule(tape, fs2, args.horizon)
        print(f"      {gname:<38} {len(fs2):>7} {label:<44} {tot:>8.1f}")

    # ── 7. ONE SLOT ──────────────────────────────────────────────────────────
    if args.one_slot:
        print("\n6. ONE SLOT — the same rules again, but the bot may hold only one trade at a time")
        for name, rule in (
            (f"plain target {best[1]:.2f}R", dict(target_r=best[1])),
            (
                f"target {be_best[0]:.2f}R + breakeven {be_best[1] or 'off'}",
                dict(target_r=be_best[0], be_at=be_best[1]),
            ),
            (
                f"bank {lad_best[2]:.0%} at {lad_best[1]:.2f}R, runner {lad_best[3]:.2f}R",
                dict(
                    target_r=lad_best[3], tp1_r=lad_best[1], tp1_pct=lad_best[2], be_at=lad_best[4]
                ),
            ),
        ):
            res = _run(tape, fs, args.horizon, **rule)
            order = sorted(range(len(res)), key=lambda k: res[k]["i0"])
            taken, busy_until = [], -1
            for k in order:
                if res[k]["i0"] <= busy_until:
                    continue
                taken.append(res[k])
                busy_until = res[k]["exit_i"]
            screen = _tot(res)
            print(
                f"   {name:<52} screen {screen:>7.1f}R over {len(res)} "
                f"-> one slot {_tot(taken):>7.1f}R over {len(taken)}"
            )

    print(
        "\n⚠ A SCREEN IS AN UPPER BOUND, and every cell above is a reconstruction. Replay the "
        "winner before believing it:"
    )
    print("    python3 backtest/tools/exit_audit.py --set exec_req_fvg=False --set ...")
    return 0


def _hours_to(tape: Tape, s: Setup, filled, level_r: float) -> float:
    """Hours from the fill to the first bar whose favourable extreme reached `level_r`.

    Its own scan rather than a value threaded out of `walk`, because `walk` is run once per RULE
    and this question is asked of the rule-free path. The fill bar is skipped for the same reason
    it is there: its extreme is the approach, not the trade's move.
    """
    i0, e, _st, risk = filled
    d = s.dir
    for i in range(i0 + 1, min(i0 + 100_000, tape.n)):
        fav = (tape.h[i] - e) / risk if d > 0 else (e - tape.l[i]) / risk
        if fav >= level_r:
            return (i - i0) * 0.25
    return float("nan")


if __name__ == "__main__":
    raise SystemExit(main())
