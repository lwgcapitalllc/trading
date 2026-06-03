# CLAUDE.md — Regime Classifier Subsystem

**Purpose:** Canonical market regime classifier shared by live forex bots and the command-center backtest lab.
**Scope:** Regime classification logic only. No trading decisions, no MT5 operations, no UI.
**Status:** Production — live bots depend on this via `algos/shared/shared_regime.py`.
**Last reviewed:** 2026-06-02

---

## Key paths

```
regime/
├── classifier.py      ← compute_signals(), classify_regime(), coarse_label()
├── thresholds.py      ← all configurable cutoffs as module-level constants
├── __init__.py        ← re-exports the public API
├── CLAUDE.md          ← this file
└── REGIME_CLASSIFIER.md ← plain-English algorithm doc
```

---

## Public API

```python
from regime import classify_regime, compute_signals, coarse_label

# Canonical call — returns a label string
label = classify_regime(df_short, df_long, mode="fine")
# mode="coarse" returns 3 labels; mode="fine" returns up to 5

# Signal values (useful for diagnostics and the lab's Performance by Regime table)
sigs = compute_signals(df_short, df_long)
# → {"adx": float, "atr_ratio": float, "rsi_range": float, "score_norm": int} | None

# Display layer: convert a fine label to its 3-label equivalent
coarse = coarse_label("HIGH_VOLATILITY")  # → "RANGING"
```

---

## Consumers

| Consumer | Mode | Path |
|---|---|---|
| Live forex bots (Bot 1, Bot 2, FFT) | coarse | `algos/shared/shared_regime.py` (thin shim) |
| Command-center backtest lab (M4+) | fine | `command-center/backend/services/` |

The shim at `algos/shared/shared_regime.py` preserves the legacy `RegimeClassifier` class interface. Bot code is unchanged.

---

## Do

- Change thresholds only in `thresholds.py`. Never hardcode a number in `classifier.py`.
- When adding a new label or signal, update `REGIME_CLASSIFIER.md` in the same commit.
- Test any threshold change against the live bots' saved `regime_state_*.json` files to confirm behavior before deploying.
- Keep signal math (ADX, ATR ratio, RSI range) in `classifier.py` only. The shim must not reimplement any signal.

## Never do

- Add ML, hidden state, or stochastic elements. All rules must be deterministic.
- Import from `algos/`, `command-center/`, or `smart-money/`. This module has no subsystem dependencies.
- Change the coarse-mode scoring path without confirming bit-for-bit compatibility with the shim's output.
- Rename or remove `classify_regime`, `compute_signals`, or `coarse_label` from `__init__.py` without updating all consumers.

---

## References

- Algorithm explained in plain English: `REGIME_CLASSIFIER.md`
- Shim and bot integration: `algos/shared/shared_regime.py`
- Monorepo context: `../CLAUDE.md`
