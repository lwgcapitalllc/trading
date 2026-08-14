"""B-LEG tests — offline, no network.

Two layers: hand-traced BLegTracker unit tests (band-freeze maths, arm, tap, staleness
death) driven with SimpleNamespace stand-ins for Signals/SeqState, and an end-to-end
driver run on the real engine stack over synthetic multi-day bars (proves the whole chain
wires up, records one decision per post-warmup bar, and books only finite trades).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "strategies" / "python"))
sys.path.insert(0, str(_ROOT / "backtest" / "tests"))

from _synth import synth_bars  # noqa: E402
from mpc_bleg import BLegConfig, BLegTracker, MpcBLegStrategy  # noqa: E402


def _sig(index, close, high, low, *, bull_sos=False, bear_sos=False,
         bbh=None, bbl=None, sbh=None, sbl=None,
         bbh_ms=None, bbl_ms=None, sbh_ms=None, sbl_ms=None):
    # ⚠ The four `*_ms` fields are carried even though most tests here ignore them. `Signals` is a
    # dataclass that ALWAYS has them, so a fixture that omitted them would be a shape production
    # never produces — and the tracker would have to reach for them with `getattr(..., None)`,
    # which permanently erases the difference between "no anchor" and "wrong object passed".
    return SimpleNamespace(
        index=index, close=close, high=high, low=low,
        bull_sos=bull_sos, bear_sos=bear_sos,
        bull_bos_high=bbh, bull_bos_low=bbl, bear_bos_high=sbh, bear_bos_low=sbl,
        bull_bos_high_ms=bbh_ms, bull_bos_low_ms=bbl_ms,
        bear_bos_high_ms=sbh_ms, bear_bos_low_ms=sbl_ms)


def _seq(bleg_arm_l=False, bleg_arm_s=False):
    return SimpleNamespace(bleg_arm_l=bleg_arm_l, bleg_arm_s=bleg_arm_s)


# ── BLEG_MAX conversion (Pine: days → bars, round-half-away-from-zero) ─────────────
def test_bleg_max_bars_from_days():
    # 1.25 days on 15m (900s) = the original 120 bars
    assert BLegTracker(BLegConfig(bleg_max_days=1.25), tf_seconds=900).bleg_max == 120
    # 1 day on 5m (300s) = 288 bars
    assert BLegTracker(BLegConfig(bleg_max_days=1.0), tf_seconds=300).bleg_max == 288
    # never below 1
    assert BLegTracker(BLegConfig(bleg_max_days=1.0), tf_seconds=10_000_000).bleg_max == 1


# ── band freeze on a bull SOS (Pine 3697-3710) ────────────────────────────────────
def test_band_freeze_long():
    tr = BLegTracker(BLegConfig(), tf_seconds=900)
    # leg 100 → 110, this bar's high 112. top = 0.5, bot = 0.382, inv = origin.
    st = tr.update(_sig(10, close=108, high=112, low=104, bull_sos=True, bbh=110, bbl=100),
                   _seq())
    assert st.l_top == 105.0                    # 100 + 10*0.5
    assert abs(st.l_bot - 103.82) < 1e-9        # 100 + 10*0.382
    assert st.l_inv == 100.0                    # leg origin (fib 1.0)
    assert st.l_tgt == 112.0                    # expansion extreme = this bar's high
    assert st.l_on is False and st.l_bar is None  # frozen, not armed yet


# ── target extends until armed, then arm freezes it (Pine 3728-3737) ──────────────
def test_arm_and_target_freeze():
    tr = BLegTracker(BLegConfig(), tf_seconds=900)
    tr.update(_sig(10, 108, 112, 104, bull_sos=True, bbh=110, bbl=100), _seq())
    # a later expansion bar (no SOS) pushes the target up while not yet armed
    st = tr.update(_sig(11, 109, 115, 106), _seq())
    assert st.l_tgt == 115.0 and st.l_on is False
    # arm on the continuation-BOS death captured by the sequence
    st = tr.update(_sig(12, 109, 114, 107), _seq(bleg_arm_l=True))
    assert st.l_on is True and st.l_bar == 12
    # once armed the target no longer tracks (frozen at the pre-arm extreme)
    st = tr.update(_sig(13, 109, 120, 108), _seq())
    assert st.l_tgt == 115.0


# ── tap + staleness death (Pine 3749-3753) ────────────────────────────────────────
def test_tap_and_staleness_death():
    cfg = BLegConfig(bleg_max_days=1.25)   # 120 bars on 15m
    tr = BLegTracker(cfg, tf_seconds=900)
    tr.update(_sig(10, 108, 112, 104, bull_sos=True, bbh=110, bbl=100), _seq())
    tr.update(_sig(11, 109, 114, 106), _seq(bleg_arm_l=True))   # armed @ bar 11
    # price taps the 0.5 band (low <= top=105) → tapped, still on
    st = tr.update(_sig(12, 106, 107, 104.9), _seq())
    assert st.l_tap is True and st.l_on is True
    # 120 bars after the arm bar it goes stale
    st = tr.update(_sig(11 + 121, 106, 107, 106), _seq())
    assert st.l_on is False


# ── invalidation death: a close past the leg origin (Pine 3752) ───────────────────
def test_invalidation_death_long():
    tr = BLegTracker(BLegConfig(), tf_seconds=900)
    tr.update(_sig(10, 108, 112, 104, bull_sos=True, bbh=110, bbl=100), _seq())
    tr.update(_sig(11, 109, 114, 106), _seq(bleg_arm_l=True))
    st = tr.update(_sig(12, 99.5, 108, 99), _seq())   # close 99.5 < inv 100
    assert st.l_on is False


# ── deepest-band-wins migration keeps the farther band on a fresh untapped SOS ────
def test_deepest_band_migration():
    tr = BLegTracker(BLegConfig(), tf_seconds=900)
    tr.update(_sig(10, 108, 112, 104, bull_sos=True, bbh=110, bbl=100), _seq())
    tr.update(_sig(11, 109, 114, 106), _seq(bleg_arm_l=True))  # live, untapped, top=105
    # a fresh same-side SOS whose 0.5 (106) is NEARER price(109) than the current top(105):
    # |106-109|=3 vs |105-109|=4 → keep the deeper (farther) existing band, don't migrate.
    st = tr.update(_sig(12, 109, 114, 107, bull_sos=True, bbh=112, bbl=100), _seq())
    assert st.l_top == 105.0   # unchanged — the deeper band won


# ── end-to-end on the real engine stack ───────────────────────────────────────────
def test_driver_runs_end_to_end():
    strat = MpcBLegStrategy().run(synth_bars(12), warmup=100)
    assert len(strat.decisions) == 12 * 96 - 100
    assert isinstance(strat.execution.equity, float)
    for t in strat.execution.trades:
        assert t.r == t.r          # not NaN
        assert t.qty > 0


def test_driver_is_deterministic():
    a = MpcBLegStrategy().run(synth_bars(8))
    b = MpcBLegStrategy().run(synth_bars(8))
    assert [d.long_armed for d in a.decisions] == [d.long_armed for d in b.decisions]
    assert len(a.execution.trades) == len(b.execution.trades)


def test_longs_and_shorts_off_means_no_trades():
    strat = MpcBLegStrategy(BLegConfig(exec_longs=False, exec_shorts=False)).run(synth_bars(12))
    assert strat.execution.trades == []


def test_this_fork_records_no_blocked_setups():
    """The A+ bot's blocked-setup markers are deliberately NOT ported here: their reason codes
    answer "why was this A+ setup refused", and A+ never places an order in this fork — so the
    tags would report the opposite of what a reader assumes. The fork gets none by CONSTRUCTION
    (recording hangs off the parent's `_place_entries`, which `BLegExecution` overrides); this
    pins that, so restoring the parent's entry path can't quietly switch them on."""
    strat = MpcBLegStrategy().run(synth_bars(12), warmup=100)
    assert strat.execution.blocks == []


def test_this_fork_records_no_missed_setups():
    """Same call, same reason — the missed-setup confluences score how far an **A+** setup got,
    and A+ never trades here. Unlike the blocks this one is NOT free: the miss watch runs from
    `step()`, which this fork delegates straight to the parent, so it takes the explicit
    `_records_misses = False` opt-out. Pin it — a flag is much easier to flip by accident than
    an overridden method."""
    strat = MpcBLegStrategy().run(synth_bars(30), warmup=100)
    assert strat.execution.misses == []


# ── the re-defaulted exit/staleness levers (2026-08-06) ───────────────────────────
def test_this_fork_redefaults_the_time_stop_and_the_parent_keeps_its_own():
    """`exec_time_stop_hrs` is a FORK PIN. Both forks measured this lever on their own trades
    and got different answers — A+ sat on a 24h-40h plateau and ships 36, this fork sits on a
    4h-12h one and ships 8 — so inheriting would silently move every B-LEG exit to a number
    measured on a different strategy. The mode is deliberately NOT pinned: "Before TP1 only"
    is right on both.

    Measured here by real replay, 186,312 M15 bars, spread + swap charged:
        Off 111 / +6.50R / maxDD -12.01 · 36h 112 / +12.02R / -8.89 · 8h 114 / +17.56R / -5.15
    """
    from mpc_sos_fade import SosFadeConfig

    assert BLegConfig().exec_time_stop_hrs == 8.0
    assert SosFadeConfig().exec_time_stop_hrs == 36.0, \
        "the A+ parent must KEEP 36 — its own plateau is 24h-40h, measured on A+ trades"
    assert BLegConfig().exec_time_stop_mode == "Before TP1 only"
    assert SosFadeConfig().exec_time_stop_mode == "Before TP1 only", \
        "the MODE is shared on purpose — only the hours fork"


def test_the_time_stop_only_ever_fires_before_tp1():
    """The whole case for 8 hours rests on this: the lever cuts DEAD trades, never winners.
    If the stage gate were ever dropped the clock would start closing runners and the measured
    +17.56R would describe a strategy nobody shipped — which is exactly what `"Always"` does
    on the A+ fork (+97.32R against +142.17R).

    Read off the Pine rather than asserted about the Python, because the Pine is the half that
    has no test suite of its own and the `lStage == 0` term is the one a tidy-up would remove.
    """
    import re

    for name in ("mpc_b_leg_strategy.pine", "mpc_b_leg_strategy_export.pine"):
        src = (_ROOT / "indicators" / "strategies" / name).read_text()
        hits = [ln for ln in src.splitlines()
                if re.match(r"bool [ls]TimeUp = ", ln)]
        assert len(hits) == 2, f"{name}: expected a long and a short time-stop line, got {len(hits)}"
        for ln in hits:
            stage = "lStage" if ln.startswith("bool lTimeUp") else "sStage"
            assert f'execTimeStopMode == "Always" or {stage} == 0' in ln, \
                f"{name}: the stage gate is gone from `{ln.split('=')[0].strip()}` — the clock " \
                "would now cut winners too"


def test_this_fork_redefaults_the_trail_step_and_the_staleness_cap():
    """Both are FORK PINS, not inherited values, and both would silently revert if somebody
    "reconciled" this config with its parent's.

    `exec_trail_pct` is a percent of PRICE while a B leg's whole 1R is 0.13%-1.25% of price,
    so the parent's 1.0 makes one trail step larger than the entire risk and the ratchet can
    never climb off the stage-2 floor. That floor is exactly 1R here by construction
    (TP1 = 2*edge - inv, stop = inv), so the runner banks precisely +1.00R and hands back the
    rest — measured, 9 of 50 baseline trades exited at exactly that.

    `bleg_max_days` was 1.25 because the Pine input's `maxval` was 3; 4-5 days measures best
    and the cap was what had never been checked.
    """
    from mpc_sos_fade import SosFadeConfig

    assert BLegConfig().exec_trail_pct == 0.05
    assert SosFadeConfig().exec_trail_pct == 1.0, \
        "the A+ parent must KEEP 1.0 — its own sweep says the opposite (0.25% -> 43.6R vs 109.3R)"
    assert BLegConfig().bleg_max_days == 4.0


def test_the_staleness_cap_default_is_reachable_on_its_own_pine_input():
    """A default outside its input's own `maxval` is a config the Pine cannot express, which
    would put `compare_bleg.py` red on the first export taken at the shipped settings. The cap
    was raised 3 -> 6 in the same commit as the 1.25 -> 4.0 default; this reads the Pine rather
    than trusting the memory of having done it."""
    import re

    for name in ("mpc_b_leg_strategy.pine", "mpc_b_leg_strategy_export.pine"):
        src = (_ROOT / "indicators" / "strategies" / name).read_text()
        line = next(ln for ln in src.splitlines() if ln.startswith("float bLegMaxDays = input."))
        default = float(re.search(r"input\.float\(([\d.]+)", line).group(1))
        lo = float(re.search(r"minval = ([\d.]+)", line).group(1))
        hi = float(re.search(r"maxval = ([\d.]+)", line).group(1))
        assert default == BLegConfig().bleg_max_days, f"{name}: Pine default {default} != config"
        assert lo <= default <= hi, f"{name}: default {default} outside [{lo}, {hi}]"

        tl = next(ln for ln in src.splitlines() if ln.startswith("float execTrailPct = input."))
        td = float(re.search(r"input\.float\(([\d.]+)", tl).group(1))
        assert td == BLegConfig().exec_trail_pct, f"{name}: Pine execTrailPct {td} != config"

        # Same check for the time stop. It has a `minval` and no `maxval`, so only the floor
        # is asserted — 8.0 sitting under a 0.25 minval would be the same unexpressable-config
        # bug from the other end.
        hl = next(ln for ln in src.splitlines() if ln.startswith("float execTimeStopHrs = input."))
        hd = float(re.search(r"input\.float\(([\d.]+)", hl).group(1))
        hlo = float(re.search(r"minval = ([\d.]+)", hl).group(1))
        assert hd == BLegConfig().exec_time_stop_hrs, f"{name}: Pine execTimeStopHrs {hd} != config"
        assert hd >= hlo, f"{name}: default {hd} is below its own minval {hlo}"


def test_the_meta_descs_are_the_pine_tooltips_verbatim():
    """The lab row and the Pine input are ONE name and ONE explanation — the contract recorded
    in this meta file's own `_comment`. It is enforced here rather than remembered, because the
    failure mode is silent: the panel goes on describing the old behaviour and reads as correct.
    Asserts it MATCHED something first, so a renamed param cannot make this vacuously green."""
    import json
    import re

    pine = (_ROOT / "indicators" / "strategies" / "mpc_b_leg_strategy.pine").read_text().splitlines()
    meta = json.loads((_ROOT / "strategies" / "python" / "mpc_bleg"
                       / "mpc_bleg.meta.json").read_text())
    by_name = {p["name"]: p for p in meta["params"]}
    checked = 0
    for field, ty, var in (("bleg_max_days", "float", "bLegMaxDays"),
                           ("exec_trail_pct", "float", "execTrailPct"),
                           ("exec_time_stop_hrs", "float", "execTimeStopHrs"),
                           ("exec_time_stop_mode", "string", "execTimeStopMode")):
        line = next(ln for ln in pine if ln.startswith(f"{ty} {var} = input."))
        tip = re.search(r'tooltip = "((?:[^"\\]|\\.)*)"', line).group(1)
        assert by_name[field]["desc"] == tip, f"{field}: meta desc has drifted from the Pine tooltip"
        checked += 1
    assert checked == 4, "this test matched nothing — the params were renamed, not verified"
