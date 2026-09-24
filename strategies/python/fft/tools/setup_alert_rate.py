#!/usr/bin/env python3
"""setup_alert_rate.py — what FFT's signals room would have said, and proof it moves no trade.

Replays FFT over the raw PU Prime 1-minute bars twice — the setup watch ON and OFF — and feeds the
ON run through the REAL alert layer (`algos/live/setup_alerts.py`) with a counting sender, so the
messages counted are the ones a live bot would post.

Prints, and EXITS 1 if either of the first two fails:
  1. REPORTING ONLY  the trades and every spent leg are identical with the watch on and off
  2. ANNOUNCED       every trade had its setup's ENTERED reply
  3. VOLUME          roots and messages a month, the share of roots that became trades, and the
                     lead time from the root to the fill

⚠ `backtest/tools/alert_rate.py` is the SOS Fade / extreme-leg tool and does not run a 1-minute
bot, so FFT is measured here. Re-run it after any change to FFT's entry logic or to `setups.py`.

Usage:
  python strategies/python/fft/tools/setup_alert_rate.py                        # 2020-01 -> now
  python strategies/python/fft/tools/setup_alert_rate.py --start 2026-06-01 --config fft_1
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
for _p in (ROOT, ROOT / "strategies" / "python", ROOT / "algos" / "live"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

CACHE = ROOT / "backtest" / "cache" / "PUPrime_Demo" / "XAUUSD_p__M1.csv"
INSTANCES = ROOT / "algos" / "markets" / "fx" / "instances"


def replay(df, cfg, *, watch: bool, alerts=None):
    import fft
    from backtest.replay import EngineStack, iter_bars

    s = fft.FftStrategy(config=cfg)
    s.execution.bar_ms = 60_000
    if not watch:
        s.setup_watch.observe = lambda *a, **k: None
    stack = EngineStack(s.engine_config())
    for bar in iter_bars(df):
        s.step(stack.step(bar))
        if alerts is not None:
            alerts.on_bar(s)
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--config", default="fft_1", help="instance whose settings to replay")
    ap.add_argument("--bars", type=Path, default=CACHE)
    a = ap.parse_args()

    from fft.config import FftConfig
    from setup_alerts import SetupAlerts

    params = json.loads((INSTANCES / a.config / "config.json").read_text())["strategy_params"]
    cfg = FftConfig(**params)
    df = pd.read_csv(a.bars, usecols=["time", "open", "high", "low", "close"], parse_dates=["time"])
    df = df[df["time"] >= a.start]
    if a.end:
        df = df[df["time"] < a.end]
    df = df.set_index("time").astype(float)

    posts = []

    def send(text, *_, reply_to=None, **__):
        posts.append(text)
        return len(posts)

    sa = SetupAlerts(send=send, display="FFT", digits=2)
    on = replay(df, cfg, watch=True, alerts=sa)
    off = replay(df, cfg, watch=False)

    def book(s):
        return (
            [(t.dir, t.entry_ms, t.entry_price, t.exit_ms, t.exit_price, t.qty, t.exit_reason)
             for t in s.execution.trades],
            [(x.kind, x.ts_ms, x.dir, x.traded, x.why, x.fill_price) for x in s.touches],
        )

    same = book(on) == book(off)
    kinds = Counter(p.split("\n")[0] for p in posts)
    roots = sum(v for k, v in kinds.items() if "SETUP FORMING" in k)
    entered = sum(v for k, v in kinds.items() if "ENTERED" in k)
    trades = len(on.execution.trades)
    months = (df.index[-1] - df.index[0]).days / 30.44

    print(f"{len(df):,} one-minute bars, {df.index[0]} -> {df.index[-1]} ({months:.1f} months)")
    print(f"1. reporting only: {'SAME' if same else 'DIFFERENT'} — {trades} trades, "
          f"{len(on.touches)} spent legs")
    print(f"2. announced: {entered} ENTERED replies for {trades} trades")
    print(f"3. {roots} roots ({roots / months:.1f} a month), {entered / max(roots, 1):.0%} became "
          f"trades; {len(posts)} messages ({len(posts) / months:.1f} a month)")
    for k, v in kinds.most_common():
        print(f"   {v:6d}  {k}")
    return 0 if same and entered == trades else 1


if __name__ == "__main__":
    sys.exit(main())
