"""Loss-recovery wiring — the toggle, the tagging, and the properties that must not drift.

Every test here was watched RED by a named mutation (see the header comment on each). The two
that matter most are `test_turning_it_on_cannot_move_one_aplus_trade` — the whole design rests on
it — and `test_running_it_twice_does_not_double_the_book`, because three separate drivers call
`finalize` and a strategy finalized twice would report a book nobody traded.

Bars are the shared synthetic frame, which carries 25 real external CHoCHs, so the structure the
recovery reads is the canonical engine's own output rather than a hand-built stand-in. The A+
losses are INJECTED: the point under test is the wiring, and making a synthetic frame lose in a
particular way would be a fixture describing a market we do not have.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "strategies" / "python"))
sys.path.insert(0, str(_ROOT / "backtest" / "tests"))

from _synth import synth_bars  # noqa: E402

from mpc_sos_fade import MpcSosFadeStrategy  # noqa: E402
from mpc_sos_fade.config import SosFadeConfig  # noqa: E402
from mpc_sos_fade.execution import Trade  # noqa: E402
from mpc_sos_fade.recovery import recovery_config  # noqa: E402

BARS = synth_bars(40)


def _loss(entry_index: int, exit_index: int, direction: int, r: float = -1.0) -> Trade:
    """One finished A+ loss, shaped exactly as `Execution` books them."""
    px = float(BARS["close"].iloc[entry_index])
    risk_usd = 10_000.0
    return Trade(
        dir=direction, entry_index=entry_index, entry_price=px, exit_index=exit_index,
        qty=1.0, risk_usd=risk_usd, pnl_usd=r * risk_usd, r=r,
        entry_ms=int(BARS.index[entry_index].timestamp() * 1000),
        exit_ms=int(BARS.index[exit_index].timestamp() * 1000),
        exit_price=px, stop_distance=5.0, exit_reason="stop",
    )


def _strategy(**kw) -> MpcSosFadeStrategy:
    cfg = dataclasses.replace(SosFadeConfig(), **kw)
    return MpcSosFadeStrategy(config=cfg, initial_capital=100_000.0)


def _with_losses(**kw):
    """A strategy carrying two injected losses, positioned before real CHoCHs in the frame."""
    st = _strategy(**kw)
    st.execution.trades.extend([_loss(150, 200, 1), _loss(300, 330, 1)])
    return st


def _recoveries(st):
    return [t for t in st.execution.trades if t.kind == "recovery"]


# ── the toggle ───────────────────────────────────────────────────────────────────────────
def test_the_toggle_off_adds_nothing():
    """RED by mutation: drop the `if not cfg.exec_recovery: return []` guard in recovery.apply."""
    st = _with_losses(exec_recovery=False)
    before = list(st.execution.trades)
    st.finalize(BARS)
    assert _recoveries(st) == []
    assert st.execution.trades == before


def test_the_toggle_on_produces_trades_from_the_losses():
    """RED by mutation: return [] unconditionally from recovery.apply.

    Guards against the whole suite passing on a feature that silently does nothing — every other
    test here would still be green with the rule disconnected.
    """
    st = _with_losses(exec_recovery=True)
    st.finalize(BARS)
    assert len(_recoveries(st)) > 0


def test_recovery_trades_are_tagged_so_the_book_can_be_split():
    """RED by mutation: build the Trade with kind="primary"."""
    st = _with_losses(exec_recovery=True)
    st.finalize(BARS)
    assert {t.kind for t in _recoveries(st)} == {"recovery"}
    assert all(t.kind == "primary" for t in st.execution.trades if t.entry_index in (150, 300))


# ── the property the whole design rests on ───────────────────────────────────────────────
def test_turning_it_on_cannot_move_one_aplus_trade():
    """RED by mutation: have recovery.apply re-size any source trade's `pnl_usd`.

    The recovery is a lab-only toggle. If it could move A+'s book, every parity number and every
    figure in the optimization log would be at the mercy of a switch.
    """
    off = _with_losses(exec_recovery=False)
    off.finalize(BARS)
    on = _with_losses(exec_recovery=True)
    on.finalize(BARS)
    a = [t for t in off.execution.trades if t.kind != "recovery"]
    b = [t for t in on.execution.trades if t.kind != "recovery"]
    assert a == b


def test_running_it_twice_does_not_double_the_book():
    """RED by mutation: delete the `if any(... == RECOVERY_KIND)` early return.

    Three drivers call finalize (run, run_dual, the lab's own loop) and the lab calls it after a
    path that may already have finalized.
    """
    st = _with_losses(exec_recovery=True)
    st.finalize(BARS)
    once = len(_recoveries(st))
    st.finalize(BARS)
    st.finalize(BARS)
    assert len(_recoveries(st)) == once


def test_a_recovery_trade_is_not_itself_recovered():
    """RED by mutation: pass `ex.trades` to the engine instead of filtering RECOVERY_KIND out.

    Recovering a recovery is a rule nobody has measured and it would compound silently. This is
    reachable only because idempotence is tracked by a flag rather than by scanning the book for
    recovery rows — with the old guard, a book containing one returned before this line.
    """
    plain = _with_losses(exec_recovery=True)
    plain.finalize(BARS)
    baseline = {(t.entry_index, t.exit_index) for t in _recoveries(plain)}
    assert baseline, "fixture produced no recovery trades — the test would be vacuous"

    seeded = _with_losses(exec_recovery=True)
    # a LOSING recovery trade already in the book, sitting before real CHoCHs in the frame
    seeded.execution.trades.append(dataclasses.replace(_loss(400, 430, 1), kind="recovery"))
    seeded.finalize(BARS)
    produced = {(t.entry_index, t.exit_index) for t in _recoveries(seeded)
                if (t.entry_index, t.exit_index) != (400, 430)}
    assert produced == baseline


# ── sizing and units ─────────────────────────────────────────────────────────────────────
def test_a_recovery_trade_risks_the_configured_fraction_of_a_normal_one():
    """RED by mutation: drop the `* frac` from risk_usd in recovery.apply."""
    st = _with_losses(exec_recovery=True, exec_recovery_risk_frac=0.25)
    st.finalize(BARS)
    cfg = st.config
    for t in _recoveries(st):
        # the balance moves as the book compounds, so compare the RATIO to a full unit at the
        # same moment rather than an absolute figure
        full_unit = t.risk_usd / cfg.exec_recovery_risk_frac
        assert t.risk_usd == pytest.approx(full_unit * 0.25, rel=1e-9)
    quarter = _recoveries(st)
    half = _with_losses(exec_recovery=True, exec_recovery_risk_frac=0.5)
    half.finalize(BARS)
    assert _recoveries(half)[0].risk_usd == pytest.approx(quarter[0].risk_usd * 2.0, rel=1e-6)


def test_r_reproduces_pnl_over_risk_like_every_other_trade():
    """RED by mutation: set `r=rt.scaled_r` on the constructed Trade.

    One row's R must not mean something different from its neighbour's — the quarter-sizing is
    carried in the dollars, not in a second meaning for R.
    """
    st = _with_losses(exec_recovery=True)
    st.finalize(BARS)
    for t in _recoveries(st):
        assert t.r == pytest.approx(t.pnl_usd / t.risk_usd, rel=1e-9)


# ── the config mapping ───────────────────────────────────────────────────────────────────
def test_a_soft_stop_of_zero_means_off_not_a_cut_at_zero():
    """RED by mutation: pass `cfg.exec_recovery_soft_stop_r` straight through in recovery_config.

    0 is how a UI says "off"; the engine says it with None. A raw 0.0 would be refused by
    RecoveryConfig — or worse, read as a cut at no adverse move at all.
    """
    assert recovery_config(SosFadeConfig(exec_recovery=True)).soft_stop_r is None
    assert recovery_config(
        SosFadeConfig(exec_recovery=True, exec_recovery_soft_stop_r=0.3)).soft_stop_r == 0.3


def test_the_config_refuses_a_soft_stop_beyond_the_structural_one():
    """RED by mutation: delete the exec_recovery_soft_stop_r bounds check in __post_init__."""
    with pytest.raises(ValueError, match="soft_stop"):
        SosFadeConfig(exec_recovery=True, exec_recovery_soft_stop_r=1.5)


def test_recovery_knobs_are_only_validated_when_the_feature_is_on():
    """RED by mutation: hoist the recovery checks out of `if self.exec_recovery:`.

    An optimizer may sweep a recovery knob while the toggle is fixed off; every combo is then
    inert, which is a wasted sweep rather than an error. Refusing would kill a valid grid.
    """
    cfg = SosFadeConfig(exec_recovery=False, exec_recovery_soft_stop_r=1.5,
                        exec_recovery_risk_frac=-1.0)
    assert cfg.exec_recovery_soft_stop_r == 1.5


# ── what the chart needs to draw one ─────────────────────────────────────────────────────
def test_a_recovery_carries_the_excursion_the_chart_draws_it_from():
    """RED by mutation: drop `mfe_price=` / `mae_price=` from the Trade built in recovery.apply.

    Without them the price chart's profit-depth view has nothing to size the favourable band or
    the `Deepest` marker against, and it degrades to a bare outcome rectangle — the same fallback
    it uses for an NT8 trade that has no fill prices at all. That reads as a DIFFERENT KIND of
    trade rather than as a thinner record, which is the failure this whole pass exists to fix.
    """
    st = _with_losses(exec_recovery=True)
    st.finalize(BARS)
    got = _recoveries(st)
    assert got, "no recovery trades; the test cannot say anything"
    for t in got:
        assert t.mfe_price > 0.0 and t.mae_price > 0.0
        # Favourable is on the trade's own side of entry, adverse on the other. `>=` because a
        # trade that never moved either way has an excursion of exactly zero, and zero excursion
        # is a measurement — not the same thing as never having asked.
        assert (t.mfe_price - t.entry_price) * t.dir >= 0.0
        assert (t.mae_price - t.entry_price) * t.dir <= 0.0


def test_the_excursion_prices_agree_with_the_excursion_dollars():
    """RED by mutation: build `mfe_usd` from `rt.r` instead of `rt.max_favourable_r`.

    Two fields describing one measurement in two units, and two consumers read them separately —
    the price chart takes the prices, the equity view takes the dollars. If they can disagree,
    one of the two pictures is wrong and neither says which.
    """
    st = _with_losses(exec_recovery=True)
    st.finalize(BARS)
    got = _recoveries(st)
    assert got, "no recovery trades; the test cannot say anything"
    for t in got:
        assert t.mfe_usd >= 0.0 and t.mae_usd <= 0.0
        assert t.mfe_usd == pytest.approx(
            abs(t.mfe_price - t.entry_price) / t.stop_distance * t.risk_usd, rel=1e-9
        )
        assert -t.mae_usd == pytest.approx(
            abs(t.mae_price - t.entry_price) / t.stop_distance * t.risk_usd, rel=1e-9
        )
