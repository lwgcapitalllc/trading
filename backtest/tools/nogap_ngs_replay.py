#!/usr/bin/env python3
"""nogap_ngs_replay.py — Run 29: the no-gap shift entry replayed through the SOS Fade bot itself.

Run 28 screened the idea outside the bot. This replays it through the strategy's own order layer
(`exec_ngs`), on a 15m primary and a 1-minute fast clock, with costs, and prints four variants on
the SAME clock so only the switches differ (rule 11):

    base        re-entry off, no-gap shift off
    ngs         re-entry off, no-gap shift on
    sec         re-entry on (shipped), no-gap shift off
    sec+ngs     both on

⚠ The shipped re-entry runs on a 5-minute clock; the no-gap shift needs 1 minute, so every variant
here runs the re-entry at 1 minute. That config setting's own note measured 1m as the most
faithful fill (+147.56R vs +145.61R at 5m), so the shift is small, but it is not the live bot.
⚠ Both frames come from one broker's cache (`--broker-dir`).

Usage:
    python3 backtest/tools/nogap_ngs_replay.py --variant ngs
    python3 backtest/tools/nogap_ngs_replay.py --variant all
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.fills import PROFILES  # noqa: E402
from backtest.replay import build_strategy  # noqa: E402

_VARIANTS = {
    "base": {"exec_secondary": False, "exec_ngs": False},
    "ngs": {"exec_secondary": False, "exec_ngs": True},
    "sec": {"exec_secondary": True, "exec_ngs": False},
    "sec+ngs": {"exec_secondary": True, "exec_ngs": True},
}


def _load(cache_dir: Path, symbol: str, tf: str, start: str, end: str):
    from backtest.data.cache import BarCache

    return BarCache(cache_dir).load(symbol, tf).loc[start:end]


def _max_dd_r(rs) -> float:
    eq = np.cumsum(rs)
    return (
        float((np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq).max())
        if len(rs)
        else 0.0
    )


def _line(label, rs) -> str:
    rs = np.asarray(rs, dtype=float)
    if not len(rs):
        return f"  {label:<18} n=0"
    top3 = np.sort(rs)[:-3].sum() if len(rs) > 3 else float("nan")
    return (
        f"  {label:<18} n={len(rs):<4} total {rs.sum():+8.2f}R  mean {rs.mean():+.3f}  "
        f"win {np.mean(rs > 0):5.1%}  without best 3 {top3:+8.2f}R  worst run {_max_dd_r(rs):6.2f}R"
    )


def run_variant(name, df15, df1, args):
    from strategies.python.sos_fade import LAB_STRATEGY

    S, C = LAB_STRATEGY["strategy"], LAB_STRATEGY["config"]
    over = dict(_VARIANTS[name], exec_sec_fill_tf_min=args.fast_min)
    if args.tp_r is not None:
        over["exec_ngs_tp_r"] = args.tp_r
    cfg = dataclasses.replace(C(fill_model="bar", symbol=args.symbol), **over)
    profile = None if args.profile == "none" else PROFILES[args.profile]
    strat = build_strategy(S, cfg, initial_capital=args.capital, cost_profile=profile)
    t0 = time.time()
    strat.run_dual(df15, df1, warmup=args.warmup)
    trades = sorted(strat.execution.trades, key=lambda t: t.entry_ms)
    print(f"\n{name}   ({time.time() - t0:.0f}s)   cost profile {args.profile}")
    print(_line("all trades", [t.r for t in trades]))
    print(_line("primary", [t.r for t in trades if t.kind == "primary"]))
    for src in sorted({t.src for t in trades if t.kind == "secondary"}, key=str):
        print(_line(f"{src}", [t.r for t in trades if t.kind == "secondary" and t.src == src]))
    ngs = [t for t in trades if t.src == "nogap shift"]
    if ngs:
        years: dict = {}
        for t in ngs:
            y = time.gmtime(t.entry_ms / 1000).tm_year
            years.setdefault(y, []).append(t.r)
        print(
            "  no-gap shift by year: "
            + "  ".join(f"{y} n{len(v)} {sum(v):+.1f}" for y, v in sorted(years.items()))
        )
        reasons: dict = {}
        for t in ngs:
            reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
        print(
            "  no-gap shift exits: "
            + "  ".join(f"{k or '?'} {v}" for k, v in sorted(reasons.items()))
        )
    sys.stdout.flush()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--variant", default="all", choices=[*_VARIANTS, "all"])
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2026-08-06")
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--profile", default="puprime_ecn")
    ap.add_argument(
        "--fast-min",
        type=int,
        default=1,
        choices=[1, 5],
        help="the fast clock the no-gap shift is read on",
    )
    ap.add_argument("--tp-r", type=float, default=None, help="override the no-gap shift target")
    ap.add_argument("--broker-dir", default=str(_ROOT / "backtest/cache/VantageMarkets_Demo"))
    args = ap.parse_args(argv)
    cdir = Path(args.broker_dir)
    df15 = _load(cdir, args.symbol, "M15", args.start, args.end)
    df1 = _load(cdir, args.symbol, f"M{args.fast_min}", args.start, args.end)
    print(
        f"{args.symbol}  15m {len(df15):,}  fast M{args.fast_min} {len(df1):,}   "
        f"{df15.index[0]} -> {df15.index[-1]}"
    )
    for name in _VARIANTS if args.variant == "all" else [args.variant]:
        run_variant(name, df15, df1, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
