"""SOS Fade Generic — the mapping onto SOS Fade, the refusals, and the parity-gate settings check.

Everything that DECIDES a trade is SOS Fade's own and is tested there. What can go wrong HERE is
the mapping: a feature left at SOS Fade's default quietly comes back, a target choice sets the
wrong rung, or the gate accepts an export taken at the wrong settings. Each test below names
the mutation it was watched going red against.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[4]
for p in (str(_ROOT), str(_ROOT / "strategies" / "python"), str(_ROOT / "backtest" / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

from _synth import synth_bars  # noqa: E402
from sos_fade import SosFadeConfig, SosFadeStrategy  # noqa: E402
from sos_fade_generic import (  # noqa: E402
    LAB_STRATEGY, TARGETS, SosFadeGenericConfig, SosFadeGenericStrategy)
from sos_fade_generic.tools.compare_generic import generic_from_export  # noqa: E402

#: Every SOS Fade feature, and the value that means OFF. Held against `to_sos_fade()` so a
#: feature cannot drift back on through SOS Fade's own default.
#: RED by mutation: deleting `exec_secondary=False` (or any line here) from `to_sos_fade`.
_OFF = {
    "exec_bleg": False, "exec_secondary": False, "exec_recovery": False,
    "exec_short_hold": False, "exec_lvl_memory": False, "exec_scale_in": False,
    "exec_respect_veto": False, "exec_htf_exhaust_only": False, "exec_htf_weekly": "Ignore",
    "exec_htf_daily": "Ignore", "exec_no_late_day": False, "exec_min_atr_pct": 0.0,
    "exec_entry_block_from": "", "exec_entry_block_to": "", "exec_close_opp_sos": False,
    "exec_time_stop_mode": "Off", "exec_be_arm_r": -1.0, "exec_giveback_arm_r": -1.0,
    "exec_rev_exit": "Off", "flat_mode": "Off", "exec_conf_sz": False,
}


def test_every_feature_beyond_the_core_is_off():
    inner = SosFadeGenericConfig().to_sos_fade()
    wrong = {f: getattr(inner, f) for f, off in _OFF.items() if getattr(inner, f) != off}
    assert wrong == {}


def test_the_off_list_is_not_vacuous():
    """At least half of the `_OFF` features are ON in SOS Fade as shipped, so the pins do work.

    RED by mutation: pointing `_OFF` at a list of fields whose SOS Fade default is already off.
    """
    shipped = SosFadeConfig()
    on_by_default = [f for f, off in _OFF.items() if getattr(shipped, f) != off]
    assert {"exec_secondary", "exec_scale_in", "exec_respect_veto", "exec_no_late_day",
            "exec_time_stop_mode", "exec_min_atr_pct"} <= set(on_by_default)


def test_the_stop_is_the_one_fib_with_no_buffer():
    inner = SosFadeGenericConfig().to_sos_fade()
    assert (inner.exec_sl_level, inner.exec_sl_deep, inner.exec_sl_buf_tk) == ("1.0", False, 0.0)


@pytest.mark.parametrize("choice, level, r", [
    ("Swing high/low", "0.0", -1.0), ("1R", "Auto", 1.0), ("2R", "Auto", 2.0), ("3R", "Auto", 3.0)])
def test_each_target_closes_the_whole_trade_at_one_rung(choice, level, r):
    inner = SosFadeGenericConfig(gen_target=choice).to_sos_fade()
    assert (inner.exec_tp1_level, inner.exec_tp1_r) == (level, r)
    assert (inner.exec_tp1_pct, inner.exec_tp2_pct) == (100.0, 0.0)


def test_both_arms_are_on_by_default():
    """Aaron's rule for this bot: armed on a sweep OR a divergence. SOS Fade ships sweep only."""
    inner = SosFadeGenericConfig().to_sos_fade()
    assert inner.exec_arm_sweep and inner.exec_arm_div


def test_an_unknown_target_is_refused():
    with pytest.raises(ValueError, match="gen_target"):
        SosFadeGenericConfig(gen_target="4R")


def test_both_arms_off_is_refused():
    with pytest.raises(ValueError, match="nothing can ever trade"):
        SosFadeGenericConfig(exec_arm_sweep=False, exec_arm_div=False)


def test_exposed_settings_reach_sos_fade():
    g = SosFadeGenericConfig(exec_longs=False, exec_risk_pct=2.5, exec_req_fvg=False,
                             aplus_window=600, exec_min_stop_val=0.2, symbol="GBPUSD.p")
    inner = g.to_sos_fade()
    assert (inner.exec_longs, inner.exec_risk_pct, inner.exec_req_fvg, inner.aplus_window,
            inner.exec_min_stop_val, inner.symbol) == (False, 2.5, False, 600, 0.2, "GBPUSD.p")


def test_tick_size_follows_the_cost_profile():
    """RED by mutation: removing the `dataclasses.replace(inner, mintick=...)` line."""
    s = SosFadeGenericStrategy(SosFadeGenericConfig(), cost_profile=SimpleNamespace(
        mintick=0.001, latency_ms=0))
    assert s.config.mintick == 0.001
    assert SosFadeGenericStrategy(SosFadeGenericConfig()).config.mintick == 0.01


def test_it_trades_exactly_as_sos_fade_at_the_mapped_settings():
    """The whole design claim: this bot IS SOS Fade at `to_sos_fade()`. Wiring, not logic."""
    bars = synth_bars(12)
    cfg = SosFadeGenericConfig()
    a = SosFadeGenericStrategy(cfg).run(bars, warmup=100)
    b = SosFadeStrategy(cfg.to_sos_fade()).run(bars, warmup=100)
    assert [dataclasses.astuple(t) for t in a.execution.trades] == \
           [dataclasses.astuple(t) for t in b.execution.trades]
    assert len(a.decisions) == len(b.decisions)


def test_lab_registration():
    assert LAB_STRATEGY["config"] is SosFadeGenericConfig
    assert LAB_STRATEGY["strategy"] is SosFadeGenericStrategy
    assert LAB_STRATEGY["self_sizing"] is True


# ── the parity gate's settings check ─────────────────────────────────────────────────────
# A one-row export carrying only the cfg_* columns `config_from_export` decodes. Bit values are
# `compare_strategy.py`'s packing, which is `sos_fade_strategy_export.pine`'s.
_GOOD_BITS = (1 | 2 | 4 | 8 | 16 | 32 | 1024 | 2048 | 16384 | 524288)   # veto (64) and late-day (512) OFF


def _export(**over):
    row = {"cfg_bits": _GOOD_BITS, "cfg_strcodes": 4000, "cfg_tp1_level": 1, "cfg_tp1_r": -1,
           "cfg_tp1_pct": 100, "cfg_tp2_pct": 0, "cfg_sl_buf": 0, "cfg_min_stop": 1,
           "cfg_min_stop_val": 0.08, "cfg_min_atr": 0, "cfg_time_stop": 0, "cfg_scale_in": 0,
           "cfg_window": 4320, "cfg_risk_pct": 5, "cfg_nogap_arm": 0, "cfg_poi_source": 0}
    row.update(over)
    return pd.DataFrame([row])


def test_gate_accepts_an_export_at_the_generic_settings():
    generic, problems = generic_from_export(_export())
    assert problems == []
    assert generic == SosFadeGenericConfig()


def test_gate_reads_an_r_target():
    generic, problems = generic_from_export(_export(cfg_tp1_level=0, cfg_tp1_r=2))
    assert problems == [] and generic.gen_target == "2R"


@pytest.mark.parametrize("over, label", [
    ({"cfg_strcodes": 3000}, "Stop fib level"),
    ({"cfg_time_stop": 1}, "Time stop"),
    ({"cfg_bits": _GOOD_BITS | 512}, "No entries in the final hour"),
    ({"cfg_bits": _GOOD_BITS | 64}, "Respect divergence/extreme veto"),
    ({"cfg_min_atr": 0.08}, "Minimum market volatility"),
    ({"cfg_tp1_pct": 0}, "TP1 size %"),
    ({"cfg_scale_in": 1}, "Add to the runner"),
    ({"cfg_tp1_level": 3}, "Target 1 level"),
])
def test_gate_refuses_an_export_at_the_wrong_settings_and_names_it(over, label):
    """RED by mutation: deleting that setting's line from `_PINNED_LABELS`."""
    generic, problems = generic_from_export(_export(**over))
    assert generic is None
    assert any(label in p for p in problems), problems
