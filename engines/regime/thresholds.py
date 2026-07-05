"""
Regime classifier thresholds — all configurable cutoffs as module-level constants.

Coarse-mode thresholds match the pre-migration shared_regime.py exactly.
Fine-mode ATR bounds are applied only when score_norm <= 1 (the RANGING space).
"""

# ── Signal scoring thresholds (coarse mode — unchanged from shared_regime.py) ──

ADX_TRENDING    = 25    # ADX >= this → +2 trend score
ADX_RANGING     = 20    # ADX >= this (but < ADX_TRENDING) → +1

ATR_EXPANDING   = 1.2   # ATR ratio >= this → +2 (volatility expanding)
ATR_COMPRESSING = 0.8   # ATR ratio >= this (but < ATR_EXPANDING) → +1

RSI_TRENDING    = 35    # RSI 20-bar range >= this → +2 (directional swing)
RSI_RANGING     = 20    # RSI 20-bar range >= this (but < RSI_TRENDING) → +1

# ── Fine-mode ATR bounds (split the RANGING space) ───────────────────────────

HIGH_VOL_ATR    = 1.5   # score_norm <= 1 AND atr_ratio >= this → HIGH_VOLATILITY
LOW_VOL_ATR     = 0.5   # score_norm <= 1 AND atr_ratio <= this → LOW_VOLATILITY

# ── Minimum row requirements before signals are trusted ──────────────────────

MIN_ROWS_SHORT  = 34    # 14-period RSI + 20-bar rolling max/min window
MIN_ROWS_LONG   = 34    # 14-period ATR + 20-period rolling mean of ATR
