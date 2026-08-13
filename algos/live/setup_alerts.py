"""setup_alerts.py — turn a strategy's live setups into a Telegram thread, one per setup.

Reads `backtest.setups.SetupSnapshot` and knows NOTHING about any particular strategy. A new bot
gets pre-trade alerts by implementing `live_setups()`; nothing here changes.

**What it sends, per setup, in order:**

    👀 SETUP FORMING     the root — confluences so far, the tradeable zone, the projected stop
    🎯 ENTRY ZONE LIVE   a reply — every confluence met, an order resting at a price
    🚫 BLOCKED           a reply — one of your own rules refused it
    ✅ ENTERED / 👋 NO TRADE   a reply — what became of it

**Three rules, each of which is a measured failure rather than a preference:**

⚠ **EDGE-TRIGGERED, and per SETUP rather than per transition.** A resting limit is rebuilt every
bar and cleared when not armed, so one setup flickers in and out of `RESTING` repeatedly —
measured at 665 transitions across 332 setups over 6.5 years. A level-triggered alert fires every
15 minutes for as long as the setup lives; an edge-triggered one on the raw transition still
announces the same setup two or three times. `_sent` records WHICH messages a setup has already
had, so each is sent once and only once.

⚠ **NEVER RAISES.** `notify.py`'s standing rule, and it binds harder here than anywhere else in
this package: this runs inside `_on_bar`, between the strategy stepping and the broker being
reconciled. A notifier that can take down a trading loop is worse than a missed message. Every
path returns; nothing propagates.

⚠ **A strategy that does not implement the contract is REPORTED, once, by name — never silently
skipped.** Three separate jobs in this repo ran for weeks against an empty registry and reported
success (root `CLAUDE.md` rule 8). "No setups" and "cannot ask for setups" must not be the same
value, which is rule 1 arriving one layer up.

See `docs/LIVE_SETUP_ALERTS.md` for the message wording, the measured volume and the build order.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence, Set

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.setups import RESTING, SetupSnapshot, implements_contract  # noqa: E402

import alerts  # noqa: E402  (same package; `runner` puts this dir on the path)

#: The four message categories, switchable per bot. Names are a WIRE FORMAT — they appear in
#: instance configs, so renaming one silently turns that category off on every bot already
#: carrying the old name. Add, never rename.
WATCHING_MSG = "watching"
ENTRY_ZONE_MSG = "entry_zone"
BLOCKED_MSG = "blocked"
RESOLVED_MSG = "resolved"

CATEGORIES = (WATCHING_MSG, ENTRY_ZONE_MSG, BLOCKED_MSG, RESOLVED_MSG)

#: What a bot sends when its config says nothing. All four: Aaron asked for the full story of a
#: setup (2026-08-13), and a category defaulting OFF is a message nobody knows they are missing.
DEFAULT_CATEGORIES = CATEGORIES


class SetupAlerts:
    """Per-bot state for the signals channel: which setups are open, and what each has been told.

    `send(text, reply_to)` is injected rather than imported so this class has no network at all —
    the runner passes its own `_notify`, which already carries per-bot chat and token routing.
    """

    def __init__(self, send: Callable[..., Optional[int]], log=None,
                 categories: Sequence[str] = DEFAULT_CATEGORIES,
                 digits: int = 2) -> None:
        self._send = send
        self._log = log
        self._digits = digits
        self._categories = tuple(c for c in categories if c in CATEGORIES)
        #: setup key -> the Telegram message id of its root, so every outcome replies to it.
        self._threads: Dict[str, Optional[int]] = {}
        #: setup key -> which categories it has already been sent. This is what makes the alert
        #: per-SETUP rather than per-transition; see the module docstring.
        self._sent: Dict[str, Set[str]] = {}
        self._unsupported_reported = False

    # ── the one entry point ──────────────────────────────────────────────────────────────────
    def on_bar(self, strategy) -> None:
        """Drain this bar's setups and send whatever is new. Never raises."""
        try:
            snaps = self._drain(strategy)
            if snaps is None:
                return
            for snap in snaps:
                self._handle(snap)
        except Exception as e:                       # noqa: BLE001 — see the module docstring
            self._warn(f"setup alerts failed on this bar: {e}")

    def supported(self, strategy) -> bool:
        """Whether this strategy can produce setups at all — for the runner's startup banner."""
        return implements_contract(getattr(strategy, "execution", strategy))

    # ── internals ────────────────────────────────────────────────────────────────────────────
    def _drain(self, strategy) -> Optional[Sequence[SetupSnapshot]]:
        """This bar's snapshots, or `None` when the strategy cannot answer.

        🔴 **`None` and `[]` are DIFFERENT and the distinction is the whole point.** `[]` means
        the strategy is watching nothing right now; `None` means it has no way to say. Collapsing
        them is the failure that left the live bot reading a dead terminal as a quiet market —
        root `CLAUDE.md` rule 1.
        """
        ex = getattr(strategy, "execution", strategy)
        if not implements_contract(ex):
            if not self._unsupported_reported:
                self._unsupported_reported = True
                self._warn(f"{type(ex).__name__} does not implement live_setups() — the signals "
                           f"channel is OFF for this bot. It is not quiet; it cannot report.")
            return None
        # `drain_setups` clears the resolved ones so they are not re-sent every bar. A strategy
        # offering only `live_setups` is read without draining and WARNED about, because the
        # terminal snapshots would repeat for the life of the process.
        drain = getattr(ex, "drain_setups", None)
        if callable(drain):
            return drain()
        self._warn(f"{type(ex).__name__} has live_setups() but no drain_setups() — resolved "
                   f"setups may repeat.")
        return ex.live_setups()

    def _handle(self, snap: SetupSnapshot) -> None:
        # 🔴 **A setup the bot has already decided it cannot take is never announced** (Aaron,
        # 2026-08-13: *"I should only be getting signals for the trades originating from my
        # default settings"*). Announcing a setup the bot has already refused is a label with no
        # code behind it, pointed at a human who might act on it.
        #
        # ⚠ **On `mpc_sos_fade` this suppresses ONE setup in 6.5 years, and the estimate that
        # justified building it was wrong by two orders of magnitude.** The guess was "220 of 609
        # are divergence-armed and this bot trades sweep-only". `arm_src` records which source
        # reached stage 1 FIRST; `sos_l_swp` records whether a sweep was live at the SOS, and
        # nearly every divergence-armed setup carries one too — so they are tradeable and most of
        # them trade. The strategy's own books settle it: **zero misses with code 1 ("arm source
        # off") over the same window.** The guard stays because it enforces the invariant
        # regardless of how often it fires, but do not quote it as a volume lever.
        #
        # ⚠ **It is checked FIRST, before any bookkeeping.** Marking it seen would be harmless
        # today and wrong the moment a strategy reports a setup that becomes tradeable later:
        # the root would already be recorded as sent and the setup would go silent for good.
        if not snap.tradeable:
            return
        sent = self._sent.setdefault(snap.key, set())

        # The root FIRST, always, whatever state the setup arrives in. A setup that reaches its
        # entry zone on the same bar it arms would otherwise have its reply sent with nothing to
        # reply to, and the thread would read backwards.
        if WATCHING_MSG not in sent:
            sent.add(WATCHING_MSG)
            if self._on(WATCHING_MSG):
                self._threads[snap.key] = self._post(alerts.format_watching(snap, self._digits))

        root = self._threads.get(snap.key)

        if snap.blocked_by and BLOCKED_MSG not in sent:
            sent.add(BLOCKED_MSG)
            if self._on(BLOCKED_MSG):
                self._post(alerts.format_blocked(snap, self._digits), reply_to=root)

        if snap.state == RESTING and ENTRY_ZONE_MSG not in sent:
            sent.add(ENTRY_ZONE_MSG)
            if self._on(ENTRY_ZONE_MSG):
                self._post(alerts.format_entry_zone(snap, self._digits), reply_to=root)

        if snap.is_terminal:
            if RESOLVED_MSG not in sent and self._on(RESOLVED_MSG):
                self._post(alerts.format_resolved(snap, self._digits), reply_to=root)
            # Drop the bookkeeping. A process meant to run for months cannot keep a dict entry
            # per setup it has ever seen — ~11 a month forever is a slow leak with no symptom.
            self._threads.pop(snap.key, None)
            self._sent.pop(snap.key, None)

    def _on(self, category: str) -> bool:
        return category in self._categories

    def _post(self, text: str, reply_to: Optional[int] = None) -> Optional[int]:
        from notify import SIGNAL
        return self._send(text, SIGNAL, reply_to=reply_to)

    def _warn(self, msg: str) -> None:
        if self._log is not None:
            self._log.warning(msg)
        else:                                        # pragma: no cover - a bot always has a log
            print(f"setup_alerts: {msg}")
