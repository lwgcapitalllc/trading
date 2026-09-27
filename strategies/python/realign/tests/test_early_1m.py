"""The early 1m trigger (`realign_early_1m`) — off must move nothing, on must fire where it says.

Every test here was watched RED by the mutation named in its docstring (2026-09-27).

⚠ The chain tests drive `EarlyTrigger1m` with a SCRIPTED engine that returns the engine's own
`ExternalEvents` record and nothing else — no field the canonical engine does not emit, so the
fixture is not more capable than production (rule 13). The engine itself is canonical and is
pinned by `test_the_1m_structure_is_the_canonical_engine_at_the_bots_swing_length`.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pandas as pd
import pytest

_PYPKGS = Path(__file__).resolve().parents[2]
_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_PYPKGS), str(_ROOT / "engines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from market_structure import StructureEngine  # noqa: E402
from market_structure.types import ExternalEvents  # noqa: E402

from realign.config import RealignConfig  # noqa: E402
from realign.dual import FastSig, RealignDualClock  # noqa: E402
from realign.early import EarlyTrigger1m  # noqa: E402
from realign.htf import MAJOR_LENGTH  # noqa: E402
from realign.strategy import RealignStrategy  # noqa: E402
from realign.tracker import Armed  # noqa: E402

MIN = 60_000
_GOLDEN = Path(__file__).resolve().parents[1] / "exports" / "golden" / "VANTAGE_XAUUSD_M5_21327bars.csv"


class _Scripted:
    """Stands in for the engine: hands back one scripted `ExternalEvents` per bar."""

    def __init__(self, events):
        self._ev = list(events)

    def update(self, bar):
        ev = self._ev.pop(0) if self._ev else ExternalEvents()
        return type("S", (), {"external": ev})()


def _trigger(events, cfg=None):
    t = EarlyTrigger1m(cfg or RealignConfig())
    t._engine = _Scripted(events)
    return t


def _long(counter_ext=95.0, target=110.0, armed_ms=0):
    return Armed(dir=+1, armed_ms=armed_ms, target=target, counter_bar=1, counter_ext=counter_ext)


def _feed(t, armed, lows, bucket=0):
    """One 1m bar per low; returns the index of the first bar that fired and its fire."""
    for i, lo in enumerate(lows):
        fires = t.update(i * MIN, 100.0, 101.0, lo, 100.5, armed, bucket)
        if fires:
            return i, fires[0]
    return None, None


BULL_SOS = ExternalEvents(bull_bos=True, bull_sos=True)   # a CHoCH bar raises BOTH flags
BULL_BOS = ExternalEvents(bull_bos=True)
BEAR_BOS = ExternalEvents(bear_bos=True)
NONE = ExternalEvents()


# ── the chain ─────────────────────────────────────────────────────────────────────

def test_a_shift_then_a_break_fires_on_the_break_bar_with_the_dip_extreme_as_stop():
    """MUTATIONS: stop from `a.counter_ext` alone (ignoring the 1m lows) — the stop reads 95.0 and
    this goes red; fire on the shift bar itself — the index reads 1."""
    t = _trigger([NONE, BULL_SOS, NONE, BULL_BOS])
    a = _long(counter_ext=95.0)
    i, f = _feed(t, [a], lows=[99.0, 94.0, 99.5, 99.8])
    assert i == 3
    assert f.dir == +1 and f.target == 110.0
    assert f.stop_ext == 94.0, "the 1m low after the last closed 5m bar deepened the dip"


def test_the_shift_bar_alone_never_fires_even_after_an_earlier_shift():
    """A CHoCH bar raises its BOS flag too. MUTATION: `with_bos = ev.bull_bos` (dropping `and not
    ev.bull_sos`) — the second shift fires on its own and this goes red."""
    t = _trigger([BULL_SOS, NONE, BULL_SOS, NONE])
    assert _feed(t, [_long()], lows=[99.0] * 4) == (None, None)


def test_a_counter_break_resets_the_count():
    """MUTATION: delete `a.m1_sos_seen = False` on a counter break — bar 2 fires and this goes red."""
    t = _trigger([BULL_SOS, BEAR_BOS, BULL_BOS, BULL_SOS, BULL_BOS])
    i, _ = _feed(t, [_long()], lows=[99.0] * 5)
    assert i == 4, "a bearish 1m break must reset the chain; only a NEW shift re-arms it"


def test_no_dip_on_the_5m_means_no_trigger_and_no_chain():
    """Before the 5m has gone counter there is no stop to place. MUTATION: drop the
    `counter_ext is None` skip — this fires (or crashes on min(None, …)) and goes red."""
    a = Armed(dir=+1, armed_ms=0, target=110.0)
    t = _trigger([BULL_SOS, BULL_BOS])
    assert _feed(t, [a], lows=[99.0, 99.0]) == (None, None)
    assert a.m1_sos_seen is False


def test_an_expired_setup_does_not_fire_inside_the_5m_bar_that_kills_it():
    """Expiry is judged on the 5m bar the 1m bar sits in, exactly as the tracker judges it.
    MUTATION: drop the window check — this fires and goes red."""
    cfg = RealignConfig()
    window = int(cfg.realign_window_hrs * 3_600_000)
    t = _trigger([BULL_SOS, BULL_BOS], cfg)
    a = _long(armed_ms=0)
    assert _feed(t, [a], lows=[99.0, 99.0], bucket=window + 5 * MIN) == (None, None)


def test_the_running_1m_extreme_restarts_when_a_5m_bar_closes():
    """After a 5m bar closes, its lows are inside the tracker's counter extreme — the 1m running
    low must not carry them twice (or carry a stale deeper one). MUTATION: make
    `on_primary_closed` a no-op — the stop reads 90.0 and this goes red."""
    t = _trigger([NONE, NONE, BULL_SOS, BULL_BOS])
    a = _long(counter_ext=95.0)
    t.update(0, 100, 101, 90.0, 100, [a], 0)       # a deep 1m low inside 5m bar 0
    t.on_primary_closed()                           # 5m bar 0 closes; its low is the tracker's now
    a.counter_ext = 94.0                            # the tracker folded that bar in (not the 90!)
    fires = []
    for i, lo in enumerate([99.0, 99.0, 99.0], start=1):
        fires = t.update(i * MIN, 100, 101, lo, 100, [a], 5 * MIN)
    assert fires and fires[0].stop_ext == 94.0


def test_the_1m_structure_is_the_canonical_engine_at_the_bots_swing_length():
    """Root rule: never a second structure implementation. MUTATION: build it with
    `major_length=15` — this goes red."""
    t = EarlyTrigger1m(RealignConfig())
    assert type(t._engine) is StructureEngine
    assert t._engine.major_length == MAJOR_LENGTH


# ── the clock: no lookahead ───────────────────────────────────────────────────────

class _Bar:
    def __init__(self, index, minute, px=100.0):
        self.index, self.timestamp_ms = index, minute * MIN
        self.open = self.high = self.low = self.close = px


class _Recorder:
    """Stands in for the strategy; records the order the clock calls it in."""

    def __init__(self):
        self.log = []

    def _step_primary_bar(self, state, time_ms):
        self.log.append(("5m", time_ms // MIN))

    def _on_fast_bar(self, sig, bucket):
        self.log.append(("1m", sig.time_ms // MIN, sig.index, bucket // MIN))


class _Stack:
    def step(self, bar):
        return bar


def test_every_1m_bar_is_stepped_before_the_5m_bar_it_sits_inside():
    """🔴 The no-lookahead contract: a 1m bar reads only 5m bars CLOSED by its open. MUTATIONS:
    flush on `<` instead of `<=` — 5m bar 0 is stepped after 1m bar 5, which then reads index 0
    and goes red; flush before the 1m bar's close rather than its open (`+ tf - MIN`) — 5m bar 0
    steps before 1m bar 4 and goes red."""
    rec = _Recorder()
    clock = RealignDualClock(rec, _Stack(), tf_primary_ms=5 * MIN)
    for i, m in enumerate((0, 5, 10)):
        clock.push_primary(_Bar(i, m))
    for m in range(0, 12):
        clock.step_fast(_Bar(m, m))
    clock.drain_primary()
    order = [(e[0], e[1]) for e in rec.log]
    assert order.index(("5m", 0)) == order.index(("1m", 5)) - 1
    assert order.index(("1m", 4)) < order.index(("5m", 0))
    fast = {e[1]: e for e in rec.log if e[0] == "1m"}
    assert fast[4][2:] == (0, 0), "a 1m bar inside 5m bar 0 is numbered on that bar"
    assert fast[5][2:] == (1, 5)
    assert ("5m", 10) in order, "drain_primary stepped the tail"


# ── the order layer ───────────────────────────────────────────────────────────────

def _strategy(**over):
    cfg = dataclasses.replace(RealignConfig(symbol="XAUUSD"),
                              **{"realign_early_1m": True, "realign_mom_days": None, **over})
    s = RealignStrategy(cfg, initial_capital=10_000.0)
    s.execution.bar_ms = 5 * MIN
    return s


def _fire_once(s, a, stop_ext=95.0):
    from realign.early import EarlyFire

    s.early.update = lambda *args, **kw: [EarlyFire(armed=a, dir=a.dir, stop_ext=stop_ext,
                                                    target=a.target)]
    s._on_fast_bar(FastSig(index=7, time_ms=3 * MIN, open=100.0, high=100.4, low=99.6,
                           close=100.2), 0)


def test_the_early_trigger_opens_at_the_1m_close_with_the_same_stop_buffer():
    """MUTATIONS: price at the 1m OPEN — entry reads 100.0; drop the tick buffer — the stop reads
    95.0; forget to consume the setup — it stays armed and the 5m trigger would fire it again."""
    s = _strategy()
    a = _long(counter_ext=95.0, target=110.0)
    s.tracker._armed = [a]
    _fire_once(s, a)
    ex = s.execution
    assert ex._pos_dir == +1
    assert ex._entry == 100.2
    assert ex._init_stop == pytest.approx(95.0 - 20 * 0.01)
    assert ex._entry_index == 7 and ex._entry_ms == 3 * MIN
    assert s.tracker._armed == [] and a.m1_entered
    assert s.early_entries == [(3 * MIN, 0, +1)]


def test_a_refused_early_trigger_leaves_the_setup_for_the_5m_trigger():
    """Every gate applies, and a refusal must not eat the setup. MUTATION: consume the setup
    before checking what the order layer answered — it disappears and this goes red."""
    s = _strategy(realign_mom_days=20)
    s.execution.mom_dir = +1                 # gold's move is WITH the long — the gate refuses it
    a = _long()
    s.tracker._armed = [a]
    _fire_once(s, a)
    assert s.execution._pos_dir == 0
    assert s.tracker._armed == [a] and not a.m1_entered


def test_the_entry_bar_is_managed_on_the_minutes_after_the_entry_only():
    """🔴 A stop printed BEFORE the early entry inside the same 5m bar is not the trade's. One
    printed AFTER it is. MUTATION: make `_early_view` return the whole bar — the first case is
    stopped out on a low from before the position existed and goes red."""
    from sos_fade.execution import Decision

    def run(after_low):
        s = _strategy()
        a = _long(counter_ext=99.0, target=110.0)
        s.tracker._armed = [a]
        _fire_once(s, a, stop_ext=99.0)                  # long 100.2, stop 98.8
        ex = s.execution
        ex.observe_after_early(0, 100.2, 100.5, after_low)
        whole = type("B", (), dict(index=7, time_ms=0, open=100.0, high=100.5, low=98.0,
                                   close=100.3, last_conf_high=None, last_conf_low=None))()
        ex._manage_open(whole, Decision(index=7))
        return ex._pos_dir

    assert run(after_low=99.9) == +1, "stopped on a low printed before the entry"
    assert run(after_low=98.7) == 0, "a stop hit after the entry, in the same 5m bar, was missed"


def test_an_entry_on_the_last_minute_leaves_that_5m_bar_untouched():
    """Nothing of the trade happened inside the 5m bar after its last minute. MUTATION: fall
    through to the whole bar when no minute came after — the pre-entry low stops it; red."""
    from sos_fade.execution import Decision

    s = _strategy()
    a = _long(counter_ext=99.0)
    s.tracker._armed = [a]
    _fire_once(s, a, stop_ext=99.0)
    whole = type("B", (), dict(index=7, time_ms=0, open=100.0, high=100.5, low=98.0,
                               close=100.3, last_conf_high=None, last_conf_low=None))()
    s.execution._manage_open(whole, Decision(index=7))
    assert s.execution._pos_dir == +1


# ── off is off, and on refuses every path that cannot run it ──────────────────────

def test_it_ships_off():
    assert RealignConfig().realign_early_1m is False
    assert RealignStrategy(RealignConfig()).early is None


def test_the_retest_entry_refuses_the_early_trigger():
    with pytest.raises(ValueError, match="realign_entry_mode"):
        RealignConfig(realign_early_1m=True, realign_entry_mode="retest")


def test_a_single_stream_path_refuses_it_rather_than_running_it_off():
    """MUTATION: delete the `_refuse_single_stream()` call in `run` — the run completes with the
    switch silently doing nothing and this goes red. Same for `step`."""
    s = RealignStrategy(RealignConfig(realign_early_1m=True))
    idx = pd.date_range("2025-01-06", periods=10, freq="5min")
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx)
    with pytest.raises(ValueError, match="realign_early_1m"):
        s.run(df)
    with pytest.raises(ValueError, match="realign_early_1m"):
        s.step(None)
    assert s.fast_feed_minutes() == 1
    assert RealignStrategy(RealignConfig()).fast_feed_minutes() is None


def _one_minute_from(df5: pd.DataFrame) -> pd.DataFrame:
    """Five 1m bars per 5m bar, spanning its range. With the switch OFF their values are unread."""
    rows, idx = [], []
    for t, r in df5.iterrows():
        path = [r.open, r.high, r.low, r.close, r.close]
        for k in range(5):
            p = path[k]
            rows.append((p, p, p, p))
            idx.append(t + pd.Timedelta(minutes=k))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx), columns=["open", "high", "low", "close"])


@pytest.mark.skipif(not _GOLDEN.exists(), reason="golden export not present")
def test_the_dual_path_with_the_switch_off_books_exactly_what_run_books():
    """🔴 Off = unchanged, on the committed golden bars. MUTATIONS: skip `drain_primary` in
    `run_dual` — the tail bars are never stepped, the decision count drops and this goes red.
    (Building the stack from `stack_config()` instead survives: for this bot the two are the
    same stack, so it is not a defect this test could see.)"""
    from gate_common import drop_live_final_bar
    from sos_fade.tools.compare_strategy import load_export

    df = drop_live_final_bar(load_export(_GOLDEN))[["open", "high", "low", "close"]]
    cfg = RealignConfig(symbol="XAUUSD")

    ref = RealignStrategy(cfg, initial_capital=10_000.0).run(df)
    dual = RealignStrategy(cfg, initial_capital=10_000.0).run_dual(df, _one_minute_from(df))

    def book(s):
        return [(t.dir, t.entry_index, t.entry_ms, t.entry_price, t.exit_index, round(t.r, 9))
                for t in s.execution.trades]

    assert len(book(ref)) > 0, "the golden export booked no trades — the comparison is vacuous"
    assert book(dual) == book(ref)
    assert len(dual.decisions) == len(ref.decisions)
