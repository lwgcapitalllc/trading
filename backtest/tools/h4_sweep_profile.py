#!/usr/bin/env python3
"""h4_sweep_profile.py — measure what price actually DOES after an H4 liquidity sweep,
before anyone writes an entry rule.

This is a study, not a strategy. It answers one question: after price takes out an H4
high or low, does it CONTINUE through, or does it revert? And — the part that decides
whether any of it is worth building — is either answer different from what an ordinary
H4 candle does anyway?

That control is the whole point of the tool. The H4 level this repo draws is the
PREVIOUS H4 CANDLE's high/low, and the sweep rule is a bare wick through it (see
`SWEEP_HIGH` in engines/liquidity/types.py — the close-back-inside guard was dropped
2026-07-06). A level that close to the last candle gets taken on a large fraction of
candles, so "62% continued" means nothing until you know a random H4 candle scores 59%.
Every headline number below is printed next to its control.

It reads the cached broker bars off disk (`backtest/cache/`), so it runs on a laptop
with no MT5 and no VPS. It imports none of the `engines/` — this is deliberately a pure
price-and-level measurement, so nothing here can inherit a bug from the structure stack,
and any edge it finds is an edge in the LEVEL.

Two level definitions are measured side by side, because they may not behave the same
and picking one up front is how a study gets a fitted answer:

  prev      the previous H4 candle's high/low — what mpc_jarvis.pine draws today.
  pivot     an H4 swing pivot high/low (`--pivot-len` bars either side, Pine's
            ta.pivothigh convention: ties allowed on the left, strict extreme on the
            right). Rarer, older, and the level real stops actually rest on. The most
            recent unswept pivot per side is the live level.

Definitions, all on the broker's own H4 candles (their boundaries shift with the
broker's DST, exactly as the TradingView "240" chart shows them):

  sweep       the bar's high traded above the live high level, or its low below the low
              level. Wick alone — no close-back requirement, matching the engine.
  wick        a sweep whose bar CLOSED back inside the level (the classic grab).
  break       a sweep whose bar CLOSED beyond the level.
  depth       how far past the level the extreme ran, in ATR(14) H4 units.
  cont        the direction of the sweep push. A high sweep continues UP.
  rev         the opposite direction.
  control     an H4 bar that swept NOTHING under this definition. Its "cont" direction
              is its own body direction, which is the closest honest analogue to "the
              bar pushed that way".

Everything in price terms is normalised by ADR20 (the 20-day mean daily range, prior
days only, NY dates). Gold ran at $1,200 in 2018 and $4,000 today — a raw dollar move is
not comparable across the sample and would make every recent year look like the edge grew.

The naive trade table is a crude sanity check, not a proposed strategy: at the sweep
bar's close take the continuation trade (and, separately, the reversal trade), stop at
the sweep bar's opposite/same extreme, target a multiple of that risk, give up after
`--horizon` H4 bars. Fills are resolved on the M15 stream so the stop-vs-target order
inside an H4 candle is not guessed; if one M15 bar holds both, the STOP wins.

Usage:
    command-center/backend/.venv/bin/python backtest/tools/h4_sweep_profile.py
    ... --start 2020-01-01 --target-r 2 --pivot-len 3
    ... --out backtest/reports/h4_sweep
"""

from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
CACHE = _ROOT / "backtest" / "cache"

# The oldest cache feed_version whose TIMESTAMPS this study can trust. A FLOOR, never an
# equality — a newer cache is newer for reasons that have nothing to do with the clock.
MIN_FEED_VERSION = 2

# A forward move smaller than this (in ADR20 units) is called "neither" rather than
# forced into continued/reverted. Without it, noise around zero votes 50/50 and every
# table reads as a coin flip with extra steps.
FLAT_ADR = 0.25

# ATR and ADR lookbacks. Both are prior-bars-only — nothing here may see its own bar.
ATR_LEN = 14
ADR_LEN = 20

# Session buckets by the sweep bar's NY hour. Deliberately coarse: this is a split, not
# the sessions engine, and importing that engine is exactly what the docstring forbids.
SESSIONS = (("Asia", 19, 3), ("London", 3, 8), ("NY", 8, 17), ("Late", 17, 19))


# ---------------------------------------------------------------------------
# data


@dataclass(frozen=True)
class Bar:
    t: dt.datetime  # NY-localised open time
    open: float
    high: float
    low: float
    close: float


def load_bars(symbol: str, tf: str) -> list[Bar]:
    """Read the cached bars and localise them to NY.

    The cache stamps bars in true UTC from feed_version 2 onward. Anything older is the
    broker-local-timestamp era and every session split in this study would be silently
    wrong, so refuse it rather than report a plausible-looking lie.

    ⚠ The floor is a MINIMUM, not an equality, and it was written as `!= 2` until
    2026-08-13 — which bricked this study the day `FEED_VERSION` went to 3 for a reason
    that has nothing to do with time (v3 added the VOLUME column; the timestamps did not
    move). This tool reads price and the clock only, so v3 is strictly better input than
    the v2 it demanded. Worse than the refusal was its MESSAGE: it blamed broker-local
    timestamps, sending the reader off to re-pull 186k bars to fix a bug in this line.
    Pin a floor when you mean a floor.
    """
    path = CACHE / f"{symbol}__{tf}.csv"
    meta = CACHE / f"{symbol}__{tf}.meta.json"
    if not path.exists():
        raise SystemExit(f"no cached bars at {path} — pull them with the MT5 agent first")
    if meta.exists():
        # Missing key == pre-sidecar == the version-1 era, same default backtest/data/cache.py uses.
        version = json.loads(meta.read_text()).get("feed_version", 1)
        if version < MIN_FEED_VERSION:
            raise SystemExit(
                f"{path.name} is feed_version {version}; this study needs at least "
                f"{MIN_FEED_VERSION} (true UTC). Re-pull the bars — version 1 bars are "
                "stamped in broker-local time and every hour in this report would be off "
                "by the broker's offset."
            )

    bars: list[Bar] = []
    with path.open() as fh:
        for row in csv.DictReader(fh):
            t = dt.datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            bars.append(
                Bar(
                    t.astimezone(NY),
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                )
            )
    bars.sort(key=lambda b: b.t)
    return bars


# ---------------------------------------------------------------------------
# derived series — all strictly prior-bar, no lookahead


def true_ranges(bars: list[Bar]) -> list[Optional[float]]:
    """ATR(14) as of the bar BEFORE each index. Simple mean of true range, not Wilder —
    this only ever buckets sweep depth, so the smoothing family is immaterial and a
    plain mean is the one a reader can check by hand."""
    tr: list[float] = []
    out: list[Optional[float]] = []
    prev_close: Optional[float] = None
    for b in bars:
        out.append(statistics.fmean(tr[-ATR_LEN:]) if len(tr) >= ATR_LEN else None)
        rng = b.high - b.low
        if prev_close is not None:
            rng = max(rng, abs(b.high - prev_close), abs(b.low - prev_close))
        tr.append(rng)
        prev_close = b.close
    return out


def adr_series(bars: list[Bar]) -> list[Optional[float]]:
    """ADR20 as of each bar, built from COMPLETED prior NY days only.

    A bar on 12 March may only use days up to 11 March. The current day's range is not
    known while the day is running, and letting it in would be a lookahead that flatters
    every normalised number in the report.
    """
    day_range: dict[dt.date, tuple[float, float]] = {}
    order: list[dt.date] = []
    for b in bars:
        d = b.t.date()
        if d not in day_range:
            day_range[d] = (b.high, b.low)
            order.append(d)
        else:
            hi, lo = day_range[d]
            day_range[d] = (max(hi, b.high), min(lo, b.low))

    ranges = {d: day_range[d][0] - day_range[d][1] for d in order}
    pos = {d: i for i, d in enumerate(order)}

    out: list[Optional[float]] = []
    for b in bars:
        i = pos[b.t.date()]
        prior = [ranges[d] for d in order[max(0, i - ADR_LEN) : i]]
        out.append(statistics.fmean(prior) if len(prior) >= 5 else None)
    return out


def ema(bars: list[Bar], length: int) -> list[Optional[float]]:
    """EMA of close as of the bar BEFORE each index — the trend context a bar could
    actually have known when it opened."""
    k = 2.0 / (length + 1)
    out: list[Optional[float]] = []
    val: Optional[float] = None
    seed: list[float] = []
    for b in bars:
        out.append(val)
        if val is None:
            seed.append(b.close)
            if len(seed) == length:
                val = statistics.fmean(seed)
        else:
            val = b.close * k + val * (1 - k)
    return out


# ---------------------------------------------------------------------------
# level definitions


def prev_levels(bars: list[Bar]) -> list[tuple[Optional[float], Optional[float]]]:
    """Definition (a): the live level on bar i is bar i-1's high / low. This is the
    `h4_high` / `h4_low` the liquidity engine creates on every H4 roll."""
    out: list[tuple[Optional[float], Optional[float]]] = [(None, None)]
    for prev in bars[:-1]:
        out.append((prev.high, prev.low))
    return out


def pivot_levels(bars: list[Bar], length: int) -> list[tuple[Optional[float], Optional[float]]]:
    """Definition (b): the live level on bar i is the most recent CONFIRMED, still-unswept
    swing pivot on each side.

    Pivot rule is Pine's `ta.pivothigh` / `ta.pivotlow`, which this repo already fixed
    once (engines/equal_highs_lows/, 2026-07-19): a tie is allowed on the LEFT of the
    centre but the right side must be a STRICT extreme, so the LAST bar of an equal run
    is the pivot. Strict-both-sides silently drops the frequent raw-price ties on gold.

    A pivot centred on bar p is only confirmed at bar p+length, so the level first
    becomes live on bar p+length+1 — non-repainting by construction.
    """
    n = len(bars)
    out: list[tuple[Optional[float], Optional[float]]] = []
    live_high: Optional[float] = None
    live_low: Optional[float] = None

    for i in range(n):
        # Publish the level BEFORE this bar is allowed to sweep it.
        out.append((live_high, live_low))

        # Retire a level this bar takes, so the next pivot can become live.
        if live_high is not None and bars[i].high > live_high:
            live_high = None
        if live_low is not None and bars[i].low < live_low:
            live_low = None

        # A pivot centred at i-length is confirmed now; adopt it for the next bar.
        p = i - length
        if p - length < 0:
            continue
        left = bars[p - length : p]
        right = bars[p + 1 : i + 1]
        c = bars[p]
        if all(b.high <= c.high for b in left) and all(b.high < c.high for b in right):
            live_high = c.high
        if all(b.low >= c.low for b in left) and all(b.low > c.low for b in right):
            live_low = c.low

    return out


# ---------------------------------------------------------------------------
# events


def session_of(t: dt.datetime) -> str:
    h = t.hour
    for name, start, end in SESSIONS:
        if start < end:
            if start <= h < end:
                return name
        elif h >= start or h < end:
            return name
    return "?"


def build_rows(
    bars: list[Bar],
    levels: list[tuple[Optional[float], Optional[float]]],
    horizons: tuple[int, ...],
) -> list[dict]:
    """One row per H4 bar — sweep or not. Control rows are produced by the SAME code
    path as event rows so nothing can differ between them except the event flag."""
    atr = true_ranges(bars)
    adr = adr_series(bars)
    trend = ema(bars, 50)
    rows: list[dict] = []
    max_h = max(horizons)

    for i, b in enumerate(bars):
        a = adr[i]
        if a is None or a <= 0 or i + max_h >= len(bars):
            continue
        lvl_hi, lvl_lo = levels[i]

        swept_high = lvl_hi is not None and b.high > lvl_hi
        swept_low = lvl_lo is not None and b.low < lvl_lo

        if swept_high and swept_low:
            # Both sides taken in one candle. Attribute it to the side price ran
            # FURTHEST past, in ATR terms — an outside bar is one event, not two, and
            # counting it twice would double-weight the most volatile candles.
            up = (b.high - lvl_hi) / (atr[i] or 1.0)
            dn = (lvl_lo - b.low) / (atr[i] or 1.0)
            swept_high, swept_low = (up >= dn), (up < dn)
            outside = True
        else:
            outside = False

        if swept_high:
            side, level, extreme, cont_dir = "high", lvl_hi, b.high, 1
        elif swept_low:
            side, level, extreme, cont_dir = "low", lvl_lo, b.low, -1
        else:
            # Control row. Direction is the bar's own body — the closest honest analogue
            # to "the bar pushed that way" available without an event.
            side, level, extreme = "none", None, None
            cont_dir = 1 if b.close > b.open else (-1 if b.close < b.open else 0)

        if cont_dir == 0:
            continue

        row = {
            "time": b.t.isoformat(),
            "year": b.t.year,
            "session": session_of(b.t),
            "is_sweep": side != "none",
            "side": side,
            "outside_bar": outside,
            "cont_dir": cont_dir,
            "close": b.close,
            "bar_high": b.high,
            "bar_low": b.low,
            "adr20": round(a, 3),
            "atr14": round(atr[i], 3) if atr[i] else None,
            "bar_index": i,
        }

        if side != "none":
            # "wick" = closed back inside the level, the classic grab. "break" = closed
            # beyond it. This is the split most SMC material treats as decisive, so it
            # gets measured rather than assumed.
            closed_beyond = b.close > level if side == "high" else b.close < level
            row["sweep_class"] = "break" if closed_beyond else "wick"
            row["depth_atr"] = abs(extreme - level) / atr[i] if atr[i] else None
            row["level"] = level
        else:
            row["sweep_class"] = "control"
            row["depth_atr"] = None
            row["level"] = None

        # Trend agreement — does the continuation direction run WITH the H4 EMA50?
        row["trend_agrees"] = None if trend[i] is None else (cont_dir > 0) == (b.close > trend[i])
        # Does the bar's own body agree with the continuation direction? On a wick sweep
        # it usually will not, and that is the interesting cell.
        row["body_agrees"] = (b.close - b.open) * cont_dir > 0

        # --- what came after, signed in the CONTINUATION direction throughout
        for h in horizons:
            fwd = bars[i + 1 : i + 1 + h]
            move = (fwd[-1].close - b.close) * cont_dir
            # Written out rather than compressed: MFE is the best excursion in the
            # continuation direction, MAE the worst against it.
            if cont_dir > 0:
                mfe = max(x.high for x in fwd) - b.close
                mae = b.close - min(x.low for x in fwd)
            else:
                mfe = b.close - min(x.low for x in fwd)
                mae = max(x.high for x in fwd) - b.close
            row[f"move_{h}_adr"] = move / a
            row[f"mfe_{h}_adr"] = mfe / a
            row[f"mae_{h}_adr"] = mae / a
            row[f"outcome_{h}"] = (
                "continued"
                if move / a >= FLAT_ADR
                else "reverted"
                if move / a <= -FLAT_ADR
                else "neither"
            )
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# the naive trade — resolved on M15 so the intrabar order is measured, not guessed


class M15Index:
    def __init__(self, bars: list[Bar]) -> None:
        self.bars = bars
        self.times = [b.t for b in bars]

    def slice(self, start: dt.datetime, end: dt.datetime) -> list[Bar]:
        lo = bisect.bisect_left(self.times, start)
        hi = bisect.bisect_left(self.times, end)
        return self.bars[lo:hi]


def simulate(
    row: dict, h4: list[Bar], m15: M15Index, horizon: int, target_r: float, direction: int
) -> Optional[dict]:
    """One naive trade. `direction` is +1 to take the continuation, -1 the reversal.

    Entry is the sweep bar's close. The stop is the sweep bar's far extreme relative to
    the trade — a continuation long risks the bar's low, a reversal short risks the
    bar's high. Both sides use the same rule so neither can be quietly favoured.

    When one M15 bar contains both the stop and the target we book the STOP. A bar
    cannot say which came first, and an optimistic guess there is exactly how a study
    talks itself into an edge.
    """
    i = row["bar_index"]
    side = row["cont_dir"] * direction
    entry = row["close"]
    stop = row["bar_low"] if side > 0 else row["bar_high"]
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    target = entry + side * risk * target_r

    start = h4[i + 1].t
    end = h4[min(i + horizon, len(h4) - 1)].t + dt.timedelta(hours=4)
    path = m15.slice(start, end)
    if not path:
        return None

    for bar in path:
        hit_stop = bar.low <= stop if side > 0 else bar.high >= stop
        hit_target = bar.high >= target if side > 0 else bar.low <= target
        if hit_stop:
            return {"r": -1.0, "outcome": "stop"}
        if hit_target:
            return {"r": target_r, "outcome": "target"}
    return {"r": side * (path[-1].close - entry) / risk, "outcome": "timed_out"}


@dataclass(frozen=True)
class TradePlan:
    """Everything that turns one H4 sweep event into one trade.

    Split out from `ConfirmCfg` on 2026-07-31 so the exit and the stop geometry became
    SWEEPABLE. The first pass only ever varied the entry retrace, and every value of it
    tested (0.5 / 0.618 / 0.786) makes the stop SMALLER — which pushes the cost drag the
    wrong way on an edge whose whole problem is cost. `entry_mode="market"` and the
    runner exits below open the directions that were missing.
    """

    direction: int = -1  # -1 = fade the sweep, +1 = continue through it
    confirm_bars: int = 16  # M15 bars allowed for acceptance
    fill_bars: int = 16  # M15 bars the limit rests before cancellation
    entry_mode: str = "limit"  # "limit" = retrace into the leg | "market" = confirm close
    retrace: float = 0.5  # limit only. risk = leg × (1 − retrace), so SMALLER = wider stop
    stop_model: str = "leg"  # "leg" = the leg origin | "atr" = H4 ATR(14) × stop_atr
    stop_atr: float = 1.0
    min_stop_pct: float = 0.1  # the repo's own guard, as % of price
    horizon: int = 4  # H4 bars from the sweep before the trade is given up
    target_r: float = 2.0  # 0 = no ceiling; the runner exits on trail or horizon
    be_at_r: float = 0.0  # move the stop to entry once this much R is seen (0 = off)
    trail_mode: str = "none"  # "none" | "pct" (of price) | "atr" (H4 ATR14 multiple)
    trail_val: float = 0.0


def run_trade(
    row: dict, h4: list[Bar], m15: M15Index, plan: TradePlan, cost: float
) -> Optional[dict]:
    """Simulate one trade off one sweep event. The single trade implementation in this
    tool — `simulate_confirmed` is a thin call into it, so the study's published numbers
    and any sweep run share one code path and cannot drift apart.

    Pessimistic conventions throughout, because an optimistic one is how a study talks
    itself into an edge:
      · the stop is checked BEFORE this bar's extreme is allowed to advance the trail,
        so a bar can never protect itself with its own favourable excursion;
      · when one M15 bar holds both the stop and the target, the STOP books;
      · the entry limit may fill and stop out on the same bar.

    Returns R gross and R net of `cost` (a round-trip in price units). Net is the number
    that matters — the stop here is a few dollars of gold and a fixed cost is a large
    slice of 1R.
    """
    i = row["bar_index"]
    d = row["cont_dir"] * plan.direction
    origin = row["bar_low"] if d > 0 else row["bar_high"]
    trigger = row["bar_high"] if d > 0 else row["bar_low"]
    atr = row.get("atr14")

    start = h4[i + 1].t
    end = h4[min(i + plan.horizon, len(h4) - 1)].t + dt.timedelta(hours=4)
    path = m15.slice(start, end)
    if not path:
        return None

    # --- acceptance beyond the swept extreme
    leg_end = trigger
    confirmed_at = None
    for k, bar in enumerate(path[: plan.confirm_bars]):
        leg_end = max(leg_end, bar.high) if d > 0 else min(leg_end, bar.low)
        origin = min(origin, bar.low) if d > 0 else max(origin, bar.high)
        if (bar.close > trigger) if d > 0 else (bar.close < trigger):
            confirmed_at = k
            break
    if confirmed_at is None:
        return {"outcome": "no_confirm", "r": None}

    leg = abs(leg_end - origin)
    if leg <= 0:
        return {"outcome": "no_leg", "r": None}

    if plan.entry_mode == "market":
        entry = path[confirmed_at].close
    else:
        entry = leg_end - d * leg * plan.retrace

    if plan.stop_model == "atr":
        if not atr:
            return {"outcome": "no_atr", "r": None}
        stop = entry - d * atr * plan.stop_atr
    else:
        stop = origin

    risk = abs(entry - stop)
    if risk <= 0 or risk < entry * plan.min_stop_pct / 100.0:
        return {"outcome": "stop_too_tight", "r": None}
    target = entry + d * risk * plan.target_r if plan.target_r > 0 else None

    def book(r: float, outcome: str) -> dict:
        return {"outcome": outcome, "r": r, "r_net": r - cost / risk, "risk": risk}

    rest = path[confirmed_at:] if plan.entry_mode == "market" else path[confirmed_at + 1 :]
    filled = plan.entry_mode == "market"
    run_extreme = entry

    for k, bar in enumerate(rest):
        if not filled:
            if k >= plan.fill_bars:
                return {"outcome": "no_fill", "r": None}
            if (bar.low <= entry) if d > 0 else (bar.high >= entry):
                filled = True  # the fill bar can still stop us out — stop wins below
            else:
                continue

        if bar.low <= stop if d > 0 else bar.high >= stop:
            return book((stop - entry) * d / risk, "stop" if stop != entry else "breakeven")
        if target is not None and (bar.high >= target if d > 0 else bar.low <= target):
            return book(plan.target_r, "target")

        # Only now may this bar's own excursion move the stop.
        run_extreme = max(run_extreme, bar.high) if d > 0 else min(run_extreme, bar.low)
        if plan.be_at_r > 0 and abs(run_extreme - entry) >= plan.be_at_r * risk:
            stop = max(stop, entry) if d > 0 else min(stop, entry)
        if plan.trail_mode != "none" and plan.trail_val > 0:
            dist = (
                bar.close * plan.trail_val / 100.0
                if plan.trail_mode == "pct"
                else (atr or 0.0) * plan.trail_val
            )
            if dist > 0:
                trail = run_extreme - d * dist
                stop = max(stop, trail) if d > 0 else min(stop, trail)

    if not filled:
        return {"outcome": "no_fill", "r": None}
    return book(d * (rest[-1].close - entry) / risk, "timed_out")


def simulate_confirmed(
    row: dict, h4: list[Bar], m15: M15Index, cfg: "ConfirmCfg", target_r: float, direction: int
) -> Optional[dict]:
    """The trade the chosen DESIGN actually implies: H4 sweep for context, 15m for entry.

    The blind version above enters at the sweep bar's close — the worst price on the bar
    — with a full-bar stop, so it under-rates the idea and a null result there proves
    less than it looks. This one is the real shape:

      1. the H4 bar sweeps the level;
      2. within `confirm_bars` M15 bars an M15 bar CLOSES beyond the swept extreme, in
         the continuation direction — price ACCEPTING past the level, which is the
         confirmation every version of this setup asks for;
      3. a resting limit waits at `retrace` of the displacement leg (leg origin = the
         sweep bar's far extreme, leg end = the running extreme at confirmation);
      4. stop at the leg origin, target a multiple of that risk.

    `direction` = -1 runs the mirror image: confirmation is a close back beyond the
    sweep bar's FAR extreme and the trade is the reversal. Both sides share this code so
    neither can be quietly favoured.

    The min-stop floor is not optional. A limit that fills close to its own stop makes
    `qty = risk / distance` explode; it has detonated two bots in this repo already
    (A+ Run 4, BOS Run 1). Trades under the floor are dropped and counted, not clipped.
    """
    plan = TradePlan(
        direction=direction,
        confirm_bars=cfg.confirm_bars,
        fill_bars=cfg.fill_bars,
        entry_mode="limit",
        retrace=cfg.retrace,
        stop_model="leg",
        min_stop_pct=cfg.min_stop_pct,
        horizon=cfg.horizon,
        target_r=target_r,
    )
    return run_trade(row, h4, m15, plan, cost=0.0)


@dataclass(frozen=True)
class ConfirmCfg:
    horizon: int
    confirm_bars: int
    fill_bars: int
    retrace: float
    min_stop_pct: float


# ---------------------------------------------------------------------------
# aggregation helpers


def _mean(rows: Iterable[dict], key: str) -> float:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return statistics.fmean(vals) if vals else float("nan")


def _median(rows: Iterable[dict], key: str) -> float:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return statistics.median(vals) if vals else float("nan")


def _share(rows: list[dict], key: str, value) -> float:
    if not rows:
        return float("nan")
    return 100.0 * sum(1 for r in rows if r.get(key) == value) / len(rows)


def _fmt(x: float, places: int = 3) -> str:
    return "—" if x != x else f"{x:+.{places}f}"


def table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def outcome_row(label: str, rows: list[dict], h: int) -> list[str]:
    return [
        label,
        str(len(rows)),
        f"{_share(rows, f'outcome_{h}', 'continued'):.1f}",
        f"{_share(rows, f'outcome_{h}', 'reverted'):.1f}",
        f"{_share(rows, f'outcome_{h}', 'neither'):.1f}",
        _fmt(_mean(rows, f"move_{h}_adr")),
        _fmt(_median(rows, f"move_{h}_adr")),
        _fmt(_mean(rows, f"mfe_{h}_adr")),
        _fmt(_mean(rows, f"mae_{h}_adr")),
    ]


OUTCOME_HEADERS = [
    "slice",
    "n",
    "cont %",
    "rev %",
    "flat %",
    "mean move",
    "med move",
    "mean MFE",
    "mean MAE",
]


# ---------------------------------------------------------------------------
# report


def report(
    name: str,
    rows: list[dict],
    h4: list[Bar],
    m15: M15Index,
    horizons: tuple[int, ...],
    horizon: int,
    target_r: float,
    cfg: "ConfirmCfg",
    cost: float,
    out: list[str],
) -> None:
    sweeps = [r for r in rows if r["is_sweep"]]
    control = [r for r in rows if not r["is_sweep"]]
    wicks = [r for r in sweeps if r["sweep_class"] == "wick"]
    breaks = [r for r in sweeps if r["sweep_class"] == "break"]

    out.append(f"\n\n## Definition: {name}\n")
    out.append(
        f"{len(rows)} usable H4 bars · **{len(sweeps)} swept "
        f"({100 * len(sweeps) / max(1, len(rows)):.1f}% of bars)** · "
        f"{len(control)} control · {len(wicks)} wick / {len(breaks)} break"
    )
    if len(sweeps) / max(1, len(rows)) > 0.5:
        out.append(
            "\n⚠ More than half of all H4 bars fire this event. It is close to a "
            "base rate, not a rare signal — read every row against the control."
        )

    out.append("\n### Forward outcome, signed in the continuation direction\n")
    out.append(
        "`cont %` = closed ≥ +0.25 ADR further in the sweep's direction. "
        "`rev %` = closed ≥ 0.25 ADR back. Control rows use the bar's own body "
        "direction.\n"
    )
    for h in horizons:
        out.append(f"\n**+{h} H4 bar{'s' if h > 1 else ''} ({h * 4}h)**\n")
        out.append(
            table(
                OUTCOME_HEADERS,
                [
                    outcome_row("sweep (all)", sweeps, h),
                    outcome_row("  · wick (closed back in)", wicks, h),
                    outcome_row("  · break (closed beyond)", breaks, h),
                    outcome_row("CONTROL (no sweep)", control, h),
                ],
            )
        )

    # ---- splits, all at the single reporting horizon
    h = horizon
    out.append(f"\n### Splits — sweeps only, +{h} H4 bars\n")

    def cuts() -> Iterable[tuple[str, list[dict]]]:
        yield "high sweep (cont = long)", [r for r in sweeps if r["side"] == "high"]
        yield "low sweep (cont = short)", [r for r in sweeps if r["side"] == "low"]
        for s in ("Asia", "London", "NY", "Late"):
            yield f"session {s}", [r for r in sweeps if r["session"] == s]
        yield "trend agrees (H4 EMA50)", [r for r in sweeps if r["trend_agrees"] is True]
        yield "trend against", [r for r in sweeps if r["trend_agrees"] is False]
        yield "body agrees", [r for r in sweeps if r["body_agrees"]]
        yield "body against", [r for r in sweeps if not r["body_agrees"]]
        yield "outside bar (both sides)", [r for r in sweeps if r["outside_bar"]]
        depths = sorted(r["depth_atr"] for r in sweeps if r["depth_atr"] is not None)
        if len(depths) >= 40:
            lo, hi = depths[len(depths) // 4], depths[3 * len(depths) // 4]
            yield (
                "shallow poke (bottom 25%)",
                [r for r in sweeps if r["depth_atr"] is not None and r["depth_atr"] <= lo],
            )
            yield (
                "deep poke (top 25%)",
                [r for r in sweeps if r["depth_atr"] is not None and r["depth_atr"] >= hi],
            )

    out.append(table(OUTCOME_HEADERS, [outcome_row(lbl, sub, h) for lbl, sub in cuts() if sub]))

    out.append(f"\n### Out-of-sample — sweeps only, +{h} H4 bars\n")
    out.append(
        "A split that changes sign between the halves is regime, not edge. This "
        "is the check the BOS regime run failed.\n"
    )
    years = sorted({r["year"] for r in sweeps})
    mid = years[len(years) // 2] if years else 0
    out.append(
        table(
            OUTCOME_HEADERS,
            [
                outcome_row(f"1st half (≤{mid - 1})", [r for r in sweeps if r["year"] < mid], h),
                outcome_row(f"2nd half (≥{mid})", [r for r in sweeps if r["year"] >= mid], h),
            ]
            + [outcome_row(str(y), [r for r in sweeps if r["year"] == y], h) for y in years],
        )
    )

    # ---- the naive trades
    out.append(
        f"\n### Naive trade — entry at the sweep bar's close, "
        f"stop at the bar's far extreme, give up after {horizon} H4 bars\n"
    )
    out.append(
        "Crude on purpose, and NOT a proposed strategy — no costs, no filter, no "
        "exit ladder. It exists so a promising outcome table has to survive "
        "contact with a stop. Fills resolved on M15; stop wins an ambiguous bar.\n"
    )
    trade_rows = []
    for tr in sorted({1.0, 2.0, 3.0, target_r}):
        for label, direction, subset in (
            ("continuation", 1, sweeps),
            ("reversal", -1, sweeps),
            ("control (cont dir)", 1, control),
        ):
            res = [t for t in (simulate(r, h4, m15, horizon, tr, direction) for r in subset) if t]
            if not res:
                continue
            rs = [t["r"] for t in res]
            trade_rows.append(
                [
                    f"{label} @ {tr:g}R",
                    str(len(res)),
                    f"{100 * sum(1 for t in res if t['outcome'] == 'target') / len(res):.1f}",
                    f"{100 * sum(1 for t in res if t['outcome'] == 'stop') / len(res):.1f}",
                    _fmt(statistics.fmean(rs), 3),
                    f"{sum(rs):+.1f}",
                ]
            )
    out.append(table(["trade", "n", "target %", "stop %", "exp R", "sum R"], trade_rows))

    # ---- the confirmed trade — the shape the design actually calls for
    out.append("\n### Confirmed trade — H4 sweep for context, 15m for entry\n")
    out.append(
        f"Acceptance beyond the swept extreme within {cfg.confirm_bars} M15 bars, "
        f"then a resting limit at {cfg.retrace:g} of the displacement leg, stop at "
        f"the leg origin, min-stop floor {cfg.min_stop_pct:g}% of price, give up "
        f"after {cfg.horizon} H4 bars. Still no costs and no exit ladder — but this "
        f"is the entry price and stop the real bot would get, so a null result here "
        f"is worth much more than a null on the blind trade above.\n"
    )
    conf_rows = []
    for tr in sorted({2.0, 3.0, target_r}):
        # The side split is not optional. Gold ran 1,200 → 4,100 across this window, so
        # "the reversal works" can just be "longs work", which is the regime talking.
        # bos Run 3 flagged the same confound and sos_fade/CLAUDE.md records its
        # mirror image on the A+ short skew.
        for label, direction, subset in (
            ("continuation", 1, sweeps),
            ("reversal", -1, sweeps),
            ("  · rev after HIGH sweep = short", -1, [r for r in sweeps if r["side"] == "high"]),
            ("  · rev after LOW sweep = long", -1, [r for r in sweeps if r["side"] == "low"]),
            ("control (body dir)", 1, control),
        ):
            res = [
                t for t in (simulate_confirmed(r, h4, m15, cfg, tr, direction) for r in subset) if t
            ]
            taken = [(src, t) for src, t in zip(subset, res) if t["r"] is not None]
            if not taken:
                continue
            rs = [t["r"] for _, t in taken]
            # The halves are the check that kills most of what looks like an edge here.
            # A sign flip between them is regime, and this repo has been fooled by one
            # before (bos Run 3/4).
            h1 = [t["r"] for src, t in taken if src["year"] < mid]
            h2 = [t["r"] for src, t in taken if src["year"] >= mid]
            # Cost drag, and this is where a thin edge dies. The stop is half a 15m
            # displacement leg, so risk is SMALL in dollars — which means a fixed
            # round-trip cost is a LARGE fraction of 1R. Anything that survives gross
            # but not net is not a strategy.
            risks = [t["risk"] for _, t in taken]
            net = [t["r"] - cost / t["risk"] for _, t in taken]
            dropped = sum(1 for t in res if t["outcome"] == "stop_too_tight")
            conf_rows.append(
                [
                    f"{label} @ {tr:g}R",
                    f"{len(taken)} / {len(res)}",
                    f"{100 * sum(1 for _, t in taken if t['outcome'] == 'target') / len(taken):.1f}",
                    _fmt(statistics.fmean(rs), 3),
                    f"{_fmt(statistics.fmean(h1), 3) if h1 else '—'} / {len(h1)}",
                    f"{_fmt(statistics.fmean(h2), 3) if h2 else '—'} / {len(h2)}",
                    f"{statistics.median(risks):.2f}",
                    _fmt(statistics.fmean(net), 3),
                    f"{sum(net):+.1f}",
                    str(dropped),
                ]
            )
    out.append(
        table(
            [
                "trade",
                "taken / events",
                "target %",
                "exp R gross",
                f"1st half (≤{mid - 1}) / n",
                f"2nd half (≥{mid}) / n",
                "med stop $",
                f"exp R net (${cost:g} r/t)",
                "sum R net",
                "stop too tight",
            ],
            conf_rows,
        )
    )


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--start", default=None, help="YYYY-MM-DD; default = all cached bars")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD")
    ap.add_argument(
        "--pivot-len",
        type=int,
        default=2,
        help="bars either side of an H4 swing pivot (definition b)",
    )
    ap.add_argument(
        "--horizon",
        type=int,
        default=4,
        help="H4 bars held by the naive trade and used for the split tables",
    )
    ap.add_argument("--target-r", type=float, default=2.0)
    ap.add_argument(
        "--cost",
        type=float,
        default=0.30,
        help="round-trip cost in price units (gold: ~$0.30 spread+slip)",
    )
    ap.add_argument(
        "--confirm-bars",
        type=int,
        default=16,
        help="M15 bars allowed for acceptance beyond the swept extreme",
    )
    ap.add_argument(
        "--fill-bars",
        type=int,
        default=16,
        help="M15 bars the entry limit rests before it is cancelled",
    )
    ap.add_argument(
        "--retrace",
        type=float,
        default=0.5,
        help="entry retrace into the displacement leg (0.5 = midpoint)",
    )
    ap.add_argument(
        "--min-stop-pct",
        type=float,
        default=0.1,
        help="stop distance floor as %% of price — the repo's own guard",
    )
    ap.add_argument("--out", default=None, help="write the per-event CSVs to this prefix")
    args = ap.parse_args()

    h4 = load_bars(args.symbol, "H4")
    m15 = load_bars(args.symbol, "M15")

    def window(bars: list[Bar]) -> list[Bar]:
        lo = dt.date.fromisoformat(args.start) if args.start else None
        hi = dt.date.fromisoformat(args.end) if args.end else None
        return [
            b for b in bars if (lo is None or b.t.date() >= lo) and (hi is None or b.t.date() <= hi)
        ]

    h4 = window(h4)
    m15 = window(m15)
    if len(h4) < 200:
        raise SystemExit(f"only {len(h4)} H4 bars in the window — nothing to measure")

    horizons = (1, 2, 4, 8)
    if args.horizon not in horizons:
        horizons = tuple(sorted(set(horizons) | {args.horizon}))

    idx = M15Index(m15)
    cfg = ConfirmCfg(
        horizon=args.horizon,
        confirm_bars=args.confirm_bars,
        fill_bars=args.fill_bars,
        retrace=args.retrace,
        min_stop_pct=args.min_stop_pct,
    )
    out: list[str] = []
    out.append("# H4 sweep profile — " + args.symbol)
    out.append(
        f"\n{len(h4)} H4 bars, {h4[0].t.date()} → {h4[-1].t.date()} "
        f"· {len(m15)} M15 bars for fill resolution "
        f"· ADR{ADR_LEN} normalised · flat band ±{FLAT_ADR} ADR"
    )
    out.append(
        "\nThe H4 grid is the broker's own, so its boundaries shift with the "
        "broker's DST exactly as the TradingView 240 chart does."
    )

    datasets = {
        "prev H4 candle high/low (what the indicator draws)": prev_levels(h4),
        f"H4 swing pivot ({args.pivot_len} bars either side)": pivot_levels(h4, args.pivot_len),
    }
    for name, levels in datasets.items():
        rows = build_rows(h4, levels, horizons)
        report(name, rows, h4, idx, horizons, args.horizon, args.target_r, cfg, args.cost, out)
        if args.out:
            prefix = Path(args.out)
            prefix.parent.mkdir(parents=True, exist_ok=True)
            slug = "prev" if name.startswith("prev") else "pivot"
            path = prefix.with_name(prefix.name + f"_{slug}.csv")
            with path.open("w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            out.append(f"\n_per-event rows → {path}_")

    text = "\n".join(out)
    print(text)
    if args.out:
        md = Path(args.out).with_suffix(".md")
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(text)
        print(f"\n[report written to {md}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
