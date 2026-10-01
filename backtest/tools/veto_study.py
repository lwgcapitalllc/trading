"""veto_study.py — the live SOS Fade bot's divergence / extreme-RSI veto, taken apart: which half of
it does the work, whether it only DELAYS a setup or kills it, and whether a looser or wider
definition of it is better. Every arm is a full replay, so a freed slot is counted.

A STUDY: it changes no bot. Replay, matching and scoring are `blocker_ab_study.py`'s (live
instance config, PU Prime XAUUSD.p, puprime_ecn costs, one position, M15 + M5 re-entry feed,
2018-09-14 -> 2026-09-29). Baseline must reproduce Run 64 / 66: 278 trades, +162.1R.

THE ASK (Aaron, 2026-09-30): "is it hurting us or can I loosen it a bit more or can I stretch the
configs of what a divergence is".

WHAT THE VETO IS (signals.py `sos_aware_veto`) — two halves, and it only ever refuses an ENTRY:
  EXTREME   RSI(14) at or above 80 blocks longs; at or below 20 blocks shorts. Live, every bar.
  DIVERGENCE  a confirmed opposing RSI divergence, printed at or before the SOS bar, not yet
            superseded by a structure break, and younger than 100 bars, blocks that side.
  A divergence itself: RSI pivot 5 bars each side, the pivot's RSI inside 25 / 75 (the ENGINE's
  zone, which the bot's settings do not expose).
  ⚠ The bot's "RSI Length" and "Pivot Width" settings reached no engine when Run 68 was taken, so
    its shape arms set the ENGINE directly. They were wired 2026-09-30 and the bot's settings now
    WIN over an engine override, so those arms set the settings instead — same values, same stack.

THE ARMS
  anatomy   whole veto off; extreme half off; divergence half off
  extreme   75/25, 85/15, 90/10 (shipped 80/20)
  lifetime  a divergence lives 25, 50, 150, 200 bars (shipped 100)
  shape     pivot width 3, 7, 10; RSI length 9, 21; divergence zone 30/70, 20/80 (shipped 5, 14,
            25/75). ⚠ RSI length also moves the extreme half, which reads the same RSI.

GATES — fixed 2026-09-30 before any arm was run. An arm is ADOPTED only if all four hold:
  1 it beats the baseline in BOTH halves (split 2022-11-01);
  2 no single differing trade is more than half the net gain;
  3 P(better) >= 0.90 (5,000 bootstrap resamples of the differing trades);
  4 its neighbour(s) in the same sweep are not worse than the baseline — a lone spike is a fit.
  ⚠ There is NO unspent held-out window: Run 65 spent 2018-09 -> 2019-12 and 2025-08 -> 2026-09,
    and the veto's one decisive trade (2025-10-21) sits inside it. The gates carry the whole load.

Usage (repo root, command-center/backend/.venv/bin/python):
  python backtest/tools/veto_study.py
"""

from __future__ import annotations

import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocker_ab_study as A  # noqa: E402

VETO = 4  # `execution._BLOCK_LABEL`
# name -> (sweep group, bot config override, engine override)
ARMS = {
    "baseline": ("", {}, {}),
    "veto off": ("anatomy", {"exec_respect_veto": False}, {}),
    "extreme half off": ("anatomy", {"div_extreme_ob": 101, "div_extreme_os": -1}, {}),
    "divergence half off": ("anatomy", {"div_valid_bars": 0}, {}),
    "extreme 75/25": ("extreme", {"div_extreme_ob": 75, "div_extreme_os": 25}, {}),
    "extreme 85/15": ("extreme", {"div_extreme_ob": 85, "div_extreme_os": 15}, {}),
    "extreme 90/10": ("extreme", {"div_extreme_ob": 90, "div_extreme_os": 10}, {}),
    "lifetime 25": ("lifetime", {"div_valid_bars": 25}, {}),
    "lifetime 50": ("lifetime", {"div_valid_bars": 50}, {}),
    "lifetime 150": ("lifetime", {"div_valid_bars": 150}, {}),
    "lifetime 200": ("lifetime", {"div_valid_bars": 200}, {}),
    "pivot 3": ("pivot", {"div_pivot_len": 3}, {}),
    "pivot 7": ("pivot", {"div_pivot_len": 7}, {}),
    "pivot 10": ("pivot", {"div_pivot_len": 10}, {}),
    "RSI length 9": ("rsi length", {"div_rsi_len": 9}, {}),
    "RSI length 21": ("rsi length", {"div_rsi_len": 21}, {}),
    "div zone 30/70": ("div zone", {}, {"rsi_oversold": 30.0, "rsi_overbought": 70.0}),
    "div zone 20/80": ("div zone", {}, {"rsi_oversold": 20.0, "rsi_overbought": 80.0}),
}
# Sweep order per group, the shipped value included, for gate 4's neighbours.
LADDERS = {
    "extreme": ["extreme 75/25", "baseline", "extreme 85/15", "extreme 90/10"],
    "lifetime": ["lifetime 25", "lifetime 50", "baseline", "lifetime 150", "lifetime 200"],
    "pivot": ["pivot 3", "baseline", "pivot 7", "pivot 10"],
    "rsi length": ["RSI length 9", "baseline", "RSI length 21"],
    "div zone": ["div zone 20/80", "baseline", "div zone 30/70"],
}


def run(name: str):
    _, cfg_over, eng_over = ARMS[name]
    tr, blocks = A.replay(cfg_over, eng_over)
    vetoed = {(b.dir, b.sos_bar) for b in blocks if VETO in b.codes}
    return name, tr, vetoed


def score(base: pd.DataFrame, arm: pd.DataFrame, rng) -> dict:
    add = arm[~arm.key.isin(set(base.key))]
    gone = base[~base.key.isin(set(arm.key))]
    both = base.merge(arm, on="key", suffixes=("_b", "_a"))
    moved = (both.r_a - both.r_b)[lambda s: s.abs() > 1e-9]
    vals = np.r_[add.r.to_numpy(), -gone.r.to_numpy(), moved.to_numpy()]
    n, diff = len(vals), arm.r.sum() - base.r.sum()
    se = math.sqrt(n) * vals.std(ddof=1) if n > 1 else 0.0
    p = (np.array([rng.choice(vals, n).sum() for _ in range(5000)]) > 0).mean() if n else 0.5
    h = [
        arm[m(arm)].r.sum() - base[m(base)].r.sum()
        for m in (lambda t: t.entry < A.SPLIT, lambda t: t.entry >= A.SPLIT)
    ]
    biggest = float(np.abs(vals).max()) if n else 0.0
    return dict(
        n=len(arm), diff=diff, se=se, p=p, h1=h[0], h2=h[1], add=add, gone=gone, moved=moved,
        dd=A.max_dd(arm.r.to_numpy()), one_trade=diff > 0 and biggest > diff / 2,
    )  # fmt: skip


def anatomy(base: pd.DataFrame, vetoed: set) -> None:
    """Of the setups the veto refused, how many traded anyway once it lifted — delay, not kill."""
    prim = base[base.kind == "primary"]
    traded = {(int(d), int(s)): r for d, s, r in zip(prim.dir, prim.sos_bar, prim.r)}
    later = [traded[k] for k in vetoed if k in traded]
    print(
        f"\nveto-refused setups in the baseline: {len(vetoed)}; traded anyway once the veto lifted: "
        f"{len(later)} ({sum(later):+.1f}R, {sum(r > 0.05 for r in later)} winners)"
    )


def main() -> None:
    with ProcessPoolExecutor(max_workers=9) as pool:
        out = {name: (tr, v) for name, tr, v in pool.map(run, ARMS)}
    base, vetoed = out["baseline"]
    print(
        f"baseline: {len(base)} trades, {base.r.sum():+.1f}R, max DD "
        f"{A.max_dd(base.r.to_numpy()):.1f}R  (Run 64/66: 278 trades, +162.1R)"
    )
    anatomy(base, vetoed)
    rng = np.random.default_rng(A.SEED)
    sc = {k: score(base, tr, rng) for k, (tr, _) in out.items() if k != "baseline"}
    sc["baseline"] = dict(diff=0.0)

    def neighbours_ok(name: str) -> bool:
        grp = ARMS[name][0]
        if grp not in LADDERS:
            return True
        lad = LADDERS[grp]
        i = lad.index(name)
        return all(sc[lad[j]]["diff"] >= 0 for j in (i - 1, i + 1) if 0 <= j < len(lad))

    print(
        f"\n{'arm':<22}{'trades':>7}{'change':>16}{'P(better)':>10}{'1st half':>10}"
        f"{'2nd half':>10}{'max DD':>8}  added / displaced          verdict"
    )
    for name in ARMS:
        if name == "baseline":
            continue
        s = sc[name]
        gates = (
            s["h1"] > 0 and s["h2"] > 0,
            not s["one_trade"],
            s["p"] >= 0.90,
            neighbours_ok(name),
        )
        verdict = "ADOPT" if all(gates) and s["diff"] > 0 else (
            "no change" if not len(s["add"]) and not len(s["gone"]) and not len(s["moved"])
            else "reject"
        )  # fmt: skip
        failed = ",".join(str(i + 1) for i, g in enumerate(gates) if not g)
        print(
            f"{name:<22}{s['n']:>7}{s['diff']:>+9.1f} ± {s['se']:<4.1f}{s['p']:>10.2f}"
            f"{s['h1']:>+10.1f}{s['h2']:>+10.1f}{s['dd']:>7.1f}R  "
            f"{len(s['add']):>3} ({s['add'].r.sum():+6.1f}R) / {len(s['gone']):>3} "
            f"({s['gone'].r.sum():+6.1f}R)  {verdict}{'' if verdict != 'reject' else ' gates ' + failed}"
        )
    for name in ARMS:
        if name == "baseline":
            continue
        s = sc[name]
        if len(s["add"]) + len(s["gone"]) == 0:
            continue
        print(f"\n-- {name}")
        for sign, t in (("+", s["add"]), ("-", s["gone"])):
            for _, x in t.sort_values("entry").iterrows():
                print(
                    f"   {sign} {x.entry:%Y-%m-%d %H:%M} {'L' if x.dir > 0 else 'S'} "
                    f"{x.kind:9s} {x.r:+.2f}R"
                )


if __name__ == "__main__":
    main()
