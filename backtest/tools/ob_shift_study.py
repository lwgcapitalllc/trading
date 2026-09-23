#!/usr/bin/env python3
"""ob_shift_study.py — does a 1-minute shift of structure INSIDE an order block reverse price?

Aaron, 2026-09-22: *"order blocks ... and the reversals from them. Like a one minute shift of
structure. I'm trying to build out a strategy on it. I need to know what's the win rates and how
effective it is."*

**WHY THIS IS NOT THE SIXTH FAILED ORDER-BLOCK RUN.** Five angles have already measured null or
negative here (`ob_opportunity.py` / `ob_confluence.py` headers hold the numbers: `Order block`
267 / +75.93R, `Either` 292 / +85.77R, a block leg on its own slot 133 / +0.02R, block presence
as a filter mildly ANTI-predictive — all against the shipped gap rule's 159 / +142.18R). Every one
of them asked *where do I rest my limit order*, i.e. the block WAS the trigger. This asks a
different question: the block is only the LOCATION, and the trigger is a 1-minute change of
character inside it. A block that price knifes through never fires; a block price reverses off
does. That is a real distinction and no tool in this repo has measured it.

**THE FOUR ARMS, AND WHY A SINGLE WIN RATE WOULD BE WORTHLESS.** A win rate for the setup alone
cannot say whether the block or the shift is carrying it, so all four corners are run:

  A  block + shift   the ask
  B  block, no shift enter blind on first touch of the zone      -> isolates what the SHIFT adds
  C  shift, no block every 1m shift anywhere on the tape         -> isolates what the BLOCK adds
  D  matched random  same side, month, NY hour, stop and target  -> the luck bar

A only earns the word "edge" if it beats B, beats C, and beats D at z >= 2. That bar is the one
`structure_patterns.py` and `rso_realign_study.py` already set in this repo, not a new invention.

⚠ **THIS IS AN OPPORTUNITY STUDY, NOT A PORTFOLIO REPLAY.** Every qualifying setup is measured
independently, with no position slot and no risk pool. Run 12 priced what that omission hides:
with one slot a marginal entry does not ADD to the book, it QUEUES in front of a real one. So a
positive result here licenses a replay, never a bot.

⚠ **NO LOOKAHEAD ON THE BLOCKS.** A block is visible to the 1-minute scan only from the minute
AFTER its higher-timeframe bar has closed. Birth and death are recorded per block id off the
engine's own active lists, never re-derived.

⚠ **THE HIGHER TIMEFRAME IS BUILT FROM THE 1-MINUTE FEED, and that is measured, not assumed** —
resampled 15m matches the broker's native 15m to 0.0000 on all four prices over 5,783 bars
(2024-01-01 -> 2024-03-31). One feed means the reserved 2018-19 window is reachable without
mixing brokers.

🔴 **THE HELD-OUT WINDOW IS ON THIS MACHINE AND THE TOOL REFUSES TO LOAD IT.** PU Prime 1-minute
gold is cached back to 2018-09-14, which covers the reserved test set (2018-09-14 -> 2019-12-31).
`--holdout` is the only way past the guard, it prints what it is spending, and per the standing
rule it gets ONE look at a candidate whose rules are already fixed.

Windows:
    search   2020-01-01 -> 2024-12-31   choose here
    confirm  2025-01-01 -> 2026-09-22   must still work here
    holdout  2018-09-14 -> 2019-12-31   locked behind --holdout

Costs: cost-free R is reported FIRST (that is the honest picture of the pattern), then net R using
the MEASURED PU Prime ECN numbers - spread 0.12/oz (median of 3,033,270 ticks) plus $1.00/side/lot
commission, which on a 100oz lot is 0.02/oz round turn. Total 0.14/oz, charged once per trade and
converted to R by the trade's own stop distance. A 1-minute stop is small, so this conversion is
where a pretty gross number usually dies - read both columns.

Usage:
    backtest/tools/ob_shift_study.py
    backtest/tools/ob_shift_study.py --htf M15 --shift ext_choch --stop block
    backtest/tools/ob_shift_study.py --window confirm
    backtest/tools/ob_shift_study.py --htf-sweep
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engines"))
sys.path.insert(0, str(ROOT))

from market_structure import Bar, StructureEngine  # noqa: E402
from order_blocks import OrderBlockEngine  # noqa: E402

from backtest.data.cache import BarCache  # noqa: E402

NY = ZoneInfo("America/New_York")

# Measured PU Prime ECN, per backtest/fills.py: spread 0.12/oz + $1.00/side/lot commission
# (100oz lot -> 0.02/oz round turn). Never copied onto another tier - Prime and Cent refuse.
COST_PER_OZ = 0.12 + 0.02

WINDOWS = {
    "search": ("2020-01-01", "2024-12-31"),
    "confirm": ("2025-01-01", "2026-09-22"),
    "holdout": ("2018-09-14", "2019-12-31"),
}
HOLDOUT_FLOOR = "2020-01-01"  # nothing before this loads without --holdout

R_TARGETS = (1.0, 1.5, 2.0, 3.0)
CONTROL_REPS = 20


# ---------------------------------------------------------------- data


def load_m1(
    symbol: str, cache_dir: Path, start: str, end: str, allow_holdout: bool
) -> pd.DataFrame:
    """Load the 1-minute feed, clamped to what actually came back (rule 3), guarding the test set."""
    if not allow_holdout and start < HOLDOUT_FLOOR:
        raise SystemExit(
            f"REFUSED: start {start} is inside the reserved test window (< {HOLDOUT_FLOOR}).\n"
            "The held-out set gets ONE look, at a candidate whose rules are already fixed.\n"
            "Pass --holdout if that is what you are deliberately spending."
        )
    df = BarCache(cache_dir).load(symbol, "M1").loc[start:end]
    if df.empty:
        raise SystemExit(f"no bars for {symbol} {start}..{end} in {cache_dir}")
    return df


def to_htf(m1: pd.DataFrame, tf: str) -> tuple[pd.DataFrame, np.ndarray]:
    """Resample the 1-minute feed up, and return each HTF bar's CLOSING 1-minute index.

    Verified bit-identical to the broker's native M15 over 5,783 bars. The closing index is what
    makes the no-lookahead rule enforceable: a block found on an HTF bar is invisible until the
    minute after that bar's last 1-minute bar.
    """
    rule = {"M5": "5min", "M15": "15min", "M30": "30min", "H1": "60min", "H4": "240min"}[tf]
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    pos = pd.Series(np.arange(len(m1)), index=m1.index)
    htf = m1.resample(rule, label="left", closed="left").agg(agg).dropna()
    last_pos = pos.resample(rule, label="left", closed="left").max().dropna()
    htf = htf.join(last_pos.rename("_end"), how="inner")
    return htf.drop(columns="_end"), htf["_end"].to_numpy().astype(np.int64)


# ---------------------------------------------------------------- engines


@dataclass
class Zone:
    top: float
    bottom: float
    bullish: bool
    birth: int  # first 1-minute index at which this block is visible
    death: int  # first 1-minute index at which it is no longer live


def block_zones(htf: pd.DataFrame, end_idx: np.ndarray, **ob_kw) -> list[Zone]:
    """Replay the canonical order-block engine and record each block's visible lifetime.

    Birth/death come from the engine's own active lists - membership is the state, per the
    engine's types (there is no lifecycle field on the block itself).
    """
    eng = OrderBlockEngine(**ob_kw)
    o, h, lo, c = (htf[k].to_numpy() for k in ("open", "high", "low", "close"))
    live: dict[int, Zone] = {}
    out: list[Zone] = []
    for i in range(len(htf)):
        ev = eng.update(i, o[i], h[i], lo[i], c[i])
        visible = int(end_idx[i]) + 1
        now = {}
        for b in list(ev.active_bull) + list(ev.active_bear):
            now[b.id] = b
        for bid in list(live):
            if bid not in now:
                z = live.pop(bid)
                z.death = visible
                out.append(z)
        for bid, b in now.items():
            if bid not in live:
                live[bid] = Zone(float(b.top), float(b.bottom), bool(b.is_bullish), visible, 10**12)
    out.extend(live.values())
    return out


def structure_flags(m1: pd.DataFrame, major_length: int = 15) -> dict[str, np.ndarray]:
    """Replay the canonical structure engine on 1-minute bars; one row of flags per minute.

    CHoCH is the engine's SOS flag (a break that also FLIPS the trend); a plain BOS is a break
    that does not. Swing levels are read off the engine after each update, never re-derived.
    """
    n = len(m1)
    o, h, lo, c = (m1[k].to_numpy() for k in ("open", "high", "low", "close"))
    eng = StructureEngine(major_length)
    f = {
        k: np.zeros(n, dtype=bool)
        for k in (
            "ext_bull_choch",
            "ext_bear_choch",
            "ext_bull_bos",
            "ext_bear_bos",
            "int_bull_choch",
            "int_bear_choch",
            "int_bull_bos",
            "int_bear_bos",
        )
    }
    swing_lo = np.full(n, np.nan)
    swing_hi = np.full(n, np.nan)
    for i in range(n):
        ev = eng.update(Bar(i, o[i], h[i], lo[i], c[i]))
        x, t = ev.external, ev.internal
        f["ext_bull_choch"][i] = bool(x.bull_sos)
        f["ext_bear_choch"][i] = bool(x.bear_sos)
        f["ext_bull_bos"][i] = bool(x.bull_bos) and not bool(x.bull_sos)
        f["ext_bear_bos"][i] = bool(x.bear_bos) and not bool(x.bear_sos)
        f["int_bull_choch"][i] = bool(t.bull_sos)
        f["int_bear_choch"][i] = bool(t.bear_sos)
        f["int_bull_bos"][i] = bool(t.bull_bos) and not bool(t.bull_sos)
        f["int_bear_bos"][i] = bool(t.bear_bos) and not bool(t.bear_sos)
        sl, sh = eng.active_swing_low, eng.active_swing_high
        if sl is not None:
            swing_lo[i] = float(sl.price)
        if sh is not None:
            swing_hi[i] = float(sh.price)
    f["swing_low"] = swing_lo
    f["swing_high"] = swing_hi
    return f


SHIFT_KINDS = {
    "ext_choch": ("ext_bull_choch", "ext_bear_choch"),
    "ext_any": ("ext_bull_choch|ext_bull_bos", "ext_bear_choch|ext_bear_bos"),
    "int_choch": ("int_bull_choch", "int_bear_choch"),
    "any": (
        "ext_bull_choch|ext_bull_bos|int_bull_choch|int_bull_bos",
        "ext_bear_choch|ext_bear_bos|int_bear_choch|int_bear_bos",
    ),
}


def shift_masks(f: dict[str, np.ndarray], kind: str) -> tuple[np.ndarray, np.ndarray]:
    bull_k, bear_k = SHIFT_KINDS[kind]
    bull = np.zeros_like(f["ext_bull_choch"])
    bear = np.zeros_like(f["ext_bear_choch"])
    for k in bull_k.split("|"):
        bull |= f[k]
    for k in bear_k.split("|"):
        bear |= f[k]
    return bull, bear


# ---------------------------------------------------------------- trade walk


def walk(
    h, l, c, entry_i: int, long: bool, entry: float, stop: float, target: float, max_hold: int
) -> tuple[int, float]:
    """Walk one trade forward. Stop is checked BEFORE target on the same bar (conservative).

    Returns (exit index, gross R). A trade still open at max_hold exits at that bar's close.
    """
    risk = abs(entry - stop)
    if risk <= 0:
        return entry_i, 0.0
    last = min(entry_i + max_hold, len(c) - 1)
    for k in range(entry_i, last + 1):
        if long:
            if l[k] <= stop:
                return k, -1.0
            if h[k] >= target:
                return k, (target - entry) / risk
        else:
            if h[k] >= stop:
                return k, -1.0
            if l[k] <= target:
                return k, (entry - target) / risk
    px = c[last]
    return last, ((px - entry) if long else (entry - px)) / risk


# ---------------------------------------------------------------- setup finders


def find_block_shift(m1, zones, bull_shift, bear_shift, f, args, require_shift: bool):
    """Arm A (require_shift=True) and Arm B (False, blind first touch of the zone).

    ⚠ **The shift does NOT have to fire while price is still inside the zone**, and an earlier
    version of this tool required exactly that - it found 8 setups in six months because a genuine
    reversal confirms as price LEAVES the zone, not while it is sitting in it. What is required is
    that the tap came first, that the shift lands within `--shift-window` minutes of it, and that
    price has not invalidated the block in between.

    Invalidation is the block's far edge: a demand block whose BOTTOM has been traded through is
    not a block price reversed off, it is one price went through, and counting it would let the
    arm quietly include the failures the setup is supposed to avoid.
    """
    n = len(m1)
    h, l = m1["high"].to_numpy(), m1["low"].to_numpy()
    births = sorted(range(len(zones)), key=lambda i: zones[i].birth)
    setups, bi, live = [], 0, []
    tapped: dict[int, int] = {}
    armed: set[int] = set()
    for t in range(n):
        while bi < len(births) and zones[births[bi]].birth <= t:
            live.append(births[bi])
            bi += 1
        live = [z for z in live if zones[z].death > t]
        for zi in live:
            z = zones[zi]
            if zi in armed:
                continue
            inside = l[t] <= z.top and h[t] >= z.bottom
            if inside and zi not in tapped:
                tapped[zi] = t
            if zi not in tapped:
                continue
            dead = (l[t] < z.bottom) if z.bullish else (h[t] > z.top)
            if dead and not require_shift:
                pass
            elif dead:
                armed.add(zi)  # invalidated before any shift - never tradeable
                continue
            if not require_shift:
                armed.add(zi)
                setups.append((tapped[zi], z.bullish, zi))
                continue
            if t - tapped[zi] > args.shift_window:
                armed.add(zi)  # the window passed without a shift
                continue
            if bull_shift[t] if z.bullish else bear_shift[t]:
                armed.add(zi)
                setups.append((t, z.bullish, zi))
    setups.sort()
    return setups


def find_shift_only(m1, bull_shift, bear_shift, args):
    """Arm C - every 1-minute shift on the tape, no block required."""
    out = []
    for t in np.nonzero(bull_shift)[0]:
        out.append((int(t), True, -1))
    for t in np.nonzero(bear_shift)[0]:
        out.append((int(t), False, -1))
    out.sort()
    return out


def build_trades(m1, setups, zones, f, args, tag: str):
    """Turn armed setups into measured trades. Entry is the NEXT bar's open (one-bar order delay)."""
    o, h, l, c = (m1[k].to_numpy() for k in ("open", "high", "low", "close"))
    idx = m1.index
    ny = idx.tz_localize("UTC").tz_convert(NY)
    month = (ny.year * 12 + ny.month).to_numpy()
    hour = ny.hour.to_numpy()
    trades = []
    for t, long, zi in setups:
        e = t + 1
        if e >= len(o) - 2:
            continue
        entry = o[e]
        if args.stop == "block" and zi >= 0:
            z = zones[zi]
            stop = z.bottom if long else z.top
        else:
            s = f["swing_low"][t] if long else f["swing_high"][t]
            if not np.isfinite(s):
                continue
            stop = s
        risk = abs(entry - stop)
        if risk <= 0 or risk > args.max_stop or risk < args.min_stop:
            continue
        row = {
            "i": e,
            "long": long,
            "entry": entry,
            "risk": risk,
            "month": int(month[e]),
            "hour": int(hour[e]),
            "ts": idx[e],
            "tag": tag,
        }
        for R in R_TARGETS:
            tgt = entry + R * risk if long else entry - R * risk
            _, rg = walk(h, l, c, e, long, entry, stop, tgt, args.max_hold)
            row[f"r{R}"] = rg
            row[f"n{R}"] = rg - COST_PER_OZ / risk
        trades.append(row)
    return trades


# ---------------------------------------------------------------- stats + control


def stats(trades: list, R: float, net: bool) -> dict:
    key = f"{'n' if net else 'r'}{R}"
    if not trades:
        return {"n": 0}
    r = np.array([t[key] for t in trades], dtype=float)
    wins = (r > 0).mean() * 100
    eq = np.cumsum(r)
    dd = float((np.maximum.accumulate(eq) - eq).max()) if len(eq) else 0.0
    gp = r[r > 0].sum()
    gl = -r[r < 0].sum()
    t = (
        float(r.mean() / (r.std(ddof=1) / math.sqrt(len(r))))
        if len(r) > 1 and r.std(ddof=1)
        else 0.0
    )
    half = len(r) // 2
    h1 = float(r[:half].sum()) if half else 0.0
    h2 = float(r[half:].sum()) if half else 0.0
    return {
        "n": len(r),
        "win": wins,
        "avg": float(r.mean()),
        "tot": float(r.sum()),
        "pf": float(gp / gl) if gl else float("inf"),
        "dd": dd,
        "t": t,
        "h1": h1,
        "h2": h2,
    }


def control(trades, m1, f, args, R: float, rng) -> dict:
    """Arm D - matched random timing. Side, calendar month, NY hour, stop DISTANCE and target are
    all held to the real trade; only WHEN is random. Anything looser measures a different claim."""
    idx = m1.index
    ny = idx.tz_localize("UTC").tz_convert(NY)
    key = ((ny.year * 12 + ny.month) * 24 + ny.hour).to_numpy()
    ok = np.arange(len(key))
    ok = ok[(ok >= 1000) & (ok < len(key) - args.max_hold - 2)]
    order = ok[np.argsort(key[ok], kind="stable")]
    ks, starts = np.unique(key[order], return_index=True)
    pools = dict(zip(ks.tolist(), np.split(order, starts[1:])))
    o, h, l, c = (m1[k].to_numpy() for k in ("open", "high", "low", "close"))
    rs = []
    for t in trades:
        pool = pools.get(int(key[t["i"]]))
        if pool is None or not len(pool):
            continue
        for k in rng.choice(pool, size=CONTROL_REPS):
            k = int(k)
            entry = o[k]
            risk = t["risk"]
            long = t["long"]
            stop = entry - risk if long else entry + risk
            tgt = entry + R * risk if long else entry - R * risk
            _, rg = walk(h, l, c, k, long, entry, stop, tgt, args.max_hold)
            rs.append(rg)
    rs = np.array(rs, dtype=float)
    if not len(rs):
        return {"n": 0, "avg": 0.0, "sd": 0.0}
    return {"n": len(rs), "avg": float(rs.mean()), "sd": float(rs.std(ddof=1))}


def matched_pools(m1, args):
    """Minutes bucketed by (calendar month, NY hour) — the matching buckets both the control and
    the luck bar draw from. Built once; the engines are not re-run for a null."""
    ny = m1.index.tz_localize("UTC").tz_convert(NY)
    key = ((ny.year * 12 + ny.month) * 24 + ny.hour).to_numpy()
    ok = np.arange(len(key))
    ok = ok[(ok >= 1000) & (ok < len(key) - args.max_hold - 2)]
    order = ok[np.argsort(key[ok], kind="stable")]
    ks, starts = np.unique(key[order], return_index=True)
    return key, dict(zip(ks.tolist(), np.split(order, starts[1:])))


def luck_bar(cell_trades: dict, m1, args, n_iter: int, rng) -> dict:
    """The bar a winner has to clear, given how many cells were LOOKED AT.

    🔴 **A z of 2 is the bar for ONE pre-declared cell. It is the wrong bar for the best of a
    96-cell grid** — the best of a big search always looks good, which is the exact mistake the
    Loaded Level scalp pick made (best of 3,456 cells, lost on new months). So the whole search is
    re-run `n_iter` times on entries that are random but matched to each real trade's side, month,
    NY hour and stop DISTANCE, and the BEST cell of each fake search is recorded. A real result has
    to beat that distribution, not beat zero.

    Only the timing is randomised. Setups, cell structure and the correlation between cells (they
    share trades) are all preserved, so the null has the same shape as the search.
    """
    key, pools = matched_pools(m1, args)
    o, h, l, c = (m1[k].to_numpy() for k in ("open", "high", "low", "close"))
    bests = []
    for _ in range(n_iter):
        best = -9.9
        for trades in cell_trades.values():
            if not trades:
                continue
            acc = {R: [] for R in R_TARGETS}
            for t in trades:
                pool = pools.get(int(key[t["i"]]))
                if pool is None or not len(pool):
                    continue
                k = int(rng.choice(pool))
                entry, risk, long = o[k], t["risk"], t["long"]
                stop = entry - risk if long else entry + risk
                for R in R_TARGETS:
                    tgt = entry + R * risk if long else entry - R * risk
                    _, rg = walk(h, l, c, k, long, entry, stop, tgt, args.max_hold)
                    acc[R].append(rg)
            for R in R_TARGETS:
                if len(acc[R]) > 5:
                    best = max(best, float(np.mean(acc[R])))
        bests.append(best)
    b = np.array(bests, dtype=float)
    return {
        "n": len(b),
        "p50": float(np.percentile(b, 50)),
        "p95": float(np.percentile(b, 95)),
        "p99": float(np.percentile(b, 99)),
        "max": float(b.max()),
        "all": b,
    }


def zscore(trades, ctl, R: float) -> float:
    r = np.array([t[f"r{R}"] for t in trades], dtype=float)
    if len(r) < 2 or not ctl["n"]:
        return 0.0
    se = math.sqrt(r.var(ddof=1) / len(r) + ctl["sd"] ** 2 / ctl["n"])
    return (r.mean() - ctl["avg"]) / se if se else 0.0


# ---------------------------------------------------------------- report


def line(label: str, s: dict) -> str:
    if not s["n"]:
        return f"  {label:<26} (no trades)"
    return (
        f"  {label:<26} n={s['n']:>5}  win={s['win']:>5.1f}%  avgR={s['avg']:>+6.3f}  "
        f"totR={s['tot']:>+8.1f}  PF={s['pf']:>4.2f}  maxDD={s['dd']:>6.1f}R  t={s['t']:>+5.2f}"
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--symbol", default="XAUUSD_p")
    p.add_argument("--cache", default=str(ROOT / "backtest/cache/PUPrime_Demo"))
    p.add_argument("--window", default="search", choices=list(WINDOWS))
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--htf", default="M15", choices=["M5", "M15", "M30", "H1", "H4"])
    p.add_argument("--htf-sweep", action="store_true", help="run M5, M15, H1 and compare")
    p.add_argument("--shift-sweep", action="store_true", help="run every shift definition")
    p.add_argument("--stop-sweep", action="store_true", help="run both stop rules")
    p.add_argument("--shift", default="ext_choch", choices=list(SHIFT_KINDS))
    p.add_argument("--stop", default="block", choices=["block", "swing"])
    p.add_argument("--shift-window", type=int, default=60, help="minutes from zone tap to shift")
    p.add_argument(
        "--max-hold", type=int, default=2880, help="bars (trading minutes) before time exit"
    )
    p.add_argument("--min-stop", type=float, default=0.30, help="$/oz - below this costs dominate")
    p.add_argument("--max-stop", type=float, default=40.0)
    p.add_argument("--major-length", type=int, default=15)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument(
        "--luck-bar",
        type=int,
        default=0,
        help="re-runs of the whole search on random entries (200 is the repo standard)",
    )
    p.add_argument(
        "--holdout", action="store_true", help="deliberately spend the reserved test set"
    )
    args = p.parse_args()

    start, end = WINDOWS[args.window]
    if args.start:
        start = args.start
    if args.end:
        end = args.end
    if args.window == "holdout" and not args.holdout:
        raise SystemExit("REFUSED: --window holdout needs --holdout. That window gets ONE look.")

    m1 = load_m1(args.symbol, Path(args.cache), start, end, args.holdout)
    print(f"\n{'=' * 112}")
    print(
        f"ORDER BLOCK + 1-MINUTE SHIFT OF STRUCTURE     {args.symbol}  {args.window}  "
        f"{m1.index[0]} -> {m1.index[-1]}  ({len(m1):,} 1m bars)"
    )
    print(
        f"shift={args.shift}  stop={args.stop}  tap->shift window={args.shift_window}m  "
        f"max hold={args.max_hold}m  costs={COST_PER_OZ:.2f}/oz (PU Prime ECN, measured)"
    )
    print("=" * 112)

    f = structure_flags(m1, args.major_length)
    rng = np.random.default_rng(args.seed)

    tfs = ["M5", "M15", "H1"] if args.htf_sweep else [args.htf]
    kinds = list(SHIFT_KINDS) if args.shift_sweep else [args.shift]
    stops = ["block", "swing"] if args.stop_sweep else [args.stop]

    cells = []
    cell_trades = {}
    for tf in tfs:
        htf, end_idx = to_htf(m1, tf)
        zones = block_zones(htf, end_idx)
        print(f"\n### {tf} blocks — {len(zones):,} blocks lived in this window")
        for kind in kinds:
            bull_shift, bear_shift = shift_masks(f, kind)
            sa = find_block_shift(m1, zones, bull_shift, bear_shift, f, args, True)
            sb = find_block_shift(m1, zones, bull_shift, bear_shift, f, args, False)
            sc = find_shift_only(m1, bull_shift, bear_shift, args)
            for st in stops:
                args.stop = st
                a = build_trades(m1, sa, zones, f, args, "A")
                cell_trades[(tf, kind, st)] = a
                b = build_trades(m1, sb, zones, f, args, "B")
                c = build_trades(m1, sc, zones, f, args, "C")
                print(
                    f"\n  [{tf} | shift={kind} | stop={st}]  armed={len(a)}  touches={len(b)}  "
                    f"bare shifts={len(c)}"
                )
                for R in R_TARGETS:
                    ctl = control(a, m1, f, args, R, rng)
                    z = zscore(a, ctl, R)
                    sA, sB, sC = stats(a, R, False), stats(b, R, False), stats(c, R, False)
                    sN = stats(a, R, True)
                    print(f"  -- target {R}R " + "-" * 92)
                    print(line("A  block + shift", sA))
                    print(line("B  block, no shift", sB))
                    print(line("C  shift, no block", sC))
                    print(
                        f"  {'D  matched random':<26} n={ctl['n']:>5}  avgR={ctl['avg']:>+6.3f}"
                        f"                                        z(A vs D)={z:>+5.2f}"
                    )
                    print(line("A  net of costs", sN))
                    if sA["n"]:
                        cells.append(
                            {
                                "h1": sA["h1"],
                                "h2": sA["h2"],
                                "tf": tf,
                                "kind": kind,
                                "stop": st,
                                "R": R,
                                "z": z,
                                "n": sA["n"],
                                "win": sA["win"],
                                "avg": sA["avg"],
                                "net": sN["avg"],
                                "netwin": sN["win"],
                                "tot": sA["tot"],
                                "b": sB.get("avg", 0.0),
                                "c": sC.get("avg", 0.0),
                            }
                        )

    if len(cells) > 1:
        print(
            f"\n{'=' * 112}\nGRID SUMMARY — {len(cells)} cells searched. "
            f"With this many looks the honest bar is the BEST cell's z, not 2.0.\n{'=' * 112}"
        )
        print(
            f"  {'cell':<34} {'n':>5} {'win%':>6} {'avgR':>7} {'netR':>7} {'netwin%':>8} "
            f"{'z':>6} {'B avgR':>7} {'C avgR':>7} {'half1':>7} {'half2':>7}"
        )
        for cc in sorted(cells, key=lambda x: -x["avg"])[:15]:
            nm = f"{cc['tf']}/{cc['kind']}/{cc['stop']}/{cc['R']}R"
            print(
                f"  {nm:<34} {cc['n']:>5} {cc['win']:>6.1f} {cc['avg']:>+7.3f} {cc['net']:>+7.3f} "
                f"{cc['netwin']:>8.1f} {cc['z']:>+6.2f} {cc['b']:>+7.3f} {cc['c']:>+7.3f} "
                f"{cc['h1']:>+7.1f} {cc['h2']:>+7.1f}"
            )

        if args.luck_bar:
            lb = luck_bar(cell_trades, m1, args, args.luck_bar, rng)
            top = max(cells, key=lambda x: x["avg"])
            print(
                f"\n  LUCK BAR — {args.luck_bar} re-runs of this whole {len(cells)}-cell search "
                f"on matched-random entries, best cell of each:"
            )
            print(
                f"    null best avgR:  median {lb['p50']:+.3f}   95th {lb['p95']:+.3f}   "
                f"99th {lb['p99']:+.3f}   max {lb['max']:+.3f}"
            )
            beat = float((lb["all"] >= top["avg"]).mean())
            print(
                f"    real best avgR:  {top['avg']:+.3f} "
                f"({top['tf']}/{top['kind']}/{top['stop']}/{top['R']}R, n={top['n']})"
            )
            print(
                f"    -> a random search beat it in {beat * 100:.1f}% of re-runs  "
                f"({'PASSES' if beat < 0.05 else 'FAILS'} the 5% luck bar)"
            )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
