"""blocker_ab_study.py — are the live SOS Fade bot's four entry blockers refusing good trades or bad
ones? Each is switched OFF on its own and the whole history replayed, so a freed slot is counted.

A STUDY: it changes no bot. The replay is `bot_confluence_study.py`'s (live instance config, PU Prime
XAUUSD.p cached bars, puprime_ecn costs, one position, M15 + the M5 re-entry feed), with one config
field overridden per arm. 2018-09-14 -> 2026-09-29 in ONE replay per arm, same window as Run 64 —
the baseline must reproduce Run 64's 278 trades / +162.1R before any arm is read.

THE ASK (Aaron, 2026-09-30): "tell me if they blocked good trades or if they're blocking bad
trades ... should I loosen them a bit?"

THE ARMS — one blocker off each:
  late    the final-hour rule                       exec_no_late_day  -> False
  veto    the divergence / extreme-RSI veto         exec_respect_veto -> False
  tight   the minimum stop distance                 exec_min_stop_mode -> "Off"
  quiet   the dead-market (minimum volatility) floor exec_min_atr_pct -> 0

THE SCORE — trades matched to the baseline by entry minute + side:
  added (only in the arm), displaced (only in the baseline), re-priced (in both, R differs).
  Change = arm R - baseline R. ± = one standard error of the sum of those differing trades;
  P(better) = share of 5,000 bootstrap resamples of them whose sum is above zero.
  Halves split 2022-11-01, as in Run 64.
  ⚠ The quiet floor and the stop floor were TUNED on 2020-2026, so their full-history benefit is
    partly in-sample; the 2018-2019 slice is printed separately for that reason.

Usage (repo root, command-center/backend/.venv/bin/python):
  python backtest/tools/blocker_ab_study.py     # five replays in parallel, a few minutes
"""

from __future__ import annotations

import dataclasses
import importlib
import math
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "engines", ROOT / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import bot_confluence_study as B  # noqa: E402

from backtest.data.source import BarSource  # noqa: E402
from backtest.replay.build import build_strategy  # noqa: E402

KEY = "sos_fade_demo"
START, END = "2018-09-14", "2026-09-29"
SPLIT = pd.Timestamp("2022-11-01")
UNTUNED_END = pd.Timestamp("2020-01-01")
SEED = 20260930
# arm -> (reader's name, block code in `execution._BLOCK_LABEL`, config override)
ARMS = {
    "base": ("baseline", None, {}),
    "late": ("Final hour", 3, {"exec_no_late_day": False}),
    "veto": ("Divergence / RSI veto", 4, {"exec_respect_veto": False}),
    "tight": ("Stop too tight", 7, {"exec_min_stop_mode": "Off"}),
    "quiet": ("Market too quiet", 10, {"exec_min_atr_pct": 0.0}),
}


def run_arm(arm: str) -> tuple[str, pd.DataFrame, Counter]:
    spec = importlib.import_module("strategies.python.sos_fade").LAB_STRATEGY
    cfg, _ = B.live_config(KEY, spec["config"])
    cfg = dataclasses.replace(cfg, **ARMS[arm][2])
    src = BarSource(server=B.SERVER)
    df = src.load(B.SYMBOL, "15", START, END)
    strat = build_strategy(
        spec["strategy"], cfg, initial_capital=B.CAPITAL, cost_profile=B.PROFILES["puprime_ecn"]
    )
    if cfg.exec_secondary:
        fill = src.load(B.SYMBOL, str(int(cfg.exec_sec_fill_tf_min)), START, END)
        strat.run_dual(df, fill, warmup=B.WARMUP)
    else:
        strat.run(df, warmup=B.WARMUP)
    ex = strat.execution
    rows = []
    for t in ex.trades:
        ms = int(getattr(t, "entry_ms", 0) or 0)
        ts = pd.Timestamp(ms, unit="ms") if ms else df.index[min(t.entry_index, len(df) - 1)]
        rows.append(
            dict(entry=ts, dir=int(t.dir), r=float(t.r), kind=getattr(t, "kind", "primary"))
        )
    tr = pd.DataFrame(rows)
    tr["key"] = list(zip(tr.entry.dt.floor("min"), tr.dir))
    blocks = Counter(c for b in ex.blocks for c in set(b.codes))  # every rule refusing a setup
    return arm, tr, blocks


def max_dd(r: np.ndarray) -> float:
    eq = np.cumsum(r)
    return float((np.maximum.accumulate(np.r_[0.0, eq])[1:] - eq).max())


def report(name: str, code: int, base: pd.DataFrame, arm: pd.DataFrame, n_blocks: int, rng) -> None:
    add = arm[~arm.key.isin(set(base.key))]
    gone = base[~base.key.isin(set(arm.key))]
    both = base.merge(arm, on="key", suffixes=("_b", "_a"))
    moved = (both.r_a - both.r_b)[lambda s: s.abs() > 1e-9]
    vals = np.r_[add.r.to_numpy(), -gone.r.to_numpy(), moved.to_numpy()]
    n = len(vals)
    se = math.sqrt(n) * vals.std(ddof=1) if n > 1 else float("nan")
    p = (
        (np.array([rng.choice(vals, n).sum() for _ in range(5000)]) > 0).mean()
        if n
        else float("nan")
    )

    def part(lo, hi):
        pick = lambda t: t[(t.entry >= lo) & (t.entry < hi)].r.sum()  # noqa: E731
        return pick(arm) - pick(base)

    lo, hi = pd.Timestamp.min, pd.Timestamp.max
    print(
        f"\n== {name} OFF — {n_blocks} setups carried this block in the baseline\n"
        f"  trades {len(arm)} ({len(arm) - len(base):+d})   R {arm.r.sum():+.1f}   "
        f"change {arm.r.sum() - base.r.sum():+.1f} ± {se:.1f}   P(better) {p:.2f}   "
        f"max DD {max_dd(arm.r.to_numpy()):.1f}R (baseline {max_dd(base.r.to_numpy()):.1f}R)\n"
        f"  added {len(add)} = {add.r.sum():+.1f}R (wins {(add.r > 0.05).sum()}, losses "
        f"{(add.r < -0.05).sum()}); displaced {len(gone)} = {gone.r.sum():+.1f}R; "
        f"re-priced {moved.sum():+.1f}R\n"
        f"  halves: before 2022-11 {part(lo, SPLIT):+.1f}R, after {part(SPLIT, hi):+.1f}R; "
        f"2018-19 (untuned) {part(lo, UNTUNED_END):+.1f}R"
    )
    for sign, t in (("+", add), ("-", gone)):
        for _, x in t.sort_values("entry").iterrows():
            print(
                f"    {sign} {x.entry:%Y-%m-%d %H:%M} {'L' if x.dir > 0 else 'S'} {x.kind:9s} {x.r:+.2f}R"
            )


def main() -> None:
    with ProcessPoolExecutor(max_workers=len(ARMS)) as pool:
        out = {a: (tr, blk) for a, tr, blk in pool.map(run_arm, ARMS)}
    base, blocks = out["base"]
    print(
        f"baseline {KEY} {START} -> {END}: {len(base)} trades, {base.r.sum():+.1f}R, "
        f"max DD {max_dd(base.r.to_numpy()):.1f}R  (Run 64: 278 trades, +162.1R)"
    )
    rng = np.random.default_rng(SEED)
    for arm, (name, code, _) in ARMS.items():
        if arm != "base":
            report(name, code, base, out[arm][0], blocks.get(code, 0), rng)


if __name__ == "__main__":
    main()
