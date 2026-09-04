"""BosTracker — the BOS continuation state machine (Stage 0/1, the anchor fib, and death).

Ports `strategies/tradingview/bos_strategy_export.pine` lines 3446-3629 plus the session-VWAP gate
at 3800-3818. It owns everything that happens BEFORE an order is considered:

    SOS opens a regime  ->  each later BOS in that direction arms a leg
                        ->  the leg carries its own fib ladder
                        ->  the leg dies (re-anchor / opposite SOS / cycle / invalidation /
                            F4 / staleness)

`BosExecution` then reads the resulting `BosState` and decides where a limit rests. The split
is the same one `b_leg` uses, and it exists for the same reason: the tracker is where every
BOS-specific rule lives, so a bug here shows up as a wrong LEG many bars before it becomes a
wrong trade, and `compare_bos.py` diffs the tracker's own state against the export's `px_leg_*`
/ `px_ord_*` / `px_ready` columns rather than only seeing "a trade differs".

⚠ **This module needs the bar's VOLUME, and it is the only thing in the repo's strategy layer
that does.** F10 reads the SESSION VWAP, which is a volume-weighted mean, and it reads it from
the canonical `engines/vwap/` — never a private one (CLAUDE.md forbids a second implementation,
and a private VWAP anchored at the break would not be the line anyone is looking at on the
chart). A frame with no volume column therefore cannot answer the gate; see `_vwap_ok`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[3]
for _p in (str(_ROOT), str(_ROOT / "engines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from vwap import VwapEngine  # noqa: E402

# The fib ratios the anchor ladder prices. Named once so the tracker, the entry ladder and
# the target ladder cannot drift into three opinions about which rungs exist.
#   0.118 / 0.236 exist ONLY as the lower two rungs of the shallow entry tiers — no fib line
#   draws them, and the Pine computes them for exactly the same reason (lP118 / lP236).
_RATIOS = (0.0, 0.118, 0.236, 0.382, 0.5, 0.618, 0.702, 0.786, 0.886, 1.0)


def fib_price(ext: Optional[float], org: Optional[float], ratio: float) -> Optional[float]:
    """Pine `f_lvl` — one helper, both directions.

    `ext` is the leg's 0.0 (the extreme it ran to), `org` its 1.0 (where the leg started).
    Long: ext = high, org = low. Short: ext = low, org = high. This is the identical
    arithmetic the fib engine's own levels use, anchored per-setup instead of per-leg.
    """
    if ext is None or org is None:
        return None
    return ext + (org - ext) * ratio


@dataclass(frozen=True)
class BosLeg:
    """One armed break, frozen at its BOS bar.

    🔴 A DEAD LEG KEEPS ITS NUMBERS. Only `on` flips. That mirrors the Pine exactly, and it
    is not cosmetic: `bosL_high` / `bosL_low` / `bosL_bar` / `bosL_n` / `bosL_half` are all
    `var` there and are reassigned ONLY when a new break arms, so after a death the export's
    `px_l_ext` / `px_l_org` / `px_ord_l` and `lFibsReady` still carry the last leg's values.
    This class cleared them until 2026-08-07, and the first real parity run went RED on the
    first compared bar with `py=None pine=4584.26` — a divergence in every bar after the
    first dead leg.

    It is behaviour-neutral on BOTH sides, which is the only reason the stale values are
    safe: every consumer of the ladder ANDs with `on` first (`_death`, `_entry_edges`,
    `long_armed`, `_record_bos_blocks`), exactly as the Pine's do. Do NOT "tidy" this into
    clearing the fields — that reintroduces the divergence and nothing in the strategy's own
    behaviour will tell you.
    """

    on: bool = False
    high: Optional[float] = None      # the break leg's high (bull) / the leg's high (bear)
    low: Optional[float] = None
    bar: Optional[int] = None         # the bar the BOS printed — the one-trade-per-leg key
    ordinal: int = 0                  # this break's number since the SOS (1 = the expansion)
    half: bool = False                # the per-anchor 0.5 latch (see the cycle-complete death)
    why: str = ""                     # why the LAST arm died — reporting only

    def disarmed(self, why: str) -> "BosLeg":
        """This leg with the FLAG off and every number kept — the Pine's `bosL_on := false`."""
        return replace(self, on=False, why=why)


@dataclass(frozen=True)
class BosState:
    """The tracker's per-bar output — one side each, plus the bar-level gates.

    REPORTING plus DECISION: `BosExecution` reads the legs, the ladders and `vwap_block_*`;
    `compare_bos.py` diffs the lot. `regime_*` / `count_*` are reporting only.
    """

    index: int
    regime_l: bool = False
    regime_s: bool = False
    count_l: int = 0                  # BOS ordinal reached on this side since the SOS
    count_s: int = 0
    traded_l: int = 0                 # filled trades this regime (F6)
    traded_s: int = 0
    long: BosLeg = BosLeg()
    short: BosLeg = BosLeg()
    # The anchor ladder, ratio -> price, for whichever leg is armed. Empty when none is.
    l_levels: dict = None
    s_levels: dict = None
    l_ready: bool = False             # Pine lFibsReady
    s_ready: bool = False
    l_top: Optional[float] = None     # the band's SHALLOW end (fib 0.5, or 0.382 if opened)
    s_top: Optional[float] = None
    vwap: Optional[float] = None
    vwap_block_l: bool = False        # F10 — price is not closing on the trend's own side
    vwap_block_s: bool = False
    fired_l: bool = False             # a BOS printed on this bar (reporting: the [BOS] log line)
    fired_s: bool = False

    def __post_init__(self) -> None:
        if self.l_levels is None:
            object.__setattr__(self, "l_levels", {})
        if self.s_levels is None:
            object.__setattr__(self, "s_levels", {})


class VolumeUnavailable(RuntimeError):
    """The session-VWAP filter is on and the bar stream carries no volume.

    Raised rather than answered, because the two available wrong answers are both bad and
    neither announces itself: block every setup (a silent zero-trade book that reads exactly
    like a strategy with no signals) or pass every setup (a filter that is on, reported as on,
    and doing nothing). The Pine cannot hit this — TradingView always has tick volume on
    XAUUSD — so there is no Pine behaviour to mirror, and refusing is the honest third answer.
    """


class BosTracker:
    """Stage 0/1 + the anchor fib + death. One instance per run; feed it every bar in order."""

    def __init__(self, config, tf_seconds: int = 900) -> None:
        self._cfg = config
        self._tf_seconds = max(1, int(tf_seconds))
        self._vwap = VwapEngine()
        # Mutable mirrors of the Pine's `var` block (3446-3456).
        self._reg_l = False
        self._reg_s = False
        self._cnt_l = 0
        self._cnt_s = 0
        self._trd_l = 0
        self._trd_s = 0
        self._leg_l = BosLeg()
        self._leg_s = BosLeg()

    # ── the staleness cap, in BARS ───────────────────────────────────────────────
    @property
    def max_bars(self) -> int:
        """Pine `BOS_MAX` — `bosMaxDays` converted to bars at this timeframe.

        Counted in bars rather than clock time on purpose (the Pine tooltip says so): weekends
        and the daily close do not use the allowance up, so a leg armed on a Friday still gets
        its full window on Monday.
        """
        return max(1, round(self._cfg.bos_max_days * 86400 / self._tf_seconds))

    # ── the one thing the execution layer writes back ────────────────────────────
    def record_fill(self, direction: int) -> None:
        """A trade opened — bump this regime's F6 counter (Pine `bosTrdL := bosTrdL + 1`).

        Called by `BosExecution._open_position`. It lives here rather than in the execution
        layer because the counter is a property of the REGIME, which the tracker owns, and a
        second copy of it in the order layer is how the two would come to disagree about
        whether the cap had been reached.
        """
        if direction > 0:
            self._trd_l += 1
        else:
            self._trd_s += 1

    # ── per-bar ──────────────────────────────────────────────────────────────────
    def update(self, sig, bar) -> BosState:
        """One bar. `sig` is the A+ `Signals` (structure + fib + divergence); `bar` is the
        `ReplayBar`, needed only for its volume."""
        cfg = self._cfg

        self._stage0(sig)
        fired_l, fired_s = self._stage1(sig)

        l_levels, s_levels = self._ladders(sig)
        l_ready = self._ready(l_levels, bull=True)
        s_ready = self._ready(s_levels, bull=False)
        l_top = self._band_top(l_levels, bull=True)
        s_top = self._band_top(s_levels, bull=False)

        self._death(sig, l_levels, s_levels, l_ready, s_ready, l_top, s_top)

        vwap_value, block_l, block_s = self._vwap_gate(sig, bar)

        return BosState(
            index=sig.index,
            regime_l=self._reg_l, regime_s=self._reg_s,
            count_l=self._cnt_l, count_s=self._cnt_s,
            traded_l=self._trd_l, traded_s=self._trd_s,
            long=self._leg_l, short=self._leg_s,
            l_levels=l_levels, s_levels=s_levels,
            l_ready=l_ready, s_ready=s_ready,
            l_top=l_top, s_top=s_top,
            vwap=vwap_value, vwap_block_l=block_l, vwap_block_s=block_s,
            fired_l=fired_l, fired_s=fired_s,
        )

    # ── Stage 0 — an SOS opens its own regime and closes the opposite one ────────
    def _stage0(self, sig) -> None:
        """Pine 3465-3486.

        ⚠ OPENING and CLOSING are gated DIFFERENTLY, and that asymmetry is a FIX, not an
        oversight (it was a bug in the Pine until 2026-07-29). Both used to sit behind
        `not session_gap_bar`, so an SOS printing on the first bar after the daily close did
        neither — and the half that mattered was the CLOSE: a bear SOS on a gap bar left the
        long leg armed, so its buy limit rested straight through into the new bearish regime
        and could still fill on the way down. That is a trade with no BOS of its own behind it.

          OPEN  stays gap-guarded — a structure event on a time-jump bar is an artifact, and
                arming a fresh regime off one is how you trade a phantom.
          CLOSE fires ALWAYS — refusing to believe an SOS cannot make it untrue. Killing on a
                possible artifact costs one setup; keeping it costs a wrong-way trade.
        """
        if sig.bear_sos:
            self._leg_l = self._leg_l.disarmed(
                "opposite SOS — the bullish regime is over" if self._leg_l.on else self._leg_l.why)
            self._reg_l = False
        if sig.bull_sos:
            self._leg_s = self._leg_s.disarmed(
                "opposite SOS — the bearish regime is over" if self._leg_s.on else self._leg_s.why)
            self._reg_s = False
        if sig.bull_sos and not sig.session_gap_bar:
            self._reg_l, self._cnt_l, self._trd_l = True, 0, 0
        if sig.bear_sos and not sig.session_gap_bar:
            self._reg_s, self._cnt_s, self._trd_s = True, 0, 0

    # ── Stage 1 — the BOS that arms a leg ───────────────────────────────────────
    def _stage1(self, sig):
        """Pine 3492-3527.

        The counter increments even when the filters refuse the leg, so the ordinal a trade
        reports is its TRUE position in the run rather than its position among the ones that
        armed. The NEWEST leg owns the setup: an existing arm is dropped BEFORE the new one is
        tested, mirroring the drawn fib re-anchoring — so a refused break still cancels the
        break before it.

        ⚠ Every BOS test reads `bull_bos and not bull_sos`: the structure engine sets
        `bull_bos = True` on every `bull_sos` bar too, so they are not mutually exclusive and
        an unguarded read would treat the shift itself as its own first continuation.
        """
        atr = _atr_of(sig)
        fire_l = (self._reg_l and sig.bull_bos and not sig.bull_sos and not sig.session_gap_bar
                  and sig.bull_bos_high is not None and sig.bull_bos_low is not None
                  and sig.bull_bos_high > sig.bull_bos_low)
        fire_s = (self._reg_s and sig.bear_bos and not sig.bear_sos and not sig.session_gap_bar
                  and sig.bear_bos_high is not None and sig.bear_bos_low is not None
                  and sig.bear_bos_high > sig.bear_bos_low)

        # ⚠ A REFUSED BREAK DISARMS AND KEEPS THE OLD LEG'S NUMBERS. Pine sets `bosL_on := false`
        # and only assigns `bosL_high` / `bosL_low` / `bosL_bar` / `bosL_n` / `bosL_half` INSIDE
        # the `if _okWhich and _okDisp and _okLeg` block — so a break the filters turn down leaves
        # the previous leg's values standing. Building a blank `BosLeg` here wiped them and put
        # the parity gate red on every bar after the first refusal. See BosLeg's docstring.
        if fire_l:
            self._cnt_l += 1
            why = ("re-anchored — a newer BOS on this side took the setup"
                   if self._leg_l.on else self._leg_l.why)
            self._leg_l = self._leg_l.disarmed(why)
            if self._arm_ok(self._cnt_l, sig.close - sig.bull_bos_high,
                            sig.bull_bos_high - sig.bull_bos_low, atr):
                self._leg_l = BosLeg(on=True, high=sig.bull_bos_high, low=sig.bull_bos_low,
                                     bar=sig.index, ordinal=self._cnt_l, half=False, why=why)

        if fire_s:
            self._cnt_s += 1
            why = ("re-anchored — a newer BOS on this side took the setup"
                   if self._leg_s.on else self._leg_s.why)
            self._leg_s = self._leg_s.disarmed(why)
            if self._arm_ok(self._cnt_s, sig.bear_bos_low - sig.close,
                            sig.bear_bos_high - sig.bear_bos_low, atr):
                self._leg_s = BosLeg(on=True, high=sig.bear_bos_high, low=sig.bear_bos_low,
                                     bar=sig.index, ordinal=self._cnt_s, half=False, why=why)

        return fire_l, fire_s

    def _arm_ok(self, ordinal: int, displacement: float, leg_size: float,
                atr: Optional[float]) -> bool:
        """F1 (which break) + F2 (displacement past the swing) + F3 (leg size), Pine 3502-3504.

        ⚠ An unknown ATR reads as a REFUSAL for F2/F3 when they are switched on, matching the
        Pine, where `>= bosMinDispAtr * atr14` against `na` is falsy. With both at 0 the ATR is
        never consulted, which is the shipped default and keeps the warmup free of refusals.
        """
        cfg = self._cfg
        if cfg.bos_which == "1st only" and ordinal != 1:
            return False
        if cfg.bos_which == "1st + 2nd" and ordinal > 2:
            return False
        if cfg.bos_min_disp_atr > 0:
            if atr is None or displacement < cfg.bos_min_disp_atr * atr:
                return False
        if cfg.bos_min_leg_atr > 0:
            if atr is None or leg_size < cfg.bos_min_leg_atr * atr:
                return False
        return True

    # ── the anchor fib ──────────────────────────────────────────────────────────
    def _ladders(self, sig):
        """Pine 3536-3566 — the leg the whole ladder is priced off.

        `bos_fib_anchor` picks it. "Break leg" is the frozen `bos_low -> bos_high` of the arm
        bar; "Expansion leg" is the LIVE structure fib (`fibo_ash`/`fibo_asl`), which keeps
        moving until the pullback confirms — and is therefore read only while the fib points
        this way, exactly as the Pine's `fibo_dir == 1 ? fibo_ash : na` does.
        """
        expansion = self._cfg.bos_fib_anchor == "Expansion leg"
        if expansion:
            l_ext = sig.fibo_ash if sig.fibo_dir == 1 else None
            l_org = sig.fibo_asl if sig.fibo_dir == 1 else None
            s_ext = sig.fibo_asl if sig.fibo_dir == -1 else None
            s_org = sig.fibo_ash if sig.fibo_dir == -1 else None
        else:
            l_ext, l_org = self._leg_l.high, self._leg_l.low
            s_ext, s_org = self._leg_s.low, self._leg_s.high
        return ({r: fib_price(l_ext, l_org, r) for r in _RATIOS},
                {r: fib_price(s_ext, s_org, r) for r in _RATIOS})

    @staticmethod
    def _ready(levels: dict, bull: bool) -> bool:
        """Pine `lFibsReady` / `sFibsReady` (3576-3577) — the ladder is priced AND the right
        way up. The direction check is what refuses an inverted leg, which would otherwise
        produce a stop on the wrong side of the entry."""
        need = (0.382, 0.5, 0.618, 0.886, 0.0, 1.0)
        if any(levels.get(r) is None for r in need):
            return False
        return levels[0.0] > levels[1.0] if bull else levels[1.0] > levels[0.0]

    def _band_top(self, levels: dict, bull: bool) -> Optional[float]:
        """Pine `lTop` / `sTop` (3572-3573) — the SHALLOW end of the entry band, in price.

        Six rules used to hardcode 0.5 (the gap's band test, the entry clamp, the fully-past
        test, the Sniper Zone clamp, the straddle fallback and the plain-fib clamp) and every
        one of them reads this instead, so opening the band moves all six together and they
        cannot drift apart. The DEEP end (0.886) is fixed and is not affected.
        """
        return levels.get(0.382 if self._cfg.bos_entry_top == "0.382" else 0.5)

    # ── death ───────────────────────────────────────────────────────────────────
    def _death(self, sig, l_levels, s_levels, l_ready, s_ready, l_top, s_top) -> None:
        """Pine 3588-3629 — the armed leg is dropped without a trade.

        The cycle-complete test is the PER-ANCHOR version of the engine's global
        `fibo7Touched`: the shallow end of the band has been tapped (the retrace happened) AND
        price has since returned to the anchor's own 0.0. The global latch cannot be used — it
        is keyed to the fib ORIGIN, which does not change across a run of breaks, so break #1's
        round trip would kill breaks #2 and #3 on their arm bar and every continuation after
        the first would be untradeable. It reads `l_top` rather than a hardcoded 0.5 so that
        "the retrace happened" means the same thing here as it does to the entry ladder.
        """
        cfg = self._cfg
        max_bars = self.max_bars

        leg = self._leg_l
        if leg.on:
            half = leg.half or (l_ready and l_top is not None and sig.low <= l_top)
            why = ""
            if half and l_ready and sig.high >= l_levels[0.0]:
                why = "cycle complete — retraced, then came back to the leg extreme"
            elif l_ready and sig.close < l_levels[1.0]:
                why = "closed past the anchor's fib 1.0 (leg origin) — leg invalidated"
            elif cfg.bos_req_hold and leg.high is not None and sig.close < leg.high:
                why = "F4 — closed back through the broken swing"
            elif leg.bar is not None and sig.index - leg.bar > max_bars:
                why = "stale — the day cap expired before the retrace arrived"
            # The half-latch is written EITHER WAY — Pine assigns `bosL_half := true` before the
            # death chain runs, so a leg that dies on the same bar it tapped the band still
            # carries the latch afterwards.
            self._leg_l = replace(leg, on=not why, half=half, why=why or leg.why)

        leg = self._leg_s
        if leg.on:
            half = leg.half or (s_ready and s_top is not None and sig.high >= s_top)
            why = ""
            if half and s_ready and sig.low <= s_levels[0.0]:
                why = "cycle complete — retraced, then came back to the leg extreme"
            elif s_ready and sig.close > s_levels[1.0]:
                why = "closed past the anchor's fib 1.0 (leg origin) — leg invalidated"
            elif cfg.bos_req_hold and leg.low is not None and sig.close > leg.low:
                why = "F4 — closed back through the broken swing"
            elif leg.bar is not None and sig.index - leg.bar > max_bars:
                why = "stale — the day cap expired before the retrace arrived"
            self._leg_s = replace(leg, on=not why, half=half, why=why or leg.why)

    # ── F10 — the session VWAP gate ─────────────────────────────────────────────
    def _vwap_gate(self, sig, bar):
        """Pine 3800-3818 — refuse a setup while price is not closing on the trend's own side.

        It is a STATE, not a cross: it never asks whether price crossed the line, only which
        side of it THIS BAR CLOSED. That is also what keeps it free of look-ahead — the arm is
        recomputed at every bar's close and rests or cancels the limit for the NEXT bar, so the
        side being read is always a closed bar's, never the side of the bar the fill happens on.
        🔴 Reading the fill bar's own close selects bars that recovered by their close, and that
        error inflated this filter's measured edge from +6.8% to +15.9% before it was caught.

        ⚠ A `None` VWAP (no volume yet on the session's first bar) BLOCKS, never passes. "Cannot
        ask" and "no" must not be the same value, and of the two answers available to a gate
        about to place money the safe one is the refusal. It costs at most one bar a day.
        """
        if self._cfg.bos_vwap_req == "Off":
            # The engine is still stepped, so switching the filter on mid-run could never
            # produce a VWAP anchored on a partial session. Costs one multiply per bar.
            self._step_vwap(sig, bar, required=False)
            return None, False, False

        value = self._step_vwap(sig, bar, required=True)
        if value is None:
            return None, True, True
        return value, not (sig.close > value), not (sig.close < value)

    def _step_vwap(self, sig, bar, *, required: bool) -> Optional[float]:
        volume = getattr(bar, "volume", None)
        if volume is None:
            if required:
                raise VolumeUnavailable(
                    "bos_vwap_req is on and this bar carries no volume, so the session VWAP "
                    "cannot be computed. Blocking every setup and passing every setup are both "
                    "wrong and neither is visible in the result. Either re-pull the bars with "
                    "volume (backtest/CLAUDE.md → the FEED_VERSION 3 note; delete that pair's "
                    ".csv and .meta.json to force it) or set bos_vwap_req='Off' deliberately."
                )
            return None
        ev = self._vwap.update(sig.index, sig.time_ms, sig.high, sig.low, sig.close, volume)
        return ev.value


def _atr_of(sig) -> Optional[float]:
    """The bar's ATR(14), read off whatever the caller attached.

    The tracker does not compute it: `Execution._update_atr` already reproduces Pine's
    `ta.atr(14)` exactly (Wilder's RMA, including its NA warmup), and a second implementation
    here would be a second answer to one question — the failure this repo names most often.
    `BosStrategy` stamps it onto the state before the tracker runs.
    """
    return getattr(sig, "bos_atr14", None)
