#!/usr/bin/env python3
"""realign_control.py — is the Realign setup better than entering at a RANDOM moment?

**The question this exists to answer.** Every Realign figure in the repo says what the setup made.
None of them says whether the SETUP did it. A strategy can look profitable because its exit ladder,
its stop geometry and its instrument's drift make money from almost any entry — and gold over
2020-2025 drifts hard. `strategies/python/realign/realign_optimization.md` Run 1 found exactly that
on the 5-minute-only arm: **random entries at the same months and hours beat the pattern's own.**

**What is held fixed, and why that is the whole design.** The control replays the REAL
`RealignStrategy` through the REAL `RealignExecution` — same entry placement, same %-risk sizing,
same three-stage stop, same runner trail, same time stop, same flat-by-close, same cost profile,
same one-position slot. Only the TRIGGER is replaced: a scripted tracker fires the same number of
setups, on the same side, in the same calendar month and New York hour, with the **same stop
distance, the same target distance and the same retest offset** as a real trigger — at a randomly
chosen bar. Everything that could make money other than the pattern is therefore present in both
arms, and the difference is the pattern.

🔴 **A SECOND IMPLEMENTATION OF THE EXIT LADDER WOULD INVALIDATE THE COMPARISON, WHICH IS WHY THERE
ISN'T ONE.** The obvious build — walk the real trade list and re-simulate random entries — has to
re-derive the ladder, and then the control and the strategy differ in two ways instead of one. The
scripted tracker is injected at the ONE seam (`strategy.tracker`) where the trigger is decided, so
every line after it is the shipped code. See `_ScriptedTracker`.

⚠ **The position slot is why the control cannot be estimated from a finished trade list.** With one
slot a randomly-timed setup displaces whatever the next real setup would have been, so the control's
trade count is not guaranteed to match the strategy's — it is REPORTED, not assumed. This is the
same effect that got the minimum-stop guard's sign wrong (+1.84R estimated, -1.84R replayed).

Usage:
    python backtest/tools/realign_control.py --start 2020-01-02 --end 2025-08-05 \\
        --server VantageMarkets_Demo --profile puprime_standard --reps 20 \\
        --set realign_entry_mode=retest --set realign_retest_bars=5 \\
        --set exec_time_stop_mode=Always --set exec_time_stop_hrs=12 --set flat_by_close=true
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_NY = ZoneInfo("America/New_York")


# ── the one seam the control replaces ────────────────────────────────────────────
class _ScriptedTracker:
    """Fires triggers from a pre-drawn schedule instead of reading market structure.

    Duck-types `RealignTracker`: `on_htf` is a no-op (the control has no false break to arm on)
    and `update` returns a `RealignState` carrying a scheduled trigger, or an empty one.

    ⚠ It reports `long_armed` / `short_armed` as False throughout. Nothing in the execution path
    reads them — they are the tracker's REPORTING fields — but a future consumer that did would be
    reading "no setup is armed" on a bar the control is about to trade, so this is stated rather
    than left to be discovered.
    """

    def __init__(self, schedule: Dict[int, Tuple[int, float, float, Optional[float]]]) -> None:
        self._sched = schedule
        self.fired = 0

    def on_htf(self, ev, time_ms, broken_high, broken_low) -> None:  # noqa: D102
        return None

    def update(self, time_ms: int, high: float, low: float, ext, internal):
        from realign.tracker import RealignState

        hit = self._sched.get(time_ms)
        if hit is None:
            return RealignState()
        self.fired += 1
        d, stop, target, level = hit
        return RealignState(
            trigger_dir=d, trigger_stop=stop, trigger_target=target, trigger_level=level
        )


def _ny_hour(ms: int) -> int:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).astimezone(_NY).hour


def _month(ms: int) -> Tuple[int, int]:
    d = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return (d.year, d.month)


def _build_config(base_cls, symbol: str, sets: List[str]):
    cfg = base_cls(symbol=symbol)
    over: dict = {}
    for s in sets:
        field, raw = s.split("=", 1)
        field, raw = field.strip(), raw.strip()
        if not hasattr(cfg, field):
            raise SystemExit(f"--set {field!r}: no such field")
        cur = getattr(cfg, field)
        if isinstance(cur, bool):
            over[field] = raw.lower() in ("1", "true", "yes", "on")
        elif isinstance(cur, int) and not isinstance(cur, bool):
            over[field] = int(float(raw))
        elif isinstance(cur, float):
            over[field] = float(raw)
        elif cur is None:
            over[field] = (
                None
                if raw.lower() in ("none", "off")
                else (float(raw) if raw.replace(".", "", 1).isdigit() else raw)
            )
        else:
            over[field] = raw
    return dataclasses.replace(cfg, **over)


def _replay(cfg, df, profile, tracker=None):
    from realign.strategy import RealignStrategy

    from backtest.replay import build_strategy

    s = build_strategy(RealignStrategy, cfg, initial_capital=10_000.0, cost_profile=profile)
    if tracker is not None:
        s.tracker = tracker
    s.run(df)
    return s


def _stats(rs: List[float]) -> dict:
    n = len(rs)
    if not n:
        return {"n": 0, "sum": 0.0, "avg": 0.0, "sd": 0.0}
    m = sum(rs) / n
    sd = (sum((r - m) ** 2 for r in rs) / (n - 1)) ** 0.5 if n > 1 else 0.0
    return {"n": n, "sum": sum(rs), "avg": m, "sd": sd}


def main(argv=None) -> int:
    import numpy as np

    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="5")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--server", default=None)
    ap.add_argument("--profile", default=None)
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20260915)
    ap.add_argument(
        "--set",
        dest="sets",
        action="append",
        default=[],
        help="FIELD=VALUE applied to BOTH arms. Repeatable.",
    )
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

    print(f"bars     {len(df):,} {args.tf}m {args.symbol}  {df.index[0]} -> {df.index[-1]}")
    print(f"broker   {args.server or '(attached terminal)'}")
    print(f"costs    {args.profile or 'NONE — free book'}")
    print(f"config   {', '.join(args.sets) or '(shipped defaults)'}")
    print(f"reps     {args.reps}  seed {args.seed}\n")

    # ── arm 1: the real strategy ────────────────────────────────────────────────
    real = _replay(cfg, df, profile)
    real_rs = [t.r for t in real.execution.trades]
    st = _stats(real_rs)
    print(f"REAL      {st['n']:3d} trades  {st['sum']:+8.2f}R  avg {st['avg']:+.3f}R")

    # The TRIGGER GEOMETRY, captured from the real run's own state stream — not from the
    # finished trade list, which has already dropped every trigger the slot was busy for.
    # A control matched only on TAKEN trades would face an easier problem than the strategy.
    times = [int(t.value // 1_000_000) for t in df.index]
    closes = df["close"].to_numpy()
    triggers = []
    for i, rs_ in enumerate(real.states):
        if rs_ is not None and rs_.trigger_dir != 0:
            triggers.append(
                (
                    times[i],
                    closes[i],
                    rs_.trigger_dir,
                    rs_.trigger_stop,
                    rs_.trigger_target,
                    rs_.trigger_level,
                )
            )
    print(
        f"          {len(triggers)} triggers fired ({st['n']} became trades — the rest "
        f"found the one position slot busy)\n"
    )

    # Pools of candidate bars, keyed the way the control is MATCHED: calendar month + NY hour.
    pools: Dict[Tuple[Tuple[int, int], int], List[int]] = {}
    for i, ms in enumerate(times):
        pools.setdefault((_month(ms), _ny_hour(ms)), []).append(i)

    rng = np.random.default_rng(args.seed)
    ctl_avgs: List[float] = []
    ctl_sums: List[float] = []
    ctl_ns: List[int] = []
    for rep in range(args.reps):
        schedule: Dict[int, Tuple[int, float, float, Optional[float]]] = {}
        for ms, close, d, stop, target, level in triggers:
            pool = pools.get((_month(ms), _ny_hour(ms)))
            if not pool:
                continue
            j = int(pool[rng.integers(len(pool))])
            c2 = float(closes[j])
            # Every DISTANCE is preserved exactly; only the moment moves.
            schedule[times[j]] = (
                d,
                c2 - (close - stop),
                c2 + (target - close),
                None if level is None else c2 - (close - level),
            )
        tr = _ScriptedTracker(schedule)
        s = _replay(cfg, df, profile, tracker=tr)
        rs_ = [t.r for t in s.execution.trades]
        cs = _stats(rs_)
        ctl_avgs.append(cs["avg"])
        ctl_sums.append(cs["sum"])
        ctl_ns.append(cs["n"])
        print(
            f"  control rep {rep + 1:2d}  {cs['n']:3d} trades  {cs['sum']:+8.2f}R  "
            f"avg {cs['avg']:+.3f}R"
        )

    if not ctl_avgs:
        raise SystemExit("no control replays completed")
    m = sum(ctl_avgs) / len(ctl_avgs)
    sd = (
        (sum((a - m) ** 2 for a in ctl_avgs) / (len(ctl_avgs) - 1)) ** 0.5
        if len(ctl_avgs) > 1
        else 0.0
    )
    print(
        f"\ncontrol   {sum(ctl_ns) / len(ctl_ns):.1f} trades avg  "
        f"{sum(ctl_sums) / len(ctl_sums):+8.2f}R  avg {m:+.3f}R  (sd across reps {sd:.3f})"
    )
    # 🔴 z is measured against the spread of the CONTROL REPS — how far the real result sits
    # from what random timing produces. It is NOT the strategy's own standard error, which
    # answers a different question (is this edge distinguishable from zero) and is printed
    # beside it so the two cannot be confused.
    z = (st["avg"] - m) / sd if sd > 0 else float("nan")
    own_se = st["sd"] / st["n"] ** 0.5 if st["n"] else float("nan")
    print(
        f"\nREAL avg {st['avg']:+.3f}R  vs  control {m:+.3f}R   "
        f"beats random by {st['avg'] - m:+.3f}R a trade"
    )
    print(f"z vs random timing: {z:+.2f}   (bar is 2.0)")
    print(f"the strategy's own standard error is {own_se:.3f}R — a DIFFERENT question")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
