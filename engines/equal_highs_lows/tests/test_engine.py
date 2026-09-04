"""
Tests for the Equal Highs/Lows (EQH/EQL) state machine.

These pin the ported Pine behaviour (mpc_jarvis.pine "EQUAL HIGHS / LOWS"): ATR(50) Wilder
tolerance, strict price pivots (ta.pivothigh/ta.pivotlow) confirmed pivot_len bars late, a level
formed when two consecutive same-side pivots land within tolerance (price = outer of the pair),
FIFO eviction past the per-side cap, and close-through mitigation.

Two layers:
  * Structural hand-checks — the ATR warm-up tolerance (0 until the 50-bar seed), pivot confirmation
    lag, single-pivot-no-form → equal-second-pivot-forms (level = max/min, left anchor), EQH/EQL
    mitigation direction, and the FIFO cap.
  * A full independent reference (array-based: a whole-series pivot scan + the formation / eviction /
    mitigation rules) run against the streaming engine on a crafted random walk — asserting per-bar
    equality on every output AND that the series fires ≥1 EQH, ≥1 EQL, ≥1 mitigation, with at least
    one formation in the ATR>0 regime (nonzero tolerance), so the positive paths are exercised.

Full Pine<->Python parity is validated separately against a TradingView export
(equal_highs_lows/tools/compare_eq.py).

Run:  python3 -m pytest equal_highs_lows/tests/ -q      (from engines/)
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

_ENGINES_ROOT = Path(__file__).resolve().parents[2]
if str(_ENGINES_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINES_ROOT))

from equal_highs_lows import EqualHighsLowsEngine


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def run(bars, **kwargs):
    """Feed (high, low, close) triples; return the list of per-bar EqEvents."""
    eng = EqualHighsLowsEngine(**kwargs)
    return [eng.update(i, h, l, c) for i, (h, l, c) in enumerate(bars)]


# ─────────────────────────────────────────────────────────────────────────────
# Independent, array-based reference (structurally different from the engine).
# ─────────────────────────────────────────────────────────────────────────────

def ref_atr(highs, lows, closes, length):
    n = len(highs)
    trs = []
    for i in range(n):
        if i == 0:
            trs.append(highs[i] - lows[i])
        else:
            trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    atr = [None] * n
    seed = []
    val = None
    alpha = 1.0 / length
    for i in range(n):
        if val is None and len(seed) < length:
            seed.append(trs[i])
            if len(seed) == length:
                val = sum(seed) / length
                atr[i] = val
        else:
            val = alpha * trs[i] + (1.0 - alpha) * val
            atr[i] = val
    return atr


def ref_pivots_conf(vals, L, is_high):
    """Return, per bar, the (pivot_value, pivot_bar) confirmed at that bar, else None.

    A strict pivot sits at centre c (value strictly beyond every other bar in [c-L, c+L]); it is
    CONFIRMED L bars later, at bar c+L — exactly the streaming engine's centred-window timing.
    """
    n = len(vals)
    conf = [None] * n
    for c in range(L, n - L):
        v = vals[c]
        strict = True
        for j in range(c - L, c + L + 1):
            if j == c:
                continue
            if is_high:
                if v <= vals[j]:
                    strict = False
                    break
            else:
                if v >= vals[j]:
                    strict = False
                    break
        if strict:
            conf[c + L] = (v, c)
    return conf


def ref_run(highs, lows, closes, pivot_len=2, atr_mult=0.1, max_levels=6, atr_len=50):
    n = len(highs)
    atr = ref_atr(highs, lows, closes, atr_len)
    conf_h = ref_pivots_conf(highs, pivot_len, True)
    conf_l = ref_pivots_conf(lows, pivot_len, False)

    prev_ph = prev_pl = None
    eqh = []  # list of prices, oldest→newest
    eql = []
    out = []
    for i in range(n):
        tol = 0.0 if atr[i] is None else atr[i] * atr_mult
        formed = 0
        # EQH
        if conf_h[i] is not None:
            ph, _ = conf_h[i]
            if prev_ph is not None and abs(ph - prev_ph) <= tol:
                eqh.append(max(ph, prev_ph))
                formed += 1
                while len(eqh) > max_levels:
                    eqh.pop(0)
            prev_ph = ph
        # EQL
        if conf_l[i] is not None:
            pl, _ = conf_l[i]
            if prev_pl is not None and abs(pl - prev_pl) <= tol:
                eql.append(min(pl, prev_pl))
                formed += 1
                while len(eql) > max_levels:
                    eql.pop(0)
            prev_pl = pl
        # Mitigation
        mit = 0
        keep_h = []
        for p in eqh:
            if closes[i] > p:
                mit += 1
            else:
                keep_h.append(p)
        eqh = keep_h
        keep_l = []
        for p in eql:
            if closes[i] < p:
                mit += 1
            else:
                keep_l.append(p)
        eql = keep_l
        out.append({"tol": tol, "formed": formed, "mit": mit,
                    "eqh": list(eqh), "eql": list(eql)})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Hand-checks
# ─────────────────────────────────────────────────────────────────────────────

def test_atr_tolerance_warmup():
    """eqTol is 0 until ATR(50) seeds (bar index 49); then ATR×0.1. With constant TR=2, tol=0.2."""
    # Flat price with high=close+1, low=close-1 → TR=2 every bar after bar 0 (also 2 on bar 0).
    bars = [(101.0, 99.0, 100.0)] * 60
    evs = run(bars)
    for i in range(49):
        assert evs[i].tolerance == 0.0, f"bar {i} tol should be 0 during ATR warm-up"
    assert abs(evs[49].tolerance - 0.2) < 1e-9   # ATR seeds at bar 49 → 2.0 × 0.1
    assert abs(evs[59].tolerance - 0.2) < 1e-9


def test_pivot_confirmation_lag():
    """A strict pivot high at bar 2 is only reported at bar 4 (pivot_len=2 bars later)."""
    bars = [
        (1.0, 0.0, 0.5),
        (2.0, 0.5, 1.0),
        (5.0, 1.0, 2.0),   # bar 2: strict pivot high
        (2.0, 0.5, 1.0),
        (1.0, 0.0, 0.5),
    ]
    evs = run(bars)
    assert evs[2].pivot_high is None      # not yet confirmed
    assert evs[3].pivot_high is None
    assert evs[4].pivot_high == 5.0       # confirmed 2 bars late
    assert all(e.pivot_high is None for e in (evs[0], evs[1]))


def test_eqh_forms_on_equal_second_pivot():
    """No level from one pivot; an equal second strict pivot high forms an EQH at max, anchored left."""
    bars = [
        (1.0, 0.0, 0.5),
        (2.0, 0.5, 1.0),
        (5.0, 1.0, 2.0),   # bar 2: pivot high (confirms bar 4) → latched, no level yet
        (2.0, 0.5, 1.0),
        (1.0, 0.0, 0.5),
        (2.0, 0.5, 1.0),
        (5.0, 1.0, 2.0),   # bar 6: equal pivot high (confirms bar 8) → EQH forms
        (2.0, 0.5, 1.0),
        (1.0, 0.0, 0.5),
    ]
    evs = run(bars)
    assert not any(e.formed for e in evs[:8])          # nothing before the second pivot confirms
    assert len(evs[8].formed) == 1
    lvl = evs[8].formed[0]
    assert lvl.is_high is True
    assert lvl.price == 5.0                            # max(5, 5)
    assert lvl.left_bar == 2                           # anchored at the FIRST pivot's bar
    assert lvl.formed_bar == 8
    assert evs[8].active_eqh == [5.0]
    assert evs[8].active_eql == []


def test_eqh_mitigation_on_close_above():
    """An active EQH is taken when a later bar CLOSES above it."""
    bars = [
        (1.0, 0.0, 0.5), (2.0, 0.5, 1.0), (5.0, 1.0, 2.0), (2.0, 0.5, 1.0), (1.0, 0.0, 0.5),
        (2.0, 0.5, 1.0), (5.0, 1.0, 2.0), (2.0, 0.5, 1.0), (1.0, 0.0, 0.5),   # EQH @5 at bar 8
        (6.0, 4.0, 6.0),                                                        # bar 9: close 6 > 5 → taken
    ]
    evs = run(bars)
    assert evs[8].active_eqh == [5.0]
    assert len(evs[9].mitigated) == 1
    assert evs[9].mitigated[0].price == 5.0
    assert evs[9].active_eqh == []


def test_eql_forms_and_mitigates_on_close_below():
    """Mirror side: two equal strict pivot lows form an EQL at min; a close below takes it."""
    bars = [
        (10.0, 9.0, 9.5),
        (9.5, 8.0, 8.5),
        (9.0, 5.0, 6.0),   # bar 2: pivot low @5
        (9.5, 8.0, 8.5),
        (10.0, 9.0, 9.5),
        (9.5, 8.0, 8.5),
        (9.0, 5.0, 6.0),   # bar 6: equal pivot low @5 → EQL forms at bar 8
        (9.5, 8.0, 8.5),
        (10.0, 9.0, 9.5),
        (6.0, 4.0, 4.0),   # bar 9: close 4 < 5 → taken
    ]
    evs = run(bars)
    assert len(evs[8].formed) == 1
    lvl = evs[8].formed[0]
    assert lvl.is_high is False
    assert lvl.price == 5.0                            # min(5, 5)
    assert evs[8].active_eql == [5.0]
    assert len(evs[9].mitigated) == 1 and evs[9].active_eql == []


def test_fifo_cap():
    """With max_levels=2, forming three EQH levels keeps only two active (oldest evicted)."""
    # Four equal strict pivot highs at bars 2,6,10,14 → three formations (each with its predecessor).
    seg = [(1.0, 0.0, 0.5), (2.0, 0.5, 1.0), (5.0, 1.0, 2.0), (2.0, 0.5, 1.0)]
    bars = seg * 4 + [(1.0, 0.0, 0.5)]
    evs = run(bars, max_levels=2)
    eqh_formed = sum(1 for e in evs for l in e.formed if l.is_high)
    assert eqh_formed == 3                             # equal pivot highs at 2,6,10,14 → 3 pairs
    assert len(evs[-1].active_eqh) == 2                # capped at 2 despite 3 formed


# ─────────────────────────────────────────────────────────────────────────────
# Full independent reference cross-check
# ─────────────────────────────────────────────────────────────────────────────

def _random_walk(n, seed):
    rng = random.Random(seed)
    highs, lows, closes = [], [], []
    price = 100.0
    for _ in range(n):
        price += rng.uniform(-1.5, 1.5)
        rng_span = rng.uniform(0.3, 2.0)
        c = price + rng.uniform(-0.5, 0.5)
        h = max(price, c) + rng_span
        l = min(price, c) - rng_span
        highs.append(h)
        lows.append(l)
        closes.append(c)
    return highs, lows, closes


def test_reference_cross_check():
    """Streaming engine == array reference, per bar, on a long random walk — with positive paths hit."""
    highs, lows, closes = _random_walk(600, seed=7)
    # A guaranteed ATR>0-regime EQH pair at the end: two near-equal (diff 0.001) strict spikes.
    base = closes[-1]
    tail = [
        (base + 0.5, base - 0.5, base),
        (base + 20.000, base + 1.0, base + 2.0),   # strict pivot high
        (base + 0.5, base - 0.5, base),
        (base + 0.4, base - 0.6, base - 0.1),
        (base + 20.001, base + 1.0, base + 2.0),   # near-equal strict pivot high (diff 0.001)
        (base + 0.5, base - 0.5, base),
        (base + 0.4, base - 0.6, base - 0.1),
    ]
    for h, l, c in tail:
        highs.append(h); lows.append(l); closes.append(c)

    bars = list(zip(highs, lows, closes))
    evs = run(bars)
    ref = ref_run(highs, lows, closes)

    n_formed = n_mit = 0
    formed_in_atr_regime_with_tol = False
    for i, (e, r) in enumerate(zip(evs, ref)):
        assert abs(e.tolerance - r["tol"]) < 1e-9, f"tol mismatch at bar {i}"
        assert len(e.formed) == r["formed"], f"formed mismatch at bar {i}"
        assert len(e.mitigated) == r["mit"], f"mitigated mismatch at bar {i}"
        assert e.active_eqh == r["eqh"], f"active_eqh mismatch at bar {i}"
        assert e.active_eql == r["eql"], f"active_eql mismatch at bar {i}"
        n_formed += len(e.formed)
        n_mit += len(e.mitigated)
        if e.formed and e.tolerance > 0.0:
            formed_in_atr_regime_with_tol = True

    assert n_formed >= 2, "series should form at least one EQH and one EQL"
    assert any(l.is_high for e in evs for l in e.formed), "no EQH formed"
    assert any(not l.is_high for e in evs for l in e.formed), "no EQL formed"
    assert n_mit >= 1, "series should mitigate at least one level"
    assert formed_in_atr_regime_with_tol, "no formation exercised the nonzero-tolerance path"
