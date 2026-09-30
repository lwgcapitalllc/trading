"""direction_filter_study.py — would the JARVIS direction rows have made the live SOS Fade bot's
trades better, secondary entries especially, once the number of filters tried has been paid for?

A STUDY: it replays the bot and scores filters on its trade list; it changes no bot. The replay,
the scoring and the gates are `bot_confluence_study.py`'s, imported — nothing re-derived. The
direction rows are `engines/directional_trend/` (gated 2026-09-30), fed the same broker M15 bars.

THE ASK (Aaron, 2026-09-30): "run a test to see if it helps with secondary trades or minimizing
losers."

THE TRADES — `sos_fade_demo` replayed with its LIVE instance config, PU Prime XAUUSD.p cached bars,
puprime_ecn costs, one position, 2018-09-14 -> 2026-09-29 in ONE replay so the slot queue is
continuous. Reconciled against lab run 168cc65e4a0f by entry minute + direction before any result
is read (feedback: studies must match the lab).

THE FEATURES — at each trade's entry, from the last M15 bar CLOSED at or before it:
  W, D, H4, M15 — each row read RELATIVE TO THE TRADE: WITH (row direction = trade direction),
  AGAINST (opposite), or neither (neutral / no break yet). A row that cannot be known yet (warm-up)
  is neither, so no filter touches that trade on that row. The 1m row is left out: it needs a 1m
  feed, and a 15m strategy's entry is not a 1m decision.

THE FILTERS — 24, each a set of trades it REMOVES:
  {skip AGAINST, skip WITH} x {W, D, H4, M15} x {all trades, primary only, secondary only}.
  "primary only" / "secondary only" remove only trades of that kind; the rest are kept.
  Scored only if it removes at least 10 trades and at most half of all trades.

GATES — fixed 2026-09-30 before any trade was tagged
  1 BOTH HALVES  the removed trades lose net R in each half of explore (2020-01-01 -> 2025-08-05,
                 split 2022-11-01).
  2 LUCK  their t below the 5th percentile of the most negative t any of the 24 reaches when the
          feature rows are shuffled across trades (5,000 shuffles, seed fixed).
  3 TEST  survivors only, ONCE: the removed trades lose net R on the held-out periods
          2018-09-14 -> 2019-12-31 and 2025-08-06 -> 2026-09-29.
  ⚠ Removing a trade frees the one slot, so a replay with the filter inside the bot could take a
    setup this list never shows. A survivor's total is an estimate until that replay is run.
  ⚠ The 2018-2019 trades were looked at once before (bot_confluence_study C3, 2026-09-15) for a
    time-of-day question. Their direction rows never were.

Usage (repo root, command-center/backend/.venv/bin/python):
  python backtest/tools/direction_filter_study.py                    # explore + reconcile
  python backtest/tools/direction_filter_study.py --spend-test-set   # gate 3, ONCE
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "engines", ROOT / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import bot_confluence_study as B  # noqa: E402
from directional_trend import DirectionalTrend  # noqa: E402

from backtest.data.source import BarSource  # noqa: E402

KEY = "sos_fade_demo"
START, END = "2018-09-14", "2026-09-29"
EXPLORE = (pd.Timestamp("2020-01-01"), pd.Timestamp("2025-08-06"))
SPLIT = pd.Timestamp("2022-11-01")
LAB_RUN = "168cc65e4a0f"
ROWS = ("W", "D", "H4", "M15")
SCOPES = ("all", "primary", "secondary")
FILTERS = [(how, row, scope) for scope in SCOPES for row in ROWS for how in ("AGAINST", "WITH")]
M15_MS = 900_000


def direction_tape(bars: pd.DataFrame) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Per M15 bar: its CLOSE time (ms) and each row's direction after it (0 when unknown)."""
    eng = DirectionalTrend(15)
    ts = (bars.index.asi8 // 1_000_000).astype(np.int64)
    out = {r: np.zeros(len(bars), dtype=np.int8) for r in ROWS}
    o, h, lo, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    for i in range(len(bars)):
        s = eng.update(int(ts[i]), o[i], h[i], lo[i], c[i])
        for name, row in (("W", s.weekly), ("D", s.daily), ("H4", s.h4), ("M15", s.m15)):
            if row is not None:
                out[name][i] = row.direction
    return ts + M15_MS, out


def features(tr: pd.DataFrame, close_ms: np.ndarray, tape: dict) -> pd.DataFrame:
    entry_ms = pd.DatetimeIndex(tr.entry).asi8 // 1_000_000
    j = np.searchsorted(close_ms, entry_ms, side="right") - 1  # last bar closed at/before entry
    ft = pd.DataFrame(index=tr.index)
    d = tr.dir.to_numpy()
    for r in ROWS:
        v = np.where(j >= 0, tape[r][np.clip(j, 0, None)], 0)
        ft[f"{r}_WITH"] = v == d
        ft[f"{r}_AGAINST"] = v == -d
    return ft


def masks(ft: pd.DataFrame, kind: np.ndarray) -> np.ndarray:
    m = []
    for how, row, scope in FILTERS:
        col = ft[f"{row}_{how}"].to_numpy(bool)
        if scope != "all":
            col = col & (kind == scope)
        m.append(col)
    return np.array(m)


def reconcile(tr: pd.DataFrame) -> None:
    spec = ROOT / "command-center/backend/reports/lab" / LAB_RUN / "chart_spec.json"
    lab = json.loads(spec.read_text())["trades"]
    key = lambda ms, d: (int(ms) // 60_000, d)  # noqa: E731
    lab_keys = {key(t["entryTime"], 1 if t["dir"] == "long" else -1): t for t in lab}
    ours = {key(pd.Timestamp(e).value // 1_000_000, int(d)) for e, d in zip(tr.entry, tr.dir)}
    both = ours & set(lab_keys)
    print(
        f"  reconcile vs lab {LAB_RUN}: study {len(ours)}, lab {len(lab_keys)}, "
        f"same entry minute + side {len(both)}; study-only {len(ours - set(lab_keys))}, "
        f"lab-only {len(set(lab_keys) - ours)}"
    )


def check_clock(bars: pd.DataFrame) -> None:
    """Bars must be UTC: gold's daily break is 17:00-18:00 New York, i.e. 21:00 or 22:00 UTC."""
    hrs = pd.Series(bars.index.hour).value_counts()
    quiet = sorted(hrs.index, key=lambda h: hrs[h])[:1]
    print(
        f"  clock check: quietest UTC hour {quiet[0]:02d}:00 ({hrs[quiet[0]]} bars vs median {int(hrs.median())})"
    )
    if quiet[0] not in (21, 22):
        raise SystemExit("bars are not UTC-stamped - the day/week boundaries would be wrong")


def table(M, r, first, n_total, title):
    sc = B.score(M, r, first)
    print(
        f"\n{title}\n  {'filter':<30}{'removed':>8}{'net R':>9}{'1st half':>10}{'2nd half':>10}{'mean':>8}{'t':>7}  pass1"
    )
    for i, (how, row, scope) in enumerate(FILTERS):
        print(
            f"  skip {row:>3} {how:<8} {scope:<10}{sc['n'][i]:>8}{sc['tot'][i]:>+9.1f}"
            f"{sc['h1'][i]:>+10.1f}{sc['h2'][i]:>+10.1f}{sc['mean'][i]:>+8.2f}{sc['t'][i]:>+7.2f}  "
            + ("yes" if sc["ok"][i] else "")
        )
    return sc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spend-test-set", action="store_true")
    args = ap.parse_args()

    print("replaying the live bot ...")
    tr = B.replay(KEY, START, END)
    reconcile(tr)

    bars = BarSource(server=B.SERVER).load(B.SYMBOL, "15", "2018-09-13", END)
    check_clock(bars)
    close_ms, tape = direction_tape(bars)
    ft = features(tr, close_ms, tape)
    kind = tr.kind.astype(str).to_numpy()
    r = tr.r.to_numpy(float)
    ent = pd.DatetimeIndex(tr.entry)

    for k in ("primary", "secondary"):
        sel = kind == k
        print(f"  {k}: {sel.sum()} trades, {r[sel].sum():+.1f}R, mean {r[sel].mean():+.2f}R")
    for row in ROWS:
        w, a = ft[f"{row}_WITH"].to_numpy(), ft[f"{row}_AGAINST"].to_numpy()
        print(
            f"  {row:>3}: with {w.sum():>3} ({r[w].sum():+6.1f}R)  against {a.sum():>3} ({r[a].sum():+6.1f}R)  neither {(~w & ~a).sum()}"
        )

    ex = (ent >= EXPLORE[0]) & (ent < EXPLORE[1])
    M_all = masks(ft, kind)
    M, rx, first = M_all[:, ex], r[ex], (ent[ex] < SPLIT)
    sc = table(
        M,
        rx,
        first,
        ex.sum(),
        f"EXPLORE {EXPLORE[0].date()} -> {EXPLORE[1].date()}: {ex.sum()} trades, {rx.sum():+.1f}R",
    )

    # Gate 2: the family's most negative t when the feature rows carry no information.
    rng = np.random.default_rng(B.SEED)
    fx, kx = ft[ex].reset_index(drop=True), kind[ex]
    worst = np.empty(B.SHUFFLES)
    for s in range(B.SHUFFLES):
        perm = rng.permutation(len(fx))
        t = B.score(masks(fx.iloc[perm].reset_index(drop=True), kx), rx, first)
        sized = (t["n"] >= B.MIN_REMOVED) & (t["n"] <= len(rx) / 2)
        worst[s] = t["t"][sized].min() if sized.any() else 0.0
    bar = float(np.quantile(worst, B.Q))
    survivors = [i for i in range(len(FILTERS)) if sc["ok"][i] and sc["t"][i] < bar]
    print(
        f"\n  gate 2 luck bar: t < {bar:+.2f} (5th pct of the family's most negative t, {B.SHUFFLES} shuffles)"
    )
    print(f"  survivors of gates 1+2: {[' '.join(FILTERS[i]) for i in survivors] or 'none'}")

    if not args.spend_test_set:
        print("\n  test set NOT spent. Re-run with --spend-test-set ONCE if there are survivors.")
        return
    te = ~ex & (ent >= pd.Timestamp(START))
    print(f"\nTEST SET (spent once): {te.sum()} trades, {r[te].sum():+.1f}R")
    for i in survivors:
        rm = M_all[i] & te
        print(
            f"  {' '.join(FILTERS[i])}: removes {rm.sum()} trades, {r[rm].sum():+.1f}R -> "
            + ("PASS" if r[rm].sum() < 0 else "FAIL")
        )


if __name__ == "__main__":
    main()
