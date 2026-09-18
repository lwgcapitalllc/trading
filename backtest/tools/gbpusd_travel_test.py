import dataclasses
import sys

sys.path.insert(0, "/Users/alwg/trading")
sys.path.insert(0, "/Users/alwg/trading/strategies/python")
from sos_fade import SosFadeStrategy
from sos_fade.profiles import GBPUSD_PUPRIME, GOLD, UNTUNED

from backtest.data.source import BarSource
from backtest.fills import PROFILES
from backtest.replay.build import build_strategy

START, END, TF = "2020-01-01", "2026-09-01", 15
src = BarSource()


def run(prof, facts, label, costs):
    cfg = dataclasses.replace(prof, facts=facts).build()
    df = src.load(cfg.symbol, TF, START, END)
    strat = build_strategy(
        SosFadeStrategy,
        cfg,
        initial_capital=10_000.0,
        cost_profile=PROFILES[cfg.account_profile] if costs else None,
    )
    strat.run(df, warmup=500)
    tr = strat.execution.trades
    rs = [t.r for t in tr]
    tot = sum(rs)
    peak = r_ = mdd = 0.0
    for x in rs:
        r_ += x
        peak = max(peak, r_)
        mdd = min(mdd, r_ - peak)
    w = len([r for r in rs if r > 0.15])
    l = len([r for r in rs if r < -0.15])
    lo = sum(t.r for t in tr if t.dir > 0)
    sh = sum(t.r for t in tr if t.dir < 0)
    print(
        f"{label:40s} {len(tr):4d} tr  {tot:+8.2f}R  maxDD {mdd:7.2f}R  "
        f"win {100 * w / max(1, w + l):4.1f}%  L {lo:+7.2f}R  S {sh:+7.2f}R"
    )


print("GBPUSD.p M15, 2020-01-01..2026-09-01, $10k\n")
run(UNTUNED, GBPUSD_PUPRIME, "UNTUNED base  costs OFF (raw signal)", False)
run(UNTUNED, GBPUSD_PUPRIME, "UNTUNED base  costs ON", True)
run(GOLD, GBPUSD_PUPRIME, "GOLD tuned    costs ON", True)
