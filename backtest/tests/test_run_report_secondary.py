"""`run_report.py` must replay the path its config asks for — or refuse.

THE DEFECT THESE PIN (found 2026-08-16). `exec_secondary` (the mpc_sos_fade 1m sniper re-entry)
defaults **True** and fills on real 1m bars via `run_dual(df15, df1m)`. `run_report.py` called
`strategy.run(df15)` unconditionally, so the flag could not do anything — and the tool still
printed `override exec_secondary = True (was True)` and exited 0.

That is this repo's most-repeated failure shape, one layer along from `optimizer.py`'s (which has
refused the same config since 2026-08-07, see `test_sweep_refuses_multi_timeframe.py`): a run that
CANNOT execute a feature and a run where the feature simply never fired produce the identical
artefact. MEASURED over full history: the dual path books 8 secondary trades worth +25.5R
(189 trades / 164.4R) that the 15m-only path cannot see (182 / 140.0R).

WATCHED RED: every test here was run against HEAD before the fix. `test_a_config_wanting_the_1m
_secondary_asks_for_the_dual_path` and both `--no-secondary` tests fail on `AttributeError:
module has no attribute '_choose_replay'` (the seam did not exist); the two behavioural ones were
then re-checked by mutation — see each docstring.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.tools.run_report import _choose_replay  # noqa: E402


@dataclass(frozen=True)
class _Cfg:
    """A frozen dataclass, like every real strategy config here — `replace` must work on it."""

    exec_secondary: bool = True


@dataclass(frozen=True)
class _NoSuchField:
    """A strategy with no secondary concept at all. Most of them."""

    something_else: int = 1


def test_a_config_wanting_the_1m_secondary_asks_for_the_dual_path():
    """MUTATION: return `False` for `wants` and this is the only test that reddens."""
    cfg, wants, note = _choose_replay(_Cfg(exec_secondary=True), no_secondary=False)
    assert wants is True
    assert cfg.exec_secondary is True
    assert note == ""


def test_a_config_not_wanting_it_asks_for_the_plain_path():
    cfg, wants, note = _choose_replay(_Cfg(exec_secondary=False), no_secondary=False)
    assert wants is False
    assert cfg.exec_secondary is False
    assert note == ""


def test_a_strategy_with_no_secondary_field_is_not_dragged_onto_the_dual_path():
    """`getattr(..., False)` rather than an attribute access — most strategies lack the field."""
    cfg, wants, note = _choose_replay(_NoSuchField(), no_secondary=False)
    assert wants is False
    assert note == ""


def test_no_secondary_SETS_the_flag_false_rather_than_only_picking_the_fast_path():
    """🔴 The load-bearing one. The reported config must be the config that RAN.

    MUTATION (run 2026-08-16): return the cfg unchanged (keeping `exec_secondary=True`) while
    still returning `wants=False`. The run would then execute the 15m-only path and write a
    config claiming the secondary was on — the exact state this whole file exists to make
    impossible. Reddens this test AND `test_the_original_config_is_not_mutated`, which is
    correct: that one asserts a fresh object came back, which the same mutation destroys.
    """
    cfg, wants, note = _choose_replay(_Cfg(exec_secondary=True), no_secondary=True)
    assert wants is False
    assert cfg.exec_secondary is False, "the run would report a feature it did not execute"
    assert "exec_secondary" in note, "a silent downgrade is the defect, not the fix"


def test_no_secondary_on_a_config_that_never_wanted_it_says_nothing():
    """No note, because there is nothing to warn about — a message here trains people to ignore
    the one above it."""
    cfg, wants, note = _choose_replay(_Cfg(exec_secondary=False), no_secondary=True)
    assert wants is False
    assert note == ""


def test_the_original_config_is_not_mutated():
    """Configs here are frozen for a reason — a run must not be able to edit its own inputs."""
    original = _Cfg(exec_secondary=True)
    returned, _, _ = _choose_replay(original, no_secondary=True)
    assert original.exec_secondary is True
    assert returned is not original


def test_the_tool_refuses_a_secondary_config_it_cannot_replay():
    """A strategy wanting the secondary but exposing no `run_dual` must RAISE, never quietly fall
    back to `run()`. This is the guarantee; the call site is asserted by reading it, because
    driving `main()` needs bars, a cache and a terminal.
    """
    src = (_ROOT / "backtest" / "tools" / "run_report.py").read_text()
    assert 'if not hasattr(strat, "run_dual"):' in src
    assert "raise SystemExit(" in src.split('if not hasattr(strat, "run_dual"):')[1][:400]
    # and the primary-only path must be the ELSE of the secondary branch, never a default
    assert "strat.run_dual(df, df1m, warmup=args.warmup)" in src
