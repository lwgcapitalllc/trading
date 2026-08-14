#!/usr/bin/env python3
"""sweep_edge.py — the sweep-and-reclaim is one trigger. Which LEVEL should it sweep?

This is a study, not a strategy. `indicators/engines/mss_sweeps_mpc.pine` arms the protected
internal swing (the iHL under a bull iBOS, the iLH above a bear iBOS) and signals when price
wicks through it and closes back. `education/learned/2026-08-11-smc-strategy-too-simple-to-
ignore-1150-trades.md` argues for the same trigger on a completely different level — the
PREVIOUS SESSION's high or low ("in London, wait for the Asian high to be taken"). Nobody
here has measured either, and no chart can settle it.

So: hold the TRIGGER fixed and vary only the LEVEL. Every family below is swept by the exact
same rule, scored the same way, against a control matched on the same three things. A
difference between two rows is then a difference in the LEVEL, which is the question.

    structure   the protected iHL/iLH a continuation break left behind — what the Pine arms
    session     a finished session's high/low   (Asia / London / NY)
    day         the previous day's high/low     (PDH / PDL)
    week        the previous week's high/low    (PWH / PWL)
    h4          the previous H4 candle's high/low — the BASELINE, not a candidate

⚠ **h4 is in here as a control, not as a proposal.** It is the cheapest, most frequently
taken level on the chart, so it is what "any old level" scores. A family that does not beat
h4 has no level edge at all, whatever it scores against the random control. `h4_sweep_profile.py`
studies the raw H4 sweep in far more depth and without the reclaim requirement — this row is
only here so the other four have something to be better than.

🔴 THE CONTROL IS THE WHOLE TOOL, and it is matched on THREE axes here rather than two.
`trigger_edge.py` matches direction and stop distance, because gold ran 1,200 -> 4,300 across
this window and a long-side "edge" is free. That is necessary and, for a SESSION study, not
sufficient: session sweeps land at specific hours, and gold does not drift uniformly around
the clock — so a control drawn from all hours would hand the session rows an edge made
entirely of what time of day it is. Every control entry here is drawn from the SAME
hour-of-day histogram as the event set it is scoring. If you add a family, its control comes
free; if you change the trigger, check this still holds.

WHAT COUNTS AS A SWEEP — one rule, applied identically to all five families:

    the level is live, and no bar has yet CLOSED through it
    this bar's wick trades through it        (low < level, or high > level)
    this bar CLOSES back on the origin side  (close > level, or close < level)

A bar that wicks through and closes through has BROKEN the level, and the level is dead —
never swept later. That makes the sweep a strictly SINGLE-BAR pattern, which is worth stating
plainly because it is not obvious: given the close-through kill, a bar that wicks through can
only resolve one of the two ways, on that same bar. It is also exactly what the Pine does.

⚠ THE ENGINES OWN THE LEVELS; THIS TOOL OWNS THE TRIGGER, and the split is deliberate.
`engines/liquidity/` decides what a level IS and when it exists — that is canonical and is not
reimplemented here. Its own mitigation rules are NOT used, because they differ per family:
day/session/H4 mitigate on a bare wick (`SWEEP_HIGH`) while week mitigates on a close-through
(`BREAK_HIGH`), so reading `ev.mitigated` would score the five families on three different
triggers and call the difference a level effect. Only `ev.created` / `ev.evicted` are read —
the lifecycle — and the trigger above is applied on top.

⚠ IT MEASURES A SKELETON. Entry at the reclaim bar's close, stop beyond the sweep wick, no
costs, no ladder, no confirmation step, no zone. The video's step 3 (drop to M1 and wait for a
change of character) and step 4 (enter from an M5 order block instead of the close) are BOTH
absent, and both would change the numbers — his own claim is that the OB entry is what turns a
1:2 trade into a 6R one. Read a row here as a prior for a LEVEL, never as a strategy's number.

⚠ NO LOOK-AHEAD, and here is why. Entry is the CLOSE of the reclaim bar. Every gate and split
below is computed from engine state on bars up to and including that close, which is state a
live bot has at that moment. `trigger_edge.py` records the trap this avoids: a filter read off
the close of the bar its LIMIT fills on selects bars that recovered by their close, and it
reported +15.9% instead of +6.8%. Nothing here fills on a limit.

⚠ Stdlib only, on purpose — no pandas, so it runs on a bare interpreter with no venv.

Usage:
    python3 backtest/tools/sweep_edge.py
    ... --families structure,session --target-r 2 --start 2020-01-01
    ... --conf-atr 0.75 --horizon 400 --out backtest/reports/sweep_edge
"""

from __future__ import annotations

import argparse
import collections
import copy
import csv
import json
import random
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engines"))

from liquidity import LiquidityEngine  # noqa: E402
from market_structure import Bar, StructureEngine  # noqa: E402
from sessions import SessionEngine  # noqa: E402

CACHE = ROOT / "backtest" / "cache"

# The cache stamps bars in true UTC from feed_version 2 onward; version 1 is the broker-local
# era. This study places every bar into a named-timezone session window, so version-1 bars
# would shift every session by the broker's offset and produce a plausible, wrong answer.
# ⚠ A FLOOR, NOT AN EQUALITY — `!= 2` bricked killzone_profile.py the day the version went to
# 3 for a reason (the volume column) that had nothing to do with time.
MIN_FEED_VERSION = 2

FAMILIES = ("structure", "session", "day", "week", "h4")

# Which liquidity `kind` feeds which family here. "pwc" is deliberately absent: the previous
# week's CLOSE is a reference price with rule NONE, not a pool of stops, and it has no side.
_KIND_TO_FAMILY = {"session": "session", "daily": "day", "weekly": "week", "h4": "h4"}


# ----------------------------------------------------------------------------- bars


@dataclass
class Row:
    i: int
    ts: int
    o: float
    h: float
    l: float
    c: float
    v: float


def load(symbol: str, tf: str) -> List[Row]:
    path = CACHE / f"{symbol}__{tf}.csv"
    meta = CACHE / f"{symbol}__{tf}.meta.json"
    if not path.exists():
        raise SystemExit(f"no cached bars at {path} — pull them with the MT5 agent first")
    if meta.exists():
        # Missing key == pre-sidecar == the version-1 era, the same default backtest/data/cache.py uses.
        version = json.loads(meta.read_text()).get("feed_version", 1)
        if version < MIN_FEED_VERSION:
            raise SystemExit(
                f"{path.name} is feed_version {version}; this study needs at least "
                f"{MIN_FEED_VERSION}, where bars are stamped in true UTC. Version-1 bars carry "
                "broker-local timestamps, so every session window here would be off by the "
                "broker's offset and every session row would be wrong. Re-pull the bars."
            )
    rows = []
    with path.open(newline="") as fh:
        for rec in csv.DictReader(fh):
            t = datetime.strptime(rec["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append(
                Row(
                    0,
                    int(t.timestamp() * 1000),
                    float(rec["open"]),
                    float(rec["high"]),
                    float(rec["low"]),
                    float(rec["close"]),
                    float(rec["volume"] or 0),
                )
            )
    return rows


def drop_coarse(rows: List[Row], tf_minutes: int) -> List[Row]:
    """Cut the coarse prefix off the front of the cache.

    The broker's deep history is stored at a coarser timeframe than the label claims — the
    XAUUSD M15 file opens with hourly bars. Walk back from the end to the last point where the
    surrounding gaps are genuinely wider than the timeframe, and start there. Same routine as
    trigger_edge.py; kept local so this tool imports nothing from a sibling tool.
    """
    start = 0
    for k in range(len(rows) - 1, 0, -1):
        if (rows[k].ts - rows[k - 1].ts) // 60000 > tf_minutes:
            window = rows[max(0, k - 200) : k]
            gaps = [(window[j].ts - window[j - 1].ts) // 60000 for j in range(1, len(window))]
            if gaps and statistics.median(gaps) > tf_minutes:
                start = k
                break
    out = rows[start:]
    for n, r in enumerate(out):
        r.i = n
    return out


def atr(rows: List[Row], length: int = 14) -> List[float]:
    out: List[float] = []
    prev = rows[0].c
    a = rows[0].h - rows[0].l
    for r in rows:
        tr = max(r.h - r.l, abs(r.h - prev), abs(r.l - prev))
        a = tr if not out else (a * (length - 1) + tr) / length
        out.append(a)
        prev = r.c
    return out


# ----------------------------------------------------------------------------- levels


@dataclass
class Live:
    """One level currently eligible to be swept, whatever family it came from.

    `sibling` is the opposite end of the same period — the Asia LOW when this is the Asia
    HIGH, created on the same bar. It is what answers the rotation question the study was
    asked ("does it come back to the other end of the range"), and it is only knowable at
    creation time, which is why it is carried here rather than looked up later.
    """

    family: str
    side: str  # "high" -> a short if swept; "low" -> a long
    name: str
    price: float
    created_i: int
    sibling: Optional[float] = None
    session_name: Optional[str] = None


@dataclass
class Signal:
    family: str
    name: str
    i: int  # the reclaim bar — entry is its close
    ts: int
    direction: int  # +1 long (swept a low), -1 short (swept a high)
    level: float
    entry: float
    stop: float
    risk_atr: float
    depth_atr: float  # how far the wick ran past the level
    age: int  # bars the level was live before it was taken

    # trend state, read at the reclaim bar's close
    ext_dir: int  # direction of the last EXTERNAL break, 0 before the first
    ext_run: int  # external continuations since the last change of character
    int_run: int  # internal continuations in the current run
    with_trend: bool

    # session context
    swept_in: str  # which session was open when the level was taken ("-" = none)
    origin: str  # which session the level came FROM ("-" for non-session families)

    # confluence: the other families with a live level on the same side within --conf-atr
    conf: frozenset = frozenset()

    # rotation targets, live at entry, in the trade's direction (None = none available)
    tgt_sibling: Optional[float] = None
    tgt_day: Optional[float] = None
    tgt_week: Optional[float] = None

    outcome: str = ""
    mfe_r: float = 0.0
    hit: Dict[str, bool] = field(default_factory=dict)


# ----------------------------------------------------------------------------- collection


def collect(
    rows: List[Row], families: List[str], conf_atr: float, mode: str = "reclaim"
) -> List[Signal]:
    """Drive the canonical engines over the bar stream and emit one Signal per swept level.

    The two structure families are tracked differently on purpose, and the asymmetry is real
    rather than an artefact: the Pine holds exactly ONE armed structure level at a time (a new
    iBOS overwrites the old one), while the liquidity engine holds many levels live at once.
    So the structure row will always carry a far smaller n than the session row, and that is a
    property of the setups, not of this harness.
    """
    st_eng = StructureEngine()
    liq = LiquidityEngine()
    sess = SessionEngine()
    a = atr(rows)

    live: Dict[int, Live] = {}  # liquidity levels, keyed by the engine's stable id
    arm: Optional[Live] = None  # the single armed structure level
    signals: List[Signal] = []

    ext_dir = 0
    ext_run = 0
    int_dir = 0
    int_run = 0

    want_liq = [f for f in families if f != "structure"]

    for r in rows:
        ev = st_eng.update(Bar(r.i, r.o, r.h, r.l, r.c))
        ext, internal = ev.external, ev.internal
        lev = liq.update(r.i, r.ts, r.h, r.l, r.c)
        sev = sess.update(r.i, r.ts, r.h, r.l)

        open_now = "-"
        if sev.in_ny:
            open_now = "NY"
        elif sev.in_london:
            open_now = "London"
        elif sev.in_asia:
            open_now = "Asia"

        # ---- levels created / removed this bar ------------------------------------
        for lvl in lev.created:
            fam = _KIND_TO_FAMILY.get(lvl.kind)
            if fam is None or fam not in want_liq or lvl.side not in ("high", "low"):
                continue
            live[lvl.id] = Live(
                family=fam,
                side=lvl.side,
                name=lvl.name,
                price=lvl.price,
                created_i=r.i,
                session_name=lvl.session_name,
            )
        # Pair each session/day/week high with its low — same kind, same creation bar. Done
        # after the whole `created` list is in, because the sibling may arrive second.
        _pair_siblings(live, lev.created, r.i)

        for lvl in lev.evicted:
            live.pop(lvl.id, None)

        # ---- the trigger, applied identically to every live level -----------------
        fired, arm = sweep_pass(
            live, arm, r, a[r.i], mode, open_now, conf_atr, ext_dir, ext_run, int_run
        )
        signals.extend(fired)

        # ---- internal run counters (the Pine's msRunDir / msRunCount) -------------
        # An iSOS is a change of character and STARTS a run at zero; each iBOS after it is one
        # continuation. Counted here because the engine does not expose a run length.
        if internal.bull_sos:
            int_dir, int_run = 1, 0
        if internal.bear_sos:
            int_dir, int_run = -1, 0
        if internal.bull_bos:
            int_run = int_run + 1 if int_dir == 1 else 1
            int_dir = 1
        if internal.bear_bos:
            int_run = int_run + 1 if int_dir == -1 else 1
            int_dir = -1

        # ---- structure disarm, then arm — the Pine's order, and it matters ---------
        # A level armed by THIS bar's iBOS must not be disarmed by the same bar's iBOS.
        if arm is not None and "structure" in families:
            against_internal = (arm.side == "low" and (internal.bear_sos or internal.bear_bos)) or (
                arm.side == "high" and (internal.bull_sos or internal.bull_bos)
            )
            against_external = (arm.side == "low" and ext.bear_sos) or (
                arm.side == "high" and ext.bull_sos
            )
            if against_internal or against_external:
                arm = None

        # The structure family's "other end" is the level the iBOS just BROKE — the iSH price
        # closed above, or the iSL it closed below. It is the far side of the leg the protected
        # swing anchors, so it is the honest analogue of a session range's opposite extreme,
        # and without it the structure row would be the only one blank in the rotation table.
        if "structure" in families:
            if internal.bull_bos and internal.demoted_low_price is not None:
                arm = Live(
                    family="structure",
                    side="low",
                    name="iHL",
                    price=internal.demoted_low_price,
                    created_i=r.i,
                    sibling=internal.bull_bos_price,
                )
            elif internal.bear_bos and internal.demoted_high_price is not None:
                arm = Live(
                    family="structure",
                    side="high",
                    name="iLH",
                    price=internal.demoted_high_price,
                    created_i=r.i,
                    sibling=internal.bear_bos_price,
                )

        # ---- external run counter --------------------------------------------------
        # ⚠ An external SOS also raises bull_bos/bear_bos in the engine, so SOS is tested FIRST
        # or every change of character would be miscounted as a continuation.
        if ext.bull_sos or ext.bear_sos:
            ext_run = 0
            ext_dir = 1 if ext.bull_sos else -1
        elif ext.bull_bos or ext.bear_bos:
            ext_run += 1
            ext_dir = 1 if ext.bull_bos else -1

    return signals


def _pair_siblings(live: Dict[int, Live], created, bar_i: int) -> None:
    """Give each high its matching low from the same period, and vice versa.

    The liquidity engine emits a period's high and low as two independent levels created on
    the same bar. The opposite end is the natural first target of a rotation, so it is bound
    here while the pair is still identifiable.
    """
    by_group: Dict[tuple, Dict[str, float]] = collections.defaultdict(dict)
    for lvl in created:
        if lvl.side in ("high", "low"):
            by_group[(lvl.kind, lvl.session_name)][lvl.side] = lvl.price
    for lv in live.values():
        if lv.created_i != bar_i:
            continue
        kind = {"session": "session", "day": "daily", "week": "weekly", "h4": "h4"}[lv.family]
        pair = by_group.get((kind, lv.session_name))
        if pair:
            lv.sibling = pair.get("low" if lv.side == "high" else "high")


def _test(lv: Live, r: Row, mode: str) -> str:
    """Sweep, break, or nothing — the one trigger, for every family.

    `reclaim` (default) is the Pine's rule and the study's headline: a wick through with a
    close back on the origin side is a SWEEP; a close through is a BREAK, and a broken level
    is dead — it is not a pool of stops any more, it is a level the market went past. Given
    the break rule, a wick bar can only resolve one of these two ways on that same bar, which
    is what makes the pattern single-bar.

    ⚠ `wick` exists because the headline comparison is otherwise CONFOUNDED. The reclaim is
    part of the trigger, not part of the level, so "structure beat session" could just as
    easily mean "the reclaim rule suits structure levels" — a different claim with a different
    fix. In `wick` mode the bare touch fires and the close is ignored, which is closer to what
    the video actually describes (it takes the level being taken, then waits for a separate
    M1 confirmation this tool does not model at all). Run both; if the ranking survives, the
    ranking is about the level.
    """
    through = (r.l < lv.price) if lv.side == "low" else (r.h > lv.price)
    if mode == "wick":
        return "sweep" if through else ""
    broke = (r.c < lv.price) if lv.side == "low" else (r.c > lv.price)
    if broke:
        return "break"
    return "sweep" if through else ""


def sweep_pass(live, arm, r, atr_here, mode, open_now, conf_atr, ext_dir, ext_run, int_run):
    """Run the trigger over every live level for ONE bar. Returns (signals, new arm).

    Mutates `live` — a level that is swept or broken is gone — and that mutation is exactly why
    this is a named function with its own test rather than a loop body.

    🔴 CONFLUENCE IS READ OFF A SNAPSHOT TAKEN BEFORE ANY LEVEL IS REMOVED, and it is not a
    detail. Several families routinely hold a level at the same price — a session low that is
    also the previous day's low is one line on the chart, not two — so on a bar that sweeps them
    all, whichever was tested first would be the only one still in `live` for the next to see.
    Scoring off the mutated dict made confluence a function of dict iteration order: measured on
    a 20k-bar slice, the four levels swept at 1192.89 reported four DIFFERENT confluence sets,
    descending as they were popped. The whole structure-vs-session-vs-both question is decided by
    that set, so the defect degraded precisely the answer the study exists to give.
    """
    snap = dict(live)
    snap_arm = arm
    fired: List[Signal] = []

    for lid, lv in snap.items():
        verdict = _test(lv, r, mode)
        if verdict in ("break", "sweep"):
            live.pop(lid, None)
        if verdict == "sweep":
            fired.append(
                _build(
                    r, atr_here, lv, snap, snap_arm, open_now, conf_atr, ext_dir, ext_run, int_run
                )
            )

    if snap_arm is not None:
        verdict = _test(snap_arm, r, mode)
        if verdict in ("break", "sweep"):
            arm = None
        if verdict == "sweep":
            fired.append(
                _build(
                    r, atr_here, snap_arm, snap, None, open_now, conf_atr, ext_dir, ext_run, int_run
                )
            )

    return fired, arm


def _build(r, atr_here, lv, live, arm, open_now, conf_atr, ext_dir, ext_run, int_run) -> Signal:
    """Turn a swept level into a Signal, with every split recorded at the reclaim bar's close.

    `live` is the pre-sweep snapshot, so a level that fired on this same bar still counts
    toward confluence — see the note in `sweep_pass`.
    """
    direction = 1 if lv.side == "low" else -1
    entry = r.c
    stop = r.l if direction == 1 else r.h
    risk = abs(entry - stop)
    depth = abs(lv.price - stop)
    tol = conf_atr * atr_here

    # Confluence — which OTHER families also hold a level at this price, same side. `arm` is
    # passed separately because the structure level is not in `live`.
    conf = {lv.family}
    for other in live.values():
        if other.side == lv.side and abs(other.price - lv.price) <= tol:
            conf.add(other.family)
    if arm is not None and arm.side == lv.side and abs(arm.price - lv.price) <= tol:
        conf.add("structure")

    # Rotation targets, in the trade's direction only — a PDH below a long's entry is not a
    # target, it is history.
    def _ahead(price: Optional[float]) -> Optional[float]:
        if price is None:
            return None
        return price if (price - entry) * direction > 0 else None

    day_side = "high" if direction == 1 else "low"
    day_prices = [x.price for x in live.values() if x.family == "day" and x.side == day_side]
    wk_prices = [x.price for x in live.values() if x.family == "week" and x.side == day_side]
    ahead_day = [p for p in day_prices if (p - entry) * direction > 0]
    ahead_wk = [p for p in wk_prices if (p - entry) * direction > 0]

    return Signal(
        family=lv.family,
        name=lv.name,
        i=r.i,
        ts=r.ts,
        direction=direction,
        level=lv.price,
        entry=entry,
        stop=stop,
        risk_atr=risk / atr_here if atr_here else 0.0,
        depth_atr=depth / atr_here if atr_here else 0.0,
        age=r.i - lv.created_i,
        ext_dir=ext_dir,
        ext_run=ext_run,
        int_run=int_run,
        with_trend=(ext_dir == direction),
        swept_in=open_now,
        origin=lv.session_name or "-",
        conf=frozenset(conf),
        tgt_sibling=_ahead(lv.sibling),
        tgt_day=min(ahead_day, key=lambda p: abs(p - entry)) if ahead_day else None,
        tgt_week=min(ahead_wk, key=lambda p: abs(p - entry)) if ahead_wk else None,
    )


# ----------------------------------------------------------------------------- scoring


def outcome_of(rows, i, direction, entry, stop, target_r, horizon) -> str:
    """+target_r before -1R, or neither inside the horizon. The tight loop, no bookkeeping.

    ⚠ When one bar holds both the stop and the target, the STOP wins — the same convention
    h4_sweep_profile.py uses. It makes every number here slightly pessimistic, which is the
    safe direction. Applied identically to signals and to controls, so the comparison between
    them is unaffected by the choice.
    """
    risk = abs(entry - stop)
    if risk <= 0:
        return "bad"
    target = entry + direction * target_r * risk
    for k in range(i + 1, min(i + 1 + horizon, len(rows))):
        bar = rows[k]
        if (bar.l <= stop) if direction == 1 else (bar.h >= stop):
            return "loss"
        if (bar.h >= target) if direction == 1 else (bar.l <= target):
            return "win"
    return "open"


def resolve(rows, sig: Signal, target_r: float, horizon: int) -> None:
    """Score one signal, and also record how far it ran and which named levels it reached.

    Everything is measured BEFORE the stop, so all three answers describe the same trade.
    """
    risk = abs(sig.entry - sig.stop)
    if risk <= 0:
        sig.outcome = "bad"
        return
    d = sig.direction
    target = sig.entry + d * target_r * risk
    named = {"sibling": sig.tgt_sibling, "day": sig.tgt_day, "week": sig.tgt_week}
    sig.hit = {k: False for k, v in named.items() if v is not None}
    sig.outcome = "open"

    for k in range(sig.i + 1, min(sig.i + 1 + horizon, len(rows))):
        bar = rows[k]
        if (bar.l <= sig.stop) if d == 1 else (bar.h >= sig.stop):
            if sig.outcome == "open":
                sig.outcome = "loss"
            return
        favour = bar.h if d == 1 else bar.l
        sig.mfe_r = max(sig.mfe_r, (favour - sig.entry) * d / risk)
        if sig.outcome == "open" and ((favour >= target) if d == 1 else (favour <= target)):
            sig.outcome = "win"
        for key, price in named.items():
            if price is not None and not sig.hit[key]:
                if (favour >= price) if d == 1 else (favour <= price):
                    sig.hit[key] = True


# The stop-distance grid the control is stratified on, in ATR(14). 0.25 is fine enough that a
# cell's entries really do share a stop distance, and coarse enough that the cells stay cheap.
_BUCKET_ATR = 0.25
_BUCKET_MAX = 40


class Control:
    """The matched control, built by POST-STRATIFICATION rather than by resampling per table.

    🔴 THIS IS THE PART THAT DECIDES WHETHER ANY NUMBER ABOVE MEANS ANYTHING. Gold ran
    1,200 -> 4,300 across this window, so a long-side "edge" is free; and session sweeps land
    at specific HOURS, and gold does not drift uniformly around the clock, so an unmatched
    control would hand the session rows an edge made entirely of what time of day it is.

    The construction: bucket the world into cells of (direction, hour-of-day, stop distance in
    0.25-ATR steps). For each cell that some event set actually needs, drop `k` random entries
    on random bars belonging to that cell and score them exactly as a signal is scored. A set's
    control win rate is then its OWN cell histogram, weighted against those cell win rates — so
    it is matched on all three axes by construction, not approximately.

    ⚠ Cells are cached and shared across every table, which is what makes ~90 control-backed
    rows affordable. Resampling 6,000 entries per row would have been ~200M bar steps.
    """

    def __init__(self, rows, target_r, horizon, k, seed):
        self.rows = rows
        self.atr = atr(rows)
        self.target_r = target_r
        self.horizon = horizon
        self.k = k
        self.seed = seed
        self.cells: Dict[tuple, tuple] = {}
        self.by_hour: Dict[int, List[int]] = collections.defaultdict(list)
        for i in range(200, len(rows) - horizon - 1):
            self.by_hour[datetime.fromtimestamp(rows[i].ts / 1000, timezone.utc).hour].append(i)

    @staticmethod
    def bucket(risk_atr: float) -> int:
        return max(1, min(_BUCKET_MAX, int(round(risk_atr / _BUCKET_ATR))))

    def cell(self, direction: int, hour: int, bucket: int) -> tuple:
        key = (direction, hour, bucket)
        if key in self.cells:
            return self.cells[key]
        pool = self.by_hour.get(hour, [])
        wins = losses = 0
        if pool:
            rnd = random.Random(hash((self.seed, direction, hour, bucket)))
            risk_atr = bucket * _BUCKET_ATR
            for _ in range(self.k):
                i = pool[rnd.randrange(len(pool))]
                entry = self.rows[i].c
                stop = entry - direction * risk_atr * self.atr[i]
                o = outcome_of(self.rows, i, direction, entry, stop, self.target_r, self.horizon)
                if o == "win":
                    wins += 1
                elif o == "loss":
                    losses += 1
        self.cells[key] = (wins, losses)
        return self.cells[key]

    def win_rate(self, sigs: List[Signal]) -> Optional[float]:
        """The control win rate for THIS event set's own direction/hour/stop histogram."""
        hist = collections.Counter()
        for s in sigs:
            hour = datetime.fromtimestamp(s.ts / 1000, timezone.utc).hour
            hist[(s.direction, hour, self.bucket(s.risk_atr))] += 1
        num = den = 0.0
        for (d, h, b), count in hist.items():
            w, l = self.cell(d, h, b)
            if w + l == 0:
                continue
            num += count * w / (w + l)
            den += count
        return num / den if den else None


# ----------------------------------------------------------------------------- report


def line(label, sigs, ctl: Optional["Control"] = None, target_r: float = 2.0):
    n = len(sigs)
    if not n:
        print(f"  {label:<38} n=0")
        return
    w = sum(1 for s in sigs if s.outcome == "win")
    lose = sum(1 for s in sigs if s.outcome == "loss")
    dec = w + lose
    wr = w / dec if dec else 0.0
    exp = (w * target_r - lose) / n
    se = (wr * (1 - wr) / dec) ** 0.5 if dec > 1 else 0.0
    med = statistics.median(s.risk_atr for s in sigs)
    tail = ""
    if ctl is not None and dec:
        cwr = ctl.win_rate(sigs)
        if cwr is not None:
            z = (wr - cwr) / se if se else 0.0
            tail = f"  ctrl={cwr:>5.1%}  edge={wr - cwr:>+6.1%} ({z:>+4.1f}s)"
    print(f"  {label:<38} n={n:>5}  WR={wr:>6.1%}  expR={exp:>+6.3f}  risk={med:>4.2f}ATR{tail}")


def _dedupe(sigs: List[Signal]) -> List[Signal]:
    """Collapse rows that are ONE trade wearing several hats.

    ⚠ The families are not disjoint samples. A session low that is also the previous day's low
    and the previous H4 low is one price on the chart, and a bar that sweeps it emits a
    separate Signal per family — which is what makes the per-family rows comparable. Any row
    that claims to be a BOOK ("take either kind") must collapse them first, or it reports the
    same trade up to five times and inflates its own n. Keyed on (bar, direction, stop), which
    is exactly what makes two rows the same trade.
    """
    seen = {}
    for s in sigs:
        seen.setdefault((s.i, s.direction, round(s.stop, 4)), s)
    return list(seen.values())


def rotation(label, sigs):
    """The question the study was actually asked: after the sweep, does it rotate?"""
    n = len(sigs)
    if not n:
        print(f"  {label:<38} n=0")
        return
    med_mfe = statistics.median(s.mfe_r for s in sigs)
    r1 = sum(1 for s in sigs if s.mfe_r >= 1) / n
    r3 = sum(1 for s in sigs if s.mfe_r >= 3) / n
    r6 = sum(1 for s in sigs if s.mfe_r >= 6) / n
    parts = []
    for key, name in (("sibling", "other end"), ("day", "prev day"), ("week", "prev week")):
        have = [s for s in sigs if key in s.hit]
        if have:
            got = sum(1 for s in have if s.hit[key]) / len(have)
            parts.append(f"{name} {got:>5.1%} (of {len(have)})")
        else:
            parts.append(f"{name}     -")
    print(
        f"  {label:<38} n={n:>5}  medMFE={med_mfe:>5.2f}R  "
        f">=1R {r1:>5.1%}  >=3R {r3:>5.1%}  >=6R {r6:>5.1%}   " + "   ".join(parts)
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="M15")
    ap.add_argument("--tf-minutes", type=int, default=15)
    ap.add_argument(
        "--families",
        default=",".join(FAMILIES),
        help="comma list of " + "/".join(FAMILIES) + " (h4 is the baseline, keep it in)",
    )
    ap.add_argument(
        "--trigger",
        default="reclaim",
        choices=("reclaim", "wick"),
        help=(
            "reclaim = wick through AND close back (the Pine's rule); wick = the bare touch, "
            "close ignored. Run both — see _test()"
        ),
    )
    ap.add_argument("--target-r", type=float, default=2.0)
    ap.add_argument("--horizon", type=int, default=400, help="bars to give the trade")
    ap.add_argument(
        "--conf-atr",
        type=float,
        default=0.5,
        help="how close two levels must be to count as confluence, in ATR(14)",
    )
    ap.add_argument(
        "--min-risk-atr",
        type=float,
        default=0.0,
        help=(
            "drop signals whose stop is tighter than this, in ATR(14). 0 = keep everything, "
            "which is the honest default for a study but NOT a strategy setting — see the "
            "warning this tool prints"
        ),
    )
    ap.add_argument(
        "--ctrl-k",
        type=int,
        default=40,
        help="random control entries per (direction, hour, stop-distance) cell",
    )
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--start", default=None, help="YYYY-MM-DD")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD")
    ap.add_argument("--out", default=None, help="write every signal to <out>.csv")
    args = ap.parse_args()

    families = [f.strip() for f in args.families.split(",") if f.strip()]
    bad = [f for f in families if f not in FAMILIES]
    if bad:
        raise SystemExit(f"unknown families {bad}; pick from {list(FAMILIES)}")

    rows = drop_coarse(load(args.symbol, args.tf), args.tf_minutes)
    print(
        f"{len(rows)} true-{args.tf} {args.symbol} bars, "
        f"{datetime.fromtimestamp(rows[0].ts / 1000, timezone.utc):%Y-%m-%d} -> "
        f"{datetime.fromtimestamp(rows[-1].ts / 1000, timezone.utc):%Y-%m-%d}"
    )
    print(
        f"trigger = {args.trigger}; scored at +{args.target_r}R before -1R within "
        f"{args.horizon} bars; breakeven WR = {1 / (1 + args.target_r):.1%}"
    )
    print(
        "control matched on direction + stop distance + hour of day, "
        f"{args.ctrl_k} entries per cell\n"
    )

    sigs = collect(rows, families, args.conf_atr, args.trigger)

    # The window filter is applied AFTER the replay, never before it: the engines need their
    # full warm-up, and a structure engine started in 2023 is not the same engine.
    lo = (
        datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if args.start
        else None
    )
    hi = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc) if args.end else None
    if lo or hi:
        keep = []
        for s in sigs:
            when = datetime.fromtimestamp(s.ts / 1000, timezone.utc)
            if lo and when < lo:
                continue
            if hi and when > hi:
                continue
            keep.append(s)
        sigs = keep
        print(f"window filter: {len(sigs)} signals kept\n")

    if args.min_risk_atr > 0:
        before = len(sigs)
        sigs = [s for s in sigs if s.risk_atr >= args.min_risk_atr]
        print(f"min-risk filter at {args.min_risk_atr} ATR: {before} -> {len(sigs)} signals\n")

    for s in sigs:
        resolve(rows, s, args.target_r, args.horizon)
    sigs = [s for s in sigs if s.outcome != "bad"]

    med_risk = statistics.median(s.risk_atr for s in sigs) if sigs else 0.0
    if med_risk < 1.0 and args.min_risk_atr == 0:
        print(
            f"⚠ median stop is {med_risk:.2f} ATR — the sweep wick is often only a few dollars "
            "wide on gold.\n"
            "  Every R below is measured against that, so spread and slippage would eat a much\n"
            "  larger share of it than of a normal trade, and none of them are modelled here.\n"
            "  Re-run with --min-risk-atr 0.5 before believing any headline R.\n"
        )

    def sub(**kw):
        out = sigs
        for k, v in kw.items():
            out = [s for s in out if getattr(s, k) == v]
        return out

    ctl = Control(rows, args.target_r, args.horizon, args.ctrl_k, args.seed)
    scored = dict(ctl=ctl, target_r=args.target_r)

    print("== 1. THE QUESTION: which level is worth sweeping? ==")
    print("   (h4 is the baseline. A family that does not beat it has no level edge.)")
    for f in families:
        line(f, sub(family=f), **scored)

    print("\n== 2. does the trend filter earn its place? ==")
    print("   with-trend = the sweep points the same way as the last EXTERNAL break")
    for f in families:
        fs = sub(family=f)
        line(f"{f}  with-trend", [s for s in fs if s.with_trend], **scored)
        line(f"{f}  against-trend", [s for s in fs if not s.with_trend], **scored)
        line(f"{f}  trending mkt (extRun>=1)", [s for s in fs if s.ext_run >= 1], **scored)

    print(f"\n== 3. structure AND session on the same price (within {args.conf_atr} ATR) ==")
    if "structure" in families and "session" in families:
        both = [s for s in sigs if {"structure", "session"} <= s.conf]
        line(
            "structure only",
            [s for s in sub(family="structure") if "session" not in s.conf],
            **scored,
        )
        line(
            "session only",
            [s for s in sub(family="session") if "structure" not in s.conf],
            **scored,
        )
        line("structure + session (either row)", _dedupe(both), **scored)
        line(
            "union: take either kind",
            _dedupe(sub(family="structure") + sub(family="session")),
            **scored,
        )
    else:
        print("  (needs both structure and session in --families)")

    print("\n== 4. the video's actual claim: previous session's high taken in the next one ==")
    print("   origin = the session the level came from; taken = the session it was swept in")
    if "session" in families:
        names = [s.name for s in SessionEngine.DEFAULT_SESSIONS]
        ss = sub(family="session")
        for origin in names:
            for taken in names:
                if origin == taken:
                    continue
                pick = [s for s in ss if s.origin == origin and s.swept_in == taken]
                if pick:
                    line(f"{origin} H/L taken in {taken}", pick, **scored)
        print("  -- and the same rows with the trend filter on --")
        for origin in names:
            for taken in names:
                if origin == taken:
                    continue
                pick = [
                    s for s in ss if s.origin == origin and s.swept_in == taken and s.with_trend
                ]
                if pick:
                    line(f"{origin} H/L in {taken}, with-trend", pick, **scored)
    else:
        print("  (needs session in --families)")

    print("\n== 5. does it rotate? how far price ran before the stop ==")
    print("   'other end' = the opposite extreme of the same period the level came from")
    for f in families:
        rotation(f, sub(family=f))
    print("  -- with-trend only --")
    for f in families:
        rotation(f"{f}  with-trend", [s for s in sub(family=f) if s.with_trend])

    print("\n== 6. by year — an edge living in one year is a curve fit ==")
    for f in families:
        years = collections.defaultdict(list)
        for s in sub(family=f):
            years[datetime.fromtimestamp(s.ts / 1000, timezone.utc).year].append(s)
        for y in sorted(years):
            line(f"{f} {y}", years[y], **scored)

    print("\n== 7. vs the R target — an edge only at one target is an artefact of that target ==")
    for rr in (1.0, 1.5, 2.0, 3.0, 5.0):
        rr_ctl = Control(rows, rr, args.horizon, args.ctrl_k, args.seed)
        print(f"  target +{rr}R  (breakeven WR {1 / (1 + rr):.1%})")
        for f in families:
            fs = [_rescored(rows, s, rr, args.horizon) for s in sub(family=f)]
            line(f"  {f}", fs, ctl=rr_ctl, target_r=rr)

    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        out = path.with_suffix(".csv")
        with out.open("w", newline="") as fh:
            wtr = csv.writer(fh)
            wtr.writerow(
                [
                    "time",
                    "family",
                    "name",
                    "direction",
                    "level",
                    "entry",
                    "stop",
                    "risk_atr",
                    "depth_atr",
                    "age_bars",
                    "ext_dir",
                    "ext_run",
                    "int_run",
                    "with_trend",
                    "origin",
                    "swept_in",
                    "confluence",
                    "outcome",
                    "mfe_r",
                    "hit_sibling",
                    "hit_day",
                    "hit_week",
                ]
            )
            for s in sigs:
                wtr.writerow(
                    [
                        f"{datetime.fromtimestamp(s.ts / 1000, timezone.utc):%Y-%m-%d %H:%M}",
                        s.family,
                        s.name,
                        s.direction,
                        f"{s.level:.2f}",
                        f"{s.entry:.2f}",
                        f"{s.stop:.2f}",
                        f"{s.risk_atr:.3f}",
                        f"{s.depth_atr:.3f}",
                        s.age,
                        s.ext_dir,
                        s.ext_run,
                        s.int_run,
                        int(s.with_trend),
                        s.origin,
                        s.swept_in,
                        "|".join(sorted(s.conf)),
                        s.outcome,
                        f"{s.mfe_r:.3f}",
                        s.hit.get("sibling", ""),
                        s.hit.get("day", ""),
                        s.hit.get("week", ""),
                    ]
                )
        print(f"\nwrote {len(sigs)} signals to {out}")


def _rescored(rows, s: Signal, target_r: float, horizon: int) -> Signal:
    """A copy of one signal scored at a different R target.

    Copied rather than mutated, so the earlier tables keep the target they were printed
    under — a table whose numbers changed after it was printed is the kind of thing nobody
    notices until the conclusion is already written down.
    """
    c = copy.copy(s)
    c.outcome = outcome_of(rows, s.i, s.direction, s.entry, s.stop, target_r, horizon)
    return c


if __name__ == "__main__":
    main()
