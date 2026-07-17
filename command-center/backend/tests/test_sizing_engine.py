"""
Dynamic sizing & risk engine unit tests (services/sizing_engine).

Pure engine — builds RawTrades and ruleset dicts inline. Covers the locked model:
the bullet/consistent goal switch, room ÷ 7 sizing, the one-loss-can't-breach guard,
open-trade risk reservation (a running trade reserves its risk; the next signal is
shrunk or blocked), the contract ladder, the consistency throttle, daily halts, breach
detection, and the per-signal decision log the engine emits.

Reference: account 50,000; trailing max-loss 2,000 ⇒ start floor 48,000; room 2,000.
"""

from datetime import datetime

import pytest

from services.sizing_engine import (
    RawTrade, ContractLadder, run_engine, MODE_BULLET, MODE_CONSISTENT, MODE_MANUAL,
)


# ── Builders ──────────────────────────────────────────────────────────────────

def mk_trade(index, entry_px, exit_px, *, direction=1, stop_distance=5.0, pv=100.0,
             comm=0.0, day="2024-01-02", t_in="09:40", t_out="09:45", exit_reason=None):
    et = datetime.fromisoformat(f"{day}T{t_in}:00")
    xt = datetime.fromisoformat(f"{day}T{t_out}:00")
    return RawTrade(index=index, entry_time=et, exit_time=xt, direction=direction,
                    entry_price=entry_px, exit_price=exit_px, stop_distance=stop_distance,
                    point_value=pv, commission_per_side=comm, exit_reason=exit_reason)


def ruleset(**over):
    base = {
        "ruleset_type": "prop_eval", "account_size": 50000, "profit_target": 3000,
        "max_loss_eod": 2000, "mll_lock_balance": 50100, "consistency_pct": None,
        "daily_loss_cap": None, "risk_per_trade_pct": None, "daily_halt_fraction": None,
        "daily_profit_target": None, "max_drawdown_from_peak_pct": None,
        "max_contracts": {"mini_max": 4, "micro_max": 40, "scaling": None},
    }
    base.update(over)
    return base


def _dec(res, signal_id):
    return next(d for d in res.decisions if d["signal_id"] == str(signal_id))


# ── Per-contract economics & contract (unchanged) ─────────────────────────────

def test_net_per_contract_and_risk():
    t = mk_trade(1, 100, 110, pv=2.0, stop_distance=5.0, comm=0.5)
    assert t.gross_per_contract() == pytest.approx(20.0)
    assert t.net_per_contract() == pytest.approx(19.0)
    assert t.risk_per_contract() == pytest.approx(10.0)
    assert t.stop_price() == pytest.approx(95.0)   # long, 100 - 5


def test_from_record_parses_strings():
    t = RawTrade.from_record({
        "index": 7, "entry_time": "2024-03-01 14:30:00", "exit_time": "2024-03-01 15:00:00",
        "direction": "Short", "entry_price": 200, "exit_price": 190, "stop_distance": 4,
        "point_value": 5, "commission_per_side": 1.0, "exit_reason": "Target",
    })
    assert t.direction == -1
    assert t.gross_per_contract() == pytest.approx(50.0)
    assert t.day == "2024-03-01"


def test_ladder_bidirectional_band():
    lad = ContractLadder({"scaling": {"mode": "bidirectional_band", "bands": [
        {"profit_min": 0, "profit_max": 999, "mini": 2, "micro": 20},
        {"profit_min": 1000, "profit_max": 1999, "mini": 3, "micro": 30},
        {"profit_min": 2000, "profit_max": None, "mini": 4, "micro": 40}]}}, is_micro=True)
    assert lad.cap_at(0) == 20 and lad.cap_at(1500) == 30 and lad.cap_at(5000) == 40


def test_ladder_cumulative_ratchet():
    lad = ContractLadder({"scaling": {"mode": "cumulative_ratchet",
        "start": {"mini": 2, "micro": 20},
        "tiers": [{"profit_trigger": 1500, "mini": 3, "micro": 30},
                  {"profit_trigger": 2000, "mini": 4, "micro": 40}]}}, is_micro=False)
    assert lad.cap_at(0) == 2 and lad.cap_at(1600) == 3 and lad.cap_at(2500) == 4


# ── Goal switch: consistent vs bullet ─────────────────────────────────────────

def test_consistent_sizes_room_div_7():
    # room 2000 ÷ 7 = 285.7 budget; risk/contract 10 → 28 contracts.
    t = mk_trade(1, 100, 105, pv=2.0, stop_distance=5.0)
    res = run_engine([t], ruleset(), is_micro=True, mode=MODE_CONSISTENT)
    assert _dec(res, 1)["sizing"]["contracts"] == 28
    assert _dec(res, 1)["sizing"]["bound_by"] == "room_div7"


def test_bullet_takes_max_the_rules_allow():
    # bullet → min(ladder 40, drawdown 200) = 40 (the ladder cap).
    t = mk_trade(1, 100, 105, pv=2.0, stop_distance=5.0)
    res = run_engine([t], ruleset(), is_micro=True, mode=MODE_BULLET)
    assert _dec(res, 1)["sizing"]["contracts"] == 40
    assert _dec(res, 1)["sizing"]["bound_by"] == "contract_ladder"


def test_bullet_one_loss_cannot_oversize_past_room():
    # Big risk/contract → the drawdown/room ceiling, not the ladder, caps the bullet.
    # room 2000 / (250×2=500) = 4 contracts.
    t = mk_trade(1, 100, 101, pv=2.0, stop_distance=250.0)
    res = run_engine([t], ruleset(), is_micro=True, mode=MODE_BULLET)
    assert _dec(res, 1)["sizing"]["contracts"] == 4
    assert _dec(res, 1)["sizing"]["bound_by"] == "drawdown_clamp"


def test_consistent_uses_peak_floor_for_personal():
    # personal: no trailing floor, 15%-from-peak instead → floor 8500, room 1500.
    # 1500 ÷ 7 = 214 budget; risk/contract 10 → 21 contracts.
    rs = ruleset(ruleset_type="personal", account_size=10000, max_loss_eod=0,
                 mll_lock_balance=None, max_drawdown_from_peak_pct=15, max_contracts=None,
                 profit_target=0)
    t = mk_trade(1, 100, 105, pv=2.0, stop_distance=5.0)
    res = run_engine([t], rs, is_micro=True, mode=MODE_CONSISTENT)
    assert _dec(res, 1)["sizing"]["contracts"] == 21


# ── Open-trade risk reservation ───────────────────────────────────────────────

def test_open_trade_shrinks_the_next_trade():
    # A is open (reserves 28×10=280) when B fires → B sizes off 2000-280 = 1720 ÷ 7.
    a = mk_trade(1, 100, 105, pv=2.0, stop_distance=5.0, t_in="09:40", t_out="11:00")
    b = mk_trade(2, 100, 105, pv=2.0, stop_distance=5.0, t_in="09:50", t_out="10:00")
    res = run_engine([a, b], ruleset(max_contracts=None), is_micro=True, mode=MODE_CONSISTENT)
    assert _dec(res, 1)["sizing"]["contracts"] == 28          # full room
    assert _dec(res, 2)["sizing"]["contracts"] == 24          # 1720 ÷ 7 ÷ 10


def test_open_trade_blocks_when_no_room_left():
    # A (bullet, big risk) reserves all 2000 of room → B is blocked, not sized.
    a = mk_trade(1, 100, 101, pv=2.0, stop_distance=250.0, t_in="09:40", t_out="11:00")
    b = mk_trade(2, 100, 101, pv=2.0, stop_distance=250.0, t_in="09:50", t_out="10:00")
    res = run_engine([a, b], ruleset(max_contracts=None), is_micro=True, mode=MODE_BULLET)
    db = _dec(res, 2)
    assert db["outcome"] == "blocked"
    assert any(g["gate"] == "insufficient_room" and not g["passed"] for g in db["gates"])
    assert res.blocked_trades == 1


# ── Contract ladder & consistency ─────────────────────────────────────────────

def test_consistency_throttle_caps_winning_day():
    # consistency 50% × target 3000 = 1500/day; winner nets 20/contract → cap 75.
    rs = ruleset(max_loss_eod=20000, mll_lock_balance=None, consistency_pct=50,
                 profit_target=3000, max_contracts=None)
    t1 = mk_trade(1, 100, 110, pv=2.0, stop_distance=1.0, t_in="09:40", t_out="09:45")
    t2 = mk_trade(2, 100, 110, pv=2.0, stop_distance=1.0, t_in="09:50", t_out="09:55")
    res = run_engine([t1, t2], rs, is_micro=True, mode=MODE_CONSISTENT)
    assert _dec(res, 1)["sizing"]["contracts"] == 75
    assert _dec(res, 1)["sizing"]["bound_by"] == "consistency_throttle"
    assert _dec(res, 2)["outcome"] == "skipped"               # day's allowance spent


# ── Minimum size (round up to 1, but only when 1 fits the room) ───────────────

def test_rounds_up_to_one_when_soft_target_shrinks_below_min():
    # room 2000, risk/contract 1500: room÷7 budget (≈0.19) is below 1, but 1 micro's
    # risk (1500) fits the room → round up to 1.
    t = mk_trade(1, 100, 101, pv=100.0, stop_distance=15.0)
    res = run_engine([t], ruleset(), is_micro=True, mode=MODE_CONSISTENT)
    assert _dec(res, 1)["sizing"]["contracts"] == 1
    assert _dec(res, 1)["sizing"]["bound_by"] == "min_size"


def test_skips_when_one_micro_will_not_fit_the_room():
    # risk/contract 2500 > room 2000 → even 1 micro would breach → skip, no round-up.
    t = mk_trade(1, 100, 101, pv=100.0, stop_distance=25.0)
    res = run_engine([t], ruleset(), is_micro=True, mode=MODE_BULLET)
    d = _dec(res, 1)
    assert d["outcome"] == "skipped"
    assert d["sizing"]["contracts"] == 0
    assert d["sizing"]["bound_by"] == "drawdown_clamp"


# ── Halts ─────────────────────────────────────────────────────────────────────

def test_daily_loss_halt_blocks_rest_of_day():
    rs = ruleset(max_loss_eod=20000, mll_lock_balance=None, daily_loss_cap=1000,
                 daily_halt_fraction=0.5, max_contracts={"micro_max": 1, "scaling": None})
    t1 = mk_trade(1, 100, 95, pv=200.0, stop_distance=5.0, t_in="09:40", t_out="09:45")  # -1000
    t2 = mk_trade(2, 100, 105, pv=200.0, stop_distance=5.0, t_in="09:50", t_out="09:55")
    res = run_engine([t1, t2], rs, is_micro=True, mode=MODE_BULLET)
    assert res.timeline[0].halt_reason == "daily_loss"
    assert _dec(res, 2)["outcome"] == "blocked"


def test_profit_target_halt_blocks_rest_of_day():
    rs = ruleset(max_loss_eod=20000, mll_lock_balance=None, daily_profit_target=1000,
                 max_contracts={"micro_max": 1, "scaling": None})
    t1 = mk_trade(1, 100, 105, pv=200.0, stop_distance=5.0, t_in="09:40", t_out="09:45")  # +1000
    t2 = mk_trade(2, 100, 105, pv=200.0, stop_distance=5.0, t_in="09:50", t_out="09:55")
    res = run_engine([t1, t2], rs, is_micro=True, mode=MODE_BULLET)
    assert res.timeline[0].halt_reason == "profit_target"
    assert _dec(res, 2)["outcome"] == "blocked"


# ── Breach ────────────────────────────────────────────────────────────────────

def test_trailing_floor_breach_flagged():
    # Stop overrun: realized loss (10 pts) exceeds the stop (5 pts) → 4 contracts still
    # punch through the 48,000 floor.
    t = mk_trade(1, 100, 90, pv=100.0, stop_distance=5.0)
    res = run_engine([t], ruleset(max_contracts={"micro_max": 9999, "scaling": None}),
                     is_micro=True, mode=MODE_BULLET)
    assert res.final_balance == 46000
    assert res.breach_day == "2024-01-02"
    assert res.breach_reason == "trailing_max_loss"


# ── Decision log emission ─────────────────────────────────────────────────────

def test_emits_full_decision_per_signal():
    t = mk_trade(1, 100, 110, pv=2.0, stop_distance=5.0, exit_reason="ORB_Long Profit target")
    res = run_engine([t], ruleset(), is_micro=True, mode=MODE_CONSISTENT,
                     instrument="MNQ", strategy="ORB", account_id="run123")
    assert len(res.decisions) == 1
    d = res.decisions[0]
    assert d["outcome"] == "taken"
    assert d["instrument"] == "MNQ" and d["strategy"] == "ORB"
    assert d["entry"]["stop"] == pytest.approx(95.0)
    assert d["exit"]["reason"] == "target"
    assert d["account_snapshot"]["available_room"] == 2000.0


# ── Output shape / ordering / validation ──────────────────────────────────────

def test_daily_pnl_and_net_match():
    t1 = mk_trade(1, 100, 110, pv=2.0, stop_distance=5.0, day="2024-01-02")
    t2 = mk_trade(2, 100, 95, pv=2.0, stop_distance=5.0, day="2024-01-03")
    res = run_engine([t1, t2], ruleset(), is_micro=True, mode=MODE_CONSISTENT)
    assert [d["date"] for d in res.daily_pnl] == ["2024-01-02", "2024-01-03"]
    assert len(res.timeline) == 2
    assert res.net_pnl == pytest.approx(sum(d["pnl"] for d in res.daily_pnl))


def test_trades_processed_in_day_order():
    late = mk_trade(2, 100, 110, pv=2.0, stop_distance=5.0, day="2024-01-05")
    early = mk_trade(1, 100, 110, pv=2.0, stop_distance=5.0, day="2024-01-02")
    res = run_engine([late, early], ruleset(), is_micro=True, mode=MODE_CONSISTENT)
    assert [d["date"] for d in res.daily_pnl] == ["2024-01-02", "2024-01-05"]


def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        run_engine([], ruleset(), is_micro=True, mode="turbo")


# ── Manual mode ───────────────────────────────────────────────────────────────
# You set the risk % and it does not move. The account's HARD caps still clamp it —
# manual is a request, not a licence to breach the floor or the ladder.

def test_manual_risks_exactly_the_pct_of_balance():
    """5% of a 50,000 balance = 2,500 budget; 500 risk/contract ⇒ 5 contracts.
    Not room÷7 (2000/7=285 ⇒ 0), not bullet (ladder max 4) — manual's own number."""
    t = mk_trade(1, 5000, 5010, stop_distance=5.0, pv=100.0)
    rs = ruleset(max_loss_eod=None, max_contracts=None)   # no floor, no ladder ⇒ no clamps
    res = run_engine([t], rs, is_micro=False, mode=MODE_MANUAL, manual_risk_pct=5.0)
    assert res.sized_trades[0].contracts == 5
    assert res.sized_trades[0].bound_by == "manual_pct"


def test_manual_compounds_with_the_balance():
    """"5% per trade" means 5% of the balance AT THAT TRADE, so a win grows the next size."""
    a = mk_trade(1, 5000, 5100, stop_distance=5.0, pv=100.0, day="2024-01-02")
    b = mk_trade(2, 5000, 5010, stop_distance=5.0, pv=100.0, day="2024-01-03")
    rs = ruleset(max_loss_eod=None, max_contracts=None)
    res = run_engine([a, b], rs, is_micro=False, mode=MODE_MANUAL, manual_risk_pct=5.0)
    # Trade 1: 5% of 50,000 = 2,500 ⇒ 5 contracts, +100pts x 100 x 5 = +50,000 ⇒ balance 100,000.
    # Trade 2: 5% of 100,000 = 5,000 ⇒ 10 contracts.
    assert res.sized_trades[0].contracts == 5
    assert res.sized_trades[1].contracts == 10


def test_manual_still_obeys_the_hard_drawdown_clamp():
    """A big manual % cannot punch through the room to the floor — one stop must not breach."""
    t = mk_trade(1, 5000, 5010, stop_distance=5.0, pv=100.0)
    # room = 2,000 ⇒ at 500/contract the hard clamp is 4 contracts, below manual's 5.
    res = run_engine([t], ruleset(max_contracts=None), is_micro=False,
                     mode=MODE_MANUAL, manual_risk_pct=5.0)
    assert res.sized_trades[0].contracts == 4
    assert res.sized_trades[0].bound_by == "drawdown_clamp"


def test_manual_still_obeys_the_contract_ladder():
    t = mk_trade(1, 5000, 5010, stop_distance=5.0, pv=100.0)
    res = run_engine([t], ruleset(max_loss_eod=None), is_micro=False,
                     mode=MODE_MANUAL, manual_risk_pct=50.0)
    assert res.sized_trades[0].contracts == 4          # mini_max
    assert res.sized_trades[0].bound_by == "contract_ladder"


def test_manual_without_a_pct_is_refused():
    """Silently falling back to some other size would misreport what the run did."""
    t = mk_trade(1, 5000, 5010)
    for bad in (None, 0):
        with pytest.raises(ValueError, match="manual_risk_pct"):
            run_engine([t], ruleset(), is_micro=False, mode=MODE_MANUAL, manual_risk_pct=bad)


def test_unknown_mode_is_refused():
    t = mk_trade(1, 5000, 5010)
    with pytest.raises(ValueError, match="mode must be"):
        run_engine([t], ruleset(), is_micro=False, mode="yolo")


# ── The "Unconstrained (No Limits)" ruleset ──────────────────────────────────

def test_unconstrained_ruleset_has_no_limits(fresh_db):
    """The seeded row's whole purpose is that nothing clamps. If a limit ever gets added to
    it, manual sizing silently stops meaning what it says — so assert each one is absent."""
    from services import lab_db
    rs = lab_db.get_ruleset("unconstrained")
    assert rs is not None, "the unconstrained ruleset must be seeded"
    assert not rs["max_loss_eod"]                       # no trailing floor
    assert rs["max_drawdown_from_peak_pct"] is None     # no peak floor
    assert rs["daily_loss_cap"] is None                 # no daily halt
    assert rs["daily_profit_target"] is None            # no profit halt
    assert not rs["profit_target"]                      # no target
    assert rs["consistency_pct"] is None                # no throttle
    assert rs["max_contracts"] is None                  # no ladder


def test_unconstrained_plus_manual_means_exactly_that_pct(fresh_db):
    """The pairing the UI recommends: no clamps, so the manual % binds and nothing else does."""
    from services import lab_db
    rs = lab_db.get_ruleset("unconstrained")
    t = mk_trade(1, 2000, 2010, stop_distance=5.0, pv=100.0)
    # 5% of 10,000 = 500 budget; 5.0 x 100 = 500/contract ⇒ exactly 1.
    res = run_engine([t], rs, is_micro=False, mode=MODE_MANUAL, manual_risk_pct=5.0)
    assert res.sized_trades[0].contracts == 1
    assert res.sized_trades[0].bound_by == "manual_pct"   # nothing else bound it
    assert res.breach_day is None                         # nothing to breach
