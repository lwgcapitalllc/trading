#!/usr/bin/env python3
"""realign_inverse.py — what happens if you take the OPPOSITE side of every Realign trigger?

**The question this exists to answer** (Aaron, 2026-09-17): "if my realign loses seventy percent
of the time, why do I not just take the trade in the opposite direction?"

Two arms are printed, and they answer two DIFFERENT questions:

1. **MIRROR** — the honest inverse. Every trigger the real strategy fires is replayed at the same
   bar with its direction flipped, its STOP where its TARGET was and its TARGET where its STOP was.
   Its R is therefore measured against a different (usually much larger) risk distance, so it is
   NOT the real book's R with the sign changed. This arm goes through the REAL `RealignExecution`
   — same sizing, same three-stage ladder, same runner trail, same time stop, same costs, same one
   position slot — because only the trigger's geometry is replaced. Same seam as
   `realign_control.py` (`strategy.tracker`), and for the same reason: a second exit ladder would
   make the two arms differ in two ways instead of one.

2. **SIGN-FLIP** — the fantasy version, sum(-R) over the real book. Nobody can trade it (it assumes
   you are paid the negative of an outcome whose risk you never took), but it is the CEILING of the
   idea, so if it loses, every real version of the idea loses too.

⚠ **Market entry only.** The mirrored trigger carries no retest level: the real one's level is a
structure price on the other side, and mirroring it would invent a level no engine published. The
tool REFUSES a retest config rather than silently substituting one.

⚠ **This is a measurement, not a strategy.** Nothing here is wired to a bot.

Usage:
    python backtest/tools/realign_inverse.py --start 2020-01-02 --end 2026-08-06 \\
        --server VantageMarkets_Demo --profile puprime_ecn
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backtest.tools.realign_control import (  # noqa: E402
    _build_config,
    _replay,
    _ScriptedTracker,
    _stats,
)


def _book(rs: List[float]) -> dict:
    st = _stats(rs)
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    gross_w = sum(wins)
    gross_l = -sum(losses)
    st["win_pct"] = 100.0 * len(wins) / st["n"] if st["n"] else 0.0
    st["pf"] = (gross_w / gross_l) if gross_l > 0 else float("inf")
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    st["maxdd"] = dd
    return st


def _line(tag: str, st: dict) -> str:
    return (
        f"{tag:<10} {st['n']:3d} trades  {st['sum']:+8.2f}R  avg {st['avg']:+.3f}R  "
        f"win {st['win_pct']:5.1f}%  PF {st['pf']:.2f}  maxDD {st['maxdd']:.2f}R"
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="5")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--server", default=None)
    ap.add_argument("--profile", default=None)
    ap.add_argument("--set", dest="sets", action="append", default=[])
    args = ap.parse_args(argv)

    from realign.config import RealignConfig

    from backtest.data.source import BarSource

    profile = None
    if args.profile:
        from backtest.fills import PROFILES

        if args.profile not in PROFILES:
            raise SystemExit(f"--profile {args.profile!r}: not in fills.PROFILES")
        profile = PROFILES[args.profile]

    df = BarSource(server=args.server).load(args.symbol, args.tf, args.start, args.end)
    cfg = _build_config(RealignConfig, args.symbol, args.sets)
    if cfg.realign_entry_mode != "market":
        raise SystemExit(
            f"realign_entry_mode={cfg.realign_entry_mode!r}: the mirror has no retest level "
            "to rest at (see the docstring). Market entry only."
        )

    print(f"bars     {len(df):,} {args.tf}m {args.symbol}  {df.index[0]} -> {df.index[-1]}")
    print(f"broker   {args.server or '(attached terminal)'}")
    print(f"costs    {args.profile or 'NONE — free book'}")
    print(f"config   {', '.join(args.sets) or '(shipped defaults)'}\n")

    real = _replay(cfg, df, profile)
    real_rs = [t.r for t in real.execution.trades]
    print(_line("REAL", _book(real_rs)))
    print(_line("SIGN-FLIP", _book([-r for r in real_rs])))

    times = [int(t.value // 1_000_000) for t in df.index]
    triggers = []
    for i, rs_ in enumerate(real.states):
        if rs_ is not None and rs_.trigger_dir != 0:
            triggers.append((times[i], rs_.trigger_dir, rs_.trigger_stop, rs_.trigger_target))
    print(f"           {len(triggers)} triggers fired ({len(real_rs)} became trades)\n")

    # The mirror: same bar, flipped side, stop and target exchanged.
    schedule: Dict[int, Tuple[int, float, float, Optional[float]]] = {
        ms: (-d, target, stop, None) for ms, d, stop, target in triggers
    }
    inv = _replay(cfg, df, profile, tracker=_ScriptedTracker(schedule))
    inv_rs = [t.r for t in inv.execution.trades]
    print(_line("MIRROR", _book(inv_rs)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
