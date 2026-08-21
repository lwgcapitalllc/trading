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
    direction: int          # engine dir (Pine st1.dir): 1 up / -1 down / 0 undetermined
    new_bull_sos: bool      # a bull SOS fired on THIS 1m bar (the latched bar advanced)
    new_bear_sos: bool
    # The 1m engine's last CONFIRMED swing high/low. Read only by `exec_sec_stop="swing low"`;
    # None until the 1m engine has confirmed one, which refuses the arm rather than guessing.
    conf_high: Optional[float] = None
    conf_low: Optional[float] = None


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
        self.conf_high: Optional[float] = None
        self.conf_low: Optional[float] = None

    def update(self, index: int, o: float, h: float, l: float, c: float) -> M1State:
        st = self._engine.update(Bar(index=index, open=o, high=h, low=l, close=c))
        ext = st.external
        # The 1m engine's last CONFIRMED swing — the anchor `exec_sec_stop="swing low"` uses. It is
        # read straight off the same engine the SOS latch reads, so the two can never describe
        # different 1-minute structure.
        ch, cl = self._engine.last_confirmed_high, self._engine.last_confirmed_low
        self.conf_high = ch.price if ch is not None else None
        self.conf_low = cl.price if cl is not None else None

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
            bull_sos_bar=self.bull_sos_bar, bear_sos_bar=self.bear_sos_bar,
            bull_leg_hi=self.bull_leg_hi, bull_leg_lo=self.bull_leg_lo,
            bear_leg_hi=self.bear_leg_hi, bear_leg_lo=self.bear_leg_lo,
            direction=self._engine.dir, new_bull_sos=new_bull, new_bear_sos=new_bear,
            conf_high=self.conf_high, conf_low=self.conf_low,
        )


@dataclass(frozen=True)
class SecArm:
    """One 1m bar's secondary-arm result — what `Execution.step_secondary` needs to rest
    (or cancel) the sniper limit. `*_leg` is the 1m SOS bar the entry would trade, so the
    execution can retire that leg on a fill (each 1m leg re-enters at most once)."""

    l_armed: bool = False
    l_edge: Optional[float] = None      # resting BUY limit — 38.2% retrace of the 1m leg
    l_sl: Optional[float] = None        # stop = 1m leg origin (1.0) − buffer
    l_tp1: Optional[float] = None       # 15m fib 0.5
    l_tp2: Optional[float] = None       # 15m fib 0.382 (TP3 = runner)
    l_leg: Optional[int] = None
    s_armed: bool = False
    s_edge: Optional[float] = None
    s_sl: Optional[float] = None
    s_tp1: Optional[float] = None
    s_tp2: Optional[float] = None
    s_leg: Optional[int] = None
    # WHICH trigger latched this side — "1m shift" | "gap" | "reclaim", or None when nothing is
    # latched. Carried because the halves can be live together and want DIFFERENT exit ladders, so
    # the execution has to know which one it just filled. ⚠ Naming the source rather than testing
    # the config at the ladder is deliberate: the config can be read at any time, but the question
    # is what armed THIS trade, and a fourth trigger added later answers it the same way.
    l_src: Optional[str] = None
    s_src: Optional[str] = None


class SecondaryArm:
    """The secondary latch + arm state machine — a line-for-line port of the Pine WIP
    `f_secArm` (from the stashed secondary-trade branch). See `docs/MPC_SOS_FADE_SECONDARY.md`.

    Holds, per side, the latched 1m leg (`_leg` = its SOS bar, `_hi`/`_lo` = its 0.0/1.0
    anchors), the leg that has already re-entered (`_traded`, retired so it can't fire twice),
    and the 15m leg killed by a stopped re-entry (`_dead`). Each `update()` reads: the current
    1m structure (`M1State`), the last-closed 15m context (`sig` = Signals, `seq` = SeqState),
    whether the account is flat, and the primary's `be_sos_*` latches — and returns a `SecArm`.

    **Three eligibility rules beyond the zone (Aaron's spec):**
      - A live 15m RSI DIVERGENCE, gating both the latch and the arm. ⚠ Since 2026-08-20 this is
        `exec_sec_req_div` (default ON = the shipped rule) rather than a hardcoded read of
        `sig.*_div_active`. 🔴 It is NOT `exec_arm_div`, and confusing the two is what hid the
        feature: the PRIMARY ships sweep-armed with `exec_arm_div` OFF, so the re-entry was asking
        for a divergence the primary never needed, and could not fire at all on the shipped book.
        Aaron, 2026-08-20: *"Secondary trades, I don't care about divergence."*
      - The PRIMARY must have reached breakeven — hit at least TP1 (`be_sos == *_sos_bar`). A
        primary that opened and got stopped at its initial stop leaves NO re-entry on that leg.
        ⚠ Since 2026-08-19 this is the DEFAULT of `exec_sec_require` rather than the only rule —
        "Any close", "Stopped only" and "None" are the looser doors, and the swept-stop case
        (in at 0.618, stopped at 0.886, price reclaims and runs) is what "Stopped only" names.
        The zone edges are likewise `exec_sec_zone_shallow` / `exec_sec_zone_deep` now. Every
        default reproduces the shipped book exactly; see `_primary_gate` and `_zone_edges`.
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
        self._l_dead: Optional[int] = None      # 15m leg killed by a stopped re-entry (no more)
        self._l_used: Optional[int] = None      # 15m leg the cap is counting re-entries on
        self._l_used_n: int = 0                 # how many it has had (`exec_sec_max_per_setup`)
        self._s_leg: Optional[int] = None
        self._s_hi: Optional[float] = None
        self._s_lo: Optional[float] = None
        self._s_traded: Optional[int] = None
        self._s_dead: Optional[int] = None
        self._s_used: Optional[int] = None
        self._s_used_n: int = 0
        # The RECLAIM half's per-side state — live whenever `exec_sec_trigger` names it, alone
        # or combined with the gap.
        # `_seen` = the primary gate was already open on an EARLIER 1m bar, so a reclaim needs a
        # bar of its own rather than firing on the stop-out bar's own upper wick. `_rec` = price
        # has since traded back through the deep edge. `_void` = price reached the stop anchor
        # first, so this setup's re-entry is finished. All three clear with the setup.
        self._l_seen = self._s_seen = False
        self._l_rec = self._s_rec = False
        self._l_void = self._s_void = False
        # The 15m SOS bar each side is currently arming against, captured in `update()` because
        # `mark_traded` is called by the driver without `seq` in hand.
        self._l_sos: Optional[int] = None
        self._s_sos: Optional[int] = None

    def update(self, m1: M1State, sig, seq, zone_close: float, ny_hour: int,
               flat: bool, be_sos_l: Optional[int],
               be_sos_s: Optional[int],
               closed_sos_l: Optional[int] = None, closed_sos_s: Optional[int] = None,
               lost_sos_l: Optional[int] = None, lost_sos_s: Optional[int] = None,
               poi_edge_l: Optional[float] = None,
               poi_edge_s: Optional[float] = None,
               bar_high: Optional[float] = None,
               bar_low: Optional[float] = None) -> SecArm:
        cfg = self._cfg
        _trig = getattr(cfg, "exec_sec_trigger", "1m shift")
        # Both may be true at once under the combined value. They stay two independent booleans
        # rather than one mode, so every block below reads the question it actually cares about
        # ("is the gap half live") instead of enumerating which combined values include it — the
        # shape that would need editing again the next time a value is added.
        gap_trigger = _trig in ("FVG in zone", "FVG in zone + Deep-edge reclaim")
        rec_trigger = _trig in ("Deep-edge reclaim", "FVG in zone + Deep-edge reclaim")

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
            self._l_used_n = 0
            self._l_seen = self._l_rec = self._l_void = False
        if seq.s_sos_bar is None:
            self._s_leg = self._s_hi = self._s_lo = None
            self._s_dead = None
            self._s_used = None
            self._s_used_n = 0
            self._s_seen = self._s_rec = self._s_void = False

        # 2. Zone (0.886..0.618 of the 15m fib) — a 15m gate: Pine reads the last-closed 15m bar
        #    `close`, so `zone_close` is that bar's close (NOT the live 1m close, which the 1m SOS
        #    has usually left by the time it confirms). See the class docstring.
        p3, p6 = sig.fibo_p3, sig.fibo_p6
        # The zone EDGES (`exec_sec_zone_shallow` / `exec_sec_zone_deep`). At the shipped
        # 0.618/0.886 these read `fibo_p3` / `fibo_p6` themselves rather than recomputing them
        # from the leg, so the default path cannot move by a floating-point rounding step — the
        # thing that would make a control run disagree with every stored figure for no reason.
        z_lo, z_hi = self._zone_edges(sig)
        zone_l = (sig.fibo_dir == 1 and z_lo is not None and z_hi is not None
                  and zone_close <= z_lo and zone_close >= z_hi)
        zone_s = (sig.fibo_dir == -1 and z_lo is not None and z_hi is not None
                  and zone_close >= z_lo and zone_close <= z_hi)

        # The 15m DIVERGENCE requirement (`exec_sec_req_div`). Gates the latch AND the arm, because
        # the Pine WIP tested it in both places. ON (default) = the shipped rule exactly; OFF asks
        # only that the 15m setup itself is live, which is the state a sweep-armed book is in.
        # ⚠ This is NOT `exec_arm_div` — that one says what may ARM THE PRIMARY. A sweep-armed
        # primary paired with this ON is a re-entry that can never fire; see the config comment.
        req_div = getattr(cfg, "exec_sec_req_div", True)
        div_l = sig.bull_div_active or not req_div
        div_s = sig.bear_div_active or not req_div


        # What the PRIMARY on this leg must have done (`exec_sec_require`). Computed HERE rather
        # than at the arm because the RECLAIM trigger below keys its whole state machine off the
        # moment this gate opens — under the shipped "Breakeven" default it is read once, at the
        # arm, exactly as before.
        gate_l = self._primary_gate(seq.l_sos_bar, be_sos_l, closed_sos_l, lost_sos_l)
        gate_s = self._primary_gate(seq.s_sos_bar, be_sos_s, closed_sos_s, lost_sos_s)
        # The RECLAIM half asks its OWN question (`exec_rec_require`, default "Stopped only"), so
        # the two halves can be live together wanting opposite things of the primary. Under the
        # combined value config validation has already refused any pairing but Breakeven/Stopped
        # only, which is what makes the shared latch below safe.
        if rec_trigger:
            rmode = getattr(cfg, "exec_rec_require", "Stopped only")
            rgate_l = self._primary_gate(seq.l_sos_bar, be_sos_l, closed_sos_l, lost_sos_l, rmode)
            rgate_s = self._primary_gate(seq.s_sos_bar, be_sos_s, closed_sos_s, lost_sos_s, rmode)
        else:
            rgate_l = rgate_s = False

        # 2c. THE RECLAIM TRIGGER — no 1m structure event and no gap. The case it names is the one
        #     the geometry points at: the primary was stopped at the deep edge, price did NOT go on
        #     to break the leg, and instead came back through that level. The re-entry is then a
        #     resting limit AT the deep edge with the stop at whatever `exec_sec_stop` names, so
        #     the risk is the deep-edge-to-stop gap rather than the primary's full stop distance.
        #
        #     🔴 THE WAIT IS THE WHOLE EDGE, NOT AN IMPLEMENTATION DETAIL. Measured over 7.9 years
        #     on the 1m stream: resting a limit back at the level earned +43.0R over 53 re-entries,
        #     while entering on the reclaim bar's close earned +0.0R over 56. Same setups, same
        #     stop, same target — only the wait differs. Do not "improve" this into a market entry.
        #
        #     ⚠ THREE THINGS IT DELIBERATELY DOES NOT DO, each of which would silence it:
        #     - It does NOT require the zone. The zone reads the last-closed 15m bar's close, and a
        #       primary is stopped at the deep edge precisely by a 15m bar closing THROUGH it, so
        #       the zone gate is usually false at the only moment this trigger can fire.
        #     - It does NOT fire on the bar the gate opens (`_seen`). On the stop-out bar price is
        #       at the level by definition, and that bar's own wick back through it is the stop
        #       being hit, not a reclaim.
        #     - It arms ONCE per setup and then voids on the stop anchor. If price reaches the stop
        #       level before the retest fills, the leg is finished — a resting limit whose stop is
        #       already breached is not a trade anyone would take.
        if rec_trigger:
            deep_l, deep_s = z_hi, z_hi
            # ⚠ Read HERE rather than from the shared `l_stop`/`s_stop` below, and the difference
            # is not cosmetic. That pair is computed AFTER the 1m leg latch because the shipped
            # "1m leg" anchor reads the leg latched on THIS bar — hoisting it broke every 1m-shift
            # test in this file. This trigger needs its anchor one step early, and may only ask
            # for it because config validation refuses "1m leg" and "swing low" against it, so
            # both of its legal anchors are pure reads of the 15m fib.
            rec_stop_l, rec_stop_s = self._stop_anchor(
                m1, sig, getattr(cfg, "exec_rec_stop", "1.0"))
            for side in (1, -1):
                sos = seq.l_sos_bar if side > 0 else seq.s_sos_bar
                gate = rgate_l if side > 0 else rgate_s
                deep = deep_l if side > 0 else deep_s
                stop = rec_stop_l if side > 0 else rec_stop_s
                if sos is None or not gate or deep is None:
                    continue
                seen = self._l_seen if side > 0 else self._s_seen
                if seen and bar_high is not None and bar_low is not None:
                    # Voided by the stop anchor, else reclaimed by trading back through the edge.
                    if stop is not None and ((bar_low <= stop) if side > 0 else (bar_high >= stop)):
                        if side > 0:
                            self._l_void = True
                        else:
                            self._s_void = True
                    elif (bar_high > deep) if side > 0 else (bar_low < deep):
                        if side > 0:
                            self._l_rec = True
                        else:
                            self._s_rec = True
                if side > 0:
                    self._l_seen = True
                else:
                    self._s_seen = True
            # The "leg" is the SETUP, keyed on its 15m SOS bar, so `_traded` / `_dead` / `_used`
            # all keep working unchanged — the same shape the gap trigger uses.
            if seq.l_sos_bar is not None and div_l and self._l_rec and not self._l_void:
                self._l_leg, self._l_hi, self._l_lo = seq.l_sos_bar, None, None
            if seq.s_sos_bar is not None and div_s and self._s_rec and not self._s_void:
                self._s_leg, self._s_hi, self._s_lo = seq.s_sos_bar, None, None

        # 3. Latch a fresh 1m leg on a new same-side 1m SOS while the 15m setup (+ div) are live.
        #
        #    🔴 IT RUNS UNDER EVERY TRIGGER, INCLUDING THE ONES THAT DO NOT USE A 1m LEG, AND THAT
        #    IS THE SHIPPED BEHAVIOUR — do not "tidy" it behind a trigger test. Under the gap or the
        #    reclaim this latch still moves `_l_leg`, which `_traded` / `_dead` / `_used` all read,
        #    so gating it changes which setups may re-enter. It was gated twice during this build
        #    and the control replay caught both: the shipped book went 54 re-entries to 58 the first
        #    time, and the second time it left the combined book's two halves behaving differently
        #    from the same halves run alone. What this latch does NOT do is decide the PRICE.
        if (cfg.exec_secondary and m1.new_bull_sos and seq.l_sos_bar is not None
                and div_l and zone_l
                and m1.bull_leg_hi is not None and m1.bull_leg_lo is not None
                and m1.bull_leg_hi > m1.bull_leg_lo):
            self._l_leg, self._l_hi, self._l_lo = m1.bull_sos_bar, m1.bull_leg_hi, m1.bull_leg_lo
        if (cfg.exec_secondary and m1.new_bear_sos and seq.s_sos_bar is not None
                and div_s and zone_s
                and m1.bear_leg_hi is not None and m1.bear_leg_lo is not None
                and m1.bear_leg_hi > m1.bear_leg_lo):
            self._s_leg, self._s_hi, self._s_lo = m1.bear_sos_bar, m1.bear_leg_hi, m1.bear_leg_lo

        # 3b. THE GAP TRIGGER — no 1m structure event at all. While the setup is alive and the
        #     last-closed 15m bar sits in the zone, the "leg" is the SETUP (keyed on its 15m SOS
        #     bar, so `_traded` / `_dead` / `_used` all keep working unchanged) and the entry is
        #     the PRIMARY's own point-of-interest price. Nothing here recomputes the gap rules.
        #
        #
        #     ⚠ UNGATED, exactly as it ships, and under the combined value too. Gating it on the
        #     gap half's own precondition was tried — to stop it latching a stopped setup out from
        #     under the reclaim — and it works, but it costs the gap half 7 of its 54 re-entries
        #     when the reclaim is switched on, because a latch that arrives later shifts the
        #     one-per-setup bookkeeping. The reclaim protects itself instead, by asking whether
        #     price actually reclaimed rather than whether something latched (see `_leg_ok`), which
        #     leaves BOTH halves behaving exactly as they do alone.
        if gap_trigger:
            if seq.l_sos_bar is not None and div_l and zone_l and poi_edge_l is not None:
                self._l_leg, self._l_hi, self._l_lo = seq.l_sos_bar, None, None
            if seq.s_sos_bar is not None and div_s and zone_s and poi_edge_s is not None:
                self._s_leg, self._s_hi, self._s_lo = seq.s_sos_bar, None, None

        # The stop anchor (`exec_sec_stop`). "1m leg" is the shipped rule and reads the latched 1m
        # leg origin; the other three are 15m/1m anchors the gap trigger needs, since it has no leg.
        l_stop, s_stop = self._stop_anchor(m1, sig)
        # Everything from here is keyed on WHICH half OWNS this side, resolved just below. Under
        # a single trigger that is the trigger; under the combined value it is whichever
        # precondition is open, and `None` when neither is.
        # 🔴 WHICH RULE PRICES A SIDE IS DECIDED BY THE CONFIGURED TRIGGER — and when both halves
        # are configured, by WHICH PRECONDITION IS OPEN. Never by whichever block latched last.
        #
        # Two control replays were needed to arrive at that. Keying it off the latch let a 1m
        # structure event price a GAP book at a 1-minute retrace (+4 re-entries and +4.9R on the
        # SHIPPED book). Suppressing the 1m latch to stop that then made the combined book's halves
        # behave differently from the same halves run alone — 22 gap re-entries and 9 reclaims
        # moved to a different minute, which reads as "combining changed things" when it was the
        # fix that changed them.
        #
        # The precondition answers it cleanly because at most one gate can be open on a setup: a
        # primary either reached TP1 or closed at stage 0. So each half prices exactly the setups
        # it would have priced alone, and the shared latch is left doing only what it always did.
        def _src_for(rgate, gate):
            if gap_trigger and rec_trigger:
                # Validation has already refused any pairing where both could be true at once.
                return "reclaim" if rgate else ("gap" if gate else None)
            if rec_trigger:
                return "reclaim"
            if gap_trigger:
                return "gap"
            return "1m shift"

        l_src = _src_for(rgate_l, gate_l)
        s_src = _src_for(rgate_s, gate_s)
        l_from_rec = l_src == "reclaim"
        s_from_rec = s_src == "reclaim"
        if l_from_rec or s_from_rec:
            # The reclaim's stop is its OWN anchor (`exec_rec_stop`), which under the combined
            # value is a different level from the gap half's. Resolved per side so one half's
            # setting can never price the other half's trade.
            r_stop_l, r_stop_s = self._stop_anchor(m1, sig, getattr(cfg, "exec_rec_stop", "1.0"))
            if l_from_rec:
                l_stop = r_stop_l
            if s_from_rec:
                s_stop = r_stop_s
        # Whether the arm has a usable leg. The 1m trigger needs its latched leg to be valid and
        # pointing the right way; the other two need an entry price and a stop, and ask the SAME
        # question of both so a missing anchor can never read as "no setup".
        #
        # ⚠ Resolved PER SIDE, never once for both. Under the combined value the long side can be
        # owned by the reclaim while the short side is owned by the gap, and one shared branch
        # would price one of them off the other's rule. `sig.fibo_dir` means only one side can arm
        # at a time, so today that could not reach a fill — which is exactly the kind of "cannot
        # happen yet" that stops being true quietly.
        def _leg_ok(src, leg, hi, lo, stop, poi, side):
            if leg is None or stop is None or src is None:
                # `src is None` = both halves live and NEITHER precondition is open. Refuse rather
                # than fall through to the 1m rule below, which would enter at a retrace of a
                # 1-minute leg — a trigger nobody selected.
                return False
            if src == "reclaim":
                # The entry price IS the deep edge: is there an entry, and is the stop the right
                # side of it — AND has price actually come back through the level.
                #
                # 🔴 THAT LAST CLAUSE READS THE RECLAIM'S OWN STATE RATHER THAN "SOMETHING LATCHED
                # THIS SIDE", AND THE DISTINCTION IS THE WHOLE RULE. `_l_leg` is shared bookkeeping
                # that three different blocks write, so treating a latch as proof of a reclaim lets
                # any of them arm this half a bar before price returned. It was guarded at the gap
                # latch first, which worked and cost the gap half 7 of its 54 re-entries under the
                # combined value — a fix in the wrong place, paid for by the other half.
                rec = (self._l_rec if side > 0 else self._s_rec)
                void = (self._l_void if side > 0 else self._s_void)
                return (rec and not void and z_hi is not None
                        and (z_hi > stop if side > 0 else z_hi < stop))
            if src == "gap":
                return poi is not None and (poi > stop if side > 0 else poi < stop)
            return hi is not None and lo is not None and hi > lo

        l_leg_ok = _leg_ok(l_src, self._l_leg, self._l_hi, self._l_lo,
                           l_stop, poi_edge_l, 1)
        s_leg_ok = _leg_ok(s_src, self._s_leg, self._s_hi, self._s_lo,
                           s_stop, poi_edge_s, -1)

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
        # How many re-entries one setup may have (`exec_sec_max_per_setup`, default 1 = the
        # shipped cap). The dead-leg rule below is unaffected and is NOT a count: a re-entry that
        # stops out ends the leg whatever this is, so a deeper cascade runs through SCRATCHES only.
        depth = getattr(cfg, "exec_sec_max_per_setup", 1)
        l_capped = (cap and self._l_used is not None and seq.l_sos_bar == self._l_used
                    and self._l_used_n >= depth)
        s_capped = (cap and self._s_used is not None and seq.s_sos_bar == self._s_used
                    and self._s_used_n >= depth)

        # The 1m engine's own DIRECTION, optionally required to agree (`exec_sec_req_m1_dir`).
        # OFF by default = the shipped rule, which reads the 1m SOS events and ignores direction.
        m1_ok_l = (not getattr(cfg, "exec_sec_req_m1_dir", False)) or m1.direction == 1
        m1_ok_s = (not getattr(cfg, "exec_sec_req_m1_dir", False)) or m1.direction == -1
        # The precondition the ARM checks follows the source too: a reclaim-latched side is
        # answerable to `exec_rec_require`, everything else to the shared one. Under every
        # single-trigger value these are the same object, so nothing shipped moves.
        arm_gate_l = rgate_l if l_from_rec else gate_l
        arm_gate_s = rgate_s if s_from_rec else gate_s
        l_armed = (cfg.exec_secondary and cfg.exec_longs and flat and m1_ok_l
                   and not (l_from_rec and self._l_void)
                   and seq.l_sos_bar is not None and arm_gate_l
                   and seq.l_sos_bar != self._l_dead and not l_capped
                   and div_l and sig.fibo_dir == 1 and fibs_ready
                   and l_leg_ok
                   and (self._l_traded is None or self._l_leg != self._l_traded)
                   and not late and (not long_veto or not respect_veto))
        s_armed = (cfg.exec_secondary and cfg.exec_shorts and flat and m1_ok_s
                   and not (s_from_rec and self._s_void)
                   and seq.s_sos_bar is not None and arm_gate_s
                   and seq.s_sos_bar != self._s_dead and not s_capped
                   and div_s and sig.fibo_dir == -1 and fibs_ready
                   and s_leg_ok
                   and (self._s_traded is None or self._s_leg != self._s_traded)
                   and not late and (not short_veto or not respect_veto))

        buf = cfg.exec_sl_buf_tk * cfg.mintick
        # `exec_sec_retrace` (default 0.382 — the constant this replaced, so the shipped path is
        # unchanged). 0.0 rests at the leg extreme, which is entering on the 1m SOS itself. The stop
        # is the leg ORIGIN either way, so a shallower ratio is a WIDER stop and a smaller position.
        ratio = cfg.exec_sec_retrace
        # Per side off the SOURCE, same reasoning as `_leg_ok` above.
        #   "reclaim" — the deep edge itself, the level the primary was stopped at and price has
        #               since reclaimed. No retrace of anything, because there is no 1m leg.
        #   "gap"     — the primary's own resting price, likewise no leg to retrace.
        def _edge(src, armed, hi, lo, poi, side):
            if not armed or src is None:
                return None
            if src == "reclaim":
                return z_hi
            if src == "gap":
                return poi
            return (hi - (hi - lo) * ratio) if side > 0 else (lo + (hi - lo) * ratio)

        l_edge = _edge(l_src, l_armed, self._l_hi, self._l_lo, poi_edge_l, 1)
        s_edge = _edge(s_src, s_armed, self._s_hi, self._s_lo, poi_edge_s, -1)
        return SecArm(
            l_armed=l_armed, l_edge=l_edge,
            l_sl=(l_stop - buf) if l_armed else None,
            l_tp1=sig.fibo_p2, l_tp2=sig.fibo_p1, l_leg=self._l_leg,
            s_armed=s_armed, s_edge=s_edge,
            s_sl=(s_stop + buf) if s_armed else None,
            s_tp1=sig.fibo_p2, s_tp2=sig.fibo_p1, s_leg=self._s_leg,
            l_src=l_src if l_armed else None,
            s_src=s_src if s_armed else None,
        )

    def _stop_anchor(self, m1: M1State, sig, mode=None):
        """(long stop, short stop) before the buffer — `exec_sec_stop`.

        `mode` overrides the config field, which is how the RECLAIM half reads its own anchor
        (`exec_rec_stop`) while the gap half reads the shared one. None = read the config.

        Returns None on a side whose anchor does not exist yet (no latched 1m leg, no confirmed 1m
        swing, no fib). ⚠ None must stay None: falling back to another anchor would price the trade
        off a level the operator did not choose, and this repo's sizing is `risk / stop_distance`.
        """
        if mode is None:
            mode = getattr(self._cfg, "exec_sec_stop", "1m leg")
        if mode == "1m leg":
            return self._l_lo, self._s_hi
        if mode == "swing low":
            return m1.conf_low, m1.conf_high
        if mode == "0.886":
            return sig.fibo_p6, sig.fibo_p6
        if mode == "1.0":
            return sig.fibo_p10, sig.fibo_p10
        raise ValueError(
            f"exec_sec_stop must be one of ['0.886', '1.0', '1m leg', 'swing low'], got {mode!r}")

    def _zone_edges(self, sig):
        """(shallow, deep) prices of the 15m retrace zone the re-entry may arm in.

        Returns `fibo_p3` / `fibo_p6` UNCHANGED at the shipped 0.618 / 0.886 — the levels the
        signal already publishes — and only computes off the leg for any other ratio. Two ways of
        producing the same number would otherwise differ in the last bits and make a control run
        disagree with itself. The leg is `fibo_p7` (0.0, the extreme) → `fibo_p10` (1.0, origin),
        which is the same anchor pair every other ratio here is priced from.
        """
        cfg = self._cfg
        shallow = getattr(cfg, "exec_sec_zone_shallow", 0.618)
        deep = getattr(cfg, "exec_sec_zone_deep", 0.886)
        lo = sig.fibo_p3 if shallow == 0.618 else self._lvl(sig, shallow)
        hi = sig.fibo_p6 if deep == 0.886 else self._lvl(sig, deep)
        return lo, hi

    @staticmethod
    def _lvl(sig, ratio: float):
        p7, p10 = sig.fibo_p7, sig.fibo_p10
        if p7 is None or p10 is None:
            return None
        return p7 + (p10 - p7) * ratio

    def _primary_gate(self, sos, be_sos, closed_sos, lost_sos, mode=None) -> bool:
        """What the PRIMARY on this 15m leg must have done — `exec_sec_require`.

        `mode` overrides the config field, which is how the RECLAIM half asks its own question
        (`exec_rec_require`) while the gap half asks the shared one. None = read the config, which
        is every caller that existed before the combined trigger.

        "Breakeven" is the shipped rule and is byte-identical to the `be_sos == sos` test it
        replaced. The other three are looser doors onto the same latch machinery: the dead-leg
        rule and `exec_sec_once_per_setup` still bound every one of them.

        ⚠ An unknown value REFUSES rather than falling through to the loosest reading. A typo
        that quietly armed on every live setup would be indistinguishable, on the page, from the
        strategy having found a lot of re-entries.
        """
        if mode is None:
            mode = getattr(self._cfg, "exec_sec_require", "Breakeven")
        if mode == "Breakeven":
            return be_sos == sos
        if mode == "Any close":
            return closed_sos == sos
        if mode == "Stopped only":
            return lost_sos == sos
        if mode == "None":
            return True
        raise ValueError(
            f"exec_sec_require must be one of ['Any close', 'Breakeven', 'None', "
            f"'Stopped only'], got {mode!r}")

    def mark_traded(self, direction: int) -> None:
        """Retire the just-filled 1m leg (Pine `sec.lTraded := sec.lPend`) so it re-enters once.

        Also retires the 15m SOS bar for `exec_sec_once_per_setup`. The stamp is UNCONDITIONAL —
        the config is read at ARM time, not here — so flipping the cap on mid-run cannot find a
        half-filled latch, and the OFF path simply never looks at it."""
        if direction > 0:
            self._l_traded = self._l_leg
            self._l_used_n = (self._l_used_n + 1) if self._l_used == self._l_sos else 1
            self._l_used = self._l_sos
        else:
            self._s_traded = self._s_leg
            self._s_used_n = (self._s_used_n + 1) if self._s_used == self._s_sos else 1
            self._s_used = self._s_sos

    def mark_dead(self, direction: int, seq) -> None:
        """A re-entry on this 15m leg hit its initial stop — the leg is dead. No further re-entries
        on it until a new break of structure resets it (`seq.*_sos_bar` goes None / changes)."""
        if direction > 0:
            self._l_dead = seq.l_sos_bar
        else:
            self._s_dead = seq.s_sos_bar
