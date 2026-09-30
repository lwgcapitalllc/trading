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
  sos+bos         AARON'S DEFINITION (2026-09-22): a shift of structure against the trade and
                  THEN a break of structure the same way. The shift alone is only half of it.
  engulf          a BIG engulfing against the trade — the pattern at the chart's own settings
                  (`candlesticks.CHART_PRESET`), with a body >= 2x the last 20 bars' median.
                  ⚠ Size is the signal; the bare pattern fires on almost every bar.
  level2/level3   price reaches a major level (previous day/week high-low, session extremes)
                  and closes back off it, twice or three times — "hitting it over and over".
  level+turn      the confluence: a level rejected AND structure shifting or a big engulfing
                  on the same bar.

🔴 THE REVERSAL RULES READ A CHART OF THEIR OWN, SET BY --signal-tf. The trade is found on the
15m chart, but a 15m reversal is confirmed long after the turn: by the time the bar closes the
give-back has already happened. So `choch`, `div` and `candle` run on their own faster frame
(1m or 5m) and are checked on every one of ITS bars inside the hold, with the exit still priced
at the next bar's open of that same frame. `liq` and `poc` stay on the trade's frame — both are
session levels, and the level is the same price whatever chart draws it.
⚠ A FAST FRAME IS NOT FREE: it fires earlier AND more often, and both effects land in the same
number. That is the point of running all three frames side by side rather than one.

EVERY RULE EXITS AT THE NEXT BAR'S OPEN, never at the close of the bar that fired it. That is
the one-bar order delay every fill model in this repo is built on, and pricing a fill at the
moment its rule fired is how a backtest measures a decision instead of a trade.

COSTS are the trade's own `costs_usd` from the baseline replay, carried unchanged. An exit that
skips a rung of the ladder would in truth pay slightly less; this overstates the cost of leaving
early by a fraction of a tick, which is the safe direction.

WINDOWS. Explore on 2020-01-01 -> 2025-08-31. The reserved test set is 2018-09-14 -> 2019-12-31
and it is spent ONCE, behind --spend-test-set. 2025-09-01 onward is already spent.

--separation (2026-09-25) asks the question underneath the losing exit rules: when a signal fires
on a trade already up at least 1R (or 2R), is it a REAL reversal or a FALSE alarm inside a move that
carried on? It grades the first armed fire per trade per signal, on every chart the signal reads,
and adds five signals: a failed gap in the trade's direction (`ifvg`), no new best for 8/16/32
15m bars (`stall<N>`), a 2.5-ATR bar closing against the trade (`disp`), the 15m shift
(`choch@15m`) and the 1m INTERNAL shift (`ichoch@1m`). Thresholds are the SEP_* constants, declared
before any result. It runs the 1m engines over the whole window: expect ~20 minutes.

Usage:
    command-center/backend/.venv/bin/python backtest/tools/exit_study.py
    command-center/backend/.venv/bin/python backtest/tools/exit_study.py --start 2020-01-01 --end 2025-08-31
    command-center/backend/.venv/bin/python backtest/tools/exit_study.py --separation --csv-dir <dir>
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

# A body this many times the last 20 bars' median counts as "big" (his word for the engulfing
# that matters). Declared here, before any result, rather than tuned until something wins.
_BIG_BODY_X = 2.0
# How near price must come to a level to count as touching it, as a share of that bar's range.
_TOUCH_BAND = 0.25

# THE COMBINATIONS, declared before any result. Each is (signals, mode); "first" leaves on
# whichever fires first, "half" banks half on the first and the rest on the second.
GIVE = "give50@1.5R"
COMBOS: Dict[str, Tuple[Tuple[str, ...], str]] = {
    "give|choch": ((GIVE, "choch"), "first"),
    "give|level2": ((GIVE, "level2"), "first"),
    "give|choch|level2": ((GIVE, "choch", "level2"), "first"),
    "give|engulf": ((GIVE, "engulf"), "first"),
    "half:choch->give": (("choch", GIVE), "half"),
    "half:level2->give": (("level2", GIVE), "half"),
    "half:any2": ((GIVE, "choch", "level2", "engulf"), "half"),
}


@dataclasses.dataclass
class Walk:
    """One trade's re-walk: what each rule would have banked, in R."""

    actual_r: float
    peak_r: float
    by_rule: Dict[str, float]
    # rule -> (timestamp in ms the rule fired, R it would have banked). Two frames feed this,
    # so the TIME is the only axis both share — a bar index means different things on each.
    fired_at: Dict[str, Tuple[int, float]] = dataclasses.field(default_factory=dict)
    peak_ms: int = 0  # when the trade topped out — the clock question


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


def _engine_track(df, tf: int = TF):
    """One pass of the engines over these bars. Returns per-bar-index snapshots.

    `tf` is the bar size in minutes, and it only picks the gap engine's settings row: the
    indicator splits its gap threshold and close test at 15m, and the engine takes one row per run.

    Canonical engines only — this package replays `engines/`, it never reimplements one.
    """
    import fair_value_gaps.engine as fvg_defaults
    from candlesticks import CHART_PRESET, CandlestickEngine
    from fair_value_gaps import FairValueGapEngine
    from liquidity import LiquidityEngine
    from market_structure import StructureEngine
    from market_structure.types import Bar
    from rsi_divergence import RsiDivergenceEngine
    from session_volume_profile import SvpEngine

    ms = StructureEngine()
    liq = LiquidityEngine()
    svp = SvpEngine()
    rsi = RsiDivergenceEngine()
    # The chart settings actually read on the charts, not the engine's Pine-mirroring
    # defaults — a "reversal candle" measured at trend=5 fires on almost every bar.
    cse = CandlestickEngine(**CHART_PRESET)
    # The gap settings row the CHART draws at this bar size — never a row typed here.
    if tf * 60 >= fvg_defaults.SPLIT_SECONDS:
        fvg = FairValueGapEngine(
            threshold_pct=fvg_defaults.FROM_15M_THRESHOLD_PCT,
            require_close=fvg_defaults.FROM_15M_REQUIRE_CLOSE,
        )
    else:
        fvg = FairValueGapEngine()

    has_volume = "volume" in df.columns
    track: List[dict] = []
    ts = df.index.view("int64") // 1_000_000
    o = df["open"].to_numpy()
    stamps = df.index.view("int64") // 1_000_000
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
        fvg_ev = fvg.update(i, float(o[i]), float(h[i]), float(lo[i]), float(c[i]))

        ext = ms_ev.external
        itn = ms_ev.internal
        # "A BIG engulfing" — the pattern alone is not the signal he reads, the SIZE is.
        # Big = a body at least `_BIG_BODY_X` times the median body of the last 20 bars.
        body = abs(float(c[i]) - float(o[i]))
        j0 = max(0, i - 20)
        bodies = sorted(abs(float(c[k]) - float(o[k])) for k in range(j0, i + 1))
        med = bodies[len(bodies) // 2] if bodies else 0.0
        big = med > 0 and body >= med * _BIG_BODY_X
        track.append(
            {
                "bull_sos": bool(getattr(ext, "bull_sos", False)),
                "bear_sos": bool(getattr(ext, "bear_sos", False)),
                "bull_bos": bool(getattr(ext, "bull_bos", False)),
                "bear_bos": bool(getattr(ext, "bear_bos", False)),
                # INTERNAL shift bools only — the internal *_price fields are known wrong
                # (strategies/python/sos_fade/CLAUDE.md, the fast-frame internal shift feed).
                "bull_isos": bool(getattr(itn, "bull_sos", False)),
                "bear_isos": bool(getattr(itn, "bear_sos", False)),
                # Gaps formed THIS bar, as the engine emits them: (bottom, top, is_bullish).
                "fvg_formed": tuple(
                    (float(g.bottom), float(g.top), bool(g.is_bullish)) for g in fvg_ev.formed
                ),
                "levels": tuple(
                    float(getattr(x, "price", float("nan"))) for x in (liq_ev.active or ())
                ),
                "poc": poc,
                "div": tuple(bool(d.is_bullish) for d in (rsi_ev.detected or ())),
                "bull_engulf": big and cs_ev.has("bullish_engulfing"),
                "bear_engulf": big and cs_ev.has("bearish_engulfing"),
                "high": float(h[i]),
                "low": float(lo[i]),
                "close": float(c[i]),
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
    names += ["liq", "poc", "choch", "sos+bos", "engulf", "div", "level2", "level3", "level+turn"]
    names += list(COMBOS)
    return names


def walk_reversals(fdf, ftrack, tr, dist, cost_r) -> Dict[str, float]:
    """The three signal rules on their OWN frame, priced at that frame's next bar open."""
    import numpy as np

    d = 1 if tr.dir > 0 else -1
    entry = float(tr.entry_price)
    stamps = fdf.index.view("int64") // 1_000_000
    when = lambda i: int(stamps[i])  # noqa: E731 — the bar the rule fired on
    i0 = int(np.searchsorted(stamps, int(tr.entry_ms), side="left"))
    i1 = int(np.searchsorted(stamps, int(tr.exit_ms), side="right")) - 1
    o = fdf["open"].to_numpy()
    fired: Dict[str, float] = {}
    if i1 <= i0:
        return fired
    # His definition, in his words: a SHIFT of structure against us, then a BREAK of structure
    # the same way, confirms the reversal. The shift alone is only half of it.
    # ⚠ The engine flags a SHIFT as a break too (a shift IS a break that also flips the trend),
    # so "then a break" has to mean a LATER bar or the rule silently collapses into `choch`.
    # Measured 2026-09-22: without this the two columns were identical, 9 fires each.
    shift_bar: Optional[int] = None
    # A level he names — previous day/week high-low, session extremes — is "hit over and over"
    # when price reaches it repeatedly and cannot go through. Counted per level price.
    touches: Dict[float, int] = {}
    for i in range(i0, min(i1, len(ftrack) - 1) + 1):
        t = ftrack[i]
        nxt = float(o[i + 1]) if i + 1 <= i1 else float(tr.exit_price)
        r = (nxt - entry) * d / dist - cost_r
        against_sos = t["bull_sos"] if d < 0 else t["bear_sos"]
        against_bos = t["bull_bos"] if d < 0 else t["bear_bos"]
        against_engulf = t["bull_engulf"] if d < 0 else t["bear_engulf"]
        if against_sos and shift_bar is None:
            shift_bar = i
        if "choch" not in fired and against_sos:
            fired["choch"] = (when(i), r)
        if "sos+bos" not in fired and shift_bar is not None and i > shift_bar and against_bos:
            fired["sos+bos"] = (when(i), r)
        if "engulf" not in fired and against_engulf:
            fired["engulf"] = (when(i), r)
        if "div" not in fired and any(b == (d < 0) for b in t["div"]):
            fired["div"] = (when(i), r)

        # Touch counting: price reaches into a band around the level and closes back off it.
        band = (t["high"] - t["low"]) * _TOUCH_BAND
        rejected = False
        for lv in t["levels"]:
            if lv != lv or band <= 0:
                continue
            reached = t["low"] - band <= lv <= t["high"] + band
            if not reached:
                continue
            closed_off = abs(t["close"] - lv) > band
            if closed_off:
                touches[lv] = touches.get(lv, 0) + 1
                rejected = True
                if "level2" not in fired and touches[lv] >= 2:
                    fired["level2"] = (when(i), r)
                if "level3" not in fired and touches[lv] >= 3:
                    fired["level3"] = (when(i), r)
        # The confluence he described: a level being hit again AND the structure turning there.
        if "level+turn" not in fired and rejected and (against_sos or against_engulf):
            fired["level+turn"] = (when(i), r)
    return fired


def walk_trade(df, track, tr, peak_bands, giveback) -> Walk:
    """Walk one trade bar by bar and price every rule's exit at the NEXT bar's open."""
    d = 1 if tr.dir > 0 else -1
    entry = float(tr.entry_price)
    dist = float(tr.stop_distance) or 1.0
    cost_r = (float(tr.costs_usd or 0.0) / float(tr.risk_usd)) if tr.risk_usd else 0.0
    i0 = _bar_of(df, getattr(tr, "entry_ms", None), int(tr.entry_index))
    i1 = _bar_of(df, getattr(tr, "exit_ms", None), int(tr.exit_index))
    if i1 <= i0:
        return Walk(float(tr.r), float(tr.r), {}, {})

    stamps = df.index.view("int64") // 1_000_000
    h = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    c = df["close"].to_numpy()
    o = df["open"].to_numpy()

    def r_at(price: float) -> float:
        return (price - entry) * d / dist - cost_r

    fired: Dict[str, float] = {}
    peak_r = 0.0
    peak_ms = 0
    for i in range(i0, i1 + 1):
        best = h[i] if d > 0 else lo[i]
        here_peak = (float(best) - entry) * d / dist
        if here_peak > peak_r:
            peak_r, peak_ms = here_peak, int(stamps[i])
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
                    fired[key] = (int(stamps[i]), r_at(nxt))

        if "liq" not in fired:
            ahead = [
                lv
                for lv in t["levels"]
                if lv == lv and (lv - entry) * d > 0 and (lv - here) * d <= 0
            ]
            if ahead:
                fired["liq"] = (int(stamps[i]), r_at(nxt))
        if "poc" not in fired and t["poc"] is not None:
            p = float(t["poc"])
            if (p - entry) * d > 0 and (p - here) * d <= 0:
                fired["poc"] = (int(stamps[i]), r_at(nxt))
    w = Walk(float(tr.r), peak_r, {k: v[1] for k, v in fired.items()}, fired)
    w.peak_ms = peak_ms
    return w


def combine(w: Walk, signals: Tuple[str, ...], mode: str) -> Optional[float]:
    """What a COMBINATION of signals would have banked on this trade.

    The market does not repeat one behaviour, so a single trigger is one answer to every
    question. Two modes, both asked for 2026-09-22:
      "first"  — leave the whole trade on whichever of these signals fires first.
      "half"   — bank HALF on the first signal and the rest on the second DIFFERENT one;
                 if no second signal arrives, the other half rides to the real exit.
    Returns None when nothing fired, which means the trade is unchanged.
    """
    hits = sorted((w.fired_at[s] for s in signals if s in w.fired_at), key=lambda x: x[0])
    if not hits:
        return None
    if mode == "first":
        return hits[0][1]
    first = hits[0]
    later = [h for h in hits if h[0] > first[0]]
    second = later[0][1] if later else w.actual_r
    return 0.5 * first[1] + 0.5 * second


def _book(walks: List[Walk], rule: str) -> Tuple[float, float, float]:
    """Total R, worst drawdown of the closed-trade curve, and return per drawdown."""
    cum = peak = dd = total = 0.0
    for w in walks:
        if rule == "hold":
            r = w.actual_r
        elif rule in COMBOS:
            sigs, mode = COMBOS[rule]
            got = combine(w, sigs, mode)
            r = w.actual_r if got is None else got
        else:
            r = w.by_rule.get(rule, w.actual_r)
        total += r
        cum += r
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return total, dd, (total / dd if dd else float("inf"))


def _hours(walks: List[Walk]) -> None:
    """WHEN does a trade top out, and when does the give-back start?

    Hours are NEW YORK, the clock this market is quoted against — never the machine's local
    time, which would move the answer with whoever ran the tool.
    """
    import pandas as pd

    rows = [w for w in walks if w.peak_r >= 1.5 and w.peak_ms]
    if not rows:
        return
    peak_h: Dict[int, List[float]] = {}
    fire_h: Dict[int, int] = {}
    for w in rows:
        # HALF-hour slots, not hours: Aaron names 8:15, 9:30 and 10:00 as separate moments,
        # and an hourly bucket cannot tell those apart.
        t = pd.Timestamp(w.peak_ms, unit="ms", tz="UTC").tz_convert("America/New_York")
        peak_h.setdefault(t.hour * 2 + (t.minute >= 30), []).append(w.peak_r - w.actual_r)
        hit = w.fired_at.get("give50@1.5R")
        if hit:
            ft = pd.Timestamp(hit[0], unit="ms", tz="UTC").tz_convert("America/New_York")
            fk = ft.hour * 2 + (ft.minute >= 30)
            fire_h[fk] = fire_h.get(fk, 0) + 1
    print(f"\nWHEN {len(rows)} trades that reached 1.5R topped out (New York time)")
    print("slot    topped out   gave back (R)   give-back rule fired")
    for k in sorted(peak_h):
        gb = peak_h[k]
        h, m = divmod(k, 2)
        print(f"{h:02d}:{m * 30:02d} {len(gb):11d} {sum(gb):14.1f} {fire_h.get(k, 0):20d}")


# ════════════════════════════════════════════════════════════════════════════════════════════
# SEPARATION MODE (--separation, 2026-09-25)
#
# Every reversal signal above LOST as an exit rule. This mode asks the question underneath: when
# a signal fires on a trade that is ALREADY in profit, is it a real reversal or a false alarm
# inside a move that carried on? A signal only earns a full replay if it separates the two.
#
# The signal on bar t reads nothing past bar t's close. The LABEL reads the rest of the hold —
# that is the only place lookahead is allowed, because the label is the answer being graded.
#
# THRESHOLDS, declared before any result was seen. None of them may be tuned afterwards.
# ════════════════════════════════════════════════════════════════════════════════════════════
SEP_ARMS: Tuple[float, ...] = (1.0, 2.0)  # a fire counts only once the trade's best is this far up
SEP_CONTINUE_R = 0.5  # the move "continued" if the trade later beats its best-at-fire by this
SEP_RUNNER_R = 5.0  # a trade that closed at least this far up is a runner a signal would cut
SEP_STALL_BARS: Tuple[int, ...] = (8, 16, 32)  # 15m bars with no new best
SEP_DISP_ATR_X = 2.5  # displacement: a bar's range at least this many ATRs
SEP_DISP_CLOSE_SHARE = 0.25  # ...closing in this share of its range on the side against the trade
SEP_ATR_LEN = 14  # Wilder ATR — a THRESHOLD computed here, not an engine

# Which signal reads which chart. Fast-frame signals run on 5m AND 1m; the gap and displacement
# signals on 5m and 15m; the level signals, the stall and the 15m shift on the trade's own 15m.
SEP_FRAMES: Dict[int, Tuple[str, ...]] = {
    1: ("choch", "sos+bos", "engulf", "div", "level2", "ichoch"),
    5: ("choch", "sos+bos", "engulf", "div", "level2", "ifvg", "disp"),
    15: ("choch", "liq", "poc", "ifvg", "disp") + tuple(f"stall{n}" for n in SEP_STALL_BARS),
}


def _wilder_atr(h, lo, c, n: int = SEP_ATR_LEN):
    """Wilder's ATR; element i uses bars up to and including i. NaN until n bars exist."""
    import numpy as np

    tr = np.empty(len(h))
    tr[0] = h[0] - lo[0]
    if len(h) > 1:
        pc = c[:-1]
        tr[1:] = np.maximum(h[1:] - lo[1:], np.maximum(abs(h[1:] - pc), abs(lo[1:] - pc)))
    atr = np.full(len(h), np.nan)
    if len(h) < n:
        return atr
    atr[n - 1] = tr[:n].mean()
    for i in range(n, len(h)):
        atr[i] = (atr[i - 1] * (n - 1) + tr[i]) / n
    return atr


@dataclasses.dataclass
class SepFrame:
    """One chart's bars, arrays and engine track, built once and shared by every trade."""

    tf: int
    track: List[dict]
    stamps: object
    o: object
    h: object
    lo: object
    c: object
    atr: object

    @classmethod
    def build(cls, df, tf: int, track: Optional[List[dict]] = None) -> "SepFrame":
        h = df["high"].to_numpy()
        lo = df["low"].to_numpy()
        c = df["close"].to_numpy()
        return cls(
            tf=tf,
            track=track if track is not None else _engine_track(df, tf),
            stamps=df.index.view("int64") // 1_000_000,
            o=df["open"].to_numpy(),
            h=h,
            lo=lo,
            c=c,
            atr=_wilder_atr(h, lo, c),
        )


@dataclasses.dataclass
class SepFire:
    """The FIRST armed fire of one signal on one trade, and how the rest of the hold graded it."""

    signal: str
    tf: int
    arm: float
    trade: int
    fired_ms: int
    peak_at_fire: float  # best R so far, fire bar included (known at its close)
    exit_r: float  # banked at the NEXT bar's open of this frame, costs as exit_study charges
    actual_r: float  # what the trade really closed at
    later_best: float  # best R the trade printed AFTER the fire bar (the label's lookahead)

    @property
    def continued(self) -> bool:
        return self.later_best > self.peak_at_fire + SEP_CONTINUE_R

    @property
    def real(self) -> bool:
        """REAL reversal: never beat peak+0.5R later AND closed below what leaving would bank."""
        return (not self.continued) and self.actual_r < self.exit_r

    @property
    def saved(self) -> float:
        return self.exit_r - self.actual_r


def separation_walk(fr: SepFrame, tr, trade_no: int, signals: Tuple[str, ...]) -> List[SepFire]:
    """Walk one trade on one frame; return the first ARMED fire per (signal, arm level)."""
    import numpy as np

    d = 1 if tr.dir > 0 else -1
    entry = float(tr.entry_price)
    dist = float(tr.stop_distance) or 1.0
    cost_r = (float(tr.costs_usd or 0.0) / float(tr.risk_usd)) if tr.risk_usd else 0.0
    i0 = int(np.searchsorted(fr.stamps, int(tr.entry_ms), side="left"))
    i1 = int(np.searchsorted(fr.stamps, int(tr.exit_ms), side="right")) - 1
    i1 = min(i1, len(fr.track) - 1)
    if i1 <= i0:
        return []
    seg = slice(i0, i1 + 1)
    best = ((fr.h[seg] - entry) if d > 0 else (entry - fr.lo[seg])) / dist
    run_peak = np.maximum.accumulate(best)
    # later[k] = best R on bars AFTER k in the hold; -inf past the last bar.
    later = np.full(len(best), -np.inf)
    if len(best) > 1:
        later[:-1] = np.maximum.accumulate(best[::-1])[::-1][1:]

    out: Dict[Tuple[str, float], SepFire] = {}
    shift_bar: Optional[int] = None
    touches: Dict[float, int] = {}
    my_gaps: List[Tuple[float, float]] = []  # (bottom, top) of trade-direction gaps since entry
    since_best = 0
    # The last bar of the hold is never a fire: its next open is after the trade already closed.
    for i in range(i0, i1):
        k = i - i0
        t = fr.track[i]
        if k > 0 and best[k] > run_peak[k - 1]:
            since_best = 0
        elif k > 0:
            since_best += 1
        here = float(fr.c[i])
        firing: List[str] = []

        against_sos = t["bull_sos"] if d < 0 else t["bear_sos"]
        against_bos = t["bull_bos"] if d < 0 else t["bear_bos"]
        if against_sos and shift_bar is None:
            shift_bar = i
        if against_sos:
            firing.append("choch")
        if shift_bar is not None and i > shift_bar and against_bos:
            firing.append("sos+bos")
        if t["bull_engulf"] if d < 0 else t["bear_engulf"]:
            firing.append("engulf")
        if any(b == (d < 0) for b in t["div"]):
            firing.append("div")
        if t["bull_isos"] if d < 0 else t["bear_isos"]:
            firing.append("ichoch")

        # level2 — the same touch-and-reject count `walk_reversals` keeps.
        band = (t["high"] - t["low"]) * _TOUCH_BAND
        for lv in t["levels"]:
            if lv != lv or band <= 0:
                continue
            if t["low"] - band <= lv <= t["high"] + band and abs(t["close"] - lv) > band:
                touches[lv] = touches.get(lv, 0) + 1
                if touches[lv] >= 2:
                    firing.append("level2")
        # liq / poc — the same "a level ahead of the entry has been reached" test `walk_trade` uses.
        if any(lv == lv and (lv - entry) * d > 0 and (lv - here) * d <= 0 for lv in t["levels"]):
            firing.append("liq")
        if t["poc"] is not None:
            p = float(t["poc"])
            if (p - entry) * d > 0 and (p - here) * d <= 0:
                firing.append("poc")

        # ifvg — a gap in the trade's direction, born inside the hold, then a CLOSE past its far
        # edge (the engine's own mitigation test: bull `close <= bottom`, bear `close >= top`).
        # Checked here rather than read off the engine's `mitigated` list because the engine's cap
        # evicts gaps (7 on any frame) long before many are closed through, and an evicted gap
        # never reports its mitigation. Gaps born THIS bar are added after the check.
        hit = [g for g in my_gaps if (here <= g[0] if d > 0 else here >= g[1])]
        if hit:
            firing.append("ifvg")
            my_gaps = [g for g in my_gaps if g not in hit]
        my_gaps += [(b, tp) for (b, tp, bull) in t["fvg_formed"] if bull == (d > 0)]

        # disp — range >= X ATR (the ATR as of the bar BEFORE, so the bar cannot inflate its own
        # yardstick), closing in the quarter of its range on the side against the trade.
        rng = float(fr.h[i] - fr.lo[i])
        a = fr.atr[i - 1] if i > 0 else float("nan")
        if a == a and a > 0 and rng >= SEP_DISP_ATR_X * a:
            if d > 0 and here <= fr.lo[i] + SEP_DISP_CLOSE_SHARE * rng:
                firing.append("disp")
            if d < 0 and here >= fr.h[i] - SEP_DISP_CLOSE_SHARE * rng:
                firing.append("disp")
        for n in SEP_STALL_BARS:
            if since_best >= n:
                firing.append(f"stall{n}")

        if not firing:
            continue
        exit_r = (float(fr.o[i + 1]) - entry) * d / dist - cost_r
        for s in firing:
            if s not in signals:
                continue
            for arm in SEP_ARMS:
                if (s, arm) in out or run_peak[k] < arm:
                    continue
                out[(s, arm)] = SepFire(
                    signal=s,
                    tf=fr.tf,
                    arm=arm,
                    trade=trade_no,
                    fired_ms=int(fr.stamps[i]),
                    peak_at_fire=float(run_peak[k]),
                    exit_r=exit_r,
                    actual_r=float(tr.r),
                    later_best=float(later[k]),
                )
    return list(out.values())


def separation_rows(fires: List[SepFire]) -> List[dict]:
    """One row per (signal, frame, arm level)."""
    groups: Dict[Tuple[str, int, float], List[SepFire]] = {}
    for f in fires:
        groups.setdefault((f.signal, f.tf, f.arm), []).append(f)
    rows = []
    for (sig, tf, arm), fs in groups.items():
        real = [f for f in fs if f.real]
        false = [f for f in fs if not f.real]
        runners = [f for f in fs if f.actual_r >= SEP_RUNNER_R]
        rows.append(
            {
                "signal": f"{sig}@{tf}m",
                "arm_r": arm,
                "fires": len(fs),
                "real": len(real),
                "false": len(false),
                "precision": len(real) / len(fs),
                "mean_saved_real": sum(f.saved for f in real) / len(real) if real else 0.0,
                "mean_cost_false": sum(-f.saved for f in false) / len(false) if false else 0.0,
                "net_saved": sum(f.saved for f in fs),
                "runner_fires": len(runners),
                "runner_r_given_up": sum(-f.saved for f in runners),
            }
        )
    rows.sort(key=lambda r: -r["net_saved"])
    return rows


def run_separation(df, track, trades, args) -> int:
    """--separation: load each frame once, walk every trade on it, print and save the table."""
    import csv

    from backtest.data.source import BarSource

    # The baseline — what the trades that got into profit showed and kept.
    walks = [walk_trade(df, track, t, (), ()) for t in trades]
    print(f"\nBASELINE: {len(walks)} trades")
    for arm in SEP_ARMS:
        got = [w for w in walks if w.peak_r >= arm]
        print(
            f"  reached >= {arm:g}R: {len(got):4d} trades, showed {sum(w.peak_r for w in got):7.1f}R, "
            f"kept {sum(w.actual_r for w in got):7.1f}R"
        )
    print(
        f"  all trades: showed {sum(w.peak_r for w in walks):.1f}R, kept "
        f"{sum(w.actual_r for w in walks):.1f}R"
    )

    fires: List[SepFire] = []
    for tf in sorted(SEP_FRAMES, reverse=True):
        if tf == TF:
            fr = SepFrame.build(df, tf, track)
        else:
            print(f"loading {SYMBOL} {tf}m ...", flush=True)
            fdf = BarSource(server=SERVER).load(SYMBOL, tf, args.start, args.end)
            if fdf.empty:
                print(f"no {tf}m bars — the cache holds none for this window.")
                return 1
            print(f"  {len(fdf):,} bars; running the engines over them ...", flush=True)
            fr = SepFrame.build(fdf, tf)
        for n, tr in enumerate(trades):
            fires += separation_walk(fr, tr, n, SEP_FRAMES[tf])

    rows = separation_rows(fires)
    print(
        "\nSEPARATION — first ARMED fire per trade, per signal, per arm level.\n"
        f"  exit_r   = R banked leaving at the NEXT bar's open of the frame that fired, costs as charged.\n"
        f"  REAL     = the trade never later beats its best-at-fire + {SEP_CONTINUE_R:g}R AND closed below exit_r.\n"
        f"  FALSE    = it later beat best-at-fire + {SEP_CONTINUE_R:g}R, OR closed at/above exit_r.\n"
        f"  saved    = exit_r - actual_r (positive: leaving helped). Runner = closed >= {SEP_RUNNER_R:g}R.\n"
    )
    hdr = (
        f"{'signal':<14}{'arm':>4}{'fires':>7}{'real':>6}{'false':>6}{'prec':>7}"
        f"{'saved/real':>11}{'cost/false':>11}{'net':>8}{'runners':>8}{'run R lost':>11}"
    )
    print(hdr)
    for r in rows:
        print(
            f"{r['signal']:<14}{r['arm_r']:>4g}{r['fires']:>7}{r['real']:>6}{r['false']:>6}"
            f"{r['precision']:>7.2f}{r['mean_saved_real']:>11.2f}{r['mean_cost_false']:>11.2f}"
            f"{r['net_saved']:>8.1f}{r['runner_fires']:>8}{r['runner_r_given_up']:>11.1f}"
        )
    cands = [r for r in rows if r["precision"] >= 0.6 and r["net_saved"] > 0]
    print(
        "\nCANDIDATES (precision >= 0.60 AND net saved > 0): "
        + (", ".join(f"{r['signal']} arm {r['arm_r']:g}R" for r in cands) if cands else "none")
    )

    if args.csv_dir:
        out = Path(args.csv_dir)
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "separation_table.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["signal"])
            w.writeheader()
            w.writerows(rows)
        with open(out / "separation_fires.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(
                [
                    "signal",
                    "tf",
                    "arm",
                    "trade",
                    "fired_ms",
                    "peak_at_fire",
                    "exit_r",
                    "actual_r",
                    "later_best",
                    "real",
                    "saved",
                ]
            )
            for f in fires:
                w.writerow(
                    [
                        f.signal,
                        f.tf,
                        f.arm,
                        f.trade,
                        f.fired_ms,
                        f"{f.peak_at_fire:.4f}",
                        f"{f.exit_r:.4f}",
                        f"{f.actual_r:.4f}",
                        f"{f.later_best:.4f}",
                        int(f.real),
                        f"{f.saved:.4f}",
                    ]
                )
        print(f"\nwrote {out / 'separation_table.csv'} and {out / 'separation_fires.csv'}")
    print(
        "\n⚠ CHEAP MODE: one book, re-walked. Separation picks what earns a replay; it decides "
        "nothing."
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", default=EXPLORE_START)
    ap.add_argument("--end", default=EXPLORE_END)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument(
        "--signal-tf",
        type=int,
        default=5,
        choices=(1, 5, 15),
        help="the chart the reversal rules read (the trade is still found on 15m)",
    )
    ap.add_argument("--spend-test-set", action="store_true")
    ap.add_argument(
        "--separation",
        action="store_true",
        help="grade each reversal signal as REAL reversal vs FALSE alarm once in profit",
    )
    ap.add_argument("--csv-dir", default=None, help="--separation: write its CSVs here")
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
    if args.separation:
        return run_separation(df, track, trades, args)

    peak_bands = (1.0, 1.5, 2.0, 3.0)
    giveback = (0.25, 0.33, 0.5)
    walks = [walk_trade(df, track, t, peak_bands, giveback) for t in trades]

    if args.signal_tf == TF:
        fdf, ftrack = df, track
    else:
        print(f"loading {SYMBOL} {args.signal_tf}m for the reversal rules ...", flush=True)
        from backtest.data.source import BarSource

        fdf = BarSource(server=SERVER).load(SYMBOL, args.signal_tf, args.start, args.end)
        if fdf.empty:
            print(f"no {args.signal_tf}m bars — the cache holds none for this window.")
            return 1
        print(f"  {len(fdf):,} bars; running the engines over them ...", flush=True)
        ftrack = _engine_track(fdf)
    for tr, w in zip(trades, walks):
        dist = float(tr.stop_distance) or 1.0
        cost_r = (float(tr.costs_usd or 0.0) / float(tr.risk_usd)) if tr.risk_usd else 0.0
        rev = walk_reversals(fdf, ftrack, tr, dist, cost_r)
        w.fired_at.update(rev)
        w.by_rule.update({k: v[1] for k, v in rev.items()})

    reached = sum(1 for w in walks if w.peak_r >= 1)
    best_case = sum(w.peak_r for w in walks)
    print(
        f"\n{len(walks)} trades, {reached} reached 1R, best case {best_case:.0f}R, "
        f"kept {sum(w.actual_r for w in walks):.0f}R"
    )
    print(f"reversal rules read the {args.signal_tf}m chart; levels read {TF}m")
    print("\nrule            total R   worst DD   ret/DD   fired on")
    rows = []
    for rule in _rules(peak_bands, giveback):
        total, dd, ratio = _book(walks, rule)
        if rule in COMBOS:
            n = sum(1 for w in walks if combine(w, *COMBOS[rule]) is not None)
        else:
            n = sum(1 for w in walks if rule in w.by_rule)
        rows.append((ratio, rule, total, dd, n))
    hold = [r for r in rows if r[1] == "hold"][0]
    for ratio, rule, total, dd, n in [hold] + sorted(
        [r for r in rows if r[1] != "hold"], key=lambda r: -r[0]
    ):
        print(f"{rule:<14} {total:8.1f}   {dd:8.2f}   {ratio:6.1f}   {n:4d}")
    _hours(walks)
    print(
        "\n⚠ CHEAP MODE: one book, re-walked. An exit that frees the slot earlier gets no "
        "credit for the trade that would have queued behind it. Rank with this; decide with a "
        "replay."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
