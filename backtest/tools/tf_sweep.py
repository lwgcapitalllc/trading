#!/usr/bin/env python3
"""tf_sweep.py — does the A+ edge exist on timeframes other than 15 minutes?

Aaron, 2026-08-09: "does this mean you gonna run the strategy that we were thinking about, but
just on, like, thirty minutes, one hour, four hour time frames?"

One full replay of `sos_fade` per timeframe, at the SHIPPED defaults, over the same calendar
window. Everything about the strategy is held constant; only the bar size moves.

⚠ **THIS IS NOT A COMPARISON OF EQUALS AND MUST NOT BE READ AS ONE.** A 4-hour bar is 16 M15 bars,
so a 4H run sees a sixteenth of the bars, arms a fraction of the setups, and lands a fraction of
the trades. Fewer trades is the EXPECTED result, not a verdict — and with fewer trades the error
bar on the edge widens fast. Read the AVERAGE R and its noise, never the total.

⚠ **THE 15m ROW IS THE CONTROL, and it must reproduce the documented 159 / +142.18R baseline.**
If it does not, the sweep is measuring something other than this bot and every other row is
meaningless. Asserted, not assumed.

⚠ **ONE ENGINE CONSTANT IS GENUINELY TIMEFRAME-DEPENDENT AND IS LEFT ALONE ON PURPOSE.**
`sos_fade_strategy.pine` splits the minimum-gap floor by timeframe — 0.0 below 15m, **0.1 at 15m and
above** (`SosFadeStrategy.engine_config`) — so 0.1 is the correct value at 30m, 1H and 4H and
nothing needs changing. It would be wrong only BELOW 15m, which is why this tool refuses those.

⚠ **THE COSTS ARE OFF, matching every baseline figure in this repo.** A higher timeframe holds
longer, so it pays more swap — a charged sweep would legitimately look worse at 4H for a reason
that has nothing to do with the edge. Charge them as a second pass once a row is interesting.

Usage:
    python backtest/tools/tf_sweep.py --start 2020-01-01 --end 2026-08-03
    python backtest/tools/tf_sweep.py --tfs 15,30,60,240
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_SCRATCH_R = 0.25

# Below this the Pine's minimum-gap floor is a DIFFERENT number (0.0, not 0.1) and
# `engine_config()` hardcodes the 15m-and-above value. Refuse rather than silently replay a
# strategy configured for a floor it is not running under.
_MIN_TF = 15

_LABEL = {"15": "15m", "30": "30m", "60": "1H", "240": "4H", "1440": "1D"}


def _mean_sd(rs):
    n = len(rs)
    m = sum(rs) / n
    if n < 2:
        return m, 0.0
    return m, (sum((r - m) ** 2 for r in rs) / (n - 1)) ** 0.5


def _max_dd_r(rs):
    """Peak-to-trough of the cumulative R curve. In R rather than dollars, because dollars at
    fixed-% risk compound and a drawdown in dollars is then a leverage artefact as much as a
    result — the 2026-08-03 lesson about reading a cost against R and never against net dollars."""
    peak = cum = 0.0
    worst = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return worst


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tfs", default="15,30,60,240")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument(
        "--expect-15m-trades",
        type=int,
        default=159,
        help="assert the 15m control row reproduces the documented baseline",
    )
    args = ap.parse_args(argv)

    from backtest.data.source import BarSource
    from strategies.python.sos_fade import LAB_STRATEGY

    end = args.end or dt.date.today().isoformat()
    tfs = [t.strip() for t in args.tfs.split(",") if t.strip()]
    for t in tfs:
        if int(t) < _MIN_TF:
            raise SystemExit(
                f"--tfs {t} is below {_MIN_TF}m. `engine_config()` pins the minimum-gap floor at "
                f"0.1, which is the Pine's 15m-and-above value; below 15m the Pine uses 0.0, so "
                f"this run would replay a strategy configured for a floor it is not under."
            )

    StrategyCls, ConfigCls = LAB_STRATEGY["strategy"], LAB_STRATEGY["config"]
    src = BarSource()
    rows = []

    for tf in tfs:
        label = _LABEL.get(tf, f"{tf}m")
        print(f"loading {args.symbol} {tf}m  {args.start} -> {end} ...", flush=True)
        df = src.load(args.symbol, tf, args.start, end)
        if df.empty:
            print(f"  no bars at {label} — skipped")
            continue
        print(f"  {len(df):,} bars   replaying {label} ...", flush=True)

        # Shipped defaults. `exec_secondary=False` is pinned rather than left to the default,
        # because `run()` is primary-only and a True there would refuse outright on any frame
        # without a 1-minute stream — see the 2026-08-07 default-reach lesson.
        cfg = ConfigCls(fill_model="bar", symbol=args.symbol, exec_secondary=False)
        strat = StrategyCls(config=cfg, initial_capital=args.capital).run(df)
        rs = [t.r for t in strat.execution.trades]
        rows.append((label, tf, len(df), rs))
        print(f"    {len(rs)} trades  {sum(rs):+.2f}R", flush=True)

    ctrl = next((r for r in rows if r[1] == "15"), None)
    if ctrl and args.expect_15m_trades and len(ctrl[3]) != args.expect_15m_trades:
        raise SystemExit(
            f"the 15m control made {len(ctrl[3])} trades, not the documented "
            f"{args.expect_15m_trades}. This sweep is not replaying the shipped bot, so no row "
            f"below can be compared to anything."
        )

    print()
    print(
        f"{'tf':<5} {'bars':>9} {'trades':>7} {'total R':>10} {'avg R':>9} {'+/- se':>8} "
        f"{'maxDD R':>9} {'win%':>6}  {'ex-best R':>10}"
    )
    print("-" * 84)
    for label, _tf, nbars, rs in rows:
        if not rs:
            print(f"{label:<5} {nbars:>9,} {0:>7}   — no trades —")
            continue
        m, sd = _mean_sd(rs)
        se = sd / len(rs) ** 0.5
        w = sum(1 for r in rs if r > _SCRATCH_R)
        print(
            f"{label:<5} {nbars:>9,} {len(rs):>7} {sum(rs):>+10.2f} {m:>+9.3f} {se:>8.3f} "
            f"{_max_dd_r(rs):>9.2f} {w / len(rs) * 100:>5.1f}% {sum(rs) - max(rs):>+10.2f}"
        )

    print()
    print("  avg R is the number to read; total R scales with how many bars the timeframe has.")
    print("  '+/- se' is the standard error on that average — a row whose avg is smaller than")
    print("  ~2x its own se has not shown an edge, however good the total looks.")
    print("  ex-best R strips each row's single best trade: this bot is designed fat-tailed, so")
    print("  a thin row can be one lucky runner wearing a strategy's name.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
