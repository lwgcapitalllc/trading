"""Secondary (1m sniper) re-entry — the 1-minute side of the MPC SOS Fade bot.

The primary A+ trade is a 15m setup (see `execution.py`). The SECONDARY is a re-entry
on the *same* 15m leg, sniped off the 1-minute chart: after the primary has traded and
gone flat, while the 15m divergence + SOS are still live and price is back in the
0.618-0.886 zone, a 1m shift of structure in the trade direction rests a tight limit at
a 38.2% retrace of that 1m leg. Full rules + the Pine source: `docs/MPC_SOS_FADE_SECONDARY.md`.

This module owns the 1-minute STRUCTURE feed (`Structure1m`) — a line-for-line port of
the Pine `f_struct1m` helper (from the stashed secondary-trade WIP). It runs the canonical
`market_structure` engine on 1m bars and latches, per side, the most-recent 1m SOS bar and
the break leg it defined (`bull_bos_high`/`bull_bos_low` = the leg's 0.0 / 1.0 anchors).
Nothing here reads the fib — the Pine reads the leg straight off the structure engine's SOS
event, so we do too.

The arm/latch state machine that consumes this feed + the 15m context lives in `SecondaryArm`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# engines/ on path so `market_structure` imports by bare name (same shim as backtest/replay/stack.py).
_ENGINES = Path(__file__).resolve().parents[3] / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

from market_structure import Bar, StructureEngine  # noqa: E402

from .signals import sos_aware_veto  # noqa: E402


@dataclass(frozen=True)
class M1State:
    """The latched 1m structure read, as of one 1m bar — the exact tuple Pine's
    `f_struct1m` returns, plus the per-side 'a new SOS fired this bar' edges the
    secondary latch keys off (Pine `m1NewBullSos` / `m1NewBearSos`).

    `*_leg_hi` / `*_leg_lo` are the break leg's endpoints: 0.0 (extreme) and 1.0 (origin,
    = the stop anchor). They persist until the next same-side 1m SOS overwrites them, so a
    consumer can read the current leg on any bar, not only the SOS bar."""

    bull_sos_bar: Optional[int]
    bear_sos_bar: Optional[int]
    bull_leg_hi: Optional[float]
    bull_leg_lo: Optional[float]
    bear_leg_hi: Optional[float]
    bear_leg_lo: Optional[float]
    direction: int  # engine dir (Pine st1.dir): 1 up / -1 down / 0 undetermined
    new_bull_sos: bool  # a bull SOS fired on THIS 1m bar (the latched bar advanced)
    new_bear_sos: bool


class Structure1m:
    """The 1-minute structure feed. Port of Pine `f_struct1m`: one `market_structure`
    engine on 1m bars, latching the most-recent SOS bar + break leg per side.

    Stateful streaming, like every engine: build once, feed one 1m bar per `update()`
    in time order. `major_length` matches the 15m engine (the validated default 15) —
    the Pine's `f_struct1m` uses the same `majorLength` on both feeds.
    """

    def __init__(self, major_length: int = 15) -> None:
        self._engine = StructureEngine(major_length=major_length)
        self.bull_sos_bar: Optional[int] = None
        self.bear_sos_bar: Optional[int] = None
        self.bull_leg_hi: Optional[float] = None
        self.bull_leg_lo: Optional[float] = None
        self.bear_leg_hi: Optional[float] = None
        self.bear_leg_lo: Optional[float] = None

    def update(self, index: int, o: float, h: float, l: float, c: float) -> M1State:
        ext = self._engine.update(Bar(index=index, open=o, high=h, low=l, close=c)).external

        new_bull = bool(ext.bull_sos)
        new_bear = bool(ext.bear_sos)
        # Latch on an SOS, mirroring `f_struct1m`: record the SOS bar and the break leg's
        # endpoints straight off the structure event (0.0 = *_bos_high, 1.0 = *_bos_low).
        if new_bull:
            self.bull_sos_bar = index
            self.bull_leg_hi = ext.bull_bos_high
            self.bull_leg_lo = ext.bull_bos_low
        if new_bear:
            self.bear_sos_bar = index
            self.bear_leg_hi = ext.bear_bos_high
            self.bear_leg_lo = ext.bear_bos_low

        return M1State(
            bull_sos_bar=self.bull_sos_bar,
            bear_sos_bar=self.bear_sos_bar,
            bull_leg_hi=self.bull_leg_hi,
            bull_leg_lo=self.bull_leg_lo,
            bear_leg_hi=self.bear_leg_hi,
            bear_leg_lo=self.bear_leg_lo,
            direction=self._engine.dir,
            new_bull_sos=new_bull,
            new_bear_sos=new_bear,
        )


@dataclass(frozen=True)
class SecArm:
    """One 1m bar's secondary-arm result — what `Execution.step_secondary` needs to rest
    (or cancel) the sniper limit. `*_leg` is the 1m SOS bar the entry would trade, so the
    execution can retire that leg on a fill (each 1m leg re-enters at most once)."""

    l_armed: bool = False
    l_edge: Optional[float] = None  # resting BUY limit — 38.2% retrace of the 1m leg
    l_sl: Optional[float] = None  # stop = 1m leg origin (1.0) − buffer
    l_tp1: Optional[float] = None  # 15m fib 0.5
    l_tp2: Optional[float] = None  # 15m fib 0.382 (TP3 = runner)
    l_leg: Optional[int] = None
    s_armed: bool = False
    s_edge: Optional[float] = None
    s_sl: Optional[float] = None
    s_tp1: Optional[float] = None
    s_tp2: Optional[float] = None
    s_leg: Optional[int] = None


class SecondaryArm:
    """The secondary latch + arm state machine — a line-for-line port of the Pine WIP
    `f_secArm` (from the stashed secondary-trade branch). See `docs/MPC_SOS_FADE_SECONDARY.md`.

    Holds, per side, the latched 1m leg (`_leg` = its SOS bar, `_hi`/`_lo` = its 0.0/1.0
    anchors), the leg that has already re-entered (`_traded`, retired so it can't fire twice),
    and the 15m leg killed by a stopped re-entry (`_dead`). Each `update()` reads: the current
    1m structure (`M1State`), the last-closed 15m context (`sig` = Signals, `seq` = SeqState),
    whether the account is flat, and the primary's `be_sos_*` latches — and returns a `SecArm`.

    **Two eligibility rules beyond the zone (Aaron's spec):**
      - The PRIMARY must have reached breakeven — hit at least TP1 (`be_sos == *_sos_bar`). A
        primary that opened and got stopped at its initial stop leaves NO re-entry on that leg.
      - The cascade continues across winners/scratches (re-enter on each fresh 1m shift while the
        setup lives), but a re-entry that hits its own initial stop KILLS the leg (`mark_dead`):
        no more re-entries until a new break of structure resets it.

    **`exec_sec_once_per_setup` (default ON) caps the cascade at one re-entry per PRIMARY.** The
    latch above retires the 1-MINUTE leg, so one 15m setup can keep handing out fresh legs — on
    2024-12-02 it took two re-entries off one structure break, the second two minutes after the
    first closed. With the cap, a fill also retires the 15m SOS BAR (`_used`), which is one-to-one
    with the primary because the arm already requires `be_sos == seq.*_sos_bar`. A new break gives
    a new SOS bar and re-opens the door, so this bounds a cascade rather than retiring the feature.
    ⚠ `_used` is deliberately NOT `_dead`, even though both gate on the 15m SOS bar and the cheap
    version of this would have reused it. They answer different questions — *this setup has had its
    re-entry* vs *a re-entry stopped out, so the leg is finished* — and merging them would make the
    stop-out rule silently depend on a preference switch.

    **Zone is a 15m gate, not a 1m one (faithful to the Pine).** Pine's `zoneL` reads the 15m
    bar `close` (`close <= fiboP3 and close >= fiboP6`): "the last 15m bar closed inside the
    retrace zone." That gate stays open for the whole 15m bar (~15 one-minute bars), and any 1m
    SOS inside it is the trigger. Checking the LIVE 1m close instead would almost never fire —
    a 1m up-shift confirms *after* price has ticked up off the zone low, so the 1m close has
    usually left the zone by the SOS bar. The ONLY intended deviation from the Pine is the exact
    1m SOS *timing* (Pine samples the 1m engine once per 15m bar; we see every 1m bar).
    """

    def __init__(self, config) -> None:
        self._cfg = config
        self._l_leg: Optional[int] = None
        self._l_hi: Optional[float] = None
        self._l_lo: Optional[float] = None
        self._l_traded: Optional[int] = None
        self._l_dead: Optional[int] = None  # 15m leg killed by a stopped re-entry (no more)
        self._l_used: Optional[int] = None  # 15m leg that has had its one re-entry (the cap)
        self._s_leg: Optional[int] = None
        self._s_hi: Optional[float] = None
        self._s_lo: Optional[float] = None
        self._s_traded: Optional[int] = None
        self._s_dead: Optional[int] = None
        self._s_used: Optional[int] = None
        # The 15m SOS bar each side is currently arming against, captured in `update()` because
        # `mark_traded` is called by the driver without `seq` in hand.
        self._l_sos: Optional[int] = None
        self._s_sos: Optional[int] = None

    def update(
        self,
        m1: M1State,
        sig,
        seq,
        zone_close: float,
        ny_hour: int,
        flat: bool,
        be_sos_l: Optional[int],
        be_sos_s: Optional[int],
    ) -> SecArm:
        cfg = self._cfg

        # 1. Clear a latched 1m leg the instant its 15m setup dies (Pine: `if na(aplusL_sosBar)`).
        #    A new break of structure also resets the dead-leg flag (the leg is fresh again).
        #    `_used` (the one-per-setup cap) clears here too: the setup it referred to is gone.
        #    The `!=` test below would already re-open on a new SOS bar, so this is tidiness
        #    rather than correctness — but leaving a latch pointing at a dead setup is how the
        #    next reader concludes it means something.
        self._l_sos, self._s_sos = seq.l_sos_bar, seq.s_sos_bar
        if seq.l_sos_bar is None:
            self._l_leg = self._l_hi = self._l_lo = None
            self._l_dead = None
            self._l_used = None
        if seq.s_sos_bar is None:
            self._s_leg = self._s_hi = self._s_lo = None
            self._s_dead = None
            self._s_used = None

        # 2. Zone (0.886..0.618 of the 15m fib) — a 15m gate: Pine reads the last-closed 15m bar
        #    `close`, so `zone_close` is that bar's close (NOT the live 1m close, which the 1m SOS
        #    has usually left by the time it confirms). See the class docstring.
        p3, p6 = sig.fibo_p3, sig.fibo_p6
        zone_l = (
            sig.fibo_dir == 1
            and p3 is not None
            and p6 is not None
            and zone_close <= p3
            and zone_close >= p6
        )
        zone_s = (
            sig.fibo_dir == -1
            and p3 is not None
            and p6 is not None
            and zone_close >= p3
            and zone_close <= p6
        )

        # 3. Latch a fresh 1m leg on a new same-side 1m SOS while the 15m setup + div are live.
        if (
            cfg.exec_secondary
            and m1.new_bull_sos
            and seq.l_sos_bar is not None
            and sig.bull_div_active
            and zone_l
            and m1.bull_leg_hi is not None
            and m1.bull_leg_lo is not None
            and m1.bull_leg_hi > m1.bull_leg_lo
        ):
            self._l_leg, self._l_hi, self._l_lo = m1.bull_sos_bar, m1.bull_leg_hi, m1.bull_leg_lo
        if (
            cfg.exec_secondary
            and m1.new_bear_sos
            and seq.s_sos_bar is not None
            and sig.bear_div_active
            and zone_s
            and m1.bear_leg_hi is not None
            and m1.bear_leg_lo is not None
            and m1.bear_leg_hi > m1.bear_leg_lo
        ):
            self._s_leg, self._s_hi, self._s_lo = m1.bear_sos_bar, m1.bear_leg_hi, m1.bear_leg_lo

        # 4. Arm — flat, the PRIMARY on this 15m leg reached breakeven (be_sos == l_sos_bar; a
        #    primary stopped at its initial stop leaves no re-entry), the leg is not dead (no prior
        #    re-entry stopped out), div + dir + fibs live, this 1m leg not already re-entered, not
        #    late-day, veto clear (Pine `s.lArmed := …`).
        fibs_ready = None not in (sig.fibo_p1, sig.fibo_p2, p3, p6, sig.fibo_p7, sig.fibo_p10)
        late = cfg.exec_no_late_day and 16 <= ny_hour < 18
        respect_veto = cfg.exec_respect_veto
        # Same SOS-aware veto the primary reads (Pine longVetoA/shortVetoA).
        long_veto, short_veto = sos_aware_veto(sig, seq.l_sos_bar, seq.s_sos_bar)
        # The one-per-setup cap. Inert when off, so the OFF path is the original rule exactly.
        cap = cfg.exec_sec_once_per_setup
        l_capped = cap and self._l_used is not None and seq.l_sos_bar == self._l_used
        s_capped = cap and self._s_used is not None and seq.s_sos_bar == self._s_used

        l_armed = (
            cfg.exec_secondary
            and cfg.exec_longs
            and flat
            and seq.l_sos_bar is not None
            and be_sos_l == seq.l_sos_bar
            and seq.l_sos_bar != self._l_dead
            and not l_capped
            and sig.bull_div_active
            and sig.fibo_dir == 1
            and fibs_ready
            and self._l_hi is not None
            and self._l_lo is not None
            and self._l_hi > self._l_lo
            and (self._l_traded is None or self._l_leg != self._l_traded)
            and not late
            and (not long_veto or not respect_veto)
        )
        s_armed = (
            cfg.exec_secondary
            and cfg.exec_shorts
            and flat
            and seq.s_sos_bar is not None
            and be_sos_s == seq.s_sos_bar
            and seq.s_sos_bar != self._s_dead
            and not s_capped
            and sig.bear_div_active
            and sig.fibo_dir == -1
            and fibs_ready
            and self._s_hi is not None
            and self._s_lo is not None
            and self._s_hi > self._s_lo
            and (self._s_traded is None or self._s_leg != self._s_traded)
            and not late
            and (not short_veto or not respect_veto)
        )

        buf = cfg.exec_sl_buf_tk * cfg.mintick
        # `exec_sec_retrace` (default 0.382 — the constant this replaced, so the shipped path is
        # unchanged). 0.0 rests at the leg extreme, which is entering on the 1m SOS itself. The stop
        # is the leg ORIGIN either way, so a shallower ratio is a WIDER stop and a smaller position.
        ratio = cfg.exec_sec_retrace
        l_edge = (self._l_hi - (self._l_hi - self._l_lo) * ratio) if l_armed else None
        s_edge = (self._s_lo + (self._s_hi - self._s_lo) * ratio) if s_armed else None
        return SecArm(
            l_armed=l_armed,
            l_edge=l_edge,
            l_sl=(self._l_lo - buf) if l_armed else None,
            l_tp1=sig.fibo_p2,
            l_tp2=sig.fibo_p1,
            l_leg=self._l_leg,
            s_armed=s_armed,
            s_edge=s_edge,
            s_sl=(self._s_hi + buf) if s_armed else None,
            s_tp1=sig.fibo_p2,
            s_tp2=sig.fibo_p1,
            s_leg=self._s_leg,
        )

    def mark_traded(self, direction: int) -> None:
        """Retire the just-filled 1m leg (Pine `sec.lTraded := sec.lPend`) so it re-enters once.

        Also retires the 15m SOS bar for `exec_sec_once_per_setup`. The stamp is UNCONDITIONAL —
        the config is read at ARM time, not here — so flipping the cap on mid-run cannot find a
        half-filled latch, and the OFF path simply never looks at it."""
        if direction > 0:
            self._l_traded = self._l_leg
            self._l_used = self._l_sos
        else:
            self._s_traded = self._s_leg
            self._s_used = self._s_sos

    def mark_dead(self, direction: int, seq) -> None:
        """A re-entry on this 15m leg hit its initial stop — the leg is dead. No further re-entries
        on it until a new break of structure resets it (`seq.*_sos_bar` goes None / changes)."""
        if direction > 0:
            self._l_dead = seq.l_sos_bar
        else:
            self._s_dead = seq.s_sos_bar
