"""What a strategy must provide to run as a LIVE bot — the contract, not one bot's wiring.

**Why this module exists.** Until 2026-09-03 the live contract had no definition. It was whatever
`sos_fade.execution.Execution` happened to implement, and a strategy became live-capable by
SUBCLASSING that class — which `b_leg`, `bos` and `realign` all do. That works for a strategy
shaped like SOS Fade and offers nothing to one that is not: `extreme_leg` is an independent
implementation, so it inherited none of it and could not be a bot at all.

🔴 **The failure mode that argument hides is the one worth naming: the live path reads almost
every decision field through `getattr(dec, name, default)`, so a field a strategy never sets is
INDISTINGUISHABLE from a field with nothing to report.** Omit the stop and the bridge simply never
ratchets the broker's stop — no error, no halt, no log line, and a position rides its original
stop while every dashboard stays green. **That is this repo's rule 1 in a new place: "nothing to
report" and "never implemented" must not be the same value.** A defensive read cannot tell them
apart, so the distinction has to be made HERE, before the bot starts.

**So this module does three things and refuses to do a fourth:**

1. Names the contract — `STRATEGY_ATTRS`, `EXECUTION_ATTRS`, `DECISION_FIELDS`, `LOAD_BEARING`.
2. Checks a strategy against it (`verify_live_ready`) so a non-conforming bot is refused BY NAME
   at startup rather than raising `AttributeError` on a Tuesday.
3. Provides the generic halves any adopter needs — save/restore, the commanded close, the
   pass-through stages, and a decision object.
4. **It does NOT re-implement any strategy's logic**, and it must never grow a branch naming one.

⚠ **The lists here are MEASURED off `algos/live/`, not remembered.** `tests/test_live_contract.py`
re-derives them from that source and goes red when the live path starts reading something new.
**A contract maintained by hand is a second implementation of the thing it describes.**

⚠ **Satisfying this contract does NOT make a strategy safe to arm.** It makes it *startable*. Rule
9 still applies: nothing here has been near a broker until it has.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "STRATEGY_ATTRS",
    "EXECUTION_ATTRS",
    "DECISION_FIELDS",
    "ENTRY_STYLES",
    "LOAD_BEARING",
    "LiveDecision",
    "PassThroughSignals",
    "PassThroughSequence",
    "LivePositionMixin",
    "verify_live_ready",
    "LiveContractError",
]


# ── the contract ─────────────────────────────────────────────────────────────

#: What `algos/live/runner.py` drives on the STRATEGY object, once per bar.
#: It calls `signals.update(state)` -> `sequence.update(sig)` -> `execution.step(sig, seq)`.
STRATEGY_ATTRS = ("signals", "sequence", "execution", "engine_config")

#: What `algos/live/bridge.py` reads off the EXECUTION object.
#: ⚠ The four leading underscores are not an accident and not ours to rename: the bridge reads
#: them directly, so they are public surface wearing a private name. Renaming one is a live change.
EXECUTION_ATTRS = (
    "_pos_dir",          # 0 flat / +1 long / -1 short. Read 10 times; the bridge's main gate.
    "_entry",            # fill price of the open position
    "_pend_long",        # resting long order, or None
    "_pend_short",       # resting short order, or None
    "entry_style",       # "resting" | "market" — see ENTRY_STYLES
    "step",              # (sig, seq) -> decision
    "request_close",     # (reason) -> bool. The kill switch and the Stop button land here.
    "snapshot_position",  # () -> dict, for surviving a restart holding a position
    "restore_position",  # (dict) -> None
    "bar_ms",            # set by the runner from the feed
    "blocks",            # cleared by the runner each bar
    "misses",            # cleared by the runner each bar
    "is_flat",
    "equity",
)

#: How a strategy OPENS a position — and therefore what `algos/live/` has to do about it.
#:
#: 🔴 **The two differ in WHEN the emulator fills relative to the bridge, and that is the whole
#: distinction.** A `"resting"` strategy publishes its intent BEFORE anything fills: the bridge
#: places a limit, price comes to it later, and both books fill independently off the same order.
#: A `"market"` strategy has ALREADY filled by the time the bridge looks — it enters on the bar
#: close inside its own emulator — so the bridge's job is to catch the broker up, not to place an
#: order and wait.
#:
#: 🔴 **THIS MUST BE DECLARED, NEVER INFERRED, AND THE REASON IS A SAFETY PROPERTY.** "The
#: emulator holds a position and the broker holds nothing" is the exact state `bridge._agrees`
#: halts on, and halting is CORRECT for a resting strategy — it means a limit filled in one book
#: and not the other, which is the 2026-08-07 divergence. The same state is ROUTINE for a market
#: strategy, one instant old, and mirroring it is correct. **Nothing observable separates them:
#: the position, the direction, the fill record and the empty broker book are identical.** So a
#: bridge that guessed would either halt a working bot every trade, or silently convert a real
#: divergence into a fresh market order at a price nobody endorsed.
#:
#: ⚠ **An undeclared strategy is refused by `verify_live_ready`, and the bridge's own read
#: defaults to `"resting"`.** Both directions on purpose: nothing ships without saying which it
#: is, and any path that somehow reaches the bridge without a declaration gets the halting
#: behaviour rather than the order-placing one.
ENTRY_STYLES = ("resting", "market")

#: Every field the live path reads off a per-bar decision, with the default it reads it with.
#: Read by `bridge.sync` and `ledger.bar`, all through `getattr(dec, name, default)`.
DECISION_FIELDS: Dict[str, Any] = {
    "stop": None,
    "fills": (),
    "exit_reason": None,
    "tp1": None,
    "tp2": None,
    "long_armed": False,
    "short_armed": False,
    "long_edge": None,
    "short_edge": None,
    "l_stage": 0,
    "s_stage": 0,
    "long_veto": False,
    "short_veto": False,
}

#: The two that move money. Everything else in `DECISION_FIELDS` is reporting.
#:
#: 🔴 **A strategy that never populates these two is not broken-looking — it is SILENT.** `stop`
#: is what ratchets the broker's stop; `fills` is what books the trade. Both are read defensively,
#: so omitting them produces a bot that trades and never protects, with nothing in any log.
#: **Any adopter's tests must assert these are POPULATED on a bar that should populate them.**
#: Asserting that `step` returns an object passes against an adapter that sets nothing.
LOAD_BEARING = ("stop", "fills")


class LiveContractError(RuntimeError):
    """A strategy was asked to go live without satisfying the contract.

    ⚠ **Raised at STARTUP, deliberately.** The alternative is an `AttributeError` from somewhere
    inside the bar loop, at whatever hour the missing branch is first reached — which is the same
    information arriving too late to be useful and attached to the wrong line.
    """


# ── the decision ─────────────────────────────────────────────────────────────


@dataclass
class LiveDecision:
    """One bar's decision, carrying every field the live path reads.

    ⚠ **Defaults here MATCH the defaults the live path reads with**, so an unset field means
    exactly what the reader assumes it means. They are kept in step by
    `tests/test_live_contract.py`, which compares this dataclass against `DECISION_FIELDS`.

    ⚠ **`sos_fade.execution.Decision` is NOT this class and is not being migrated onto it.** It
    predates this module, it satisfies the same contract independently, and it carries extra
    columns its parity harness diffs against the Pine export. Changing the live bot's decision
    object to inherit from here would be a change to the strategy that is currently trading, for
    a tidiness gain. **The test asserts the two agree; it does not merge them.**
    """

    index: int = 0
    stop: Optional[float] = None
    fills: List[Any] = field(default_factory=list)
    exit_reason: Optional[str] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    long_armed: bool = False
    short_armed: bool = False
    long_edge: Optional[float] = None
    short_edge: Optional[float] = None
    l_stage: int = 0
    s_stage: int = 0
    long_veto: bool = False
    short_veto: bool = False


# ── the pass-through stages ──────────────────────────────────────────────────


class PassThroughSignals:
    """`signals.update(state) -> state`, for a strategy that decides in ONE call.

    The runner drives three stages because SOS Fade genuinely has three. A strategy whose whole
    decision happens in its own `step` has one, and pretending otherwise by splitting its logic
    would be rewriting the strategy to suit the caller. **So the seam is honest about being
    empty** rather than absent — the runner still gets its three calls, and the bar state reaches
    the execution unchanged.

    ⚠ **It is NOT a place to put logic.** Anything that decides belongs in the strategy, where its
    replay path can reach it and its parity gate can see it.
    """

    __slots__ = ()

    def update(self, state):
        return state


class PassThroughSequence:
    """`sequence.update(sig) -> None`, the second empty seam. See `PassThroughSignals`."""

    __slots__ = ()

    def update(self, sig):
        return None


# ── the generic halves ───────────────────────────────────────────────────────


class LivePositionMixin:
    """Save/restore and the commanded close, driven by a DECLARED field list.

    An adopter declares `_POSITION_FIELDS` — the attribute names that together are the whole open
    position — and gets `snapshot_position` / `restore_position` for free.

    ⚠ **`_POSITION_FIELDS` is the WHOLE open-trade state and a missing entry is SILENT.** The
    record round-trips, the bot restarts, and the omitted latch comes back at its class default —
    so a trade already moved to breakeven is managed as though it never was. **Adopters must pin
    this with a test that compares the list against what the class actually assigns while a
    position is open**, the way `sos_fade/tests/test_position_snapshot.py` does.

    ⚠ **Restore REFUSES an incomplete record rather than filling defaults**, and that refusal is
    the safety property. A record missing a field is not "a position at the default" — it is a
    record we cannot trust, and managing a real position against a guess is the failure this
    exists to end. The caller halts, which is what a bot did before any of this existed.

    ⚠ **Restore must be called AFTER the warm-up, never before.** A warm-up replay afterwards
    overwrites the restored book with whatever it imagined.
    """

    #: Adopters override. Empty here so a class that forgets is caught by `verify_live_ready`
    #: rather than silently snapshotting nothing.
    _POSITION_FIELDS: Sequence[str] = ()

    def _encode_position_field(self, name: str, value):
        """Hook: turn one field into plain JSON types. Override for non-trivial values.

        ⚠ Anything mutable that the OPEN trade keeps appending to must be COPIED here, or the
        snapshot aliases it and keeps growing after it was taken.
        """
        return value

    def _decode_position_field(self, name: str, value):
        """Hook: the inverse of `_encode_position_field`."""
        return value

    def snapshot_position(self) -> dict:
        if not self._POSITION_FIELDS:
            raise LiveContractError(
                f"{type(self).__name__} declares no _POSITION_FIELDS, so a restart would "
                f"silently drop the open position rather than refuse to manage it."
            )
        if self.is_flat:
            raise ValueError(
                "snapshot_position() called while flat — there is nothing to record")
        return {
            name: self._encode_position_field(name, getattr(self, name))
            for name in self._POSITION_FIELDS
        }

    def restore_position(self, snap: dict) -> None:
        missing = [n for n in self._POSITION_FIELDS if n not in snap]
        if missing:
            raise ValueError(
                "refusing to restore an incomplete position record; missing: "
                + ", ".join(sorted(missing)))
        for name in self._POSITION_FIELDS:
            setattr(self, name, self._decode_position_field(name, snap[name]))


# ── the check ────────────────────────────────────────────────────────────────


def verify_live_ready(strategy) -> List[str]:
    """What this strategy is missing before it could be a live bot. Empty list means conformant.

    ⚠ **It checks PRESENCE, never correctness.** A strategy can satisfy every name here and still
    populate the stop with nonsense. This turns "crashes somewhere in the bar loop" into "refused
    at startup, by name" — which is worth having and is not the same as being proven.

    ⚠ **It is deliberately not a decorator or a base class anybody must inherit.** A strategy is
    live-ready because it PROVIDES these things, however it chooses to; SOS Fade satisfies it
    without importing this module, and the test asserts exactly that.
    """
    missing: List[str] = []

    for name in STRATEGY_ATTRS:
        if not hasattr(strategy, name):
            missing.append(f"strategy.{name}")

    ex = getattr(strategy, "execution", None)
    if ex is None:
        missing.append("strategy.execution (cannot check the execution contract without it)")
        return missing

    for name in EXECUTION_ATTRS:
        if not hasattr(ex, name):
            missing.append(f"execution.{name}")

    fields = getattr(ex, "_POSITION_FIELDS", None)
    if hasattr(ex, "snapshot_position") and not fields:
        missing.append(
            "execution._POSITION_FIELDS (declared empty: a restart would drop the open position)")

    # PRESENCE is checked above with everything else; this is the one place the contract also
    # checks a VALUE, because a typo here is not a missing feature — it is the bridge falling back
    # to the resting behaviour and halting a market bot on its first trade. See `ENTRY_STYLES`.
    style = getattr(ex, "entry_style", None)
    if style is not None and style not in ENTRY_STYLES:
        missing.append(
            f"execution.entry_style is {style!r}, which is not one of {ENTRY_STYLES}; "
            f"algos/live/ would treat it as 'resting'")

    return missing
