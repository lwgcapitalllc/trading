# CLAUDE.md — Regime Classifier Subsystem

**Purpose:** Canonical market regime classifier shared by live forex bots and the command-center backtest lab.
**Scope:** Regime classification logic only. No trading decisions, no MT5 operations, no UI.
**Status:** Production — live bots depend on this via `algos/shared/shared_regime.py`.
**Last reviewed:** 2026-06-12

---

## Key paths

```
engines/regime/
├── classifier.py      ← compute_signals(), classify_regime()
├── thresholds.py      ← all configurable cutoffs as module-level constants
├── __init__.py        ← re-exports the public API
├── CLAUDE.md          ← this file
└── REGIME_CLASSIFIER.md ← plain-English algorithm doc
```

---

## Public API

```python
from regime import classify_regime, compute_signals

# Canonical call — returns a label string
label = classify_regime(df_short, df_long)
# Returns: TRENDING | TRANSITIONING | RANGING | HIGH_VOLATILITY | LOW_VOLATILITY | UNKNOWN

# Signal values (useful for diagnostics and the lab's Performance by Regime table)
sigs = compute_signals(df_short, df_long)
# → {"adx": float, "atr_ratio": float, "rsi_range": float, "score_norm": int} | None
```

---

## Consumers

| Consumer | Path |
|---|---|
| Live forex bots (SMC Trend, Mean Reversion, FFT) | `algos/shared/shared_regime.py` (thin shim — preserves `RegimeClassifier` class interface) |
| Command-center backtest lab (M4+) | `command-center/backend/services/` |

All consumers receive 5-label output directly. Each bot owns its own `REGIME_RISK_TABLE` mapping labels to `(risk_multiplier, trade_allowed)` pairs.

---

## Do

- Change thresholds only in `thresholds.py`. Never hardcode a number in `classifier.py`.
- When adding a new label or signal, update `REGIME_CLASSIFIER.md` in the same commit.
- Test any threshold change against the live bots' saved `regime_state_*.json` files to confirm behavior before deploying.
- Keep signal math (ADX, ATR ratio, RSI range) in `classifier.py` only. The shim must not reimplement any signal.

## Never do

- Add ML, hidden state, or stochastic elements. All rules must be deterministic.
- Import from `algos/`, `command-center/`, or `smart-money/`. This module has no subsystem dependencies.
- Rename or remove `classify_regime` or `compute_signals` from `__init__.py` without updating all consumers.
- Add a `mode` parameter back — the classifier was simplified to one 5-label output set on 2026-06-02.

---

## References

- Algorithm explained in plain English: `REGIME_CLASSIFIER.md`
- Shim and bot integration: `algos/shared/shared_regime.py`
- Monorepo context: `../CLAUDE.md`
