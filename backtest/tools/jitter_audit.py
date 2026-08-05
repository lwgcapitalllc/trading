#!/usr/bin/env python3
"""jitter_audit.py — how much of the backtest survives a few cents of feed difference?

**Why this exists.** The shadow diff (`algos/tools/shadow_diff.py`, 2026-08-04) ran the live
bot's decision stream against a lab replay of the same window and found ten of eleven fields
bar-for-bar identical. The eleventh was the entry price, and on 25 consecutive bars it was
**$10.08 apart** — not because anything had drifted, but because both prices were rungs on the
SAME fib ladder and `exec_fib_nearest` had rested on a different one. Four cents of broker
quote difference moved the resting entry by ten dollars, and with the stop at 0.886 that is a
$32.28 stop against a $22.16 stop: **46% apart**, so the nominal 1R is unchanged while position
SIZE and fill probability move materially.

That measured the MECHANISM on one leg. It said nothing about how OFTEN it happens, and one leg
cannot: the flip is a discontinuity, so it either fires on a setup or it does not. This tool
measures the frequency over the full history, which is the number that decides whether a
backtest's trade list transfers to a different broker.

**The jitter model, and it is the whole design.** Each bar's four prices are shifted by ONE
offset drawn per bar. Two properties, both deliberate:

- **A per-bar CONSTANT shift cannot flip a rung, and that is exactly why the offset varies per
  bar rather than across the run.** Move every price in the window by four cents and every fib
  level moves with it — the ladder, the gap edge and the entry all translate together and the
  rule picks the same rung. What flips it is the SMALL VARIATION in the offset: the shadow diff
  measured 0.04 on some bars and 0.05 on others, which moves a gap edge relative to a ladder
  anchored on different bars. So the offset is redrawn every bar, and the amplitude defaults to
  the measured spread of that difference rather than to a round number.
- **Shifting all four prices of a bar together preserves the bar.** `high >= max(open, close)`
  and `low <= min(open, close)` still hold, and no bar becomes a shape the market cannot
  produce. Jittering O/H/L/C independently would manufacture inside-out candles and measure the
  engines' behaviour on impossible data, which is a different and useless question.

**What comes out.** Per seed, against the un-jittered baseline:

  1. **Trades LOST and GAINED** — a setup that filled and now does not, or the reverse.
  2. **Trades that FLIPPED a rung** — same entry bar, entry price moved by more than the noise
     could possibly account for. This is the G17 number.
  3. **Trades that merely SHIFTED** — same entry bar, price moved by about the noise. Expected,
     and not a finding.
  4. **What the flips did to the stop**, in percent, because that is the part that changes
     position size while leaving R looking untouched.
  5. **Total R**, per seed and as a spread across seeds.

⚠ **A flip that also DELAYS the fill shows up as a lost trade plus a gained one, not as a price
change.** A deeper limit is harder to reach, so the order may fill on a later bar or never. That
is the honest bookkeeping — it genuinely is a different trade — but it means the flip count here
is a FLOOR on how often the rule changed its mind, not a total.

⚠ **This measures SENSITIVITY, not a broker.** It answers "how stable is this trade list under a
few cents of quote difference", which is the question a backtest measured on Vantage and traded
on PU Prime has to answer. It does not predict PU Prime's trade list — only running on PU Prime
data does that.

Usage:
    python backtest/tools/jitter_audit.py
    python backtest/tools/jitter_audit.py --amp 0.05 --seeds 8
    python backtest/tools/jitter_audit.py --strategy mpc_bleg --start 2020-01-01
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import importlib
import random
import statistics
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Same registry shape as overlap_audit.py / run_report.py — a package that declares
# LAB_STRATEGY runs here for free. Keep them in step when a third Python strategy lands.
_STRATEGIES = {
    "mpc_sos_fade": "strategies.python.mpc_sos_fade",
    "mpc_bleg": "strategies.python.mpc_bleg",
}

# The default amplitude is the MEASURED thing, not a round number: the shadow diff found Vantage
# above PU Prime by 0.04–0.05 on every one of 148 live bars. The offset here is drawn from
# [-amp, +amp], so `amp = 0.05` spans a little more than the observed range in both directions.
_DEFAULT_AMP = 0.05


def _jitter(df, amp: float, seed: int):
    """A copy of the frame with each bar's four prices shifted by one per-bar offset.

    ⚠ **One offset per BAR, applied to all four prices** — see the module docstring. Independent
    per-price noise would build candles where the high is below the close, and the engines would
    then be measured on data no feed can produce.
    """
    rng = random.Random(seed)
    out = df.copy()
    offsets = [rng.uniform(-amp, amp) for _ in range(len(out))]
    for col in ("open", "high", "low", "close"):
        out[col] = [p + o for p, o in zip(out[col].tolist(), offsets)]
    return out


def _replay(key: str, df, warmup: int, capital: float):
    mod = importlib.import_module(_STRATEGIES[key])
    spec = mod.LAB_STRATEGY
    cfg = spec["config"](fill_model="bar", symbol="XAUUSD")
    strat = spec["strategy"](config=cfg, initial_capital=capital)
    strat.run(df, warmup=warmup)
    return strat.execution.trades


# A baseline trade that vanished and a jittered trade that appeared, same direction and this
# close in time, are read as ONE trade that was RETIMED rather than as two different trades.
# 16 bars = 4 hours on M15, the same window `overlap_audit.py` uses for "one structure break".
_RETIME_BARS = 16


class Diff:
    """One jittered run against the baseline, classified.

    `flipped` is the G17 number and its threshold is derived rather than chosen: an offset drawn
    from [-amp, +amp] can move a price by at most `amp`, so two runs can differ by at most
    `2 * amp` from the noise alone. Anything beyond that is not the noise — it is a different
    decision, and on this strategy the only decision that moves an entry by dollars is which
    fib rung `exec_fib_nearest` rested on.

    ⚠ **`lost` and `gained` are the counts AFTER retimed pairs are removed, and that distinction
    is the difference between an alarming number and a true one.** A resting limit that fills one
    bar later is the same setup, the same direction and very nearly the same trade; counting it
    as one trade destroyed plus one invented would report the trade list as far less stable than
    it is. Retimed pairs are reported separately, because they are not nothing either — the entry
    price and therefore the size did move.
    """

    __slots__ = ("seed", "lost", "gained", "retimed", "flipped", "shifted",
                 "total_r", "stop_deltas")

    def __init__(self, seed: int):
        self.seed = seed
        self.lost: list = []
        self.gained: list = []
        self.retimed: list = []      # (baseline trade, jittered trade, bars apart)
        self.flipped: list = []      # (baseline trade, jittered trade)
        self.shifted = 0
        self.total_r = 0.0
        self.stop_deltas: list[float] = []


def _diff(base: list, jit: list, seed: int, noise_ceiling: float,
          bar_ms: int = 15 * 60 * 1000, retime_bars: int = _RETIME_BARS) -> Diff:
    d = Diff(seed)
    d.total_r = sum(t.r for t in jit)

    by_ms = {t.entry_ms: t for t in jit}
    seen = set()
    unmatched_base: list = []
    for b in base:
        j = by_ms.get(b.entry_ms)
        if j is None:
            unmatched_base.append(b)
            continue
        seen.add(b.entry_ms)
        if abs(j.entry_price - b.entry_price) > noise_ceiling:
            d.flipped.append((b, j))
            if b.stop_distance:
                d.stop_deltas.append(
                    100.0 * (j.stop_distance - b.stop_distance) / b.stop_distance)
        elif j.entry_price != b.entry_price:
            d.shifted += 1

    unmatched_jit = [t for t in jit if t.entry_ms not in seen]

    # Second pass: pair what is left by direction and proximity, NEAREST FIRST, one-to-one. A
    # greedy nearest pass is what stops one jittered trade from being claimed as the retimed twin
    # of two different baseline trades, which would understate both counts at once.
    window = retime_bars * bar_ms
    cands = [(abs(b.entry_ms - j.entry_ms), i, k, b, j)
             for i, b in enumerate(unmatched_base)
             for k, j in enumerate(unmatched_jit)
             if b.dir == j.dir and abs(b.entry_ms - j.entry_ms) <= window]
    cands.sort(key=lambda c: (c[0], c[1], c[2]))
    used_b: set[int] = set()
    used_j: set[int] = set()
    for gap, i, k, b, j in cands:
        if i in used_b or k in used_j:
            continue
        used_b.add(i)
        used_j.add(k)
        d.retimed.append((b, j, round(gap / bar_ms)))

    d.lost = [b for i, b in enumerate(unmatched_base) if i not in used_b]
    d.gained = [j for k, j in enumerate(unmatched_jit) if k not in used_j]
    return d


def _pct(part: int, whole: int) -> str:
    return f"{100.0 * part / whole:.1f}%" if whole else "—"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strategy", default="mpc_sos_fade", choices=sorted(_STRATEGIES))
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--start", default=None,
                    help="YYYY-MM-DD (default: the broker's measured earliest bar at this tf)")
    ap.add_argument("--end", default=None)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--amp", type=float, default=_DEFAULT_AMP,
                    help="per-bar offset drawn from [-amp, +amp], in price units")
    ap.add_argument("--seeds", type=int, default=5, help="how many jittered replays")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    if args.amp <= 0:
        raise SystemExit("--amp must be positive; a zero jitter measures nothing")

    from backtest.data.history import floor_for
    from backtest.data.source import BarSource

    start = args.start
    if start is None:
        fl = floor_for(args.symbol, args.tf)
        if fl is None:
            raise SystemExit(
                f"cannot measure the broker's earliest {args.tf}m history for {args.symbol}. "
                f"Pass --start explicitly rather than guessing one.")
        start = fl.isoformat()
    end = args.end or dt.date.today().isoformat()

    print(f"loading {args.symbol} {args.tf}m  {start} -> {end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, start, end)
    if df.empty:
        print("no bars returned")
        return 1
    print(f"  {len(df):,} bars  {df.index[0]} -> {df.index[-1]}", flush=True)

    print("  replaying the baseline (no jitter) ...", flush=True)
    base = _replay(args.strategy, df, args.warmup, args.capital)
    base_r = sum(t.r for t in base)
    print(f"  baseline: {len(base)} trades  {base_r:+.2f}R", flush=True)

    ceiling = 2 * args.amp
    diffs: list[Diff] = []
    for seed in range(1, args.seeds + 1):
        print(f"  replaying seed {seed}/{args.seeds} (+/- {args.amp}) ...", flush=True)
        jit = _replay(args.strategy, _jitter(df, args.amp, seed), args.warmup, args.capital)
        diffs.append(_diff(base, jit, seed, ceiling))

    # ── report ──
    w = 100
    print("\n" + "=" * w)
    print(f"JITTER AUDIT   {args.strategy}   +/- {args.amp} per bar   {args.seeds} seeds"
          f"   {df.index[0].date()} -> {df.index[-1].date()}")
    print("=" * w)
    print(f"\nbaseline   {len(base)} trades   {base_r:+.2f}R")
    print(f"\n  a rung FLIP is an entry moved by more than {ceiling:.3f} — beyond anything the "
          f"noise can do.\n  a SHIFT is an entry moved by about the noise, which is expected and "
          f"is not a finding.\n")

    hdr = (f"  {'seed':>4}  {'trades':>6}  {'total R':>9}  {'lost':>5}  {'gained':>6}"
           f"  {'retimed':>7}  {'FLIPPED':>7}  {'shifted':>7}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for d in diffs:
        n = len(base) - len(d.lost) + len(d.gained)
        print(f"  {d.seed:>4}  {n:>6}  {d.total_r:>+9.2f}  {len(d.lost):>5}  {len(d.gained):>6}"
              f"  {len(d.retimed):>7}  {len(d.flipped):>7}  {d.shifted:>7}")

    flips = sum(len(d.flipped) for d in diffs)
    lost = sum(len(d.lost) for d in diffs)
    gained = sum(len(d.gained) for d in diffs)
    retimed = sum(len(d.retimed) for d in diffs)
    rs = [d.total_r for d in diffs]
    per_run = len(base) * len(diffs)
    ns = len(diffs)

    print(f"\n--- ACROSS ALL {ns} SEEDS ---")
    print(f"  rung flips        {flips:5d}  = {_pct(flips, per_run)} of baseline trades"
          f"   ({flips / ns:.1f} per run)")
    print(f"  trades RETIMED    {retimed:5d}  = {_pct(retimed, per_run)}"
          f"   ({retimed / ns:.1f} per run)   same setup, filled up to"
          f" {_RETIME_BARS} bars away")
    print(f"  trades lost       {lost:5d}  = {_pct(lost, per_run)}"
          f"   ({lost / ns:.1f} per run)   no twin at all")
    print(f"  trades gained     {gained:5d}   ({gained / ns:.1f} per run)")
    print(f"  ⚠ a flip that also moves the entry BAR is counted as retimed or lost+gained, never")
    print(f"    as a flip, so the flip figure is a FLOOR on how often the rule changed its mind.")

    mean_r = statistics.mean(rs)
    sd = statistics.stdev(rs) if ns > 1 else 0.0
    print(f"\n  total R   baseline {base_r:+.2f}"
          f"   jittered min {min(rs):+.2f}  median {statistics.median(rs):+.2f}  max {max(rs):+.2f}")
    print(f"            mean {mean_r:+.2f}  sd {sd:.2f}R over {ns} seeds"
          f"   (spread {max(rs) - min(rs):.2f}R)")
    print(f"  ⚠ the sd is over {ns} seeds and is itself an estimate — read it as an order of")
    print(f"    magnitude for how much of the result is the FEED rather than the edge.")
    if rs and min(rs) > 0:
        print(f"  ✅ every seed finished POSITIVE. The trade LIST moves; the sign of the edge did not.")
    else:
        print(f"  🔴 at least one seed finished NEGATIVE — the edge itself did not survive the noise.")

    all_stop = [x for d in diffs for x in d.stop_deltas]
    print("\n--- WHAT A FLIP DID TO THE STOP (position size follows this, R does not) ---")
    if all_stop:
        mags = [abs(x) for x in all_stop]
        print(f"  {len(all_stop)} flips with a measurable stop change")
        print(f"  |change| in the 1R distance:  min {min(mags):.1f}%"
              f"   median {statistics.median(mags):.1f}%   max {max(mags):.1f}%")
        print(f"  ⚠ the nominal R is unchanged by construction — the trade is sized to the stop.")
        print(f"    What moves is the POSITION SIZE and how far price must travel to fill.")
    else:
        print("  no flips, so nothing to report here.")

    # ── files ──
    out = Path(args.out) if args.out else _ROOT / "backtest" / "reports" / (
        "jitter_" + dt.datetime.now().strftime("%Y%m%dT%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "flips.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["seed", "entry_utc", "dir", "base_entry", "jit_entry", "entry_delta",
                     "base_stop_dist", "jit_stop_dist", "stop_delta_pct", "base_r", "jit_r"])
        for d in diffs:
            for b, j in d.flipped:
                sd = (100.0 * (j.stop_distance - b.stop_distance) / b.stop_distance
                      if b.stop_distance else "")
                wr.writerow([
                    d.seed, dt.datetime.utcfromtimestamp(b.entry_ms / 1000).isoformat(), b.dir,
                    round(b.entry_price, 5), round(j.entry_price, 5),
                    round(j.entry_price - b.entry_price, 5),
                    round(b.stop_distance, 5), round(j.stop_distance, 5),
                    (round(sd, 2) if sd != "" else ""), round(b.r, 3), round(j.r, 3)])

    with open(out / "seeds.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["seed", "trades", "total_r", "lost", "gained", "retimed",
                     "flipped", "shifted"])
        for d in diffs:
            wr.writerow([d.seed, len(base) - len(d.lost) + len(d.gained), round(d.total_r, 3),
                         len(d.lost), len(d.gained), len(d.retimed), len(d.flipped), d.shifted])

    print(f"\nwrote {out}/flips.csv, seeds.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
