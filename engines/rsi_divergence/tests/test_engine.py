"""
Tests for the RSI-divergence state machine.

These pin the ported Pine behaviour (mpc_jarvis.pine "RSI DIVERGENCE — regular divergence at the
extremes"): Wilder's RSI (ta.rsi), strict RSI pivots (ta.pivotlow/ta.pivothigh) confirmed pivot_len
bars late, and a regular divergence at the extremes — a bullish signal on a lower price low with a
higher RSI low from oversold, the bearish mirror from overbought — plus the live confluence flags.

Two layers:
  * Structural hand-checks — RSI warm-up, RSI value vs an independent standard Wilder implementation,
    pivot timing/value, and the live-flag window.
  * A full independent reference (array-based: standard Wilder RSI + a pivot scan + the divergence
    rule) run against the streaming engine on crafted multi-swing series — asserting per-bar equality
    on every output AND that the series actually fires ≥1 bullish and ≥1 bearish divergence, so the
    positive path is exercised, not just agreement on "nothing happened".

Full Pine<->Python parity is validated separately against a TradingView export
(rsi_divergence/tools/compare_rsi_div.py).

Run:  python3 -m pytest rsi_divergence/tests/ -q      (from engines/)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from rsi_divergence import RsiDivergenceEngine

# ─────────────────────────────────────────────────────────────────────────────
# Independent reference implementation (array-based, structurally different from
# the streaming engine) — standard Wilder RSI + pivot scan + divergence rule.
# ─────────────────────────────────────────────────────────────────────────────


def _rsi_from(avg_gain, avg_loss):
    if avg_loss == 0.0:
        return 100.0
    if avg_gain == 0.0:
        return 0.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def ref_wilder_rsi(closes, length):
    """Standard textbook Wilder RSI: SMA seed at bar `length`, then the (n-1)/n recursion."""
    n = len(closes)
    rsi = [None] * n
    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        chg = closes[i] - closes[i - 1]
        gains[i] = chg if chg > 0 else 0.0
        losses[i] = -chg if chg < 0 else 0.0
    if n > length:
        ag = sum(gains[1 : length + 1]) / length
        al = sum(losses[1 : length + 1]) / length
        rsi[length] = _rsi_from(ag, al)
        for i in range(length + 1, n):
            ag = (ag * (length - 1) + gains[i]) / length
            al = (al * (length - 1) + losses[i]) / length
            rsi[i] = _rsi_from(ag, al)
    return rsi


def ref_pivots(vals, L):
    """(pivot_low, pivot_high) arrays: value at the bar the pivot is CONFIRMED (candidate L back)."""
    n = len(vals)
    pl = [None] * n
    ph = [None] * n
    for i in range(2 * L, n):
        window = vals[i - 2 * L : i + 1]  # 2L+1 wide; candidate is window[L] == vals[i-L]
        if any(v is None for v in window):
            continue
        cand = window[L]
        others = [window[j] for j in range(len(window)) if j != L]
        if all(cand < v for v in others):
            pl[i] = cand
        if all(cand > v for v in others):
            ph[i] = cand
    return pl, ph


def ref_run(highs, lows, rsi, pivot_len=5, os_=25.0, ob=75.0, valid=100):
    """Full reference output per bar, mirroring the Pine block with array logic.

    Takes a precomputed `rsi` array (rather than closes) so the structural pivot/divergence/flag
    logic is validated on the SAME RSI values the engine used — RSI math is checked independently in
    test_rsi_matches_standard_wilder. (Feeding a second, algebraically-equal float formulation of
    Wilder's RMA here would only inject ~1e-13 tie-breaking noise into the strict pivot test on
    synthetic data — real RSI never ties exactly.)"""
    n = len(rsi)
    pl, ph = ref_pivots(rsi, pivot_len)

    prev_low_rsi = prev_low_price = prev_low_bar = None
    prev_high_rsi = prev_high_price = prev_high_bar = None
    last_bull = last_bear = None
    out = []
    for i in range(n):
        bull_pulse = bear_pulse = False
        if pl[i] is not None:
            p_low = lows[i - pivot_len]
            p_bar = i - pivot_len
            if prev_low_rsi is not None:
                if (
                    p_low < prev_low_price
                    and pl[i] > prev_low_rsi
                    and min(pl[i], prev_low_rsi) <= os_
                ):
                    last_bull = p_bar
                    bull_pulse = True
            prev_low_rsi, prev_low_price, prev_low_bar = pl[i], p_low, p_bar
        if ph[i] is not None:
            p_high = highs[i - pivot_len]
            p_bar = i - pivot_len
            if prev_high_rsi is not None:
                if (
                    p_high > prev_high_price
                    and ph[i] < prev_high_rsi
                    and max(ph[i], prev_high_rsi) >= ob
                ):
                    last_bear = p_bar
                    bear_pulse = True
            prev_high_rsi, prev_high_price, prev_high_bar = ph[i], p_high, p_bar
        bull_active = last_bull is not None and i - last_bull <= valid
        bear_active = last_bear is not None and i - last_bear <= valid
        out.append(
            {
                "rsi": rsi[i],
                "pl": pl[i],
                "ph": ph[i],
                "bull": bull_pulse,
                "bear": bear_pulse,
                "bull_active": bull_active,
                "bear_active": bear_active,
                "bull_age": None if last_bull is None else i - last_bull,
                "bear_age": None if last_bear is None else i - last_bear,
            }
        )
    return out


# ── deterministic multi-swing series (drives RSI to both extremes; makes divergences) ──


def _swing_series():
    """A deterministic path: an oscillation (sine) that drives the RSI to both extremes, on a
    two-phase drift — a downtrend that starts steep then goes gentle (successive lower price lows on
    a HIGHER RSI low => bullish divergences), then an uptrend that starts steep then goes gentle
    (higher price highs on a LOWER RSI high => bearish divergences). Produces several of each."""
    closes = []
    for k in range(220):  # downtrend phase
        drift = -0.9 * k if k < 90 else -0.9 * 90 - 0.35 * (k - 90)
        closes.append(round(1000.0 + drift + 22.0 * math.sin(k / 6.0), 2))
    for k in range(220):  # uptrend phase
        drift = 0.9 * k if k < 90 else 0.9 * 90 + 0.35 * (k - 90)
        closes.append(round(700.0 + drift + 22.0 * math.sin(k / 6.0), 2))
    highs = [c + 0.7 for c in closes]
    lows = [c - 0.7 for c in closes]
    return highs, lows, closes


def _feed_all(eng, highs, lows, closes):
    """Run the engine over the series; return (per-bar output dicts, engine rsi array)."""
    last_bull = last_bear = None
    out = []
    rsi = []
    for i, (h, l, c) in enumerate(zip(highs, lows, closes)):
        ev = eng.update(i, h, l, c)
        rsi.append(ev.rsi)
        for d in ev.detected:
            if d.is_bullish:
                last_bull = d.pivot_bar
            else:
                last_bear = d.pivot_bar
        out.append(
            {
                "rsi": ev.rsi,
                "pl": ev.pivot_low_rsi,
                "ph": ev.pivot_high_rsi,
                "bull": any(d.is_bullish for d in ev.detected),
                "bear": any(not d.is_bullish for d in ev.detected),
                "bull_active": ev.bull_active,
                "bear_active": ev.bear_active,
                "bull_age": None if last_bull is None else i - last_bull,
                "bear_age": None if last_bear is None else i - last_bear,
            }
        )
    return out, rsi


def _approx(a, b, tol=1e-9):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


# ── RSI warm-up + value ──


def test_rsi_is_none_until_length_then_defined():
    eng = RsiDivergenceEngine(rsi_len=14)
    closes = [1000.0 + i for i in range(20)]
    rsis = [eng.update(i, c + 1, c - 1, c).rsi for i, c in enumerate(closes)]
    assert all(r is None for r in rsis[:14])  # na warm-up: bars 0..13
    assert rsis[14] is not None  # first defined at bar == rsi_len


def test_rsi_matches_standard_wilder():
    eng = RsiDivergenceEngine(rsi_len=14)
    _, _, closes = _swing_series()
    ref = ref_wilder_rsi(closes, 14)
    got = [eng.update(i, c + 1, c - 1, c).rsi for i, c in enumerate(closes)]
    for i, (r, g) in enumerate(zip(ref, got)):
        assert _approx(r, g), f"RSI mismatch at bar {i}: ref={r} engine={g}"


# ── pivot detection ──


def test_pivot_low_confirms_late_at_the_trough():
    # For every pivot low the engine confirms on the swing series, prove the timing/offset: the
    # reported value is the RSI of the candidate bar pivot_len bars back, and that candidate is a
    # strict local RSI minimum over the (2L+1)-bar window. Uses the engine's OWN RSI (no cross-impl
    # tie noise), so this pins the pivot geometry precisely.
    L = 5
    highs, lows, closes = _swing_series()
    eng = RsiDivergenceEngine(rsi_len=14, pivot_len=L)
    rsi = []
    confirmed = []
    for i, c in enumerate(closes):
        ev = eng.update(i, highs[i], lows[i], c)
        rsi.append(ev.rsi)
        if ev.pivot_low_rsi is not None:
            confirmed.append(i)
            assert _approx(ev.pivot_low_rsi, rsi[i - L]), f"bar {i}: pivot != rsi[i-L]"
            win = [rsi[i - 2 * L + j] for j in range(2 * L + 1)]
            assert all(win[L] < win[j] for j in range(2 * L + 1) if j != L)
    assert len(confirmed) >= 2, "the swing series must confirm several pivot lows"


# ── full reference cross-check (the centrepiece) ──


def test_engine_matches_reference_and_fires_both_divergences():
    highs, lows, closes = _swing_series()
    eng = RsiDivergenceEngine()  # defaults: 14 / 5 / 25 / 75 / 100
    got, rsi = _feed_all(eng, highs, lows, closes)
    ref = ref_run(highs, lows, rsi)

    for i, (g, r) in enumerate(zip(got, ref)):
        assert _approx(g["rsi"], r["rsi"]), f"rsi mismatch bar {i}"
        assert _approx(g["pl"], r["pl"]), f"pivot-low mismatch bar {i}"
        assert _approx(g["ph"], r["ph"]), f"pivot-high mismatch bar {i}"
        assert g["bull"] == r["bull"], f"bull pulse mismatch bar {i}"
        assert g["bear"] == r["bear"], f"bear pulse mismatch bar {i}"
        assert g["bull_active"] == r["bull_active"], f"bull_active mismatch bar {i}"
        assert g["bear_active"] == r["bear_active"], f"bear_active mismatch bar {i}"
        assert g["bull_age"] == r["bull_age"], f"bull_age mismatch bar {i}"
        assert g["bear_age"] == r["bear_age"], f"bear_age mismatch bar {i}"

    assert any(g["bull"] for g in got), "series should have fired a bullish divergence"
    assert any(g["bear"] for g in got), "series should have fired a bearish divergence"


def test_detected_divergence_carries_correct_anchors():
    highs, lows, closes = _swing_series()
    eng = RsiDivergenceEngine()
    bull = None
    bear = None
    for i, (h, l, c) in enumerate(zip(highs, lows, closes)):
        for d in eng.update(i, h, l, c).detected:
            if d.is_bullish and bull is None:
                bull = d
            if not d.is_bullish and bear is None:
                bear = d
    assert bull is not None and bear is not None
    # Bullish: lower price low but higher RSI low, the lower RSI from oversold.
    assert bull.pivot_price < bull.prev_price
    assert bull.pivot_rsi > bull.prev_rsi
    assert min(bull.pivot_rsi, bull.prev_rsi) <= 25.0
    # Bearish: higher price high but lower RSI high, the higher RSI from overbought.
    assert bear.pivot_price > bear.prev_price
    assert bear.pivot_rsi < bear.prev_rsi
    assert max(bear.pivot_rsi, bear.prev_rsi) >= 75.0


# ── live-confluence flag window ──


def test_bull_active_expires_after_valid_bars():
    # Force one bullish divergence, then feed flat bars and watch the flag switch off exactly
    # valid_bars after the divergence's PIVOT bar (pivot is pivot_len bars behind confirmation).
    highs, lows, closes = _swing_series()
    eng = RsiDivergenceEngine(valid_bars=10)
    pivot_bar = None
    idx = 0
    outputs = []
    for i, (h, l, c) in enumerate(zip(highs, lows, closes)):
        ev = eng.update(i, h, l, c)
        outputs.append((i, ev.bull_active))
        for d in ev.detected:
            if d.is_bullish and pivot_bar is None:
                pivot_bar = d.pivot_bar
        idx = i
    assert pivot_bar is not None
    # keep feeding flat bars past the window; active must go false once age > 10
    flat = closes[-1]
    for k in range(1, 20):
        i = idx + k
        ev = eng.update(i, flat + 1, flat - 1, flat)
        expect = (i - pivot_bar) <= 10
        assert ev.bull_active == expect, f"bar {i}: age={i - pivot_bar} active={ev.bull_active}"


# ── negative conditions ──


def test_no_divergence_before_any_pivot_pair():
    # Fewer bars than a full pivot window can never confirm a divergence.
    eng = RsiDivergenceEngine(rsi_len=5, pivot_len=3)
    fired = False
    for i in range(6):  # < 2*pivot_len+1 windows possible
        ev = eng.update(i, 1000 + i, 999 + i, 1000 + i)
        fired = fired or bool(ev.detected)
    assert not fired


def _count(eng, highs, lows, closes, bullish):
    n = 0
    for i, (h, l, c) in enumerate(zip(highs, lows, closes)):
        n += sum(1 for d in eng.update(i, h, l, c).detected if d.is_bullish == bullish)
    return n


def test_oversold_gate_is_live():
    # A bullish divergence requires the lower of its two RSI lows to sit at/below the oversold level.
    # Raising that level admits more pivot pairs; lowering it admits fewer — proving the gate gates.
    highs, lows, closes = _swing_series()
    admissive = _count(RsiDivergenceEngine(oversold=100.0), highs, lows, closes, bullish=True)
    strict = _count(RsiDivergenceEngine(oversold=5.0), highs, lows, closes, bullish=True)
    assert admissive > strict >= 0


def test_overbought_gate_is_live():
    # Mirror: a bearish divergence requires the higher of its two RSI highs at/above overbought.
    highs, lows, closes = _swing_series()
    admissive = _count(RsiDivergenceEngine(overbought=0.0), highs, lows, closes, bullish=False)
    strict = _count(RsiDivergenceEngine(overbought=95.0), highs, lows, closes, bullish=False)
    assert admissive > strict >= 0
