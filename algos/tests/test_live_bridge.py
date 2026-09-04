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
# 2026-07-31 (`instances/sos_fade_demo/config.json` → `_measured`).
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
        # ⚠ **WHICH LEG owns the restored trade comes back too, because production does that**
        # (`_entry_kind` is in the real `Execution._POSITION_FIELDS`, and `entry_kind` is the
        # public read of it). Leaving it out made this fake LESS capable than the thing it
        # stands for, in exactly the field a restart can get wrong — so a restored re-entry
        # would have looked like a primary here no matter what the bridge did with it, and the
        # test could not have failed. A double that cannot express the defect certifies it.
        if "_entry_kind" in snap:
            self.entry_kind = snap["_entry_kind"]


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


def _no_ladder_closes_fully(cfg) -> bool:
    """No single ladder takes its position to zero at a price.

    ⚠ This asserted `full_exit_at_price(cfg) == []` until 2026-09-02, when that function was
    DELETED rather than left behind: the bridge gained a full-exit path, so a check whose whole
    subject was "the bridge cannot do this" became a rule describing behaviour the code no longer
    has. The property these tests are really about is `bank_ladders` — that rungs are summed
    within ONE position's ladder and never across two — so they now say that directly.
    """
    return all(
        sum(pct for _name, pct in rungs) < 100.0 - 1e-9
        for _kind, rungs in live_bridge.bank_ladders(cfg)
    )


# ── configuration guards ──────────────────────────────────────────────────────
def test_a_partial_ladder_that_leaves_a_runner_is_SUPPORTED_since_the_bank_path_landed():
    """30 + 40 = 70, so 30% still rides out to the stop — and `_sync_partials` can reconcile the
    broker down to it. ⚠ This asserted a REFUSAL until 2026-09-01, and the refusal was right for
    as long as the bridge had no exit path at all."""
    cfg = types.SimpleNamespace(
        exec_tp1_pct=30.0, exec_tp2_pct=40.0, exec_secondary=False, fill_model="bar"
    )
    assert _no_ladder_closes_fully(cfg)
    live_bridge.assert_supported(cfg)  # no raise


def test_a_ladder_that_SUMS_to_the_whole_position_is_SUPPORTED_since_the_exit_path_landed():
    """50 + 50 reaches zero at a price, which the bridge can now execute.

    ⚠ **This asserted a REFUSAL until 2026-09-02, and the refusal was right for as long as every
    exit reached the broker as a stop move.** `_mirror_strategy_exit` is the path: the rung
    finalises the trade in the strategy's book and the bridge closes the broker's position to
    match. What made it possible is that a full bank leaves the strategy FLAT, which is what
    separates it from a partial — see `test_a_PARTIAL_target_is_left_to_the_banking_path`.
    """
    cfg = types.SimpleNamespace(
        exec_tp1_pct=50.0, exec_tp2_pct=50.0, exec_secondary=False, fill_model="bar"
    )
    live_bridge.assert_supported(cfg)  # no raise


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
#   - The two re-entry tests failed on the MESSAGE, not on the refusal — the old bridge already
#     refused that config for having no second feed. They were the weakest reds here, and worth
#     nothing if read as the first kind.
#     🔴 **AND THE MOMENT THEY WERE WRITTEN FOR HAS PASSED, WHICH IS WHY THEY NOW ASSERT NO
#     REFUSAL AT ALL (2026-09-02).** They were pinning that the banking reason would SURVIVE the
#     feed refusal being lifted. It was lifted, and the banking reason had gone too — so the
#     honest form of both is that the config starts. ⚠ Worth reading as a general warning about
#     this shape: a test that proves its point by catching SOME refusal is only as good as the
#     refusal it happens to catch, and it goes quietly meaningless the day that one is retired.
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


def test_the_short_hold_variant_is_SUPPORTED_since_the_exit_path_landed():
    """One boolean, and the whole position comes off at 2R. ⚠ Refused from 2026-09-01 to
    2026-09-02 — before that check existed the bot STARTED and would have ridden past a target
    its backtest closed at, which is the defect the refusal was written for. The bridge executes
    that exit now, so the refusal is gone rather than softened."""
    live_bridge.assert_supported(_shipped(exec_short_hold=True))  # no raise


def test_short_hold_REPLACES_the_shared_rung_rather_than_adding_to_it():
    """`_tp1_pct` reads one or the other, never both. Naming both would send the reader to set a
    field that is not being read."""
    banks = live_bridge.price_triggered_banks(_shipped(exec_short_hold=True, exec_tp1_pct=30.0))
    assert [name for name, _ in banks] == ["exec_sh_tp1_pct"]


def test_the_reclaim_re_entry_that_banks_its_WHOLE_position_now_STARTS():
    """`exec_rec_tp1_pct` is 100 — the whole position off at its target, no runner — and it is
    ALSO the setting that measured best for that trigger (+21.00R against +7.16R without). That
    made it the one refusal where the best configuration was the unsupported one, and it is the
    reason the full-exit path was built.

    ⚠ **THIS CONFIG WAS REFUSED TWICE OVER AND IS NOW ACCEPTED, so read what changed rather than
    the count.** Its 100% rung stopped being a refusal on 2026-09-02 when the bridge gained a
    full exit; the blanket second-feed refusal went the same day when the re-entry's own order
    path landed. ⚠ Nothing here has run against a broker — rule 9.

    MUTATION: put either refusal back in `assert_supported` and this goes red.
    """
    cfg = _shipped(exec_secondary=True)
    assert not _no_ladder_closes_fully(cfg), (
        "the reclaim's 100% is the whole point of this test — if it stops closing fully, this "
        "test has quietly become a different one"
    )
    live_bridge.assert_supported(cfg)  # no raise


def test_the_gap_re_entrys_half_bank_now_STARTS_too():
    """Its 50% leaves a runner, so the ordinary bank path serves it — no full exit involved. This
    is the shape the ARMED bot would run if the re-entry were switched on today.

    ⚠ It asserted the banking refusal until the bank path landed on 2026-09-01, then the
    second-feed refusal until that was lifted on 2026-09-02. Both reasons are gone; the config is
    unchanged."""
    cfg = _shipped(exec_secondary=True, exec_sec_trigger="FVG in zone")
    assert _no_ladder_closes_fully(cfg)
    live_bridge.assert_supported(cfg)  # no raise


def test_a_combined_trigger_names_BOTH_rungs():
    """'FVG in zone + Reclaim Entry' runs both halves, and they bank different percentages off
    different fields. A refusal naming one would be fixed by setting one and refused again."""
    banks = live_bridge.price_triggered_banks(
        _shipped(exec_secondary=True, exec_sec_trigger="FVG in zone + Reclaim Entry")
    )
    assert sorted(name for name, _ in banks) == ["exec_rec_tp1_pct", "exec_sec_tp1_pct"]


def test_a_re_entry_that_INHERITS_a_zero_rung_banks_NOTHING():
    """-1.0 means 'inherit the shared field', which is 0 here — so nothing comes off at a price
    and the whole position rides its stop. A rule that reported a bank here would send somebody
    to mirror a scale-out that never happens.

    ⚠ It leaned on the second-feed refusal to prove it "fell through" until 2026-09-02. That
    refusal is gone, so it now reads the banking rule's own answer, which is what it was always
    about."""
    cfg = _shipped(exec_secondary=True, exec_sec_trigger="FVG in zone", exec_sec_tp1_pct=-1.0)
    assert live_bridge.price_triggered_banks(cfg) == []
    live_bridge.assert_supported(cfg)  # no raise


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


# ── the trade record has to say WHICH LEG, and what the trade really risked ───
#
# 🔴 **NEITHER WAS RECORDED UNTIL 2026-09-02, and both were found by trying to write the audit
# that reads this file.** The re-entry went live the same day, and the one record meant to answer
# *what did this bot do* could not tell a re-entry from an ordinary trade, while the risk field
# it did carry stated the PRIMARY's percentage for a trade sized at half of it. ⚠ **The
# transferable part: a record is only as good as the question somebody actually puts to it. These
# fields had been "obviously fine" for as long as one leg existed.**


def _filled(ex, *, entry=3289.7, stop=3280.0, lots=0.42, ledger=None):
    """Drive one PRIMARY limit through to a broker fill and hand back the bridge and its ledger."""
    b, ops, led, notes = _bridge(ex, ledger=ledger)
    b.sync(_Dec(), _Sig())
    ops.positions = [_Pos(901, 0, entry, lots, stop)]
    ex._pos_dir, ex._pend_long, ex._pend_sec = 1, None, None
    return b, ops, led, notes


def test_the_trade_record_says_which_LEG_opened_it():
    """⚠ **The fill is driven through the RE-ENTRY's own order, not by labelling a primary one.**
    A first draft set the strategy's leg marker and placed the order on the primary path, and the
    record came back `primary` — CORRECTLY, because `_slot_that_filled` asks the ticket first and
    the ticket is the stronger evidence. A test that had "fixed" that would have broken the one
    thing standing between a mislabelled trade and a wrong audit.

    MUTATION: drop `intent` from either ledger call and this goes red. Without it a re-entry and
    a primary are the same row, and no audit of the re-entry can start.
    """
    ex = _FakeExecution(pend_sec=_Pend(1, 3270.0, 20.0, 3260.0), entry_kind="secondary")
    b, ops, ledger, _ = _bridge(ex)
    b.sync_fast(_fast_step())  # the re-entry's own limit goes out on the fill clock

    ops.positions = [_Pos(ops.orders[0].ticket, 0, 3270.0, 0.20, 3260.0)]  # ...it fills
    ex._pos_dir, ex._pend_sec = 1, None
    b.sync_fast(_fast_step())

    opened = [kw for k, kw in ledger.rows if k == "opened"][0]
    assert opened["intent"] == "secondary"

    ops.positions = []  # it closes
    ex._pos_dir = 0
    b.sync_fast(_fast_step())
    closed = [kw for k, kw in ledger.rows if k == "closed"][0]
    assert closed["intent"] == "secondary", "the two halves are separate lines; both must say"


def test_a_PRIMARY_still_records_itself_as_one():
    """⚠ Not decoration. A change that stamped every trade as a re-entry would pass the test
    above and mislabel every trade this bot has ever taken."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, _ops, ledger, _ = _filled(ex)
    b.sync(_Dec(stop=3280.0), _Sig())
    assert [kw for k, kw in ledger.rows if k == "opened"][0]["intent"] == "primary"


def test_the_recorded_risk_is_MEASURED_off_the_position_not_read_off_a_setting():
    """🔴 The defect this exists for: a re-entry sizes at a FRACTION of the primary's percentage,
    so the setting says 10 for a trade risking 5 — in the ledger and in the Telegram message.

    The measurement cannot be fooled that way: $9.70 to the stop on a $1,000 basis is 0.97%
    whatever any setting says, and it also catches a broker-adjusted stop and a partial fill.

    MUTATION: record `exec_risk_pct` as the realised figure and this goes red.
    """
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, _ops, ledger, _ = _filled(ex)
    b._account_balance = lambda: 10_000.0
    b.sync(_Dec(stop=3280.0), _Sig())

    opened = [kw for k, kw in ledger.rows if k == "opened"][0]
    # $9.70 an ounce to the stop x 0.42 lots x 100 ounces a lot = $407.40, which is 4.074% of
    # a $10,000 basis. ⚠ The contract size is the unit boundary here (rule 15) and getting it
    # wrong is a 100x error in the field an audit reads — the first draft of this line did
    # exactly that, and the code was right.
    assert opened["risk_usd"] == pytest.approx(407.40, rel=1e-6)
    assert opened["risk_pct_realised"] == pytest.approx(4.074, rel=1e-6)
    assert opened["risk_pct"] != opened["risk_pct_realised"], (
        "the setting and the measurement must stay separate fields — one says what was asked "
        "for, the other what the trade got"
    )


def test_an_UNREADABLE_balance_records_None_rather_than_a_number():
    """Rule 1. A percentage of an unknown basis is an unanswered question, not a small number,
    and this is the field an audit trusts — so it must never be invented.

    MUTATION: fall back to 0.0, or to the setting, and this goes red.
    """
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, _ops, ledger, _ = _filled(ex)
    b._account_balance = lambda: None  # the balance could not be read
    b.sync(_Dec(stop=3280.0), _Sig())

    opened = [kw for k, kw in ledger.rows if k == "opened"][0]
    assert opened["risk_pct_realised"] is None
    assert opened["risk_usd"] is not None, "the DOLLARS need no balance and must still be recorded"


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

    assert _no_ladder_closes_fully(cfg)
    # ⚠ And it STARTS. Until 2026-09-02 this line asserted the second-feed refusal instead, which
    # made the test pass for a reason unrelated to what it is named after — a summed 40 + 60 would
    # have refused it too, and nobody would have seen the difference.
    live_bridge.assert_supported(cfg)  # no raise


def test_each_TRIGGERS_rungs_are_grouped_as_their_own_ladder():
    """Under the combined trigger the reclaim banks 100 and the gap banks 50, and they belong to
    two different positions that are never on the same rung.

    ⚠ **This asserted the wording of a REFUSAL until 2026-09-02**, when the full-exit path made
    that refusal go away. The property underneath it did not go away — `price_triggered_banks`
    still derives what the bridge banks from `bank_ladders`, so the grouping has to stay right —
    so the test now says it directly instead of through a message that no longer exists.
    """
    cfg = _shipped(exec_secondary=True, exec_sec_trigger="FVG in zone + Reclaim Entry")

    ladders = dict(live_bridge.bank_ladders(cfg))
    totals = {kind: sum(pct for _n, pct in rungs) for kind, rungs in ladders.items()}

    assert len(ladders) >= 2, "the two triggers were folded into one ladder"
    assert any(t >= 100.0 for t in totals.values()), "the reclaim's full bank vanished"
    assert any(t < 100.0 for t in totals.values()), "the gap's runner vanished"


def test_two_rungs_on_ONE_ladder_belong_to_ONE_ladder():
    """The other half of the grouping, and it fails the mutation that gives every rung its own.
    Both rungs of one position's ladder are that position's, so they are reported together.

    ⚠ Also asserted through a refusal message until 2026-09-02. Same reason, same replacement.
    """
    ladders = live_bridge.bank_ladders(_shipped(exec_tp1_pct=50.0, exec_tp2_pct=50.0))
    primary = next(rungs for kind, rungs in ladders if kind == "the primary")

    assert sum(pct for _n, pct in primary) == 100.0
    assert len(primary) == 2


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


# ── the full exit at a price, and the hole it turned up (2026-09-02) ────────
#
# `_mirror_strategy_exit` generalises the commanded close to every exit leg the BROKER cannot
# execute for itself. Two of them were unreachable before: a target that takes the whole
# position, and the time stop — which was switched ON for the armed bot the whole time.


def _exit_fill(tag, direction=1, qty=1.0, price=3300.0):
    return types.SimpleNamespace(
        kind="exit",
        order_id=("L-" if direction > 0 else "S-") + tag,
        price=price,
        qty=qty,
        dir=direction,
    )


def test_a_TIME_STOP_exit_closes_the_broker_position():
    """🔴 A LIVE HOLE, not a new capability. The time stop is ON for the armed bot — 36 hours,
    before-breakeven only — and nothing mirrored it: the strategy would exit in its own book, the
    broker would keep the position, and the bridge would halt on the next bar with the trade
    still open and nobody managing its stop. Only the operator's own close was ever wired.

    MUTATION: drop "-TIME" from `BRIDGE_OWNED_EXITS` and this goes red with nothing closed.
    """
    b, ops, _, _ = _open_for_close()
    dec = _Dec(stop=3280.0)
    dec.fills = [_exit_fill("TIME")]

    b.sync(dec, _Sig())

    assert ("close", 777, "bullish", "TIME") in ops.actions
    assert b.state is not live_bridge.BridgeState.HALTED


def test_a_target_that_takes_the_WHOLE_position_closes_it_at_the_broker():
    """The full exit at a price. `_sync_partials` cannot express this: a rung taking the last of
    a position finalises the trade in the same step, so by the time the bridge looks there is no
    intended size left to reconcile towards — the strategy is simply flat.

    MUTATION: drop "-TP1" from `BRIDGE_OWNED_EXITS` and this goes red, which is the bot RIDING
    where the backtest CLOSED — the exact divergence the old refusal existed to prevent.
    """
    b, ops, _, _ = _open_for_close()
    dec = _Dec(stop=3280.0)
    dec.fills = [_exit_fill("TP1")]

    b.sync(dec, _Sig())

    assert ("close", 777, "bullish", "TP1") in ops.actions


def test_a_PARTIAL_target_is_left_to_the_banking_path():
    """🔴 THE DANGEROUS CASE, and the reason the flatness test exists rather than a tag test.

    A rung that banks 50% and rides the rest emits exactly the same `-TP1` exit fill as one that
    takes the lot. Acting on the tag alone would market-close the WHOLE position and delete a
    runner the strategy is still managing — turning a scale-out into a full exit, silently, on
    every partial.

    MUTATION: remove the `self._ex._pos_dir != 0` guard in `_mirror_strategy_exit` and this goes
    red with the runner closed.
    """
    ops = _FakeMt5Ops()
    ops.positions = [_Pos(777, 0, 3290.0, 1.0, 3280.0)]
    ex = _FakeExecution(pos_dir=1)  # the strategy is STILL HOLDING the runner
    b, ops, _, _ = _bridge(ex, mt5ops=ops)
    b._pos_ticket, b._pos_dir, b._pos_lots = 777, 1, 1.0
    b._pos_entry, b._pos_stop = 3290.0, 3280.0

    dec = _Dec(stop=3280.0)
    dec.fills = [_exit_fill("TP1", qty=0.5)]

    b.sync(dec, _Sig())

    assert not any(a[0] == "close" for a in ops.actions), "a scale-out was turned into a full exit"


def test_a_STOP_OUT_is_never_mirrored():
    """The control for the tag the allow-list deliberately omits. `execution._close_at` stamps an
    ordinary stop-out `L-CLOSE`, and the broker's own stop order has already filled it — closing
    at market here would be a second, unasked-for order against a position that is gone.

    ⚠ It is the SAME tag the opposite-structure force-close carries, which is why that
    configuration is refused at startup instead of guessed at.

    MUTATION: add "-CLOSE" to `BRIDGE_OWNED_EXITS` and this goes red.
    """
    b, ops, _, _ = _open_for_close()
    dec = _Dec(stop=3280.0)
    dec.fills = [_exit_fill("CLOSE")]

    b.sync(dec, _Sig())

    assert not any(a[0] == "close" for a in ops.actions)


def test_the_opposite_structure_close_is_REFUSED_rather_than_guessed_at():
    """Refusing is the answer (rule 17's shape, applied to an exit). The bridge cannot tell this
    exit from a stop-out, and either guess is wrong in a way nothing would report: mirroring
    market-closes on top of a filling stop, ignoring leaves the broker holding a trade the
    strategy has exited and halts the bot.

    MUTATION: delete the `exec_close_opp_sos` branch in `assert_supported` and this goes red.
    """
    with pytest.raises(live_bridge.UnsupportedStrategyConfig, match="SAME tag"):
        live_bridge.assert_supported(_shipped(exec_close_opp_sos=True))


# ── the lot ceiling, reconciled against the venue (2026-09-02) ─────────────────
#
# The CLAMP lives in the strategy's sizing seam (`backtest/portfolio/account.py`); all the bridge
# does is hold that ceiling at min(configured, what this broker accepts). Tests here cover only
# that reconciliation — the clamping itself is pinned in `backtest/tests/test_account.py`.
#
# ⚠ These use the REAL `SoloAccount`, not a stand-in with a `max_lots` attribute. A stub would
# accept any number this code wrote, including one the real object rejects, which is the
# fixture-more-capable-than-production trap the GOLD_SPEC note above already records.


class _ExWithAccount:
    """The one thing the bridge touches for this: the strategy's account seam."""

    def __init__(self, account):
        self._account = account


def _spec_with_max(volume_max):
    return SymbolSpec(
        symbol="XAUUSD",
        contract_size=100.0,
        tick_size=0.01,
        tick_value=1.0,
        volume_min=0.01,
        volume_max=volume_max,
        volume_step=0.01,
        digits=2,
    )


def _ceiling_bridge(configured=100.0):
    from backtest.portfolio.account import SoloAccount

    ex = _ExWithAccount(SoloAccount(balance=10_000.0, max_lots=configured))
    b, _, _, _ = _bridge(ex)
    return b, ex._account


def test_a_venue_maximum_BELOW_the_configured_ceiling_lowers_it():
    """The case the reconciliation exists for. A ceiling above what the broker takes is not a
    ceiling — the strategy would size to 100 and the order would be refused at 50.

    RED when `_reconcile_lot_ceiling` returns before assigning, or takes max() instead of min().
    """
    b, acct = _ceiling_bridge(configured=100.0)
    b._reconcile_lot_ceiling(_spec_with_max(50.0))
    assert acct.max_lots == 50.0


def test_a_venue_maximum_ABOVE_the_configured_ceiling_does_NOT_raise_it():
    """Aaron's rule, 2026-09-02: he does not want to trade more than his own ceiling whatever a
    broker permits. A venue offering 200 must not move it.

    RED when the min() becomes max(), or when the broker's figure is assigned unconditionally.
    """
    b, acct = _ceiling_bridge(configured=100.0)
    b._reconcile_lot_ceiling(_spec_with_max(200.0))
    assert acct.max_lots == 100.0


def test_an_UNREADABLE_venue_maximum_leaves_the_configured_ceiling_alone():
    """Rule 1 on this path. A terminal that has not said what the band is has not said the band
    is zero — and a zero ceiling refuses every order for the rest of the session.

    RED when the `broker_max <= 0` guard is dropped: the ceiling goes to 0.0 (or None, which
    switches the cap off entirely — the opposite error, equally silent).
    """
    for unreadable in (None, 0.0, -1.0):
        b, acct = _ceiling_bridge(configured=100.0)
        b._reconcile_lot_ceiling(_spec_with_max(unreadable))
        assert acct.max_lots == 100.0, unreadable


def test_the_ceiling_does_not_RATCHET_down_after_one_bad_read():
    """The startup-fact-that-drifts problem (rule 16) inverted: this runs per order, so a single
    wrong or missing volume band must not pin the ceiling low for the rest of the session.

    RED when the reconciliation reads `account.max_lots` as its base instead of remembering the
    CONFIGURED value — the ceiling then stays at 50 forever once it has been there.
    """
    b, acct = _ceiling_bridge(configured=100.0)
    b._reconcile_lot_ceiling(_spec_with_max(50.0))
    assert acct.max_lots == 50.0
    b._reconcile_lot_ceiling(_spec_with_max(100.0))  # the band reads correctly again
    assert acct.max_lots == 100.0, "one bad read pinned the ceiling low"


def test_a_strategy_with_no_ceiling_configured_is_left_switched_OFF():
    """`max_lots=None` is the parity anchor's escape hatch. The bridge must not switch a cap ON
    for a run that deliberately has none.

    RED when the `max_lots is None` early return is dropped — the broker's band becomes a
    ceiling nobody asked for.
    """
    from backtest.portfolio.account import SoloAccount

    ex = _ExWithAccount(SoloAccount(balance=10_000.0, max_lots=None))
    b, _, _, _ = _bridge(ex)
    b._reconcile_lot_ceiling(_spec_with_max(50.0))
    assert ex._account.max_lots is None


def test_an_execution_with_no_account_seam_does_not_raise():
    """A notifier convenience must never be able to stop a trading loop, and neither may this.

    RED when the `account is None` guard is dropped — AttributeError inside order planning.
    """

    class _NoAccount:
        pass

    b, _, _, _ = _bridge(_NoAccount())
    b._reconcile_lot_ceiling(_spec_with_max(50.0))  # must not raise


# ── the ACCOUNT room — sharing one balance across separate PROCESSES (2026-09-03) ──────
#
# Aaron: each bot gets a share of the account, and when one is occupying more than its share the
# others SHRINK to what is left rather than being refused; with nothing left they refuse and say
# why. The shrink itself is `SoloAccount.room()` inside the strategy's own sizing — all the
# bridge does is hand it the number, which is the same division of labour the venue lot ceiling
# uses and the only reason a live shrink is safe at all.
#
# ⚠ These use the REAL `SoloAccount` for the same reason the ceiling tests do: a stub accepts any
# number this code writes, including ones the real object rejects.
def _room_bridge(cap_pct=10.0, balance=10_000.0):
    from backtest.portfolio.account import SoloAccount

    ex = _ExWithAccount(SoloAccount(balance=balance))
    b, m, ledger, notes = _bridge(ex, account_risk_cap_pct=cap_pct)
    b._account_balance = lambda: balance
    return b, m, ledger, notes, ex._account


def _other_bot_lots(volume=0.5, entry=3300.0, stop=3290.0, ticket=9001):
    """A position under ANOTHER bot's magic, stated in LOTS — 0.5 lots on a $10 stop is $500.

    ⚠ **Deliberately NOT called `_other_bot`.** One already exists above taking RISK DOLLARS, and
    naming this the same shadowed it: `_other_bot(200.0)` silently became 200 LOTS — a $200,000
    position where the test meant $200 — and reddened a refusal test that had nothing to do with
    this work. Two helpers for one idea in one file is how that happens; the units are in the name
    now so a reader cannot pick the wrong one by accident.
    """
    from account_risk import Exposure

    return Exposure(
        ticket=ticket,
        symbol="XAUUSD",
        magic=424242,
        direction=1,
        volume=volume,
        entry=entry,
        stop=stop,
        resting=False,
    )


def test_an_EMPTY_account_leaves_this_bot_the_whole_cap():
    b, m, _, _, acct = _room_bridge()
    b.refresh_account_room()
    assert acct.external_room == 1_000.0  # 10% of $10,000


def test_ANOTHER_BOTS_position_takes_its_risk_out_of_this_bots_room():
    """The whole feature. $500 held elsewhere against a $1,000 cap leaves $500, and the strategy
    then sizes into that instead of being refused outright."""
    b, m, _, _, acct = _room_bridge()
    m.external = [_other_bot_lots(volume=0.5)]
    b.refresh_account_room()
    assert acct.external_room == 500.0


def test_a_FULL_account_leaves_no_room_at_all():
    b, m, _, _, acct = _room_bridge()
    m.external = [_other_bot_lots(volume=1.0)]  # $1,000 — the entire cap
    b.refresh_account_room()
    assert acct.external_room == 0.0


def test_an_OVERSPENT_account_reads_as_zero_room_not_a_negative_one():
    """A negative would sail through `min(desired, room)` as the smaller number and grant a
    negative size. It happens whenever the balance falls under an open position."""
    b, m, _, _, acct = _room_bridge()
    m.external = [_other_bot_lots(volume=2.0)]  # $2,000 against a $1,000 cap
    b.refresh_account_room()
    assert acct.external_room == 0.0


def test_an_UNREADABLE_account_leaves_NO_room_rather_than_all_of_it():
    """ "Cannot ask" is never "affordable". A budget that opens itself when the terminal wobbles
    is absent exactly when the account is least healthy."""
    b, m, _, _, acct = _room_bridge()
    m.exposure_readable = False
    b.refresh_account_room()
    assert acct.external_room == 0.0


def test_an_UNREADABLE_BALANCE_leaves_NO_room():
    """A cap is a fraction of something. With nothing to take a fraction OF, refuse."""
    b, m, _, _, acct = _room_bridge()
    b._account_balance = lambda: None
    b.refresh_account_room()
    assert acct.external_room == 0.0


def test_a_position_with_NO_STOP_leaves_no_room():
    """Its risk is UNBOUNDED, not absent — a hand trade left running is exactly that. Scoring it
    zero would let the one thing the cap exists to bound sit invisibly underneath it."""
    b, m, _, _, acct = _room_bridge()
    m.external = [_other_bot_lots(volume=0.5, stop=0.0)]
    b.refresh_account_room()
    assert acct.external_room == 0.0


def test_NO_CAP_configured_leaves_the_room_UNSET_rather_than_zero():
    """Rule 1. An uncapped bot is a supported state and must behave exactly as it always has —
    `None`, meaning infinite, never 0.0, which would refuse every trade it ever tried."""
    b, m, _, _, acct = _room_bridge(cap_pct=None)
    b.refresh_account_room()
    assert acct.external_room is None


def test_this_bots_OWN_RESTING_ORDER_does_not_eat_its_own_share():
    """🔴 Counted in BOTH places this would halve the bot's share whenever it had anything on.
    The broker read excludes our known tickets because the emulator's own `reserved()` already
    subtracts them inside `room()`.

    ⚠ **This drives the RESTING path specifically** — an earlier version set `_pos_ticket` and
    cleared `_rest`, so despite its name it only ever exercised the position exclusion and
    survived a mutation that emptied the resting one. The two lines are separate and each needs
    its own test.
    """
    from account_risk import Exposure

    b, m, _, _, acct = _room_bridge()
    b.refresh_account_room()
    empty = acct.external_room

    slot = next(iter(b._rest))
    b._rest[slot] = live_bridge._Rest(ticket=555, price=3300.0, lots=0.5, sl=3290.0)
    m.external = [
        Exposure(
            ticket=555,
            symbol="XAUUSD",
            magic=m.magic,
            direction=1,
            volume=0.5,
            entry=3300.0,
            stop=3290.0,
            resting=True,
        )
    ]
    b.refresh_account_room()
    assert acct.external_room == empty, "our own resting order must not spend our own share"


def test_this_bots_OWN_OPEN_POSITION_does_not_eat_its_own_share():
    """The other half, and it is a separate line in the exclusion — see the note above."""
    from account_risk import Exposure

    b, m, _, _, acct = _room_bridge()
    b.refresh_account_room()
    empty = acct.external_room

    b._pos_ticket = 777
    m.external = [
        Exposure(
            ticket=777,
            symbol="XAUUSD",
            magic=m.magic,
            direction=1,
            volume=0.5,
            entry=3300.0,
            stop=3290.0,
            resting=False,
        )
    ]
    b.refresh_account_room()
    assert acct.external_room == empty, "our own position must not spend our own share"


def test_something_under_our_magic_we_have_NO_RECORD_OF_is_COUNTED():
    """🔴 The 2026-08-25 premise, pinned. "Known" is the load-bearing word: excluding by MAGIC
    rather than by TICKET is what let five copies of one order read as an empty account. Anything
    under our magic we cannot account for must spend the budget like anybody else's."""
    from account_risk import Exposure

    b, m, _, _, acct = _room_bridge()
    m.external = [
        Exposure(
            ticket=31337,  # ours by magic, and we have no record of it
            symbol="XAUUSD",
            magic=m.magic,
            direction=1,
            volume=0.5,
            entry=3300.0,
            stop=3290.0,
            resting=False,
        )
    ]
    b.refresh_account_room()
    assert acct.external_room == 500.0, "an orphan under our own magic must still be counted"


def test_a_strategy_with_no_account_seam_is_left_alone():
    """A strategy that does not size through the account seam has no room to hand it, and must
    not crash the bar because of it."""

    class _NoAccount:
        pass

    b, _, _, _ = _bridge(_NoAccount(), account_risk_cap_pct=10.0)
    b.refresh_account_room()  # must not raise


def test_running_OUT_of_room_says_so_ONCE_and_the_RECOVERY_speaks(monkeypatch):
    """🔴 The recovery message is what makes the silence safe. Without it, quiet would mean
    either "there is room again" or "still full, not worth repeating", and the reader would have
    to go and look — which is the work the alert exists to save."""
    b, m, ledger, notes, _ = _room_bridge()

    m.external = [_other_bot_lots(volume=1.0)]
    b.refresh_account_room()
    b.refresh_account_room()  # still full — must NOT repeat itself
    exhausted = [n for n in notes if "NO ACCOUNT RISK LEFT" in n]
    assert len(exhausted) == 1, "an alarm that repeats hourly is one people scroll past"

    m.external = []
    b.refresh_account_room()
    back = [n for n in notes if "ACCOUNT RISK AVAILABLE" in n]
    assert len(back) == 1, "silence after an alarm must not be ambiguous"
    # ⚠ The fake records an event as "event:<name>" — asserted against its real shape rather
    # than the name alone, which counted 0 and passed nothing while both records were present.
    kinds = [k for k, _ in ledger.rows]
    assert kinds.count("event:account_room_exhausted") == 1
    assert kinds.count("event:account_room_restored") == 1
