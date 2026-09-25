#!/usr/bin/env python3
"""setup_alert_rate.py — what ANY bot's signals room would have said, and proof it moves no trade.

Builds the strategy the way the live runner does (`runner._build_strategy`: the package's
`LAB_STRATEGY`, the instance's own `strategy_params`), steps it through the live contract
(`signals` → `sequence` → `execution.step`) over the broker's cached bars, and feeds its setups
through the REAL alert layer (`algos/live/setup_alerts.py`) with a counting sender — so the
messages counted are the ones the live bot would post. Then it replays the same bars with the
strategy's setup watch switched off.

Prints, and EXITS 1 if either of the first two fails:
  1. REPORTING ONLY  the trade list is identical with the watch on and off
  2. ANNOUNCED       every trade had its setup's ENTERED reply
  3. VOLUME          roots and messages a month, the share of roots that became trades

⚠ A strategy whose setup watch is not a `setup_watch` attribute with an `observe` method (SOS
Fade's is built into its order layer) cannot be switched off from here, so check 1 is skipped
and SAID to be skipped. `backtest/tools/alert_rate.py` is the older SOS Fade / extreme-leg tool.

Run it for every new bot that reports setups, and after any change to a bot's entry logic.

Usage:
  python algos/tools/setup_alert_rate.py fft_1
  python algos/tools/setup_alert_rate.py realign_1 --start 2024-01-01
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "strategies" / "python", ROOT / "algos" / "live"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

INSTANCES = ROOT / "algos" / "markets" / "fx" / "instances"
CACHE = ROOT / "backtest" / "cache"
MINUTES = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "H4": 240}


def build(cfg: dict):
    """The runner's construction, minus the broker: same class, same params, by name."""
    pkg = importlib.import_module(cfg["strategy_package"])
    lab = pkg.LAB_STRATEGY
    cls, cfg_cls = lab["strategy"], lab["config"]
    if cls.__name__ != cfg["strategy_class"]:
        sys.exit(f"{cfg['strategy_package']} provides {cls.__name__}, not {cfg['strategy_class']}")
    params = dict(cfg["strategy_params"])
    params.setdefault("symbol", cfg["symbol"])
    return cls(cfg_cls(**params), initial_capital=10_000.0)


def replay(cfg: dict, df, *, watch: bool, alerts=None):
    from backtest.replay import EngineStack, iter_bars

    s = build(cfg)
    s.execution.bar_ms = MINUTES[cfg["timeframe"]] * 60_000
    if not watch:
        s.setup_watch.observe = lambda *a, **k: None
    stack = EngineStack(s.engine_config())
    for bar in iter_bars(df):
        sig = s.signals.update(stack.step(bar))
        s.execution.step(sig, s.sequence.update(sig))
        if alerts is not None:
            alerts.on_bar(s)
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bot", help="the bot's key, e.g. fft_1")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--bars", type=Path, default=None, help="a bar CSV (time,open,high,low,close)")
    a = ap.parse_args()

    from setup_alerts import SetupAlerts

    cfg = json.loads((INSTANCES / a.bot / "config.json").read_text())
    server = cfg["server"].replace("-", "_")
    bars = a.bars or CACHE / server / f"{cfg['symbol'].replace('.', '_')}__{cfg['timeframe']}.csv"
    if not bars.exists():
        sys.exit(f"no cached bars at {bars} — pass --bars")
    df = pd.read_csv(bars, usecols=["time", "open", "high", "low", "close"], parse_dates=["time"])
    df = df[df["time"] >= a.start]
    if a.end:
        df = df[df["time"] < a.end]
    df = df.set_index("time").astype(float)

    posts = []

    def send(text, *_, reply_to=None, **__):
        posts.append(text)
        return len(posts)

    sa = SetupAlerts(send=send, display=cfg.get("display_name", a.bot), digits=2)
    if not sa.supported(build(cfg)):
        sys.exit(f"{cfg['strategy_class']} does not report setups — nothing to measure")
    on = replay(cfg, df, watch=True, alerts=sa)
    switchable = callable(getattr(getattr(on, "setup_watch", None), "observe", None))

    def book(s):
        return [
            (t.dir, t.entry_ms, t.entry_price, t.exit_ms, t.exit_price, t.qty, t.exit_reason)
            for t in s.execution.trades
        ]

    same = book(on) == book(replay(cfg, df, watch=False)) if switchable else None
    kinds = Counter(p.split("\n")[0] for p in posts)
    roots = sum(v for k, v in kinds.items() if "SETUP FORMING" in k)
    entered = sum(v for k, v in kinds.items() if "ENTERED" in k)
    trades = len(on.execution.trades)
    months = (df.index[-1] - df.index[0]).days / 30.44

    print(
        f"{a.bot}: {len(df):,} {cfg['timeframe']} bars, {df.index[0]} -> {df.index[-1]} "
        f"({months:.1f} months)"
    )
    print(
        "1. reporting only: "
        + (
            "SKIPPED — this strategy's watch cannot be switched off from here"
            if same is None
            else f"{'SAME' if same else 'DIFFERENT'} — {trades} trades with the watch on and off"
        )
    )
    print(f"2. announced: {entered} ENTERED replies for {trades} trades")
    print(
        f"3. {roots} roots ({roots / months:.1f} a month), {entered / max(roots, 1):.0%} became "
        f"trades; {len(posts)} messages ({len(posts) / months:.1f} a month)"
    )
    for k, v in kinds.most_common():
        print(f"   {v:6d}  {k}")
    reasons = Counter(p.split("\n")[1][:90] for p in posts if "NO TRADE" in p)
    if reasons:
        print("   why no trade:")
        for k, v in reasons.most_common(8):
            print(f"   {v:6d}  {k}")
    return 0 if same is not False and entered == trades else 1


if __name__ == "__main__":
    sys.exit(main())
