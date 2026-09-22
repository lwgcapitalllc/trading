"""Which fib each rung sits on, as a setting (`exec_tp1_level` / `exec_tp2_level`).

WHY THIS EXISTS. The rung PERCENTAGES have been tunable since the start; the rung LEVELS were
hardcoded in two places (the long block and the short block), so "what is the best first target"
could not be asked. Aaron, 2026-09-20: *"idk what is the best TP1 and TP2"*.

WATCHED RED against HEAD: every test here failed at construction (unexpected keyword) except the
Auto-default one, which is mutation-proved instead — change either default off "Auto" and it goes
red, and that default is what keeps every stored figure reproducible.

🔴 THE FALLBACK TESTS ARE THE POINT. A level behind the entry is not a target, and which levels
those are depends on where the trade FILLED, so it cannot be refused at construction. The danger
is not the fallback — it is a fallback nobody counted, which would let a sweep report a level as
measured on trades that ignored it.
"""

import pytest

from strategies.python.sos_fade.config import SosFadeConfig
from strategies.python.sos_fade.execution import Execution


class _Sig:
    """A fib ladder on a LONG leg: price rises toward 0.0, so 0.0 is the furthest target."""
    fibo_p7 = 120.0    # 0.0   — swing extreme
    fibo_p1 = 112.0    # 0.382
    fibo_p2 = 110.0    # 0.5
    fibo_p3 = 108.0    # 0.618
    fibo_p4 = 107.0    # 0.702
    fibo_p5 = 106.0    # 0.786
    fibo_p6 = 105.0    # 0.886
    fibo_p10 = 100.0   # 1.0   — leg origin


def _levels(deep, entry=106.0, dir_=1, **cfg_kw):
    ex = Execution(SosFadeConfig(exec_min_atr_pct=0.0, **cfg_kw))
    return ex, ex._ladder_levels(_Sig(), deep, entry, dir_)


def test_AUTO_is_the_default_and_is_the_shipped_deep_shallow_rule():
    """MUTATION: change either default off "Auto" and this goes red. It is the only thing keeping
    every figure in sos_fade_optimization.md reproducible."""
    cfg = SosFadeConfig()
    assert cfg.exec_tp1_level == "Auto" and cfg.exec_tp2_level == "Auto"
    _, deep = _levels(True)
    assert deep == (110.0, 112.0)          # 0.5 then 0.382
    _, shallow = _levels(False)
    assert shallow == (112.0, 120.0)       # 0.382 then 0.0


def test_a_named_level_PINS_that_rung_for_a_deep_and_a_shallow_entry_alike():
    """The whole point: Auto gives a deep and a shallow entry different targets, a named one does
    not. If this passed only for deep, the setting would be a second Auto."""
    _, deep = _levels(True, exec_tp1_level="0.0")
    _, shallow = _levels(False, exec_tp1_level="0.0")
    assert deep[0] == 120.0 and shallow[0] == 120.0


def test_the_two_rungs_are_set_INDEPENDENTLY():
    _, lv = _levels(True, exec_tp1_level="0.382", exec_tp2_level="0.0")
    assert lv == (112.0, 120.0)


def test_naming_only_the_SECOND_leaves_the_first_on_Auto():
    _, lv = _levels(True, exec_tp2_level="0.0")
    assert lv == (110.0, 120.0)            # 0.5 from Auto, 0.0 named


def test_a_level_BEHIND_the_entry_falls_back_to_Auto_and_is_COUNTED():
    """Entry at 106 (the 0.786). The 0.886 sits at 105, BELOW it — not a target for a long."""
    ex, lv = _levels(True, entry=106.0, exec_tp1_level="0.886")
    assert lv[0] == 110.0                  # the Auto level, not 105
    assert ex.tp_level_fallbacks == 1


def test_a_level_ON_the_entry_is_also_a_fallback_never_a_zero_distance_target():
    ex, lv = _levels(True, entry=110.0, exec_tp1_level="0.5")
    assert lv[0] == 110.0                  # Auto happens to be the same price here…
    assert ex.tp_level_fallbacks == 1      # …but it got there by falling back, and says so


def test_the_counter_counts_RUNGS_not_setups():
    ex, _ = _levels(True, entry=106.0, exec_tp1_level="0.886", exec_tp2_level="1.0")
    assert ex.tp_level_fallbacks == 2


def test_it_MIRRORS_for_a_short_where_beyond_means_below():
    """A short's targets are below its entry, so the same ratio flips which side counts."""
    ex, lv = _levels(True, entry=110.0, dir_=-1, exec_tp1_level="1.0")
    assert lv[0] == 100.0                  # the leg origin, below the entry — a real target
    assert ex.tp_level_fallbacks == 0


def test_an_unknown_level_REFUSES_at_construction():
    with pytest.raises(ValueError, match="exec_tp1_level"):
        SosFadeConfig(exec_min_atr_pct=0.0, exec_tp1_level="0.75")


def test_0_236_REFUSES_and_the_message_says_WHY_rather_than_just_no():
    """It was asked for by name. A refusal a reader cannot act on gets worked around."""
    with pytest.raises(ValueError) as err:
        SosFadeConfig(exec_min_atr_pct=0.0, exec_tp1_level="0.236")
    assert "0.236" in str(err.value) and "engine" in str(err.value)
