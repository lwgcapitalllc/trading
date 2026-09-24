"""FFT — the frames, the order layer, the live seams, and one pin on real bars.

🔴 **The strategy's RULES are proven by `tools/compare_study.py`, not here.** That tool runs the bot
and the study over years of the same bars and matches every trade and every first touch; a unit
test built from a handful of synthetic bars could only restate what its author believed the rules
were. What is pinned here is the machinery those rules sit on — where a synthetic bar CAN say
exactly what must happen.

⚠ Every test whose docstring names a "Mutation:" was RUN against that mutation on 2026-09-21 and
went RED (rule 12) — except the restart test, whose mutation is a future field and is guarded by
the field-set assertion instead. ⚠ Run mutations with PYTHONDONTWRITEBYTECODE=1: two same-sized
mutants written in one second let Python reuse the other's stale bytecode, and one test read GREEN
against a mutation it catches.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

_PYPKGS = Path(__file__).resolve().parents[2]
_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_PYPKGS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from live_contract import LOAD_BEARING, verify_live_ready  # noqa: E402

from fft import LAB_STRATEGY, FftConfig, FftStrategy  # noqa: E402
from fft.execution import FftExecution, _Open  # noqa: E402
from fft.frames import ClockFrame, feed  # noqa: E402

M = 60_000
T0 = 1_700_000_100_000 - (1_700_000_100_000 % (5 * M))  # a 5-minute boundary


# ── the frames ───────────────────────────────────────────────────────────────
def test_a_candle_closes_on_its_last_minute():
    """Mutation: drop the last-minute check in `add` → the candle only appears at 10:05."""
    f = ClockFrame(5)
    got = [feed(f, i, T0 + i * M, 10, 11 + i, 9, 10) for i in range(5)]
    assert got[:4] == [[], [], [], []]
    (c,) = got[4]
    assert (c.index, c.start_ms, c.high, c.first_bar, c.last_bar) == (0, T0, 15, 0, 4)


def test_a_missing_last_minute_closes_the_candle_when_the_next_window_arrives():
    """Mutation: skip `close_by_arrival` → the 10:00 candle is never handed out."""
    f = ClockFrame(5)
    for i in range(4):
        assert feed(f, i, T0 + i * M, 10, 11, 9, 10) == []
    out = feed(f, 4, T0 + 5 * M, 10, 11, 9, 10)  # 10:04 never printed; 10:05 arrives
    assert [c.start_ms for c in out] == [T0]


def test_the_first_bar_to_print_the_high_owns_it():
    """Mutation: `>=` instead of `>` → the later tie wins, unlike the study's argmax."""
    f = ClockFrame(5)
    highs = [10, 12, 12, 11, 12]
    out = []
    for i, h in enumerate(highs):
        out += feed(f, i, T0 + i * M, 10, h, 9, 10)
    assert out[0].high_bar == 1


def test_bars_going_backwards_are_refused():
    f = ClockFrame(5)
    feed(f, 0, T0 + 5 * M, 10, 11, 9, 10)
    with pytest.raises(ValueError):
        feed(f, 1, T0, 10, 11, 9, 10)


# ── the settings ─────────────────────────────────────────────────────────────
def test_an_unknown_target_is_refused_not_ignored():
    with pytest.raises(ValueError):
        FftConfig(target="TP3")


def test_both_sides_off_is_refused():
    with pytest.raises(ValueError):
        FftConfig(exec_longs=False, exec_shorts=False)


def test_only_one_minute_bars_are_accepted():
    with pytest.raises(ValueError):
        FftStrategy().set_timeframe_minutes(5)


def test_the_15m_overextension_skip_is_off_by_default():
    """The user's decision, 2026-09-21: present, not on — the lead is unproven."""
    assert FftConfig().skip_15m_overextended is False


def _ready_to_buy(nbos15: int, on: bool) -> FftStrategy:
    """A strategy whose every other rule passes a buy at the 61.8 on the next minute."""
    from fft.frames import Candle
    from fft.strategy import Row5

    s = FftStrategy(FftConfig(skip_15m_overextended=on))
    zero, one = 110.0, 95.0
    lv = {k: zero + r * (one - zero) for k, r in (("E1", 0.618), ("E2", 0.702), ("E4", 0.886))}
    lv.update({"1.0": one, "TP1": zero + 0.5 * (one - zero), "TP2": zero + 0.382 * (one - zero)})
    lv["TP3"] = zero
    s.row5 = Row5(
        index=10, close=103.0, dir=1, sdir=1, levels=lv, e1_done=False, origin=2, ext_loc=8, nbos=0
    )
    s._candles5[8] = Candle(8, T0, 104.0, zero, 103.0, 106.0, 40, 44, 42, 40)
    s.dir15, s.nbos15, s.dir1 = 1, nbos15, -1
    return s


def test_the_15m_overextension_skip_refuses_at_four_bos_and_not_three():
    """Mutation: `>` for `>=` in the gate → the 4-BOS setup is traded; went RED 2026-09-21."""
    import pandas as pd

    ts = int(pd.Timestamp("2026-03-24 15:00", tz="UTC").value // 10**6)  # a Tuesday, mid-session
    assert _ready_to_buy(4, on=True)._decide(50, ts)["why"] == "bos15"
    assert _ready_to_buy(3, on=True)._decide(50, ts)["order"] is not None
    assert _ready_to_buy(6, on=False)._decide(50, ts)["order"] is not None


# ── the order layer ──────────────────────────────────────────────────────────
def _ex(profile=None, capital=10_000.0) -> FftExecution:
    return FftExecution(FftConfig(), initial_capital=capital, profile=profile)


def _rest_buy(ex: FftExecution, edge=100.0, stop=90.0, tp=104.0):
    ex.set_pending(
        ex.build_order(
            1, edge, stop, tp, key=(1, 7), kind="first", levels={"E1": edge, "1.0": stop, "TP2": tp}
        )
    )


def test_a_buy_limit_fills_at_its_price_and_is_sized_to_the_risk():
    """Mutation: size off the entry price instead of the stop distance → qty 5, not 50."""
    ex = _ex()
    _rest_buy(ex)
    fill = ex.resolve(1, T0, 101.0, 102.0, 99.5)
    assert fill is not None and fill.price == 100.0
    assert ex.pos.qty == pytest.approx(10_000 * 0.05 / 10.0)


def test_the_fill_minute_can_stop_out_but_cannot_take_profit_unless_filled_at_the_open():
    """Mutation: credit the target on a mid-minute fill → this books a win the study never had."""
    ex = _ex()
    _rest_buy(ex)
    ex.resolve(1, T0, 101.0, 105.0, 99.5)  # touched 100 and printed 105 in one minute
    assert ex.pos is not None and not ex.trades  # still open: the high may have come first
    ex2 = _ex()
    _rest_buy(ex2)
    ex2.resolve(1, T0, 99.0, 105.0, 98.0)  # OPENED below the limit: the minute is ours
    assert ex2.trades and ex2.trades[0].exit_reason == "target"
    assert ex2.trades[0].entry_price == 99.0


def test_a_minute_reaching_both_ends_books_the_stop():
    """Mutation: test the target first in `_exits` → a win."""
    ex = _ex()
    _rest_buy(ex)
    ex.resolve(1, T0, 101.0, 102.0, 99.5)
    ex.resolve(2, T0 + M, 100.0, 105.0, 89.0)
    assert ex.trades[0].exit_reason == "stop" and ex.trades[0].r == pytest.approx(-1.0)


def test_a_target_hit_is_the_tp2_multiple():
    ex = _ex()
    _rest_buy(ex)
    ex.resolve(1, T0, 101.0, 102.0, 99.5)
    ex.resolve(2, T0 + M, 101.0, 104.5, 100.5)
    assert ex.trades[0].exit_reason == "target" and ex.trades[0].r == pytest.approx(0.4)


def test_a_minute_opening_through_the_stop_is_not_a_trade():
    """Mutation: drop the through-the-stop refusal → a trade entered below its own stop."""
    ex = _ex()
    _rest_buy(ex)
    assert ex.resolve(1, T0, 85.0, 86.0, 84.0) is None
    assert ex.pos is None and ex.misses and "through the stop" in ex.misses[0].reason


def test_with_bid_ask_fills_a_buy_limit_needs_the_ask_to_reach_it():
    """Mutation: drop the entry adjustment → it fills on the bid touching 100."""
    from backtest.fills import PROFILES

    prof = dataclasses.replace(PROFILES["puprime_ecn"], bid_ask_fills=True)
    ex = _ex(prof)
    _rest_buy(ex)
    assert ex.resolve(1, T0, 101.0, 102.0, 100.0 - prof.spread / 2) is None
    ex2 = _ex(prof)
    _rest_buy(ex2)
    assert ex2.resolve(1, T0, 101.0, 102.0, 100.0 - prof.spread) is not None


def test_the_fill_profile_setting_prices_a_live_buy_on_the_ask():
    """The live runner builds the bot with NO cost profile, so the setting must supply one — or
    the bid touching the 61.8 fills a trade the broker's ask never reached and the bridge halts.
    Mutation: drop the `fill_profile` lookup in `FftStrategy.__init__` → the bid touch fills."""
    from backtest.fills import PROFILES

    half = PROFILES["puprime_ecn"].spread / 2
    live = FftStrategy(FftConfig(fill_profile="puprime_ecn"))  # the runner's call: no profile
    _rest_buy(live.execution)
    assert live.execution.resolve(1, T0, 101.0, 102.0, 100.0 - half) is None
    chart = FftStrategy(FftConfig())
    _rest_buy(chart.execution)
    assert chart.execution.resolve(1, T0, 101.0, 102.0, 100.0 - half) is not None


def test_an_unknown_fill_profile_is_refused():
    with pytest.raises(ValueError, match="not a broker profile"):
        FftStrategy(FftConfig(fill_profile="puprime_ecm"))


def test_a_shared_account_sizes_the_order_when_placed_not_when_filled():
    """Live, the bridge states the account's free risk before each minute. The order must be sized
    to it when PLACED, so the broker's resting order and the emulator's are one size.
    Mutation: drop `affordable_qty` from `size` → 50 oz rests, the fill refuses, RED."""
    ex = _ex()
    ex._account.external_room = 300.0  # $300 free; the trade wants $500 (5% of $10,000)
    _rest_buy(ex)
    assert ex.pend.qty == pytest.approx(30.0)  # $300 over a $10 stop
    assert ex.resolve(1, T0, 101.0, 102.0, 99.5) is not None
    assert ex.pos.qty == pytest.approx(30.0)
    tight = _ex()
    tight._account.external_room = 100.0  # under half its own share: no order at all
    assert tight.size(100.0, 90.0) == 0.0


def test_no_room_on_the_account_is_its_own_refusal():
    """Mutation: fold a 0.0 size into `unsized` → the setup reads as a zero stop distance."""
    import pandas as pd

    ts = int(pd.Timestamp("2026-03-24 15:00", tz="UTC").value // 10**6)
    s = _ready_to_buy(0, on=False)
    s.execution._account.external_room = 0.0
    assert s._decide(50, ts)["why"] == "room"


def test_one_position_at_a_time():
    ex = _ex()
    _rest_buy(ex)
    ex.resolve(1, T0, 101.0, 102.0, 99.5)
    _rest_buy(ex)
    assert ex.pend is None, "a resting order was accepted while a position was open"


# ── the live seams ───────────────────────────────────────────────────────────
def test_it_satisfies_the_live_contract_as_a_resting_strategy():
    s = FftStrategy()
    assert verify_live_ready(s) == []
    assert s.execution.entry_style == "resting"


def test_the_resting_order_carries_its_target():
    """Mutation: return None from `planned_full_exit_price` → the order goes out targetless."""
    ex = _ex()
    _rest_buy(ex)
    assert ex._pend_long is not None and ex._pend_short is None
    assert ex.planned_full_exit_price(ex._pend_long) == 104.0


def test_an_open_position_survives_a_restart_whole():
    """Mutation: add a field to `_Open` the snapshot does not carry → the restore differs."""
    ex = _ex()
    _rest_buy(ex)
    ex.resolve(1, T0, 101.0, 102.0, 99.5)
    snap = ex.snapshot_position()
    ex2 = _ex()
    ex2.restore_position(snap)
    assert ex2.pos == ex.pos
    assert set(snap["pos"]) == {f.name for f in dataclasses.fields(_Open)}


def test_the_fill_bar_reports_the_entry_and_the_stop():
    """The two load-bearing fields on the bar that opens a trade. Mutation: skip the entry fill
    in `step` → `fills` is empty on the fill bar and the bridge books nothing."""
    assert {"stop", "fills"} <= set(LOAD_BEARING)
    s = FftStrategy()
    ex = s.execution
    _rest_buy(ex)

    class _Bar:  # the decision is read off the execution, so the bar only needs an index
        index = 1

    s.step = lambda sig: ex.resolve(1, T0, 101.0, 102.0, 99.5)  # the fill, and nothing else
    dec = ex.step(type("Sig", (), {"bar": _Bar})(), None)
    assert [f.kind for f in dec.fills] == ["entry"] and dec.stop == 90.0 and dec.tp1 == 104.0


def test_the_lab_registration_declares_a_one_minute_self_sizing_strategy():
    assert LAB_STRATEGY["strategy"] is FftStrategy and LAB_STRATEGY["config"] is FftConfig
    assert LAB_STRATEGY["suggested_bar_value"] == 1 and LAB_STRATEGY["self_sizing"] is True


# ── one pin on real bars ─────────────────────────────────────────────────────
_CACHE = _ROOT / "backtest" / "cache" / "PUPrime_Demo" / "XAUUSD_p__M1.csv"


@pytest.mark.skipif(not _CACHE.exists(), reason="no PU Prime M1 cache on this machine")
def test_three_months_of_real_bars_reproduce_the_same_nine_trades():
    """Pinned 2026-09-21, the day `compare_study.py` matched the study 34/34 over the last year.
    A change that moves any of these is a change to what the bot trades — re-run the study match.
    """
    import pandas as pd

    sys.path.insert(0, str(_ROOT / "backtest" / "tools"))
    from loaded_level_study import clean_reopens

    df = pd.read_csv(_CACHE, usecols=["time", "open", "high", "low", "close"], parse_dates=["time"])
    df = df[(df.time >= "2025-09-01") & (df.time < "2025-12-01")].set_index("time").astype(float)
    clean, _ = clean_reopens(df)
    s = FftStrategy().run(clean)
    got = [
        (str(pd.Timestamp(t.entry_ms, unit="ms")), t.dir, t.exit_reason) for t in s.execution.trades
    ]
    assert got == [
        ("2025-09-09 07:29:00", -1, "target"),
        ("2025-09-16 23:07:00", -1, "target"),
        ("2025-09-17 17:36:00", -1, "stop"),
        ("2025-09-30 14:11:00", -1, "stop"),
        ("2025-10-08 18:15:00", 1, "target"),
        ("2025-10-31 13:52:00", 1, "target"),
        ("2025-11-06 21:50:00", 1, "target"),
        ("2025-11-07 11:32:00", 1, "target"),
        ("2025-11-26 15:30:00", -1, "target"),
    ]


def test_a_restored_position_still_stops_out_after_the_bar_count_restarts():
    """🔴 **The 2026-09-24 halt on the extreme-leg bots, which share this gate.** Every live
    re-warm numbers bars from the start of its own window again, so a trade carried across one
    comes back with an entry bar number HIGHER than every live bar after it. Gated on that
    number, the stop is never tested and the broker closes a trade the strategy still holds.
    RED against the old `self.pos.entry_index < index` gate in `resolve`.
    """
    old = _ex()
    _rest_buy(old)
    old.resolve(9_000, T0, 101.0, 102.0, 99.5)          # filled, in the old process's count
    assert old.pos is not None
    new = _ex()
    new.restore_position(old.snapshot_position())
    new.resolve(500, T0 + 60 * M, 100.0, 100.5, 89.0)  # an hour later, renumbered: far below the stop
    assert new.pos is None, "the strategy ignored its own stop on a restored trade"
    assert new.trades[-1].exit_reason == "stop"
