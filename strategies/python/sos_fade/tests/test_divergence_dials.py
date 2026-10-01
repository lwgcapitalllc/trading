"""The "RSI Length" and "Pivot Width (bars)" settings must reach the divergence engine.

🔴 **They reached NO engine until 2026-09-30.** Both live on the config, and the engine is built
from the stack's own config, which the static `engine_config()` cannot fill from an instance. So
a run at any other value replayed 14 / 5 and reported it as measured — a stress test's
sensitivity shift on either could not move. `sos_fade_optimization.md` Run 68 measured that the
pivot width alone moves 5-11R, so the dead dial was hiding a real sensitivity.

Watched RED against the pre-fix code: the four that set the dials failed on `rsi_pivot_len == 5`.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pandas as pd
import pytest

from backtest.replay import EngineConfig, EngineStack, stack_config_for
from strategies.python.sos_fade.config import SosFadeConfig
from strategies.python.sos_fade.strategy import SosFadeStrategy

_DIALED = dict(div_rsi_len=21, div_pivot_len=7)


def test_the_bots_stack_carries_both_dials():
    ec = SosFadeStrategy(SosFadeConfig(**_DIALED)).stack_config()
    assert (ec.rsi_len, ec.rsi_pivot_len) == (21, 7)


def test_the_dials_reach_the_engine_object_itself():
    """A field on the config is not a wired one — read the engine the stack actually built."""
    rsi = EngineStack(stack_config_for(SosFadeStrategy(SosFadeConfig(**_DIALED)))).rsi
    assert (rsi._rsi_len, rsi._pivot_len) == (21, 7)


def test_the_defaults_change_nothing():
    """Value-neutral at the shipped 14 / 5 — the stack is the one every baseline was measured on."""
    assert SosFadeStrategy(SosFadeConfig()).stack_config() == SosFadeStrategy.engine_config()


def test_an_explicit_engine_config_still_takes_the_bots_dials():
    """`run(engine_config=...)` is how the parity gate and studies hand in a base; the bot's own
    settings win for the two dials, so the gate configured from an export sees the export's."""
    base = dataclasses.replace(SosFadeStrategy.engine_config(), rsi_len=9, rsi_pivot_len=3)
    ec = SosFadeStrategy(SosFadeConfig(**_DIALED)).stack_config(base)
    assert (ec.rsi_len, ec.rsi_pivot_len) == (21, 7)


def test_a_strategy_without_a_per_instance_layer_gets_its_static_config():
    pinned = EngineConfig(major_length=77)
    assert stack_config_for(SimpleNamespace(engine_config=lambda: pinned)) is pinned


class _Built(Exception):
    pass


def test_the_optimizer_builds_the_bots_stack(monkeypatch):
    """The optimizer drives its own bar loop, so it is one of the places the dials went missing."""
    import backtest.replay as replay
    from backtest import optimizer

    seen = []

    def capture(cfg):
        seen.append(cfg)
        raise _Built

    monkeypatch.setattr(replay, "EngineStack", capture)
    # The default config needs the fast feed; this test is about the stack, not that refusal.
    monkeypatch.setattr(optimizer, "_refuse_unreplayable", lambda *a, **k: None)
    idx = pd.date_range("2026-05-01", periods=50, freq="15min")
    df = pd.DataFrame({"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}, index=idx)
    combo = optimizer.Combo(params={}, config=SosFadeConfig(**_DIALED))
    with pytest.raises(_Built):
        optimizer._replay_one(SosFadeStrategy, df, 10_000.0, combo)
    assert (seen[0].rsi_len, seen[0].rsi_pivot_len) == (21, 7)
