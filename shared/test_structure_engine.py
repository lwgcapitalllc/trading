"""
Structure Engine — owner-validation test harness.

Three scenarios must pass before integrating into bot_fft.py:
  1. Walkthrough  — HL, BOS → HH 4520, BOS → HH 4540, retracement
  2. Wick fakeout — wick pierces HH, body-close stays under → no BOS
  3. SOS          — established bullish leg, body-close below HL → flip bearish

Run:  python shared/test_structure_engine.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from structure_engine import StructureEngine

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

_failures = []


def check(label: str, condition: bool) -> None:
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}")
    if not condition:
        _failures.append(label)


def candle(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close}


def bullish_bootstrap(base=4490.0, n=20):
    """20 gently rising candles; min close ≈ base, max close ≈ base+10."""
    result = []
    for i in range(n):
        o = base + i * 0.5
        c = o + 0.3
        result.append(candle(o, c + 0.2, o - 0.1, c))
    return result
    # After bootstrap: swing_low.body ≈ 4490.3, swing_high.body ≈ 4499.8


# =============================================================================
# Scenario 1 — Walkthrough
# =============================================================================
print("\n=== Scenario 1: Walkthrough ===")
eng = StructureEngine()

for c in bullish_bootstrap(base=4490.0):
    eng.update(c)

# State after bootstrap (not yet leg_established):
check("Bootstrap → bullish bias",       eng.bias == "bullish")
check("Bootstrap → leg NOT established", not eng.leg_established)
check("Bootstrap swing_high set",       eng.swing_high is not None)
check("Bootstrap swing_low set",        eng.swing_low  is not None)

bootstrap_hh = eng.swing_high.body   # ≈ 4499.8
bootstrap_hl = eng.swing_low.body    # ≈ 4490.3

# --- BOS 1: body-close above bootstrap HH → HH becomes 4521, HL = old HH body ---
r = eng.update(candle(4500.0, 4522.0, 4499.0, 4521.0))  # close 4521 > 4499.8
check("BOS 1 fires",                   r.bos)
check("BOS 1: leg established",        r.leg_established)
check("BOS 1: HH close ≈ 4521",        abs(r.swing_high.body - 4521.0) < 0.01)
check("BOS 1: new HL = old HH body",   abs(r.swing_low.body - bootstrap_hh) < 0.01)

hh_after_bos1 = r.swing_high.body    # 4521.0
check("BOS 1: prev_swing_low = bootstrap HL", abs(r.prev_swing_low.body - bootstrap_hl) < 0.01)
# _bos_level = 4521.0 (new HH close)

# --- Consolidation candle (bullish, below new HH — no BOS, no event) ---
# close=4520 < HH=4521, bullish so no RETRACEMENT check
r = eng.update(candle(4519.0, 4525.0, 4518.0, 4520.0))  # bullish, close below HH
check("Extension: no BOS",             not r.bos)
check("Extension: no RETR",            not r.retracement_began)

# --- BOS 2: body-close above 4521 → HH 4541, HL = 4521 ---
r = eng.update(candle(4521.0, 4542.0, 4519.0, 4541.0))  # close 4541 > 4521
check("BOS 2 fires",                   r.bos)
check("BOS 2: HH close ≈ 4541",        abs(r.swing_high.body - 4541.0) < 0.01)
check("BOS 2: new HL ≈ 4521 (old HH)", abs(r.swing_low.body - hh_after_bos1) < 0.01)
check("BOS 2: prev_swing_low = BOS1 HL (old bootstrap HH)", abs(r.prev_swing_low.body - bootstrap_hh) < 0.01)
# After BOS 2: _bos_level = 4541, HL = 4521

# --- Pre-retracement: bullish candle just below bos_level — no event ---
r = eng.update(candle(4539.0, 4543.0, 4538.0, 4540.0))  # bullish, close < bos_level=4541
check("Pre-retr candle: no RETR",      not r.retracement_began)

# --- Retracement: first bearish body-close back under bos_level=4541 and above HL=4521 ---
r = eng.update(candle(4535.0, 4536.0, 4524.0, 4525.0))  # bearish, 4521 < close=4525 < 4541
check("RETRACEMENT_BEGAN fires",       r.retracement_began)
check("No BOS on retracement candle",  not r.bos)
check("Still bullish after retr",      r.bias == "bullish")

# RETRACEMENT_BEGAN must not fire again on next bearish close above HL
r = eng.update(candle(4526.0, 4527.0, 4521.5, 4522.0))  # bearish, close 4522 > HL=4521
check("RETR does not fire twice",      not r.retracement_began)


# =============================================================================
# Scenario 2 — Wick-only fakeout (no BOS)
# =============================================================================
print("\n=== Scenario 2: Wick-only fakeout ===")
eng2 = StructureEngine()

for c in bullish_bootstrap(base=4490.0):
    eng2.update(c)

hh = eng2.swing_high.body   # ≈ 4499.8

# First BOS to establish leg
eng2.update(candle(4500.0, 4515.0, 4499.0, 4514.0))  # BOS: close 4514 > 4499.8

hh2 = eng2.swing_high.body  # 4514.0

# Fakeout: high wicks above HH but body-close stays under it
r = eng2.update(candle(4512.0, 4518.0, 4511.0, 4513.0))  # close 4513 < 4514 → no BOS
check("Wick above HH — no BOS registered", not r.bos)
check("HH unchanged after wick fakeout",   abs(r.swing_high.body - hh2) < 0.01)

# A true BOS for comparison — body-close above HH
r = eng2.update(candle(4513.0, 4525.0, 4512.0, 4521.0))  # close 4521 > 4514
check("Genuine BOS after fakeout fires",   r.bos)
check("HH updated to 4521",                abs(r.swing_high.body - 4521.0) < 0.01)


# =============================================================================
# Scenario 3 — SOS: established bullish leg flips to bearish
# =============================================================================
print("\n=== Scenario 3: SOS (shift of structure) ===")
eng3 = StructureEngine()

for c in bullish_bootstrap(base=4490.0):
    eng3.update(c)

# BOS to establish leg (leg_established = True)
eng3.update(candle(4500.0, 4522.0, 4499.0, 4521.0))  # BOS → HH=4521, HL=old bootstrap HH

hl_level = eng3.swing_low.body   # new HL = old bootstrap HH ≈ 4499.8

check("Before SOS: bullish",          eng3.bias == "bullish")
check("Before SOS: leg established",  eng3.leg_established)

# Candle that wicks under HL but body-closes above it — no SOS
r = eng3.update(candle(4502.0, 4504.0, 4497.0, 4501.0))  # close 4501 > 4499.8
check("Wick under HL: no SOS",        not r.sos)
check("Bias still bullish",           r.bias == "bullish")

# SOS candle: body-close below the HL
r = eng3.update(candle(4501.0, 4502.0, 4496.0, 4497.0))  # close 4497 < 4499.8
check("SOS fires",                    r.sos)
check("Bias flips to bearish",        r.bias == "bearish")
check("Leg NOT established after SOS", not r.leg_established)

# Now engine tracks LH/LL in bearish mode
# Next bearish BOS should fire
r = eng3.update(candle(4497.0, 4498.0, 4480.0, 4481.0))  # close 4481 < 4497 → bearish BOS
check("Bearish BOS fires after flip",  r.bos)
check("Leg established bearish",       r.leg_established)
check("Bias still bearish",            r.bias == "bearish")


# =============================================================================
# Summary
# =============================================================================
print("\n" + "=" * 50)
if _failures:
    print(f"RESULT: {len(_failures)} FAILED")
    for f in _failures:
        print(f"  ✗ {f}")
    sys.exit(1)
else:
    print("RESULT: ALL CHECKS PASSED")
    sys.exit(0)
