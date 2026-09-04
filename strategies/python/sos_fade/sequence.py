"""SosFadeSequence — the A+ setup state machine.

A line-for-line port of the A+ SETUP SEQUENCE block in `strategies/tradingview/sos_fade_strategy.pine`
(3708-3972) plus the execution layer's arm-source snapshot (4309-4355). It is a
*sequence, not a checklist*: each stage counts only if the previous one is done.

    Stage 1 ARM    a new liquidity sweep OR a new confirmed RSI divergence
    Stage 2 SOS    an external same-side SOS inside the staleness window
    Stage 3 EARLY  the SOS leg's fib 0.5 tapped
    Stage 4 READY  the SOS leg's fib 0.618 reached (E1-E3 zone live)

State is held per side (`_l_*` long / `_s_*` short), mirroring the Pine `aplusL_*` /
`aplusS_*` vars. The sequence also snapshots which Stage-1 source (sweep / divergence)
was live at the SOS — the execution layer's arm-source filter reads that to isolate a
trigger. CONT (continuation) tracking is ported for completeness (the Pine table shows
it) but is NOT traded — out of scope per the spec.

`update(sig)` consumes one `Signals` (see signals.py) and returns a `SeqState`. Feed
bars in order; do not skip.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .signals import pois_for


@dataclass
class SeqState:
    """The A+ sequence's per-bar output — what execution.py reads to place orders."""

    l_stage: int
    s_stage: int
    l_sos_bar: Optional[int]
    s_sos_bar: Optional[int]
    l_half: bool
    l_618: bool
    s_half: bool
    s_618: bool
    l_poi: bool
    s_poi: bool
    l_fvg: bool            # a live FVG overlaps the long entry band (confluence flag)
    s_fvg: bool
    # arm sources live at the SOS (raw, before the enable-toggles are applied)
    sos_l_swp: bool
    sos_l_div: bool
    sos_s_swp: bool
    sos_s_div: bool
    # edge triggers this bar (execution's miss/label bookkeeping reads these)
    new_sweep_l: bool
    new_div_l: bool
    new_sweep_s: bool
    new_div_s: bool
    retro_link_l: bool
    retro_link_s: bool
    # B-LEG arm capture (Pine bLegArmL/bLegArmS, sos_fade_strategy.pine ~3661) — TRUE on the bar
    # a stage-2 REV dies on a continuation BOS while still at 2/3 (no 0.5/0.618 latch). Read
    # HERE, BEFORE the leg-resolution death below clears l_sos_bar and before the half/618
    # latch update — the exact pre-death window the Pine captures it in. Nothing in the A+
    # path reads these, so they are parity-neutral; the B-LEG bot consumes them.
    bleg_arm_l: bool = False
    bleg_arm_s: bool = False
    # Which Stage-1 SOURCE currently holds the arm slot on each side — "SWP" / "DIV" / "".
    # Pine `armHolderL` / `armHolderS` (sos_fade_strategy.pine 3061-3062), which that file's own
    # comment calls read-only bookkeeping: nothing in the engine or the trade path reads it.
    # It exists so the missed-setup callout can name the source that armed a setup EVEN WHEN
    # that source is switched off — the one case the live `sos_*_swp`/`sos_*_div` flags cannot
    # answer, because the execution layer has already filtered them through the toggles.
    # REPORTING ONLY, so parity-neutral (same standing as `bleg_arm_*` above).
    l_arm_src: str = ""
    s_arm_src: str = ""


_DAY_MS = 86_400_000


class SosFadeSequence:
    def __init__(self, config) -> None:
        self._cfg = config
        self._window_ms = config.aplus_window * 60_000

        # ── long side (Pine aplusL_*) ──
        self._l_sweep_bar: Optional[int] = None
        self._l_sos_bar: Optional[int] = None
        self._l_poi = False
        self._l_arm_time: Optional[int] = None
        self._l_half = False
        self._l_618 = False
        self._cont_l_bos: Optional[int] = None
        # ── short side (Pine aplusS_*) ──
        self._s_sweep_bar: Optional[int] = None
        self._s_sos_bar: Optional[int] = None
        self._s_poi = False
        self._s_arm_time: Optional[int] = None
        self._s_half = False
        self._s_618 = False
        self._cont_s_bos: Optional[int] = None

        # last SOS per side (Pine lastBull/BearSosBar/Time)
        self._last_bull_sos_bar: Optional[int] = None
        self._last_bull_sos_time: Optional[int] = None
        self._last_bear_sos_bar: Optional[int] = None
        self._last_bear_sos_time: Optional[int] = None

        # arm-source tracking (Pine armSwp*/armDiv* + sos*_swp/div, exec 4309-4342)
        self._arm_swp_l: Optional[int] = None
        self._arm_swp_lt: Optional[int] = None
        self._arm_div_l: Optional[int] = None
        self._arm_div_lt: Optional[int] = None
        self._arm_swp_s: Optional[int] = None
        self._arm_swp_st: Optional[int] = None
        self._arm_div_s: Optional[int] = None
        self._arm_div_st: Optional[int] = None
        self._sos_l_swp = False
        self._sos_l_div = False
        self._sos_s_swp = False
        self._sos_s_div = False

        # which source holds the Stage-1 slot (Pine armHolderL/armHolderS) — see SeqState
        self._arm_holder_l = ""
        self._arm_holder_s = ""

        # previous-bar values for the edge detectors (Pine `X != X[1]`)
        self._prev_recent_ssl_bar: Optional[int] = None
        self._prev_recent_bsl_bar: Optional[int] = None
        self._prev_last_bull_div_bar: Optional[int] = None
        self._prev_last_bear_div_bar: Optional[int] = None

    def update(self, sig) -> SeqState:
        gap = sig.session_gap_bar

        # ── last SOS per side, remembered first (Pine 3712-3715) ──
        if sig.bull_sos:
            self._last_bull_sos_bar = sig.index
            self._last_bull_sos_time = sig.time_ms
        if sig.bear_sos:
            self._last_bear_sos_bar = sig.index
            self._last_bear_sos_time = sig.time_ms

        # ── Stage-1 edge triggers (Pine 3730-3740) ──
        new_sweep_l = (sig.recent_ssl != "" and sig.recent_ssl_bar != self._prev_recent_ssl_bar
                       and not gap)
        # Pine `newDivL = not na(lastBullDivBar) and lastBullDivBar != lastBullDivBar[1]`.
        # The `!= [1]` is `na`-poisoned: on the FIRST-ever divergence the prior value is
        # `na`, and Pine returns `na` (falsy) for any comparison with `na` — so the first
        # divergence is NEVER seen as "new" and never arms. Python's `X != None` is True,
        # which would arm it, so require the previous bar be non-None to match Pine exactly.
        new_div_l = (sig.last_bull_div_bar is not None
                     and self._prev_last_bull_div_bar is not None
                     and sig.last_bull_div_bar != self._prev_last_bull_div_bar)
        if new_sweep_l and sig.recent_ssl == "Day Low" and sig.recent_ssl_time is not None \
                and (sig.time_ms - sig.recent_ssl_time) > _DAY_MS:
            new_sweep_l = False  # daily sweep older than a day is stale fuel

        new_sweep_s = (sig.recent_bsl != "" and sig.recent_bsl_bar != self._prev_recent_bsl_bar
                       and not gap)
        new_div_s = (sig.last_bear_div_bar is not None
                     and self._prev_last_bear_div_bar is not None
                     and sig.last_bear_div_bar != self._prev_last_bear_div_bar)
        if new_sweep_s and sig.recent_bsl == "Day High" and sig.recent_bsl_time is not None \
                and (sig.time_ms - sig.recent_bsl_time) > _DAY_MS:
            new_sweep_s = False

        # ── Stage-1 arm (Pine 3752-3761) ──
        l_can_arm = self._l_sweep_bar is None and self._l_sos_bar is None
        l_can_arm_div = self._l_sos_bar is None
        if new_sweep_l and l_can_arm:
            self._l_sweep_bar = sig.recent_ssl_bar
            self._l_arm_time = sig.time_ms
            self._arm_holder_l = "SWP"
        if new_div_l and l_can_arm_div:
            self._l_sweep_bar = sig.last_bull_div_bar
            self._l_arm_time = sig.time_ms
            self._arm_holder_l = "DIV"

        # ── retro-link: adopt an SOS that already fired at/after the div pivot (3771-3773) ──
        retro_link_l = (new_div_l and self._l_sweep_bar is not None and self._l_sos_bar is None
                        and self._last_bull_sos_bar is not None
                        and self._last_bull_sos_bar >= sig.last_bull_div_bar
                        and sig.time_ms - self._last_bull_sos_time <= self._window_ms)
        if retro_link_l:
            self._l_sos_bar = self._last_bull_sos_bar

        # ── short arm + retro (Pine 3784-3798) ──
        s_can_arm = self._s_sweep_bar is None and self._s_sos_bar is None
        s_can_arm_div = self._s_sos_bar is None
        if new_sweep_s and s_can_arm:
            self._s_sweep_bar = sig.recent_bsl_bar
            self._s_arm_time = sig.time_ms
            self._arm_holder_s = "SWP"
        if new_div_s and s_can_arm_div:
            self._s_sweep_bar = sig.last_bear_div_bar
            self._s_arm_time = sig.time_ms
            self._arm_holder_s = "DIV"
        retro_link_s = (new_div_s and self._s_sweep_bar is not None and self._s_sos_bar is None
                        and self._last_bear_sos_bar is not None
                        and self._last_bear_sos_bar >= sig.last_bear_div_bar
                        and sig.time_ms - self._last_bear_sos_time <= self._window_ms)
        if retro_link_s:
            self._s_sos_bar = self._last_bear_sos_bar

        # ── POI latch while armed (Pine 3800-3804) ──
        if self._l_sweep_bar is not None:
            self._l_poi = self._l_poi or sig.poi_long_now
        if self._s_sweep_bar is not None:
            self._s_poi = self._s_poi or sig.poi_short_now

        # ── Stage 2 — SOS within the staleness window (Pine 3806-3810) ──
        if sig.bull_sos and self._l_arm_time is not None \
                and sig.time_ms - self._l_arm_time <= self._window_ms:
            self._l_sos_bar = sig.index
        if sig.bear_sos and self._s_arm_time is not None \
                and sig.time_ms - self._s_arm_time <= self._window_ms:
            self._s_sos_bar = sig.index

        # ── stale-arm clear (Pine 3819-3826) ──
        if not gap and self._l_sweep_bar is not None and self._l_sos_bar is None \
                and self._l_arm_time is not None and sig.time_ms - self._l_arm_time > self._window_ms:
            self._l_sweep_bar = None
            self._l_arm_time = None
            self._arm_holder_l = ""
        if not gap and self._s_sweep_bar is not None and self._s_sos_bar is None \
                and self._s_arm_time is not None and sig.time_ms - self._s_arm_time > self._window_ms:
            self._s_sweep_bar = None
            self._s_arm_time = None
            self._arm_holder_s = ""

        # ── sequence death: opposite SOS (Pine 3835-3843) ──
        if sig.bear_sos and not gap:
            self._clear_long()
        if sig.bull_sos and not gap:
            self._clear_short()
        if (sig.bull_sos or sig.bear_sos) and not gap:
            self._cont_l_bos = None
            self._cont_s_bos = None

        # ── B-LEG arm capture (Pine 3661) — READ BEFORE the leg-resolution death below,
        #    which clears l_sos_bar on the continuation BOS, and before the half/618 latch
        #    update (both happen later this bar). The B LEG owns exactly this death: a live
        #    stage-2 REV breaking structure again in-trend while still at 2/3 (neither latch
        #    set), fib pointing the trade's way, TP3 not yet hit. ──
        bleg_arm_l = (self._l_sos_bar is not None and not gap
                      and sig.bull_bos and not sig.bull_sos
                      and not self._l_half and not self._l_618
                      and sig.fibo_dir == 1 and not sig.fibo7_touched)
        bleg_arm_s = (self._s_sos_bar is not None and not gap
                      and sig.bear_bos and not sig.bear_sos
                      and not self._s_half and not self._s_618
                      and sig.fibo_dir == -1 and not sig.fibo7_touched)

        # ── A+ leg resolution: TP3 / invalidation / continuation-BOS (Pine 3854-3861) ──
        if self._l_sos_bar is not None and not gap:
            if (sig.fibo_dir == 1 and sig.fibo7_touched) or sig.fibo_dir == -1 \
                    or (sig.fibo_dir == 1 and sig.fibo_p10 is not None and sig.close < sig.fibo_p10) \
                    or (sig.bull_bos and not sig.bull_sos):
                self._clear_long()
        if self._s_sos_bar is not None and not gap:
            if (sig.fibo_dir == -1 and sig.fibo7_touched) or sig.fibo_dir == 1 \
                    or (sig.fibo_dir == -1 and sig.fibo_p10 is not None and sig.close > sig.fibo_p10) \
                    or (sig.bear_bos and not sig.bear_sos):
                self._clear_short()

        # ── CONT trigger + resolution (Pine 3869-3883) — tracked, not traded ──
        if sig.bull_bos and self._l_sweep_bar is None:
            self._cont_l_bos = sig.index
        if sig.bear_bos and self._s_sweep_bar is None:
            self._cont_s_bos = sig.index
        if self._cont_l_bos is not None:
            if (sig.fibo_dir == 1 and sig.fibo7_touched) or sig.fibo_dir == -1 \
                    or (sig.fibo_dir == 1 and sig.fibo_p10 is not None and sig.close < sig.fibo_p10):
                self._cont_l_bos = None
        if self._cont_s_bos is not None:
            if (sig.fibo_dir == -1 and sig.fibo7_touched) or sig.fibo_dir == 1 \
                    or (sig.fibo_dir == -1 and sig.fibo_p10 is not None and sig.close > sig.fibo_p10):
                self._cont_s_bos = None

        # ── Stage-3 latch: A+-owned 0.5 / 0.618 progress (Pine 3890-3899) ──
        if self._l_sos_bar is not None:
            self._l_half = self._l_half or sig.fibo_half_reached
            self._l_618 = self._l_618 or sig.fibo_618_ever_reached
        else:
            self._l_half = False
            self._l_618 = False
        if self._s_sos_bar is not None:
            self._s_half = self._s_half or sig.fibo_half_reached
            self._s_618 = self._s_618 or sig.fibo_618_ever_reached
        else:
            self._s_half = False
            self._s_618 = False

        # ── stage value (Pine 3903-3913) ──
        l_stage = 0
        if self._l_sos_bar is not None:
            l_stage = 4 if self._l_618 else 3 if self._l_half else 2
        elif self._l_sweep_bar is not None:
            l_stage = 1
        s_stage = 0
        if self._s_sos_bar is not None:
            s_stage = 4 if self._s_618 else 3 if self._s_half else 2
        elif self._s_sweep_bar is not None:
            s_stage = 1

        # ── FVG confluence: a live gap overlapping the entry band (Pine 3644-3659) ──
        # The `exec_fvg_pre_zone` gate is applied HERE as well as in the entry-edge loop,
        # because Pine gates both consumers with the same `f_gapPreZone` — otherwise a gap the
        # entry may not use could still be reported as the confluence that armed the setup.
        l_fvg = s_fvg = False
        if sig.fibo_p2 is not None and sig.fibo_p6 is not None:
            # The precedence RANK is deliberately ignored here: this flag answers "is there a
            # zone in the band at all", and under "FVG first" a leg whose only zone is an order
            # block is one the entry really will trade off that block. Ranking the flag would
            # report no confluence on a setup that is about to fire.
            for top, bot, is_bull, born, _rank in pois_for(self._cfg, sig):
                gap_ok = (not self._cfg.exec_fvg_pre_zone
                          or sig.fibo_half_bar is None
                          or born < sig.fibo_half_bar)
                if is_bull:
                    if sig.fibo_dir == 1 and bot <= sig.fibo_p2 and top >= sig.fibo_p6 and gap_ok:
                        l_fvg = True
                else:
                    if sig.fibo_dir == -1 and top >= sig.fibo_p2 and bot <= sig.fibo_p6 and gap_ok:
                        s_fvg = True

        # ── arm-source snapshot (Pine exec 4318-4342) ──
        if new_sweep_l:
            self._arm_swp_l, self._arm_swp_lt = sig.recent_ssl_bar, sig.time_ms
        if new_div_l:
            self._arm_div_l, self._arm_div_lt = sig.last_bull_div_bar, sig.time_ms
        if new_sweep_s:
            self._arm_swp_s, self._arm_swp_st = sig.recent_bsl_bar, sig.time_ms
        if new_div_s:
            self._arm_div_s, self._arm_div_st = sig.last_bear_div_bar, sig.time_ms

        w = self._window_ms
        if sig.bull_sos:
            self._sos_l_swp = self._arm_swp_lt is not None and sig.time_ms - self._arm_swp_lt <= w
            self._sos_l_div = self._arm_div_lt is not None and sig.time_ms - self._arm_div_lt <= w
        if sig.bear_sos:
            self._sos_s_swp = self._arm_swp_st is not None and sig.time_ms - self._arm_swp_st <= w
            self._sos_s_div = self._arm_div_st is not None and sig.time_ms - self._arm_div_st <= w
        if retro_link_l:
            self._sos_l_div = True
            self._sos_l_swp = self._arm_swp_lt is not None \
                and self._arm_swp_lt <= self._last_bull_sos_time \
                and self._last_bull_sos_time - self._arm_swp_lt <= w
        if retro_link_s:
            self._sos_s_div = True
            self._sos_s_swp = self._arm_swp_st is not None \
                and self._arm_swp_st <= self._last_bear_sos_time \
                and self._last_bear_sos_time - self._arm_swp_st <= w

        # advance the edge-detector history
        self._prev_recent_ssl_bar = sig.recent_ssl_bar
        self._prev_recent_bsl_bar = sig.recent_bsl_bar
        self._prev_last_bull_div_bar = sig.last_bull_div_bar
        self._prev_last_bear_div_bar = sig.last_bear_div_bar

        return SeqState(
            l_stage=l_stage, s_stage=s_stage,
            l_sos_bar=self._l_sos_bar, s_sos_bar=self._s_sos_bar,
            l_half=self._l_half, l_618=self._l_618, s_half=self._s_half, s_618=self._s_618,
            l_poi=self._l_poi, s_poi=self._s_poi, l_fvg=l_fvg, s_fvg=s_fvg,
            sos_l_swp=self._sos_l_swp, sos_l_div=self._sos_l_div,
            sos_s_swp=self._sos_s_swp, sos_s_div=self._sos_s_div,
            new_sweep_l=new_sweep_l, new_div_l=new_div_l,
            new_sweep_s=new_sweep_s, new_div_s=new_div_s,
            retro_link_l=retro_link_l, retro_link_s=retro_link_s,
            bleg_arm_l=bleg_arm_l, bleg_arm_s=bleg_arm_s,
            l_arm_src=self._arm_holder_l, s_arm_src=self._arm_holder_s,
        )

    def _clear_long(self) -> None:
        self._l_sos_bar = None
        self._l_sweep_bar = None
        self._l_poi = False
        self._l_arm_time = None
        self._arm_holder_l = ""

    def _clear_short(self) -> None:
        self._s_sos_bar = None
        self._s_sweep_bar = None
        self._s_poi = False
        self._s_arm_time = None
        self._arm_holder_s = ""
