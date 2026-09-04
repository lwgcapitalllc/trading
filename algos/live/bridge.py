"""bridge.py — the strategy's intent, mirrored onto MT5.

**The design decision this file implements** (`docs/LIVE_TRADING_PIPELINE.md` D3): the strategy
stays AUTHORITATIVE and the bridge only makes the broker match it. The bridge never decides
whether to trade, what size, or where a stop belongs — every one of those is already computed
by the same `Execution` object the backtest runs, which is what preserves the bar-for-bar parity
with the Pine that was expensive to earn. If a change here would require a trading judgement,
the split is wrong.

**Why a mirror and not a rewrite of the execution layer.** `Execution` is a broker EMULATOR: it
holds its own resting limits (`_pend_long` / `_pend_short`), its own position, and fills them
against bar OHLC. Live, MT5 is the broker. The two could have been merged by tearing the fills
out of the strategy — and that would have thrown away the one thing that makes a live number
comparable to a backtest number. So both run, and this file reconciles them once per closed bar.

**The reconciliation happens at BAR CLOSE, and the timing is load-bearing.** Inside a bar MT5
fills the moment price touches a level, while the emulator only evaluates when `step()` is next
called. Comparing them mid-bar would report a disagreement on every single fill. At bar close,
both have seen the same bar, so a difference that survives is a real one.

**A real difference HALTS the bot.** Not "log and continue", not "adopt the broker's view". A
position the strategy does not know about, or a strategy position the broker does not have,
means the two ledgers have parted and every subsequent decision is computed against a fiction.
The position keeps its broker-side stop (see D4 — the stop always lives at the broker, so a
halt is never an unprotected position), Telegram fires, and a human decides. On a demo, with
Aaron watching, "stop and tell me" is the honest response; silently continuing is how a live
system loses the ability to explain itself.

**What is deliberately NOT supported, and it is a SHORT list now.** Partial take-profits were on
it until 2026-09-01 and a rung taking the WHOLE position until 2026-09-02; both are mirrored
today. What remains is the force-close on an opposite structure break — refused because its fill
carries the same tag an ordinary stop-out does, so nothing can tell the bridge which happened —
and adding size to a winner, which needs an entry path this bridge does not have. Every one of
them is a refusal in `assert_supported()`, not a silent skip.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

# `notify` lives in algos/shared. The runner puts it on sys.path before importing this module,
# but a test that imports the bridge alone must not have to know that — an import path is not a
# contract worth restating in every caller.
_SHARED = Path(__file__).resolve().parent.parent / "shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

import alerts  # noqa: E402
import notify  # noqa: E402  (for the TRADE/HEALTH routing kinds only)

# A sibling module, imported the same flat way the runner imports this one — `algos/live/` is put
# on the path by whoever loads the package, and a test that imports the bridge alone must not have
# to know that either.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import position_state  # noqa: E402
from alert_format import alert, joined  # noqa: E402

# The third answer a broker call can give. Its own dependency-free module on purpose — see
# the note in `algos/shared/broker_result.py` about what importing it from `mt5_ops` broke.
from broker_result import UNKNOWN  # noqa: E402
from order_sizing import (  # noqa: E402
    DEFAULT_MARGIN_SAFETY_PCT,
    plan_order,
)


class BridgeState(str, Enum):
    WARMING = "warming"  # the emulator opened a position during warmup — wait for it to flatten
    LIVE = "live"
    HALTED = "halted"  # emulator and broker disagree; no further orders


@dataclass
class _Rest:
    """What we believe is resting at the broker in one slot."""

    ticket: int
    price: float
    lots: float
    sl: float


@dataclass
class _FastSig:
    """A fill-clock bar in the shape the booking path reads.

    ⚠ **An ADAPTER, not a second signal.** The fast feed hands out a `ReplayBar`, whose time
    field is named differently from the 15-minute signal's, and every read in the booking path
    is a `getattr` with a default — so handing the raw bar over would silently record every
    re-entry with no timestamp and nothing would fail.
    """

    index: Optional[int] = None
    time_ms: Optional[int] = None


@dataclass
class _FastDec:
    """What the re-entry wants at the broker on this fill-clock bar."""

    stop: Optional[float] = None
    tp1: float = 0.0
    tp2: float = 0.0


#: The exit legs the BRIDGE has to execute, by the tag the strategy stamps on the fill.
#:
#: 🔴 **The list is what the BROKER cannot do for itself.** A stop is already an order sitting at
#: the broker, so a stop-out needs nothing from this bridge. Everything here is a decision the
#: strategy made against a closed bar — a target that took the whole position, an operator's
#: instruction, the clock running out — and the broker has never heard of any of them.
#:
#: ⚠ **`CLOSE` is deliberately ABSENT, and it is absent because it is AMBIGUOUS rather than
#: because it is safe.** `execution._close_at` defaults to that tag, so an ordinary STOP-OUT and
#: an opposite-structure force-close both arrive stamped `L-CLOSE` and nothing in the fill tells
#: them apart. Mirroring it would market-close on a stop the broker is already filling; ignoring
#: it silently mis-executes the force-close. So the force-close is REFUSED at startup instead —
#: an unsupported thing that says so beats either guess.
#:
#: ⚠ **Adding an exit leg to the strategy means adding it here.** This is an allow-list, so a new
#: tag defaults to *not mirrored* — the bot exits in its own book, the broker keeps the position,
#: and the bridge halts on the next bar. That is loud rather than silent, which is why the
#: allow-list is the safe direction, but it is still a halt somebody has to come and read.
BRIDGE_OWNED_EXITS = ("-CMD", "-TIME", "-TP1", "-TP2")


#: Every place an order can rest, as (INTENT, side).
#:
#: 🔴 **Keyed by intent and not by side alone, since 2026-09-02.** The primary and the re-entry
#: can both want a resting limit at the same moment, and on the same side — the re-entry arms
#: while the bot is flat, which is exactly when the primary is offering its own limit. Keyed by
#: direction alone the two collide on one key: the second placement overwrites the first's
#: record, and `_observe_orphans` then cancels the order nobody remembers within a bar.
#:
#: ⚠ **The side is part of the key rather than read off the pending order.** It costs one unused
#: slot and buys the property that every lookup in this file — a fill, a vanished order, a
#: refusal — finds its slot by the two things it always knows, and no caller has to ask a
#: pending order which way round it is.
PRIMARY_LONG = ("primary", 1)
PRIMARY_SHORT = ("primary", -1)
SECONDARY_LONG = ("secondary", 1)
SECONDARY_SHORT = ("secondary", -1)
SLOTS = (PRIMARY_LONG, PRIMARY_SHORT, SECONDARY_LONG, SECONDARY_SHORT)


def primary_slot(direction: int):
    """The primary's slot on one side."""
    return PRIMARY_LONG if direction > 0 else PRIMARY_SHORT


def secondary_slot(direction: int):
    """The re-entry's slot on one side."""
    return SECONDARY_LONG if direction > 0 else SECONDARY_SHORT


def slot_label(slot) -> str:
    """How a slot is named in a log line or an alert a person reads."""
    kind, direction = slot
    side = "bullish" if direction > 0 else "bearish"
    return f"{side} {'re-entry' if kind == 'secondary' else 'primary'}"


class UnsupportedStrategyConfig(RuntimeError):
    """The strategy is configured to do something the live bridge cannot mirror."""


def price_triggered_banks(strategy_config) -> list:
    """Every setting asking for size to come off AT A PRICE, as `(field, percent)` pairs.

    🔴 **THE BRIDGE HAS NO EXIT PATH AT ALL.** Its only order calls are `place_pending_limit`,
    `modify_pending`, `cancel_pending` and `move_sl` — every exit reaches the broker as a STOP
    MOVE. So any rung that banks a percentage when a price is touched is unmirrorable, and a bot
    that runs one trades a book its own backtest does not: it rides where the lab banked.

    🔴 **THIS FUNCTION EXISTS BECAUSE THE OLD CHECK READ TWO FIELDS AND THE STRATEGY READS SIX
    (found 2026-09-01).** `assert_supported` tested `exec_tp1_pct` / `exec_tp2_pct` only, which
    is the LAST branch of `execution.Execution._tp1_pct` — the three branches above it were
    invisible to it. Two of them are reachable by flipping ONE setting on the live bot:

      - `exec_short_hold` ON replaces the primary's first rung with `exec_sh_tp1_pct`, whose
        default is **100** — the whole position off at the R target, no runner. Nothing refused
        it, so the bot would have STARTED and silently ridden every trade past its target.
      - `exec_secondary` ON gives the re-entry its own rung: `exec_rec_tp1_pct` (default **100**)
        under a reclaim trigger, `exec_sec_tp1_pct` (**50** on this bot) otherwise. This is the
        one that matters for G18 stage 2 — placing the re-entry's ENTRY is not enough, because
        its 50% scale-out has nowhere to go.

    ⚠ **It MIRRORS `Execution._tp1_pct` branch for branch and must be re-read against it when
    that changes.** The branches, in the strategy's own order: a secondary reads its own
    percentage (reclaim source vs any other), `-1.0` means inherit the shared `exec_tp1_pct`; a
    primary under `exec_short_hold` reads `exec_sh_tp1_pct`; everything else reads the shared
    field. Which triggers count as the reclaim is `config.py`'s own `rec_on` test.

    ⚠ **`exec_sec_tp2_x` is deliberately NOT listed.** It moves where the second rung SITS; how
    much comes off there is `exec_tp2_pct` alone (`execution.py` — `p2 = qty * exec_tp2_pct/100`),
    so at `exec_tp2_pct = 0` nothing banks there whatever the multiple says.

    Returns [] for a configuration the bridge can mirror. A LIST rather than a bool so the
    refusal can name the fields — "partial take-profits are on" sends nobody anywhere.
    """

    seen = set()
    flat = []
    for _kind, rungs in bank_ladders(strategy_config):
        for name, pct in rungs:
            if name not in seen:
                seen.add(name)
                flat.append((name, pct))
    return flat


def bank_ladders(strategy_config) -> list:
    """The same rungs, grouped into the LADDERS a single position can actually walk.

    Returns `[(kind, [(field, percent), ...]), ...]` — one entry per ladder that can exist under
    this configuration, `kind` naming it in words a reader can act on.

    🔴 **THIS GROUPING IS THE WHOLE POINT, AND ITS ABSENCE MADE THE FULL-EXIT CHECK REFUSE
    CONFIGURATIONS THAT ARE FINE.** The flat list above is right for the question *does anything
    bank at a price at all*, and wrong for *does any position reach zero* — because a primary and
    a re-entry are DIFFERENT POSITIONS and their percentages never meet. Added together, a
    primary banking 40% and a gap re-entry banking 60% reached a full exit that neither one
    performs, and the refusal then named two fields belonging to two trades that are never on the
    same rung.

    The ladders, and which field supplies each rung (`execution.Execution._tp1_pct` decides the
    first, `_remaining_brackets` reads `exec_tp2_pct` for the second whatever the trade is):

      | ladder                     | first rung          | second rung     |
      |----------------------------|---------------------|-----------------|
      | primary, short-hold ON     | `exec_sh_tp1_pct`   | `exec_tp2_pct`  |
      | primary, short-hold OFF    | `exec_tp1_pct`      | `exec_tp2_pct`  |
      | re-entry under a reclaim   | `exec_rec_tp1_pct`  | `exec_tp2_pct`  |
      | re-entry under a gap       | `exec_sec_tp1_pct`  | `exec_tp2_pct`  |

    ⚠ **Exactly ONE primary ladder is live at a time** — short-hold is a boolean, and the
    strategy tests the secondary branch FIRST, so short-hold never applies to a re-entry.
    ⚠ **The two re-entry ladders BOTH exist only under the combined trigger**, and even then a
    given re-entry is one or the other — never both — which is precisely why they are separate
    rows rather than one summed list.
    ⚠ **`exec_tp2_pct` therefore appears in EVERY ladder and is not double-counted**, because a
    ladder is only ever summed against itself.
    """

    def g(name, default):
        return getattr(strategy_config, name, default)

    shared_tp1 = float(g("exec_tp1_pct", 0) or 0)
    shared_tp2 = float(g("exec_tp2_pct", 0) or 0)
    tail = [("exec_tp2_pct", shared_tp2)] if shared_tp2 else []
    ladders = []

    # ── the PRIMARY's ladder ───────────────────────────────────────────────────────────────
    if g("exec_short_hold", False):
        # REPLACES the shared first rung for a primary, so the shared field is not also read.
        sh = float(g("exec_sh_tp1_pct", 100.0) or 0)
        first = [("exec_sh_tp1_pct", sh)] if sh else []
    else:
        first = [("exec_tp1_pct", shared_tp1)] if shared_tp1 else []
    if first or tail:
        ladders.append(("the primary", first + tail))

    # ── the RE-ENTRY's ladders, gated exactly as `config.py` gates them ────────────────────
    if g("exec_secondary", False):
        trigger = g("exec_sec_trigger", "Reclaim Entry")
        if trigger in ("Reclaim Entry", "FVG in zone + Reclaim Entry"):
            own = float(g("exec_rec_tp1_pct", 100.0))
            pct = shared_tp1 if own == -1.0 else own
            first = [("exec_rec_tp1_pct", pct)] if pct else []
            if first or tail:
                ladders.append(("the re-entry after a stop-out", first + tail))
        if trigger in ("FVG in zone", "Structure shift", "FVG in zone + Reclaim Entry"):
            own = float(g("exec_sec_tp1_pct", -1.0))
            pct = shared_tp1 if own == -1.0 else own
            first = [("exec_sec_tp1_pct", pct)] if pct else []
            if first or tail:
                ladders.append(("the re-entry into a gap", first + tail))
    return ladders


def assert_supported(strategy_config) -> None:
    """Refuse a configuration the bridge would silently mis-execute.

    Better to not start than to run a strategy whose scale-outs quietly never happen — the
    equity curve would diverge from every backtest and nothing would say why.
    """
    # 🔴 **A LADDER THAT BANKS 100% AT A PRICE WAS REFUSED HERE UNTIL 2026-09-02.** The bridge
    # had no full-exit path — every exit reached the broker as a stop move — so a rung taking the
    # last of a position would have been silently skipped and the bot would have RIDDEN where the
    # backtest CLOSED. `_mirror_strategy_exit` is that path now: the rung finalises the trade in
    # the strategy's book and the bridge closes the broker's position to match. The refusal is
    # gone rather than softened, which is the distinction worth keeping — the capability it was
    # standing in for actually exists.
    # ⚠ It has never run against a broker. Rule 9 applies to the first one.
    if getattr(strategy_config, "exec_close_opp_sos", False):
        raise UnsupportedStrategyConfig(
            "exec_close_opp_sos closes the position at market when structure breaks against it, "
            "and the bridge cannot mirror that exit: `execution._close_at` stamps it with the "
            "SAME tag an ordinary stop-out carries, so nothing in the fill tells the bridge "
            "whether the broker has already closed the trade with its own stop order or is "
            "still holding it. Mirroring would market-close on top of a filling stop; ignoring "
            "it would leave the broker holding a trade the strategy has exited, and the bot "
            "would halt. Refusing is the answer until the strategy gives that exit its own tag. "
            "Turn it off. See docs/LIVE_TRADING_PIPELINE.md G18."
        )
    # 🔴 **`exec_secondary` WAS REFUSED OUTRIGHT HERE UNTIL 2026-09-02, ON TWO GROUNDS, AND BOTH
    # HAVE SINCE STOPPED BEING TRUE.** The refusal said the re-entry *"needs a SECOND bar stream"*
    # and that this bridge *"has no path that places the re-entry's order"*. The second stream is
    # built by `runner._build_fast_feed` and merged by the strategy's own `DualClock`; the order
    # is placed by `sync_fast`, on the re-entry's own slot. So the refusal is GONE rather than
    # softened — the same distinction as the full-exit one above, and the only one worth making:
    # a refusal is retired when the capability it stood in for exists, never to get a bot started.
    #
    # 🔴 **WHAT REPLACES IT ASKS A DIFFERENT QUESTION, AND THE DIFFERENCE IS THE WHOLE POINT.**
    # The setting is now mirrorable, so it is no longer a reason to refuse. What IS still a reason
    # is a configuration that asks for a re-entry the runner will never deliver — a strategy with
    # no fill clock to offer, or no merge to interleave it with. That cannot be seen in the config
    # alone, so it is `assert_secondary_wired` below, asked by every caller that can answer it.
    #
    # ⚠ It has never run against a broker. Rule 9 applies to the first one.
    if getattr(strategy_config, "exec_scale_in", False):
        raise UnsupportedStrategyConfig(
            "exec_scale_in adds SIZE to a winning position, and this bridge mirrors ONE entry "
            "limit and one ratcheting stop — it has no path that places a second entry. Left "
            "unrefused the bot would trade the base position, place no adds, and say nothing: "
            "the backtest would show a scaled book and the account would show an unscaled one, "
            "which is the exact divergence this function exists to prevent. Turn it off, or "
            "build the add path (and the account-level allocator it needs — margin sees the "
            "full stacked position even though risk-to-stop does not). See "
            "docs/LIVE_TRADING_PIPELINE.md G10."
        )
    if getattr(strategy_config, "fill_model", "bar") != "bar":
        raise UnsupportedStrategyConfig(
            "fill_model must be 'bar' live. 'tick' is a BACKTEST cost model that resolves fills "
            "against historical tick data; live, the broker resolves fills and its real prices "
            "are recorded by the ledger."
        )


def assert_secondary_wired(strategy_config, *, fill_clock_minutes, has_merge: bool) -> None:
    """Refuse a re-entry that is switched ON and has nothing to run on.

    🔴 **THE FAILURE THIS EXISTS FOR IS SILENT, WHICH IS WHY IT IS A REFUSAL AND NOT A LOG LINE.**
    The re-entry is placed by `sync_fast`, and `sync_fast` is only ever driven when the runner
    built a second bar feed. The runner builds one by ASKING THE STRATEGY (`fast_feed_minutes`),
    not by reading `exec_secondary` — `algos/live/` holds no trading logic and does not know what
    a re-entry is. So a strategy whose config says *re-enter* but which offers no fill clock gets
    no second feed, and the bot starts, trades the primary alone, and re-enters never. Nothing
    fails. The backtest shows re-entries and the account does not, which is the exact divergence
    `assert_supported` exists to prevent — arriving through the seam rather than through a setting.

    🔴 **IT IS A SEPARATE FUNCTION BECAUSE THE QUESTION CANNOT BE ANSWERED FROM THE CONFIG.** Both
    facts it needs live on the STRATEGY OBJECT, and the two callers reach that object in different
    ways — the runner holds it, and `promote.py` cannot import it at all (the staged snapshot
    carries no `algos/` tree, so the answers are shipped out of the verify subprocess as VALUES).
    Passing them in is what lets one rule serve both. That is `feed.fast_feed_timeframe`'s shape
    exactly, and for the same reason: a copy in the promote tool drifts the first time either
    moves, and this repo has already paid for that twice.

    ⚠ **`fill_clock_minutes=None` is *the strategy offers no fill clock*, and this function is the
    place that decides what that MEANS** — nothing at all when the config wants no re-entry, and a
    refusal when it does. One value, two meanings, separated by the only thing that can tell them
    apart. Rule 1 is about not destroying that distinction at the bottom; here it is reconstructed
    at the top, from the config beside it.

    ⚠ **A caller that could not ASK must not call this with `None`.** `promote.startup_refusals`
    reports the raised exception instead and skips this check, because *asking blew up* and *there
    is no fill clock* are different answers and printing the same sentence for both is the defect
    one layer down.

    🔴 **THE MERGE HALF IS NOT GATED ON `exec_secondary`, AND THAT IS THE FIX FOR A HOLE THIS
    FUNCTION NEARLY SHIPPED WITH.** Written the obvious way — return early unless the config wants
    a re-entry — it stopped refusing a strategy that asks for a fast feed for some OTHER reason
    and has no merge, which `promote.startup_refusals` had covered before this function absorbed
    it. So the two halves ask different questions on purpose: *did the config order something the
    strategy cannot supply* (a re-entry with no clock), and *did the strategy order something it
    cannot itself handle* (a clock with no merge). Only the first is about the re-entry.

    ⚠ **`runner._make_clock` raises on the merge too, and neither is redundant.** That raise
    happens after the feed is built and the strategy is warmed; this one happens before either,
    and it is the half `promote.py --dry-run` can reach.
    """
    if fill_clock_minutes is None:
        if not getattr(strategy_config, "exec_secondary", False):
            return
        raise UnsupportedStrategyConfig(
            "exec_secondary asks for a re-entry, but the strategy offers no fill clock — it "
            "answers fast_feed_minutes() with nothing, or does not implement it. The runner "
            "builds the second bar stream off that answer, so it would build none: the bot "
            "would start, trade the primary alone, and place no re-entry ever, with nothing "
            "in the logs saying so. Give the strategy a fast_feed_minutes(), or turn the "
            "re-entry off. See docs/LIVE_TRADING_PIPELINE.md G18."
        )
    if not has_merge:
        # ⚠ **It names the STRATEGY and not `exec_secondary`, because this branch is not about
        # the re-entry** — see the note above. A message naming a setting that may well be off is
        # the exact defect the old "1-minute bar stream" wording had: confidently wrong, and it
        # sends the next reader to change the wrong thing.
        raise UnsupportedStrategyConfig(
            f"the strategy asks for a {fill_clock_minutes}-minute fill clock but provides no "
            f"make_dual_clock(), so there is nothing to merge the two streams with — the runner "
            f"would have two feeds and no rule for which bar is stepped when. A strategy that "
            f"needs a second feed owns the merge; see "
            f"strategies/python/sos_fade/dual_clock.py."
        )


class OrderBridge:
    def __init__(
        self,
        bot_mt5,
        execution,
        ledger,
        log,
        *,
        notify=None,
        dry_run: bool = True,
        margin_safety_pct: float = DEFAULT_MARGIN_SAFETY_PCT,
        account_risk_cap_pct: Optional[float] = None,
        # ADDED to the broker balance before the cap measures anything. It must be the SAME
        # number the strategy sizes against - see `_account_balance`.
        sizing_basis_adjustment: float = 0.0,
        instance_dir: Optional[Path] = None,
    ) -> None:
        self._mt5 = bot_mt5
        # Where `position.json` lives. `None` disables the whole restore path — the bridge then
        # behaves exactly as it did before it existed, which is what every offline test that does
        # not care about restarts gets, and what a caller with no instance directory deserves.
        self._instance_dir = instance_dir
        # Set by `adopt_broker_state` when it has VERIFIED a recorded position against the broker,
        # and consumed by `apply_restore` after the warm-up. It is held rather than applied on the
        # spot because the warm-up replays 5,000 bars through this same emulator and would
        # overwrite anything written before it — see `apply_restore`.
        self._pending_restore: Optional[dict] = None
        self._restored = False
        self._ex = execution
        self._ledger = ledger
        self._log = log
        self._notify = notify or (lambda text, kind, reply_to=None: None)
        self.dry_run = dry_run
        self._margin_safety_pct = float(margin_safety_pct)
        # The ACCOUNT-level cap: max open risk across EVERY bot on this account, as a % of the
        # live balance. `None` = uncapped, which is the honest state for a one-bot account and
        # is what every result measured before it existed was taken on — inventing a default
        # would change a live bot's behaviour with no measurement behind it. The runner SAYS
        # which state it is in at startup, so "no cap" is a reported fact rather than an
        # absence nobody noticed (the `deadman_url` precedent). See G10.
        self._risk_cap_pct = None if account_risk_cap_pct is None else float(account_risk_cap_pct)
        self._sizing_basis_adjustment = float(sizing_basis_adjustment or 0.0)
        self._strategy_name = getattr(bot_mt5, "bot_label", "") or "strategy"

        self.state = BridgeState.LIVE
        self._rest: dict[tuple, Optional[_Rest]] = {s: None for s in SLOTS}
        # A slot whose last placement came back UNKNOWN. It is NOT a refusal and NOT a rest: it
        # means an order may or may not be at the broker under our magic, and the one thing we
        # must not do is send another. Cleared by the orphan sweep once the book can be read.
        self._unresolved: dict[tuple, bool] = {s: False for s in SLOTS}
        # Why the LAST refusal is remembered per side, rather than just logged and dropped.
        # A refused order is not by itself a broken state — the setup may never fill, and
        # halting on every unaffordable setup would stop a bot for a trade that never happened.
        # But if the EMULATOR then fills that same setup, the two ledgers part, and the halt
        # message must say *why the broker had no order* instead of the generic "your limit
        # filled here and not there". On 2026-08-07 that generic message was all Aaron got.
        self._refused: dict[tuple, str] = {s: "" for s in SLOTS}
        # One alert per distinct refusal per side. Re-stating an unaffordable setup every bar
        # for the six hours it rests is how a channel gets muted before the day it matters.
        self._refusal_alerted: dict[tuple, str] = {s: "" for s in SLOTS}
        # Has the ACCOUNT budget run out? Latched so the alert is loud once and then quiet, and
        # so RECOVERY speaks — without the second message, silence would mean either "there is
        # room again" or "still full", and the reader would have to go and look.
        # ⚠ Starts False, meaning "not blocked as far as we know". The first refresh that finds
        # no room announces it; a bot that starts with a full account says so on its first bar.
        self._room_blocked: bool = False
        # The same idea for the PARTIAL path, keyed on the cause rather than on a side: a
        # position that cannot be banked re-offers the identical problem on every 15m bar, and
        # an alert per bar is one nobody reads by the third. Cleared when a bank succeeds and
        # when a position opens, so a later genuine problem still speaks.
        self._partial_alerted: str = ""
        self._pos_ticket: Optional[int] = None
        # WHICH LEG opened the position, and therefore which clock manages it. The primary is
        # decided on 15-minute closes and the re-entry on the fill clock, so the two must not
        # both book the same trade or both ratchet the same stop. Read off the strategy at the
        # fill (`entry_kind`) rather than inferred from which slot's order we think filled.
        self._pos_intent: str = "primary"
        self._pos_dir: int = 0
        self._pos_entry: float = 0.0
        self._pos_lots: float = 0.0
        self._pos_stop: float = 0.0
        self._pos_intended: float = 0.0
        self._pos_risk_usd: float = 0.0
        self._pos_opened_bar: Optional[int] = None
        # Telegram's id for THIS position's entry message. The exit replies to it, so the two
        # halves of a trade read as one thread. None means the entry alert never landed, and the
        # exit then goes out standalone rather than not at all.
        self._pos_alert_id = None
        self.halt_reason: str = ""

    @property
    def is_flat(self) -> bool:
        """No position open AND nothing resting at the broker.

        Stricter than "no position" on purpose. This is the seam a runtime config change
        is applied on (see `runner._maybe_reload_runtime`), and a resting limit is an
        order the OLD settings sized and priced. Waiting for it to fill or be cancelled is
        what keeps every trade attributable to exactly one configuration — otherwise the
        ledger records a trade at 5% risk that was actually sized at 10%.
        """
        return self._pos_ticket is None and not any(self._rest.values())

    # ── startup ──────────────────────────────────────────────────────────────
    def begin_live(self) -> None:
        """Called once, after warmup, before the first live bar.

        If the emulator finished warmup holding a position, that trade's ENTRY happened in the
        past at a price that is gone. Opening it now at market would be a different trade — so
        the bridge sits in WARMING and places nothing until the emulator flattens naturally.
        This is why a bot's first live trade is always one whose entry decision was made on a
        live bar.

        🔴 **"Once" is a lie, and the halt guard below is why this docstring keeps the word
        anyway.** Three paths in `runner.py` call this again on a bot that has been trading for
        weeks — `_recover_link` after a link outage, the `gap > 4` re-warm, and
        `_maybe_reload_runtime` when a setting changes while flat. Each rebuilds the strategy
        and replays history, and this is the line that hands the rebuilt one back.
        """
        if self.state is BridgeState.HALTED:
            # 🔴 **THE HALT LATCHES, AND THIS IS THE LINE THAT MAKES THAT TRUE.** Every
            # branch below ASSIGNS `self.state`, so before this guard existed a halted bot went
            # back to LIVE on the next reconnect, bar gap or settings edit — and nothing
            # re-halted it, because both runner-side latches (`_fleet_halted`,
            # `_account_mismatch_halted`) had already fired and return early forever. The
            # account-identity case is the one that costs money: it halts *because the terminal
            # is logged into an account this bot was not pointed at*, and a reconnect put the
            # bot back to placing orders on exactly that account.
            #
            # The guard lives HERE, not at the three call sites, for the same reason the latch
            # exists at all: a rule enforced at every caller is one the fourth caller has never
            # heard of. `_halt` already refuses to re-halt an already-halted bridge; this is
            # that same rule arriving from the other side. Only a restart clears it.
            self._log.error(
                f"Re-warmed, but this bot is HALTED ({self.halt_reason}) and stays halted. It "
                f"will keep observing and place nothing. Restart it."
            )
            self._ledger.event("begin_live_refused_while_halted", reason=self.halt_reason)
            return
        if self._restored:
            # A RESTORED position is not a warm-up artefact: its entry is a real fill this bot
            # made and recorded, and the broker is holding it right now. The bridge must go
            # straight to LIVE so the very next bar can ratchet its stop — sitting in WARMING
            # would reproduce the exact failure the restore exists to end, one layer up.
            self.state = BridgeState.LIVE
            return
        if self._ex._pos_dir != 0:
            self.state = BridgeState.WARMING
            self._log.warning(
                "Warmup ended with the strategy holding a simulated position — its entry is in "
                "the past, so it will NOT be opened live. Waiting for it to close before "
                "placing anything."
            )
            self._ledger.event(
                "warmup_position_skipped", dir=self._ex._pos_dir, entry=self._ex._entry
            )
        else:
            self.state = BridgeState.LIVE

    def adopt_broker_state(self) -> None:
        """Read what MT5 already holds for this bot's magic, at startup.

        A position we have no record of is NOT adopted — it is a halt. Silently taking over an
        unknown position is how a restart doubles a book: the strategy would size a fresh entry
        with no idea it is already exposed.

        **The one exception is a position this bot wrote down itself** (`position_state.py`): a
        restart with a trade open used to halt and leave that trade unmanaged overnight — its
        broker stop stood, but nothing ratcheted it and the time stop never fired. If the record
        matches the broker on ticket, direction, size, entry and stop, the position is held for
        `apply_restore` to hand back to the emulator after the warm-up. **Every other shape still
        halts**, including a torn record, a ticket that does not match, and a single field that
        disagrees.
        """
        positions = self._mt5.get_open_positions()
        orders = self._mt5.get_pending_orders()
        if positions:
            if not self._stage_restore(positions):
                return
        for o in orders:
            # Resting orders from a previous run are stale by construction — the strategy
            # recomputes its limit every bar off state we no longer have.
            self._log.info(f"Cancelling stale pending order T{o.ticket} from a previous run")
            self._exec(
                lambda t=o.ticket: self._mt5.cancel_pending(t), f"cancel stale pending T{o.ticket}"
            )

    def _stage_restore(self, positions) -> bool:
        """Can this broker position be proved to be the one we wrote down? Halt if not.

        Returns True when a restore has been staged, False when the bridge has halted. The five
        refusals below are deliberately separate messages: "the two disagreed" is true of every
        cause at once and sends the reader to the wrong half of the system — the same defect the
        halt message for a vanished order was fixed for on 2026-08-07.
        """
        magic = self._mt5.magic
        if len(positions) > 1:
            self._halt(
                f"MT5 holds {len(positions)} positions under magic {magic} at startup; "
                f"this strategy takes one at a time, so no record can describe them. "
                f"Close them by hand before starting the bot."
            )
            return False

        p = positions[0]
        if self._instance_dir is None:
            self._halt(
                f"MT5 already holds a position under magic {magic} at startup and this "
                f"bridge was built with no instance directory, so it cannot read the "
                f"position record. Close it by hand before starting the bot."
            )
            return False

        record = position_state.read(self._instance_dir)
        if record is None:
            self._halt(
                f"MT5 already holds position T{p.ticket} under magic {magic} at startup, and "
                f"there is no usable record of it in "
                f"{position_state.path_for(self._instance_dir)}. The bot will NOT take it over — "
                f"it would size its next entry with no idea it is already exposed. The position "
                f"keeps its broker-side stop. Close it by hand, or clear it, before restarting."
            )
            return False

        symbol = getattr(self._mt5, "symbol", "") or ""
        if record.magic != magic or (symbol and record.symbol != symbol):
            self._halt(
                f"The position record in {position_state.path_for(self._instance_dir)} was "
                f"written for {record.symbol} magic {record.magic}, and this bot is "
                f"{symbol or '?'} magic {magic}. It describes a different bot's trade."
            )
            return False

        if int(p.ticket) != record.ticket:
            self._halt(
                f"MT5 holds position T{p.ticket} under magic {magic}, but the record describes "
                f"T{record.ticket}. Whatever is open is not the trade this bot wrote down, so it "
                f"will not be managed. The position keeps its broker-side stop."
            )
            return False

        diffs = position_state.disagreements(record, p, point=self._point())
        if diffs:
            self._halt(
                f"The recorded position T{record.ticket} and the one MT5 holds do not match: "
                + "; ".join(diffs)
                + ". Something changed it outside the bot — a hand edit in the terminal is the "
                "usual cause. It will NOT be adopted: every later stop move would be computed "
                "off a level the strategy never chose. The position keeps its broker-side "
                "stop; fix it by hand, or close it, then restart."
            )
            return False

        # Verified. The bridge's own bookkeeping can be set now; the EMULATOR's cannot, because
        # the warm-up has not run yet and would overwrite it (see `apply_restore`).
        self._pending_restore = record.strategy
        self._pos_ticket = int(p.ticket)
        self._pos_dir = record.broker.dir
        self._pos_entry = record.broker.entry
        self._pos_lots = record.broker.lots
        self._pos_stop = record.broker.stop
        # NOT known across a restart, and each is left at the value that reads as "unknown"
        # rather than at a plausible stand-in. `_pos_intended` would otherwise report a slippage
        # of zero, which is a measurement nobody took; `_pos_opened_bar` counts from wherever
        # this process's warm-up stopped, so a held-bars figure derived from it would be an
        # arbitrary integer wearing a real field's name.
        self._pos_intended = 0.0
        self._pos_opened_bar = None
        # No entry alert exists in this process, so the exit posts standalone instead of as a
        # reply. One orphaned exit message beats no exit message.
        self._pos_alert_id = None
        self._pos_risk_usd = (
            abs(record.broker.entry - record.broker.stop)
            * record.broker.lots
            * self._contract_size()
        )
        return True

    def stage_rewarm(self) -> None:
        """Carry an OPEN position across a re-warm. Call BEFORE the strategy is rebuilt.

        🔴 **A re-warm mid-trade used to lose the position and halt the bot, and it is the more
        likely door onto the same failure than a process restart.** `_recover_link` and the
        `gap > 4` branch both rebuild the strategy and replay 5,000 bars through a fresh
        emulator — so a link outage while a trade was open (MetaTrader auto-updated under the
        bot for 50 minutes on 2026-08-04) left the broker holding a position the emulator knew
        nothing about, and `_agrees` halted on the very next bar. The bot survived the outage and
        then stopped managing the trade because of the recovery.

        Nothing is verified against the broker here, and nothing needs to be: this is the same
        process that has been holding the position all along, so the state is not a claim being
        re-read off disk — it is being handed from one emulator instance to the next.
        """
        if self._pos_ticket is None:
            self._pending_restore = None
            return
        try:
            self._pending_restore = self._ex.snapshot_position()
        except Exception as e:
            # Deliberately not a halt: the re-warm has not happened yet, so halting here would
            # stop a bot that is still perfectly coherent. `_agrees` halts on the next bar if the
            # position really is lost, which is the existing, tested path.
            self._pending_restore = None
            self._log.error(
                f"Could not carry the open position across the re-warm: {e}. The bridge will "
                f"halt on the next bar if the strategy and the broker have parted."
            )

    def apply_restore(self, *, announce: bool = True) -> bool:
        """Hand the verified position back to the emulator. Call AFTER the warm-up.

        ⚠ **The ORDER is the whole reason this is a second method.** `warm()` replays ~5,000 bars
        through this same `Execution` object, and that replay opens and closes imaginary trades of
        its own — so anything written into the emulator before it is overwritten by a fiction.
        Staging at `adopt_broker_state` (which must read the broker before anything else can take
        time) and applying here is what keeps the real position the last word.
        """
        if self._pending_restore is None:
            return False
        snap = self._pending_restore
        self._pending_restore = None
        try:
            self._ex.restore_position(snap)
        except Exception as e:
            # A record that got past every check above and still cannot be applied means the
            # emulator's own state shape moved under a record written by an older build. Halting
            # is the same answer as an unreadable record, for the same reason.
            self._halt(
                f"The recorded position T{self._pos_ticket} passed every broker check and "
                f"the strategy refused to restore it: {e}. This usually means the record "
                f"was written by a different version of the strategy. The position keeps "
                f"its broker-side stop; close it by hand, or clear the record, then "
                f"restart."
            )
            return False
        self._restored = True
        # 🔴 **WHICH LEG OWNS THIS TRADE HAS TO COME BACK TOO, AND IT WAS THE ONE FIELD THAT DID
        # NOT (fixed 2026-09-02, with the blanket re-entry refusal).** `_pos_intent` is stamped at
        # the FILL and defaults to `"primary"` at construction, so a restart holding a RE-ENTRY
        # picked it back up as a primary: the 15-minute clock would have ratcheted its stop and
        # booked its close, and the fill clock — which is the one that opened it — would have sat
        # out. A hold length is an index into ONE clock's bar numbering and these two differ by
        # 3x, so the trade would also have been booked in the wrong frame.
        #
        # ⚠ **It is read off the EMULATOR rather than off the position record**, because the
        # emulator has just restored that same field from that same record (`_POSITION_FIELDS`
        # carries `_entry_kind`) and it refuses an incomplete record rather than defaulting. Two
        # readers of one record is how the two ends drift; there is one reader, and this asks it.
        #
        # ⚠ **The `"primary"` fallback is for a strategy with no re-entry concept at all**, which
        # is every other bot here — for one that has the concept the attribute always exists, so
        # this is not a guess standing in for an unasked question.
        # ⚠ **This was unreachable until today**: no configuration with a re-entry could start.
        self._pos_intent = getattr(self._ex, "entry_kind", "primary")
        self._log.info(
            f"Restored position T{self._pos_ticket} — {self._side(self._pos_dir)} "
            f"{self._pos_lots} lots @ {self._pos_entry}, stop {self._pos_stop}, "
            f"stage {getattr(self._ex, '_stage', '?')}, opened by the "
            f"{'re-entry' if self._pos_intent == 'secondary' else 'primary'}. It will be managed "
            f"from the next bar."
        )
        self._ledger.event(
            "position_restored",
            ticket=self._pos_ticket,
            dir=self._pos_dir,
            lots=self._pos_lots,
            entry=self._pos_entry,
            stop=self._pos_stop,
            stage=getattr(self._ex, "_stage", None),
            # WHICH CLOCK picks the trade back up. Recorded because it decides who ratchets the
            # stop from here, and because a restart is the only moment it can be got wrong — a
            # fill stamps it from the order that filled, and that cannot disagree with itself.
            intent=self._pos_intent,
            reason="restart" if announce else "rewarm",
        )
        # ⚠ A re-warm passes `announce=False` and the record above still lands. `_recover_link`
        # and the gap branch each already send their own message for the SAME event, and two
        # alerts for one event is how a channel gets muted — but the ledger has to carry it
        # either way, because "the position survived the re-warm" is exactly what a later audit
        # needs and it is invisible from the outside.
        if announce:
            self._notify(
                alert(
                    "🔄",
                    "TRADE RESUMED",
                    self._strategy_name,
                    joined(
                        [
                            f"{self._side(self._pos_dir)} {self._pos_lots} lots @ {self._pos_entry}",
                            f"stop {self._pos_stop}",
                        ]
                    ),
                    "The bot restarted and picked its open trade back up. It manages it from the "
                    "next bar. Nothing to do.",
                ),
                notify.HEALTH,
            )
        return True

    def _save_position(self) -> None:
        """Write the open position down, so a restart can pick it up. Never raises.

        Called after every change to the position — the fill, and every stop move — because the
        stop is the field that moves, and a record holding last hour's stop would be REFUSED at
        the next start (the broker's real stop would disagree with it). A stale record does not
        adopt a wrong stop; it costs the restore.
        """
        if self._instance_dir is None or self._pos_ticket is None:
            return
        try:
            snap = self._ex.snapshot_position()
        except Exception as e:
            self._log.warning(f"Could not snapshot the position for the restart record: {e}")
            return
        ok = position_state.write(
            self._instance_dir,
            bot=getattr(self._ledger, "bot_key", "") or self._strategy_name,
            symbol=getattr(self._mt5, "symbol", "") or "",
            magic=self._mt5.magic,
            ticket=self._pos_ticket,
            broker=position_state.BrokerFacts(
                dir=self._pos_dir, lots=self._pos_lots, entry=self._pos_entry, stop=self._pos_stop
            ),
            strategy=snap,
        )
        if not ok:
            self._log.warning(
                "Could not write the position record. The trade is unaffected; a restart before "
                "it closes would halt rather than resume it."
            )

    # ── the per-bar entry point ──────────────────────────────────────────────
    def resting_lots(self, direction: int) -> Optional[float]:
        """The lot size ACTUALLY resting in the primary slot on one side, or `None` if nothing is.

        🔴 **Read from `_rest`, never recomputed, and that is the entire safety property.** The
        strategy sizes in INSTRUMENT UNITS (ounces for gold); MT5 takes LOTS. Deriving a display
        figure here would be a second conversion competing with `order_sizing`'s one seam — the
        defect that rested 54.82 lots on a $2,000 account, 221x the intent. This returns the
        number that was sent to the broker and is showing in the terminal, or nothing.

        ⚠ **`None` means NO ORDER IS RESTING — it is never "cannot ask".** A caller with no bridge
        at all does not hold this method; absence of the bridge is how *cannot ask* is expressed
        (`setup_alerts.SetupAlerts`, whose `lots_for` defaults to None). Collapsing the two would
        let a refused order and an offline backtest render the same message.
        """
        held = self._rest.get(primary_slot(direction))
        return None if held is None else float(held.lots)

    def sync(self, dec, sig) -> None:
        """Reconcile once, for the bar that just closed. Order matters: observe what the broker
        did during the bar, THEN compare, THEN act."""
        if self.state is BridgeState.HALTED:
            return

        positions = self._mt5.get_open_positions()
        # BEFORE `_observe_close`, and the order is the whole design. A commanded exit leaves
        # the emulator flat with the broker still holding, which `_agrees` halts on — correctly,
        # because that is otherwise indistinguishable from a position vanishing for a reason
        # nobody can name. So the broker is brought into line FIRST, and the ordinary close
        # path below then books, alerts and records the trade exactly as it does every other
        # exit. Doing it afterwards would need a second booking path for one kind of exit.
        positions = self._mirror_strategy_exit(positions, dec)
        self._observe_close(positions, dec, sig, owner="primary")
        self._observe_open(positions, dec, sig)
        # AFTER `_observe_open`, which consumes the filled slot's rest when a position appears
        # perfectly ordinary fill reads as a vanished order.
        self._observe_vanished()
        # AFTER `_observe_vanished`, which is the last thing that can legitimately clear a
        # `_rest` entry. Running it earlier would let a rest the bot is about to forget count as
        # "known" and leave a genuine orphan resting for another bar.
        self._observe_orphans()

        if self.state is BridgeState.WARMING:
            if self._ex._pos_dir == 0:
                self.state = BridgeState.LIVE
                self._log.info(
                    "Warmup position closed — the bot is now LIVE and will place orders."
                )
                self._ledger.event("went_live")
            else:
                return

        if not self._agrees(positions):
            return

        if self._ex._pos_dir != 0:
            self._cancel_all_rest("a position is open")
            # BEFORE the stop, matching the emulator's own order: it banks the rung, then moves
            # the stop behind what is left. Reversed, a stop staged for the post-bank size would
            # be sent while the broker still holds the pre-bank size.
            self._sync_partials(positions)
            self._sync_stop(dec)
        else:
            # The PRIMARY's two slots only. The re-entry's slot is reconciled on the fill
            # clock by `sync_fast`, and reaching across from here would price its limit off a
            # 15-minute bar it never saw.
            self._sync_slot(PRIMARY_LONG, self._ex._pend_long, sig)
            self._sync_slot(PRIMARY_SHORT, self._ex._pend_short, sig)

    def sync_fast(self, step) -> None:
        """Reconcile the RE-ENTRY, on the fill clock. **G18 stage 2.**

        `sync` above owns the primary's two slots and any position the PRIMARY opened. This owns
        the re-entry's two slots and any position the RE-ENTRY opened. Neither reaches across,
        and the split is not tidiness:

        - **A stop belongs to the clock that computes it.** The strategy only writes a stop onto
          the 15-minute decision while the open trade is a primary (`execution.step`), so the
          15-minute path is already inert on a re-entry's stop — and this path must stay equally
          inert on a primary's, or it would ratchet to a value the primary's own leg has not
          decided yet.
        - **A hold length is an index into ONE clock's bar numbering.** Booking a trade on the
          clock that did not open it would measure its life in the wrong frame, and here the two
          differ by 3x.

        🔴 **Cancelling every other resting order the moment a position appears is the safety
        half, and it is why this runs the whole cycle rather than just placing an order.** The
        primary's limits are placed while the bot is flat, which is exactly when a re-entry can
        fill. Left until the next 15-minute close they are a second position waiting to happen —
        up to fifteen minutes of it. On this clock the window is one fill-clock bar.

        ⚠ **THE BLANKET REFUSAL THAT KEPT THIS OFF EVERY LIVE BOT WAS LIFTED ON 2026-09-02**, so
        a bot with the re-entry switched on now reaches this path. What refuses in its place is
        `assert_secondary_wired`, and it refuses something else: a re-entry with no fill clock to
        run on. ⚠ **Rule 9 has not been satisfied — no re-entry order has ever reached a broker.**
        """
        if self.state is not BridgeState.LIVE:
            # WARMING is the 15-minute path's transition to make: it owns the warm-up position
            # whose closing is the thing being waited for. HALTED places nothing, ever.
            return

        bar = getattr(step, "bar", None)
        sig = _FastSig(
            index=getattr(bar, "index", None),
            time_ms=getattr(bar, "timestamp_ms", None),
        )
        dec = self._fast_decision()

        positions = self._mt5.get_open_positions()
        self._observe_close(positions, dec, sig, owner="secondary")
        self._observe_open(positions, dec, sig)
        self._observe_vanished()
        self._observe_orphans()

        if not self._agrees(positions):
            return

        if self._ex._pos_dir != 0:
            self._cancel_all_rest("a position is open")
            if self._pos_intent == "secondary":
                self._sync_partials(positions)
                self._sync_stop(dec)
            return

        pend = getattr(self._ex, "_pend_sec", None)
        wanted = secondary_slot(pend.dir) if pend is not None else None
        # BOTH slots every bar, so the side that is no longer armed has its order cancelled
        # rather than left resting because nothing came back to look at it.
        for slot in (SECONDARY_LONG, SECONDARY_SHORT):
            self._sync_slot(slot, pend if slot == wanted else None, sig)

    def _fast_decision(self) -> "_FastDec":
        """The re-entry's live stop and targets, read off the strategy.

        ⚠ **An unreadable stop is SAID, never treated as "no change".** Leaving the broker's stop
        where it is happens to be the safe direction, but it is also exactly what a correctly
        ratcheting trade looks like from outside — so a strategy object that cannot answer would
        be indistinguishable from one with nothing to move. Rule 1.
        """
        if self._ex._pos_dir == 0 or self._pos_intent != "secondary":
            return _FastDec()
        getter = getattr(self._ex, "_current_stop", None)
        if not callable(getter):
            self._log.error(
                "The re-entry is holding a position and the strategy cannot report its stop. "
                "The broker's stop stands and is NOT being ratcheted."
            )
            self._ledger.event("secondary_stop_unreadable", ticket=self._pos_ticket)
            return _FastDec()
        return _FastDec(
            stop=getter(),
            tp1=getattr(self._ex, "_tp1", 0.0) or 0.0,
            tp2=getattr(self._ex, "_tp2", 0.0) or 0.0,
        )

    # ── observation ──────────────────────────────────────────────────────────
    def _observe_close(self, positions, dec, sig, owner: str = "primary") -> None:
        if self._pos_ticket is None:
            return
        if any(p.ticket == self._pos_ticket for p in positions):
            return
        if self._pos_intent != owner:
            # The OTHER clock opened this trade and books it. Not a guess about who is faster:
            # `_pos_opened_bar` is an index into the opening clock's own bar numbering, so the
            # hold length this method reports is meaningless measured against the other one —
            # and the two frames here differ by 3x. The same trade booked twice would also
            # double every alert and every ledger row.
            return
        # NET of swap and commission, with the parts kept separate — see
        # `mt5_ops.get_deal_breakdown`. The R below is therefore the R the ACCOUNT got, not the
        # R the price move implies, which is the only version worth alerting on: a scratch that
        # is +0.02R gross and −0.06R after an overnight swap is a loss, and reporting the gross
        # would make the live record disagree with the balance for no stated reason.
        #
        # `get_deal_breakdown` is optional on the handle on purpose. This bridge is driven by
        # test doubles and by an older `mt5_ops` on any box that has not pulled, and a missing
        # method must degrade to the previous behaviour rather than crash out of an EXIT path —
        # losing the exit record is far worse than losing the cost breakdown.
        costs = None
        if hasattr(self._mt5, "get_deal_breakdown"):
            b = self._mt5.get_deal_breakdown(self._pos_ticket)
            # `deals: 0` is "not found", not "free" — fall back rather than book zero costs.
            if b and b.get("deals"):
                costs = b
        if costs is not None:
            price, pnl = costs["close_price"], costs["net_usd"]
        else:
            price, pnl = self._mt5.get_deal_result(self._pos_ticket)
        r = (pnl / self._pos_risk_usd) if self._pos_risk_usd else None
        reason = getattr(dec, "exit_reason", "") or self._infer_exit_reason(price)
        held = None
        if self._pos_opened_bar is not None and getattr(sig, "index", None) is not None:
            held = sig.index - self._pos_opened_bar
        side = "LONG" if self._pos_dir > 0 else "SHORT"
        self._log.info(
            f"POSITION CLOSED | T{self._pos_ticket} {side} @ {price} | "
            f"P&L ${pnl:,.2f}" + (f" ({r:+.2f}R)" if r is not None else "")
        )
        self._ledger.trade_closed(
            ticket=self._pos_ticket,
            direction=side,
            symbol=self._mt5.symbol,
            price=price,
            pnl_usd=pnl,
            r_multiple=r,
            reason=reason,
            lots=self._pos_lots,
            held_bars=held,
            # ⚠ **And `held_bars` is counted in the OPENING clock's frame**, which is why the leg
            # has to travel with it — a re-entry's 12 bars is an hour and a primary's is three.
            intent=self._pos_intent,
            # The measurement this bot was armed to take. `entry_price`/`intended_price` give
            # entry slippage, gross-vs-net gives the real cost of the hold, and both are needed
            # per trade because a single netted figure cannot be taken apart afterwards.
            gross_usd=costs["gross_usd"] if costs else None,
            swap_usd=costs["swap_usd"] if costs else None,
            commission_usd=costs["commission_usd"] if costs else None,
            entry_price=self._pos_entry,
            intended_price=self._pos_intended,
        )
        self._notify(
            alerts.format_exit(
                strategy=self._strategy_name,
                symbol=self._mt5.symbol,
                exit_price=price,
                pnl_usd=pnl,
                r_multiple=r,
                digits=self._digits(),
                # Nested getattr on purpose: this package reads the strategy defensively everywhere
                # else, and a strategy without a `cfg` must not be able to stop an exit alert.
                scratch_r=getattr(getattr(self._ex, "cfg", None), "exec_scratch_r", 0.15),
                threaded=self._pos_alert_id is not None,
                # The SAME reason the ledger records, so the message and the audit trail cannot
                # disagree. It is what separates a -0.02R scratch from a -1.00R loser on a screen
                # where both say "exited at a stop", and only one of them is the risk rule working.
                exit_reason="" if reason == "closed" else reason,
                when=self._bar_time(sig),
            ),
            notify.TRADE,
            reply_to=self._pos_alert_id,
        )
        self._pos_ticket = None
        self._pos_dir = 0
        self._pos_risk_usd = 0.0
        self._pos_opened_bar = None
        self._pos_alert_id = None
        # The trade is over, so the restart record describes a ticket that no longer exists. It
        # could not restore anything (the ticket cannot match a position that is not there), but
        # leaving it would put a dead trade in front of the next person reading the instance
        # directory. `_restored` is cleared too: the NEXT position is an ordinary live fill.
        self._restored = False
        if self._instance_dir is not None:
            position_state.clear(self._instance_dir)

    def _mirror_strategy_exit(self, positions, dec):
        """Close the broker position when the STRATEGY has exited a trade the broker cannot.

        The strategy has already exited in its own book — a target that took the whole position,
        a person asking to get out, or the clock running out — and each leaves an exit fill on
        this bar's decision. This is the other half: the broker still holds the position, and
        without this nothing in this bridge can take it off at market.

        🔴 **THIS IS THE FULL-EXIT-AT-A-PRICE PATH, and it is why `assert_supported` no longer
        refuses a ladder that banks 100%.** `_sync_partials` reconciles the broker DOWN to the
        size the strategy still wants, which cannot express zero: a rung taking the last of the
        position finalises the trade in the same step, so by the time the bridge looks, the
        strategy is flat and there is no "intended size" left to reconcile towards. The two are
        complementary rather than alternatives — a bank that leaves a runner is a reconciliation,
        and a bank that ends the trade is an exit.

        🔴 **IT ALSO CLOSES A HOLE THAT WAS LIVE.** The time stop is ON for the armed bot
        (36 hours, before-breakeven only) and nothing mirrored it: the strategy would exit in its
        own book, the broker would keep the position, and the bridge would halt on the next bar
        with the trade still open and unmanaged. Only the operator's own close was ever wired.

        ⚠ **It acts on the strategy's own exit record, never on a flag this layer invents.**
        `algos/live/` holds no trading logic — the strategy decides it is out, and the bridge
        mirrors that, which is the same rule that keeps a live result comparable to a backtest.

        ⚠ **A FAILED close is left to halt.** It returns the book unchanged, so `_agrees` sees
        the emulator flat against a live broker position and stops the bot — which is the right
        outcome: the two ledgers genuinely have parted, and carrying on would compute every
        later decision against a trade that is still open. Retrying here would be a recovery
        tool repeating the fault it is recovering from.

        Returns the position list to reconcile against — re-read from the broker after a
        successful close, so the verdict comes from the ACCOUNT rather than from a return code.
        """
        if self._pos_ticket is None:
            return positions
        fills = getattr(dec, "fills", ()) or ()
        tag = next(
            (
                t
                for f in fills
                if f.kind == "exit"
                for t in BRIDGE_OWNED_EXITS
                if str(f.order_id).endswith(t)
            ),
            None,
        )
        if tag is None:
            return positions
        # 🔴 **THE STRATEGY MUST BE FLAT, AND THIS IS WHAT SEPARATES A FULL EXIT FROM A BANK.**
        # A target that takes 50% and rides the rest emits exactly the same `-TP1` exit fill as
        # one that takes the lot. Acting on the tag alone would close the WHOLE position on a
        # partial and delete a runner the strategy is still managing. `_sync_partials` owns the
        # case where the trade continues; this owns only the case where it ended.
        if self._ex._pos_dir != 0:
            return positions
        if not any(p.ticket == self._pos_ticket for p in positions):
            # Already gone — it filled a stop in the same instant, or a previous pass closed it.
            # Not an error, and not a second close: the ordinary path books it.
            return positions

        label = tag.lstrip("-")
        side = "bullish" if self._pos_dir > 0 else "bearish"
        if self.dry_run:
            self._log.info(f"[DRY RUN] would close T{self._pos_ticket} at market ({label})")
            self._ledger.event("dry_run_action", action="mirrored_exit", exit=label)
            return positions

        self._log.info(f"MIRRORING {label} EXIT | closing T{self._pos_ticket} at market")
        ok, price, _pnl = self._mt5.close_position(self._pos_ticket, side, label)
        if not ok:
            self._log.error(
                f"{label} close of T{self._pos_ticket} FAILED. The strategy is flat and the "
                f"broker is not; the bridge will halt on the next check rather than trade "
                f"against a position it does not believe it has."
            )
            self._ledger.event("commanded_close_failed", ticket=self._pos_ticket, exit=label)
            self._notify(
                alert(
                    "⛔",
                    "CLOSE FAILED",
                    self._mt5.bot_label,
                    "It was asked to close the open trade and the broker refused.",
                    "The position is STILL OPEN and the bot will halt. Close it by hand.",
                ),
                notify.HEALTH,
            )
            return positions

        self._ledger.event("commanded_close", ticket=self._pos_ticket, price=price, exit=label)
        # Re-read rather than assuming: the account is what says whether it is gone.
        return self._mt5.get_open_positions()

    def _observe_open(self, positions, dec, sig) -> None:
        if self._pos_ticket is not None or not positions:
            return
        p = positions[0]
        side = "LONG" if p.type == 0 else "SHORT"
        d = 1 if p.type == 0 else -1
        slot = self._slot_that_filled(p, d)
        self._pos_intent = slot[0]
        rest = self._rest.get(slot)
        intended = rest.price if rest else 0.0
        # The order that filled is no longer resting.
        self._rest[slot] = None
        self._pos_ticket = p.ticket
        self._pos_dir = d
        self._pos_entry = p.price_open
        self._pos_lots = p.volume
        self._pos_stop = p.sl
        self._pos_intended = intended
        self._pos_opened_bar = getattr(sig, "index", None)
        # Risk in dollars, for the R on the exit message. Measured off the BROKER's fill and the
        # stop that was actually attached, not off the strategy's intended price — R has to
        # describe the trade that happened.
        self._pos_risk_usd = abs(p.price_open - p.sl) * p.volume * self._contract_size()
        self._log.info(
            f"POSITION OPENED | T{p.ticket} {side} {p.volume}L @ {p.price_open} | SL={p.sl}"
        )
        # A new trade is a new chance to bank. Whatever the LAST position could not bank must not
        # silence this one — a latch that outlives its cause is a guard that has stopped guarding.
        self._partial_alerted = ""
        # ONE balance read, shared by the record and the message below. Two reads of a moving
        # number would let the ledger and the Telegram alert disagree about the same trade.
        realised = self._realised_risk_pct()
        self._ledger.trade_opened(
            ticket=p.ticket,
            direction=side,
            symbol=self._mt5.symbol,
            lots=p.volume,
            price=p.price_open,
            stop=p.sl,
            intended_price=intended,
            tp1=getattr(dec, "tp1", 0.0) or 0.0,
            tp2=getattr(dec, "tp2", 0.0) or 0.0,
            # Read off the strategy LIVE, not cached at construction — the runner mutates
            # this same config object when a runtime change is applied, so caching it here
            # would record the risk the bot started with rather than the one it sized on.
            # `Execution.cfg` is a real property; the nested getattr is only so a test
            # double without one does not break an alert.
            # ⚠ This is the setting ASKED FOR and it is the PRIMARY's number even on a re-entry.
            # What the trade actually got is the measured pair below. Rule 3.
            risk_pct=getattr(getattr(self._ex, "cfg", None), "exec_risk_pct", None),
            risk_usd=self._pos_risk_usd or None,
            risk_pct_realised=realised,
            intent=self._pos_intent,
            confluences=self._confluences(dec, sig),
        )
        self._pos_alert_id = self._notify(
            alerts.format_entry(
                strategy=self._strategy_name,
                symbol=self._mt5.symbol,
                direction=side,
                entry=p.price_open,
                stop=p.sl,
                lots=p.volume,
                digits=self._digits(),
                point=self._point(),
                # The dollars already computed above, and the % that produced them. This is the ONLY
                # message that states the risk — the exit replies to it, so repeating it there is
                # repeating what is one tap up the thread.
                risk_usd=self._pos_risk_usd or None,
                # 🔴 **THE MEASURED PERCENTAGE, NOT THE SETTING (2026-09-02).** This message said
                # the primary's figure for every trade, so the first live re-entry would have
                # announced 10% while risking 5%. It falls back to the setting only when the
                # balance cannot be read, which is the one case where nothing can be measured.
                # ⚠ Read from the variable, not by calling again: a second call is a second
                # balance read, and two readings of a moving number in one message is how a
                # message comes to disagree with itself.
                risk_pct=(
                    realised
                    if realised is not None
                    else getattr(getattr(self._ex, "cfg", None), "exec_risk_pct", None)
                ),
                when=self._bar_time(sig),
            ),
            notify.TRADE,
        )
        # Record it the moment it exists, not at the end of the bar: a process that dies between
        # the fill and the next stop move must still leave a resumable trade behind.
        self._save_position()

    def _slot_that_filled(self, position, d: int):
        """Which slot's resting order became this position?

        The primary and the re-entry can both have a limit resting on side `d`, so "the position
        is long" no longer names one order.

        ⚠ **The TICKET is asked first, and nothing here depends on it matching.** Where a
        triggered pending order carries its ticket through to the position it settles the
        question outright; where it does not, the strategy's own `entry_kind` is the only other
        thing that knows which leg filled, and `_agrees` has just checked that the two books
        describe the same position.
        """
        for slot in (primary_slot(d), secondary_slot(d)):
            rest = self._rest.get(slot)
            if rest is not None and rest.ticket == position.ticket:
                return slot
        return (
            secondary_slot(d)
            if getattr(self._ex, "entry_kind", "primary") == "secondary"
            else primary_slot(d)
        )

    def _observe_orphans(self) -> None:
        """A resting order at the broker, under OUR magic, that this bot has no record of.

        🔴 **Built 2026-08-25. This is the direction nothing ever looked.** `_observe_vanished`
        below checks the orders we REMEMBER against the broker; nothing checked the broker
        against what we remember. Startup sweeps stale orders and then never looks again — so
        four orders sat resting and unowned for five hours, through twenty bars, and the first
        thing that noticed was the position-count halt after they had all filled.

        ⚠ **It CANCELS rather than adopting.** Adoption needs a decision about which strategy
        intent the order belongs to, and getting that wrong silently attaches a live order to
        the wrong side. Cancelling costs at most one bar: the strategy re-offers its limit on
        the next close, and `_sync_slot` places a fresh one it actually owns.

        ⚠ **An unreadable order book does nothing at all** — no cancels, and `_unresolved` stays
        set, so nothing is placed either. Fail closed: "cannot ask" is never "nothing there".
        """
        live = self._mt5.pending_orders_strict()
        if live is None:
            return  # cannot ask. Sweep nothing, clear nothing, and keep placement blocked.

        known = {r.ticket for r in self._rest.values() if r is not None}
        orphans = [o for o in live if o.ticket not in known]
        for o in orphans:
            self._log.error(
                f"ORPHAN ORDER T{o.ticket} ({o.volume_current} lots @ {o.price_open}) is resting "
                f"under magic {self._mt5.magic} and this bot has no record of placing it. "
                f"Cancelling it."
            )
            self._ledger.event(
                "order_orphaned",
                ticket=int(o.ticket),
                lots=float(o.volume_current),
                price=float(o.price_open),
                stop=float(o.sl),
            )
            self._exec(
                lambda t=o.ticket: self._mt5.cancel_pending(t), f"cancel orphan pending T{o.ticket}"
            )
        if orphans:
            self._notify(
                alert(
                    "⚠️",
                    "ORPHAN ORDERS",
                    self._mt5.bot_label,
                    f"{len(orphans)} resting order(s) were at the broker under this bot's magic "
                    f"with no record of being placed. They have been cancelled.",
                    "Nothing was opened. The usual cause is a broker request whose reply never "
                    "came back. Worth reading the log for why.",
                ),
                notify.HEALTH,
            )
        # The book was READ, so any unknown placement is now resolved one way or the other:
        # it either showed up here and was cancelled, or it never landed.
        self._unresolved = {s: False for s in SLOTS}

    def _observe_vanished(self) -> None:
        """A resting order that is gone from the broker WITHOUT having filled.

        🔴 **Built 2026-08-07 because nothing could see this.** The bot's sell limit was deleted
        by the broker with `deleted [no money]` — it could not afford to activate 54.82 lots on a
        $2,000 account — and the bot had no idea. It kept believing the order was resting, the
        emulator filled itself on the same bar, and the only symptom anywhere in the system was a
        generic halt six hours later saying the two disagreed.

        A pending order can leave the book three ways: it FILLS (a position appears, handled one
        method up), WE cancel it (its slot is cleared at the same moment), or the BROKER removes
        it — margin, expiry, an admin action, a manual delete in the terminal. Only the third
        reaches here, and it is always worth a message: it means an order the strategy is still
        counting on does not exist.
        """
        if not any(self._rest.values()):
            return
        live = {o.ticket for o in (self._mt5.get_pending_orders() or [])}
        for slot, held in list(self._rest.items()):
            if held is None or held.ticket in live:
                continue
            d = slot[1]
            self._rest[slot] = None
            why = (
                f"The {slot_label(slot)} limit T{held.ticket} ({held.lots} lots @ {held.price}) "
                f"is no longer at the broker and never filled. The broker removed it — the "
                f"usual cause is that the account could not afford to activate it."
            )
            self._log.error(why)
            self._ledger.event(
                "order_vanished",
                dir=d,
                ticket=held.ticket,
                lots=held.lots,
                price=held.price,
                stop=held.sl,
            )
            # HEALTH, not TRADE: no trade happened. It is the machinery failing to carry out an
            # instruction, which is the same class of fact as a halt.
            self._notify(
                alert(
                    "⚠️",
                    "ORDER GONE",
                    self._mt5.bot_label,
                    why,
                    "The strategy still expects it. Check the account's free margin.",
                ),
                notify.HEALTH,
            )

    def _agrees(self, positions) -> bool:
        """Both ledgers must tell the same story. Anything else halts — see the module
        docstring for why this is not 'log and continue'."""
        emu = self._ex._pos_dir != 0
        broker = bool(positions)
        if len(positions) > 1:
            self._halt(
                f"MT5 holds {len(positions)} positions under magic {self._mt5.magic}; "
                f"this strategy takes one at a time."
            )
            return False
        if emu and not broker:
            # Name the refusal if there was one. The generic sentence below is true but useless
            # on its own — it describes the symptom of every cause at once, and on 2026-08-07 it
            # sent the reader looking at the fill logic when the answer was the order size.
            # Ordered: this side's slots first, then anything else that refused. A refusal on
            # the side the emulator actually filled is the one that explains the disagreement.
            because = next(
                (
                    self._refused.get(slot, "")
                    for slot in sorted(SLOTS, key=lambda s: s[1] != self._ex._pos_dir)
                    if self._refused.get(slot, "")
                ),
                "",
            )
            self._halt(
                "The strategy believes it is in a position but MT5 has none. Its resting "
                "limit filled in the emulator and not at the broker (or the position was "
                "closed outside the bot). Every later decision would be computed against "
                "a trade that does not exist."
                + (f"\nThe last order on this side was REFUSED: {because}" if because else "")
            )
            return False
        if broker and not emu:
            self._halt(
                "MT5 holds a position the strategy does not know about. It will keep its "
                "broker-side stop, but the bot will not manage it."
            )
            return False
        return True

    # ── action ───────────────────────────────────────────────────────────────
    def _sync_slot(self, slot, pend, sig) -> None:
        """Make the broker's resting order in one slot match the strategy's intent.

        ⚠ **One slot, and only this slot.** The primary's two slots are reconciled on 15-minute
        closes and the re-entry's on the fill clock, so a call that reached across would place an
        order priced off a bar its own strategy leg has not seen.
        """
        direction = slot[1]
        if self._unresolved[slot]:
            # Set by a placement whose outcome could not be established, cleared by the first
            # sweep that manages to read the book. Nothing in this slot moves in between - not a
            # placement, not a cancel - because every one of those needs to know what is already
            # there.
            self._log.error(
                f"the {slot_label(slot)} slot is unresolved - a previous placement's outcome is "
                f"still unknown. Doing nothing in this slot."
            )
            return
        held = self._rest[slot]
        if pend is None:
            if held is not None:
                self._drop_rest(slot, held, "cancel")
            self._refused[slot] = ""
            self._refusal_alerted[slot] = ""
            return

        plan = self._plan(direction, pend)
        if not plan.ok:
            self._record_refusal(slot, plan, pend)
            if held is not None:
                # The strategy still wants this trade, but we cannot place it at the size it
                # asked for. Leaving a stale order resting would mean the broker carries a size
                # nobody currently endorses.
                self._drop_rest(slot, held, "cancel (refused)")
            return

        self._refused[slot] = ""
        self._refusal_alerted[slot] = ""
        lots = plan.lots

        if held is None:
            self._place(slot, lots, pend, sig, plan)
            return

        # MODIFY cannot change volume (see mt5_ops) — a size change is a cancel + re-place.
        if abs(lots - held.lots) > 1e-9:
            # 🔴 **The re-place is CONDITIONAL on the cancel, since 2026-08-25.** This threw the
            # cancel's answer away and cleared `_rest` regardless, so a cancel that failed left
            # an order resting that the bot had forgotten — and then placed a second one on top
            # of it. That is one of the three ways one order became five positions, and unlike
            # the other two it needs no timeout at all: an ordinary rejected cancel does it.
            if not self._drop_rest(slot, held, "re-size"):
                return
            self._place(slot, lots, pend, sig, plan)
            return

        if self._moved(held.price, pend.edge) or self._moved(held.sl, pend.sl):
            ok = self._exec(
                lambda t=held.ticket: self._mt5.modify_pending(t, pend.edge, pend.sl),
                f"move {slot_label(slot)} limit T{held.ticket} → {pend.edge} SL {pend.sl}",
            )
            if ok:
                self._rest[slot] = _Rest(held.ticket, pend.edge, lots, pend.sl)

    def _drop_rest(self, slot, held, why: str) -> bool:
        """Cancel a resting order and forget it — **only if the broker agrees it is gone.**

        Returns True when the order is confirmed off the book. On False the record is KEPT, so
        the next bar retries the cancel rather than placing a second order beside the first.

        ⚠ **`UNKNOWN` is treated exactly like a failed cancel**, which is the conservative half:
        the worst case is one stale order the sweep will cancel, against the alternative of two
        live orders where the strategy wanted one.
        """
        ok = self._exec(
            lambda t=held.ticket: self._mt5.cancel_pending(t),
            f"{why} {slot_label(slot)} limit T{held.ticket}",
        )
        if ok is True:
            self._rest[slot] = None
            return True
        self._log.error(
            f"Cancel of T{held.ticket} was not confirmed ({ok!r}). Keeping the record and "
            f"placing nothing on this side — a second order beside an uncancelled one is the "
            f"failure this check exists to prevent."
        )
        self._ledger.event(
            "cancel_unconfirmed", dir=slot[1], intent=slot[0], ticket=held.ticket, why=why
        )
        return False

    # ── sizing ───────────────────────────────────────────────────────────────
    #
    # 🔴 EVERY order goes through `_plan`, and `_plan` is the ONLY place a lot count is
    # produced. That single-seam rule is the fix for 2026-08-07: before it, the conversion from
    # the strategy's units to MT5's lots did not exist anywhere, and there was no one place a
    # reviewer could have looked to notice.

    def refresh_account_room(self) -> None:
        """Tell the emulator how many dollars of ACCOUNT budget are still free, before it sizes.

        Aaron, 2026-09-03: each bot gets a share of one account, and when one is occupying more
        than its share **the others shrink to what is left** rather than being refused outright;
        with nothing left they refuse and say why on Telegram.

        🔴 **THE SHRINK HAPPENS IN THE STRATEGY'S OWN SIZING, NEVER IN THE ORDER, AND THAT IS THE
        ONLY REASON IT IS ALLOWED AT ALL.** All this does is hand the emulator a number; the clamp
        is `Execution._fit_to_budget` at PLACEMENT, so the position the emulator books and the
        order this bridge sends are the same size. Shrinking the ORDER would leave the two holding
        different trades, grading different R, and `_agrees` would halt the bot on a divergence
        the safety feature created. **That is why the account cap REFUSED and never shrank until
        this existed, and `_account_cap_check` stays on as the backstop.**

        🔴 **PLACEMENT, NOT THE FILL — and the first attempt got that wrong in a way worth
        keeping on the record.** The clamp was originally `SoloAccount.room()` inside
        `request_fill`. Same seam, same arithmetic, one step too late: by the time an order
        fills, a full-size order has been resting at the broker for hours, so shrinking the
        emulator's copy there produces exactly the two-different-books divergence this paragraph
        forbids. MEASURED before it was backed out: a $0.50 budget granted 0.0005 lots against a
        0.01 broker minimum. **A safety clamp is defined by its MOMENT as much as its seam.**

        ⚠ **A residual case is left standing rather than papered over**: if the budget shrinks
        between placement and fill, `request_fill` still refuses the emulator's side while the
        broker's resting order may fill. That is the pre-existing behaviour, it is now rare
        rather than routine, and it is a divergence either way — the only real fix is that the
        budget is decided once, at placement, which is what this now does.

        🔴 **IT MUST RUN BEFORE THE STRATEGY STEPS, WHICH IS WHY THE RUNNER CALLS IT AND NOT
        `_plan`.** `request_fill` happens while the strategy is stepping a bar; by the time this
        bridge reconciles, the fill has already been sized. The lot ceiling can afford to lag a
        bar because a venue's volume band is a standing broker property — an account's remaining
        risk is not, and a bar-old figure is exactly the window another bot fills.

        ⚠ **EVERY unreadable input means NO ROOM, never unlimited.** The terminal that cannot be
        asked, a balance that will not read, a position carrying no stop — all of them refuse.
        A budget that opens itself when the account is least healthy is not a budget, and this is
        the same call `_account_cap_check` already makes one layer down.

        ⚠ **This bot's own known tickets are EXCLUDED from the broker read on purpose** — they are
        counted by the emulator's own `reserved()`, which `SoloAccount.room()` subtracts. Counting
        them in both places would halve this bot's share every time it held anything.
        """
        account = getattr(self._ex, "_account", None)
        if account is None or not hasattr(account, "external_room"):
            return  # a strategy whose sizing does not go through the account seam
        if self._risk_cap_pct is None:
            account.external_room = None  # uncapped, and that is a supported state
            return

        room, why = self._account_room()
        account.external_room = room
        self._announce_room(room, why)

    def _others_risk(self, spec):
        """What everybody ELSE has on, as `(risk, code, why)`.

        `risk` is `None` when it cannot be measured, and `code` then names WHICH failure — the
        two have different causes and call for different work.

        🔴 **ONE definition, used by the budget refresh AND by `_account_cap_check`'s backstop.**
        It was briefly written twice, and the duplication was caught by two mutation anchors
        matching in two places — which is the cheap version of the lesson: the exclusion rule
        below carries a premise that has already been wrong once (2026-08-25, five copies of one
        order), and a premise living in two copies is one that gets corrected in one of them.

        ⚠ **This bot's own KNOWN tickets are excluded, and "known" is load-bearing.** Anything
        else under our own magic is COUNTED, because by definition we do not know what it is.
        """
        from account_risk import RiskUnmeasurable, measure_exposure

        items = self._mt5.account_exposure()
        if items is None:
            return (
                None,
                "account_risk_unreadable",
                (
                    "the account's open positions and orders could not be read, so the account-level "
                    "risk cap cannot be checked. Refusing rather than assuming the account is empty."
                ),
            )
        mine = {r.ticket for r in self._rest.values() if r is not None}
        if self._pos_ticket is not None:
            mine.add(self._pos_ticket)
        try:
            return (
                measure_exposure(
                    [it for it in items if it.magic != self._mt5.magic or it.ticket not in mine],
                    spec,
                ),
                "",
                "",
            )
        except RiskUnmeasurable as e:
            # A position with no stop. Its risk is UNBOUNDED, not absent — scoring it zero would
            # hide the one thing this cap exists to bound.
            #
            # ⚠ Its OWN code, not the unreadable one. "The terminal would not answer" and "the
            # account is carrying something whose risk cannot be computed" call for completely
            # different work, and this repo already records that two failures must never share
            # one message. Collapsing them is exactly what this refactor did for an hour, and a
            # pre-existing test caught it.
            return None, "account_risk_unmeasurable", str(e)

    def _account_room(self):
        """The dollars still free under the account cap, and the reason when there are none.

        ⚠ **There is exactly ONE floor at zero, deliberately.** A `max(0.0, ...)` here as well
        made the negative case untestable: no single mutation could produce a negative room, so
        the test asserting one cannot happen passed for free. Two guards for one rule is how a
        test stops being able to fail.
        """
        balance = self._account_balance()
        if balance is None or balance <= 0:
            return 0.0, "the account balance could not be read"
        spec = self._mt5.symbol_spec()
        if spec is None:
            return 0.0, "the symbol specification could not be read"
        others, _code, why = self._others_risk(spec)
        if others is None:
            return 0.0, why

        cap = balance * self._risk_cap_pct / 100.0
        room = cap - others.total_ccy
        if room <= 0.0:
            return 0.0, (
                f"the account already has ${others.total_ccy:,.2f} at risk against a "
                f"${cap:,.2f} cap ({self._risk_cap_pct}% of ${balance:,.2f})"
            )
        return room, ""

    def _announce_room(self, room: float, why: str) -> None:
        """Say it ONCE when the budget runs out, and say so again when it comes back.

        ⚠ **The recovery message is what makes the silence safe.** Without it, quiet would mean
        either *there is room again* or *still full, not worth repeating*, and the reader would
        have to go and look — which is the work the alert exists to save. This repo already
        records that rule from the ledger sync's own alarm.
        """
        blocked = room <= 0.0
        if blocked == self._room_blocked:
            return
        self._room_blocked = blocked
        if blocked:
            self._ledger.event("account_room_exhausted", reason=why)
            self._notify(
                alert(
                    "⚠️",
                    "NO ACCOUNT RISK LEFT",
                    self._mt5.bot_label,
                    f"This bot cannot open a trade: {why}.",
                    "Setups will be refused until room comes back — which happens as another "
                    "bot's stop moves up or its trade closes. Nothing is wrong with this bot.",
                ),
                notify.HEALTH,
            )
        else:
            self._ledger.event("account_room_restored", room_ccy=round(room, 2))
            self._notify(
                alert(
                    "✅",
                    "ACCOUNT RISK AVAILABLE",
                    self._mt5.bot_label,
                    f"${room:,.2f} of account risk budget is free again.",
                    "This bot can take setups again. Nothing to do.",
                ),
                notify.HEALTH,
            )

    def _reconcile_lot_ceiling(self, spec) -> None:
        """Hold the emulator's lot ceiling at `min(what we configured, what the venue accepts)`.

        🔴 **The clamp itself lives in the STRATEGY's sizing, never here, and that is the whole
        reason a clamp is allowable at all.** `backtest/portfolio/account.py` caps the qty the
        emulator books, so the position it holds and the order this bridge sends are the same
        size. Clamping the ORDER instead is what `order_sizing.plan_order` still refuses to do:
        it would leave the emulator holding 742 lots against a broker holding 100, the two would
        grade different R, and `_agrees` would halt the bot on a divergence the safety feature
        had created. **Clamping at the DECISION is safe; clamping at the ORDER is not.**

        So all this does is tell the emulator what the venue will take. Without it a configured
        ceiling ABOVE the broker's own maximum is not a ceiling — the strategy sizes to 100, the
        broker refuses at 50, and `plan_order` is left to refuse an order nobody can place.

        ⚠ **Both numbers are LOTS.** `spec.volume_max` is the broker's own volume band and
        `max_lots` is the policy figure; no contract-size conversion happens on this path, and
        introducing one here would be the 2026-08-07 units bug arriving by a new route.

        ⚠ **It only ever LOWERS, and it re-reads the CONFIGURED value each time rather than the
        current one.** Ratcheting off the live value would let one bad read pin the ceiling low
        for the rest of the session — the startup-fact-that-drifts problem (rule 16) inverted.

        ⚠ **A missing or non-positive `volume_max` is CANNOT ASK, not NO LIMIT and not ZERO.**
        Rule 1: a terminal that has not said what the band is leaves the configured ceiling
        exactly where it was. Treating it as 0 would refuse every order; treating it as infinite
        would hand the broker a size it rejects.
        """
        account = getattr(self._ex, "_account", None)
        if account is None or getattr(account, "max_lots", None) is None:
            return  # no ceiling configured (or no account seam) — nothing to reconcile
        if not hasattr(self, "_configured_max_lots"):
            self._configured_max_lots = account.max_lots
        broker_max = getattr(spec, "volume_max", None)
        if broker_max is None or float(broker_max) <= 0:
            account.max_lots = self._configured_max_lots
            return
        account.max_lots = min(self._configured_max_lots, float(broker_max))

    def _plan(self, direction: int, pend):
        """How many lots, or why not. See `algos/shared/order_sizing.py` for the reasoning."""
        spec = self._mt5.symbol_spec()
        if spec is None:
            from order_sizing import SizingRefusal

            return SizingRefusal(
                "symbol_unreadable",
                f"the terminal returned no symbol info for {self._mt5.symbol}, so nothing is "
                f"known about lot size, tick value or the volume band.",
            )

        self._reconcile_lot_ceiling(spec)

        side = "bullish" if direction > 0 else "bearish"
        cfg = getattr(self._ex, "cfg", None)
        plan = plan_order(
            qty_units=pend.qty,
            entry=pend.edge,
            stop=pend.sl,
            spec=spec,
            # Read LIVE off the strategy, never cached at construction — the runner mutates this
            # same config object when a runtime risk change is applied, and a cached copy would
            # size against the risk the bot started with.
            point_value=float(getattr(cfg, "point_value", 1.0) or 1.0),
            # The BROKER's balance, not the emulator's. This is the second half of the
            # 2026-08-07 fix: the emulator compounds its warm-up replay, so its equity had drifted
            # to ~$4,423 against a real $2,000 and it sized every order off the fiction.
            account_equity=self._account_balance(),
            risk_pct=getattr(cfg, "exec_risk_pct", None),
            free_margin=self._mt5.free_margin(),
            margin_for=lambda lots: self._mt5.margin_for(side, lots, pend.edge),
            margin_safety_pct=self._margin_safety_pct,
        )
        # The ACCOUNT-level cap runs LAST, on a plan that already passed every per-order check.
        # Order matters: a refusal should name the first thing wrong with the order itself
        # (a collapsed stop, an unaffordable margin, a size below the broker minimum) before it
        # starts talking about what OTHER bots are holding.
        return self._account_cap_check(plan, spec)

    def _account_cap_check(self, plan, spec):
        """Does this order fit inside the whole ACCOUNT's risk budget?

        This is the one check that reads past this bot's own magic number, and it is the reason
        `mt5_ops.account_exposure()` exists. Every other read in the live path is magic-filtered —
        correct for isolation, and precisely what makes a bot blind to the account it shares.

        ⚠ **This bot's own KNOWN exposure is excluded, and that is not a shortcut.** The strategy
        has ONE position slot, so an order of ours that this bot has a RECORD of is the thing this
        order REPLACES (`_sync_slot` cancels and re-places on a size change), never something it
        adds to. Counting it would make the bot refuse its own re-sizes as soon as it was near the
        cap, which reads exactly like a broken strategy.

        🔴 **"Known" was the word missing until 2026-08-25, and its absence cost 5x the intended
        risk.** The exclusion was written as *our magic*, and it carried an unstated premise: that
        anything under our magic is something we placed and are about to replace. When four orders
        reached the broker that this bot had no record of, the premise was false — and the one
        check on the account that could have counted five copies of a 10% order was the one check
        told not to look. It reported an empty account while half the balance was committed.

        ✅ **So the exclusion is now by TICKET, not by magic.** Our open position and our recorded
        resting orders are excluded; anything else under our magic is COUNTED, because by
        definition we do not know what it is. In normal running the two sets are identical and
        this changes nothing — `_observe_orphans` cancels unowned orders before `_sync_slot` is
        ever reached, so there is nothing left for it to find. That is the point: it is the
        backstop for the sweep having failed, and it costs nothing while the sweep works.

        ⚠ **A premise like that must be written next to the exclusion it justifies.** This one was
        documented, reasoned, and correct on the day it was written; nothing announced the day it
        stopped being true.

        ⚠ **It refuses; it never shrinks.** `algos/shared/account_risk.py` records why at length:
        a resized order is not the trade the strategy's emulator is holding, the two grade
        different R, and `_agrees` eventually halts the bot on a divergence the safety feature
        created. The backtest allocator SHRINKS instead, which is coherent there because the
        account hands the granted size back; nothing hands a size back across a process boundary.
        """
        from account_risk import check_account_cap

        if self._risk_cap_pct is None or not plan.ok:
            return plan

        from order_sizing import SizingRefusal

        # ⚠ ONE definition of what everybody else is holding, shared with the budget refresh —
        # see `_others_risk`. It was written twice for about an hour and the premise inside it
        # has already been wrong once, so a second copy is the thing to avoid rather than the
        # convenience to keep.
        open_risk, code, why = self._others_risk(spec)
        if open_risk is None:
            # The terminal could not be asked, or something on the book carries no stop — and the
            # CODE says which, because they call for different work. Same call as an uncomputable
            # margin either way: "cannot ask" is never "affordable", and a cap that opens itself
            # when the terminal wobbles is absent exactly when the account is least healthy.
            return SizingRefusal(code, why)

        # `risk_ccy`, not `intended_risk_ccy` — the cap bounds what actually goes ON THE BOOK,
        # and rounding to the broker's volume step is always DOWN, so the intended figure would
        # refuse orders that genuinely fit. The two differ by less than one volume step, but a
        # refusal a reader cannot reproduce from the order that was placed is a refusal nobody
        # can act on.
        verdict = check_account_cap(
            new_order_risk_ccy=plan.risk_ccy,
            open_risk=open_risk,
            balance=self._account_balance(),
            cap_pct=self._risk_cap_pct,
        )
        if verdict.allowed:
            return plan
        return SizingRefusal(verdict.code, verdict.detail)

    def _realised_risk_pct(self) -> Optional[float]:
        """What this position ACTUALLY risks, as a % of the basis it was sized against.

        🔴 **MEASURED off the position the broker opened, never restated from a setting.** The
        distance from the fill to the stop that is really attached, times the size that was really
        filled — so it catches a sizing bug, a broker-adjusted stop and a partial fill, none of
        which a settings figure can see. That is the whole reason it exists beside `risk_pct`
        rather than replacing it: one says what was asked for, the other what was got. Rule 3.

        🔴 **AND IT IS THE FIELD THAT MAKES A RE-ENTRY AUDITABLE.** A re-entry sizes at a fraction
        of the primary's percentage (`exec_sec_risk_pct`), so the setting alone says 10 for a trade
        that risks 5. Deriving the true figure here — rather than copying the strategy's
        multiplication into this file — keeps the sizing rule in exactly one place.

        ⚠ **`None` means it could not be worked out**, and the two causes are deliberately not
        separated here because neither is usable: an unreadable balance and a position with no
        measurable risk both leave a percentage that would have to be invented. Rule 1 — the
        caller must not print a number, and the ledger records the `None`.
        """
        basis = self._account_balance()
        if not basis or not self._pos_risk_usd:
            return None
        return self._pos_risk_usd / basis * 100.0

    def _account_balance(self):
        """The balance the account CAP measures against, or None if it cannot be read.

        `None` is passed straight through to `plan_order`, which then simply skips the
        authorised-risk check rather than comparing against a fabricated zero — the same
        three-state rule as `mt5_link`. A zero here would refuse every order forever.

        ⚠ **It applies the same stated adjustment the strategy sizes against** (2026-08-26). The
        cap and the sizing must read ONE number: a cap measured against the broker's balance
        while the strategy sizes against an adjusted one is a cap that is quietly looser than it
        says, and the difference only appears in a month nobody is checking.
        """
        try:
            import MetaTrader5 as mt5
            from sizing_basis import sizing_basis

            info = mt5.account_info()
            raw = float(info.balance) if info else None
            return sizing_basis(raw, self._sizing_basis_adjustment)
        except Exception:
            return None

    def _record_refusal(self, slot, plan, pend) -> None:
        """A refused order is loud once, then quiet — but never forgotten."""
        direction = slot[1]
        detail = f"[{plan.code}] {plan.detail}"
        self._refused[slot] = detail
        self._ledger.event(
            "order_refused",
            dir=direction,
            intent=slot[0],
            code=plan.code,
            detail=plan.detail,
            wanted_units=pend.qty,
            price=pend.edge,
            stop=pend.sl,
            sos_bar=getattr(pend, "sos_bar", None),
        )
        self._log.error(f"Order REFUSED ({slot_label(slot)}): {detail}")
        if self._refusal_alerted.get(slot) == plan.code:
            return
        self._refusal_alerted[slot] = plan.code
        self._notify(
            alert(
                "⚠️",
                "ORDER REFUSED",
                self._mt5.bot_label,
                f"A {slot_label(slot)} setup was ready and no order was placed.\n{plan.detail}",
                "No position was opened. The strategy will keep re-offering it while the setup "
                "lives, and this will not alert again for the same reason.",
            ),
            notify.HEALTH,
        )

    def _place(self, slot, lots: float, pend, sig, plan=None) -> None:
        direction = slot[1]
        side = "bullish" if direction > 0 else "bearish"
        ticket = self._exec(
            lambda: self._mt5.place_pending_limit(side, lots, pend.edge, pend.sl),
            f"place {slot_label(slot)} limit {lots}L @ {pend.edge} SL {pend.sl}",
        )
        if isinstance(ticket, tuple):
            ticket = ticket[0]
        if ticket is UNKNOWN:
            # 🔴 The send did not confirm AND the order book could not be read, so an order may
            # or may not be resting under our magic right now. The one thing that must not
            # happen is another send: that is precisely how four timed-out requests became four
            # live orders. Block this side until `_observe_orphans` can read the book and settle
            # it — cancelling anything it finds, or confirming nothing landed.
            self._unresolved[slot] = True
            self._log.error(
                f"Placement outcome UNKNOWN for the {slot_label(slot)} slot. Placing nothing "
                f"more in it until the order book can be read."
            )
            self._ledger.event(
                "order_unknown",
                dir=direction,
                intent=slot[0],
                lots=lots,
                price=pend.edge,
                stop=pend.sl,
            )
            return
        if ticket:
            self._rest[slot] = _Rest(ticket, pend.edge, lots, pend.sl)
            self._ledger.event(
                "order_placed",
                dir=direction,
                intent=slot[0],
                ticket=ticket,
                lots=lots,
                price=pend.edge,
                stop=pend.sl,
                sos_bar=getattr(pend, "sos_bar", None),
                # The sizing WORKING is now part of the record, not just the
                # sizing failing. `risk_ccy` is what this order really puts at
                # risk in account currency — the number that was wrong by 221x
                # and that no artefact anywhere would have revealed.
                risk_ccy=getattr(plan, "risk_ccy", None),
                intended_risk_ccy=getattr(plan, "intended_risk_ccy", None),
                margin_ccy=getattr(plan, "margin_ccy", None),
                units=pend.qty,
            )
        elif not self.dry_run:
            # place_pending_limit already logged WHY; record it so a refused setup is countable
            # next to the strategy's own blocked setups.
            self._ledger.event(
                "order_refused", dir=direction, lots=lots, price=pend.edge, stop=pend.sl
            )

    def _alert_once(self, code: str, body: str) -> None:
        """Say something ONCE per cause, and log it every time.

        ⚠ The log is unconditional and only the ALERT is latched. A problem that persists for
        forty bars should be forty lines in the log — that is the record — and one message on
        the phone, which is the part that stops being read when it repeats.
        """
        self._log.error(body)
        if self._partial_alerted == code:
            return
        self._partial_alerted = code
        self._notify(
            alert(
                "⚠️",
                "PARTIAL NOT BANKED",
                self._mt5.bot_label,
                body,
                "The position keeps its broker stop and the strategy keeps managing it. This "
                "will not alert again for the same reason.",
            ),
            notify.HEALTH,
        )

    def _intended_open_lots(self):
        """How much the STRATEGY believes is still open, in LOTS. `None` = could not ask.

        ⚠ **`None` is not zero.** Zero would mean *bank the whole position*, which is a full
        exit — the single most destructive misreading available here. A strategy this bridge
        cannot interrogate must stop it acting, not licence it to close everything (rule 1).

        ⚠ **It reads the emulator's own fields**, the same coupling this bridge already has with
        `_pend_long`, `_pend_short` and `_pos_dir`. `_qty` is everything the position has been
        given (adds included) and `_filled_qty` is everything that has left it, so the difference
        is the intended size whether or not the strategy has scaled. A public seam on `Execution`
        would be the better shape and is deliberately NOT taken here: `execution.py` is a
        strategy file, and rule 22 says a changed strategy does not ship until its parity gate
        has actually RUN on a real export. That is a decision to make with an export in hand, not
        while wiring a bridge.
        """
        qty = getattr(self._ex, "_qty", None)
        filled = getattr(self._ex, "_filled_qty", None)
        if qty is None or filled is None:
            return None
        cs = self._contract_size()
        if not cs:
            return None
        return max(0.0, (float(qty) - float(filled))) / cs

    def _sync_partials(self, positions) -> None:
        """Bank the broker down to the size the strategy believes is still open.

        🔴 **A RECONCILIATION, NOT AN EVENT — and that is the whole design.** It does not watch
        for a rung being touched; it asks *how much should be open* and closes the difference.
        So a partial missed by a restart, a dropped connection or a skipped bar is simply taken
        on the next sync, and a partial that already happened is a no-op. An event-driven version
        has to remember what it has done, and this bridge's whole history says that is the
        state which goes wrong.

        ⚠ **IT FILLS AT MARKET, ON A CLOSED PRIMARY BAR — THE LAB FILLS AT THE RUNG PRICE.** That
        is a real and permanent divergence, not a bug to be tuned away: `sync` runs once per
        closed 15m bar, so a rung touched mid-bar is banked at whatever the market is when the
        bar shuts. It makes the live result WORSE than the backtest in a rising market and better
        in a falling one, and it is the first thing to check when a live partial's price does not
        match the lab's. Recorded on every `partial_banked` event so a shadow diff can attribute
        it rather than rediscover it.

        ⚠ **It only ever CLOSES.** If the broker holds LESS than the strategy expects, that is a
        disagreement about the book and belongs to `_agrees`/`_observe_vanished`, which halt.
        Quietly re-opening size here would be this bridge inventing a trade.
        """
        if self._pos_ticket is None:
            return
        # 🔴 **A CONFIGURATION THAT BANKS NOTHING NEVER ENTERS THIS PATH, AND THAT IS LOAD-BEARING
        # RATHER THAN AN OPTIMISATION.** The shipped bot runs `exec_tp1_pct = exec_tp2_pct = 0` —
        # bank nothing, ride the runner — so there is no size to take off, and asking "how much
        # should be open" of a strategy that never banks would answer "all of it" on every bar.
        # Without this gate the first version alerted *cannot read the intended size* on 18
        # existing tests, whose doubles quite reasonably have no `_qty`. **An always-on
        # reconciliation against a book nobody is scaling is noise, and noise is how a real
        # partial failure gets scrolled past.** With it, a bot at 0/0 behaves byte for byte as it
        # did before this feature existed.
        if not price_triggered_banks(getattr(self._ex, "_cfg", None)):
            return
        want = self._intended_open_lots()
        if want is None:
            self._alert_once(
                "partials_unreadable",
                "Cannot read how much of the position should still be open, so nothing was "
                "banked. The broker keeps whatever it holds and its stop.",
            )
            return
        held = next((float(p.volume) for p in positions if p.ticket == self._pos_ticket), None)
        if held is None:
            return  # not our position to reconcile this bar; `_observe_close` owns that
        excess = held - want
        if excess <= 1e-9:
            return
        direction = "bullish" if self._ex._pos_dir > 0 else "bearish"
        res = self._exec(
            lambda: self._mt5.partial_close(self._pos_ticket, excess, direction),
            f"bank {excess:.2f}L of T{self._pos_ticket} ({held:.2f}L held, {want:.2f}L wanted)",
        )
        if res is UNKNOWN:
            # Rule 1: a retry could bank twice. Stop until a later bar reads a consistent size.
            self._alert_once(
                "partial_unknown",
                f"A partial close of {excess:.2f}L on T{self._pos_ticket} returned an unknown "
                f"result. Nothing further will be banked until the position reads consistently.",
            )
            self._ledger.event(
                "partial_unknown",
                ticket=self._pos_ticket,
                lots=round(excess, 2),
                held=round(held, 2),
                wanted=round(want, 2),
            )
            return
        if not res:
            # `partial_close` REFUSES a size the broker cannot express exactly rather than
            # rounding it (rule 17), so this is the expected answer for a slice below the volume
            # minimum. The position stays over-sized and the strategy keeps managing it — which
            # is the safe half — but the two books now differ, so it must be SAID.
            self._alert_once(
                "partial_refused",
                f"Could not bank {excess:.2f}L of T{self._pos_ticket}: the broker cannot express "
                f"that size. The position is still {held:.2f}L where the strategy expects "
                f"{want:.2f}L, so the live result will differ from the backtest on this trade.",
            )
            self._ledger.event(
                "partial_refused",
                ticket=self._pos_ticket,
                lots=round(excess, 2),
                held=round(held, 2),
                wanted=round(want, 2),
            )
            return
        self._pos_lots = want
        self._partial_alerted = ""
        self._ledger.event(
            "partial_banked",
            ticket=self._pos_ticket,
            lots=round(excess, 2),
            held_before=round(held, 2),
            held_after=round(want, 2),
            # ⚠ NAMED, not implied: this fill is a MARKET close on a closed bar, never the
            # rung's own price. A shadow diff comparing it to the lab must know that.
            fill="market_on_bar_close",
        )

    def _sync_stop(self, dec) -> None:
        """Keep the broker's stop on the open position equal to the strategy's current stop.

        The stop lives AT THE BROKER by design (D4): a crash, a reboot or a dropped network must
        not leave a position unprotected. The bot's job is only to ratchet it.
        """
        want = getattr(dec, "stop", None)
        if want is None or self._pos_ticket is None:
            return
        if not self._moved(self._pos_stop, want):
            return
        ok = self._exec(
            lambda: self._mt5.move_sl(self._pos_ticket, want),
            f"move stop T{self._pos_ticket} {self._pos_stop} → {want}",
        )
        if ok:
            self._ledger.event("stop_moved", ticket=self._pos_ticket, was=self._pos_stop, now=want)
            self._pos_stop = want
            # Re-record: the stop is the field that moves, and a record holding the previous
            # stop would be REFUSED at the next start because the broker's real one disagrees.
            self._save_position()

    def _cancel_all_rest(self, why: str) -> None:
        for slot, held in list(self._rest.items()):
            if held is not None:
                self._exec(
                    lambda t=held.ticket: self._mt5.cancel_pending(t),
                    f"cancel {slot_label(slot)} limit T{held.ticket} ({why})",
                )
                self._rest[slot] = None

    # ── plumbing ─────────────────────────────────────────────────────────────
    def _exec(self, action, description: str):
        """Every mutating broker call goes through here, so `--dry-run` is a property of the
        bridge rather than something each call site has to remember."""
        if self.dry_run:
            self._log.info(f"[DRY RUN] would {description}")
            self._ledger.event("dry_run_action", action=description)
            return True
        self._log.info(description)
        return action()

    def halt(self, reason: str) -> None:
        """Halt this bridge on an OUTSIDE authority's instruction.

        Two callers, both in `runner.py`: the fleet switch, and the account-identity check that
        fires when the terminal turns out to be logged into an account this bot was not pointed
        at (added 2026-08-12, after exactly that happened under a running bot).

        A public seam rather than letting a caller reach into `_halt`, because the two have
        genuinely different causes and only one of them is a defect: `_halt` means *this bot's
        emulator and the broker disagree*, which is a fault to investigate, while this means
        *somebody, or something, told the whole fleet to stop*, which is a decision to honour.
        The EFFECT is identical on purpose — no further orders, open positions keep their
        broker stops — so there is exactly one state a reader has to reason about.
        """
        self._halt(reason)

    def _halt(self, reason: str) -> None:
        if self.state is BridgeState.HALTED:
            return
        self.state = BridgeState.HALTED
        self.halt_reason = reason
        self._log.error(f"HALTED: {reason}")
        self._ledger.event("halted", reason=reason)
        # HEALTH, not TRADE, and the call is worth defending: a halt is the bot refusing to place
        # orders, which is a fact about the machinery. It is also the single most consequential
        # message here — which is why it must not sit in a room that is only checked when a fill
        # arrives. `log_review.py` raises it AGAIN as a standing chip on the Bots page precisely
        # because one Telegram line, in any room, is not enough for this one.
        self._notify(
            alert(
                "⛔",
                "HALTED",
                self._mt5.bot_label,
                reason,
                "Anything open keeps its broker stop. Check the account, then restart it.",
            ),
            notify.HEALTH,
        )

    def _moved(self, a: float, b: float) -> bool:
        """Price comparison at the symbol's own precision — a float that differs in the 9th
        decimal is not a moved order, and treating it as one would rewrite every order every
        bar for nothing."""
        try:
            import MetaTrader5 as mt5

            si = mt5.symbol_info(self._mt5.symbol)
            tick = si.point if si and si.point else 0.01
        except Exception:
            tick = 0.01
        return abs(float(a or 0) - float(b or 0)) >= tick

    def _contract_size(self) -> float:
        try:
            import MetaTrader5 as mt5

            si = mt5.symbol_info(self._mt5.symbol)
            return float(si.trade_contract_size) if si else 1.0
        except Exception:
            return 1.0

    def _symbol_attr(self, name: str, fallback):
        """One symbol property off the terminal, with a fallback that only applies when MT5 is
        not there to ask (tests, dry runs on a machine without it). Never hardcoded per symbol —
        `digits` and `point` differ by broker, and a wrong pip size makes every stop distance in
        every alert wrong in a way nobody would question."""
        try:
            import MetaTrader5 as mt5

            si = mt5.symbol_info(self._mt5.symbol)
            return getattr(si, name) if si else fallback
        except Exception:
            return fallback

    def _digits(self) -> int:
        return int(self._symbol_attr("digits", 2))

    def _point(self) -> float:
        return float(self._symbol_attr("point", 0.01))

    @staticmethod
    def _bar_time(sig):
        """The BAR's timestamp, not the wall clock — an alert should be stamped with when the
        trade happened. Falls back to None, which `alerts` reads as "now"."""
        from datetime import datetime, timezone

        ms = getattr(sig, "time_ms", None)
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc) if ms else None

    def _infer_exit_reason(self, price: float) -> str:
        if not self._pos_stop or not price:
            return "closed"
        hit_stop = (self._pos_dir > 0 and price <= self._pos_stop) or (
            self._pos_dir < 0 and price >= self._pos_stop
        )
        return "stop" if hit_stop else "closed"

    @staticmethod
    def _side(direction: int) -> str:
        return "LONG" if direction > 0 else "SHORT"

    @staticmethod
    def _stamp(sig) -> str:
        from datetime import datetime, timezone

        ms = getattr(sig, "time_ms", None)
        if not ms:
            return ""
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    @staticmethod
    def _confluences(dec, sig) -> dict:
        """What was true when the trade opened. Read defensively — this is the record that makes
        "why did this not work" answerable later, and a strategy without one of these fields
        should log the rest rather than nothing."""
        return {
            "l_stage": getattr(dec, "l_stage", None),
            "s_stage": getattr(dec, "s_stage", None),
            "long_edge": getattr(dec, "long_edge", None),
            "short_edge": getattr(dec, "short_edge", None),
            "long_veto": getattr(dec, "long_veto", None),
            "short_veto": getattr(dec, "short_veto", None),
            "tp1": getattr(dec, "tp1", None),
            "tp2": getattr(dec, "tp2", None),
            "bull_div_active": getattr(sig, "bull_div_active", None),
            "bear_div_active": getattr(sig, "bear_div_active", None),
            "recent_ssl": getattr(sig, "recent_ssl", None),
            "recent_bsl": getattr(sig, "recent_bsl", None),
            "ny_hour": getattr(sig, "ny_hour", None),
        }
