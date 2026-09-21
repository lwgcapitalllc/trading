"""loaded_level_confluence.py — the Loaded Level setup with the user's CONFLUENCE: a sweep of a
session high or the previous day's high at the stab, and the option to wait for a bearish SOS.

A STUDY on `loaded_level_study.py`: same detector, same walk, same single position slot, no Pine
twin — every number it prints is a lab finding. Written 2026-09-16 from two of the user's trades:
16 Sep (5m) and their re-drawing of Example 8, 4-8 Sep, on a 3-minute chart ("Ex8b").

🔴 COST-FREE BY INSTRUCTION. Spread 0, no commission, no swap: R is the bare price path (entry,
   stop, target, time exit), and the matched random entries walk the same cost-free books. A
   positive number here is NOT a tradeable edge until it survives costs.
🔴 NEVER READ GOLD BARS BEFORE 2020-01-01. 2018-09 -> 2019-12 is a reserved test set. The M1
   cache file begins in 2018, so `_read_cache_from` finds the first 2020 row by binary search on
   byte offsets and parses nothing before it (a handful of pre-2020 TIMESTAMPS are compared).

THE RULE — fixed before any backtest result was seen (a short; longs are the SAME code on
mirrored bars, where every "high" below is a low):
  SETUP     the study's short setup: an armed top "1", a lower high "2", inducement, a stab of
            "2". Sized like the user's trades, on the level's own geometry: stop - level
            >= 2 ATR(50) and top-to-4 >= 10 ATR(50), on every timeframe. FLOOR: (level - target)
            / (stop - level) >= 1.0 to the cell's target — all of the user's trades are 1.13 or
            better, and without a floor a stab barely above "4" (0.15R) consumes the setup first.
            The same candidates feed every cell, so AGG and CON are compared on the same setups.
  S         the SWEEP: an untaken session high (Asia, London or New York) or previous-trading-day
            high from the liquidity engine is taken between the bar that first reaches the level
            and the entry decision. Secondary, reported only: any named high (adds H4 and the
            previous week). The engine rolls the trading day at 18:00 New York; PU Prime gold is
            shut 17:00-18:00, so the 17:00 rollover gives the same days.
  AGG       the study's stab entry: a sell limit at the level, filled on the first-touch bar.
            Stop = top + 0.25 ATR(50). With S required the sweep must already have happened when
            the limit fills, so ONLY a named high at or below the level, taken on the first-touch
            bar, counts (price had to pass it to reach the level). A high taken above the level
            on that bar is taken AFTER the fill — using it would be look-ahead.
  CON       sell at the CLOSE of the first bar printing an EXTERNAL bearish SOS (the structure
            engine's bearish change of character — the event the study's SOS filter uses):
              S ignored:  the first SOS at or after the first-touch bar;
              S required: the first SOS at or after the bar where S happened — sweep, THEN SOS,
                          the order the user describes.
            Within 24 hours (clock time) of the first touch. Refused if price reached the AGG stop
            or the target between the first touch and the SOS bar (raw bars, inclusive).
            STOP: the highest raw high from the first touch to the SOS bar + 0.25 ATR(50) at the
            SOS bar; refused under 1 ATR(50). (The user dropped the "stop at 1" variant.)
  TARGETS   "4" (the user's base) and "named" (the study's untaken named low past 4).
  EXITS     the study's walk: stop, target or time limit. No runners, no trailing stop.
  TIME      the study's bar counts mean the same HOURS on every timeframe: sweep look-back 2h,
            setup expiry 72h, pool age 72h, max hold 96h (on 5m these ARE the study's numbers).
  ONE SLOT  per cell, both directions sharing it; a setup trades at most once.

THE DECLARED FAMILY — 32 cells, direction both:
  scale {EXTERNAL, INTERNAL} x timeframe {5m, 3m} x {AGG, CON} x {S required, S ignored} x {4, named}
  3m = PU Prime M1 resampled UP by the data layer's `resample_up`.
  Short alone, long alone and the any-named-high S are REPORTED ONLY, never gated.
🔴 THE INTERNAL SCALE IS NOT BUILT, BY INSTRUCTION ("no re-detection; if the study's detector cannot
   be pointed at internal structure without a second implementation, stop"). It cannot:
   `S.detect` takes every swing from the equal-highs/lows engine's 2-bar pivot and hardcodes the
   swing's bar as `i - 2` (tops, levels, the sweep look-back, the "highest since the sweep" check,
   the first "4" window and the inducement lows all key off it). The structure engine's internal
   swings carry their OWN bar and are known later — MEASURED on 50,291 5m bars of 2026: an
   internal swing high 2-19 bars after it printed (median 4, exactly 2 only 10% of the time), an
   internal lower high 1-155 bars after (median 11, exactly 2 4.5%). Fed through that slot every
   internal top and level would sit on the wrong bar. The missing piece is a seam in
   `loaded_level_study.detect`: take the swing source as an argument and read each swing's bar
   from its event. `--scale internal` refuses until it exists.

WINDOWS
  explore  2020-01-01 -> 2025-08-31 — THE GATE. Walks stop at the window end; a trade still open
           there is dropped and counted, never marked.
  recent   2025-09-01 -> today, reported SEPARATELY and never as a gate: it was already used for
           one Loaded Level test and it contains the user's own trades.

THE GATE (explore, direction both, cost-free): >= 30 trades in each half; average R positive in
both halves; t >= 2.95 (32 declared cells, Bonferroni 5%); beats matched random entries (same
direction, stop and target distance, same walk) at z >= 2. If a cell passes, STOP: it is not to be
run anywhere else, and 2018-2019 stays untouched.

ROUND 2 (2026-09-16, declared before any round-2 result) — the sweep is MANDATORY:
  SWEEP     a session high (Asia, London, New York) or the previous trading day's high, taken
            from 2 HOURS (clock) before the bar that first reaches the level up to the entry
            decision. E0 only: the window ends at the touch bar and only highs at or below the
            level count. E1-E4: the first such high in the window must come at or before the
            entry — each confirmation is the first one at or after BOTH the touch and that sweep.
  CELLS     5m setups (sized and floored as above), target 4, direction both, one slot, cost-free:
    E0 AGG       limit at 2, stop = top + 0.25 ATR(50).
    E1 CLOSE-5   sell at the close of the first 5m bar that closes below the level.
    E2 CLOSE-15  the same on 15m candles (5m resampled UP, closed-left); entry at that close.
    E3 SOS-1m    sell at the close of the first 1m bar printing an EXTERNAL bearish SOS (the
                 structure engine run on clean PU Prime M1 bars). The touch and the sweep are
                 timed to the minute from raw 1m highs; a 5m bar whose 1m bars never reach the
                 price is timed at its last minute. Walked on 1m bars, same 96-hour limit.
    E4 SOS-5m    the round-1 conservative entry, under this sweep window.
    E1-E4: within 24h of the touch; refused if the E0 stop or the target traded first (touch ->
    entry, raw bars, inclusive); stop = highest raw high touch -> entry + 0.25 ATR(50) of the
    last closed 5m bar, refused under 1 ATR.
  GATE      explore only: >= 30 trades a half, both halves > 0, t >= 2.33 (5 cells), z >= 2.
            The break-even win rate is worked out TRADE BY TRADE (it was 1/(1+avg R:R) in round 1).
  SELECTION over E0's own explore trades: does each confirmation fire on that SAME stab (no
            slot), and how did E0 do on the stabs it keeps against the ones it drops?
  REPLAY    60 E0-qualifying setups, seed 20260916, decisions 2022-01-01 -> 2025-08-31 NY: 10 per
            year first, then 20 from the rest; direction as it falls; nothing within 3 days of a
            user trade; decisions at least 7 days apart (so no chart shows another's outcome);
            first qualifying stab per setup, one per bar and direction; setups whose 1, 2 or 4
            lies outside the window are left out. Bars: the 720 before the decision bar (reopen
            spikes clipped as the detector saw them, real prices), then the decision bar CUT AT
            THE TOUCH from raw PU Prime M1 bars: its open through the first minute reaching the
            level; that minute contributes only its open and the level (nothing else of it is
            known by the touch); close = the level.
            Levels: those still live at the decision bar, plus those taken inside the window.
            Anything stamped on the decision bar must be known by the touch minute: its swing
            labels and breaks (reported at the close) are dropped; a weekly level's "taken" is
            dropped (a close rule); a session / daily "taken" stays only if the cut M1 path
            trades through it; the sweep shown is the latest one known by the touch minute. A
            setup with none is replaced by the next item of the same seeded stream.
            Outcomes go to a separate CSV (E0-E4 with no slot).

Usage (one command each; --tf 5 or 3):
  python backtest/tools/loaded_level_confluence.py fetch               # extend PU Prime M5/M15/M1
  python backtest/tools/loaded_level_confluence.py readback --tf 5     # the 16 Sep trade + recall
  python backtest/tools/loaded_level_confluence.py readback --tf 3     # the Ex8b trade + recall
  python backtest/tools/loaded_level_confluence.py run --tf 5          # the declared cells, 5m
  python backtest/tools/loaded_level_confluence.py run --tf 3          # the declared cells, 3m
  python backtest/tools/loaded_level_confluence.py review --tf 5       # blind review list, 5m
  python backtest/tools/loaded_level_confluence.py review --tf 3       # blind review list, 3m
  python backtest/tools/loaded_level_confluence.py entries             # round 2: recall + E0-E4
  python backtest/tools/loaded_level_confluence.py replay              # round 2: blind replay data
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loaded_level_study as S  # noqa: E402

from backtest.data.resample import resample_up  # noqa: E402
from backtest.replay.loop import iter_bars  # noqa: E402

RESERVED_BEFORE = pd.Timestamp("2020-01-01")  # 🔴 never read gold bars before this
START = "2020-01-01"
RECENT = pd.Timestamp("2025-09-01")  # explore = [START, RECENT)
REVIEW_FROM = pd.Timestamp("2026-06-01", tz=S.NY).tz_convert("UTC").tz_localize(None)
REVIEW_CAP = 60
SERVER = "PUPrime-Demo"  # the terminal's name; its cache folder is PUPrime_Demo
MIN_RISK_ATR = 2.0
MIN_RANGE_ATR = 10.0
FLOOR = 1.0
CON_WAIT_NS = 24 * 3600 * 10**9
CON_MIN_RISK_ATR = 1.0
MIN_PER_HALF = 30
T_BAR = 2.95  # 32 declared cells
Z_BAR = 2.0
TARGETS = ("4", "named")
PRIMARY = frozenset({"session", "daily"})  # any session high, previous trading day's high
ANY_NAMED = frozenset({"session", "daily", "h4", "weekly"})
CELLS = [
    dict(entry=e, s=s, target=t) for e in ("AGG", "CON") for s in (True, False) for t in TARGETS
]

# The user's trades. Broker top / fill bar (UTC) / entry: `S.EXAMPLES` plus the two added here.
# Targets are the user's own (docs/DAVINCI_MODEL_SPEC.md, and the 2026-09-16 drawings).
EX10 = ("Ex10 16 Sep", 4402.52, "2026-09-16 13:10", 4355.37)
EX8B = ("Ex8b 07 Sep 3m", 4449.00, "2026-09-08 01:50", 4438.45)
TRADES = [*S.EXAMPLES, EX10, EX8B]
USER_TARGET = {
    "Ex3 26 Aug": 4583.10,
    "Ex4 25 Aug": 4594.56,
    "Ex5 28 Aug": 4568.54,
    "Ex6 31 Aug": 4396.16,
    "Ex7 04 Sep": 4457.07,
    "Ex8 07 Sep": 4364.87,
    "Ex9 22 Jul": 4106.68,
    "Ex10 16 Sep": 4253.08,
    "Ex8b 07 Sep 3m": 4381.20,
}
# The user's drawings (TradingView feed; times NY, as the user gave them) for the read-back.
READBACK = {
    5: dict(
        trade=EX10,
        steps=dict(
            top=(4405.0, "Fri 11 Sep ~11:00-12:00"), level=(4357.0, "Sun 13 / Mon 14 ~00:00"),
            three=(4280.0, "Mon 14 ~04:00"), four=(4254.0, "Mon 14 ~09:00"),
            stab=(4367.40, "Wed 16 ~09:00-12:00"), nl=(4352.0, "Fri 11 afternoon"),
        ),
        agg=(4355.38, 4401.85, 4253.08), con=(4324.0, 4367.40, 4253.08), con_at=None,
        nl_utc=("2026-09-11 16:00", "2026-09-11 21:00"),
    ),
    3: dict(
        trade=EX8B,
        steps=dict(
            top=(4449.70, "Fri 04 Sep ~11:20"), level=(4438.45, "Fri 04 ~15:30"),
            three=(4389.0, "Mon 07 ~00:20"), four=(4381.0, "Mon 07 ~07:30"),
            stab=(4442.85, "Tue 08 ~00:05"),
        ),
        agg=(4438.45, 4449.67, 4381.20), con=(4421.60, 4442.85, 4381.20),
        con_at="2026-09-08 05:45", nl_utc=None,
    ),
}  # fmt: skip


# ─────────────────────────────── recording the engines ───────────────────────────────


@dataclass
class Events:
    """What the canonical engines printed on one side's bars, captured while `S.detect` runs —
    the SAME events the detector read, never a second pass and never a re-detection."""

    sos: dict = field(default_factory=dict)  # bar -> level an EXTERNAL bearish SOS broke
    bos: dict = field(default_factory=dict)  # bar -> (level, its bar) an EXTERNAL bearish BOS broke
    isos: dict = field(default_factory=dict)  # bar -> level an INTERNAL bearish SOS broke
    taken: dict = field(default_factory=dict)  # bar -> [(name, kind, price)] highs taken
    ph: dict = field(default_factory=dict)  # confirm bar -> strict pivot high (bar is i - 2)
    # Chart context for the blind replay — recorded on the REAL (short-side) bars only:
    full: bool = False
    breaks: list = field(
        default_factory=list
    )  # (bar, swing bar, price, BOS|SOS, bull|bear, ext|int)
    swings: list = field(
        default_factory=list
    )  # (known bar, swing bar, price, HH|HL|LH|LL, ext|int)
    levels: dict = field(default_factory=dict)  # id -> [name, price, created, taken, evicted]


_REC = Events()
_INT_LABEL = {"iHH": "HH", "iLL": "LL", "iLH": "LH", "iHL": "HL"}  # iSH / iSL (the seed) skipped
_LEVEL_KINDS = frozenset({"daily", "weekly", "session"})


def _record_context(i: int, x, n, liq) -> None:
    for bull in (True, False):
        if bull and x.bull_bos and x.bull_bos_price is not None:
            loc = x.bull_bos_h_loc if x.bull_bos_h_loc is not None else i
            _REC.breaks.append(
                (i, loc, x.bull_bos_price, "SOS" if x.bull_sos else "BOS", "bull", "ext")
            )
        if not bull and x.bear_bos and x.bear_bos_price is not None:
            loc = x.bear_bos_l_loc if x.bear_bos_l_loc is not None else i
            _REC.breaks.append(
                (i, loc, x.bear_bos_price, "SOS" if x.bear_sos else "BOS", "bear", "ext")
            )
        if (n.bull_bos or n.bull_sos) if bull else (n.bear_bos or n.bear_sos):
            sos = bool(n.bull_sos if bull else n.bear_sos)
            if bull:
                px, loc = (
                    (n.bull_sos_price, n.bull_sos_loc)
                    if sos
                    else (n.bull_bos_price, n.bull_bos_loc)
                )
            else:
                px, loc = (
                    (n.bear_sos_price, n.bear_sos_loc)
                    if sos
                    else (n.bear_bos_price, n.bear_bos_loc)
                )
            if px is not None and loc is not None:
                _REC.breaks.append(
                    (i, loc, px, "SOS" if sos else "BOS", "bull" if bull else "bear", "int")
                )
    for lab, px, at in ((x.broken_high_label, x.broken_high_price, x.broken_high_index),
                        (x.broken_low_label, x.broken_low_price, x.broken_low_index)):  # fmt: skip
        if lab in ("HH", "LH", "HL", "LL") and px is not None and at is not None:
            _REC.swings.append((i, at, px, lab, "ext"))
    for lab, px, at in (
        (
            n.swing_high_label if n.new_swing_high else None,
            n.new_swing_high_price,
            n.new_swing_high_index,
        ),
        (
            n.swing_low_label if n.new_swing_low else None,
            n.new_swing_low_price,
            n.new_swing_low_index,
        ),
        (n.demoted_high_label, n.demoted_high_price, n.demoted_high_index),
        (n.demoted_low_label, n.demoted_low_price, n.demoted_low_index),
    ):
        if lab in _INT_LABEL and px is not None and at is not None:
            _REC.swings.append((i, at, px, _INT_LABEL[lab], "int"))
    if liq is None:
        return
    for v in liq.created:
        if v.kind in _LEVEL_KINDS and v.side in ("high", "low"):
            _REC.levels[v.id] = [v.name, v.price, i, None, None]
    for v in liq.mitigated:
        if v.id in _REC.levels and _REC.levels[v.id][3] is None:
            _REC.levels[v.id][3] = i
    for v in liq.evicted:
        if v.id in _REC.levels and _REC.levels[v.id][4] is None:
            _REC.levels[v.id][4] = i


_BaseStack = S.EngineStack  # the unrecorded stack, for the 1m structure pass


class _RecStack(S.EngineStack):
    def step(self, bar):
        st = super().step(bar)
        x, n = st.structure.external, st.structure.internal
        if x.bear_bos:
            _REC.bos[bar.index] = (x.bear_bos_price, x.bear_bos_l_loc)
            if x.bear_sos:
                _REC.sos[bar.index] = x.bear_bos_price
        if n.bear_sos:
            _REC.isos[bar.index] = n.bear_sos_price
        if st.liquidity is not None:
            got = [(v.name, v.kind, v.price) for v in st.liquidity.mitigated if v.side == "high"]
            if got:
                _REC.taken[bar.index] = got
        if _REC.full:
            _record_context(bar.index, x, n, st.liquidity)
        return st


class _RecEq(S.EqualHighsLowsEngine):
    def update(self, bar_index, high, low, close):
        ev = super().update(bar_index, high, low, close)
        if ev.pivot_high is not None:
            _REC.ph[bar_index] = ev.pivot_high
        return ev


S.EngineStack = _RecStack  # `S.detect` looks both names up at call time
S.EqualHighsLowsEngine = _RecEq


# ─────────────────────────────── bars and sides ───────────────────────────────


def configure(tf: int) -> None:
    """The study's bar counts, rescaled to mean the same hours (identical on 5m)."""
    per_hour = 60 // tf
    S.SWEEP_LB, S.EXPIRY, S.POOL_AGE, S.MAX_HOLD = (
        2 * per_hour,
        72 * per_hour,
        72 * per_hour,
        96 * per_hour,
    )


def _read_cache_from(path: Path, start: pd.Timestamp) -> pd.DataFrame:
    """A cache CSV from its first row at/after `start`. The row is found by binary search on
    byte offsets, so no earlier row's prices are ever parsed."""
    target = start.strftime("%Y-%m-%d %H:%M:%S").encode()
    size = path.stat().st_size
    with path.open("rb") as f:
        cols = f.readline().decode().strip().split(",")
        lo, hi = f.tell(), size
        while hi - lo > 256:
            mid = (lo + hi) // 2
            f.seek(mid)
            f.readline()
            p = f.tell()
            line = f.readline()
            if not line or line[:19] >= target:
                hi = mid
            else:
                lo = p
        f.seek(lo)
        while True:
            p = f.tell()
            line = f.readline()
            if not line or line[:19] >= target:
                break
        f.seek(p)
        df = pd.read_csv(f, header=None, names=cols, parse_dates=["time"])
    if len(df) and df["time"].iloc[0] < start:
        sys.exit("refused: the cache reader returned a bar before the start")
    return df.set_index("time")


def load(server_dir: str, symbol: str, tf: int) -> pd.DataFrame:
    if pd.Timestamp(START) < RESERVED_BEFORE:
        sys.exit("refused: gold bars before 2020-01-01 are a reserved test set")
    base = {5: "M5", 3: "M1"}[tf]
    path = S.ROOT / "backtest" / "cache" / server_dir / f"{symbol}__{base}.csv"
    df = _read_cache_from(path, pd.Timestamp(START))[["open", "high", "low", "close"]].astype(float)
    if tf == 3:
        df = resample_up(df, 3, 1)
    closed = df.index + pd.Timedelta(minutes=tf) <= pd.Timestamp.now("UTC").tz_localize(None)
    return df[closed]


def fetch(end: str) -> None:
    from backtest.data import BarSource

    src = BarSource(server=SERVER)
    for tf in ("M5", "M15", "M1"):
        df = src.load("XAUUSD.p", tf, "2026-09-10", end)
        print(f"{tf}: cache now ends {df.index[-1]} UTC")


@dataclass
class Side:
    name: str
    st: S.Side  # the study's side: setups, candidate columns, top, range
    ev: Events
    atr: np.ndarray
    L: np.ndarray  # clean lows (detection)
    sos_bars: np.ndarray = None
    isos_bars: np.ndarray = None
    sweep_bars: dict = None  # "primary" / "any" -> sorted bars where such a high was taken

    def sign(self, px: float) -> float:
        return px if self.name == "short" else -px

    def label(self, name: str) -> str:
        if self.name == "short":
            return name
        return {"PDH": "PDL", "PWH": "PWL"}.get(
            name, name[:-1] + "L" if name.endswith("H") else name
        )

    def taken(self, a: int, b: int, kinds: frozenset, at_most: float = math.inf) -> list:
        """Highs of `kinds` taken on bars a..b, priced at or below `at_most` (side space)."""
        out = []
        for j in sorted(k for k in self.ev.taken if a <= k <= b):
            for name, kind, px in self.ev.taken[j]:
                if kind in kinds and px <= at_most + 1e-9:
                    out.append((j, self.label(name), self.sign(px)))
        return out


def build(raw: pd.DataFrame, tf: int, context: bool = False) -> dict:
    global _REC
    clean, fixed = S.clean_reopens(raw)
    print(
        f"{len(raw):,} {tf}m bars {raw.index[0]} -> {raw.index[-1]} UTC; {len(fixed)} reopen "
        f"spikes clipped for detection; COST-FREE (spread 0, no fees, no swap); time limits "
        f"sweep {S.SWEEP_LB} / expiry {S.EXPIRY} / hold {S.MAX_HOLD} bars"
    )
    sides = {}
    for name, cl, rw in (("short", clean, raw), ("long", S.mirror(clean), S.mirror(raw))):
        _REC = Events(full=context and name == "short")
        st = S.build_side(name, cl, rw, 0.0)
        h, lo, c = (cl[k].to_numpy() for k in ("high", "low", "close"))
        sd = Side(name, st, _REC, S.wilder_atr(h, lo, c), lo)
        sd.sos_bars = np.array(sorted(_REC.sos), dtype=np.int64)
        sd.isos_bars = np.array(sorted(_REC.isos), dtype=np.int64)
        sd.sweep_bars = {
            tag: np.array(
                sorted(j for j, got in _REC.taken.items() if any(k in kinds for _, k, _ in got)),
                dtype=np.int64,
            )
            for tag, kinds in (("primary", PRIMARY), ("any", ANY_NAMED))
        }
        sides[name] = sd
    return sides


# ─────────────────────────────── entries ───────────────────────────────

S_T: dict = {}  # "t" -> bar open times (ns), set once the bars are loaded


def _first(arr: np.ndarray, at_least: int) -> int | None:
    k = int(np.searchsorted(arr, at_least))
    return int(arr[k]) if k < len(arr) else None


def candidates(sd: Side, target: str, n_end: int):
    """Indices of the study's candidates sized like the user's trades, with their stop/target."""
    c = sd.st.c
    if not len(c["bar"]):
        return np.array([], dtype=int), None, None
    tgt = S.targets(sd.st, target)
    stop = sd.st.top + S.BUFFER * c["atr"]
    risk, reward = stop - c["entry"], c["entry"] - tgt
    with np.errstate(divide="ignore", invalid="ignore"):
        rr = np.where(risk > 0, reward / risk, -1.0)
        m = c["induced"] & (risk > 0) & (reward > 0) & ~np.isnan(c["atr"])
        m &= (rr >= FLOOR) & (sd.st.range_atr >= MIN_RANGE_ATR)
        m &= risk >= MIN_RISK_ATR * c["atr"]
    m &= c["bar"] < n_end
    return np.flatnonzero(m), stop, tgt


def agg_entry(sd: Side, k: int, stop: float, tgt: float, s_mode: str | None):
    c = sd.st.c
    i, level = int(c["bar"][k]), float(c["entry"][k])
    sweeps = sd.taken(i, i, ANY_NAMED if s_mode == "any" else PRIMARY, at_most=level)
    if s_mode and not sweeps:
        return None
    if sd.st.book.H[i] < level:  # raw bars never reached the resting limit
        return None
    return dict(ebar=i, entry=level, stop=stop, target=tgt, force=False, sweeps=sweeps, sos=None)


def con_entry(sd: Side, k: int, agg_stop: float, tgt: float, s_mode: str | None, n_end: int):
    c, b, t = sd.st.c, sd.st.book, S_T["t"]
    i = int(c["bar"][k])
    start = i
    if s_mode:
        sb = _first(sd.sweep_bars[s_mode], i)
        if sb is None or t[sb] - t[i] > CON_WAIT_NS:
            return None
        start = sb
    j = _first(sd.sos_bars, start)
    if j is None or j >= n_end - 1 or t[j] - t[i] > CON_WAIT_NS:
        return None
    hi = float(b.H[i : j + 1].max())
    if hi >= agg_stop or b.L[i : j + 1].min() <= tgt:
        return None
    entry, a = float(b.C[j]), float(sd.atr[j])
    stop = hi + S.BUFFER * a
    if stop - entry < CON_MIN_RISK_ATR * a:
        return None
    sweeps = sd.taken(i, j, ANY_NAMED if s_mode == "any" else PRIMARY)
    return dict(ebar=j, entry=entry, stop=stop, target=tgt, force=True, sweeps=sweeps, sos=j)


def walk(e: dict, book: S.Book):
    first = e["ebar"] + (1 if e["force"] else 0)
    return book.walk(first, e["entry"], e["stop"], e["target"], force=e["force"])


def run_cell(sides: list, cell: dict, books: dict, n_end: int, s_mode: str | None) -> tuple:
    rows = []
    for sd in sides:
        ks, stop, tgt = candidates(sd, cell["target"], n_end)
        c = sd.st.c
        for k in ks:
            if cell["entry"] == "AGG":
                e = agg_entry(sd, k, float(stop[k]), float(tgt[k]), s_mode)
                a = float(c["atr"][k])
            else:
                e = con_entry(sd, k, float(stop[k]), float(tgt[k]), s_mode, n_end)
                a = float(sd.atr[e["ebar"]]) if e else math.nan
            if e is None:
                continue
            e.update(side=sd, k=int(k), setup=int(c["setup"][k]), stab=int(c["bar"][k]), atr=a)
            rows.append((e["ebar"], e["stab"], float(c["entry"][k]), -e["setup"], sd.name, e))
    rows.sort(key=lambda r: r[:5])
    trades, traded, free, still_open = [], set(), -1, 0
    for ebar, *_, e in rows:
        sd = e["side"]
        key = (sd.name, e["setup"])
        if key in traded or ebar <= free:
            continue
        book = books[sd.name]
        res = walk(e, book)
        if res is None:
            continue
        xbar, r, outcome = res
        traded.add(key)
        free = xbar
        if outcome == "time" and xbar == book.n - 1 and ebar + S.MAX_HOLD > book.n - 1:
            still_open += 1
            continue
        risk = e["stop"] - e["entry"]
        trades.append(dict(
            e, bar=ebar, xbar=xbar, r=r, r_gross=r, outcome=outcome,
            rr=(e["entry"] - e["target"]) / risk, risk_atr=risk / e["atr"],
        ))  # fmt: skip
    return trades, still_open


# ─────────────────────────────── scoring ───────────────────────────────


def matched_random(books: dict, trades: list, lo: int, reps: int = 20, seed: int = 7) -> tuple:
    """`S.control` with the draw range bounded to the window: same direction, stop distance,
    target distance and walk; only the entry bar is random, entered at a close."""
    rng = np.random.default_rng(seed)
    rs, hits = [], 0
    for t in trades:
        b = books[t["side"].name]
        risk, reward = t["stop"] - t["entry"], t["entry"] - t["target"]
        for _ in range(reps):
            j = int(rng.integers(lo, b.n - S.MAX_HOLD - 2))
            e = b.C[j] - b.en
            _, r, how = b.walk(j + 1, e, e + risk, e - reward, force=True)
            rs.append(r)
            hits += how == "target"
    return np.array(rs), hits / max(len(rs), 1) * 100


def score(trades: list, books: dict, split: int, months: float, lo: int) -> dict:
    st = S.stats(trades, split, months)
    if st["n"] < 2:
        return dict(st, be=0.0, rand=0.0, rwin=0.0, z=0.0)
    g = np.array([t["r"] for t in trades])
    rs, rwin = matched_random(books, trades, lo)
    z = (g.mean() - rs.mean()) / math.sqrt(g.var(ddof=1) / len(g) + rs.var(ddof=1) / len(rs))
    be = float(np.mean([100.0 / (1.0 + t["rr"]) for t in trades]))  # trade by trade
    return dict(st, be=be, rand=float(rs.mean()), rwin=float(rwin), z=float(z))


def gate(sc: dict, t_bar: float = T_BAR) -> str:
    fails = []
    if sc["n1"] < MIN_PER_HALF or sc["n2"] < MIN_PER_HALF:
        fails.append("halves<30")
    if not (sc["h1"] > 0 and sc["h2"] > 0):
        fails.append("a half <=0")
    if sc["t_stat"] < t_bar:
        fails.append(f"t<{t_bar}")
    if sc["z"] < Z_BAR:
        fails.append(f"z<{Z_BAR:g}")
    return "PASS" if not fails else "fail: " + ", ".join(fails)


HEAD = (
    f"{'cell':<26} {'n':>5} {'/mo':>5} {'win%':>6} {'RR':>5} {'BEwin%':>7} {'avgR':>7} "
    f"{'totR':>7} {'1st½ (n)':>13} {'2nd½ (n)':>13} {'maxDD':>6} {'t':>6} "
    f"{'randR':>7} {'randWin':>7} {'z':>6}"
)


def fmt(label: str, sc: dict, open_n: int) -> str:
    extra = f"  (+{open_n} open, excluded)" if open_n else ""
    return (
        f"{label:<26} {sc['n']:>5} {sc['pm']:>5.1f} {sc['win']:>5.1f}% {sc['rr']:>5.2f} "
        f"{sc.get('be', 0):>6.1f}% {sc['avg']:>+7.3f} {sc['tot']:>+7.1f} "
        f"{sc['h1']:>+7.1f} ({sc['n1']:>3}) {sc['h2']:>+7.1f} ({sc['n2']:>3}) {sc['dd']:>6.1f} "
        f"{sc['t_stat']:>+6.2f} {sc.get('rand', 0):>+7.3f} {sc.get('rwin', 0):>6.1f}% "
        f"{sc.get('z', 0):>+6.2f}{extra}"
    )


def cell_name(cell: dict, s_mode: str | None) -> str:
    s = {None: "S ignored", "primary": "S required", "any": "S=any named"}[s_mode]
    return f"{cell['entry']} {s} tgt {cell['target']}"


# ─────────────────────────────── report helpers ───────────────────────────────


def ny(index: pd.DatetimeIndex, i: int | None) -> str:
    if i is None or i < 0:
        return ""
    return index[i].tz_localize("UTC").tz_convert(S.NY).strftime("%a %d %b %H:%M")


def fmt_sweeps(index, sweeps: list) -> str:
    return "; ".join(f"{n} {p:.2f} @{ny(index, j)}" for j, n, p in sweeps) or "none"


def anatomy(sd: Side, k: int) -> dict:
    """1 / 2 / 3 / 4 / 5 for one candidate, in real prices. "3" is the low broken by the last
    external bearish break before "4" printed (the deck's "a small low taken"), at the bar the
    structure engine gives for it — which may be before the top. The detector's own inducement
    is looser: any swing low after the top undercut."""
    c = sd.st.c
    s = sd.st.setups[int(c["setup"][k])]
    i, level = int(c["bar"][k]), float(c["entry"][k])
    seg = sd.L[s.top_bar + 1 : i]
    b4 = s.top_bar + 1 + int(np.argmin(seg)) if len(seg) else -1
    lv = [j - 2 for j, px in sd.ev.ph.items() if abs(px - level) < 1e-9 and s.top_bar < j - 2 < i]
    three = [j for j in sd.ev.bos if s.top_bar < j <= b4]
    j3 = max(three) if three else None
    px3, j3_low = sd.ev.bos[j3] if j3 is not None else (math.nan, None)
    j3_low = -1 if j3_low is None else int(j3_low)
    return dict(
        top=sd.sign(s.top), top_bar=s.top_bar, level=sd.sign(level),
        level_bar=max(lv) if lv else -1,
        three=sd.sign(px3) if j3 is not None else math.nan,
        three_bar=j3 if j3 is not None else -1, three_low_bar=j3_low,
        four=sd.sign(float(c["low4"][k])), four_bar=b4, stab_bar=i, setup=s.id, kind=s.kind,
    )  # fmt: skip


def show_trade(tag: str, sd: Side, book: S.Book, index, e: dict | None) -> None:
    if e is None:
        print(f"    {tag:<46} no entry")
        return
    res = walk(e, book)
    if res is None:
        print(f"    {tag:<46} limit {sd.sign(e['entry']):.2f} never filled")
        return
    xbar, r, outcome = res
    risk = e["stop"] - e["entry"]
    first = e["ebar"] + (1 if e["force"] else 0)
    mae = (book.H[first : xbar + 1].max() - e["entry"]) / risk
    print(
        f"    {tag:<46} entry {sd.sign(e['entry']):.2f} @{ny(index, e['ebar'])}  stop "
        f"{sd.sign(e['stop']):.2f}  target {sd.sign(e['target']):.2f}  R:R "
        f"{(e['entry'] - e['target']) / risk:.2f} -> {outcome} {r:+.2f}R @{ny(index, xbar)} "
        f"({xbar - e['ebar']} bars)  worst against {mae:.2f}R"
    )


def find_trade(sd: Side, index, name: str, top_px: float, fill_utc: str, entry: float):
    """The study's recall match: the same top (+-0.60) alive at the fill, and a level stab within
    3 bars and $3.00 of the user's entry."""
    fb = int(index.searchsorted(pd.Timestamp(fill_utc)))
    hits = [
        s
        for s in sd.st.setups
        if abs(s.top - top_px) <= 0.6 and s.made <= fb and (s.dead == -1 or s.dead >= fb)
    ]
    if not hits:
        near = [s for s in sd.st.setups if abs(s.top - top_px) <= 0.6]
        return None, (
            f"top armed but dead at {ny(index, near[-1].dead)}" if near else "top never armed"
        )
    s = hits[-1]
    c = sd.st.c
    ks = [
        int(k)
        for k in np.flatnonzero(c["setup"] == s.id)
        if abs(c["bar"][k] - fb) <= 3 and abs(c["entry"][k] - entry) <= 3.0
    ]
    if not ks:
        return (
            None,
            f"top armed (setup {s.id}) but no level stab within 3 bars / $3.00 of the entry",
        )
    return min(ks, key=lambda k: abs(c["entry"][k] - entry)), ""


# ─────────────────────────────── Stage A ───────────────────────────────


def read_trade(sides: dict, raw: pd.DataFrame, n: int, tf: int, spec: dict) -> None:
    sd, index, t = sides["short"], raw.index, S_T["t"]
    book, c = sd.st.book, sd.st.c
    name = spec["trade"][0]
    k, why = find_trade(sd, index, *spec["trade"])
    print(f"\nSTAGE A — {name} ON PU PRIME {tf}m, EXTERNAL scale (cost-free)")
    if k is None:
        print(f"  the detector does NOT take it: {why}")
        return
    a = anatomy(sd, k)
    s = sd.st.setups[a["setup"]]
    u = spec["steps"]
    i = a["stab_bar"]
    s1 = _first(sd.sweep_bars["primary"], i)
    sos1 = _first(sd.sos_bars, i)
    sos2 = _first(sd.sos_bars, s1) if s1 is not None else None
    isos1 = _first(sd.isos_bars, i)
    print(
        f"  armed: setup {s.id}, sweep under the top = {s.kind}, armed {ny(index, s.made)}; "
        f"setup dies {ny(index, s.dead) or 'alive'}"
    )
    rows = [
        ("1 top", "top", a["top"], a["top_bar"]),
        ("2 loaded lower high", "level", a["level"], a["level_bar"]),
        ("3 low (printed)", "three", a["three"], a["three_low_bar"]),
        ("3 ... broken by an ext bear BOS", "three", a["three"], a["three_bar"]),
        ("4 lower low", "four", a["four"], a["four_bar"]),
        ("5 first touch of 2 (bar high)", "stab", float(book.H[i]), i),
    ]
    for j in sorted({x for x in (sos1, sos2, isos1) if x is not None}):
        hb = int(i + np.argmax(book.H[i : j + 1]))
        rows.append((f"5 stab high, touch -> {ny(index, j)[-5:]}", "stab", float(book.H[hb]), hb))
    print(f"  {'step':<34} {'user':>9} {'user time (NY)':<24} {'PU Prime':>9}  PU Prime NY time")
    for lab, key, pp, bar in rows:
        up, ut = u[key]
        print(f"  {lab:<34} {up:>9.2f} {ut:<24} {pp:>9.2f}  {ny(index, bar)}")
    if spec["nl_utc"]:
        lo_t, hi_t = (pd.Timestamp(x) for x in spec["nl_utc"])
        fri = [(j - 2, px) for j, px in sorted(sd.ev.ph.items()) if lo_t <= index[j - 2] < hi_t]
        print(
            f"  NL (user {u['nl'][0]:.2f}, {u['nl'][1]}): PU Prime swing highs "
            + ", ".join(f"{px:.2f} @{ny(index, j)[-5:]}" for j, px in fri)
        )
    last = min(n - 1, i + int(36 * 60 / tf))
    since = int(index.searchsorted(index[i] - pd.Timedelta(hours=24)))
    print("\n  Named highs taken, 24h before first touch -> 36h after (liquidity engine):")
    for j, nm, px in sd.taken(since, last, ANY_NAMED):
        kind = "S" if nm.startswith(("Asia", "London", "NY", "PDH")) else "other"
        where = "before first touch" if j < i else "after first touch"
        print(f"    {ny(index, j)}  {nm:<9} {px:.2f}  [{kind}]  {where}")
    print("\n  Bearish SOS after the first touch (structure engine; external is what CON uses):")
    evs = [(j, "external", sd.ev.sos[j]) for j in sd.sos_bars if i <= j <= last]
    evs += [(j, "internal", sd.ev.isos[j]) for j in sd.isos_bars if i <= j <= last]
    for j, scale, px in sorted(evs):
        print(
            f"    {ny(index, j)}  {scale:<8} broke {px:.2f}  bar close {book.C[j]:.2f}  "
            f"(+{(t[j] - t[i]) / 3.6e12:.1f}h)"
        )
    print(
        f"  -> first external SOS after touch {ny(index, sos1) or 'none'}; first S after touch "
        f"{ny(index, s1) or 'none'}; first external SOS at/after that S {ny(index, sos2) or 'none'}"
    )
    lvl = float(c["entry"][k])
    print(
        f"  S on the touch bar at/below the level (AGG-S): "
        f"{fmt_sweeps(index, sd.taken(i, i, PRIMARY, at_most=lvl))}"
    )
    if sos1 is not None:
        print(
            f"  S between touch and the first external SOS: {fmt_sweeps(index, sd.taken(i, sos1, PRIMARY))}"
        )

    print("\n  THE TRADES at the user's level, walked on PU Prime bars (cost-free):")
    for tgt_name in TARGETS:
        _, stop, tgt = candidates(sd, tgt_name, n)
        st_k, tg_k = float(stop[k]), float(tgt[k])
        print(f"   target {tgt_name} = {tg_k:.2f}  (level R:R {(lvl - tg_k) / (st_k - lvl):.2f})")
        for tag, e in (
            ("AGG (limit at 2, stop top+0.25ATR)", agg_entry(sd, k, st_k, tg_k, None)),
            ("CON, S ignored (first SOS after touch)", con_entry(sd, k, st_k, tg_k, None, n)),
            ("CON, S required (first SOS after sweep)", con_entry(sd, k, st_k, tg_k, "primary", n)),
        ):
            show_trade(tag, sd, book, index, e)
    ae, ast, atg = spec["agg"]
    ce, cst, ctg = spec["con"]
    print("   the user's own numbers, walked on PU Prime bars:")
    show_trade(f"user AGG {ae} / {ast} / {atg}", sd, book, index,
               dict(ebar=i, entry=ae, stop=ast, target=atg, force=False))  # fmt: skip
    con_bar = (
        sos2 if spec["con_at"] is None else int(index.searchsorted(pd.Timestamp(spec["con_at"])))
    )
    if con_bar is not None:
        show_trade(f"user CON {ce} / {cst} / {ctg} @bar {ny(index, con_bar)[-5:]}", sd, book, index,
                   dict(ebar=con_bar, entry=ce, stop=cst, target=ctg, force=True))  # fmt: skip

    print("\n  WHAT THE DECLARED ONE-SLOT CELLS DID WITH THIS SETUP (direction both):")
    books = {nm: sides[nm].st.book for nm in sides}
    for cell in CELLS:
        s_mode = "primary" if cell["s"] else None
        trades, _ = run_cell(list(sides.values()), cell, books, n, s_mode)
        mine = [x for x in trades if x["side"].name == "short" and x["setup"] == s.id]
        if not mine:
            took = "did not trade it"
        else:
            x = mine[0]
            took = (
                f"stab of {float(c['entry'][x['k']]):.2f} @{ny(index, x['stab'])}, entry "
                f"{x['entry']:.2f} @{ny(index, x['bar'])}, stop {x['stop']:.2f}, target "
                f"{x['target']:.2f} -> {x['outcome']} {x['r']:+.2f}R; S: {fmt_sweeps(index, x['sweeps'])}"
            )
        print(f"    {cell_name(cell, s_mode):<26} {took}")


def recall(sides: dict, raw: pd.DataFrame, n: int, tf: int) -> None:
    sd, index, t = sides["short"], raw.index, S_T["t"]
    book, c = sd.st.book, sd.st.c
    print(
        f"\nRECALL on {tf}m — the user's 9 trades (short side). S = a session high or the previous"
    )
    print("day's high. Every window runs from the first touch of the level to the user's target.")
    hdr = ("trade", "first touch @level", "S on touch bar <=lvl", "S touch->target",
           "1st ext bear SOS after touch", "ext SOS after 1st S", "target hit",
           "bear SOS touch->before target bar ext/int", "any named high touch->target")  # fmt: skip
    print("  " + " | ".join(hdr))
    for name, top_px, fill, entry in TRADES:
        k, why = find_trade(sd, index, name, top_px, fill, entry)
        if k is None:
            print(f"  {name} | not found: {why}")
            continue
        i, lvl = int(c["bar"][k]), float(c["entry"][k])
        hit = np.flatnonzero(book.L[i + 1 : n] <= USER_TARGET[name])
        th = i + 1 + int(hit[0]) if len(hit) else None
        end = th if th is not None else n - 1
        j1 = _first(sd.sos_bars, i)
        s1 = _first(sd.sweep_bars["primary"], i)
        s1 = s1 if s1 is not None and s1 <= end else None
        j2 = _first(sd.sos_bars, s1) if s1 is not None else None
        n_ext = int(((sd.sos_bars >= i) & (sd.sos_bars < end)).sum())
        n_int = int(((sd.isos_bars >= i) & (sd.isos_bars < end)).sum())

        def hrs(j):
            return f"+{(t[j] - t[i]) / 3.6e12:.1f}h"

        def sos_txt(j):
            if j is None:
                return "none"
            late = " AFTER target" if th is not None and j >= th else " before target"
            return f"{ny(index, j)[4:]} ({hrs(j)}){late}"

        on_bar = ", ".join(x for _, x, _ in sd.taken(i, i, PRIMARY, at_most=lvl)) or "no"
        s_win = ", ".join(f"{x} {hrs(j)}" for j, x, _ in sd.taken(i, end, PRIMARY)) or "no"
        tgt_txt = f"{ny(index, th)[4:]} ({hrs(th)})" if th else "not yet"
        print(
            f"  {name} | {ny(index, i)[4:]} @{lvl:.2f} | {on_bar} | {s_win} | {sos_txt(j1)} | "
            f"{sos_txt(j2) if s1 is not None else 'no S before target'} | {tgt_txt} | "
            f"{n_ext}/{n_int} | {fmt_sweeps(index, sd.taken(i, end, ANY_NAMED))}"
        )


# ─────────────────────────────── Stage B ───────────────────────────────


def _side_raw(raw: pd.DataFrame, name: str) -> pd.DataFrame:
    return raw if name == "short" else S.mirror(raw)


def dump_trades(path: Path, trades: list, index) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["side", "setup", "first_touch_ny", "level", "entry_ny", "entry", "stop",
                    "target", "rr", "outcome", "r", "exit_ny", "risk_atr", "sweeps"])  # fmt: skip
        for t in trades:
            sd = t["side"]
            lvl = sd.sign(float(sd.st.c["entry"][t["k"]]))
            w.writerow([
                sd.name, t["setup"], ny(index, t["stab"]), f"{lvl:.2f}", ny(index, t["bar"]),
                f"{sd.sign(t['entry']):.2f}", f"{sd.sign(t['stop']):.2f}",
                f"{sd.sign(t['target']):.2f}", f"{t['rr']:.2f}", t["outcome"], f"{t['r']:+.3f}",
                ny(index, t["xbar"]), f"{t['risk_atr']:.2f}", fmt_sweeps(index, t["sweeps"]),
            ])  # fmt: skip


def declared(sides: dict, raw: pd.DataFrame, tf: int, out: Path) -> None:
    n_full = len(raw)
    cut = int(raw.index.searchsorted(RECENT))
    exp_books = {nm: S.Book(_side_raw(raw, nm).iloc[:cut], nm, 0.0) for nm in sides}
    full_books = {nm: sides[nm].st.book for nm in sides}
    by_dir = {"both": ["short", "long"], "short": ["short"], "long": ["long"]}
    rows_out, verdicts = [], []
    for window in ("explore", "recent"):
        if window == "explore":
            books, n_end, split, lo = exp_books, cut, cut // 2, 60
            months = (raw.index[cut - 1] - raw.index[0]).days / 30.44
            print(
                f"\n{tf}m EXTERNAL — EXPLORE {raw.index[0]:%Y-%m-%d} -> {raw.index[cut - 1]:%Y-%m-%d}"
                f" — THE GATE (>= {MIN_PER_HALF} a half, both halves > 0, t >= {T_BAR}, "
                f"z >= {Z_BAR:g}); halves split at {raw.index[split]:%Y-%m-%d}"
            )
        else:
            books, n_end, split, lo = full_books, n_full, cut + (n_full - cut) // 2, cut
            months = (raw.index[-1] - raw.index[cut]).days / 30.44
            print(
                f"\n{tf}m EXTERNAL — RECENT {raw.index[cut]:%Y-%m-%d} -> {raw.index[-1]:%Y-%m-%d} — "
                f"NOT A GATE: already used for one Loaded Level test and contains the user's own "
                f"trades; halves split at {raw.index[split]:%Y-%m-%d}"
            )
        for d in ("both", "short", "long"):
            tag = "  <- the declared cells" if d == "both" else "  (reported only)"
            print(f"\n  direction {d}{tag}\n  {HEAD}")
            modes = [("primary", True), (None, False)] + ([("any", True)] if d == "both" else [])
            for cell in CELLS:
                for s_mode, s_flag in modes:
                    if s_flag != cell["s"]:
                        continue
                    group = [sides[x] for x in by_dir[d]]
                    trades, open_n = run_cell(group, cell, books, n_end, s_mode)
                    if window == "recent":
                        trades = [x for x in trades if x["bar"] >= cut]
                    sc = score(trades, books, split, months, lo)
                    name = cell_name(cell, s_mode)
                    is_declared = d == "both" and s_mode != "any"
                    line = fmt(name, sc, open_n)
                    if is_declared:
                        slug = name.replace(" ", "_")
                        dump_trades(out / f"trades_{tf}m_{window}_{slug}.csv", trades, raw.index)
                        if window == "explore":
                            v = gate(sc)
                            verdicts.append((name, v))
                            line += f"  {v}"
                    elif s_mode == "any":
                        line += "  (secondary S, not gated)"
                    print("  " + line)
                    rows_out.append(dict(tf=tf, scale="external", window=window, direction=d,
                                         cell=name, declared=is_declared, open_excluded=open_n,
                                         **sc))  # fmt: skip
    path = out / f"cells_{tf}m_external.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0]))
        w.writeheader()
        w.writerows(rows_out)
    print(f"\nGATE VERDICT ({tf}m external, explore, direction both, cost-free, t >= {T_BAR}):")
    for name, v in verdicts:
        print(f"  {name:<26} {v}")
    passed = [nm for nm, v in verdicts if v == "PASS"]
    print(
        f"  -> {len(passed)} of {len(verdicts)} cells pass"
        + (f": {', '.join(passed)} — STOP, run it nowhere else" if passed else "")
    )
    print(f"wrote {path.relative_to(S.ROOT)} and the per-trade files beside it")


# ─────────────────────────────── Stage C ───────────────────────────────


def review(sides: dict, raw: pd.DataFrame, tf: int, out: Path) -> None:
    index, n = raw.index, len(raw)
    lo_bar = int(index.searchsorted(REVIEW_FROM))
    sd_s = sides["short"]
    user_k = {}
    for name, top_px, fill, entry in TRADES:
        k, _ = find_trade(sd_s, index, name, top_px, fill, entry)
        if k is not None:
            user_k.setdefault(k, name)
    user_setups = {int(sd_s.st.c["setup"][k]): nm for k, nm in user_k.items()}
    books = {nm: sides[nm].st.book for nm in sides}
    slot = {}
    for cell in CELLS:
        if cell["target"] == "named" and cell["s"]:
            trades, _ = run_cell(list(sides.values()), cell, books, n, "primary")
            slot[cell["entry"]] = {
                (x["side"].name, x["ebar"], round(x["entry"], 2)) for x in trades
            }
    found = {}  # (side, agg key, con key) -> row, kept for the most recent top
    for sd in sides.values():
        ks, stop, tgt = candidates(sd, "named", n)
        c = sd.st.c
        firsts: dict = {}
        for k in ks:
            sid = int(c["setup"][k])
            for kind in ("AGG", "CON"):
                if (sid, kind) in firsts:
                    continue
                st_k, tg_k = float(stop[k]), float(tgt[k])
                e = (
                    agg_entry(sd, k, st_k, tg_k, "primary")
                    if kind == "AGG"
                    else con_entry(sd, k, st_k, tg_k, "primary", n)
                )
                if e is not None:
                    firsts[(sid, kind)] = (e["ebar"], int(k))
        listed = {}
        for (sid, kind), (ebar, k) in firsts.items():
            if ebar >= lo_bar:
                listed.setdefault(k, set()).add(kind)
        extra = {k for k in user_k if sd.name == "short" and int(c["bar"][k]) >= lo_bar}
        ks_set = {int(x) for x in ks}
        for k in sorted(set(listed) | extra):
            kinds = listed.get(k, set())
            a = anatomy(sd, k)
            st_k, tg_k = float(stop[k]), float(tgt[k])
            s_here = bool(kinds) or (
                k in ks_set
                and bool(
                    agg_entry(sd, k, st_k, tg_k, "primary")
                    or con_entry(sd, k, st_k, tg_k, "primary", n)
                )
            )
            s_mode = "primary" if s_here else None  # a user trade the S rule does not list
            agg = agg_entry(sd, k, st_k, tg_k, s_mode) if (not kinds or "AGG" in kinds) else None
            con = con_entry(sd, k, st_k, tg_k, s_mode, n) if (not kinds or "CON" in kinds) else None
            sweeps = (con or agg or {}).get("sweeps", [])
            sos = con["sos"] if con else None
            first_e = min((x["ebar"] for x in (agg, con) if x), default=a["stab_bar"])
            same = user_setups.get(a["setup"]) if sd.name == "short" else None
            lvl, a_k = float(c["entry"][k]), float(c["atr"][k])
            if kinds:
                status = "S met"
            elif k not in ks_set:
                status = (
                    f"user trade NOT SIZED: stop {(st_k - lvl) / a_k:.1f} ATR (need 2), top-to-4 "
                    f"{sd.st.range_atr[k]:.1f} ATR (need 10), R:R {(lvl - tg_k) / (st_k - lvl):.2f} "
                    f"(need 1), inducement {bool(c['induced'][k])}; entries shown ignore S"
                )
            elif s_here:
                status = "user trade: S met here, but its setup's first S entry is another row"
            else:
                status = "user trade: NO SWEEP in the window; entries shown ignore S"
            user = user_k.get(k, "") if sd.name == "short" else ""
            hi_end = sos if sos is not None else a["stab_bar"]
            extreme = sd.sign(float(sd.st.book.H[a["stab_bar"] : hi_end + 1].max()))
            row = {
                "first_entry_ny": ny(index, first_e), "direction": sd.name,
                "user_trade": user or (f"same setup as {same}" if same else ""),
                "status": status,
                "1_top": f"{a['top']:.2f}", "1_time_ny": ny(index, a["top_bar"]),
                "2_level": f"{a['level']:.2f}", "2_time_ny": ny(index, a["level_bar"]),
                "3_bos_level": "" if math.isnan(a["three"]) else f"{a['three']:.2f}",
                "3_broken_ny": ny(index, a["three_bar"]),
                "4_low": f"{a['four']:.2f}", "4_time_ny": ny(index, a["four_bar"]),
                "5_first_touch_ny": ny(index, a["stab_bar"]),
                "5_stab_extreme_to_entry": f"{extreme:.2f}",
                "sweeps_taken": fmt_sweeps(index, sweeps),
                "sos_time_ny": ny(index, sos),
                "sos_level": f"{sd.sign(sd.ev.sos[sos]):.2f}" if sos is not None else "",
                "agg_entry": f"{sd.sign(agg['entry']):.2f}" if agg else "",
                "agg_stop": f"{sd.sign(agg['stop']):.2f}" if agg else "",
                "con_entry": f"{sd.sign(con['entry']):.2f}" if con else "",
                "con_stop": f"{sd.sign(con['stop']):.2f}" if con else "",
                "target": f"{sd.sign(tg_k):.2f}",
                "target_is": "named low past 4" if abs(tg_k - float(c["low4"][k])) > 1e-9 else "4 (no named low in range)",
            }  # fmt: skip
            oc = {"direction": sd.name, "first_entry_ny": row["first_entry_ny"]}
            for tag, e in (("agg", agg), ("con", con)):
                res = walk(e, sd.st.book) if e else None
                if res is None:
                    oc.update({f"{tag}_outcome": "not filled" if e else "", f"{tag}_r": "",
                               f"{tag}_exit_ny": "", f"{tag}_bars": ""})  # fmt: skip
                    continue
                xbar, r, how = res
                if how == "time" and xbar == n - 1 and e["ebar"] + S.MAX_HOLD > n - 1:
                    how = "still open"
                oc.update({f"{tag}_outcome": how, f"{tag}_r": f"{r:+.2f}",
                           f"{tag}_exit_ny": ny(index, xbar), f"{tag}_bars": xbar - e["ebar"]})  # fmt: skip
            for tag, e in (("agg", agg), ("con", con)):
                key = (sd.name, e["ebar"], round(e["entry"], 2)) if e else None
                oc[f"{tag}_in_one_slot_run"] = (
                    "yes" if key in slot.get(tag.upper(), set()) else "no"
                )
            akey = (agg["ebar"], round(agg["entry"], 2)) if agg else None
            ckey = (con["ebar"], round(con["entry"], 2)) if con else None
            dkey = (sd.name, akey, ckey, bool(kinds))
            if dkey not in found or a["setup"] > found[dkey][0] or user:
                if dkey in found and found[dkey][3]["user_trade"] and not user:
                    continue
                found[dkey] = (a["setup"], first_e, sd.name, row, oc)
    rows = sorted(found.values(), key=lambda p: (p[1], p[2]))
    s_rows = [p for p in rows if p[3]["status"] == "S met"]
    u_rows = [p for p in rows if p[3]["status"] != "S met"]
    kept = s_rows[-REVIEW_CAP:]
    kept_ids = {id(p) for p in kept}
    final = [p for p in rows if id(p) in kept_ids or p in u_rows]
    blind = [{"row": j + 1, **p[3]} for j, p in enumerate(final)]
    outcomes = [{"row": j + 1, **p[4]} for j, p in enumerate(final)]
    stamp = f"external_{tf}m_{REVIEW_FROM:%Y-%m-%d}_to_{index[-1]:%m-%d}"
    for fname, data in ((f"review_{stamp}.csv", blind), (f"review_{stamp}_OUTCOMES.csv", outcomes)):
        with (out / fname).open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows(data)
        print(f"wrote {(out / fname).relative_to(S.ROOT)} ({len(data)} rows)")
    print(
        f"{len(s_rows)} S-required setups exist on {tf}m (duplicates from several tops sharing one "
        f"entry merged); kept the {len(kept)} most recent; plus {len(u_rows)} user trades the S "
        f"rule does not list"
    )
    for r in blind:
        print(
            f"  {r['row']:>3} {r['direction']:<5} {r['first_entry_ny']:<17} {r['user_trade'][:26]:<26} "
            f"AGG {r['agg_entry']:>8} CON {r['con_entry']:>8}  {r['sweeps_taken'][:50]}"
            + ("" if r["status"] == "S met" else f"  [{r['status']}]")
        )


# ─────────────────────────────── ROUND 2: sweep mandatory, confirmations, replay ───────────────

SWEEP_BEFORE_NS = 2 * 3600 * 10**9
NS_MIN = 60 * 10**9
T_BAR2 = 2.33  # 5 declared cells
ENTRY_NAMES = {
    "E0": "E0 AGG",
    "E1": "E1 CLOSE-5",
    "E2": "E2 CLOSE-15",
    "E3": "E3 SOS-1m",
    "E4": "E4 SOS-5m",
}
REPLAY_SEED = 20260916
REPLAY_N = 60
REPLAY_PER_YEAR = 10
REPLAY_YEARS = (2022, 2023, 2024, 2025)
REPLAY_BARS = 720  # bars BEFORE the decision bar; the decision bar is the 721st and last
REPLAY_GAP_DAYS = 7  # sampled decisions this far apart, so no chart shows another's outcome
USER_BUFFER_DAYS = 3


@contextmanager
def holding(bars: int):
    """`S.Book.walk` reads the module's time limit; set it for one bar size at a time."""
    old = S.MAX_HOLD
    S.MAX_HOLD = bars
    try:
        yield
    finally:
        S.MAX_HOLD = old


def _truncate(book: S.Book, n: int) -> S.Book:
    out = copy.copy(book)
    out.H, out.L, out.O, out.C, out.n = book.H[:n], book.L[:n], book.O[:n], book.C[:n], n
    return out


@dataclass
class R2:
    raw5: pd.DataFrame
    t5: np.ndarray
    sides: dict
    last15: np.ndarray  # the 5m bars that close a 15m candle (resampled UP, closed-left)
    t1: np.ndarray
    books1: dict  # side -> 1m Book on raw bars
    sos1: dict  # side -> sorted 1m bars printing an EXTERNAL bearish SOS (clean 1m bars)
    cut5: int
    cut1: int

    def axis(self, name: str):
        """(explore books, full books, explore end, hold bars) for one bar size."""
        if name == "5m":
            full = {k: v.st.book for k, v in self.sides.items()}
            cut, hold = self.cut5, 96 * 12
        else:
            full, cut, hold = self.books1, self.cut1, 96 * 60
        return {k: _truncate(v, cut) for k, v in full.items()}, full, cut, hold


def load_m1() -> pd.DataFrame:
    path = S.ROOT / "backtest" / "cache" / "PUPrime_Demo" / "XAUUSD_p__M1.csv"
    df = _read_cache_from(path, pd.Timestamp(START))[["open", "high", "low", "close"]].astype(float)
    closed = df.index + pd.Timedelta(minutes=1) <= pd.Timestamp.now("UTC").tz_localize(None)
    return df[closed]


def m1_sos(clean1: pd.DataFrame) -> np.ndarray:
    """External bearish SOS bars from the canonical structure engine on 1m bars — nothing else runs."""
    cfg = S.EngineConfig(
        fib=False, sniper=False, macro=False, internal=False, fvg=False,
        rsi=False, sessions=False, liquidity=False,
    )  # fmt: skip
    st = _BaseStack(cfg)
    return np.array(
        [b.index for b in iter_bars(clean1) if st.step(b).structure.external.bear_sos],
        dtype=np.int64,
    )


def build_r2(context: bool) -> R2:
    configure(5)
    raw5 = load("PUPrime_Demo", "XAUUSD_p", 5)
    t5 = raw5.index.asi8
    S_T["t"] = t5
    sides = build(raw5, 5, context)
    m15 = resample_up(raw5, 15, 5)
    last15 = np.searchsorted(t5, (m15.index + pd.Timedelta(minutes=15)).asi8) - 1
    if not np.allclose(raw5["close"].to_numpy()[last15], m15["close"].to_numpy()):
        sys.exit("refused: a 15m close does not equal the close of its last 5m bar")
    t0 = time.time()
    raw1 = load_m1()
    clean1, fixed = S.clean_reopens(raw1)
    books1, sos1 = {}, {}
    for name, cl, rw in (("short", clean1, raw1), ("long", S.mirror(clean1), S.mirror(raw1))):
        books1[name] = S.Book(rw, name, 0.0)
        sos1[name] = m1_sos(cl)
    t1 = raw1.index.asi8
    print(
        f"{len(raw1):,} 1m bars {raw1.index[0]} -> {raw1.index[-1]} UTC ({len(fixed)} reopen spikes "
        f"clipped for detection); 1m external bearish SOS: {len(sos1['short']):,} short-side, "
        f"{len(sos1['long']):,} long-side ({time.time() - t0:.0f}s); {len(m15):,} 15m candles"
    )
    return R2(
        raw5, t5, sides, last15.astype(np.int64), t1, books1, sos1,
        int(np.searchsorted(t5, RECENT.value)), int(np.searchsorted(t1, RECENT.value)),
    )  # fmt: skip


def _first_sweep(r: R2, sd: Side, i: int) -> int | None:
    """The first session / previous-day high taken from 2h before the touch, within 24h of it."""
    lo = int(np.searchsorted(r.t5, r.t5[i] - SWEEP_BEFORE_NS))
    s = _first(sd.sweep_bars["primary"], lo)
    return None if s is None or r.t5[s] - r.t5[i] > CON_WAIT_NS else s


def r2_entry(r: R2, code: str, sd: Side, k: int, stop_agg: float, tgt: float, n_end: int):
    """One candidate's entry under round 2's rules. Returns (entry or None, reason). `n_end` is on
    the entry's own bar axis (5m, or 1m for E3)."""
    c, b, t = sd.st.c, sd.st.book, r.t5
    i, level = int(c["bar"][k]), float(c["entry"][k])
    lo = int(np.searchsorted(t, t[i] - SWEEP_BEFORE_NS))
    if code in ("E0", "E0s"):
        sw = sd.taken(lo, i, PRIMARY, at_most=level)
        if code == "E0s":  # a high AT the level is taken only by trading through it: after the fill
            sw = [x for x in sw if x[0] < i or sd.sign(x[2]) < level - 1e-9]
        if not sw:
            return None, "no sweep at/below the level, 2h before -> touch"
        if b.H[i] < level:
            return None, "limit not filled"
        e = dict(axis="5m", ebar=i, entry=level, stop=stop_agg, target=tgt, force=False, sweeps=sw)
        return e, ""
    s = _first_sweep(r, sd, i)
    if s is None:
        return None, "no sweep, 2h before -> 24h after"
    start = max(i, s)
    if code == "E3":
        return _entry_1m(r, sd, i, s, level, stop_agg, tgt, lo, n_end)
    limit = min(n_end - 1, int(np.searchsorted(t, t[i] + CON_WAIT_NS, "right")))
    if code == "E4":
        j = _first(sd.sos_bars, start)
    elif code == "E2":
        q, j = int(np.searchsorted(r.last15, start)), None
        while q < len(r.last15) and r.last15[q] < limit:
            if b.C[r.last15[q]] < level:
                j = int(r.last15[q])
                break
            q += 1
    else:
        hit = np.flatnonzero(b.C[start:limit] < level)
        j = start + int(hit[0]) if len(hit) else None
    if j is None or j >= limit:
        return None, "no confirmation within 24h"
    hi = float(b.H[i : j + 1].max())
    if hi >= stop_agg:
        return None, "stop traded first"
    if b.L[i : j + 1].min() <= tgt:
        return None, "target traded first"
    entry, a = float(b.C[j]), float(sd.atr[j])
    stop = hi + S.BUFFER * a
    if stop - entry < CON_MIN_RISK_ATR * a:
        return None, "stop under 1 ATR"
    sw = sd.taken(lo, j, PRIMARY)
    return dict(axis="5m", ebar=j, entry=entry, stop=stop, target=tgt, force=True, sweeps=sw), ""


def _entry_1m(r, sd, i, s, level, stop_agg, tgt, lo, n_end1):
    b1, t1, t5 = r.books1[sd.name], r.t1, r.t5

    def minute(bar5: int, price: float, strict: bool) -> int | None:
        m0 = int(np.searchsorted(t1, t5[bar5]))
        m1 = int(np.searchsorted(t1, t5[bar5] + 5 * NS_MIN))
        if m1 <= m0:
            return None
        hit = np.flatnonzero(b1.H[m0:m1] > price if strict else b1.H[m0:m1] >= price)
        return m0 + int(hit[0]) if len(hit) else m1 - 1  # not found: the bar's last minute

    tm = minute(i, level, strict=False)
    if tm is None:
        return None, "no 1m bars in the touch bar"
    start = tm
    if s > i:  # the sweep came after the touch: find the minute it happened
        p = min(px for _, kind, px in sd.ev.taken[s] if kind in PRIMARY)
        sm = minute(s, p, strict=True)
        if sm is None:
            return None, "no 1m bars in the sweep bar"
        start = max(tm, sm)
    limit = min(n_end1 - 1, int(np.searchsorted(t1, t5[i] + CON_WAIT_NS, "right")))
    j = _first(r.sos1[sd.name], start)
    if j is None or j >= limit:
        return None, "no 1m SOS within 24h"
    hi = float(b1.H[tm : j + 1].max())
    if hi >= stop_agg:
        return None, "stop traded first"
    if b1.L[tm : j + 1].min() <= tgt:
        return None, "target traded first"
    a5 = int(np.searchsorted(t5, t1[j] + NS_MIN - 5 * NS_MIN, "right")) - 1  # last closed 5m bar
    entry, a = float(b1.C[j]), float(sd.atr[a5])
    stop = hi + S.BUFFER * a
    if stop - entry < CON_MIN_RISK_ATR * a:
        return None, "stop under 1 ATR"
    j5 = int(np.searchsorted(t5, t1[j], "right")) - 1
    sw = sd.taken(lo, j5, PRIMARY)
    return dict(axis="1m", ebar=j, entry=entry, stop=stop, target=tgt, force=True, sweeps=sw), ""


def r2_cell(r: R2, code: str, side_names: list, books: dict, n5: int, n_axis: int, hold: int):
    """The one-slot replay of one entry, on that entry's own bar axis."""
    rows = []
    for nm in side_names:
        sd = r.sides[nm]
        ks, stop, tgt = candidates(sd, "4", n5)
        c = sd.st.c
        for k in ks:
            e, _ = r2_entry(r, code, sd, int(k), float(stop[k]), float(tgt[k]), n_axis)
            if e is None:
                continue
            e.update(side=sd, k=int(k), setup=int(c["setup"][k]), stab=int(c["bar"][k]))
            e["atr"] = float(c["atr"][k]) if code == "E0" else _atr_at(r, sd, e)
            rows.append((e["ebar"], e["stab"], float(c["entry"][k]), -e["setup"], nm, e))
    rows.sort(key=lambda x: x[:5])
    trades, traded, free, still_open = [], set(), -1, 0
    with holding(hold):
        for ebar, *_, e in rows:
            key = (e["side"].name, e["setup"])
            if key in traded or ebar <= free:
                continue
            book = books[e["side"].name]
            res = walk(e, book)
            if res is None:
                continue
            xbar, rr_, outcome = res
            traded.add(key)
            free = xbar
            if outcome == "time" and xbar == book.n - 1 and ebar + hold > book.n - 1:
                still_open += 1
                continue
            risk = e["stop"] - e["entry"]
            trades.append(dict(
                e, bar=ebar, xbar=xbar, r=rr_, r_gross=rr_, outcome=outcome,
                rr=(e["entry"] - e["target"]) / risk, risk_atr=risk / e["atr"],
            ))  # fmt: skip
    return trades, still_open


def _atr_at(r: R2, sd: Side, e: dict) -> float:
    if e["axis"] == "5m":
        return float(sd.atr[e["ebar"]])
    return float(sd.atr[int(np.searchsorted(r.t5, r.t1[e["ebar"]] - 4 * NS_MIN, "right")) - 1])


_CAND: dict = {}


def _cand4(r: R2, sd: Side):
    """Stop and target-4 arrays for every candidate of one side (cached)."""
    if sd.name not in _CAND:
        _, stop, tgt = candidates(sd, "4", len(r.t5))
        _CAND[sd.name] = (stop, tgt)
    return _CAND[sd.name]


def standalone(r: R2, code: str, sd: Side, k: int, explore: bool, books: dict | None = None):
    """One candidate's entry and walk with no slot. Returns (entry, (xbar, R, outcome)) or reason."""
    stop, tgt = _cand4(r, sd)
    ex, full, cut, hold = r.axis("1m" if code == "E3" else "5m")
    bk = books if books is not None else (ex if explore else full)
    n_axis = cut if explore else (len(r.t1) if code == "E3" else len(r.t5))
    e, why = r2_entry(r, code, sd, k, float(stop[k]), float(tgt[k]), n_axis)
    if e is None:
        return None, why
    with holding(hold):
        res = walk(e, bk[sd.name])
        if res is None:
            return None, "not filled"
        book = bk[sd.name]
        if res[2] == "time" and res[0] == book.n - 1 and e["ebar"] + hold > book.n - 1:
            return None, "still open"
    return e, res


def entries(r: R2, out: Path) -> None:
    n5, n1 = len(r.t5), len(r.t1)
    months_ex = (r.t5[r.cut5 - 1] - r.t5[0]) / 8.64e13 / 30.44
    months_rc = (r.t5[-1] - r.t5[r.cut5]) / 8.64e13 / 30.44
    split5_ex, split5_rc = r.cut5 // 2, r.cut5 + (n5 - r.cut5) // 2
    print(
        f"\nROUND 2 — 5m setups, sweep MANDATORY (session / previous-day high, 2h before the touch "
        f"-> entry), target 4, direction both, one slot, COST-FREE. Gate: >= {MIN_PER_HALF} a half, "
        f"both halves > 0, t >= {T_BAR2}, z >= {Z_BAR:g}. Break-even win rate is trade by trade."
    )
    rows_out, e0_trades, verdicts = [], None, []
    for window in ("explore", "recent"):
        label = (
            f"EXPLORE {r.raw5.index[0]:%Y-%m-%d} -> {r.raw5.index[r.cut5 - 1]:%Y-%m-%d} — THE GATE; "
            f"halves split at {r.raw5.index[split5_ex]:%Y-%m-%d}"
            if window == "explore"
            else f"RECENT {r.raw5.index[r.cut5]:%Y-%m-%d} -> {r.raw5.index[-1]:%Y-%m-%d} — NOT A "
            f"GATE (used before, holds the user's trades); halves split at "
            f"{r.raw5.index[split5_rc]:%Y-%m-%d}"
        )
        print(f"\n{label}\n  {HEAD}")
        for code, name in ENTRY_NAMES.items():
            ax = "1m" if code == "E3" else "5m"
            ex, full, cut, hold = r.axis(ax)
            tt = r.t1 if ax == "1m" else r.t5
            if window == "explore":
                books, n5_end, n_axis, lo = ex, r.cut5, cut, 60
                split = int(np.searchsorted(tt, r.t5[split5_ex]))
            else:
                books, n5_end, n_axis, lo = full, n5, (n1 if ax == "1m" else n5), cut
                split = int(np.searchsorted(tt, r.t5[split5_rc]))
            trades, open_n = r2_cell(r, code, ["short", "long"], books, n5_end, n_axis, hold)
            if window == "recent":
                trades = [x for x in trades if x["bar"] >= cut]
            with holding(hold):
                sc = score(
                    trades, books, split, months_ex if window == "explore" else months_rc, lo
                )
            line = fmt(name, sc, open_n)
            if window == "explore":
                v = gate(sc, T_BAR2)
                verdicts.append((name, v))
                line += f"  {v}"
                if code == "E0":
                    e0_trades = trades
            print("  " + line)
            dump_r2(out / f"r2_trades_{window}_{code}.csv", trades, r)
            rows_out.append(dict(window=window, cell=name, open_excluded=open_n, **sc))
    print(
        "\nCORRECTION, not a declared cell — E0 counted a session/daily high AT the level as swept, "
        "but such a high\nis only taken by trading THROUGH the level, i.e. after the limit fills "
        "(found building the replay deck).\nE0s keeps only highs below the level, or taken on an "
        "earlier bar:"
    )
    ex, full, cut, hold = r.axis("5m")
    for window, books, n_end, lo, split, months in (
        ("explore", ex, r.cut5, 60, split5_ex, months_ex),
        ("recent", full, n5, r.cut5, split5_rc, months_rc),
    ):
        trades, open_n = r2_cell(r, "E0s", ["short", "long"], books, n_end, n_end, hold)
        if window == "recent":
            trades = [x for x in trades if x["bar"] >= r.cut5]
        with holding(hold):
            sc = score(trades, books, split, months, lo)
        tail = f"  {gate(sc, T_BAR2)}" if window == "explore" else "  (not a gate)"
        print("  " + fmt(f"E0s ({window})", sc, open_n) + tail)
        dump_r2(out / f"r2_trades_{window}_E0s.csv", trades, r)
        rows_out.append(
            dict(window=window, cell="E0s AGG strict (correction)", open_excluded=open_n, **sc)
        )
    with (out / "r2_cells.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0]))
        w.writeheader()
        w.writerows(rows_out)
    flag = np.array([
        not any(x[0] < t["stab"] or t["side"].sign(x[2]) < float(t["side"].st.c["entry"][t["k"]]) - 1e-9
                for x in t["sweeps"])
        for t in e0_trades
    ])  # fmt: skip
    rr0 = np.array([t["r"] for t in e0_trades])
    print(
        f"  E0's {len(e0_trades)} explore trades: {int(flag.sum())} had only an at-the-level sweep "
        f"(avg R {rr0[flag].mean():+.3f}); the other {int((~flag).sum())} avg R {rr0[~flag].mean():+.3f}"
    )
    print(f"\nGATE VERDICT (explore, cost-free, t >= {T_BAR2}):")
    for name, v in verdicts:
        print(f"  {name:<14} {v}")
    print(f"  -> {sum(v == 'PASS' for _, v in verdicts)} of {len(verdicts)} cells pass")
    selection(r, e0_trades)


def _ny_ns(x: int) -> str:
    return pd.Timestamp(int(x)).tz_localize("UTC").tz_convert(S.NY).strftime("%Y-%m-%d %H:%M")


def dump_r2(path: Path, trades: list, r: R2) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["side", "setup", "touch_ny", "level", "entry_ny", "entry", "stop", "target",
                    "rr", "outcome", "r", "exit_ny", "risk_atr", "sweeps"])  # fmt: skip
        for t in trades:
            sd, tt = t["side"], (r.t1 if t["axis"] == "1m" else r.t5)
            w.writerow([
                sd.name, t["setup"], _ny_ns(r.t5[t["stab"]]),
                f"{sd.sign(float(sd.st.c['entry'][t['k']])):.2f}", _ny_ns(tt[t["bar"]]),
                f"{sd.sign(t['entry']):.2f}", f"{sd.sign(t['stop']):.2f}",
                f"{sd.sign(t['target']):.2f}", f"{t['rr']:.2f}", t["outcome"], f"{t['r']:+.3f}",
                _ny_ns(tt[t["xbar"]]), f"{t['risk_atr']:.2f}", fmt_sweeps(r.raw5.index, t["sweeps"]),
            ])  # fmt: skip


def selection(r: R2, e0_trades: list) -> None:
    """Does a confirmation PICK better setups, or only move the entry? Over E0's own explore
    trades: does each confirmation fire on the SAME stab (no slot), and how did E0 do on the
    stabs it keeps against the ones it drops?"""
    print(
        f"\nSELECTION CHECK — E0's {len(e0_trades)} explore trades. 'kept' = the confirmation fires "
        f"on that same stab (standalone, no slot)."
    )
    print(
        f"  {'entry':<12} {'kept':>5} {'E0 on kept: win / avgR / tot':>30} "
        f"{'E0 on dropped: win / avgR / tot':>33} {'entry on kept: win / avgR / tot':>33}"
    )
    e0r = np.array([t["r"] for t in e0_trades])
    e0w = np.array([t["outcome"] == "target" for t in e0_trades])
    why_all = {}
    for code in ("E1", "E2", "E3", "E4"):
        keep, rr_, why = [], [], []
        for t in e0_trades:
            e, res = standalone(r, code, t["side"], t["k"], explore=True)
            keep.append(e is not None)
            why.append("" if e is not None else res)
            if e is not None:
                rr_.append((res[1], res[2] == "target"))
        why_all[code] = why
        keep = np.array(keep)
        er = np.array([x[0] for x in rr_])
        ew = np.array([x[1] for x in rr_])

        def trio(w, x):
            return f"{w.mean() * 100:5.1f}% / {x.mean():+.3f} / {x.sum():+6.1f}" if len(x) else "-"

        print(
            f"  {ENTRY_NAMES[code]:<12} {int(keep.sum()):>5} {trio(e0w[keep], e0r[keep]):>30} "
            f"{trio(e0w[~keep], e0r[~keep]):>33} {trio(ew, er):>33}"
        )
    print(
        "  ⚠ 'kept' needs the confirmation to come BEFORE E0's stop or target traded, so the kept set\n"
        "    is chosen by what price did AFTER E0's fill. E0's R on it is conditioned on the future;\n"
        "    only the entry's own R on kept is a tradeable number. Why E0's trades were dropped:"
    )
    for code, why in why_all.items():
        parts = []
        for reason in sorted({w for w in why if w}):
            m = np.array([w == reason for w in why])
            parts.append(f"{reason}: {int(m.sum())} (E0 {e0r[m].mean():+.2f}R)")
        print(f"    {ENTRY_NAMES[code]:<12} " + "; ".join(parts))


def recall2(r: R2) -> None:
    sd, index = r.sides["short"], r.raw5.index
    c = sd.st.c
    ks_all = set(int(x) for x in candidates(sd, "4", len(r.t5))[0])
    print(
        "\nRECALL (round 2) — the user's 9 trades on 5m. Sweep = session / previous-day high, 2h "
        "before the touch -> entry (aggressive: -> touch, at/below the level). Target 4, no slot."
    )
    print(
        "  trade | touch @level | sized | E0 sweep | first sweep in window | E0 | E1 | E2 | E3 | E4"
    )
    for name, top_px, fill, entry in TRADES:
        k, why = find_trade(sd, index, name, top_px, fill, entry)
        if k is None:
            print(f"  {name} | not found: {why}")
            continue
        i = int(c["bar"][k])
        lo = int(np.searchsorted(r.t5, r.t5[i] - SWEEP_BEFORE_NS))
        e0s = sd.taken(lo, i, PRIMARY, at_most=float(c["entry"][k]))
        s = _first_sweep(r, sd, i)
        first = "none"
        if s is not None:
            nm = [x for j, x, _ in sd.taken(s, s, PRIMARY)]
            first = f"{', '.join(nm)} {(r.t5[s] - r.t5[i]) / 3.6e12:+.1f}h"
        cells = []
        for code in ENTRY_NAMES:
            e, res = standalone(r, code, sd, k, explore=False)
            if e is None:
                cells.append(f"- ({res})")
                continue
            tt = r.t1 if e["axis"] == "1m" else r.t5
            cells.append(
                f"{sd.sign(e['entry']):.2f} {(tt[e['ebar']] - r.t5[i]) / 3.6e12:+.1f}h "
                f"{res[2]} {res[1]:+.2f}R"
            )
        print(
            f"  {name} | {ny(index, i)[4:]} @{float(c['entry'][k]):.2f} | "
            f"{'yes' if k in ks_all else 'NO'} | "
            f"{', '.join(f'{x} {(r.t5[j] - r.t5[i]) / 6e10:+.0f}min' for j, x, _ in e0s) or 'none'} | "
            f"{first} | " + " | ".join(cells)
        )


# ─────────────────────────────── the blind replay ───────────────────────────────


def _ts(r: R2, i: int) -> int:
    return int(r.t5[i] // 10**9)


def _p(x: float) -> float:
    return round(float(x), 2)


def replay(r: R2, out: Path) -> None:
    rng = np.random.default_rng(REPLAY_SEED)
    real = r.sides["short"]
    idx_ny = r.raw5.index.tz_localize("UTC").tz_convert(S.NY)
    user_t = [pd.Timestamp(f).value for _, _, f, _ in TRADES]
    lo_t = pd.Timestamp(f"{REPLAY_YEARS[0]}-01-01", tz=S.NY).value
    hi_t = pd.Timestamp(f"{REPLAY_YEARS[-1] + 1}-01-01", tz=S.NY).value
    hi_t = min(hi_t, pd.Timestamp("2025-09-01", tz=S.NY).value)
    pool, out_of_window = {}, 0
    for nm in ("short", "long"):
        sd = r.sides[nm]
        ks, stop, tgt = candidates(sd, "4", r.cut5)
        c, seen = sd.st.c, set()
        for k in ks:
            k, sid, i = int(k), int(c["setup"][k]), int(c["bar"][k])
            if sid in seen or not (lo_t <= r.t5[i] < hi_t):
                continue
            e, _ = r2_entry(r, "E0", sd, k, float(stop[k]), float(tgt[k]), r.cut5)
            if e is None:
                continue
            seen.add(sid)
            if any(abs(r.t5[i] - u) < USER_BUFFER_DAYS * 8.64e13 for u in user_t):
                continue
            a = anatomy(sd, k)
            if min(a["top_bar"], a["level_bar"], a["four_bar"]) < i - REPLAY_BARS:
                out_of_window += 1
                continue
            key = (nm, i)
            if key not in pool or sid > pool[key][1]:
                pool[key] = (nm, sid, k, i, e)
    items = sorted(pool.values(), key=lambda x: (x[3], x[0]))
    known = {"short": 0, "long": 0}
    for nm, sid, k, i, e in items:
        lvl = float(r.sides[nm].st.c["entry"][k])
        sign = r.sides[nm].sign
        known[nm] += any(x[0] < i or sign(x[2]) < lvl - 1e-9 for x in e["sweeps"])
    print(
        f"\nREPLAY POOL by direction: {sum(x[0] == 'short' for x in items)} short / "
        f"{sum(x[0] == 'long' for x in items)} long; with a sweep KNOWN by the touch "
        f"(below the level, or on an earlier bar): {known['short']} short / {known['long']} long"
    )
    print(
        f"\nREPLAY POOL: {len(items)} sweep-required 5m setups (first qualifying stab per setup, one "
        f"per bar and direction) {REPLAY_YEARS[0]}-01-01 -> 2025-08-31 NY; {out_of_window} more "
        f"dropped because 1, 2 or 4 lies outside the {REPLAY_BARS}-bar window"
    )

    def ok(it, against) -> bool:
        return all(abs(r.t5[it[3]] - r.t5[x[3]]) >= REPLAY_GAP_DAYS * 8.64e13 for x in against)

    # The seeded draw. Each stream remembers where it stopped, so a setup that has to be replaced
    # is replaced by the NEXT item of the same stream — no new random numbers, nothing else moves.
    chosen, streams = [], {}
    for y in REPLAY_YEARS:
        year = [it for it in items if idx_ny[it[3]].year == y]
        perm, pos, got = rng.permutation(len(year)), 0, 0
        while pos < len(perm) and got < REPLAY_PER_YEAR:
            q, pos = perm[pos], pos + 1
            if ok(year[q], chosen):
                chosen.append(year[q])
                got += 1
        streams[y] = [year, perm, pos]
    rest = [it for it in items if it not in chosen]
    perm, pos = rng.permutation(len(rest)), 0
    while pos < len(perm) and len(chosen) < REPLAY_N:
        q, pos = perm[pos], pos + 1
        if ok(rest[q], chosen):
            chosen.append(rest[q])
    streams["rest"] = [rest, perm, pos]
    order = rng.permutation(len(chosen))

    counts = dict(swings=0, breaks=0, taken_weekly=0, taken_after_touch=0, sweep_moved=0,
                  gap_open=0, m1_never_reached=0, reopen_bar=0)  # fmt: skip
    slots: dict = {}  # id number -> (item, deck)
    lost = []
    for n_id, q in enumerate(order, start=1):
        it = chosen[q]
        deck = _deck(r, real, it, f"R{n_id:02d}")
        if deck is None:
            lost.append((n_id, it))
        slots[n_id] = (it, deck)
    replaced = []
    for n_id, it in lost:
        current = [v[0] for v in slots.values() if v[1] is not None]
        y = idx_ny[it[3]].year
        in_year = sum(idx_ny[x[3]].year == y for x in current)
        order_of_streams = [y, "rest"] if in_year < REPLAY_PER_YEAR else ["rest", y]
        found = None
        for key in order_of_streams:
            pool_s, perm_s, pos_s = streams[key]
            while pos_s < len(perm_s):
                cand = pool_s[perm_s[pos_s]]
                pos_s += 1
                if cand in current or any(cand is x for _, x in lost) or not ok(cand, current):
                    continue
                deck = _deck(r, real, cand, f"R{n_id:02d}")
                if deck is not None:
                    found = (cand, deck)
                    break
            streams[key][2] = pos_s
            if found:
                break
        if found is None:
            sys.exit(f"refused: no replacement left for R{n_id:02d}")
        slots[n_id] = found
        replaced.append((n_id, it, found[0], key))
    setups, outcomes = [], []
    for n_id in sorted(slots):
        (nm, sid, k, i, e), deck = slots[n_id]
        for kk, v in deck.pop("_counts").items():
            counts[kk] += v
        setups.append(deck)
        outcomes.append(_replay_outcome(r, r.sides[nm], deck["id"], k, i, e))
    print(
        "DECISION BAR CUT AT THE TOUCH (PU Prime M1): removed from the decision bar — "
        f"{counts['swings']} swing labels, {counts['breaks']} breaks, "
        f"{counts['taken_weekly']} weekly 'taken' stamps (a close rule, unknowable at the touch), "
        f"{counts['taken_after_touch']} session/daily 'taken' stamps the M1 path had not reached "
        f"by the touch (those levels stay, as live); sweep moved to an earlier known one on "
        f"{counts['sweep_moved']} setups\n"
        f"  gap opens beyond the level: {counts['gap_open']}; 1m never reached the level: "
        f"{counts['m1_never_reached']}; decision bar is a clipped reopen bar: {counts['reopen_bar']}; "
        f"the touch minute is drawn as [its open, the level] only"
    )
    for n_id, old, new, key in replaced:
        print(
            f"  R{n_id:02d} LOST its sweep ({old[0]} {ny(r.raw5.index, old[3])}: its only sweep is taken "
            f"after the touch) -> replaced by {new[0]} {ny(r.raw5.index, new[3])} "
            f"(next draw of stream {key})"
        )
    if not replaced:
        print("  no setup lost its sweep")
    doc = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tf": "5m",
        "symbol": "XAUUSD.p PU Prime",
        "tz": "America/New_York",
        "setups": setups,
    }
    folder = out / "replay"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "replay_setups.json"
    path.write_text(json.dumps(doc, separators=(",", ":")))
    opath = folder / "replay_outcomes.csv"
    before = {}
    if opath.exists():
        for line in opath.read_text().splitlines()[1:]:
            before[line.split(",", 1)[0]] = line
    with opath.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(outcomes[0]))
        w.writeheader()
        w.writerows(outcomes)
    if before:
        after = {ln.split(",", 1)[0]: ln for ln in opath.read_text().splitlines()[1:]}
        changed = sorted(x for x in after if before.get(x) != after[x])
        print(
            f"OUTCOMES vs the previous file: {len(after) - len(changed)} of {len(after)} rows "
            f"byte-identical; changed: {changed or 'none'}"
        )
    validate(path, r)


def _cut_bar(r: R2, i: int, short: bool, level: float):
    """The decision bar cut at the touch: raw PU Prime M1 bars from the bar's open through the first
    minute that reaches the level, that minute's far side clipped to the level, close = level.
    Returns (bar, clipped minute highs, clipped minute lows, flags)."""
    b = r.books1["short"]  # real, raw 1m
    m0 = int(np.searchsorted(r.t1, r.t5[i]))
    m1 = int(np.searchsorted(r.t1, r.t5[i] + 5 * NS_MIN))
    if m1 <= m0:
        return None
    reach = b.H[m0:m1] >= level if short else b.L[m0:m1] <= level
    hit = np.flatnonzero(reach)
    flags = {"m1_never_reached": int(not len(hit))}
    tm = m0 + (int(hit[0]) if len(hit) else m1 - m0 - 1)
    hs, ls = b.H[m0 : tm + 1].copy(), b.L[m0 : tm + 1].copy()
    # In the touch minute only its open and the trade at the level are known to have happened
    # by the touch: that minute spans exactly [open, level]. Earlier minutes are whole.
    otm = float(b.O[tm])
    if short:
        hs[-1], ls[-1] = level, otm
    else:
        ls[-1], hs[-1] = level, otm
    o = float(b.O[m0])
    hi, lo = max(float(hs.max()), o), min(float(ls.min()), o)
    flags["gap_open"] = int(o > level if short else o < level)
    bar = [int(r.t5[i] // 10**9), _p(o), _p(hi), _p(lo), _p(level)]
    return bar, hs, ls, flags


def _deck(r: R2, real: Side, it, rid: str):
    nm, sid, k, i, e = it
    sd = r.sides[nm]
    short = nm == "short"
    level = sd.sign(e["entry"])
    cut = _cut_bar(r, i, short, level)
    if cut is None:
        return None
    bar, hs, ls, flags = cut

    def taken_by_touch(px: float, high: bool) -> bool:
        return bool((hs > px).any()) if high else bool((ls < px).any())

    known = [(j, n_, px) for j, n_, px in e["sweeps"] if j < i or taken_by_touch(px, high=short)]
    if not known:
        return None
    deck = _replay_setup(r, real, sd, rid, k, i, e, bar, taken_by_touch, known[-1])
    deck["_counts"]["sweep_moved"] = int(known[-1] != e["sweeps"][-1])
    deck["_counts"].update(flags)
    deck["_counts"]["reopen_bar"] = int(_clean_bars(r)[i][1:] != _raw_bar(r, i))
    return deck


def _raw_bar(r: R2, i: int) -> list:
    return [_p(x) for x in r.raw5.iloc[i][["open", "high", "low", "close"]]]


def _replay_setup(r, real, sd, rid, k, i, e, last_bar, taken_by_touch, sweep) -> dict:
    a0 = i - REPLAY_BARS
    bars = _clean_bars(r)[a0:i] + [last_bar]
    a = anatomy(sd, k)
    counts = dict(swings=0, breaks=0, taken_weekly=0, taken_after_touch=0)

    def mark(bar, px):
        return None if bar < 0 or bar < a0 or math.isnan(px) else {"t": _ts(r, bar), "p": _p(px)}

    swings = []
    for known, at, px, lab, sc in real.ev.swings:
        if a0 <= at and known <= i:
            if known == i:  # reported at the decision bar's close: after the touch
                counts["swings"] += 1
                continue
            swings.append({"t": _ts(r, at), "p": _p(px), "label": lab, "scale": sc})
    breaks = []
    for bar, loc, px, lab, d, sc in real.ev.breaks:
        if a0 <= bar <= i:
            if bar == i:
                counts["breaks"] += 1
                continue
            breaks.append({"t": _ts(r, bar), "t_from": _ts(r, loc), "p": _p(px), "label": lab,
                           "dir": d, "scale": sc})  # fmt: skip
    levels = []
    for name, px, made, taken, evicted in real.ev.levels.values():
        if made > i:
            continue
        if taken == i:
            high = name in ("PDH", "PWH") or name.endswith(" H")
            if name in ("PWH", "PWL"):
                counts["taken_weekly"] += 1
                taken = None
            elif not taken_by_touch(px, high=high):
                counts["taken_after_touch"] += 1
                taken = None
        taken_in = taken is not None and a0 <= taken <= i
        live = (taken is None or taken > i) and (evicted is None or evicted > i)
        if taken_in or live:
            levels.append({
                "name": name, "p": _p(px), "t_from": _ts(r, made),
                "t_taken": _ts(r, taken) if taken_in else None,
            })  # fmt: skip
    sj, sname, spx = sweep  # the most recent qualifying high known by the touch minute
    return {
        "id": rid,
        "direction": sd.name,
        "decision_ny": _ny_ns(r.t5[i]),
        "bars": bars,
        "marks": {
            "1": mark(a["top_bar"], a["top"]),
            "2": mark(a["level_bar"], a["level"]),
            "3": mark(a["three_low_bar"], a["three"]),
            "4": mark(a["four_bar"], a["four"]),
        },
        "swings": swings,
        "breaks": breaks,
        "levels": levels,
        "sweep": {"name": sname, "p": _p(spx), "t": _ts(r, sj)},
        "plan": {
            "entry": _p(sd.sign(e["entry"])),
            "stop": _p(sd.sign(e["stop"])),
            "target": _p(sd.sign(e["target"])),
            "rr": round((e["entry"] - e["target"]) / (e["stop"] - e["entry"]), 2),
        },
        "_counts": counts,
    }


_CLEAN5: list = []


def _clean_bars(r: R2) -> list:
    """The real 5m bars the detector saw (reopen spikes clipped), as [t, o, h, l, c]."""
    if not _CLEAN5:
        cl, _ = S.clean_reopens(r.raw5)
        ts = (r.t5 // 10**9).tolist()
        cols = [np.round(cl[x].to_numpy(), 2).tolist() for x in ("open", "high", "low", "close")]
        _CLEAN5.extend([t, o, h, lo, c] for t, o, h, lo, c in zip(ts, *cols))
    return _CLEAN5


def _replay_outcome(r: R2, sd: Side, rid: str, k: int, i: int, e: dict) -> dict:
    row = {"id": rid, "direction": sd.name, "decision_ny": _ny_ns(r.t5[i])}
    for code in ENTRY_NAMES:
        ent, res = standalone(r, code, sd, k, explore=False)
        tt = r.t1 if code == "E3" else r.t5
        if ent is None:
            row.update({f"{code}_fill": "", f"{code}_entry": "", f"{code}_stop": "",
                        f"{code}_outcome": res, f"{code}_r": "", f"{code}_exit": ""})  # fmt: skip
            continue
        row.update({
            f"{code}_fill": _ny_ns(tt[ent["ebar"]]),
            f"{code}_entry": _p(sd.sign(ent["entry"])), f"{code}_stop": _p(sd.sign(ent["stop"])),
            f"{code}_outcome": res[2], f"{code}_r": round(float(res[1]), 3),
            f"{code}_exit": _ny_ns(tt[res[0]]),
        })  # fmt: skip
    return row


def validate(path: Path, r: R2) -> None:
    doc = json.loads(path.read_text())
    bad, beyond = [], []
    years: dict = {}
    dirs: dict = {}
    for st in doc["setups"]:
        d = st["bars"][-1][0]
        dec = pd.Timestamp(st["decision_ny"], tz=S.NY).value // 10**9
        times = [m["t"] for m in st["marks"].values() if m]
        times += [x["t"] for x in st["swings"]]
        times += [x["t"] for x in st["breaks"]] + [x["t_from"] for x in st["breaks"]]
        times += [x["t_from"] for x in st["levels"]]
        times += [x["t_taken"] for x in st["levels"] if x["t_taken"] is not None]
        times += [st["sweep"]["t"]]
        if d != dec or max(times) > d or len(st["bars"]) != REPLAY_BARS + 1:
            bad.append(st["id"])
        _, o, h, lo, c = st["bars"][-1]
        lvl = st["plan"]["entry"]
        past = h > lvl if st["direction"] == "short" else lo < lvl
        if past or c != lvl or not (lo <= min(o, c) and h >= max(o, c)):
            beyond.append(st["id"])
        y = st["decision_ny"][:4]
        years[y] = years.get(y, 0) + 1
        dirs[st["direction"]] = dirs.get(st["direction"], 0) + 1
    no3 = sum(st["marks"]["3"] is None for st in doc["setups"])
    first = [st["decision_ny"] for st in doc["setups"][:5]]
    print(
        f"\nREPLAY FILE {path.relative_to(S.ROOT)}: {path.stat().st_size / 1e6:.2f} MB, "
        f"{len(doc['setups'])} setups, {REPLAY_BARS + 1} bars each (720 before + the decision bar CUT AT THE TOUCH)\n"
        f"  validation: {'PASS' if not bad else 'FAIL ' + ', '.join(bad)} — last bar = decision bar, "
        f"and no mark / swing / break / level / sweep time after it\n"
        f"  last bar ends at the touch (high / low not past the level, close = level, OHLC "
        f"consistent): {'PASS' if not beyond else 'FAIL ' + ', '.join(beyond)}\n"
        f"  per year {dict(sorted(years.items()))}; per direction {dirs}; mark 3 missing on {no3}\n"
        f"  first ids decide at {first} (ids are shuffled, not by date); seed {REPLAY_SEED}"
    )


# ─────────────────────────────── main ───────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Loaded Level + sweep/SOS confluence — see the docstring."
    )
    ap.add_argument("mode", choices=("fetch", "readback", "run", "review", "entries", "replay"))
    ap.add_argument("--tf", type=int, choices=(5, 3), default=5)
    ap.add_argument("--scale", choices=("external", "internal"), default="external")
    ap.add_argument("--server-dir", default="PUPrime_Demo")
    ap.add_argument("--symbol", default="XAUUSD_p")
    ap.add_argument("--end", default="2026-09-16", help="fetch: last date to pull")
    ap.add_argument("--out", default="backtest/reports/loaded_level_confluence")
    a = ap.parse_args()
    if a.mode == "fetch":
        fetch(a.end)
        return
    if a.scale == "internal":
        sys.exit(
            "refused: the internal scale needs a seam in loaded_level_study.detect (swing source "
            "as an argument, each swing's bar read from its event) — see the docstring"
        )
    out = S.ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if a.mode in ("entries", "replay"):
        r = build_r2(context=a.mode == "replay")
        if a.mode == "entries":
            recall2(r)
            entries(r, out)
        else:
            replay(r, out)
        print(f"({time.time() - t0:.0f}s)")
        return
    configure(a.tf)
    raw = load(a.server_dir, a.symbol, a.tf)
    S_T["t"] = raw.index.asi8
    sides = build(raw, a.tf)
    if a.mode == "readback":
        read_trade(sides, raw, len(raw), a.tf, READBACK[a.tf])
        recall(sides, raw, len(raw), a.tf)
    elif a.mode == "run":
        declared(sides, raw, a.tf, out)
    else:
        review(sides, raw, a.tf, out)
    print(f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
