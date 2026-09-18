import dataclasses
import sys

sys.path.insert(0, "/Users/alwg/trading")
sys.path.insert(0, "/Users/alwg/trading/strategies/python")
from sos_fade import SosFadeStrategy
from sos_fade.profiles import GBPJPY_PUPRIME, UNTUNED, XAUUSD_VANTAGE

from backtest.data.fx import series_for
from backtest.data.source import BarSource
from backtest.fills import PROFILES
from backtest.replay.build import build_strategy

START, END, TF = "2020-01-01", "2026-09-01", 15
src = BarSource()


def run(facts, label, costs, rate_sym=None):
    cfg = dataclasses.replace(UNTUNED, facts=facts).build()
    df = src.load(cfg.symbol, TF, START, END)
    strat = build_strategy(
        SosFadeStrategy,
        cfg,
        initial_capital=10_000.0,
        cost_profile=PROFILES[cfg.account_profile] if costs else None,
    )
    if rate_sym:
        r = series_for(src, rate_sym, 1440, "2019-12-01", END, invert=True, label=rate_sym)
        strat.execution.set_rate_provider(r.provider())
    strat.run(df, warmup=500)
    tr = strat.execution.trades
    rs = [t.r for t in tr]
    tot = sum(rs)
    peak = run_ = mdd = 0.0
    for x in rs:
        run_ += x
        peak = max(peak, run_)
        mdd = min(mdd, run_ - peak)
    w = len([r for r in rs if r > 0.15])
    l = len([r for r in rs if r < -0.15])
    print(
        f"{label:38s} {len(tr):4d} tr  {tot:+8.2f}R  maxDD {mdd:7.2f}R  win {100 * w / max(1, w + l):4.1f}%"
    )


gold_ecn = dataclasses.replace(XAUUSD_VANTAGE, symbol="XAUUSD.p", account_profile="puprime_ecn")
print("UNTUNED baseline, 6.7 years, M15 — costs ON vs OFF\n")
run(GBPJPY_PUPRIME, "GBPJPY  costs OFF (raw signal)", False, "USDJPY.p")
run(GBPJPY_PUPRIME, "GBPJPY  costs ON", True, "USDJPY.p")
run(gold_ecn, "XAUUSD  costs OFF (raw signal)", False)
run(gold_ecn, "XAUUSD  costs ON", True)
