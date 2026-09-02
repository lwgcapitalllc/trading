"""The order bridge — strategy intent mirrored onto MT5.

These tests pin the DECISIONS, not the wire format: what the bridge chooses to place, move,
cancel or refuse given a strategy state and a broker state. That is where every bug in this
layer lives, and none of it needs a terminal.

The two behaviours worth reading first:
  * a real emulator-vs-broker disagreement HALTS the bot rather than continuing on a fiction;
  * a size change is a CANCEL + RE-PLACE, because MT5's MODIFY silently ignores volume.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest

_LIVE = Path(__file__).resolve().parent.parent / "live"
_SHARED = Path(__file__).resolve().parent.parent / "shared"
sys.path.insert(0, str(_SHARED))
sys.path.insert(0, str(_LIVE))
import bridge as live_bridge  # noqa: E402
from order_sizing import SymbolSpec  # noqa: E402

# The live bot's real symbol, with the numbers measured off the PU Prime terminal on
# 2026-07-31 (`instances/mpc_sos_fade_demo/config.json` → `_measured`).
#
# ⚠ The fake below returns THIS dataclass — the same type `mt5_ops.symbol_spec` returns. That is
# deliberate and it is a rule, not a convenience: this repo has already lost three weeks to a
# test fixture that was MORE COMPLETE than production (`test_secondary.py`, 2026-08-06 — the fake
# 1m bar carried two fields the real one did not, so every test exercised a shape the code never
# produced). Sharing the type makes that impossible: a field the fake supplies is one the real
# method must supply too.
GOLD_SPEC = SymbolSpec(
    symbol="XAUUSD",
    contract_size=100.0,
    tick_size=0.01,
    tick_value=1.0,
    volume_min=0.01,
    volume_max=100.0,
    volume_step=0.01,
    digits=2,
)


# ── fakes ─────────────────────────────────────────────────────────────────────
@dataclass
class _Pend:
    dir: int
    edge: float
    qty: float
    sl: float
    tp1: float = 0.0
    tp2: float = 0.0
    sos_bar: int = 7


class _Pos:
    def __init__(self, ticket, type_, price_open, volume, sl):
        self.ticket, self.type = ticket, type_
        self.price_open, self.volume, self.sl = price_open, volume, sl


class _Order:
    def __init__(self, ticket, price=0.0, sl=0.0, volume=0.0, buy=True):
        self.ticket = ticket
        # Carried so `account_exposure` below can be DERIVED from this book rather than
        # hand-listed beside it. A fake whose exposure disagrees with its own order book is the
        # 2026-08-07 trap one level up: it would test a shape production never produces.
        self.price, self.sl, self.volume, self.buy = price, sl, volume, buy
        # MT5 names these fields `price_open` and `volume_current` on a real order, and the
        # orphan sweep reads them by those names. Mirrored rather than renamed: the existing
        # `price`/`volume` are load-bearing for the exposure derivation above, and a fake that
        # answers to a name production does not use is the other half of the same trap.
        self.price_open = price
        self.volume_current = volume


class _FakeMt5Ops:
    symbol = "XAUUSD"
    magic = 770115
    bot_label = "BOT_TEST"

    def __init__(self, *, spec=GOLD_SPEC, free=1_000_000.0, leverage=500.0):
        self.positions: list = []
        self.orders: list = []
        self.actions: list = []
        self._ticket = 900
        self.deal = (0.0, 0.0)
        self.spec = spec
        self.free = free
        self.leverage = leverage
        # What OTHER magics hold on this account — another bot, or a hand trade. `None` stands
        # for "the terminal could not be asked", which is a different answer from an empty
        # account and the bridge has to treat it as one.
        self.external: list = []
        self.exposure_readable = True
        # Whether the ORDER BOOK can be read. Production distinguishes "nothing resting" from
        # "could not ask" (`mt5_ops.pending_orders_strict`), and a fake that cannot produce the
        # second models a system we do not have — which is the fixture trap this repo has been
        # caught by four times. It is the state the whole 2026-08-25 fix turns on.
        self.orders_readable = True
        # Tickets that have become positions. See `_book()`.
        self._filled: set = set()
        # What the broker says when asked to cancel. True (gone), False (still there), or
        # `broker_result.UNKNOWN`.
        self.cancel_result = True
        # True / False / UNKNOWN, same three answers `mt5_ops.partial_close` really gives.
        self.partial_result = True
        # Whether a full close at market succeeds. See `close_position` below.
        self.close_result = True

    def get_open_positions(self, symbol=None):
        # Remember every ticket that has ever been open, so `_book()` can keep a filled order
        # out of the order book AFTER its position closes too. In MT5 a triggered order is gone
        # for good; it does not come back when the position does.
        self._filled.update(p.ticket for p in self.positions)
        return list(self.positions)

    def _book(self):
        """The resting orders, with anything that has FILLED removed.

        ⚠ **Derived, because MT5 cannot show an order as both resting and filled.** A triggered
        pending order leaves `orders_get` and appears in `positions_get` under the SAME ticket.
        Tests here open a position by assigning `positions` directly, and before 2026-08-25
        nothing read the order book afterwards, so the fake was never wrong in a way that showed
        — it simply carried a state production cannot produce. The orphan sweep reads that book
        every bar, and it flagged the fake's phantom order the moment it was switched on. **A
        fixture more capable than production hides the defect; this one invented one.**
        """
        self._filled.update(p.ticket for p in self.positions)
        return [o for o in self.orders if o.ticket not in self._filled]

    def get_pending_orders(self, symbol=None):
        return self._book()

    def pending_orders_strict(self, symbol=None):
        return self._book() if self.orders_readable else None

    def account_exposure(self, symbol=None):
        """Everything on the account across EVERY magic — this bot's own book plus `external`.

        DERIVED from `self.positions` / `self.orders`, never hand-listed: production reads one
        terminal, so a fake whose exposure and whose order book can disagree tests a state that
        cannot occur. It also means the bridge's own-magic exclusion is genuinely exercised —
        with a hand-listed exposure it would be exercising nothing.
        """
        from account_risk import Exposure

        if not self.exposure_readable:
            return None
        out = []
        for p in self.positions:
            out.append(
                Exposure(
                    ticket=p.ticket,
                    symbol=self.symbol,
                    magic=self.magic,
                    direction=1 if p.type == 0 else -1,
                    volume=p.volume,
                    entry=p.price_open,
                    stop=p.sl,
                    resting=False,
                )
            )
        for o in self.orders:
            out.append(
                Exposure(
                    ticket=o.ticket,
                    symbol=self.symbol,
                    magic=self.magic,
                    direction=1 if o.buy else -1,
                    volume=o.volume,
                    entry=o.price,
                    stop=o.sl,
                    resting=True,
                )
            )
        return out + list(self.external)

    def normalize_volume(self, lots, symbol=None):
        v = int(lots / 0.01 + 1e-9) * 0.01
        return round(v, 2) if v >= 0.01 else 0.0

    def symbol_spec(self, symbol=None):
        return self.spec

    def free_margin(self):
        return self.free

    def margin_for(self, direction, lots, price, symbol=None):
        if self.spec is None:
            return None
        return lots * self.spec.contract_size * price / self.leverage

    # ⚠ `place` / `cancel` maintain `self.orders`, because a real broker does. Until 2026-08-07
    # this fake recorded the CALL and left the order book empty, so `get_pending_orders()`
    # always answered "nothing resting" — which is indistinguishable from the broker having
    # deleted the order, the exact condition `_observe_vanished` now watches for. A fake whose
    # book never agrees with its own actions cannot test anything that reads that book.
    def place_pending_limit(self, direction, lots, price, sl, tp=0.0, comment="", symbol=None):
        self._ticket += 1
        self.actions.append(("place", direction, lots, price, sl))
        self.orders.append(
            _Order(self._ticket, price=price, sl=sl, volume=lots, buy=direction == "bullish")
        )
        return self._ticket, price

    def modify_pending(self, ticket, price, sl, tp=0.0, symbol=None):
        self.actions.append(("modify", ticket, price, sl))
        return True

    # ⚠ Like `cancel_pending` below, this has THREE outcomes because production has three, and
    # it MOVES ITS OWN BOOK on success. A fake that recorded the call and left the position at
    # its old volume would let the bridge reconcile forever against a size that never changed —
    # and "it banked every bar" is precisely the failure this reconciliation could have.
    def partial_close(self, ticket, lots, direction):
        self.actions.append(("partial", ticket, round(lots, 4), direction))
        if self.partial_result is not True:
            return self.partial_result
        for p in self.positions:
            if p.ticket == ticket:
                p.volume = round(p.volume - lots, 8)
        return True

    def close_position(self, ticket, direction, reason=""):
        """Close the WHOLE position at market — the real signature, returning the same
        `(ok, price, pnl)` triple `mt5_ops.close_position` does.

        ⚠ **`close_result` can say False, because the broker can.** A fake that could only
        succeed is exactly why a discarded cancel result went unnoticed for as long as it did
        (see `cancel_pending` below) — the bridge's failure branch here halts a live bot, so it
        is the branch most worth being able to produce.
        """
        self.actions.append(("close", ticket, direction, reason))
        if not self.close_result:
            return False, 0.0, 0.0
        self.positions = [p for p in self.positions if p.ticket != ticket]
        return True, 3300.0, 12.5

    def cancel_pending(self, ticket):
        """Three outcomes, because production has three: gone, still there, or unknown.

        ⚠ **`cancel_result` defaults to True and a fake that could ONLY say True is why a failed
        cancel went unnoticed for as long as it did** — the bridge threw the answer away, and no
        test could show it, because no test could produce an answer worth keeping.
        """
        self.actions.append(("cancel", ticket))
        if self.cancel_result is True:
            self.orders = [o for o in self.orders if o.ticket != ticket]
        return self.cancel_result

    def move_sl(self, ticket, new_sl, tp=None):
        self.actions.append(("move_sl", ticket, new_sl))
        return True

    def get_deal_result(self, ticket):
        return self.deal

    def disconnect(self):
        pass


class _FakeExecution:
    def __init__(
        self,
        pos_dir=0,
        pend_long=None,
        pend_short=None,
        qty=None,
        filled=0.0,
        cfg=None,
        pend_sec=None,
        entry_kind="primary",
        current_stop=None,
    ):
        # `_qty` / `_filled_qty` are what the bridge reconciles the broker's SIZE against, the
        # same private coupling it already has with `_pend_long` and `_pos_dir`. They default to
        # None so every test written before banking existed describes a strategy that scales
        # nothing — which is what those tests are about.
        self._qty = qty
        self._filled_qty = filled
        # The bridge asks THIS whether anything banks at all, and returns immediately if not.
        # None means the same as a config with every rung at zero: nothing to take off.
        self._cfg = cfg
        self._pos_dir = pos_dir
        self._pend_long = pend_long
        self._pend_short = pend_short
        # The RE-ENTRY's resting order and the leg that owns any open position. Both exist on the
        # real `Execution` (`_pend_sec`, and `entry_kind` as a public property), and the fill
        # clock reads them every fast bar — so a fake without them would raise inside the path
        # rather than describe a strategy that has no re-entry. Their defaults are what the
        # shipped bot looks like: no re-entry armed, any position a primary's.
        self._pend_sec = pend_sec
        self.entry_kind = entry_kind
        self._current_stop_value = current_stop
        self._entry = 0.0
        self._stage = 0
        self.blocks: list = []
        self.misses: list = []
        # The restart/re-warm seam. The real `Execution` has both (see its
        # `_POSITION_FIELDS` block) and the bridge calls them whenever a position is open, so a
        # fake without them would raise inside the per-bar path — the fixture-less-complete-than-
        # production trap this file was already bitten by on 2026-08-07.
        self.snapshot: dict = {}
        self.restored = None

    def _current_stop(self) -> float:
        """What the strategy wants the stop to be RIGHT NOW.

        ⚠ Present because the real `Execution` has it and the fill clock calls it on every bar a
        re-entry is open. A fake that answered when production could not would hide the branch
        that has to SAY it cannot (rule 1), so the tests that exercise that branch delete this
        method rather than making it return a sentinel.
        """
        return self._current_stop_value

    def snapshot_position(self) -> dict:
        return dict(self.snapshot)

    def restore_position(self, snap: dict) -> None:
        self.restored = snap
        self._pos_dir = snap.get("_pos_dir", 0)
        self._stage = snap.get("_stage", 0)


class _Dec:
    def __init__(self, stop=None, **kw):
        self.stop = stop
        self.l_stage = kw.get("l_stage", 0)
        self.s_stage = kw.get("s_stage", 0)
        self.long_edge = kw.get("long_edge")
        self.short_edge = kw.get("short_edge")
        self.long_veto = kw.get("long_veto", False)
        self.short_veto = kw.get("short_veto", False)
        self.tp1 = kw.get("tp1", 0.0)
        self.tp2 = kw.get("tp2", 0.0)


class _Sig:
    index = 42
    time_ms = 1_780_000_000_000
    close = 3300.0
    ny_hour = 9
    bull_div_active = False
    bear_div_active = False
    recent_ssl = ""
    recent_bsl = ""


class _FakeLedger:
    def __init__(self):
        self.rows: list = []

    def _rec(self, kind, **kw):
        self.rows.append((kind, kw))

    def event(self, name, **kw):
        self._rec("event:" + name, **kw)

    def trade_opened(self, **kw):
        self._rec("opened", **kw)

    def trade_closed(self, **kw):
        self._rec("closed", **kw)

    def bar(self, *a, **k):
        pass

    def kinds(self):
        return [k for k, _ in self.rows]


class _Log:
    def __init__(self):
        self.lines = []

    def _rec(self, m):
        self.lines.append(str(m))

    info = warning = error = _rec


def install_mt5_stub(monkeypatch):
    """Put a fake MetaTrader5 in place. A plain function, not a fixture, so a sibling test module
    can install the same stub — importing a FIXTURE by name and then naming it as a parameter
    shadows it, which the linter rejects and which would silently give that module a second,
    unrelated fixture of the same name if it did not."""
    m = types.ModuleType("MetaTrader5")

    class _SI:
        point = 0.01
        trade_contract_size = 100.0

    class _AI:
        # The account-level risk cap is a fraction of the LIVE balance, so the stub has to serve
        # one. Without it `_account_balance` returns None and the cap REFUSES every order —
        # correctly ("cannot ask" is never "affordable"), but it would make every cap test pass
        # for the wrong reason.
        balance = 2000.0

    m.symbol_info = lambda s: _SI()
    m.account_info = lambda: _AI()
    monkeypatch.setitem(sys.modules, "MetaTrader5", m)


@pytest.fixture(autouse=True)
def _stub_mt5(monkeypatch):
    """`_moved` and `_contract_size` reach for MetaTrader5. Stub it so the tick size and contract
    size are the real gold ones rather than the fallbacks."""
    install_mt5_stub(monkeypatch)


def _bridge(
    execution,
    *,
    dry_run=False,
    mt5ops=None,
    ledger=None,
    notes=None,
    kinds=None,
    account_risk_cap_pct=None,
    instance_dir=None,
):
    mt5ops = mt5ops or _FakeMt5Ops()
    ledger = ledger or _FakeLedger()
    notes = notes if notes is not None else []
    kinds = kinds if kinds is not None else []

    def _notify(text, kind, reply_to=None):
        """Mirrors the real signature: a routing KIND, an optional reply target, and back comes a
        message id. The id is what a trade's EXIT replies to, so a fake that returned None would
        quietly test the no-thread path and never the one that runs.

        `kind` is positional and required here on purpose — a fake that defaulted it would go on
        passing after a call site stopped stating one, which is the whole thing the routing exists
        to make impossible. `kinds` records them so a test can assert WHERE a message went."""
        notes.append(text)
        kinds.append(kind)
        return len(notes)

    b = live_bridge.OrderBridge(
        mt5ops,
        execution,
        ledger,
        _Log(),
        notify=_notify,
        dry_run=dry_run,
        account_risk_cap_pct=account_risk_cap_pct,
        instance_dir=instance_dir,
    )
    b.state = live_bridge.BridgeState.LIVE
    return b, mt5ops, ledger, notes


# ── configuration guards ──────────────────────────────────────────────────────
def test_a_partial_ladder_that_leaves_a_runner_is_SUPPORTED_since_the_bank_path_landed():
    """30 + 40 = 70, so 30% still rides out to the stop — and `_sync_partials` can reconcile the
    broker down to it. ⚠ This asserted a REFUSAL until 2026-09-01, and the refusal was right for
    as long as the bridge had no exit path at all."""
    cfg = types.SimpleNamespace(
        exec_tp1_pct=30.0, exec_tp2_pct=40.0, exec_secondary=False, fill_model="bar"
    )
    assert live_bridge.full_exit_at_price(cfg) == []
    live_bridge.assert_supported(cfg)  # no raise


def test_a_ladder_that_SUMS_to_the_whole_position_is_still_refused():
    """50 + 50 reaches zero at a price, and the last of a position can only leave as a stop move.
    ⚠ SUMMED, never tested field by field — a check reading `== 100` on one rung waves this
    straight through."""
    cfg = types.SimpleNamespace(
        exec_tp1_pct=50.0, exec_tp2_pct=50.0, exec_secondary=False, fill_model="bar"
    )
    with pytest.raises(
        live_bridge.UnsupportedStrategyConfig, match="WHOLE position off at a price"
    ):
        live_bridge.assert_supported(cfg)


def test_tick_fill_model_is_refused():
    cfg = types.SimpleNamespace(
        exec_tp1_pct=0, exec_tp2_pct=0, exec_secondary=False, fill_model="tick"
    )
    with pytest.raises(live_bridge.UnsupportedStrategyConfig, match="BACKTEST cost model"):
        live_bridge.assert_supported(cfg)


def test_the_shipped_config_is_supported():
    cfg = types.SimpleNamespace(
        exec_tp1_pct=0.0, exec_tp2_pct=0.0, exec_secondary=False, fill_model="bar"
    )
    live_bridge.assert_supported(cfg)  # no raise


# ── the banking rungs the old check could not see (2026-09-01) ────────────────
#
# 🔴 `assert_supported` read `exec_tp1_pct`/`exec_tp2_pct` only — the LAST branch of
# `execution.Execution._tp1_pct`. Three branches above it were invisible to it, and all three
# default to banking 100%.
#
# ⚠ **All nine tests below were watched RED against the bridge as it stood before 2026-09-01,
# and the reds are NOT the same strength — say which is which rather than counting them.**
#   - `test_the_short_hold_variant_is_refused` failed with **DID NOT RAISE**. That is the real
#     one: `exec_short_hold` is a single boolean on a bot that is armed today, nothing refused
#     it, and the bot would have STARTED and ridden every trade past a target the backtest
#     banked 100% at.
#   - The two re-entry refusals failed on the MESSAGE, not on the refusal — the old bridge
#     already refused that config for having no second feed. They pin that the banking reason
#     SURVIVES once G18 stage 2 relaxes the feed refusal, which is the moment it starts
#     mattering. A weaker red, and worth nothing if read as the first kind.
#   - The rest exercise `price_triggered_banks` directly, so against HEAD they fail on the
#     function not existing. Weakest red there is, so they were proved by MUTATION instead —
#     six mutations, each reddening its own named test, none surviving:
#
#       mutation                                       went red
#       ---------------------------------------------  ------------------------------------------
#       short-hold branch deleted                      short_hold_variant + short_hold_REPLACES
#       short-hold ADDS instead of REPLACING           short_hold_REPLACES
#       reclaim branch deleted                         reclaim_re_entry + combined_trigger
#       gap/shift branch deleted                       gap_re_entrys + combined_trigger
#       -1.0 no longer means INHERIT                   INHERITS_a_zero_rung + second_rungs_MULTIPLE
#       the second rung's MULTIPLE treated as a bank   second_rungs_MULTIPLE


def _shipped(**over):
    """The live bot's own exit-related settings, so a test says what it CHANGED."""
    cfg = dict(
        exec_tp1_pct=0.0,
        exec_tp2_pct=0.0,
        fill_model="bar",
        exec_short_hold=False,
        exec_sh_tp1_pct=100.0,
        exec_secondary=False,
        exec_sec_trigger="Reclaim Entry",
        exec_sec_tp1_pct=50.0,
        exec_rec_tp1_pct=100.0,
    )
    cfg.update(over)
    return types.SimpleNamespace(**cfg)


def test_the_short_hold_variant_is_refused():
    """One boolean, and the whole position is meant to come off at 2R. The bridge can only move a
    stop, so nothing would come off — and before this check the bot STARTED."""
    with pytest.raises(live_bridge.UnsupportedStrategyConfig, match="exec_sh_tp1_pct=100"):
        live_bridge.assert_supported(_shipped(exec_short_hold=True))


def test_short_hold_REPLACES_the_shared_rung_rather_than_adding_to_it():
    """`_tp1_pct` reads one or the other, never both. Naming both would send the reader to set a
    field that is not being read."""
    banks = live_bridge.price_triggered_banks(_shipped(exec_short_hold=True, exec_tp1_pct=30.0))
    assert [name for name, _ in banks] == ["exec_sh_tp1_pct"]


def test_the_reclaim_re_entry_takes_the_WHOLE_position_and_is_still_refused():
    """`exec_rec_tp1_pct` is 100 — the whole position off at its target, no runner. It is ALSO the
    setting that measured best for that trigger (+21.00R against +7.16R without), which is why
    this refusal has to be loud: the best configuration is the unsupported one, so the reclaim
    waits on a full-exit path while the gap trigger does not."""
    with pytest.raises(live_bridge.UnsupportedStrategyConfig, match="exec_rec_tp1_pct=100"):
        live_bridge.assert_supported(_shipped(exec_secondary=True))


def test_the_gap_re_entrys_half_bank_is_no_longer_a_BANKING_refusal():
    """Its 50% leaves a runner, so the bank path can serve it. What still stops it is the missing
    SECOND ENTRY — and the two must not be confused, because different work fixes each.
    ⚠ This asserted the banking refusal until the bank path landed on 2026-09-01."""
    cfg = _shipped(exec_secondary=True, exec_sec_trigger="FVG in zone")
    assert live_bridge.full_exit_at_price(cfg) == []
    with pytest.raises(live_bridge.UnsupportedStrategyConfig, match="SECOND bar stream"):
        live_bridge.assert_supported(cfg)


def test_a_combined_trigger_names_BOTH_rungs():
    """'FVG in zone + Reclaim Entry' runs both halves, and they bank different percentages off
    different fields. A refusal naming one would be fixed by setting one and refused again."""
    banks = live_bridge.price_triggered_banks(
        _shipped(exec_secondary=True, exec_sec_trigger="FVG in zone + Reclaim Entry")
    )
    assert sorted(name for name, _ in banks) == ["exec_rec_tp1_pct", "exec_sec_tp1_pct"]


def test_a_re_entry_that_INHERITS_a_zero_rung_is_not_a_banking_refusal():
    """-1.0 means 'inherit the shared field', which is 0 here — so nothing banks and this must
    fall through to the SECOND-FEED refusal instead. A check that refuses everything is not a
    check."""
    cfg = _shipped(exec_secondary=True, exec_sec_trigger="FVG in zone", exec_sec_tp1_pct=-1.0)
    assert live_bridge.price_triggered_banks(cfg) == []
    with pytest.raises(live_bridge.UnsupportedStrategyConfig, match="SECOND bar stream"):
        live_bridge.assert_supported(cfg)


def test_the_second_rungs_MULTIPLE_alone_does_not_refuse():
    """`exec_sec_tp2_x` moves where the second rung sits; how much comes off there is
    `exec_tp2_pct` alone. At 0 nothing banks whatever the multiple says."""
    cfg = _shipped(
        exec_secondary=True,
        exec_sec_trigger="FVG in zone",
        exec_sec_tp1_pct=-1.0,
        exec_sec_tp2_x=2.0,
    )
    assert live_bridge.price_triggered_banks(cfg) == []


def test_the_live_bots_own_config_still_passes():
    """The bot that is ARMED right now. If this reddens, a guard has started refusing a
    configuration that is trading — read that before changing the test."""
    assert live_bridge.price_triggered_banks(_shipped()) == []
    live_bridge.assert_supported(_shipped())  # no raise


# ── placing and maintaining a resting limit ───────────────────────────────────
def test_a_strategy_limit_becomes_a_broker_limit():
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, ledger, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    assert ops.actions == [("place", "bullish", 0.42, 3290.0, 3280.0)]
    assert "event:order_placed" in ledger.kinds()


def test_an_unchanged_limit_is_left_alone():
    """Re-writing an identical order every bar is churn the broker sees as flapping — and it
    resets the order's queue position for nothing."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ops.actions.clear()
    b.sync(_Dec(), _Sig())
    assert ops.actions == []


def test_a_moved_limit_is_modified_in_place():
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ex._pend_long = _Pend(1, 3292.5, 42.0, 3282.0)
    ops.actions.clear()
    b.sync(_Dec(), _Sig())
    assert ops.actions == [("modify", 901, 3292.5, 3282.0)]


def test_a_resized_limit_is_cancelled_and_replaced():
    """MT5's MODIFY ignores volume. Sizing moves with equity every bar, so getting this wrong
    means the position size silently freezes at whatever it was when the order was first
    placed."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ex._pend_long = _Pend(1, 3290.0, 55.0, 3280.0)
    ops.actions.clear()
    b.sync(_Dec(), _Sig())
    assert [a[0] for a in ops.actions] == ["cancel", "place"]
    assert ops.actions[-1][2] == 0.55


def test_a_withdrawn_setup_cancels_the_order():
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ex._pend_long = None
    ops.actions.clear()
    b.sync(_Dec(), _Sig())
    assert ops.actions == [("cancel", 901)]


def test_a_sub_minimum_size_is_recorded_rather_than_rounded_up():
    """The account is too small for this stop distance. Placing the broker minimum instead
    would be a bigger bet than the strategy risk-checked — and it would look like a normal
    trade afterwards. Recorded so the missing trade is countable.

    ⚠ The event is `order_refused` carrying `code`, not the old dedicated `order_too_small`.
    That was one of eight ways an order can fail to reach the broker, and giving one of them its
    own name left the other seven — including the margin refusal that would have caught the
    2026-08-07 order — with nowhere to be recorded.
    """
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 0.4, 3280.0))  # 0.4 oz = 0.004 lots
    b, ops, ledger, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    assert ops.actions == []
    assert "event:order_refused" in ledger.kinds()
    refusal = next(kw for k, kw in ledger.rows if k == "event:order_refused")
    assert refusal["code"] == "below_broker_minimum"


# ── an open position ──────────────────────────────────────────────────────────
def test_the_stop_is_ratcheted_to_the_strategys_current_stop():
    ops = _FakeMt5Ops()
    ops.positions = [_Pos(555, 0, 3290.0, 0.42, 3280.0)]
    ex = _FakeExecution(pos_dir=1)
    b, ops, ledger, _ = _bridge(ex, mt5ops=ops)
    b.sync(_Dec(stop=3285.0), _Sig())
    assert ("move_sl", 555, 3285.0) in ops.actions
    assert "event:stop_moved" in ledger.kinds()


def test_an_unchanged_stop_is_not_rewritten():
    ops = _FakeMt5Ops()
    ops.positions = [_Pos(555, 0, 3290.0, 0.42, 3280.0)]
    b, ops, _, _ = _bridge(_FakeExecution(pos_dir=1), mt5ops=ops)
    b.sync(_Dec(stop=3280.0), _Sig())
    assert not any(a[0] == "move_sl" for a in ops.actions)


def test_opening_a_position_reports_the_brokers_real_fill():
    """The strategy's intended limit and the broker's fill are BOTH recorded — the gap between
    them is the only honest measure of live execution quality, and it is invisible if only one
    is kept."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, ledger, notes = _bridge(ex)
    b.sync(_Dec(), _Sig())  # places the limit
    ops.positions = [_Pos(901, 0, 3289.7, 0.42, 3280.0)]  # ...it fills, 30c better
    ex._pos_dir, ex._pend_long = 1, None
    b.sync(_Dec(stop=3280.0), _Sig())

    opened = [kw for k, kw in ledger.rows if k == "opened"][0]
    assert opened["price"] == 3289.7  # what the broker gave
    assert opened["intended_price"] == 3290.0  # where the strategy rested its limit
    assert notes and "ENTRY" in notes[0]


# ── which room each alert goes to ────────────────────────────────────────────────────────────
# The bridge is the only thing in this repo that sends a TRADE message, and it also sends the
# single most serious HEALTH one. Both are pinned, because the split is only worth anything if
# it holds at the one place that produces both kinds.


def test_the_entry_and_exit_alerts_are_TRADES():
    import notify

    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    kinds: list = []
    b, ops, ledger, notes = _bridge(ex, kinds=kinds)
    b.sync(_Dec(), _Sig())
    ops.positions = [_Pos(901, 0, 3290.0, 0.42, 3280.0)]
    ex._pos_dir, ex._pend_long = 1, None
    b.sync(_Dec(stop=3280.0), _Sig())  # entry alert
    ops.positions = []
    ex._pos_dir = 0
    b.sync(_Dec(), _Sig())  # exit alert
    assert kinds, "the bridge sent nothing at all"
    assert set(kinds) == {notify.TRADE}


def test_a_HALT_is_health_not_a_trade():
    """A halt is the bot refusing to place orders — a fact about the machinery, and the one
    message that must not be sitting in a room only checked when a fill arrives."""
    import notify

    kinds: list = []
    b, ops, ledger, notes = _bridge(_FakeExecution(), kinds=kinds)
    b._halt("emulator and broker disagree")
    assert kinds == [notify.HEALTH]
    assert notes and "HALTED" in notes[0]


def test_closing_a_position_reports_pnl_and_r():
    """Risk is measured off the BROKER's fill and the stop actually attached — R has to
    describe the trade that happened, not the one that was intended."""
    ops = _FakeMt5Ops()
    ops.positions = [_Pos(901, 0, 3290.0, 0.42, 3280.0)]
    ex = _FakeExecution(pos_dir=1)
    b, ops, ledger, notes = _bridge(ex, mt5ops=ops)
    b.sync(_Dec(stop=3280.0), _Sig())  # adopt the open position
    ops.positions = []  # ...it closes
    ops.deal = (3320.0, 1260.0)  # 30 points × 0.42 × 100
    ex._pos_dir = 0
    b.sync(_Dec(), _Sig())

    closed = [kw for k, kw in ledger.rows if k == "closed"][0]
    assert closed["pnl_usd"] == 1260.0
    # risk = |3290 - 3280| × 0.42 lots × 100 contract size = $420 → 3R
    assert closed["r_multiple"] == pytest.approx(3.0)
    # The exit alert leads with the OUTCOME, not the word "exit" — see algos/live/alerts.py.
    assert any("WIN" in n and "Made $1,260.00" in n for n in notes)


def test_a_position_cancels_any_leftover_resting_order():
    """One position slot. A limit still resting on the other side would open a second trade the
    strategy has no model of."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ops.positions = [_Pos(950, 1, 3320.0, 0.4, 3330.0)]  # a SHORT filled
    ex._pos_dir = -1
    ops.actions.clear()
    b.sync(_Dec(stop=3330.0), _Sig())
    assert ("cancel", 901) in ops.actions


# ── divergence ────────────────────────────────────────────────────────────────
def test_a_strategy_position_the_broker_does_not_have_halts_the_bot():
    """Every later decision would be computed against a trade that does not exist."""
    b, ops, ledger, notes = _bridge(_FakeExecution(pos_dir=1))
    b.sync(_Dec(stop=3280.0), _Sig())
    assert b.state is live_bridge.BridgeState.HALTED
    assert "MT5 has none" in b.halt_reason
    assert any("HALTED" in n for n in notes)


def test_a_broker_position_the_strategy_does_not_know_about_halts_the_bot():
    ops = _FakeMt5Ops()
    ops.positions = [_Pos(777, 0, 3290.0, 0.42, 3280.0)]
    b, ops, _, _ = _bridge(_FakeExecution(pos_dir=0), mt5ops=ops)
    # the position is observed (so it is logged), then the disagreement is caught
    b.sync(_Dec(), _Sig())
    ops.positions = [_Pos(777, 0, 3290.0, 0.42, 3280.0)]
    b._pos_ticket = None
    b.sync(_Dec(), _Sig())
    assert b.state is live_bridge.BridgeState.HALTED


def test_a_halted_bridge_places_nothing_further():
    ex = _FakeExecution(pos_dir=1)
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(stop=3280.0), _Sig())  # halts
    ops.actions.clear()
    ex._pos_dir, ex._pend_long = 0, _Pend(1, 3290.0, 42.0, 3280.0)
    b.sync(_Dec(), _Sig())
    assert ops.actions == []


def test_startup_refuses_to_adopt_an_unknown_position(tmp_path):
    """Silently taking over an unknown position is how a restart doubles a book — the strategy
    would size a fresh entry with no idea it is already exposed.

    ⚠ The instance directory is REAL and EMPTY, which is the case this test is about: the bot can
    read its own records perfectly well and there simply is not one for this position. Running it
    with `instance_dir=None` would halt too, for the unrelated reason that the bridge cannot look
    — a pass that says nothing about the rule being pinned here.
    """
    ops = _FakeMt5Ops()
    ops.positions = [_Pos(1, 0, 3290.0, 0.42, 3280.0)]
    b, ops, _, _ = _bridge(_FakeExecution(), mt5ops=ops, instance_dir=tmp_path)
    b.adopt_broker_state()
    assert b.state is live_bridge.BridgeState.HALTED
    assert "no usable record" in b.halt_reason


def test_startup_clears_stale_resting_orders():
    """A limit from a previous run was priced off state this process no longer has."""
    ops = _FakeMt5Ops()
    ops.orders = [_Order(11), _Order(12)]
    b, ops, _, _ = _bridge(_FakeExecution(), mt5ops=ops)
    b.adopt_broker_state()
    assert [a for a in ops.actions if a[0] == "cancel"] == [("cancel", 11), ("cancel", 12)]


# ── warmup ────────────────────────────────────────────────────────────────────
def test_a_position_opened_during_warmup_is_never_placed_live():
    """Its entry is in the past at a price that is gone. Opening it now at market would be a
    different trade, so the bridge waits for the emulator to flatten."""
    ex = _FakeExecution(pos_dir=1, pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, ledger, _ = _bridge(ex)
    b.begin_live()
    assert b.state is live_bridge.BridgeState.WARMING
    b.sync(_Dec(stop=3280.0), _Sig())
    assert ops.actions == []  # no order, and no halt either
    assert b.state is live_bridge.BridgeState.WARMING


def test_the_bridge_goes_live_once_the_warmup_position_closes():
    ex = _FakeExecution(pos_dir=1)
    b, ops, ledger, _ = _bridge(ex)
    b.begin_live()
    ex._pos_dir = 0
    ex._pend_long = _Pend(1, 3290.0, 42.0, 3280.0)
    b.sync(_Dec(), _Sig())
    assert b.state is live_bridge.BridgeState.LIVE
    assert "event:went_live" in ledger.kinds()
    assert ops.actions == [("place", "bullish", 0.42, 3290.0, 3280.0)]


# ── dry run ───────────────────────────────────────────────────────────────────
def test_dry_run_sends_nothing_but_records_what_it_would_have_done():
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, ledger, _ = _bridge(ex, dry_run=True)
    b.sync(_Dec(), _Sig())
    assert ops.actions == []
    assert "event:dry_run_action" in ledger.kinds()


# ── sizing: the 2026-08-07 oversizing incident ────────────────────────────────
#
# The arithmetic itself is pinned instrument-by-instrument in `test_order_sizing.py`. These are
# the BRIDGE's half: that it converts at all, that it converts through the one seam, and that
# every way an order can fail to reach the broker leaves a record and a message.


class _Cfg:
    """A stand-in for `SosFadeConfig` carrying only what the bridge reads off it."""

    def __init__(self, risk_pct=10.0, point_value=1.0):
        self.exec_risk_pct = risk_pct
        self.point_value = point_value
        self.exec_tp1_pct = 0.0
        self.exec_tp2_pct = 0.0


def _sizing_bridge(
    pend,
    *,
    balance=2000.0,
    free=2000.0,
    spec=GOLD_SPEC,
    risk_pct=10.0,
    point_value=1.0,
    monkeypatch=None,
):
    ex = _FakeExecution(pend_long=pend)
    ex.cfg = _Cfg(risk_pct, point_value)
    ops = _FakeMt5Ops(spec=spec, free=free)
    b, ops, ledger, notes = _bridge(ex, mt5ops=ops)
    b._account_balance = lambda: balance
    return b, ops, ledger, notes


def test_the_bridge_sends_LOTS_where_the_strategy_computed_UNITS():
    """🔴 THE REGRESSION TEST FOR THE INCIDENT. Watched red against HEAD.

    `Execution` computes `qty = equity·risk%/stop_distance` in the INSTRUMENT's units — ounces
    for gold. MT5's `volume` is LOTS. Before 2026-08-07 the bridge handed one straight to the
    other and every order was 100x, because gold's contract is 100 oz.

    24.79 ounces is a $200 risk over an $8.07 stop. It must reach the broker as **0.24 lots**,
    not 24.79.
    """
    b, ops, _, _ = _sizing_bridge(_Pend(1, 4286.75448, 24.79, 4294.82248))
    b.sync(_Dec(), _Sig())
    assert len(ops.actions) == 1
    verb, side, lots, price, sl = ops.actions[0]
    assert (verb, side) == ("place", "bullish")
    assert lots == 0.24, f"sent {lots} lots — units were not converted to lots"


def test_the_exact_incident_order_never_reaches_the_broker():
    """🔴 The real numbers off ticket 320620565, driven through the real bridge.

    54.82 units at 10% of a compounded $4,423 emulator balance, on an account holding $2,000.
    Before the fix this went out as 54.82 LOTS, rested for eight hours, and was deleted by the
    broker at the fill with `[no money]`.
    """
    b, ops, ledger, notes = _sizing_bridge(_Pend(-1, 4286.75448, 54.82, 4294.82248))
    b._ex._pend_long, b._ex._pend_short = None, _Pend(-1, 4286.75448, 54.82, 4294.82248)
    b.sync(_Dec(), _Sig())
    assert ops.actions == []
    assert "event:order_refused" in ledger.kinds()
    assert any("REFUSED" in n for n in notes)


def test_an_order_the_account_cannot_afford_is_refused_and_not_shrunk():
    """Aaron's question, at the bridge. The answer is NO TRADE — never a smaller one.

    A shrunk order leaves the emulator holding one size and the broker another, and the two
    drift apart with nothing reporting it. That is the same divergence that halts the bot,
    arriving quietly instead of loudly.
    """
    # 500 oz = 5 lots = $43,000 of margin at 1:500, against $2,000 free. The balance is set so
    # the risk is genuinely AUTHORISED ($5,000 is 10% of $50,000) — otherwise the equity check
    # fires first and this test would pass without ever reaching the margin one.
    b, ops, ledger, _ = _sizing_bridge(
        _Pend(1, 4300.0, 500.0, 4290.0), balance=50_000.0, free=2000.0
    )
    b.sync(_Dec(), _Sig())
    assert ops.actions == []
    code = next(kw for k, kw in ledger.rows if k == "event:order_refused")["code"]
    assert code == "insufficient_margin"


def test_a_refusal_alerts_once_and_then_stays_quiet():
    """A setup can rest for hours and is re-offered every bar. One message, not sixty — a
    channel that repeats itself is one nobody reads on the day it matters."""
    b, ops, ledger, notes = _sizing_bridge(_Pend(1, 3290.0, 0.4, 3280.0))
    for _ in range(5):
        b.sync(_Dec(), _Sig())
    assert ops.actions == []
    assert len([n for n in notes if "REFUSED" in n]) == 1
    # ...but every occurrence is still RECORDED, so the count is not lost with the noise.
    assert len([k for k in ledger.kinds() if k == "event:order_refused"]) == 5


def test_a_refusal_that_clears_can_alert_again():
    """The counterpart. Keying the silence on the refusal CODE rather than on 'have we ever
    alerted' is what stops this becoming the de-duplicating-alerter bug — a NEW problem after a
    good order must still speak up."""
    pend_ok = _Pend(1, 4300.0, 200.0 / 10.0, 4290.0)  # 20 oz, $200 risk, 0.20 lots
    b, ops, _, notes = _sizing_bridge(_Pend(1, 3290.0, 0.4, 3280.0))
    b.sync(_Dec(), _Sig())
    assert len([n for n in notes if "REFUSED" in n]) == 1
    b._ex._pend_long = pend_ok
    b.sync(_Dec(), _Sig())  # places fine, refusal cleared
    b._ex._pend_long = _Pend(1, 3290.0, 0.4, 3280.0)
    b.sync(_Dec(), _Sig())
    assert len([n for n in notes if "REFUSED" in n]) == 2


def test_a_symbol_the_terminal_cannot_describe_refuses_rather_than_guessing():
    """No symbol info means no contract size and no tick value. Every available fallback is a
    number that would size a real position off a guess."""
    b, ops, ledger, _ = _sizing_bridge(_Pend(1, 4300.0, 20.0, 4290.0), spec=None)
    b.sync(_Dec(), _Sig())
    assert ops.actions == []
    code = next(kw for k, kw in ledger.rows if k == "event:order_refused")["code"]
    assert code == "symbol_unreadable"


def test_a_placed_order_records_what_it_actually_risks():
    """🔴 The record that did not exist. Nothing anywhere on 2026-08-07 stated what an order
    put at risk in dollars — so a 221x position left an artefact indistinguishable from a
    correct one. `order_placed` now carries the money, not just the lots."""
    b, ops, ledger, _ = _sizing_bridge(_Pend(1, 4300.0, 20.0, 4290.0))
    b.sync(_Dec(), _Sig())
    rec = next(kw for k, kw in ledger.rows if k == "event:order_placed")
    assert rec["lots"] == 0.2
    assert rec["units"] == 20.0
    assert rec["risk_ccy"] == pytest.approx(200.0, abs=0.5)
    assert rec["margin_ccy"] is not None


# ── an order the broker deleted underneath us ─────────────────────────────────
def test_a_resting_order_the_broker_deleted_is_noticed_and_reported():
    """🔴 Watched red against HEAD. This is what actually happened, and nothing could see it.

    The broker removed the resting sell limit with `deleted [no money]`. The bridge went on
    believing it was there, the emulator filled itself on the next bar, and the only symptom
    anywhere was a generic halt six hours later saying the two disagreed.
    """
    b, ops, ledger, notes = _sizing_bridge(_Pend(1, 4300.0, 20.0, 4290.0))
    b.sync(_Dec(), _Sig())
    assert b._rest[live_bridge.PRIMARY_LONG] is not None
    ops.orders.clear()  # the broker deleted it; no position appeared
    b.sync(_Dec(), _Sig())
    assert "event:order_vanished" in ledger.kinds()
    assert any("ORDER GONE" in n for n in notes)


def test_a_filled_order_is_not_reported_as_vanished():
    """The other half, and the one that makes the check usable: an order leaving the book
    because it FILLED is the normal case and must stay silent.

    ⚠ KEPT AND LABELLED: this one PASSES against HEAD, and could not have failed there — before
    the vanish check existed there was nothing to fire wrongly. It pins the ordering that makes
    the new check usable (`_observe_vanished` runs AFTER `_observe_open`, which consumes the
    resting order on a fill), and without it a later 'tidy-up' that reorders the two would turn
    every ordinary fill into an alert with the whole suite still green.
    """
    b, ops, ledger, notes = _sizing_bridge(_Pend(1, 4300.0, 20.0, 4290.0))
    b.sync(_Dec(), _Sig())
    ops.orders.clear()
    ops.positions = [_Pos(950, 0, 4300.0, 0.2, 4290.0)]
    b._ex._pos_dir = 1
    b.sync(_Dec(stop=4290.0), _Sig())
    assert "event:order_vanished" not in ledger.kinds()
    assert not any("ORDER GONE" in n for n in notes)


def test_the_halt_names_the_refusal_that_caused_it():
    """🔴 The message Aaron actually got, improved.

    'Its resting limit filled in the emulator and not at the broker' is true of every cause at
    once, so it sent the reader at the fill logic when the answer was the order size. If the
    order was REFUSED, the halt says so and quotes the reason.
    """
    b, ops, ledger, notes = _sizing_bridge(
        _Pend(1, 4300.0, 500.0, 4290.0), balance=50_000.0, free=2000.0
    )
    b.sync(_Dec(), _Sig())  # refused: insufficient margin
    b._ex._pos_dir = 1  # the emulator fills it anyway
    b._ex._pend_long = None
    b.sync(_Dec(stop=4290.0), _Sig())
    assert b.state is live_bridge.BridgeState.HALTED
    assert "REFUSED" in b.halt_reason
    assert "insufficient_margin" in b.halt_reason


# ── the ACCOUNT-level risk cap (G10) ──────────────────────────────────────────
#
# `exec_risk_pct` is per-TRADE and has never had anything above it, so two bots at 10% put 20%
# on from a state neither can see. These drive the whole seam — the unfiltered broker read, the
# arithmetic, and the refusal — rather than the arithmetic alone, because the arithmetic was
# already right in `test_account_risk.py` and the wiring is where a cap goes quietly missing.
def _cap_pend(edge=3300.0, sl=3290.0, qty=20.0):
    """A long wanting $200 of risk on the stub's $2,000 balance: 20 oz = 0.2 lots, $10 stop,
    $1.00 per 0.01 per lot = $200 = exactly 10%."""
    return _Pend(dir=1, edge=edge, qty=qty, sl=sl)


def _other_bot(risk_dollars, magic=880220):
    """A SECOND bot's open position holding `risk_dollars` of the account's budget."""
    from account_risk import Exposure

    lots = risk_dollars / (10.0 / 0.01 * 1.00)  # $10 of stop distance on gold
    return Exposure(
        ticket=555,
        symbol="XAUUSD",
        magic=magic,
        direction=1,
        volume=lots,
        entry=3300.0,
        stop=3290.0,
        resting=False,
    )


def test_with_no_cap_configured_the_bridge_behaves_exactly_as_before(_stub_mt5):
    """The default has to be inert. Every live result this repo has measured was taken with no
    account cap, and a default appearing from nowhere would move a live bot with no measurement
    behind it."""
    b, ops, _, _ = _bridge(_FakeExecution(pend_long=_cap_pend()))
    ops.external = [_other_bot(100_000.0)]  # the account is enormously over any cap
    b.sync(_Dec(), _Sig())
    assert [a[0] for a in ops.actions] == ["place"]


def test_the_second_bot_is_REFUSED_when_the_first_holds_the_whole_budget(_stub_mt5):
    """Aaron's requirement, end to end: one bot has the account's risk on, this one wants in,
    and the system blocks it. Nothing reaches the broker."""
    b, ops, ledger, notes = _bridge(
        _FakeExecution(pend_long=_cap_pend()), account_risk_cap_pct=10.0
    )
    ops.external = [_other_bot(200.0)]  # the whole 10% of $2,000
    b.sync(_Dec(), _Sig())

    assert ops.actions == []
    refusals = [e for e in ledger.rows if e[0] == "event:order_refused"]
    assert refusals and refusals[0][1]["code"] == "account_risk_cap"
    assert "880220" in refusals[0][1]["detail"]


def test_room_freed_by_the_other_bot_moving_ITS_stop_to_breakeven_lets_this_one_in(_stub_mt5):
    """The property that makes a reservation model worth having, and the reason the cap reads the
    CURRENT stop rather than the entry one: the other bot is still in the market, still holding a
    full position, and holding NO risk — so it is not blocking anything."""
    b, ops, _, _ = _bridge(_FakeExecution(pend_long=_cap_pend()), account_risk_cap_pct=10.0)
    from account_risk import Exposure

    ops.external = [
        Exposure(
            ticket=555,
            symbol="XAUUSD",
            magic=880220,
            direction=1,
            volume=0.20,
            entry=3300.0,
            stop=3300.0,
            resting=False,
        )
    ]
    b.sync(_Dec(), _Sig())
    assert [a[0] for a in ops.actions] == ["place"]


def test_a_partly_used_budget_REFUSES_rather_than_placing_a_smaller_order(_stub_mt5):
    """Refuse, never shrink. A resized order is not the trade the strategy's emulator is holding;
    the two would grade different R and `_agrees` would halt the bot on a divergence the safety
    feature created. The BACKTEST allocator shrinks instead, which is coherent there because the
    account hands the granted size back — nothing hands a size back across a process boundary."""
    b, ops, ledger, _ = _bridge(_FakeExecution(pend_long=_cap_pend()), account_risk_cap_pct=10.0)
    ops.external = [_other_bot(150.0)]  # $50 of room against a $200 order
    b.sync(_Dec(), _Sig())

    assert ops.actions == []  # NOT a 0.05-lot order
    assert [e[1]["code"] for e in ledger.rows if e[0] == "event:order_refused"] == [
        "account_risk_cap"
    ]


def test_this_bots_OWN_resting_order_does_not_block_its_own_re_size(_stub_mt5):
    """The own-magic exclusion, and it is not a shortcut. The strategy has ONE position slot, so
    anything of ours already resting is what this order REPLACES — counting it would make the bot
    refuse its own re-sizes near the cap, which reads exactly like a broken strategy."""
    b, ops, _, _ = _bridge(_FakeExecution(pend_long=_cap_pend()), account_risk_cap_pct=10.0)
    b.sync(_Dec(), _Sig())  # places, and the fake's book now holds it
    assert [a[0] for a in ops.actions] == ["place"]

    b._ex._pend_long = _cap_pend(edge=3301.0, sl=3291.0)  # same risk, moved a dollar
    b.sync(_Dec(), _Sig())
    assert [a[0] for a in ops.actions] == ["place", "modify"]


def test_a_hand_trade_with_NO_STOP_refuses_rather_than_scoring_as_zero_risk(_stub_mt5):
    """The dangerous shape. A stopless position's risk is UNBOUNDED, and the falsy value it
    arrives as is the same shape as 'no risk' — so scoring it zero would let the one thing the
    cap exists to bound sit invisibly underneath it."""
    b, ops, ledger, _ = _bridge(_FakeExecution(pend_long=_cap_pend()), account_risk_cap_pct=10.0)
    from account_risk import Exposure

    ops.external = [
        Exposure(
            ticket=42,
            symbol="XAUUSD",
            magic=0,
            direction=1,
            volume=0.5,
            entry=3300.0,
            stop=0.0,
            resting=False,
        )
    ]
    b.sync(_Dec(), _Sig())

    assert ops.actions == []
    refusals = [e for e in ledger.rows if e[0] == "event:order_refused"]
    assert refusals[0][1]["code"] == "account_risk_unmeasurable"
    assert "NO broker-side stop" in refusals[0][1]["detail"]


def test_an_unreadable_account_REFUSES_and_never_reads_as_an_empty_one(_stub_mt5):
    """A cap that opens itself when the terminal wobbles is a cap that is absent exactly when the
    account is least healthy — the `mt5_link` three-state rule applied to money."""
    b, ops, ledger, _ = _bridge(_FakeExecution(pend_long=_cap_pend()), account_risk_cap_pct=10.0)
    ops.exposure_readable = False
    b.sync(_Dec(), _Sig())

    assert ops.actions == []
    assert [e[1]["code"] for e in ledger.rows if e[0] == "event:order_refused"] == [
        "account_risk_unreadable"
    ]


def test_a_per_order_refusal_is_reported_BEFORE_the_account_cap(_stub_mt5):
    """Precedence. A refusal should name the first thing wrong with the ORDER itself before it
    starts talking about what other bots are holding — otherwise a collapsed stop gets blamed on
    a busy account and the reader goes looking in the wrong place."""
    b, ops, ledger, _ = _bridge(
        _FakeExecution(pend_long=_Pend(dir=1, edge=3300.0, qty=20.0, sl=3300.0)),
        account_risk_cap_pct=10.0,
    )
    ops.external = [_other_bot(200.0)]  # the account is also full
    b.sync(_Dec(), _Sig())
    assert [e[1]["code"] for e in ledger.rows if e[0] == "event:order_refused"] == [
        "zero_stop_distance"
    ]


# ── banking part of a position (2026-09-01) ───────────────────────────────────
#
# 🔴 The bridge had NO exit path of any kind: its only order calls were place / modify / cancel
# a resting limit, and move a stop. Every exit reached the broker as a stop move, so any rung
# that takes size off AT A PRICE simply never happened. `_sync_partials` is the reconciliation
# that closes that gap.
#
# ⚠ It is a RECONCILIATION, not an event: it asks how much SHOULD be open and closes the
# difference. That is why a missed bar, a restart or a dropped connection self-heals, and why
# every test below drives it by setting a size rather than by firing a rung.


def _banking_cfg(**over):
    """A config that banks something, so the bridge enters the partial path at all."""
    base = dict(
        exec_tp1_pct=50.0,
        exec_tp2_pct=0.0,
        exec_secondary=False,
        exec_short_hold=False,
        exec_scale_in=False,
        fill_model="bar",
    )
    base.update(over)
    return types.SimpleNamespace(**base)


def _open_bank(qty=1.0, filled=0.5, held=1.0, cfg=None, partial=True):
    """An open long of `held` lots where the strategy believes `qty - filled` should remain."""
    ops = _FakeMt5Ops()
    ops.positions = [_Pos(555, 0, 3290.0, held, 3280.0)]
    ops.partial_result = partial
    ex = _FakeExecution(pos_dir=1, qty=qty, filled=filled, cfg=cfg or _banking_cfg())
    b, ops, ledger, notes = _bridge(ex, mt5ops=ops)
    b._contract_size = lambda: 1.0  # the units→lots conversion has its own test below
    return b, ops, ledger, notes


def test_a_position_larger_than_the_strategy_expects_is_BANKED_DOWN():
    b, ops, ledger, _ = _open_bank(qty=1.0, filled=0.5, held=1.0)
    b.sync(_Dec(stop=3280.0), _Sig())
    assert ("partial", 555, 0.5, "bullish") in ops.actions
    assert "event:partial_banked" in ledger.kinds()
    assert ops.positions[0].volume == 0.5


def test_a_SHORT_is_banked_in_its_own_direction():
    ops = _FakeMt5Ops()
    ops.positions = [_Pos(555, 1, 3290.0, 1.0, 3300.0)]
    ex = _FakeExecution(pos_dir=-1, qty=1.0, filled=0.5, cfg=_banking_cfg())
    b, ops, _, _ = _bridge(ex, mt5ops=ops)
    b._contract_size = lambda: 1.0
    b.sync(_Dec(stop=3300.0), _Sig())
    assert ("partial", 555, 0.5, "bearish") in ops.actions


def test_a_position_that_ALREADY_matches_is_left_alone():
    """The reconciliation must be a no-op once it has run, or it banks every bar until the
    position is gone — the worst failure this shape has."""
    b, ops, ledger, _ = _open_bank(qty=1.0, filled=0.5, held=0.5)
    b.sync(_Dec(stop=3280.0), _Sig())
    assert not any(a[0] == "partial" for a in ops.actions)
    assert "event:partial_banked" not in ledger.kinds()


def test_banking_TWICE_does_not_happen_because_the_second_pass_sees_the_new_size():
    b, ops, ledger, _ = _open_bank(qty=1.0, filled=0.5, held=1.0)
    b.sync(_Dec(stop=3280.0), _Sig())
    b.sync(_Dec(stop=3280.0), _Sig())
    assert [a for a in ops.actions if a[0] == "partial"] == [("partial", 555, 0.5, "bullish")]


def test_a_config_that_banks_NOTHING_never_enters_the_path():
    """The shipped bot runs 0/0 — bank nothing, ride the runner. It must behave byte for byte as
    it did before this feature existed, and asking a strategy that never scales how much should
    be open would answer 'all of it' on every bar."""
    b, ops, ledger, _ = _open_bank(
        qty=1.0, filled=0.5, held=1.0, cfg=_banking_cfg(exec_tp1_pct=0.0)
    )
    b.sync(_Dec(stop=3280.0), _Sig())
    assert not any(a[0] == "partial" for a in ops.actions)


def test_a_broker_holding_LESS_than_expected_is_never_re_opened():
    """A disagreement about the book belongs to the halt machinery. Quietly buying size back
    here would be the bridge inventing a trade."""
    b, ops, _, _ = _open_bank(qty=1.0, filled=0.0, held=0.4)
    b.sync(_Dec(stop=3280.0), _Sig())
    assert not any(a[0] == "partial" for a in ops.actions)


def test_a_REFUSED_partial_is_alerted_and_recorded_rather_than_retried_silently():
    """`partial_close` refuses a size the broker cannot express (rule 17). The position stays
    over-sized — the safe half — but the two books now differ, so it must be SAID."""
    b, ops, ledger, notes = _open_bank(held=1.0, partial=False)
    b.sync(_Dec(stop=3280.0), _Sig())
    assert "event:partial_refused" in ledger.kinds()
    assert any("PARTIAL NOT BANKED" in str(m) for m in notes), notes
    assert ops.positions[0].volume == 1.0


def test_a_repeated_refusal_alerts_ONCE():
    """The identical problem re-offers itself on every 15m bar. An alert per bar is one nobody
    reads by the third."""
    b, ops, ledger, notes = _open_bank(held=1.0, partial=False)
    for _ in range(4):
        b.sync(_Dec(stop=3280.0), _Sig())
    assert len([m for m in notes if "PARTIAL NOT BANKED" in str(m)]) == 1
    assert len([k for k in ledger.kinds() if k == "event:partial_refused"]) == 4, (
        "the LOG and the ledger record every attempt; only the ALERT is latched"
    )


def test_an_UNKNOWN_partial_stops_rather_than_retrying():
    """Rule 1. A retry could bank twice, and 'I could not find out' is not 'it did not happen'."""
    b, ops, ledger, notes = _open_bank(held=1.0, partial=live_bridge.UNKNOWN)
    b.sync(_Dec(stop=3280.0), _Sig())
    assert "event:partial_unknown" in ledger.kinds()
    assert "event:partial_banked" not in ledger.kinds()
    assert ops.positions[0].volume == 1.0


def test_a_strategy_whose_size_CANNOT_be_read_banks_nothing():
    """`None` is not zero. Zero would mean bank the WHOLE position, which is a full exit — the
    single most destructive misreading available here."""
    ops = _FakeMt5Ops()
    ops.positions = [_Pos(555, 0, 3290.0, 1.0, 3280.0)]
    ex = _FakeExecution(pos_dir=1, qty=None, cfg=_banking_cfg())
    b, ops, ledger, notes = _bridge(ex, mt5ops=ops)
    b._contract_size = lambda: 1.0
    b.sync(_Dec(stop=3280.0), _Sig())
    assert not any(a[0] == "partial" for a in ops.actions)
    assert any("PARTIAL NOT BANKED" in str(m) for m in notes)


def test_the_intended_size_is_converted_from_UNITS_to_LOTS():
    """The emulator counts instrument UNITS and the broker takes LOTS. Getting this wrong is how
    a 54.82-lot order reached a $2,000 account."""
    b, ops, _, _ = _open_bank(qty=200.0, filled=100.0, held=1.5)
    b._contract_size = lambda: 100.0
    b.sync(_Dec(stop=3280.0), _Sig())
    # 100 units still wanted / 100 per lot = 1.00 lot; 1.50 held, so 0.50 comes off.
    assert ("partial", 555, 0.5, "bullish") in ops.actions
    # ⚠ The FIRST version of this test asserted a NO-OP (200/100 wanted against 1.0 held) and was
    # VACUOUS: unconverted, the bridge wants 100 lots against 1.5 held, the excess goes negative
    # and it banks nothing — the same observable answer. It survived the mutation that deletes
    # the division. A test whose two branches agree is describing neither.


def test_the_banked_record_says_it_filled_at_MARKET_not_at_the_rung():
    """A permanent divergence from the lab, which fills at the rung's own price. It is named on
    the record so a shadow diff attributes it rather than rediscovering it."""
    b, ops, ledger, _ = _open_bank(qty=1.0, filled=0.5, held=1.0)
    b.sync(_Dec(stop=3280.0), _Sig())
    payload = next(kw for kind, kw in ledger.rows if kind == "event:partial_banked")
    assert payload["fill"] == "market_on_bar_close"
    assert payload["held_before"] == 1.0 and payload["held_after"] == 0.5


# ── the halt latch ────────────────────────────────────────────────────────────
# 🔴 `begin_live` is NOT called once. Three paths in `runner.py` call it again on a bot that has
# been trading for weeks — a reconnect after a link outage, the bar-gap re-warm, and a settings
# change applied while flat — and every branch of it ASSIGNS the state. So a halted bot went back
# to placing orders on the next blip, and nothing re-halted it: both runner-side latches
# (`_fleet_halted`, `_account_mismatch_halted`) had already fired and return early forever.
#
# The account-identity case is the one that costs money. It halts BECAUSE the terminal is logged
# into an account this bot was not pointed at, and a reconnect put the bot straight back to
# trading that account. These tests are at the BRIDGE rather than at the three call sites for the
# same reason the guard is: a rule enforced at every caller is one the fourth caller has never
# heard of.
def test_a_halted_bridge_stays_halted_when_a_rewarm_calls_begin_live():
    b, _, _, _ = _bridge(_FakeExecution(pos_dir=0))
    b.halt("account mismatch — terminal is on 999")

    b.begin_live()

    assert b.state is live_bridge.BridgeState.HALTED


def test_a_RESTORED_position_does_not_lift_a_halt_either():
    """The restore branch returns FIRST and sets LIVE on its way out, so it is the one that
    would have resurrected a halted bot carrying an open trade — the worst of the three."""
    b, _, _, _ = _bridge(_FakeExecution(pos_dir=1))
    b._restored = True
    b.halt("fleet halt — kill switch")

    b.begin_live()

    assert b.state is live_bridge.BridgeState.HALTED


def test_a_warmup_position_does_not_lift_a_halt_either():
    """The third branch. Its answer is WARMING rather than LIVE, which places nothing today —
    but it is still the bridge leaving the state a human was told to restart it out of."""
    b, _, _, _ = _bridge(_FakeExecution(pos_dir=1))
    b.halt("emulator and broker disagree")

    b.begin_live()

    assert b.state is live_bridge.BridgeState.HALTED


def test_the_STATE_and_the_REASON_never_disagree():
    """⚠ Asserting the reason ALONE is vacuous — nothing ever cleared it, so that test passes
    against the very bug it names. The property worth pinning is the PAIR: a resurrected bridge
    read LIVE while still carrying the reason it had been halted for, and the Bots page renders
    both. A bot reporting live with a standing halt reason is the state nobody can act on."""
    b, _, _, _ = _bridge(_FakeExecution(pos_dir=0))
    b.halt("account mismatch — terminal is on 999")

    b.begin_live()

    assert (b.state is live_bridge.BridgeState.HALTED) == bool(b.halt_reason)
    assert b.halt_reason == "account mismatch — terminal is on 999"


def test_the_refusal_is_RECORDED_rather_than_silent():
    """Rule 1 in its ordinary form: *refused to resume* and *never asked* must not be the same
    thing in the record. Without this the only trace of a suppressed re-warm is the absence of a
    `went_live`, which is also what an ordinary healthy bar looks like."""
    b, _, ledger, _ = _bridge(_FakeExecution(pos_dir=0))
    b.halt("fleet halt — kill switch")

    b.begin_live()

    assert "event:begin_live_refused_while_halted" in ledger.kinds()


def test_a_HEALTHY_bridge_still_goes_live():
    """The other half, and it is the one that fails the always-refuse mutation. A guard that
    stops every bot going live is not a guard — it is an outage."""
    b, _, _, _ = _bridge(_FakeExecution(pos_dir=0))
    b.state = live_bridge.BridgeState.WARMING

    b.begin_live()

    assert b.state is live_bridge.BridgeState.LIVE


# ── the full-exit check sums ONE LADDER, never across trades ──────────────────
# 🔴 It summed everything the config banks, which made a PRIMARY at 40% and a GAP RE-ENTRY at
# 60% add up to a full exit that neither position performs — and the refusal then named two
# fields belonging to two trades that are never on the same rung. Live until 2026-09-02.
def test_a_primary_and_a_re_entry_are_DIFFERENT_positions_and_their_rungs_do_not_add():
    cfg = _shipped(
        exec_tp1_pct=40.0,
        exec_secondary=True,
        exec_sec_trigger="FVG in zone",
        exec_sec_tp1_pct=60.0,
    )

    assert live_bridge.full_exit_at_price(cfg) == []
    # Still refused, for the reason that is actually true of it — the missing second entry.
    with pytest.raises(live_bridge.UnsupportedStrategyConfig, match="SECOND bar stream"):
        live_bridge.assert_supported(cfg)


def test_the_refusal_names_only_the_ladder_that_reaches_ZERO():
    """Under the combined trigger the reclaim banks 100 and the gap banks 50. Only the reclaim
    takes a position to zero, and only it may be named — a message listing the gap sends the
    reader to change a setting that is already fine, and its trade is not the one refused."""
    cfg = _shipped(exec_secondary=True, exec_sec_trigger="FVG in zone + Reclaim Entry")

    with pytest.raises(live_bridge.UnsupportedStrategyConfig) as e:
        live_bridge.assert_supported(cfg)

    assert "exec_rec_tp1_pct" in str(e.value)
    assert "exec_sec_tp1_pct" not in str(e.value)


def test_two_rungs_on_ONE_ladder_DO_still_sum():
    """The other half, and it fails the mutation that gives every rung its own ladder. 50 + 50 on
    one position is a full exit — a check reading `== 100` on a single field waves it through."""
    with pytest.raises(live_bridge.UnsupportedStrategyConfig, match="exec_tp1_pct=50"):
        live_bridge.assert_supported(_shipped(exec_tp1_pct=50.0, exec_tp2_pct=50.0))


def test_the_shared_second_rung_appears_ONCE_across_the_ladders_that_share_it():
    """Every ladder ends on `exec_tp2_pct` — the second rung's size is the same field whatever
    the trade is. Listing it per ladder would report one setting three times as three problems."""
    cfg = _shipped(
        exec_tp2_pct=25.0,
        exec_secondary=True,
        exec_sec_trigger="FVG in zone + Reclaim Entry",
    )

    names = [name for name, _ in live_bridge.price_triggered_banks(cfg)]

    assert names.count("exec_tp2_pct") == 1


# ── closing a trade because a PERSON asked ────────────────────────────────────
# The strategy exits in its own book first (`execution.request_close` → a `-CMD` exit fill on
# that bar's decision). This is the other half: the broker still holds, and nothing else in this
# bridge can take a position off at market. Without it `_agrees` halts — correctly, because a
# position vanishing from one ledger and not the other is otherwise unexplainable.
def _cmd_fill(direction=1):
    return types.SimpleNamespace(
        kind="exit",
        order_id="L-CMD" if direction > 0 else "S-CMD",
        price=3300.0,
        qty=1.0,
        dir=direction,
    )


def _open_for_close(**kw):
    ops = _FakeMt5Ops(**kw)
    ops.positions = [_Pos(777, 0, 3290.0, 1.0, 3280.0)]
    ex = _FakeExecution(pos_dir=0)  # the strategy has ALREADY exited its own book
    b, ops, ledger, notes = _bridge(ex, mt5ops=ops)
    b._pos_ticket, b._pos_dir, b._pos_lots = 777, 1, 1.0
    b._pos_entry, b._pos_stop, b._pos_risk_usd = 3290.0, 3280.0, 100.0
    return b, ops, ledger, notes


def test_a_commanded_exit_closes_the_broker_position_at_market():
    b, ops, _, _ = _open_for_close()
    dec = _Dec(stop=3280.0)
    dec.fills = [_cmd_fill()]

    b.sync(dec, _Sig())

    assert ("close", 777, "bullish", "CMD") in ops.actions
    assert b.state is not live_bridge.BridgeState.HALTED


def test_an_ORDINARY_exit_never_triggers_a_market_close():
    """The control, and the one that matters most: every other exit reaches the broker as a
    stop that has already filled. A bridge closing at market on any flat emulator would turn
    each of those into a second, unasked-for order."""
    b, ops, _, _ = _open_for_close()
    dec = _Dec(stop=3280.0)
    dec.fills = [types.SimpleNamespace(kind="exit", order_id="L-RUN", price=3280.0, qty=1.0, dir=1)]

    b.sync(dec, _Sig())

    assert not any(a[0] == "close" for a in ops.actions)


def test_a_REFUSED_close_leaves_the_position_and_lets_the_bot_halt():
    """The two ledgers really have parted, so carrying on would compute every later decision
    against a trade that is still open. Retrying here would be a recovery tool repeating the
    fault it is recovering from."""
    b, ops, ledger, _ = _open_for_close()
    ops.close_result = False
    dec = _Dec(stop=3280.0)
    dec.fills = [_cmd_fill()]

    b.sync(dec, _Sig())

    assert ops.positions, "the position was reported closed when the broker refused"
    assert b.state is live_bridge.BridgeState.HALTED
    assert "event:commanded_close_failed" in ledger.kinds()


def test_a_DRY_RUN_asks_the_broker_for_nothing():
    b, ops, _, _ = _open_for_close()
    b.dry_run = True
    dec = _Dec(stop=3280.0)
    dec.fills = [_cmd_fill()]

    b.sync(dec, _Sig())

    assert not any(a[0] == "close" for a in ops.actions)


# ── the slot key ────────────────────────────────────────────────────────────
#
# Added 2026-09-02 with the move from side-keyed order state to intent-keyed. The three below
# pin the property that move exists for; every one names the mutation that reddens it.


def test_a_primary_limit_rests_in_the_primary_slot_and_leaves_the_reentry_slots_empty():
    """The primary must not occupy the re-entry's key, or the two collide on one side.

    MUTATION: pass `SECONDARY_LONG` from `sync` instead of `PRIMARY_LONG` and this goes red.
    """
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, _, _ = _bridge(ex)

    b.sync(_Dec(), _Sig())

    assert b._rest[live_bridge.PRIMARY_LONG] is not None
    assert b._rest[live_bridge.SECONDARY_LONG] is None
    assert b._rest[live_bridge.SECONDARY_SHORT] is None


def test_a_primary_and_a_reentry_can_rest_on_the_SAME_side_without_colliding():
    """🔴 The defect the slot key exists to prevent — and it bites through the ORPHAN SWEEP
    rather than through bookkeeping.

    Keyed by side alone, the second placement overwrites the first's record. `_observe_orphans`
    then cancels every resting order the bridge cannot account for, so the forgotten order is
    cancelled within a bar while the strategy still believes it is resting.

    MUTATION: collapse the key back to the side inside `_sync_slot` — add
    `slot = primary_slot(direction)` under its first line — and this goes red on the first
    assertion: the re-entry's placement MODIFIES the primary's resting order instead of adding
    its own, and one order reaches the broker where two were wanted.

    ⚠ Mutating `secondary_slot` does NOT redden this and was the first mutation tried: the test
    hands `_sync_slot` its slot directly, so that helper is never called here. A mutation has to
    sit on the path the test actually drives.
    """
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, _, _ = _bridge(ex)

    b.sync(_Dec(), _Sig())  # the primary's limit
    b._sync_slot(live_bridge.SECONDARY_LONG, _Pend(1, 3270.0, 42.0, 3260.0), _Sig())

    assert len(ops.orders) == 2, "the two intents did not both reach the broker"
    assert b._rest[live_bridge.PRIMARY_LONG].price == 3290.0
    assert b._rest[live_bridge.SECONDARY_LONG].price == 3270.0

    b._observe_orphans()

    assert len(ops.orders) == 2, "the sweep cancelled an order the bridge should have remembered"


def test_the_slot_is_never_recorded_under_the_ledgers_own_record_type_field():
    """`ledger._write` stamps every record with its own `kind`, so a payload key of that name
    fights it.

    🔴 MEASURED, not reasoned: writing the slot's intent as `kind=` killed six existing tests on
    the fake ledger's signature. The fake was right — production has the same reserved word one
    layer down, where it would have overwritten the record's type instead of raising.

    MUTATION: rename `intent=slot[0]` back to `kind=slot[0]` in `_place` and this goes red (it
    raises on the fake's signature before reaching the assertion, which is still red).
    """
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, _, ledger, _ = _bridge(ex)

    b.sync(_Dec(), _Sig())

    placed = [kw for k, kw in ledger.rows if k == "event:order_placed"]
    assert placed, "nothing was placed, so this proves nothing"
    for kw in placed:
        assert "kind" not in kw, "the payload collides with the record's own type field"
        assert kw["intent"] == "primary"


# ── the fill clock (G18 stage 2) ────────────────────────────────────────────
#
# `sync_fast` mirrors the RE-ENTRY onto the broker between 15-minute closes. The primary is
# still owned by `sync`, and the tests below are mostly about that line not being crossed.


class _FastBar:
    """A fill-clock bar, in the shape the fast feed hands out.

    ⚠ Its time field is `timestamp_ms`, NOT the `time_ms` the 15-minute signal uses. That
    difference is the whole reason the bridge adapts it instead of passing it through: every
    read in the booking path is a `getattr` with a default, so the raw bar would record a
    re-entry with no timestamp and nothing would fail.
    """

    def __init__(self, index=7, timestamp_ms=1_780_000_900_000):
        self.index = index
        self.timestamp_ms = timestamp_ms


def _fast_step(bar=None, arm=None, filled_dir=None, stopped_dir=None):
    return types.SimpleNamespace(
        bar=bar or _FastBar(),
        primaries=[],
        arm=arm,
        filled_dir=filled_dir,
        stopped_dir=stopped_dir,
    )


def test_the_reentry_gets_its_own_resting_limit_on_the_fill_clock():
    """The point of the stage: a second entry order, at its own price, with its own stop.

    MUTATION: have `sync_fast` return before the loop over the two secondary slots and this goes
    red with nothing at the broker.
    """
    ex = _FakeExecution(pend_sec=_Pend(1, 3270.0, 20.0, 3260.0))
    b, ops, _, _ = _bridge(ex)

    b.sync_fast(_fast_step())

    assert len(ops.orders) == 1
    assert b._rest[live_bridge.SECONDARY_LONG].price == 3270.0
    assert b._rest[live_bridge.PRIMARY_LONG] is None, "it took the primary's slot"


def test_the_fill_clock_does_not_touch_the_PRIMARYS_resting_orders():
    """The two clocks own different slots. A primary limit is priced off a 15-minute bar, so a
    fill-clock pass must leave it exactly where it is.

    MUTATION: offer `PRIMARY_LONG` from `sync_fast` alongside the secondary slots and this goes
    red — the primary's order is cancelled, because the fast pass has no primary intent to
    re-offer and a slot offered `None` is a slot whose order is cancelled.
    """
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    primary = b._rest[live_bridge.PRIMARY_LONG]
    assert primary is not None

    b.sync_fast(_fast_step())

    assert b._rest[live_bridge.PRIMARY_LONG] is primary
    assert len(ops.orders) == 1


def test_the_side_the_reentry_ABANDONED_has_its_order_cancelled():
    """The re-entry re-decides its limit every fast bar and can switch sides. Offering only the
    armed slot would leave the other side's order resting with nothing coming back to look at it.

    MUTATION: in `sync_fast`, loop over `(wanted,)` instead of both secondary slots and this goes
    red with two live orders on opposite sides.
    """
    ex = _FakeExecution(pend_sec=_Pend(1, 3270.0, 20.0, 3260.0))
    b, ops, _, _ = _bridge(ex)
    b.sync_fast(_fast_step())
    assert len(ops.orders) == 1

    ex._pend_sec = _Pend(-1, 3330.0, 20.0, 3340.0)  # it flips to the other side
    b.sync_fast(_fast_step())

    assert b._rest[live_bridge.SECONDARY_LONG] is None
    assert b._rest[live_bridge.SECONDARY_SHORT].price == 3330.0
    assert len(ops.orders) == 1, "the abandoned side was left resting at the broker"


def test_a_position_appearing_clears_every_other_resting_order_on_the_FILL_clock():
    """🔴 The safety half, and the reason this runs the whole cycle rather than just placing.

    The primary's limits are placed while the bot is FLAT — which is exactly when a re-entry can
    fill. Left until the next 15-minute close they are a second position waiting to happen, for
    up to fifteen minutes. Here the window is one fill-clock bar.

    MUTATION: drop the `_cancel_all_rest` call from `sync_fast` and this goes red with the
    primary's limit still live beside an open position.
    """
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    assert len(ops.orders) == 1, "no primary order to leave behind, so this proves nothing"

    # the re-entry fills at the broker, and the strategy is holding it
    ops.positions = [_Pos(4242, 0, 3270.0, 0.2, 3260.0)]
    ex._pos_dir = 1
    ex.entry_kind = "secondary"

    b.sync_fast(_fast_step(filled_dir=1))

    assert ops.orders == [], "a resting limit survived beside an open position"
    assert b._pos_intent == "secondary"


def test_a_HALTED_bridge_places_nothing_on_the_fill_clock_either():
    """The halt has to hold on both clocks or it is not a halt.

    MUTATION: change the state guard in `sync_fast` to `is BridgeState.HALTED` and this goes red
    with an order at the broker.
    """
    ex = _FakeExecution(pend_sec=_Pend(1, 3270.0, 20.0, 3260.0))
    b, ops, _, _ = _bridge(ex)
    b.halt("under test")

    b.sync_fast(_fast_step())

    assert ops.orders == []
    assert b._rest[live_bridge.SECONDARY_LONG] is None


def test_the_fill_clock_ratchets_a_RE_ENTRYS_stop_and_not_a_PRIMARYS():
    """A stop belongs to the clock that computes it. The strategy only writes a stop onto the
    15-minute decision while the open trade is a primary, so this path must be equally inert on
    a primary's — otherwise it writes a value the primary's own leg has not decided yet.

    MUTATION: the property is guarded TWICE and either guard alone holds it, so BOTH have to go
    to redden this — drop the intent check in `_fast_decision` (which is what makes the stop
    `None`) AND the one in `sync_fast` (which is what skips the call). Then the primary half goes
    red with `move_sl` sending the re-entry's number to the primary's ticket.

    ⚠ MEASURED: each guard was mutated alone first and NEITHER reddened it. That is the honest
    reading of a doubled guard, and it is worth stating rather than leaving the next person to
    weaken one of them, see this test still green, and conclude it was covered.
    """
    # a PRIMARY position: the fill clock must not move its stop
    ex = _FakeExecution(pos_dir=1, entry_kind="primary", current_stop=3285.0)
    b, ops, _, _ = _bridge(ex)
    ops.positions = [_Pos(555, 0, 3290.0, 0.42, 3280.0)]
    b.sync(_Dec(stop=3280.0), _Sig())
    moved_before = [a for a in ops.actions if a[0] == "move_sl"]

    b.sync_fast(_fast_step())

    assert [a for a in ops.actions if a[0] == "move_sl"] == moved_before

    # a RE-ENTRY position: the fill clock owns it
    ex2 = _FakeExecution(pos_dir=1, entry_kind="secondary", current_stop=3285.0)
    b2, ops2, _, _ = _bridge(ex2)
    ops2.positions = [_Pos(556, 0, 3290.0, 0.42, 3280.0)]
    b2.sync_fast(_fast_step())  # books the position
    b2.sync_fast(_fast_step())  # ...and ratchets it

    assert any(a[0] == "move_sl" for a in ops2.actions), "the re-entry's stop never ratcheted"


def test_a_strategy_that_cannot_report_its_stop_SAYS_SO():
    """🔴 Rule 1. Leaving the broker's stop alone happens to be the safe direction, but it is
    also exactly what a correctly ratcheting trade looks like from outside — so "cannot ask" and
    "nothing to move" must not be the same outcome.

    MUTATION: return a bare `_FastDec()` from `_fast_decision` without logging or recording, and
    this goes red: the bridge falls silent about a live trade whose stop it has stopped managing.
    """
    ex = _FakeExecution(pos_dir=1, entry_kind="secondary", current_stop=3285.0)
    b, ops, ledger, _ = _bridge(ex)
    ops.positions = [_Pos(557, 0, 3290.0, 0.42, 3280.0)]
    b.sync_fast(_fast_step())  # books it while the strategy can still answer

    del type(ex)._current_stop  # ...and now it cannot
    b.sync_fast(_fast_step())

    assert "event:secondary_stop_unreadable" in ledger.kinds()
