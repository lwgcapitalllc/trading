"""`exec_tp0_pct` / `exec_tp0_atr_x` — a rung IN FRONT of TP1, priced off ATR(14) at the fill.

Why it exists: the two fib rungs sit at a median 1.10R and 1.76R and are reached by 137 and 59 of
the 245 trades on run f3e8bc41db50 — too far and too rare to touch a trade that runs 4R and hands
most of it back. This rung is near enough to catch that, and is volatility-scaled so it is not the
same distance in a quiet market as in a violent one.

Watched RED against HEAD in a scratch worktree: neither config key existed, so every test here
failed at construction. The behavioural guarantees below were then re-proved BY MUTATION against
the real implementation, because "the field is new" cannot distinguish a rung that works from one
that is merely present. The mutation map is in the docstring of each test that carries one.

🔴 The test this file exists for is `test_it_banks_size_but_NEVER_stages_the_stop`. Run 1 already
measured that moving size off the runner costs ~2R per 10%, so this lever is only ever worth
pulling for what it does to DRAWDOWN — and that trade is only honest if turning it on cannot also
move a stop, change a stage, or alter which trades are taken.
"""
from types import SimpleNamespace

from strategies.python.mpc_sos_fade.config import SosFadeConfig
from strategies.python.mpc_sos_fade.execution import Decision, Execution, _Pending


def _fill(entry, sl, tp1, tp2, direction=1, atr=None, kind="primary", **cfg_kw):
    """Fill through the real entry path. `atr` seeds the ATR the rung is priced off."""
    cfg = SosFadeConfig(**cfg_kw)
    ex = Execution(cfg)
    ex._atr = atr
    pend = _Pending(direction, entry, 1.0, sl, tp1, tp2, 1000)
    bar = SimpleNamespace(index=1, time_ms=0, open=entry, high=entry, low=entry, close=entry,
                          last_conf_high=None, last_conf_low=None)
    ex._open_position(pend, entry, bar, Decision(index=1), kind=kind)
    return ex


def test_it_ships_OFF_so_every_stored_run_still_reproduces():
    """The default must not move one figure — the live bot and this branch have to agree."""
    assert SosFadeConfig().exec_tp0_pct == 0.0
    ex = _fill(entry=100.0, sl=98.0, tp1=105.0, tp2=110.0, atr=2.0)
    assert ex._tp0 is None
    assert [b[0] for b in ex._remaining_brackets()] == ["L-RUN"]


def test_it_prices_the_rung_at_the_ATR_multiple_from_the_FILL():
    """MUTATION: multiply by anything but `exec_tp0_atr_x`, or anchor on `pend.price`
    instead of `fill_price`, and this number moves."""
    ex = _fill(entry=100.0, sl=98.0, tp1=105.0, tp2=110.0, atr=2.0,
               exec_tp0_pct=33.0, exec_tp0_atr_x=1.5)
    assert ex._tp0 == 103.0          # 100 + 1.5 * 2.00


def test_it_mirrors_for_a_short():
    ex = _fill(entry=100.0, sl=102.0, tp1=95.0, tp2=90.0, direction=-1, atr=2.0,
               exec_tp0_pct=33.0, exec_tp0_atr_x=1.5)
    assert ex._tp0 == 97.0


def test_an_unseeded_ATR_means_NO_rung_rather_than_a_rung_at_the_entry_price():
    """🔴 The failure this guards is silent and expensive: a rung priced at the entry would be
    touched by the fill bar itself and bank its whole slice at zero profit, on every trade until
    ATR seeds. MUTATION: drop the `self._atr is not None` guard and `_tp0` becomes the entry."""
    ex = _fill(entry=100.0, sl=98.0, tp1=105.0, tp2=110.0, atr=None,
               exec_tp0_pct=33.0, exec_tp0_atr_x=1.5)
    assert ex._tp0 is None
    assert [b[0] for b in ex._remaining_brackets()] == ["L-RUN"]


def test_it_takes_its_share_and_leaves_the_REST_of_the_ladder_intact():
    """The ladder before anything has filled: four rungs, a quarter each."""
    ex = _fill(entry=100.0, sl=98.0, tp1=105.0, tp2=110.0, atr=2.0,
               exec_tp0_pct=25.0, exec_tp1_pct=25.0, exec_tp2_pct=25.0, exec_tp0_atr_x=1.5)
    got = [(b[0], round(b[2], 6)) for b in ex._remaining_brackets()]
    q = ex._qty
    assert got == [("L-TP0", round(q * 0.25, 6)), ("L-TP1", round(q * 0.25, 6)),
                   ("L-TP2", round(q * 0.25, 6)), ("L-RUN", round(q * 0.25, 6))]


def test_TP1_still_gets_its_FULL_share_once_the_new_rung_has_banked():
    """🔴 This test exists because its first version did NOT catch the bug it named.

    Inspecting the ladder at `_filled_qty == 0` cannot see the cumulative accounting at all —
    `max(0, 0 - p0)` and `max(0, 0)` are both zero, so the mutation that measures TP1's fill from
    the bottom of the ladder instead of from the new rung SURVIVED. The state has to be advanced
    past TP0 for the defect to exist.

    MUTATION (run, and it now goes red): `already = max(0.0, self._filled_qty)` in the TP1 branch
    — TP1's quantity silently shrinks to nothing, because the slice TP0 already banked is counted
    against TP1 a second time.
    """
    ex = _fill(entry=100.0, sl=98.0, tp1=105.0, tp2=110.0, atr=2.0,
               exec_tp0_pct=25.0, exec_tp1_pct=25.0, exec_tp2_pct=25.0, exec_tp0_atr_x=1.5)
    q = ex._qty
    ex._filled_qty = q * 0.25                      # TP0 has banked, and nothing else has
    got = [(b[0], round(b[2], 6)) for b in ex._remaining_brackets()]
    assert got == [("L-TP1", round(q * 0.25, 6)), ("L-TP2", round(q * 0.25, 6)),
                   ("L-RUN", round(q * 0.25, 6))]


def test_the_rung_is_FIRST_in_the_ladder_because_it_is_the_nearest_price():
    ex = _fill(entry=100.0, sl=98.0, tp1=105.0, tp2=110.0, atr=2.0,
               exec_tp0_pct=33.0, exec_tp1_pct=33.0, exec_tp0_atr_x=1.5)
    names = [b[0] for b in ex._remaining_brackets()]
    assert names.index("L-TP0") < names.index("L-TP1")


def test_it_banks_size_but_NEVER_stages_the_stop():
    """🔴 THE TEST THIS FILE EXISTS FOR.

    Price runs past the volatility rung but stops short of TP1. The slice must bank AND the stop
    must not move: stage 0 is the full stop, and only TP1 arms breakeven. If this ever goes green
    the wrong way, turning the rung on has quietly changed which trades survive — and the whole
    case for the lever is that it trades R for drawdown and touches nothing else.

    MUTATION: point `_stage_rungs` at `_tp0`, or add `_tp0` to the ladder `_advance_stage` reads,
    and `_stage` becomes 1 here.
    """
    ex = _fill(entry=100.0, sl=98.0, tp1=105.0, tp2=110.0, atr=2.0,
               exec_tp0_pct=33.0, exec_tp0_atr_x=1.5)
    assert ex._tp0 == 103.0
    stop_before = ex._sl
    bar = SimpleNamespace(index=2, time_ms=60000, open=100.0, high=104.0, low=100.0, close=104.0,
                          last_conf_high=None, last_conf_low=None)
    ex._advance_stage(bar)
    assert ex._stage == 0            # TP1 at 105.0 was never touched
    assert ex._sl == stop_before     # and nothing moved the stop
