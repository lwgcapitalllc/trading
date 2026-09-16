"""setup_alerts.py — turn a strategy's live setups into a Telegram thread, one per setup.

Reads `backtest.setups.SetupSnapshot` and knows NOTHING about any particular strategy. A new bot
gets pre-trade alerts by implementing `live_setups()`; nothing here changes.

**What it sends, per setup, in order:**

    👀 SETUP FORMING     the root — confluences so far, the tradeable zone, the projected stop
    🎯 BUY/SELL LIMIT RESTING   a reply — a real order exists at a price and has NOT filled
    🚫 BLOCKED           a reply — one of your own rules refused it
    ✅ ENTERED / 👋 NO TRADE   a reply — what became of it

**Three rules, each of which is a measured failure rather than a preference:**

⚠ **EDGE-TRIGGERED, and per SETUP rather than per transition.** A resting limit is rebuilt every
bar and cleared when not armed, so one setup flickers in and out of `RESTING` repeatedly —
measured at 665 transitions across 332 setups over 6.5 years. A level-triggered alert fires every
15 minutes for as long as the setup lives; an edge-triggered one on the raw transition still
announces the same setup two or three times. `_sent` records WHICH messages a setup has already
had, so each is sent once and only once.

🔴 **AND IT SURVIVES A RESTART, since 2026-09-16.** Both halves of the bookkeeping — which
messages a setup has had, and the Telegram id its outcome must reply to — are written to the
bot's instance folder and read back on start. Without that they lived in memory only, so
stopping, starting, redeploying or re-warming a bot re-announced every open setup and orphaned
the thread the reader was looking at: measured at four identical `SETUP FORMING` roots for one
setup inside 24 hours on `sos_fade_1`, none of the first three closable. The second half of that
defect was in the STRATEGY — the setup's id was a bar POSITION, which a re-warm renumbers — and
is fixed in `sos_fade/execution.py::_setup_key`. **Either one alone still duplicates the alert.**
A setup that resolved while the bot was down is closed on the next start by `reconcile`.

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

import json
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set

import alerts  # noqa: E402  (same package; `runner` puts this dir on the path)

# ⚠ **This module inserts NOTHING onto `sys.path`, deliberately.** It is imported from
# `runner._start_setup_alerts`, which runs AFTER `_bind_code()` has put the frozen `deployed/`
# snapshot at position 0 — so `backtest.setups` below resolves against the code the bot was
# PROMOTED with, which is what the version pin promises. Re-inserting the repo root here would
# jump it back in front of the snapshot and silently undo that for every later import.
#
# The sibling rule, and the one that actually bit: `alerts.py` may not import this package at
# module level at all, because `bridge.py` pulls it in before the snapshot is bound. See the
# block at the top of that file — it took the live bot down on 2026-08-13.
from backtest.setups import RESTING, SetupSnapshot, implements_contract  # noqa: E402

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

    def __init__(
        self,
        send: Callable[..., Optional[int]],
        log=None,
        categories: Sequence[str] = DEFAULT_CATEGORIES,
        digits: int = 2,
        display: str = "",
        lots_for: Optional[Callable[[int], Optional[float]]] = None,
        order_for: Optional[Callable[[int], Optional["alerts.RestingOrder"]]] = None,
        state_path=None,
        channel: str = "",
    ) -> None:
        self._send = send
        self._log = log
        self._digits = digits
        #: The bot's display name for the message head. Comes from the RUNNER's config, because a
        #: strategy only knows its own class name — `SosFadeStrategy` where a reader wants
        #: `SOS Fade`. Empty falls back to the class name, so a caller that does not set it
        #: still renders something true.
        self._display = display
        #: side -> the lots ACTUALLY resting at the broker, or None when nothing is.
        #:
        #: 🔴 **Three states, and flattening any two of them breaks a different message.**
        #: `lots_for is None` means there is no broker to ask (a backtest, `alert_rate.py`) and
        #: the resting alert sends WITHOUT a size, exactly as it always did. A callable that
        #: returns a float means an order of that size is live. A callable that returns None
        #: means it was ASKED and nothing is resting — the order was refused or cancelled — and
        #: the alert is not sent at all, because its entire job is to say an order EXISTS.
        #: **"No order" and "no broker" must not render the same message**, which is rule 1
        #: arriving in the signals channel.
        self._lots_for = lots_for
        #: side -> the whole order the BROKER holds (price, stop, lots), or None when nothing is.
        #: Same three states as `lots_for`, and it supersedes it when given. It is what lets the
        #: thread follow an order that is re-placed at a new price or size.
        self._order_for = order_for
        #: setup key -> the order the thread last DESCRIBED, as a `RestingOrder` (or the
        #: strategy's prices with `lots=None` when there is no broker), or None once the thread
        #: — unused since cancellations went silent. Absent means no resting message has been sent yet.
        self._order: Dict[str, Optional[alerts.RestingOrder]] = {}
        self._categories = tuple(c for c in categories if c in CATEGORIES)
        #: setup key -> the Telegram message id of its root, so every outcome replies to it.
        self._threads: Dict[str, Optional[int]] = {}
        #: setup key -> which categories it has already been sent. This is what makes the alert
        #: per-SETUP rather than per-transition; see the module docstring.
        self._sent: Dict[str, Set[str]] = {}
        #: setup key -> the side and symbol it was announced with, kept ONLY so a thread whose
        #: outcome was lost across a restart can still be closed with a message that names what
        #: it was about. Nothing reads it while a setup is alive.
        self._about: Dict[str, dict] = {}
        self._unsupported_reported = False
        #: Where the three dicts above are written so they survive a restart, or `None` for a
        #: caller with nowhere to put them (a backtest, `alert_rate.py`) — which behaves exactly
        #: as this class did before persistence existed.
        self._state_path = Path(state_path) if state_path else None
        #: Which Telegram chat the stored threads belong to.
        #:
        #: 🔴 **A message id is meaningful only inside ONE chat.** Move a bot to another account
        #: and its signals go to that account's channel — which happened to `sos_fade_2` on
        #: 2026-09-15 — so every stored id would then point at a message in a chat this bot no
        #: longer writes to. Telegram answers a reply to a foreign id by dropping the reply link
        #: or refusing the send, and either way the reader would get a resolution with no setup
        #: attached and never see the setup re-announced. Threads are dropped when this changes.
        self._channel = channel
        self._load()

    # ── the one entry point ──────────────────────────────────────────────────────────────────
    def on_bar(self, strategy) -> None:
        """Drain this bar's setups and send whatever is new. Never raises."""
        try:
            snaps = self._drain(strategy)
            if snaps is None:
                return
            for snap in snaps:
                self._handle(snap)
        except Exception as e:  # noqa: BLE001 — see the module docstring
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
                self._warn(
                    f"{type(ex).__name__} does not implement live_setups() — the signals "
                    f"channel is OFF for this bot. It is not quiet; it cannot report."
                )
            return None
        # `drain_setups` clears the resolved ones so they are not re-sent every bar. A strategy
        # offering only `live_setups` is read without draining and WARNED about, because the
        # terminal snapshots would repeat for the life of the process.
        drain = getattr(ex, "drain_setups", None)
        if callable(drain):
            return drain()
        self._warn(
            f"{type(ex).__name__} has live_setups() but no drain_setups() — resolved "
            f"setups may repeat."
        )
        return ex.live_setups()

    def _handle(self, snap: SetupSnapshot) -> None:
        # 🔴 **A setup the bot has already decided it cannot take is never announced** (Aaron,
        # 2026-08-13: *"I should only be getting signals for the trades originating from my
        # default settings"*). Announcing a setup the bot has already refused is a label with no
        # code behind it, pointed at a human who might act on it.
        #
        # ⚠ **On `sos_fade` this suppresses ONE setup in 6.5 years, and the estimate that
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
        # Refreshed every bar rather than only on the root, so a state file written before this
        # setup's first announcement still names what the thread is about.
        self._about[snap.key] = {"side": snap.side, "symbol": snap.symbol}
        before = (len(sent), snap.key in self._threads)

        # The root FIRST, always, whatever state the setup arrives in. A setup that reaches its
        # entry zone on the same bar it arms would otherwise have its reply sent with nothing to
        # reply to, and the thread would read backwards.
        if WATCHING_MSG not in sent:
            sent.add(WATCHING_MSG)
            if self._on(WATCHING_MSG):
                self._threads[snap.key] = self._post(
                    alerts.format_watching(snap, self._digits, self._display)
                )

        root = self._threads.get(snap.key)

        if snap.blocked_by and BLOCKED_MSG not in sent:
            sent.add(BLOCKED_MSG)
            if self._on(BLOCKED_MSG):
                self._post(alerts.format_blocked(snap, self._digits), reply_to=root)

        # 🔴 **`announce_resting` is checked BEFORE `sent` is marked, and the order is the whole
        # point.** Marking it first would consume the setup's one resting-message slot on a bar
        # the message was suppressed, so the announcement would never arrive — the same
        # bookkeeping-before-the-guard mistake the `tradeable` check above is written to avoid,
        # and silent in exactly the same way.
        #
        # ⚠ **The STRATEGY decides when a resting order is worth announcing** (`backtest/setups.py`
        # → `announce_resting`). This layer must never learn what a fib is; it only respects the
        # answer. A strategy that does not implement it defaults True and behaves as before.
        if not snap.is_terminal:
            self._follow_order(snap, sent, root)

        if snap.is_terminal:
            if RESOLVED_MSG not in sent and self._on(RESOLVED_MSG):
                self._post(alerts.format_resolved(snap, self._digits), reply_to=root)
            # Drop the bookkeeping. A process meant to run for months cannot keep a dict entry
            # per setup it has ever seen — ~11 a month forever is a slow leak with no symptom.
            self._forget(snap.key)
            self._save()
            return
        # Saved only when something CHANGED, so a setup that lives for days does not rewrite the
        # file every 15 minutes for the whole of it.
        if before != (len(sent), snap.key in self._threads):
            self._save()

    def _order_now(self, snap: SetupSnapshot):
        """What is resting for this setup right now: `(asked, order)`.

        `asked` False means there is no broker (a backtest), and `order` is then the strategy's
        own prices with `lots=None`. `asked` True and `order` None means NOTHING is resting.
        """
        resting = snap.state == RESTING
        if self._order_for is not None:
            return True, (self._order_for(snap.side) if resting else None)
        if self._lots_for is not None:
            lots = self._lots_for(snap.side) if resting else None
            if lots is None:
                return True, None
            return True, alerts.RestingOrder(snap.entry, snap.stop, lots)
        if not resting or snap.entry is None:
            return False, None
        return False, alerts.RestingOrder(snap.entry, snap.stop, None)

    def _same(self, a, b) -> bool:
        """Equal as the READER sees them — prices at the symbol's digits, lots at 2 places."""
        if a is None or b is None:
            return a is b
        r = lambda v, n: None if v is None else round(float(v), n)  # noqa: E731
        return (r(a.price, self._digits), r(a.stop, self._digits), r(a.lots, 2)) == (
            r(b.price, self._digits),
            r(b.stop, self._digits),
            r(b.lots, 2),
        )

    def _follow_order(self, snap: SetupSnapshot, sent: Set[str], root) -> None:
        """Keep the thread describing the order the broker ACTUALLY holds.

        🔴 **The first resting message is still gated by `announce_resting`, and marked sent only
        once an order exists** — the two bookkeeping-before-the-guard mistakes this class is
        written to avoid. After that, every change the reader could see (price, stop, lots) gets
        one `MOVED` reply. An order that disappears says nothing. Aaron,
        2026-09-16: the thread must never describe an order the account is not holding.

        ⚠ **Compared at display precision**, so a stop that drifts in the fifth decimal does not
        post. ⚠ **A strategy with no resting state at all never reaches the follow-up path**,
        because nothing was announced.
        """
        asked, now = self._order_now(snap)
        if ENTRY_ZONE_MSG not in sent:
            if snap.state != RESTING or not snap.announce_resting:
                return
            if asked and now is None:
                return  # refused or cancelled — never announce an order the broker lacks
            sent.add(ENTRY_ZONE_MSG)
            self._order[snap.key] = now
            if self._on(ENTRY_ZONE_MSG):
                lots = now.lots if now is not None else None
                self._post(alerts.format_entry_zone(snap, self._digits, lots), reply_to=root)
            self._save()
            return
        if now is None:
            # 🔴 **Silent, by Aaron's call (2026-09-16): "I don't need the cancel messages."** The
            # last DESCRIBED order is kept, so the replacement is compared against what the reader
            # last saw — a re-placement at the same price says nothing, a new price says MOVED.
            return
        before = self._order.get(snap.key)
        if self._same(before, now):
            return
        self._order[snap.key] = now
        if self._on(ENTRY_ZONE_MSG):
            self._post(
                alerts.format_order_moved(
                    snap, self._digits, now if asked else None, before if asked else None
                ),
                reply_to=root,
            )
        self._save()

    # ── surviving a restart ──────────────────────────────────────────────────────────────────
    def _load(self) -> None:
        """Read back what was already announced, so a restart does not re-announce it.

        🔴 **This is the half that makes the thread real.** Before it existed the record of what
        a setup had been told lived only in memory, so stopping, restarting, redeploying or
        re-warming a bot wiped it: every live setup was announced again from scratch, and the
        Telegram message id of its first announcement was lost, so its outcome could never be
        posted as a reply to the message the reader was actually looking at. Measured on
        `sos_fade_1`, 2026-09-15: four identical `SETUP FORMING` roots for one setup in 24 hours,
        three of them permanently unclosable.

        ⚠ **NEVER raises**, like everything else here. An unreadable or half-written state file
        costs the de-duplication for one restart, which is the old behaviour — it may not cost
        the bot its start.
        """
        if self._state_path is None or not self._state_path.exists():
            return
        try:
            with open(self._state_path, encoding="utf-8") as f:
                blob = json.load(f)
            stored_channel = blob.get("channel", "")
            if stored_channel != self._channel:
                # SAID, not swallowed. The consequence is visible to the reader — open setups are
                # announced once more, in the new room — and a silent drop would look exactly like
                # the bug this whole file fixes.
                self._warn(
                    f"the signals channel changed since these threads were opened "
                    f"({stored_channel!r} -> {self._channel!r}); dropping "
                    f"{len(blob.get('setups') or {})} stored thread(s). A message id only means "
                    f"anything in its own chat, so any still-open setup is announced once more "
                    f"in the new room."
                )
                return
            for key, row in (blob.get("setups") or {}).items():
                self._threads[key] = row.get("root")
                self._sent[key] = set(row.get("sent") or ())
                self._about[key] = {"side": row.get("side"), "symbol": row.get("symbol") or ""}
                if "order" in row:
                    o = row["order"]
                    self._order[key] = None if o is None else alerts.RestingOrder(*o)
        except Exception as e:  # noqa: BLE001 — see the module docstring
            self._threads.clear()
            self._sent.clear()
            self._about.clear()
            self._order.clear()
            self._warn(f"could not read the setup-alert state ({e}) — open setups may repeat once.")

    def _save(self) -> None:
        """Write the three dicts, atomically. Never raises.

        ⚠ **Atomic because the alternative is silent.** This is written from inside the bar loop;
        a process stopped mid-write would leave truncated JSON, and `_load` would then throw away
        every open thread on the next start — the exact failure this file exists to end, arriving
        through the fix for it.
        """
        if self._state_path is None:
            return
        try:
            rows = {}
            for key, sent in self._sent.items():
                about = self._about.get(key) or {}
                rows[key] = {
                    "root": self._threads.get(key),
                    "sent": sorted(sent),
                    "side": about.get("side"),
                    "symbol": about.get("symbol") or "",
                }
                if key in self._order:
                    o = self._order[key]
                    rows[key]["order"] = None if o is None else list(o)
            tmp = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"channel": self._channel, "setups": rows}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._state_path)
        except Exception as e:  # noqa: BLE001 — see the module docstring
            self._warn(f"could not save the setup-alert state ({e}) — open setups may repeat once.")

    def reconcile(self, resolved: Sequence[SetupSnapshot], live_keys) -> None:
        """Close every thread this bot announced before it stopped and can no longer be watching.

        🔴 **`live_keys` must be `None` when the strategy could not be asked, and a collection —
        possibly empty — when it could.** `None` leaves every thread open; an empty collection
        means the bot is genuinely watching nothing and closes them all. Collapsing the two would
        close every open thread on a bar the strategy merely failed to answer, which is root
        `CLAUDE.md` rule 1 arriving in the signals channel.

        `resolved` is what the strategy replayed through the OUTAGE — the warm-up drain the runner
        used to throw away wholesale. Only the snapshots matching a thread this bot actually
        announced are used, so nothing else about that behaviour changes: years of replayed
        history still go in the bin, and the handful that close a real thread carry the
        strategy's OWN reason rather than one composed here.

        A thread with no matching snapshot and no live setup is closed with a message that says
        the outcome was not recorded. ⚠ **It must not borrow the wording of a real death.** The
        bot does not know whether that setup filled, died or expired, and a confident `NO TRADE`
        on a setup that might have traded is a label with no code behind it.
        """
        try:
            # 🔴 **Only a TERMINAL snapshot is an outcome, and never for a setup still alive.**
            # The warm-up drain is `live_setups()` in full, so it also carries every setup still
            # being watched. Treating those as resolved posted `👋 NO TRADE` with no reason onto a
            # live short on 2026-09-16 (demo, 18:41 UTC restart) — the bot placed that same order
            # four minutes later. A key in `live_keys` is still open whatever the drain says.
            still_live = set(live_keys or ())
            for snap in resolved:
                if not snap.is_terminal or snap.key not in self._sent or snap.key in still_live:
                    continue
                self._close(snap.key, alerts.format_resolved(snap, self._digits))
            if live_keys is None:
                self._save()
                return
            live = set(live_keys)
            for key in [k for k in self._sent if k not in live]:
                about = self._about.get(key) or {}
                self._close(key, alerts.format_lost(about.get("side"), about.get("symbol") or ""))
            self._save()
        except Exception as e:  # noqa: BLE001 — see the module docstring
            self._warn(f"could not reconcile the open setup threads: {e}")

    def _close(self, key: str, text: str) -> None:
        """Post a closing message onto one stored thread and forget it. Never raises."""
        if RESOLVED_MSG not in (self._sent.get(key) or ()) and self._on(RESOLVED_MSG):
            self._post(text, reply_to=self._threads.get(key))
        self._forget(key)

    def _forget(self, key: str) -> None:
        # A process meant to run for months cannot keep an entry per setup it has ever seen.
        self._threads.pop(key, None)
        self._sent.pop(key, None)
        self._about.pop(key, None)
        self._order.pop(key, None)

    def open_keys(self) -> List[str]:
        """Which setups this bot has already announced and not yet closed — for the start banner."""
        return sorted(self._sent)

    def _on(self, category: str) -> bool:
        return category in self._categories

    def _post(self, text: str, reply_to: Optional[int] = None) -> Optional[int]:
        from notify import SIGNAL

        return self._send(text, SIGNAL, reply_to=reply_to)

    def _warn(self, msg: str) -> None:
        if self._log is not None:
            self._log.warning(msg)
        else:  # pragma: no cover - a bot always has a log
            print(f"setup_alerts: {msg}")
