"""The SHORT-HOLD variant — take an A+ setup for a fixed R and close, instead of riding it.

Three rules, all behind one toggle that ships OFF: refuse an entry resting deeper than a fib,
close the whole position at a multiple of risk, and (optionally) refuse a New York hour window.

**Why the tests are weighted the way they are.** The variant was measured MARGINAL (+22.5R over
109 trades in 6.6 years against A+'s +130.8R over 158, and negative from 2024 on), so the risk
here is not that it under-performs — that is already known and written down. The risk is that it
leaks into the shipped path, which is the LIVE bot's source. So the first block below is entirely
about the toggle being off, and every rule is asserted twice: it fires when on, and it cannot fire
when off.

The second weighting is toward the ways each rule can be silently wrong rather than loudly broken:

  * the depth cap RE-PRICING instead of refusing — a shallower entry is a wider stop and a
    different position size, i.e. a different trade wearing this one's name
  * the cap turning unknown fib geometry into a refusal, which reads as a dead engine
  * the R target creeping in as the stop ratchets (it is priced off the INITIAL stop)
  * the variant reaching a RE-ENTRY, which has its own ladder and its own measured figures
  * the hour window being folded into the final-hour rule, which would leave the block marker
    saying "16:00-18:00" about a setup refused at 10:00

Watched RED — each of these was run against a deliberately broken build, and the mutation that
kills it is named in the test that catches it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT / "strategies" / "python"))

from mpc_sos_fade import Execution, SosFadeConfig  # noqa: E402
from mpc_sos_fade.execution import Decision, _Pending, _block_codes  # noqa: E402

# The bull leg every fixture uses: high anchor 110, low 100. So a fib ratio is (110 - price)/10.
#   0.5=105.0   0.618=103.82   0.702=102.98   0.786=102.0   0.886=101.14   1.0=100.0
_CAP = 102.98            # the 0.702 — the shipped cap
_ASH, _ASL = 110.0, 100.0


def _sig(dir=1, hour=8, ash=_ASH, asl=_ASL):
    """Only the fields the rules under test read. Deliberately NOT a full `Signals`: these are
    unit tests of three predicates, and the integration path is covered by the replay in
    `backtest/tools/ob_leg_replay.py`, which runs the real order layer over 155,807 real bars."""
    return SimpleNamespace(index=1, time_ms=0, ny_hour=hour, fibo_dir=dir,
                           fibo_ash=ash, fibo_asl=asl,
                           fibo_p1=106.18, fibo_p2=105.0, fibo_p3=103.82, fibo_p7=110.0,
                           # ⚠ The four higher-timeframe bias fields are EMPTY on purpose,
                           # because that is what production produces: they are declared on
                           # `Signals` with an empty-string default and assigned nowhere in the
                           # repo (checked 2026-08-24 by grep AND by driving the bot — the
                           # weekly requirement at "Must agree" takes 0 trades over 2022-23,
                           # at "Must not oppose" takes the same 48 as "Ignore"). A fixture that
                           # filled them in would be more capable than the code, which is this
                           # package's own named trap.
                           w_est_state="", d_est_state="", w_est_desc="", d_est_desc="")


def _cfg(**kw):
    # Pinned OFF: these fixtures feed too few bars to seed ATR(14), and the dead-market floor
    # refuses on an unseeded ATR by design. `test_dead_market.py` owns that behaviour.
    kw.setdefault("exec_min_atr_pct", 0.0)
    return SosFadeConfig(**kw)


# ── the toggle ships OFF, and that is the safety argument ───────────────────────
def test_the_variant_ships_off():
    """Everything else here is only safe because of this line. The shipped replay is
    byte-identical with it off — 158 trades, +130.8R, 2020-01-01 -> 2026-08-06 on the ECN tier,
    diffed on every decision field rather than on the count and the total."""
    assert SosFadeConfig().exec_short_hold is False


def test_the_defaults_are_the_measured_ones():
    c = SosFadeConfig()
    assert (c.exec_sh_max_depth, c.exec_sh_tp_r, c.exec_sh_tp1_pct) == (1.0, 2.0, 100.0)
    assert c.exec_sh_max_depth == 1.0, (
        "the depth cap ships INERT. A 0.702 cap was the original default, argued from three "
        "independent readings of the entry-depth split — and when it was finally APPLIED on a "
        "matched basis it removed 5 trades and 2.1R. See the field's own note.")
    assert (c.exec_sh_block_from, c.exec_sh_block_to) == (-1, -1), "the hour window ships off"


# ── rule 1: the depth cap ───────────────────────────────────────────────────────
@pytest.mark.parametrize("edge,expected,why", [
    (105.0, False, "the 0.5 — the shallowest the band allows"),
    (103.82, False, "the 0.618 — inside the cap"),
    (102.98, False, "exactly ON the 0.702 cap; the cap is a ceiling, not an exclusion"),
    (102.5, True, "past the cap, between 0.702 and 0.786"),
    (101.14, True, "the 0.886 — the stop fib itself"),
])
def test_the_cap_refuses_an_entry_deeper_than_its_fib(edge, expected, why):
    """MEASURED, and the mechanism replicated three ways: in the real replay of this pool the
    0.702-0.786 band made -0.53R a trade against +0.31R and +0.97R shallower than it."""
    ex = Execution(_cfg(exec_short_hold=True, exec_sh_max_depth=0.702))
    assert ex._too_deep(_sig(), edge, True) is expected, why


def test_the_cap_reads_the_SHORT_side_the_other_way_up():
    """A bear leg retraces UPWARD, so deeper is a HIGHER price. A cap that compares the same way
    on both sides passes every long test and refuses nothing at all on shorts."""
    ex = Execution(_cfg(exec_short_hold=True, exec_sh_max_depth=0.702))
    # bear leg, same anchors: 0.702 sits at 100 + 10*0.702 = 107.02
    assert ex._too_deep(_sig(dir=-1), 107.5, False) is True
    assert ex._too_deep(_sig(dir=-1), 106.0, False) is False


def test_the_cap_is_a_RATIO_so_it_travels_with_the_leg():
    """The same price is inside the cap on one leg and past it on another. A cap stored as a
    price would be right on the leg it was tuned on and meaningless everywhere else."""
    ex = Execution(_cfg(exec_short_hold=True, exec_sh_max_depth=0.702))
    # One price, two legs, opposite answers. On the 10-wide leg the 0.702 sits at 102.98, so 105
    # is comfortably inside it; on the 100-wide leg the same 0.702 sits at 129.80 and 105 is far
    # past it. A cap stored as a PRICE would be right on the leg it was tuned on and meaningless
    # on every other one.
    assert ex._too_deep(_sig(ash=110.0, asl=100.0), 105.0, True) is False
    assert ex._too_deep(_sig(ash=200.0, asl=100.0), 105.0, True) is True


def test_the_cap_cannot_fire_with_the_variant_off():
    """Mutation that kills this: drop the `exec_short_hold` test from the guard. Then the cap
    starts refusing the LIVE bot's deep entries, which are 15 trades worth +36.3R."""
    ex = Execution(_cfg(exec_sh_max_depth=0.702))
    assert ex._too_deep(_sig(), 101.14, True) is False


@pytest.mark.parametrize("sig", [
    _sig(ash=None), _sig(asl=None), _sig(dir=0),
], ids=["no high anchor", "no low anchor", "no fib direction"])
def test_unpriced_geometry_is_NOT_too_deep(sig):
    """An unknown fib must not become a silent refusal. The failure it would produce is a bot
    that quietly stops trading and looks like a broken engine rather than a filter."""
    ex = Execution(_cfg(exec_short_hold=True, exec_sh_max_depth=0.702))
    assert ex._too_deep(sig, 101.0, True) is False


def test_the_cap_REFUSES_the_order_rather_than_moving_it(monkeypatch):
    """The whole design decision, pinned. Re-pricing the limit shallower would keep the setup and
    change the trade: the stop stays pinned at its fib, so a shallower entry is a wider stop, a
    different 1R and a different size. Mutation that kills this: snap the edge to the cap instead
    of returning None."""
    from mpc_sos_fade import execution as _mod
    ex = Execution(_cfg(exec_short_hold=True, exec_sh_max_depth=0.702),
                   initial_capital=100_000.0)
    monkeypatch.setattr(ex, "_armed", lambda *a, **k: (True, False))
    monkeypatch.setattr(ex, "_record_blocks", lambda *a, **k: None)
    monkeypatch.setattr(ex, "_sl_anchor", lambda *a, **k: 101.14)
    monkeypatch.setattr(_mod, "_freeze_fib", lambda sig: None)
    seq = SimpleNamespace(l_sos_bar=1000, s_sos_bar=None)
    dec = SimpleNamespace(long_veto=False, short_veto=False)
    ex._place_entries(_sig(), seq, dec, 102.5, None)       # 102.5 is past the 0.702
    assert ex._pend_long is None, "a too-deep entry must rest NO order"
    ex._place_entries(_sig(), seq, dec, 103.82, None)      # the 0.618 is inside it
    assert ex._pend_long is not None and ex._pend_long.edge == pytest.approx(103.82)


# ── rule 2: the fixed-R target ──────────────────────────────────────────────────
def _opened(**cfg_kw):
    ex = Execution(_cfg(**cfg_kw))
    pend = _Pending(1, 100.0, 1.0, 98.0, 105.0, 106.0, None)   # entry 100, stop 98 -> 1R = 2.0
    bar = SimpleNamespace(index=1, time_ms=0, open=100.0, high=100.0, low=100.0, close=100.0,
                          last_conf_high=None, last_conf_low=None)
    ex._open_position(pend, 100.0, bar, Decision(index=1), kind="primary")
    return ex


def test_the_target_sits_at_the_configured_multiple_of_risk():
    assert _opened(exec_short_hold=True, exec_sh_tp_r=2.0)._tp1 == pytest.approx(104.0)
    assert _opened(exec_short_hold=True, exec_sh_tp_r=1.5)._tp1 == pytest.approx(103.0)


def test_a_short_puts_the_target_BELOW_the_entry():
    ex = Execution(_cfg(exec_short_hold=True, exec_sh_tp_r=2.0))
    pend = _Pending(-1, 100.0, 1.0, 102.0, 95.0, 94.0, None)
    bar = SimpleNamespace(index=1, time_ms=0, open=100.0, high=100.0, low=100.0, close=100.0,
                          last_conf_high=None, last_conf_low=None)
    ex._open_position(pend, 100.0, bar, Decision(index=1), kind="primary")
    assert ex._tp1 == pytest.approx(96.0)


def test_the_whole_position_comes_off_at_the_target():
    """100% by default, so there is no runner. Below 100 hands the remainder back to the runner
    machinery and the trade stops being short-hold, which is why the config refuses 0."""
    ex = _opened(exec_short_hold=True)
    assert ex._tp1_pct() == 100.0


def test_the_target_leaves_the_ladder_alone_with_the_variant_off():
    """The shipped primary keeps the fib rung it was priced on."""
    ex = _opened()
    assert ex._tp1 == pytest.approx(105.0)
    assert ex._tp1_pct() == SosFadeConfig().exec_tp1_pct


def test_the_variant_never_touches_a_RE_ENTRY():
    """A re-entry has its own ladder and its own measured figures.

    ⚠ **The re-entry is configured to keep its FIB rung here (-1.0), and that is the only version
    of this test that can fail.** Written first with the re-entry on its own R target, it passed
    against a build with the `kind == "primary"` guard deleted — because the re-entry branch runs
    after this one and simply overwrote the leak. A test whose subject is masked by the next
    statement is testing that statement.
    """
    cfg = _cfg(exec_short_hold=True, exec_sh_tp_r=2.0, exec_secondary=True, exec_sec_tp_r=-1.0)
    ex = Execution(cfg)
    pend = _Pending(1, 100.0, 1.0, 98.0, 105.0, 106.0, None)
    bar = SimpleNamespace(index=1, time_ms=0, open=100.0, high=100.0, low=100.0, close=100.0,
                          last_conf_high=None, last_conf_low=None)
    ex._open_position(pend, 100.0, bar, Decision(index=1), kind="secondary")
    assert ex._tp1 == pytest.approx(105.0), "the 15m fib rung the re-entry asked for"
    assert ex._tp1_pct() != cfg.exec_sh_tp1_pct or cfg.exec_tp1_pct == cfg.exec_sh_tp1_pct


# ── rule 3: the hour window ─────────────────────────────────────────────────────
@pytest.mark.parametrize("hour,blocked", [
    (9, False), (10, True), (11, True), (12, False), (13, False),
])
def test_the_hour_window_is_half_open(hour, blocked):
    ex = Execution(_cfg(exec_short_hold=True, exec_sh_block_from=10, exec_sh_block_to=12))
    assert ex._sh_hour_block(_sig(hour=hour)) is blocked


@pytest.mark.parametrize("hour,blocked", [
    (21, False), (22, True), (23, True), (0, True), (1, True), (2, False),
])
def test_a_window_may_wrap_midnight(hour, blocked):
    """Asia straddles the New York day, so a trader stating a session genuinely needs this."""
    ex = Execution(_cfg(exec_short_hold=True, exec_sh_block_from=22, exec_sh_block_to=2))
    assert ex._sh_hour_block(_sig(hour=hour)) is blocked


def test_the_hour_window_is_off_by_default_even_with_the_variant_on():
    ex = Execution(_cfg(exec_short_hold=True))
    assert all(ex._sh_hour_block(_sig(hour=h)) is False for h in range(24))


def test_the_hour_window_cannot_fire_with_the_variant_off():
    ex = Execution(_cfg(exec_sh_block_from=10, exec_sh_block_to=12))
    assert ex._sh_hour_block(_sig(hour=11)) is False


def test_the_hour_window_gets_its_OWN_code_and_does_not_borrow_the_final_hour_s():
    """🔴 The label defect this design exists to avoid. Folding these hours into the final-hour
    rule would leave the block marker and the Telegram callout both saying *"no new entries
    16:00-18:00 New York"* about a setup refused at 10:00 — a label describing a rule the code no
    longer has. Mutation that kills this: OR the window into `late` inside `_bar_gates`."""
    from mpc_sos_fade.execution import _BLOCK_LABEL
    assert _block_codes(False, False, False, False, False, False, sh_hours=True) == [8]
    assert _BLOCK_LABEL[8] != _BLOCK_LABEL[3]
    assert "16:00" not in _BLOCK_LABEL[8]


def test_the_window_travels_as_its_own_gate_and_leaves_the_final_hour_rule_alone():
    """🔴 The wiring, not the code table. The version of this test that only asked
    `_block_codes` for its answer PASSED against a build that ORed the window straight into the
    final-hour flag — because that table never sees `_bar_gates`. This drives the real method and
    asserts the two flags stay apart.

    Mutation that kills it: fold the window into `late` inside `_bar_gates`.

    ⚠ It also pins the ARITY of `_bar_gates`, which is why it unpacks the whole tuple by name.
    `mpc_bos` reuses this class and unpacks the same five, so a sixth value raised `ValueError`
    in another strategy — caught only by that strategy's parity test."""
    ex = Execution(_cfg(exec_short_hold=True, exec_sh_block_from=10, exec_sh_block_to=12))
    late, _htf_l, _htf_s, _b_l, _b_s = ex._bar_gates(_sig(hour=11))
    assert (late, ex._sh_hour_block(_sig(hour=11))) == (False, True), \
        "11:00 is the variant's window, not the final hour"
    late, _htf_l, _htf_s, _b_l, _b_s = ex._bar_gates(_sig(hour=16))
    assert (late, ex._sh_hour_block(_sig(hour=16))) == (True, False), \
        "16:00 is the final hour, not the variant's window"


def test_the_deep_refusal_gets_its_own_code_too():
    assert _block_codes(False, False, False, False, False, False, sh_deep=True) == [9]


def test_the_new_codes_did_not_renumber_the_pine_ones():
    """8 and 9 are appended, never inserted. Every existing code keeps its number, and with the
    variant off neither can appear — which is what makes a new code parity-safe here."""
    assert _block_codes(True, True, True, True, True, True, True) == [1, 2, 3, 4, 5, 6, 7]
