"""The signals room's RE-ENTRY thread — its words, its order slot, and the 1-minute clock.

🔴 **Why (2026-10-01, `sos_fade_demo`, live):** a re-entry filled with no warning. The strategy
now reports a possible re-entry as one more watched setup (`backtest/setups.py` → `reentry_of`);
these tests pin what the alert layer does with one, and that the live runner asks it after every
fast bar, since a re-entry arms and fills between two 15-minute bars.

**Proven by mutation, 2026-10-02** (new code, so nothing could go red at HEAD except by import
error). Each reddened the test named: the zone printed despite a decided price → the root test;
either order label or NO RE-ENTRY label reverted → the labels test; the unknown-price note or
the unknown-stop words blanked → those tests; an origin time invented → the no-origin test; the
first-trade slot asked for a re-entry → the thread test; the keyword passed on every setup → the
ordinary-setup test; the bridge reading the first-trade slot → the bridge test; the fast-bar call
dropped → the every-fast-bar test; `finally` replaced by re-raise → the broker-failure test; the
once-only latch dropped → the health-room test.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "algos" / "live", _ROOT / "algos" / "shared", _ROOT / "algos" / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import alerts  # noqa: E402
from setup_alerts import SetupAlerts  # noqa: E402

from backtest.setups import DEAD, FILLED, RESTING, WATCHING, Confluence, SetupSnapshot  # noqa: E402

PARENT = "SosFadeStrategy:L:t1790823600000"


def _re(**kw):
    base = dict(
        key=PARENT + ":re",
        strategy="SosFadeStrategy",
        symbol="XAUUSD.p",
        side=1,
        state=WATCHING,
        confluences=(
            Confluence("First trade", True, "First trade reached its first target, then closed"),
            Confluence("Gap", True, "A gap to rest the order on"),
        ),
        zone=(103.82, 101.14),
        stop=101.09,
        reentry_of=PARENT,
        origin_ms=1_790_823_600_000,
        planned_entry=102.8,
    )
    base.update(kw)
    return SetupSnapshot(**base)


# ── the words ────────────────────────────────────────────────────────────────────────────────
def test_the_root_names_the_setup_and_the_price_when_it_is_known():
    """MUTATION: print the zone even when a price is decided and this reddens."""
    t = alerts.format_reentry_possible(_re(), 2, "SOS Fade").split("\n")
    assert t[0] == "🔁 RE-ENTRY POSSIBLE · LONG"
    assert t[1] == "SOS Fade · XAUUSD.p"
    assert t[2].startswith("From the setup of ") and t[2].endswith(".")
    assert "✓ First trade reached its first target, then closed" in t[3]
    assert t[4] == "Buy at 102.80 · Stop 101.09"
    assert "zone" not in "\n".join(t).lower()


def test_without_a_price_it_shows_the_zone_and_says_the_price_is_not_known():
    """The plan's own words for a re-entry that still waits for its price."""
    t = alerts.format_reentry_possible(_re(planned_entry=None), 2, "SOS Fade")
    assert "Re-entry zone 101.14 – 103.82 · Stop 101.09" in t
    assert t.endswith("Exact price not known yet.")


def test_an_unknown_stop_is_said_never_left_blank_or_guessed():
    t = alerts.format_reentry_possible(_re(stop=None), 2, "SOS Fade")
    assert "Stop not known yet" in t


def test_with_no_origin_time_it_names_no_time():
    t = alerts.format_reentry_possible(_re(origin_ms=None), 2, "SOS Fade")
    assert "From the setup" not in t


def test_the_order_and_outcome_messages_say_RE_ENTRY_and_an_ordinary_setup_does_not():
    """MUTATION: drop the `reentry_of` test in any formatter and its line reddens."""
    re_rest = _re(state=RESTING, entry=102.8)
    assert alerts.format_entry_zone(re_rest, 2, 0.12).startswith("🎯 RE-ENTRY ORDER WAITING")
    assert alerts.format_order_moved(re_rest).startswith("🔁 RE-ENTRY ORDER MOVED")
    assert alerts.format_resolved(_re(state=FILLED)).startswith("✅ RE-ENTERED · LONG")
    dead = alerts.format_resolved(_re(state=DEAD, reason="The setup expired."))
    assert dead.startswith("👋 NO RE-ENTRY · LONG") and dead.endswith("The setup expired.")

    plain = _re(reentry_of=None, state=RESTING, entry=102.8)
    assert alerts.format_entry_zone(plain, 2).startswith("🎯 LIMIT ORDER WAITING")
    assert alerts.format_resolved(_re(reentry_of=None, state=FILLED)).startswith("✅ ENTERED")


# ── the thread ───────────────────────────────────────────────────────────────────────────────
class _Rec:
    def __init__(self):
        self.sent = []

    def __call__(self, text, kind, reply_to=None):
        self.sent.append((text.split("\n")[0], reply_to))
        return len(self.sent)


class _Strat:
    def __init__(self, bars):
        self._bars = list(bars)
        self.execution = self

    def live_setups(self):
        return self._bars[0] if self._bars else []

    def drain_setups(self):
        return self._bars.pop(0) if self._bars else []


def test_a_reentry_gets_its_own_thread_and_its_order_is_read_from_the_REENTRY_slot():
    """🔴 MUTATION: ask `order_for(side)` without `reentry=True` — the broker's FIRST-trade slot
    is empty, so the order-waiting message never goes out and this reddens."""
    asked = []

    def order_for(side, reentry=False):
        asked.append(reentry)
        return alerts.RestingOrder(102.8, 101.09, 0.12) if reentry else None

    rec = _Rec()
    sa = SetupAlerts(send=rec, display="SOS Fade", order_for=order_for)
    strat = _Strat([[_re()], [_re(state=RESTING, entry=102.8)], [_re(state=FILLED)]])
    for _ in range(3):
        sa.on_bar(strat)
    assert [h for h, _ in rec.sent] == [
        "🔁 RE-ENTRY POSSIBLE · LONG",
        "🎯 RE-ENTRY ORDER WAITING · LONG",
        "✅ RE-ENTERED · LONG",
    ]
    assert rec.sent[1][1] == 1 and rec.sent[2][1] == 1  # both reply to the root
    assert asked and all(asked)


def test_an_ordinary_setup_still_asks_the_first_trade_slot_with_no_keyword():
    """A caller whose `order_for` predates the keyword must keep working."""
    rec = _Rec()
    sa = SetupAlerts(send=rec, display="X", order_for=lambda side: alerts.RestingOrder(1, 0.5, 1))
    plain = _re(reentry_of=None, key="K", state=RESTING, entry=1.0)
    sa.on_bar(_Strat([[plain]]))
    assert "🎯 LIMIT ORDER WAITING · LONG" in [h for h, _ in rec.sent]


# ── the bridge's re-entry slot ───────────────────────────────────────────────────────────────
def test_the_bridge_reports_the_reentry_slot_only_when_asked():
    """Through the REAL `OrderBridge`. MUTATION: read `primary_slot` for both and this reddens."""
    import bridge as live_bridge
    from test_live_bridge import _bridge, _FakeExecution

    b, _mt5, _ledger, _notes = _bridge(_FakeExecution())
    b._rest[live_bridge.SECONDARY_LONG] = live_bridge._Rest(
        ticket=2, price=102.8, lots=0.12, sl=101.09
    )
    assert b.resting_order(1) is None
    assert b.resting_order(1, reentry=True) == (102.8, 101.09, 0.12)
    assert b.resting_lots(1, reentry=True) == 0.12
    assert b.resting_lots(1) is None


# ── the live runner asks after every FAST bar ────────────────────────────────────────────────
def _runner(sync_fast, watch_failed=None):
    import runner as live_runner

    order, health = [], []

    class _Bridge:
        dry_run = False

        def sync_fast(self, step, bar_close_ms=None):
            order.append("bridge")
            sync_fast()

    class _Alerts:
        def on_bar(self, strategy):
            order.append("alerts")

    class _Log:
        def warning(self, *a, **k):
            pass

        info = error = warning

    r = live_runner.LiveRunner.__new__(live_runner.LiveRunner)
    r.bridge = _Bridge()
    r.setup_alerts = _Alerts()
    r.log = _Log()
    r.fast_feed = SimpleNamespace(bar_seconds=60)
    r._save_reentry_memory = lambda: None
    r._notify_health = health.append
    # `_label` is the REAL property; it never raises and falls back to the display name.
    r.cfg = SimpleNamespace(bot_key="sos_fade_demo", display_name="SOS Fade", account=None)
    r.strategy = SimpleNamespace(
        execution=SimpleNamespace(reentry_watch=SimpleNamespace(failed=watch_failed))
    )
    return r, order, health


_STEP = SimpleNamespace(bar=SimpleNamespace(timestamp_ms=1_790_842_500_000), arm=None)


def test_the_signals_room_is_asked_after_every_fast_bar_and_after_the_broker():
    """🔴 The 2026-10-01 re-entry armed and filled inside one 15-minute bar. MUTATION: drop the
    call from `_observe_secondary` and this reddens."""
    r, order, _ = _runner(lambda: None)
    r._observe_secondary(_STEP)
    assert order == ["bridge", "alerts"]


def test_a_broker_failure_on_the_fast_bar_still_lets_the_room_speak():
    """MUTATION: drop the `try/finally` around `sync_fast` and the exception escapes first."""

    def boom():
        raise RuntimeError("MT5 went away")

    r, order, _ = _runner(boom)
    with pytest.raises(RuntimeError):
        r._observe_secondary(_STEP)
    assert order == ["bridge", "alerts"]


def test_a_failed_reentry_watch_is_said_in_the_health_room_ONCE():
    """A warning that stopped working looks exactly like a quiet market. MUTATION: drop the
    `_reentry_watch_failure_said` latch and it is said every minute."""
    r, _order, health = _runner(lambda: None, watch_failed="RuntimeError: bad snapshot")
    r._observe_secondary(_STEP)
    r._observe_secondary(_STEP)
    assert len(health) == 1 and "RE-ENTRY WARNINGS OFF" in health[0]
