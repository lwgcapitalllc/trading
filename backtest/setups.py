"""setups.py — the contract a strategy fills in to say WHAT IT IS WATCHING RIGHT NOW.

The alert layer (`algos/live/setup_alerts.py`) reads this and never knows which strategy it is
talking to. That is the whole point: a new bot gets pre-trade Telegram alerts by implementing one
method, not by anyone editing the notifier.

**REPORTING ONLY.** Nothing may read a `SetupSnapshot` back into a trading decision. That is what
keeps `compare_strategy.py` a valid parity gate — it diffs the `px_*` decision stream, and a
snapshot touches none of it. Same standing as `mfe_usd`, `Trade.fib` and `MissedSetup`.

⚠ **Prove that by REPLAY, never by argument.** Adding `live_setups()` to a strategy means replaying
its full history at HEAD and at the working tree and requiring a byte-identical trade list. A green
parity gate says the two implementations AGREE, never that either is RIGHT (root `CLAUDE.md` rule
14), and it says nothing at all about a branch neither side entered.

⚠ **Every price here is COPIED from what the strategy is holding, never recomputed.** A message
that re-derives an entry, a stop or a fib level is a second claim about one setup, and two claims
can disagree — the failure this repo has already met five times. An alert naming a level the bot
never traded is worse than no alert, because you would act on it.

Why this lives in `backtest/` rather than in `algos/` or beside the strategies: it is the one layer
both `algos/live/` and `strategies/python/` already import, and a strategy must never import
`algos/` — that would point the dependency from the deployable at the deployment.

See `docs/LIVE_SETUP_ALERTS.md` for the messages, the measured volume and the build order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol, Sequence, Tuple

# ── The four states a setup passes through ───────────────────────────────────────────────────
#
# A strategy reports a setup on every bar it is alive, and ONE LAST TIME carrying its resolution.
# The alternative — the alert layer noticing a setup vanish and cross-referencing the strategy's
# `misses` / `blocks` records to find out why — needs a join key those records do not carry, and a
# join that matches too little invents drift while one that matches too much invents parity. That
# trap is already recorded for `shadow_diff.py`; this design has nothing to correlate.
WATCHING = "watching"  #: confluences accumulating — the setup is forming
RESTING = "resting"  #: every confluence met and an order is live at a price
FILLED = "filled"  #: it became a trade
DEAD = "dead"  #: it ended without trading — `reason` says why

STATES = (WATCHING, RESTING, FILLED, DEAD)

#: The states a setup can be reported in and then never again. The alert layer drops its thread
#: bookkeeping on these, so a strategy that keeps reporting one would leak a thread id per bar.
TERMINAL = (FILLED, DEAD)


@dataclass(frozen=True)
class Confluence:
    """One thing a setup needs, and whether it has it yet.

    `detail` is the strategy's own words and is what makes a message worth reading — "Day High"
    rather than "met", "0.5-0.886 tagged, no FVG yet" rather than "not met". It is copied from
    state the strategy already holds; the alert layer never composes it.
    """

    name: str
    met: bool
    detail: str = ""


@dataclass(frozen=True)
class SetupSnapshot:
    """What one strategy is watching, on one side, right now.

    ⚠ **`key` must be stable for the setup's whole life and unique across sides, strategies and
    bots.** It is the Telegram thread id AND the dedupe key, and both jobs fail differently if it
    moves: a changing key starts a new thread every bar, and a colliding one files two setups'
    outcomes under one root. For `sos_fade` it is strategy + side + the SOS bar — the identity
    `_MissWatch` already keys on.

    ⚠ **`zone` and `entry` answer different questions and neither substitutes for the other.**
    `zone` is `(shallow, deep)` — the whole price range at which this setup is tradeable at all,
    known as soon as it arms, which is what makes an alert useful BEFORE an order exists. `entry`
    is the single price an order is actually resting at, and is `None` until one is. A strategy
    with no meaningful pre-entry range reports `zone=None` rather than collapsing the two: a range
    and a price are not the same claim.

    ⚠ **`stop` before an order exists is a PROJECTION and the message must say so.** It is where
    the stop would sit if the setup filled at the deep edge. Rendering it as a flat "Stop" would
    state a price the bot is not holding.
    """

    key: str
    strategy: str
    symbol: str
    side: int  #: +1 long, -1 short
    state: str
    confluences: Tuple[Confluence, ...] = ()
    zone: Optional[Tuple[float, float]] = None  #: (shallow, deep) — the valid entry range
    entry: Optional[float] = None  #: the ONE resting price, once there is one
    stop: Optional[float] = None
    targets: Tuple[float, ...] = ()
    blocked_by: Tuple[str, ...] = ()
    reason: str = ""  #: why it ended — FILLED / DEAD only
    #: Can this setup still become a trade under the CONFIG THE BOT IS RUNNING? `False` means the
    #: strategy has already decided it cannot — not that it is unlikely, but that no price path
    #: reaches a fill. The alert layer suppresses these, because a signal for a trade the bot
    #: would never take is a label with no code behind it (root `CLAUDE.md` rule 7) pointed at a
    #: human who might act on it.
    #:
    #: ⚠ **Only set it False for a decision the strategy has ALREADY made and cannot revisit.**
    #: A confluence that is merely unmet is not untradeable — it is the normal state of every
    #: setup before it fills. Getting this wrong hides real signals, and the failure is silent.
    tradeable: bool = True
    #: Is this setup close enough to acting that its RESTING ORDER is worth telling a human
    #: about? Gates the "limit resting" message only — never the root, never the outcome, and
    #: never a trade.
    #:
    #: 🔴 **It exists because an order is placed the moment a setup arms, which can be long
    #: before price could reach it.** Measured live 2026-08-14: a limit rested 41 points below
    #: price for a whole session, and the Telegram message announcing it arrived 45 minutes
    #: before anything could plausibly happen (Aaron: *"I only want to know a limit is pending
    #: when price gets back to 23.6% of the retracement"*). The strategy owns what "close
    #: enough" means, because only it knows its own geometry — the alert layer has no price and
    #: must never learn what a fib is.
    #:
    #: ⚠ **Defaults True, and that direction is deliberate.** A strategy that does not implement
    #: this announces exactly as it did before, so adding the field cannot silence an existing
    #: bot. The opposite default would make a forgotten line look like a quiet market — the
    #: no-vs-cannot-ask rule, which in this file is already why `tradeable` reads the way it
    #: does.
    #:
    #: ⚠ **A strategy setting this False must guarantee it goes True before any fill it would
    #: suppress**, or a real trade arrives in the trades room having never been signalled.
    #: `backtest/tools/alert_rate.py` is what checks that end to end; re-run it after changing
    #: how a strategy computes this.
    announce_resting: bool = True

    def __post_init__(self) -> None:
        # A bad state would route a message to the wrong formatter and, worse, would leave a
        # terminal setup un-dropped from the alert layer's thread map — a slow leak that looks
        # like nothing until the process has run for months.
        if self.state not in STATES:
            raise ValueError(f"SetupSnapshot.state {self.state!r} is not one of {STATES}")
        if self.side not in (1, -1):
            raise ValueError(f"SetupSnapshot.side must be +1 or -1, got {self.side!r}")
        if not self.key:
            raise ValueError("SetupSnapshot.key must be a stable non-empty id")
        if self.zone is not None and len(self.zone) != 2:
            raise ValueError(f"SetupSnapshot.zone must be (shallow, deep), got {self.zone!r}")

    # ── How far along it is. Derived, never stored — see the note on `of`. ───────────────────
    @property
    def met(self) -> int:
        """How many confluences this setup has."""
        return sum(1 for c in self.confluences if c.met)

    @property
    def of(self) -> int:
        """How many it needs.

        **This is what makes "2 of 3" stop being a hardcoded number.** A four-confluence strategy
        reports 3 of 4 with no change anywhere in the alert layer. Storing the total as a field
        instead would let it disagree with the list beside it.
        """
        return len(self.confluences)

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL

    @property
    def direction(self) -> str:
        return "LONG" if self.side > 0 else "SHORT"

    def met_lines(self) -> List[str]:
        """The confluence breakdown, in the strategy's own declared order."""
        return [
            f"{c.name} — {c.detail or ('yes' if c.met else 'not yet')}" for c in self.confluences
        ]


class WatchesSetups(Protocol):
    """What a strategy implements to get pre-trade alerts.

    🔴 **A strategy that does NOT implement this gets no alerts and the runner must SAY SO at
    startup — loudly, once, by name.** It must never fall back to silence. Three separate jobs in
    this repo ran for weeks against an empty registry and reported success (root `CLAUDE.md` rule
    8); an absent implementation is a fact worth reporting, not a default worth guessing.

    ⚠ **Do not stub it to make a bot "supported".** A stub returning `[]` is exactly that empty
    registry, and it is indistinguishable from a quiet market.
    """

    def live_setups(self) -> Sequence[SetupSnapshot]: ...


def implements_contract(obj: object) -> bool:
    """Whether `obj` really answers `live_setups()` — and MEANS it.

    Deliberately a `callable(getattr(...))` check and not a `try/except AttributeError` around a
    call: calling it to find out would run strategy code at startup to answer a question about its
    shape, and would swallow a genuine error inside a real implementation as "not implemented".

    🔴 **`reports_setups = False` opts a subclass OUT, and it exists because INHERITANCE CREATED
    THE EXACT FAILURE THIS MODULE WARNS ABOUT.** `b_leg` and `bos` subclass
    `sos_fade`'s `Execution` and both set `_records_misses = False`, which is what populates
    the setup context — so they inherited a `live_setups()` that returns `[]` on every bar
    forever. A method-presence check said True, the runner would have announced "Setup alerts: ON"
    for those bots, and the channel would have sent nothing: an empty registry answering
    confidently, arriving by inheritance rather than by a literal `{}`.

    **A class that cannot answer must say so rather than answering emptily.** Any object may
    declare `reports_setups = False`; anything that does not declare it is assumed to mean its
    implementation.
    """
    if not callable(getattr(obj, "live_setups", None)):
        return False
    return bool(getattr(obj, "reports_setups", True))
