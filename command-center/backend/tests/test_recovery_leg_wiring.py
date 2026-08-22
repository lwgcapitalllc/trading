"""The loss-recovery LEG's lab wiring — the refusals, the flag, and the flat config.

Everything here fails SILENTLY if it breaks. A rule with no setups that is handed no source
returns an empty book, and an empty book is indistinguishable from a rule that found nothing —
so every check is about a state being REFUSED or a flag TRAVELLING, never about a number.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as cfg  # noqa: E402
from models import StackRequest  # noqa: E402
from routers.stacks import _validate_recovery_leg  # noqa: E402
from services import strategy_scanner  # noqa: E402


def _req(**kw) -> StackRequest:
    base = dict(
        strategy_ids=["mpc_sos_fade", "mpc_bleg"],
        instrument="XAUUSD",
        start_date="2024-01-01",
        end_date="2024-06-01",
        mode="shared",
    )
    base.update(kw)
    return StackRequest(**base)


# ── the four refusals ─────────────────────────────────────────────────────────────────
def test_the_rule_may_not_be_stacked_as_a_strategy_of_its_own():
    """It has no setups. Picked as an ordinary leg it reads nothing and returns an empty book,
    which looks exactly like a rule that found no setups."""
    req = _req(strategy_ids=["mpc_sos_fade", "loss_recovery"])
    with pytest.raises(HTTPException) as e:
        _validate_recovery_leg(req, req.strategy_ids)
    assert e.value.status_code == 400
    assert "recovery_parent" in e.value.detail


def test_a_recovery_leg_is_refused_on_a_SCREEN():
    """A screen gives every leg its own full account, so the recovery could never take room off
    its parent — the only question it exists to answer."""
    req = _req(mode="screen", recovery_parent="mpc_sos_fade")
    with pytest.raises(HTTPException) as e:
        _validate_recovery_leg(req, req.strategy_ids)
    assert "SHARED" in e.value.detail


def test_a_parent_not_in_the_stack_is_refused():
    req = _req(recovery_parent="ghost")
    with pytest.raises(HTTPException) as e:
        _validate_recovery_leg(req, req.strategy_ids)
    assert "not one of this stack's strategies" in e.value.detail


def test_params_with_no_parent_are_refused_rather_than_ignored():
    """Nothing would read them, and a setting silently discarded is a page stating a value no
    code consumed."""
    req = _req(recovery_params={"rec_risk_frac": 0.5})
    with pytest.raises(HTTPException) as e:
        _validate_recovery_leg(req, req.strategy_ids)
    assert "nothing would read them" in e.value.detail


def test_a_valid_recovery_request_passes():
    """The direction that must not be refused — otherwise the feature is unreachable."""
    req = _req(recovery_parent="mpc_sos_fade", recovery_params={"rec_risk_frac": 0.25})
    _validate_recovery_leg(req, req.strategy_ids)


def test_a_stack_with_no_recovery_is_untouched():
    """Every stored stack. The validator must be inert when nothing was asked for."""
    req = _req()
    _validate_recovery_leg(req, req.strategy_ids)


# ── the flag travels ──────────────────────────────────────────────────────────────────
def test_the_scanner_marks_the_rule_as_needing_a_source():
    """`requires_source` is what every picker filters on. Without it the rule appears beside the
    real strategies and picking it produces an empty book."""
    pkg = Path(cfg.MONOREPO_ROOT) / "strategies" / "python" / "loss_recovery"
    row, err = strategy_scanner._parse_python_package(pkg, Path(cfg.MONOREPO_ROOT))
    assert err is None, err
    assert row is not None, "loss_recovery declares LAB_STRATEGY and must be scanned"
    assert row["requires_source"] is True
    assert row["self_sizing"] is True


def test_an_ordinary_strategy_does_NOT_require_a_source():
    """The half that would go unnoticed: a flag defaulting True would hide every real strategy
    from every picker."""
    pkg = Path(cfg.MONOREPO_ROOT) / "strategies" / "python" / "mpc_sos_fade"
    row, err = strategy_scanner._parse_python_package(pkg, Path(cfg.MONOREPO_ROOT))
    assert err is None, err
    assert row["requires_source"] is False


def test_every_recovery_setting_is_documented():
    """A param with no description renders as '—' on the strategy page."""
    pkg = Path(cfg.MONOREPO_ROOT) / "strategies" / "python" / "loss_recovery"
    row, _ = strategy_scanner._parse_python_package(pkg, Path(cfg.MONOREPO_ROOT))
    undocumented = [
        p["name"]
        for p in row["param_schema"]
        if p.get("category") != "foundational" and not p.get("desc")
    ]
    assert not undocumented, f"params with no description: {undocumented}"


# ── the flat lab config ───────────────────────────────────────────────────────────────
def test_an_ATR_stop_mode_is_refused_by_the_lab_config():
    """A shared-account stack has no canonical ATR, and a private copy would be a second
    implementation of an indicator this repo keeps exactly one of. The leg refuses them at
    construction; the form must never offer one."""
    sys.path.insert(0, str(Path(cfg.MONOREPO_ROOT) / "strategies" / "python"))
    from loss_recovery import STOP_MODES, RecoveryLabConfig

    assert "atr" not in STOP_MODES and "swing" not in STOP_MODES
    with pytest.raises(ValueError) as e:
        RecoveryLabConfig(rec_stop_mode="atr")
    assert "recovery_report" in str(e.value)


def test_a_zero_size_recovery_is_refused_rather_than_clamped():
    """A zero lot fills, closes and lands in the trade list at 0R — a trade that looks taken and
    moved nothing. The way to stop taking them is to remove the leg."""
    from loss_recovery import RecoveryLabConfig

    with pytest.raises(ValueError) as e:
        RecoveryLabConfig(rec_risk_frac=0.0)
    assert "looks taken" in str(e.value)


def test_the_defaults_are_the_measured_configuration():
    """Selecting the leg and touching nothing must reproduce the runs this package recorded."""
    from loss_recovery import RecoveryLabConfig, rule_config

    rule = rule_config(RecoveryLabConfig())
    assert rule.enabled is True
    assert rule.risk_fraction == 0.25
    assert rule.stop_mode == "structural"
    assert rule.soft_stop_r is None  # 0 on the form means OFF in the engine
    assert rule.horizon_days > rule.max_days, "or the time stop never fires"
