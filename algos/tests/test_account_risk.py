"""Account-level risk cap — the arithmetic and, mostly, the refusals.

Weighted toward the ways this can wrongly say "there is room", because that is the silent
direction: a cap that under-counts lets a second bot double the book and nothing anywhere reports
it, while a cap that over-counts refuses a setup loudly and somebody notices the same day.

Offline: `account_risk.py` imports no MT5 and does no I/O, which is the point of it being pure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[1] / "shared"
_LIVE = Path(__file__).resolve().parents[1] / "live"
for _p in (_SHARED, _LIVE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from account_risk import (  # noqa: E402
    AccountRisk, Exposure, RiskUnmeasurable, check_account_cap, measure_exposure,
)
from order_sizing import SymbolSpec  # noqa: E402


def _gold(symbol="XAUUSD.s") -> SymbolSpec:
    """PU Prime's gold, as measured off the live terminal 2026-08-06."""
    return SymbolSpec(symbol=symbol, contract_size=100.0, tick_size=0.01, tick_value=1.00,
                      volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=2)


def _yen() -> SymbolSpec:
    """A JPY pair — the instrument where a gold-shaped assumption is wrong by ~150x."""
    return SymbolSpec(symbol="USDJPY", contract_size=100_000.0, tick_size=0.001, tick_value=0.67,
                      volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=3)


def _pos(ticket=1, entry=3300.0, stop=3290.0, volume=0.25, magic=770115, symbol="XAUUSD.s",
         resting=False, direction=1):
    return Exposure(ticket=ticket, symbol=symbol, magic=magic, direction=direction,
                    volume=volume, entry=entry, stop=stop, resting=resting)


# ── the arithmetic ────────────────────────────────────────────────────────────────────
def test_open_risk_is_the_distance_to_the_CURRENT_stop_in_account_currency():
    """$10 of stop distance, 0.25 lots, $1.00 per 0.01 of price per lot = $250.

    The basis is the CURRENT broker-side stop, not the entry stop — which is what makes this the
    same reservation `backtest/portfolio/account.py` computes, and what makes a stop moved to
    breakeven release its room here exactly as it does there.
    """
    risk = measure_exposure([_pos()], _gold())
    assert risk.total_ccy == 250.0
    assert risk.positions == 1 and risk.resting == 0


def test_a_stop_at_breakeven_releases_its_room():
    """The property the whole cap rests on. A stop AT the entry is zero distance and zero risk."""
    assert measure_exposure([_pos(stop=3300.0)], _gold()).total_ccy == 0.0


def test_a_stop_RATCHETED_INTO_PROFIT_reserves_NOTHING():
    """This test found a real defect: the first version of `measure_exposure` used `abs()` and
    had no direction at all, so a long whose stop had climbed ABOVE its entry scored the LOCKED-IN
    PROFIT as risk — and grew it as the runner ran. A winning trade would have held the budget
    shut against the other bot for as long as it kept winning."""
    assert measure_exposure([_pos(stop=3320.0)], _gold()).total_ccy == 0.0
    # ...and the mirror, so the sign convention is pinned on both sides.
    assert measure_exposure([_pos(direction=-1, entry=3300.0, stop=3280.0)],
                            _gold()).total_ccy == 0.0
    assert measure_exposure([_pos(direction=-1, entry=3300.0, stop=3310.0)],
                            _gold()).total_ccy == 250.0


def test_two_bots_are_totalled_and_reported_per_magic():
    risk = measure_exposure([_pos(ticket=1, magic=770115),
                             _pos(ticket=2, magic=880220, volume=0.10)], _gold())
    assert risk.total_ccy == 350.0
    assert risk.per_magic == {770115: 250.0, 880220: 100.0}


def test_a_resting_order_counts_and_is_reported_separately():
    """A resting limit holds budget live, deliberately. There is no scheduler serialising two
    bots, so two limits can fill on the same tick with neither having seen the other — and a cap
    a race can walk through is not a cap. It diverges from the backtest, which reserves at fill."""
    risk = measure_exposure([_pos(ticket=1), _pos(ticket=2, resting=True, volume=0.10)], _gold())
    assert risk.total_ccy == 350.0
    assert (risk.positions, risk.resting) == (1, 1)


def test_the_arithmetic_is_instrument_agnostic():
    """0.5 of a yen (500 ticks of 0.001) on 1.0 lot at $0.67 per tick = $335. Nothing gold-shaped
    survives contact with this: the tick VALUE carries the contract size and the currency."""
    risk = measure_exposure(
        [_pos(symbol="USDJPY", entry=150.000, stop=149.500, volume=1.0)], _yen())
    assert risk.total_ccy == 335.0


# ── the refusals ──────────────────────────────────────────────────────────────────────
def test_a_position_with_NO_stop_refuses_rather_than_scoring_zero():
    """The load-bearing one. A position with no broker stop has UNBOUNDED risk, and the falsy
    value it arrives as is the same shape as 'no risk'. Scoring it zero would let a hand trade
    with an open-ended loss sit invisibly under the cap that exists to bound exactly that."""
    with pytest.raises(RiskUnmeasurable) as e:
        measure_exposure([_pos(ticket=9, stop=0.0, magic=0)], _gold())
    assert "NO broker-side stop" in str(e.value)
    assert "9" in str(e.value) and "unbounded" in str(e.value)


def test_a_resting_order_with_no_stop_refuses_too():
    with pytest.raises(RiskUnmeasurable) as e:
        measure_exposure([_pos(ticket=4, stop=None, resting=True)], _gold())
    assert "order 4" in str(e.value)


def test_a_spec_the_broker_could_not_price_refuses():
    """`tick_value = 0` is what an unselected symbol or a still-loading terminal returns. There is
    no safe stand-in for 'the broker did not say what this is worth'."""
    dead = SymbolSpec(symbol="XAUUSD.s", contract_size=100.0, tick_size=0.01, tick_value=0.0,
                      volume_min=0.01, volume_max=100.0, volume_step=0.01)
    with pytest.raises(RiskUnmeasurable) as e:
        measure_exposure([_pos()], dead)
    assert "worth" in str(e.value)


def test_a_position_on_a_DIFFERENT_symbol_refuses_rather_than_being_priced_wrong():
    """One instrument's tick value applied to another's position is a factor-of-150 error on a
    JPY pair, and it would produce a confident, plausible, wrong total."""
    with pytest.raises(RiskUnmeasurable) as e:
        measure_exposure([_pos(symbol="EURUSD")], _gold())
    assert "EURUSD" in str(e.value) and "XAUUSD.s" in str(e.value)


# ── the cap ───────────────────────────────────────────────────────────────────────────
def _risk(total, per_magic=None, positions=1, resting=0):
    return AccountRisk(total_ccy=total, positions=positions, resting=resting,
                       per_magic=per_magic or {})


def test_an_order_that_fits_is_allowed():
    v = check_account_cap(new_order_risk_ccy=100.0, open_risk=_risk(50.0),
                          balance=2000.0, cap_pct=10.0)
    assert v.allowed
    assert (v.cap_ccy, v.room_ccy) == (200.0, 150.0)


def test_the_second_bot_is_REFUSED_when_the_first_holds_the_budget():
    """Aaron's requirement in one test: one bot has the account's risk on, the other wants in,
    and the system blocks it."""
    v = check_account_cap(new_order_risk_ccy=200.0,
                          open_risk=_risk(200.0, {770115: 200.0}), balance=2000.0, cap_pct=10.0)
    assert not v.allowed
    assert v.code == "account_risk_cap"
    assert "770115" in v.detail and "$0.00 is left" in v.detail


def test_an_order_exactly_filling_the_remaining_room_is_ALLOWED():
    """The boundary is inclusive. `>` not `>=`, so a cap of exactly 10% admits an order of
    exactly 10% — otherwise a single bot at exec_risk_pct 10 under a 10% cap trades nothing."""
    v = check_account_cap(new_order_risk_ccy=200.0, open_risk=_risk(0.0, positions=0),
                          balance=2000.0, cap_pct=10.0)
    assert v.allowed


def test_no_cap_configured_is_a_supported_state_and_says_so():
    """A single bot needs no cap, and inventing one would change a live bot's behaviour with no
    measurement behind it. The caller is expected to report the state at startup."""
    v = check_account_cap(new_order_risk_ccy=1e9, open_risk=_risk(0.0), balance=2000.0,
                          cap_pct=None)
    assert v.allowed and v.code == "no_cap"


def test_an_unreadable_balance_REFUSES_and_never_reads_as_affordable():
    """'Cannot ask' is never 'affordable' — the mt5_link three-state rule applied to money."""
    v = check_account_cap(new_order_risk_ccy=10.0, open_risk=_risk(0.0), balance=None,
                          cap_pct=10.0)
    assert not v.allowed and v.code == "balance_unreadable"


def test_a_zero_or_negative_cap_refuses_LOUDLY_rather_than_silently_blocking_everything():
    """A typo'd 0 would otherwise be indistinguishable from a strategy that found no setups."""
    v = check_account_cap(new_order_risk_ccy=1.0, open_risk=_risk(0.0), balance=2000.0,
                          cap_pct=0.0)
    assert not v.allowed and v.code == "cap_not_positive"


def test_pct_of_returns_None_rather_than_zero_when_the_balance_is_unknown():
    assert _risk(250.0).pct_of(None) is None
    assert _risk(250.0).pct_of(0.0) is None
    assert _risk(250.0).pct_of(2500.0) == 0.1


# ── the magic-uniqueness guard (the other half of two bots on one account) ────────────
#
# The risk cap stops two bots overdrawing one account's RISK. This stops them reading each
# other's ORDERS. Both are prerequisites for a second live bot and neither existed until today.
def _write_instance(root, bot_key, account, magic):
    d = root / bot_key
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps({
        "bot_key": bot_key, "mt5_path": "C:/x/terminal64.exe", "account": account,
        "server": "S", "symbol": "XAUUSD.s", "magic": magic,
    }), encoding="utf-8")
    return d


def test_two_bots_on_ONE_ACCOUNT_may_not_share_a_magic(tmp_path, monkeypatch):
    """Sharing a magic is worse than it sounds: every read in mt5_ops filters on it, so each bot
    would read the OTHER's position as its own — cancel its orders, ratchet its stop, book its
    fill. It is the doubled-book failure arriving through configuration rather than a second
    process."""
    import live_config
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_instance(tmp_path, "bot_a", 700107749, 770115)
    _write_instance(tmp_path, "bot_b", 700107749, 770115)

    with pytest.raises(ValueError) as e:
        live_config.load("bot_b")
    assert "770115" in str(e.value) and "bot_a" in str(e.value)


def test_the_same_magic_on_a_DIFFERENT_account_is_fine(tmp_path, monkeypatch):
    """Per ACCOUNT, not global — the terminal scopes orders by login, and a global rule would be
    unsatisfiable once there are more accounts than sensible magic numbers."""
    import live_config
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_instance(tmp_path, "bot_a", 700107749, 770115)
    _write_instance(tmp_path, "bot_b", 999999999, 770115)
    assert live_config.load("bot_b").magic == 770115


def test_a_bot_does_not_clash_with_ITSELF(tmp_path, monkeypatch):
    """The obvious way to write this guard wrong: the config being loaded is in the same
    directory the scan walks, so without the bot_key skip every bot refuses to start."""
    import live_config
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_instance(tmp_path, "bot_a", 700107749, 770115)
    assert live_config.load("bot_a").magic == 770115


def test_an_unreadable_SIBLING_config_does_not_stop_a_healthy_bot_starting(tmp_path, monkeypatch):
    """A half-written instance directory must not brick a bot that is fine. The cost is that a
    clash hiding inside a broken file is missed — and a broken file fails loudly on its own next
    start anyway, so nothing is silent for long."""
    import live_config
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    _write_instance(tmp_path, "bot_a", 700107749, 770115)
    broken = tmp_path / "bot_broken"
    broken.mkdir()
    (broken / "config.json").write_text("{ not json", encoding="utf-8")
    assert live_config.load("bot_a").magic == 770115
