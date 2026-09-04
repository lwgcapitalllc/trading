"""Each entry method owns its pre-rung stop rule, and no rule can move a stop BACKWARDS.

WATCHED RED against HEAD (`ecdbd9b1`), in a detached worktree, before the implementation existed:

  * `test_no_retreat_*` FAILED on the real defect — walking a reclaim forward with the shared
    rule arming at 1R keeping half and the reclaim's own arming at 2.5R keeping three quarters,
    the stop went 99.00 -> 98.50 at 2.5R in front. Away from the market, on a winning trade.
  * every other test FAILED at construction, because `exec_gap_be_r`, `exec_gap_be_keep_r`,
    `exec_shift_be_r` and `exec_shift_be_keep_r` did not exist as settings.

Re-proved by MUTATION against the implementation, one at a time:

  * make `_protect_rule` fall back to the primary's pair for an unnamed secondary
    -> `test_unnamed_secondary_gets_no_movement` fails.
  * make `_protect_rule` ignore `_entry_src` and always answer the primary's pair
    -> `test_each_method_reads_only_its_own_rule` fails on the gap and shift cases.
  * put the reclaim's branch back ahead of the general one in `_current_stop`
    -> `test_no_retreat_reclaim_under_the_old_collision` fails, 99.00 -> 98.50.
  * drop the `_armed_stop()` floor from the hold-until-second-target branch
    -> `test_no_retreat_when_holding_until_the_second_target` fails, the stop widens back to the
    frozen entry stop the moment the first rung is touched.
"""
from types import SimpleNamespace

import pytest

from strategies.python.sos_fade.config import SosFadeConfig
from strategies.python.sos_fade.execution import Decision, Execution, _Pending

ENTRY, STOP = 100.0, 98.0          # risk 2.00, so 1R = 2.00 of price
RISK = ENTRY - STOP
# ⚠ The rungs handed in here are NOT the rungs the trade manages against, and that cost a red
# test to find out. A reclaim re-prices its first rung off its OWN target setting when the
# position opens (3.0R by default, so 106.00 on this trade) whatever `_Pending` carried. Parking
# these two at 500 therefore parks only the SECOND rung. The walks below stay under 3.0R instead,
# so what they measure is the PRE-RUNG rule rather than a staged ladder; the one test that needs
# a touched rung fires it by hand through `stage_at_r`.
TP1, TP2 = 500.0, 510.0
PRE_RUNG_R = 2.75


def _walk(cfg, src, upto_r=PRE_RUNG_R, step_r=0.25, stage_at_r=None,
          cap_at_rung=False):
    """Open one long and walk its favourable excursion forward, returning the stop at each step.

    `stage_at_r` fires the first rung partway up, which is how the hold-until-second-target
    branch is reached without needing a real fill.
    """
    ex = Execution(cfg)
    pend = _Pending(1, ENTRY, 1.0, STOP, TP1, TP2, 1000, src=src)
    bar = SimpleNamespace(index=1, time_ms=0, open=ENTRY, high=ENTRY, low=ENTRY, close=ENTRY,
                          last_conf_high=None, last_conf_low=None)
    ex._open_position(pend, ENTRY, bar, Decision(index=1), kind="secondary" if src else "primary")

    # ⚠ EVERY METHOD PRICES ITS OWN FIRST RUNG, so there is no single ceiling that keeps all four
    # walks pre-rung: a reclaim's sits at 3.0R and a gap re-entry's at 1.25R. A walk that crosses
    # its own rung stages the ladder and the stop moves to breakeven for entirely correct reasons,
    # which reads exactly like the rule under test having fired. Callers that assert a stop is
    # UNMOVED cap here; the no-retreat walks deliberately do not, because the property has to hold
    # across staging too.
    if cap_at_rung:
        near = min((abs(p - ENTRY) / RISK for p in ex._stage_rungs()), default=upto_r)
        upto_r = min(upto_r, near - step_r)

    out = []
    r = 0.0
    while r <= upto_r + 1e-9:
        fav = ENTRY + r * RISK
        ex._advance_stage(SimpleNamespace(high=fav, low=ENTRY, close=fav,
                                          last_conf_high=None, last_conf_low=None))
        if stage_at_r is not None and r >= stage_at_r and ex._stage < 1:
            ex._stage = 1
        out.append((round(r, 4), ex._current_stop()))
        r += step_r
    return out


def _assert_never_retreats(walk):
    prev = None
    for r, stop in walk:
        if prev is not None:
            assert stop >= prev - 1e-9, (
                "the stop moved AWAY from the market at %.2fR in front: %.4f -> %.4f"
                % (r, prev, stop))
        prev = stop


# ── the defect this change exists to close ────────────────────────────────────────────────
def test_no_retreat_reclaim_under_the_old_collision():
    """The exact pairing that retreated: the primary's rule tight, the reclaim's looser and later.

    Before the rewrite the reclaim's branch sat ABOVE the general one and won, so the stop went
    99.00 -> 98.50 once the trade was 2.5R in front. Now the primary's pair does not reach a
    reclaim at all, so there is nothing to overwrite and nothing to retreat.
    """
    cfg = SosFadeConfig(exec_secondary=True, exec_sec_trigger="Reclaim Entry",
                        exec_be_arm_r=1.0, exec_be_keep_r=0.5,
                        exec_rec_be_r=2.5, exec_rec_be_keep_r=0.75)
    _assert_never_retreats(_walk(cfg, "reclaim", upto_r=4.0))


@pytest.mark.parametrize("arm", [1.0, 1.5, 2.0, 2.5, 2.75])
@pytest.mark.parametrize("keep", [0.0, 0.25, 0.5, 0.55, 0.75, 0.95])
def test_no_retreat_across_the_whole_swept_surface(arm, keep):
    """Every arm/keep pair the de-risking grid replayed, with the primary's rule also on."""
    cfg = SosFadeConfig(exec_secondary=True, exec_sec_trigger="Reclaim Entry",
                        exec_be_arm_r=1.0, exec_be_keep_r=0.5,
                        exec_rec_be_r=arm, exec_rec_be_keep_r=keep)
    _assert_never_retreats(_walk(cfg, "reclaim", upto_r=4.0))


def test_no_retreat_when_holding_until_the_second_target():
    """The second retreat path: a touched first rung used to hand back the FROZEN entry stop.

    A re-entry set to hold its initial stop until the second target returned `_sl` unconditionally
    when the first rung fired — wider than the stop its own protection rule had already set.
    """
    cfg = SosFadeConfig(exec_secondary=True, exec_sec_trigger="Reclaim Entry",
                        exec_sec_be_at="TP2",
                        exec_rec_be_r=1.0, exec_rec_be_keep_r=0.5)
    _assert_never_retreats(_walk(cfg, "reclaim", upto_r=4.0, stage_at_r=2.0))


# ── ownership: one rule per method, and nothing else is consulted ──────────────────────────
def test_each_method_reads_only_its_own_rule():
    """Turn ON exactly one method's rule and check the other methods do not move their stops."""
    armed = {"reclaim": dict(exec_rec_be_r=1.0, exec_rec_be_keep_r=0.5),
             "gap": dict(exec_gap_be_r=1.0, exec_gap_be_keep_r=0.5),
             "Structure shift": dict(exec_shift_be_r=1.0, exec_shift_be_keep_r=0.5)}
    trigger = {"reclaim": "Reclaim Entry", "gap": "FVG in zone",
               "Structure shift": "Structure shift"}
    protected = ENTRY - 0.5 * RISK

    for owner, kwargs in armed.items():
        cfg = SosFadeConfig(exec_secondary=True, exec_sec_trigger=trigger[owner], **kwargs)
        for src in armed:
            last = _walk(cfg, src, cap_at_rung=True)[-1][1]
            if src == owner:
                assert last == pytest.approx(protected), (
                    "%s's own rule did not move its stop" % src)
            else:
                assert last == pytest.approx(STOP), (
                    "%s's stop moved on %s's rule — the methods are not independent"
                    % (src, owner))


def test_the_primary_rule_no_longer_reaches_a_re_entry():
    """The behaviour change, stated on its own: the shared rule is the PRIMARY's now."""
    cfg = SosFadeConfig(exec_secondary=True, exec_sec_trigger="Reclaim Entry",
                        exec_be_arm_r=1.0, exec_be_keep_r=0.5)
    assert _walk(cfg, None, cap_at_rung=True)[-1][1] == pytest.approx(ENTRY - 0.5 * RISK)
    for src in ("reclaim", "gap", "Structure shift"):
        assert _walk(cfg, src, cap_at_rung=True)[-1][1] == pytest.approx(STOP), (
            "%s read the primary's rule" % src)


def test_unnamed_secondary_gets_no_movement():
    """A re-entry whose trigger never named itself has no rule of its own, so nothing moves.

    ⚠ Deliberate, not a fallthrough: reinstating the primary's pair here is the shared fallback
    the whole change removes, and it is what used to apply. It can only ever leave the frozen
    entry stop in place — never widen one that has already moved.
    """
    cfg = SosFadeConfig(exec_secondary=True, exec_sec_trigger="Reclaim Entry",
                        exec_be_arm_r=1.0, exec_be_keep_r=0.5,
                        exec_rec_be_r=1.0, exec_rec_be_keep_r=0.5)
    ex = Execution(cfg)
    pend = _Pending(1, ENTRY, 1.0, STOP, TP1, TP2, 1000)          # no `src`
    bar = SimpleNamespace(index=1, time_ms=0, open=ENTRY, high=ENTRY, low=ENTRY, close=ENTRY,
                          last_conf_high=None, last_conf_low=None)
    ex._open_position(pend, ENTRY, bar, Decision(index=1), kind="secondary")
    assert ex._protect_rule() == (-1.0, 0.0)


# ── the shipped ladder does not move ───────────────────────────────────────────────────────
def test_every_method_ships_with_its_rule_at_never_move():
    """All four pairs default to -1 / 0.0, which is what keeps the parity gate green."""
    cfg = SosFadeConfig()
    for arm, keep in (("exec_be_arm_r", "exec_be_keep_r"),
                      ("exec_rec_be_r", "exec_rec_be_keep_r"),
                      ("exec_gap_be_r", "exec_gap_be_keep_r"),
                      ("exec_shift_be_r", "exec_shift_be_keep_r")):
        assert getattr(cfg, arm) == -1.0, arm
        assert getattr(cfg, keep) == 0.0, keep


def test_shipped_settings_leave_the_stop_alone_for_every_method():
    cfg = SosFadeConfig(exec_secondary=True, exec_sec_trigger="Reclaim Entry")
    for src in (None, "reclaim", "gap", "Structure shift"):
        for _r, stop in _walk(cfg, src, cap_at_rung=True):
            assert stop == pytest.approx(STOP)
