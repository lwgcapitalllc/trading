"""dual_clock.py — the ONE implementation of *which bar is stepped when* when the primary
(15m) and the re-entry's fill clock run side by side.

**Why this file exists at all.** The merge was written once, inside
`MpcSosFadeStrategy.run_dual`, and the live runner needs exactly the same rule. Writing it a
second time in `algos/live/runner.py` is the shape this repo has already been bitten by twice
(the run-form visibility evaluator and `stress_tester.param_is_reachable` disagreed in silence;
the ruff carve-out lived in somebody's memory of what they had reverted). **The merge ORDER is
the part that is easy to get wrong and impossible to see afterwards** — a fast bar stepped
against the wrong 15m context produces a perfectly ordinary-looking trade at a slightly wrong
price, forever. So there is one implementation and both drivers push bars into it.

**The rule, in one sentence.** Bars are timestamped at their OPEN, so a 15m bar opening at `t`
is only KNOWN at `t + 15m`; a fast bar opening at `X` may therefore be stepped once every 15m
bar whose CLOSE is `<= X` has been stepped, and not before. That is `lookahead_off`: the fast
bar reads the 15m context of the bar that has already closed by the time it opens.

**What each driver does differently, and it is only the arrival of bars.** The lab has both
frames complete up front and pushes every 15m bar before it steps a single fast one. The live
runner receives them from two `BarFeed`s that poll independently, so it can hold a fast bar the
15m stream has not caught up to — `covered_to_ms` / `can_step_fast` are for that caller and are
a no-op for the lab. ⚠ **Neither driver may reorder bars itself**: push them in time order per
frame and let `step_fast` decide.

⚠ **THE SECOND FRAME IS NOT A MINUTE.** It is `exec_sec_fill_tf_min`, 5 minutes by default since
2026-08-21 and the caller's choice. `run_dual`'s parameter is still named `df1m` because
renaming a public parameter moves every caller, and its own docstring says that name cannot be
trusted. Nothing in this file assumes a minute, and nothing in it may start to — read
`fast_tf_name` / `exec_sec_fill_tf_min`, never a hardcoded 60 seconds.
"""

from __future__ import annotations

from collections import namedtuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional
from zoneinfo import ZoneInfo

from .secondary import SecondaryArm, Structure1m

_NY = ZoneInfo("America/New_York")


class FastBarOutOfOrder(RuntimeError):
    """A fast bar arrived AFTER the 15m context had already moved past it.

    🔴 **This is refused rather than absorbed, and the refusal is the whole point.** Stepping it
    anyway would let that bar read a 15m context from its own future — a re-entry armed on
    information the market had not published yet, which produces an ordinary-looking trade at a
    price nothing can later show to be wrong. The live caller catches this and re-warms the fast
    side; the lab can never raise it, because it pushes every primary bar before it steps a
    single fast one.
    """

# `last_conf_high`/`last_conf_low` are the STRUCTURE runner trail's anchors, read by the shared
# `_advance_stage` on every managed bar — primary or secondary. They were missing from the
# original `run_dual` until 2026-08-06, so the FIRST fast bar after any secondary fill raised
# `AttributeError`: the re-entry had never once opened a position on real data. They come from
# the last-CLOSED 15m signal, deliberately: the secondary's whole ladder is 15m fibs and it
# shares the parent's exit ladder, so its runner must trail the same 15m confirmed swings the
# primary does. `Structure1m` is for the fast-feed SOS latch only.
FastSig = namedtuple(
    "FastSig", "index time_ms open high low close last_conf_high last_conf_low")


@dataclass
class PrimaryStep:
    """One 15m bar that has been stepped through the primary path."""

    bar: Any
    sig: Any
    seq: Any
    dec: Any


@dataclass
class FastStep:
    """One fast bar's pass, plus every 15m bar that was flushed IN FRONT of it.

    `primaries` is ordered and comes first in wall-clock terms — a caller mirroring intent onto
    a broker must act on those before it acts on anything in this record, or it reports last
    bar's decision beside this bar's price.
    """

    bar: Any
    primaries: List[PrimaryStep] = field(default_factory=list)
    # The `SecArm` this bar produced, or None when the secondary did not run (switched off, or
    # no 15m context yet). ⚠ None means NOT ASKED, never "nothing armed" — a `SecArm` with both
    # sides false is what "nothing armed" looks like. Rule 1.
    arm: Any = None
    # +1 / -1 when a re-entry FILLED on this bar in the emulator, else None.
    filled_dir: Optional[int] = None
    # +1 / -1 when a re-entry hit its initial stop on this bar, else None.
    stopped_dir: Optional[int] = None


class DualClock:
    """Owns the merge, the fast-frame structure feed and the arm state machine.

    Build one per strategy instance. It holds the same three objects `run_dual` used to build
    inline — `Structure1m`, `SecondaryArm`, and the queue of 15m bars waiting to be flushed —
    and nothing else. It does NOT own the engine stack: the caller already has one (the lab
    builds it per run, the live runner rebuilds it on every re-warm) and two would drift.
    """

    # Reachable off the instance, so a driver can catch it without importing this module. The
    # live runner deliberately knows nothing about where the merge lives — see the note in
    # `algos/live/runner.py` about `algos/live/` holding no trading logic.
    OutOfOrder = FastBarOutOfOrder

    def __init__(self, strategy, stack, *, tf_primary_ms: int, major_length: int = 15) -> None:
        self._st = strategy
        self._stack = stack
        self._tf_primary_ms = int(tf_primary_ms)
        self._major_length = int(major_length)
        self.struct_fast = Structure1m(major_length=major_length)
        self.arm_sm = SecondaryArm(strategy.config)

        # The last-CLOSED 15m context. `None` until the first 15m bar has been stepped, and the
        # secondary refuses to run until then — a fast bar with no 15m context behind it has
        # nothing to arm against, and inventing an empty one would be rule 1 exactly.
        self.last_sig: Any = None
        self.last_seq: Any = None
        # The last-CLOSED 15m bar's close. The zone gate reads THIS, not the fast bar's close —
        # see `SecondaryArm`'s docstring on why the zone is a 15m gate.
        self.last_close_primary: Optional[float] = None

        self._queue: List[Any] = []      # 15m bars pushed but not yet due
        self._covered_to_ms: Optional[int] = None   # close time of the newest 15m bar pushed
        # The CLOSE time of the newest 15m bar actually STEPPED. Different from `_covered_to_ms`,
        # which is about what has been PUSHED — and the difference is exactly what the live
        # driver's eager drain creates. Any fast bar opening before this is stale.
        self.stepped_primary_to_ms: Optional[int] = None

    # ── pushing bars in ──────────────────────────────────────────────────────

    def push_primary(self, bar) -> None:
        """Queue one CLOSED 15m bar. It is stepped when a fast bar reaches its close time, or
        by `drain_primary()` at the end of a window."""
        self._queue.append(bar)
        self._covered_to_ms = int(bar.timestamp_ms) + self._tf_primary_ms

    @property
    def covered_to_ms(self) -> Optional[int]:
        """The instant the 15m stream is complete up to. `None` = nothing pushed yet."""
        return self._covered_to_ms

    def can_step_fast(self, ts_ms: int) -> bool:
        """May a fast bar opening at `ts_ms` be stepped yet?

        🔴 **For the LIVE caller, and it is the whole reason this method is public.** The lab
        pushes every 15m bar before the first fast one, so this is always True for it. Live,
        two feeds poll independently and the fast one can arrive first — stepping it then would
        read the 15m context of the bar BEFORE the one it should, which is the silent
        mis-execution this whole file exists to prevent. The live runner buffers instead.

        ⚠ It answers *is the 15m stream caught up*, never *is there a hole in it*. A hole is a
        different market history and is handled by the re-warm, not here.

        🔴 **THE TEST IS `< covered_to + one primary bar`, NOT `<= covered_to`, AND THE
        DIFFERENCE IS A DEADLOCK.** The question is *have all 15m bars CLOSING at or before `X`
        been pushed*, not *has the stream reached X*. With 15m primaries and a 5m fill clock, a
        fast bar opening at 3900 needs the 15m bar closing at 3600 and nothing later — the next
        one closes at 4500, which is after it, so the merge would not flush it in front. The
        stricter form made that bar WAIT for the 15m bar closing at 4500, which then advanced the
        context past it and made it permanently stale: it could never be stepped at all. **Two
        thirds of every fast bar hit that**, and it was found by tracing a refusal rather than by
        reading the rule, which is why the trace is written down here.

        ⚠ **AND IT IS STILL NOT THE WHOLE STORY, WHICH IS WHY THE LIVE CALLER HAS A SECOND
        MECHANISM.** `covered_to + one primary bar` assumes primary bars are CONTIGUOUS, and gold
        breaks daily. Across that break the next 15m bar is not one bar later, so a fast bar can
        sit here waiting while the post-break primary is pushed straight past it. The live driver
        therefore also calls `LiveRunner.flush_fast_before(close)` immediately before it pushes a
        primary bar, which asks the merge rule directly — *does this bar open before the primary I
        am about to push* — and needs no assumption about spacing at all. **Read this gate as the
        cheap common case and that call as the correct one.**
        """
        if self._covered_to_ms is None:
            # 🔴 **NOTHING PUSHED YET, SO NOTHING CAN BE SAID — and this refuses rather than
            # allowing.** With no primary bar in hand there is no way to know whether one is
            # about to arrive that belongs IN FRONT of this fast bar, and stepping it on a guess
            # is the lookahead this class exists to prevent. Live it means *the warm-up has not
            # run yet*, which is the only moment it can happen — `warm()` pushes the whole
            # primary history before the fast side is warmed at all. Rule 1: cannot-tell is not
            # a yes.
            return False
        return int(ts_ms) < self._covered_to_ms + self._tf_primary_ms

    # ── stepping ─────────────────────────────────────────────────────────────

    def fast_bar_is_stale(self, ts_ms: int) -> bool:
        """Has the 15m context already moved past a fast bar opening at `ts_ms`?

        Live only, in practice. The live driver steps a 15m bar the moment it closes rather than
        waiting for a fast bar to reach it — the primary is the trade with real money and a stop
        to manage, and it must never be held up by the re-entry's feed. The cost of that choice
        is this: a fast bar that turns up late has missed its slot, and there is no honest way to
        step it.
        """
        return (self.stepped_primary_to_ms is not None
                and int(ts_ms) < self.stepped_primary_to_ms)

    def step_fast(self, bar) -> FastStep:
        """Flush every 15m bar that has CLOSED by this fast bar's open, then step the secondary.

        Order is the contract: the 15m bars come first and their output becomes the context the
        secondary reads on this same call.
        """
        out = FastStep(bar=bar)
        ts = int(bar.timestamp_ms)
        if self.fast_bar_is_stale(ts):
            raise FastBarOutOfOrder(
                f"fast bar opening at {ts} arrived after the 15m context had advanced to "
                f"{self.stepped_primary_to_ms}. Stepping it would read a context from its own "
                f"future. Re-warm the fast feed instead."
            )
        while self._queue and (int(self._queue[0].timestamp_ms) + self._tf_primary_ms) <= ts:
            out.primaries.append(self._step_primary(self._queue.pop(0)))

        # EVERY fast bar, unconditionally — the fast structure engine is a streaming state
        # machine, so skipping a bar because the secondary is switched off would leave it
        # computing over a history that never happened the moment it was switched on.
        m1 = self.struct_fast.update(bar.index, bar.open, bar.high, bar.low, bar.close)

        if not self._st.config.exec_secondary or self.last_sig is None:
            return out

        ex = self._st.execution
        ny_hour = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).astimezone(_NY).hour
        arm = self.arm_sm.update(
            m1, self.last_sig, self.last_seq, self.last_close_primary, ny_hour,
            ex.is_flat, ex.be_sos_l, ex.be_sos_s,
            ex.prim_closed_sos_l, ex.prim_closed_sos_s,
            ex.prim_lost_sos_l, ex.prim_lost_sos_s,
            ex._poi_edge_l, ex._poi_edge_s,
            bar.high, bar.low,
        )
        out.arm = arm
        sig_fast = FastSig(bar.index, ts, bar.open, bar.high, bar.low, bar.close,
                           self.last_sig.last_conf_high, self.last_sig.last_conf_low)
        filled = ex.step_secondary(sig_fast, arm)
        if filled is not None:
            self.arm_sm.mark_traded(filled)     # retire the just-filled leg
            out.filled_dir = filled
        elif ex.sec_stop_dir is not None:
            # a re-entry hit its initial stop → kill this 15m leg (no more re-entries)
            self.arm_sm.mark_dead(ex.sec_stop_dir, self.last_seq)
            out.stopped_dir = ex.sec_stop_dir
        return out

    def warm_fast_bar(self, bar) -> None:
        """Feed one HISTORICAL fast bar to the fast structure engine and nothing else.

        🔴 **It deliberately does not arm, price or fill anything.** The primary's warm-up already
        replays through the shared emulator and can leave a warm-up position behind; running the
        re-entry over the same history would open a second imaginary trade in the one position
        slot and change what the primary's warm-up saw. What the fast side needs out of history is
        its own structure state — the SOS latch and the leg it defines — and that is all this
        builds. It is also why the live warm-up cannot simply call `step_fast`.
        """
        self.struct_fast.update(bar.index, bar.open, bar.high, bar.low, bar.close)

    def reset_fast(self) -> None:
        """Throw the fast side away so it can be rebuilt from history.

        ⚠ **The primary keeps everything** — its engines, its context, its open trade. A hole in
        the re-entry's feed must not cost the trade the bot is holding. ⚠ **The arm state machine
        goes with the structure feed**, because its latched legs are keyed on fast bar numbers and
        a rebuilt feed renumbers them; keeping it would leave latches pointing at bars that no
        longer exist.
        """
        self.struct_fast = Structure1m(major_length=self._major_length)
        self.arm_sm = SecondaryArm(self._st.config)

    def drain_primary(self) -> List[PrimaryStep]:
        """Step every queued 15m bar regardless of the fast clock. The window tail — and, live,
        the path taken when the fast feed is dead but the primary must keep trading."""
        out = [self._step_primary(b) for b in self._queue]
        self._queue.clear()
        return out

    def pending_primary(self) -> int:
        return len(self._queue)

    # ── internals ────────────────────────────────────────────────────────────

    def _step_primary(self, bar) -> PrimaryStep:
        st = self._st
        state = self._stack.step(bar)
        sig = st.signals.update(state)
        seq = st.sequence.update(sig)
        dec = st.execution.step(sig, seq)
        self.last_sig, self.last_seq = sig, seq
        self.last_close_primary = bar.close
        self.stepped_primary_to_ms = int(bar.timestamp_ms) + self._tf_primary_ms
        return PrimaryStep(bar=bar, sig=sig, seq=seq, dec=dec)


def fast_tf_minutes(config) -> int:
    """The fill clock, in minutes, off the config — never a hardcoded number.

    🔴 `bridge.assert_supported` said *"needs a 1-minute bar stream"* until 2026-09-01 and it was
    simply wrong: the second frame has been 5 minutes by default since 2026-08-21 and is the
    caller's choice either way. A refusal that names the wrong feed sends the next reader to
    build the wrong thing.
    """
    return int(getattr(config, "exec_sec_fill_tf_min", 5))
