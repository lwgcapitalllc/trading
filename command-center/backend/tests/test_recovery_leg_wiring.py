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
from routers._source_guard import refuse_if_needs_source  # noqa: E402
from routers.stacks import _validate_recovery_leg, _validate_stack_strategies  # noqa: E402
from services import strategy_scanner  # noqa: E402

# 🔴 MODULE LEVEL, not inside the first test that happens to need it. It WAS inside one, and the
# next two tests imported `loss_recovery` on the back of that side effect — which held only while
# pytest ran them in file order on one worker. Adding tests to this file changed how `-n auto`
# distributes it, and the last test landed on a worker where the insert had never run. **A test
# that depends on another test having run is a test that passes for a reason nobody chose.**
sys.path.insert(0, str(Path(cfg.MONOREPO_ROOT) / "strategies" / "python"))


def _req(**kw) -> StackRequest:
    base = dict(
        strategy_ids=["sos_fade", "b_leg"],
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
    req = _req(strategy_ids=["sos_fade", "loss_recovery"])
    with pytest.raises(HTTPException) as e:
        _validate_recovery_leg(req, req.strategy_ids)
    assert e.value.status_code == 400
    assert "recovery_parent" in e.value.detail


def test_a_recovery_leg_is_refused_on_a_SCREEN():
    """A screen gives every leg its own full account, so the recovery could never take room off
    its parent — the only question it exists to answer."""
    req = _req(mode="screen", recovery_parent="sos_fade")
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
    req = _req(recovery_parent="sos_fade", recovery_params={"rec_risk_frac": 0.25})
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
    pkg = Path(cfg.MONOREPO_ROOT) / "strategies" / "python" / "sos_fade"
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


# ── running it ALONE ──────────────────────────────────────────────────────────────────
# 🔴 The stack builder was only half the hole. The rule also has a strategy DETAIL page with its
# own Run button, and a Run modal that submits straight to the backtest endpoint — so it could be
# run on its own, from the UI, with nothing refusing it. It would have completed, graded, and
# returned an empty book that reads as "this rule finds nothing".
def test_a_rule_that_needs_a_source_cannot_be_run_alone():
    with pytest.raises(HTTPException) as e:
        refuse_if_needs_source(
            {"id": "loss_recovery", "name": "Loss Recovery", "requires_source": 1}
        )
    assert e.value.status_code == 400
    # The refusal has to say what to do INSTEAD, or it is a dead end rather than a signpost.
    assert "Loss Recovery" in e.value.detail
    assert "stack" in e.value.detail


def test_an_ordinary_strategy_is_NOT_refused():
    """A guard that refuses everything passes its own refusal test and breaks the app."""
    refuse_if_needs_source({"id": "sos_fade", "name": "SOS Fade SOS Fade", "requires_source": 0})


def test_a_missing_strategy_is_left_to_the_404():
    """Not this guard's question. Swallowing it here would turn a typo'd id into 'needs a parent'."""
    refuse_if_needs_source(None)


def test_every_endpoint_that_STARTS_a_job_from_a_strategy_id_refuses_a_dependent_rule():
    """The durable half — this is what catches the NEXT endpoint somebody adds.

    The bug was not that one guard was missing; it was that three separate routers each resolve a
    strategy off the request and start work, and nothing tied them together. So the rule is
    structural: if a function looks up `req.strategy_id`, it must also call the guard.
    """
    import ast

    routers = Path(__file__).resolve().parents[1] / "routers"
    checked = []
    for path in sorted(routers.glob("*.py")):
        tree = ast.parse(path.read_text())
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = ast.dump(fn)
            if "attr='get_strategy'" not in body or "attr='strategy_id'" not in body:
                continue
            # Only the ones that CREATE work — a read-only listing resolves a strategy for its
            # name and must not be told it needs a parent. Deliberately matched on ANY insert
            # rather than a named list of them: the sweep creator uses `insert_run_sweep`, which
            # a named list did not have and would have skipped in silence. Over-including forces
            # somebody to decide; under-including is how this hole was left open in the first
            # place.
            if "attr='insert_" not in body:
                continue
            checked.append(f"{path.name}::{fn.name}")
            assert "refuse_if_needs_source" in body, (
                f"{path.name}::{fn.name} starts a job from a strategy id but never asks whether "
                f"that strategy can run alone. See routers/_source_guard.py."
            )
    assert len(checked) >= 3, f"expected the three job creators, found {checked}"


# ── one strategy plus a recovery IS a stack ───────────────────────────────────────────
# 🔴 The minimum was counted in STRATEGY IDS, so SOS Fade plus a recovery on SOS Fade — one id, two legs, the
# single most likely stack anybody builds and the exact case this leg was built for — was refused
# with "a stack needs at least 2 strategies". Nothing was broken; the feature just could not be
# reached, which is the failure shape rule 9 is about.
def test_one_strategy_plus_a_recovery_leg_is_enough():
    _validate_stack_strategies(["sos_fade"], extra_legs=1)


def test_one_strategy_on_its_own_is_still_refused():
    with pytest.raises(HTTPException) as e:
        _validate_stack_strategies(["sos_fade"])
    assert e.value.status_code == 400
    # It has to name the way out, or the reader is told a rule and not a remedy.
    assert "loss recovery" in e.value.detail


def test_the_leg_count_is_read_off_the_REQUEST_not_assumed():
    """`trigger_stack` must pass the recovery through to the count. Guarding only the helper
    would leave the endpoint counting ids and refusing the same stack one layer up."""
    import ast

    src = Path(__file__).resolve().parents[1] / "routers" / "stacks.py"
    fn = next(
        f
        for f in ast.walk(ast.parse(src.read_text()))
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name == "trigger_stack"
    )
    body = ast.dump(fn)
    assert "extra_legs" in body and "recovery_parent" in body
