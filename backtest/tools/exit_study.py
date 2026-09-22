"""exit_study.py — once a trade is up, what tells us to get out before the trail does?

A STUDY, not a strategy: it has no Pine twin and no parity gate, so every number it prints
is a lab finding and nothing here trades. Nothing in it is wired to a bot.

THE QUESTION. SOS Fade keeps 44% of the profit its trades ever show (MEASURED 2026-09-21 on
lab run ea46142df097: 533R of best-case, 235R kept). The leak is NOT the runner trail — trades
that reach 5R keep 97% of their peak. It is the band below the trail's arming point: trades
that reach 1-3R showed 123R and kept 11R. This tool walks every trade through its own hold,
bar by bar, and asks what would have got us out nearer the peak.

⚠ THIS IS THE CHEAP MODE AND IT CANNOT DECIDE ANYTHING ON ITS OWN. It re-walks the trades a
single baseline replay produced, so an exit that frees the position slot EARLIER never gets
credit for the trade that would have queued behind it, and an exit that is worse never pays
for the trade it blocked. This repo has MEASURED that effect (`notes/tools.md`: with one slot,
changing when a trade exits changes WHICH settings win, not just their score). So this ranks
candidates and kills the hopeless ones. Anything that survives here has to be built as a real
setting and replayed with the slot on before a single number of it is believed.

THE RULES TESTED, declared before any result:
  hold            what the strategy actually did — the control.
  give<P>@<T>R    once the trade's peak reaches T in R, leave if it hands back more than P
                  percent of that peak. Pure price, no engine.
  liq             leave when price reaches the nearest liquidity level ahead of the trade
                  (previous day/week high-low, session extremes, H4 sweeps) — engines/liquidity.
  poc             leave when price reaches the Asia volume line — engines/session_volume_profile.
  choch           leave when structure breaks against the trade (a CHoCH our way is a reversal)
                  — engines/market_structure. ⚠ Prior art says this LOSES (notes/tools.md).
  div             leave on a divergence against the trade — engines/rsi_divergence.
  candle          leave on a reversal candle against the trade — engines/candlesticks.

EVERY RULE EXITS AT THE NEXT BAR'S OPEN, never at the close of the bar that fired it. That is
the one-bar order delay every fill model in this repo is built on, and pricing a fill at the
moment its rule fired is how a backtest measures a decision instead of a trade.

COSTS are the trade's own `costs_usd` from the baseline replay, carried unchanged. An exit that
skips a rung of the ladder would in truth pay slightly less; this overstates the cost of leaving
early by a fraction of a tick, which is the safe direction.

WINDOWS. Explore on 2020-01-01 -> 2025-08-31. The reserved test set is 2018-09-14 -> 2019-12-31
and it is spent ONCE, behind --spend-test-set. 2025-09-01 onward is already spent.

Usage:
    command-center/backend/.venv/bin/python backtest/tools/exit_study.py
    command-center/backend/.venv/bin/python backtest/tools/exit_study.py --start 2020-01-01 --end 2025-08-31
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "engines")):
    if p not in sys.path:
        sys.path.insert(0, p)

# The windows are the gate, not a default anyone may quietly widen.
EXPLORE_START = "2020-01-01"
EXPLORE_END = "2025-08-31"
TEST_START = "2018-09-14"
TEST_END = "2019-12-31"

SYMBOL = "XAUUSD.p"
SERVER = "PUPrime-Demo"  # pinned: cache-only, no MT5 tunnel needed
PROFILE = "puprime_ecn"  # the only PU Prime tier with a MEASURED XAUUSD spread
TF = 15


@dataclasses.dataclass
class Walk:
    """One trade's re-walk: what each rule would have banked, in R."""

    actual_r: float
    peak_r: float
    by_rule: Dict[str, float]


def _load_bars(start: str, end: str):
    from backtest.data.source import BarSource

    return BarSource(server=SERVER).load(SYMBOL, TF, start, end)


def _replay(df, start: str, end: str, capital: float, warmup: int):
    """The baseline book. Secondary is pinned OFF: one bar stream cannot fill its faster leg,
    and a single-stream replay with it on silently returns a primary-only book that reads as
    the whole thing."""
    from backtest.fills import PROFILES
    from backtest.replay.build import build_strategy

    mod = importlib.import_module("strategies.python.sos_fade")
    spec = mod.LAB_STRATEGY
    cfg = spec["config"](fill_model="bar", symbol=SYMBOL, exec_secondary=False)
    strat = build_strategy(
        spec["strategy"],
        cfg,
        initial_capital=capital,
        cost_profile=PROFILES[PROFILE],
        timeframe_minutes=TF,
    )
    strat.run(df, warmup=warmup)
    return strat.execution.trades


def _engine_track(df):
    """One pass of the engines over the same bars. Returns per-bar-index snapshots.

    Canonical engines only — this package replays `engines/`, it never reimplements one.
    """
    from candlesticks import CandlestickEngine
    from liquidity import LiquidityEngine
    from market_structure import StructureEngine
    from market_structure.types import Bar
    from rsi_divergence import RsiDivergenceEngine
    from session_volume_profile import SvpEngine

    ms = StructureEngine()
    liq = LiquidityEngine()
    svp = SvpEngine()
    rsi = RsiDivergenceEngine()
    cse = CandlestickEngine()

    has_volume = "volume" in df.columns
    track: List[dict] = []
    ts = df.index.view("int64") // 1_000_000
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    c = df["close"].to_numpy()
    v = df["volume"].to_numpy() if has_volume else None

    for i in range(len(df)):
        ms_ev = ms.update(Bar(i, float(o[i]), float(h[i]), float(lo[i]), float(c[i])))
        liq_ev = liq.update(i, int(ts[i]), float(h[i]), float(lo[i]), float(c[i]))
        # ⚠ The volume engines need the bar's volume. A feed that carries none must not be
        # handed a zero — that is a measurement the feed never made (rule 1).
        poc = None
        if v is not None:
            sv = svp.update(
                i, int(ts[i]), float(o[i]), float(h[i]), float(lo[i]), float(c[i]), float(v[i])
            )
            poc = getattr(sv, "poc", None)
            poc = getattr(poc, "price", poc) if poc is not None else None
        rsi_ev = rsi.update(i, float(h[i]), float(lo[i]), float(c[i]))
        cs_ev = cse.update(i, float(o[i]), float(h[i]), float(lo[i]), float(c[i]))

        ext = ms_ev.external
        track.append(
            {
                "bull_sos": bool(getattr(ext, "bull_sos", False)),
                "bear_sos": bool(getattr(ext, "bear_sos", False)),
                "levels": tuple(
                    float(getattr(x, "price", float("nan"))) for x in (liq_ev.active or ())
                ),
                "poc": poc,
                "div": tuple(bool(d.is_bullish) for d in (rsi_ev.detected or ())),
                "bull_candle": bool(getattr(cs_ev, "bullish", ())),
                "bear_candle": bool(getattr(cs_ev, "bearish", ())),
            }
        )
    return track


def _bar_of(df, ms_value: Optional[int], fallback: int) -> int:
    """Locate a trade's bar by TIMESTAMP, never by its stored index.

    A secondary trade counts its index on the FAST feed while `df` is the M15 frame — two
    units, one reader, and 60 of 242 trades were stamped with the last bar on a 2020-2026
    replay before this was caught (`backtest/notes/tools.md`).
    """
    if ms_value is None:
        return fallback
    import numpy as np

    stamps = df.index.view("int64") // 1_000_000
    pos = int(np.searchsorted(stamps, int(ms_value), side="right")) - 1
    return max(0, min(pos, len(df) - 1))


def _rules(peak_bands: Tuple[float, ...], giveback: Tuple[float, ...]) -> List[str]:
    names = ["hold"]
    for t in peak_bands:
        for p in giveback:
            names.append(f"give{int(p * 100)}@{t:g}R")
    names += ["liq", "poc", "choch", "div", "candle"]
    return names


def walk_trade(df, track, tr, peak_bands, giveback) -> Walk:
    """Walk one trade bar by bar and price every rule's exit at the NEXT bar's open."""
    d = 1 if tr.dir > 0 else -1
    entry = float(tr.entry_price)
    dist = float(tr.stop_distance) or 1.0
    cost_r = (float(tr.costs_usd or 0.0) / float(tr.risk_usd)) if tr.risk_usd else 0.0
    i0 = _bar_of(df, getattr(tr, "entry_ms", None), int(tr.entry_index))
    i1 = _bar_of(df, getattr(tr, "exit_ms", None), int(tr.exit_index))
    if i1 <= i0:
        return Walk(float(tr.r), float(tr.r), {})

    h = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    c = df["close"].to_numpy()
    o = df["open"].to_numpy()

    def r_at(price: float) -> float:
        return (price - entry) * d / dist - cost_r

    fired: Dict[str, float] = {}
    peak_r = 0.0
    for i in range(i0, i1 + 1):
        best = h[i] if d > 0 else lo[i]
        peak_r = max(peak_r, (float(best) - entry) * d / dist)
        t = track[i]
        # The exit price is the NEXT bar's open — the one-bar order delay. A rule that fires
        # on the last bar of the hold has nowhere to go and keeps what the trade made.
        nxt = float(o[i + 1]) if i + 1 <= i1 else float(tr.exit_price)
        here = float(c[i])

        for band in peak_bands:
            for pct in giveback:
                key = f"give{int(pct * 100)}@{band:g}R"
                if key in fired or peak_r < band:
                    continue
                kept = (here - entry) * d / dist
                if kept <= peak_r * (1.0 - pct):
                    fired[key] = r_at(nxt)

        if "liq" not in fired:
            ahead = [
                lv
                for lv in t["levels"]
                if lv == lv and (lv - entry) * d > 0 and (lv - here) * d <= 0
            ]
            if ahead:
                fired["liq"] = r_at(nxt)
        if "poc" not in fired and t["poc"] is not None:
            p = float(t["poc"])
            if (p - entry) * d > 0 and (p - here) * d <= 0:
                fired["poc"] = r_at(nxt)
        if "choch" not in fired and (t["bull_sos"] if d < 0 else t["bear_sos"]):
            fired["choch"] = r_at(nxt)
        if "div" not in fired and any(b == (d < 0) for b in t["div"]):
            fired["div"] = r_at(nxt)
        if "candle" not in fired and (t["bull_candle"] if d < 0 else t["bear_candle"]):
            fired["candle"] = r_at(nxt)

    return Walk(float(tr.r), peak_r, fired)


def _book(walks: List[Walk], rule: str) -> Tuple[float, float, float]:
    """Total R, worst drawdown of the closed-trade curve, and return per drawdown."""
    cum = peak = dd = total = 0.0
    for w in walks:
        r = w.actual_r if rule == "hold" else w.by_rule.get(rule, w.actual_r)
        total += r
        cum += r
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return total, dd, (total / dd if dd else float("inf"))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", default=EXPLORE_START)
    ap.add_argument("--end", default=EXPLORE_END)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--spend-test-set", action="store_true")
    args = ap.parse_args(argv)

    if args.start < EXPLORE_START and not args.spend_test_set:
        print(
            f"REFUSED: {args.start} reaches into the reserved test set "
            f"({TEST_START} -> {TEST_END}). It is spent ONCE, and only on a rule that has "
            f"already earned it on the explore window. Pass --spend-test-set if that is what "
            f"this run is."
        )
        return 2

    print(f"loading {SYMBOL} {TF}m {args.start} -> {args.end} from {SERVER} ...", flush=True)
    df = _load_bars(args.start, args.end)
    if df.empty:
        print("no bars — the cache holds none for this window.")
        return 1
    print(f"  {len(df):,} bars  {df.index[0]} -> {df.index[-1]}", flush=True)

    trades = _replay(df, args.start, args.end, args.capital, args.warmup)
    print(f"  {len(trades)} trades replayed (secondary pinned off)", flush=True)
    print("running the engines over the same bars ...", flush=True)
    track = _engine_track(df)

    peak_bands = (1.0, 1.5, 2.0, 3.0)
    giveback = (0.25, 0.33, 0.5)
    walks = [walk_trade(df, track, t, peak_bands, giveback) for t in trades]

    reached = sum(1 for w in walks if w.peak_r >= 1)
    best_case = sum(w.peak_r for w in walks)
    print(
        f"\n{len(walks)} trades, {reached} reached 1R, best case {best_case:.0f}R, "
        f"kept {sum(w.actual_r for w in walks):.0f}R"
    )
    print("\nrule            total R   worst DD   ret/DD   fired on")
    rows = []
    for rule in _rules(peak_bands, giveback):
        total, dd, ratio = _book(walks, rule)
        n = sum(1 for w in walks if rule in w.by_rule)
        rows.append((ratio, rule, total, dd, n))
    hold = [r for r in rows if r[1] == "hold"][0]
    for ratio, rule, total, dd, n in [hold] + sorted(
        [r for r in rows if r[1] != "hold"], key=lambda r: -r[0]
    ):
        print(f"{rule:<14} {total:8.1f}   {dd:8.2f}   {ratio:6.1f}   {n:4d}")
    print(
        "\n⚠ CHEAP MODE: one book, re-walked. An exit that frees the slot earlier gets no "
        "credit for the trade that would have queued behind it. Rank with this; decide with a "
        "replay."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
