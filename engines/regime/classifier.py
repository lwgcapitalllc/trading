"""
Canonical regime classifier for LWG Capital.

Public API:
  compute_signals(df_short, df_long, cfg=None) -> dict | None
  classify_regime(df_short, df_long, thresholds=None) -> str

df_short: higher-frequency dataframe (H1 for bots, daily for lab).
          ADX(14) and RSI range(14-period RSI, 20-bar rolling max/min) computed here.
df_long:  lower-frequency dataframe (H4 for bots, daily for lab — pass the same df twice).
          ATR ratio (14-period rolling ATR / 20-period rolling mean of that ATR) computed here.

Returns one of: TRENDING | TRANSITIONING | RANGING | HIGH_VOLATILITY | LOW_VOLATILITY | UNKNOWN
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import thresholds as _T


def compute_signals(
    df_short: pd.DataFrame,
    df_long: pd.DataFrame,
    cfg: dict | None = None,
) -> dict | None:
    """
    Compute ADX, ATR ratio, RSI range, and composite score.

    Returns a dict with keys: adx, atr_ratio, rsi_range, score_norm.
    Returns None when df lengths are below minimums or any signal is NaN.

    cfg: optional threshold overrides using the same key names as thresholds.py.
    """
    t = _resolve(cfg)

    if len(df_short) < t["MIN_ROWS_SHORT"] or len(df_long) < t["MIN_ROWS_LONG"]:
        return None

    adx = _adx(df_short)
    atr_ratio = _atr_ratio(df_long)
    rsi_range = _rsi_range(df_short)

    if any(np.isnan(v) for v in (adx, atr_ratio, rsi_range)):
        return None

    score = 0
    if adx >= t["ADX_TRENDING"]:
        score += 2
    elif adx >= t["ADX_RANGING"]:
        score += 1
    if atr_ratio >= t["ATR_EXPANDING"]:
        score += 2
    elif atr_ratio >= t["ATR_COMPRESSING"]:
        score += 1
    if rsi_range >= t["RSI_TRENDING"]:
        score += 2
    elif rsi_range >= t["RSI_RANGING"]:
        score += 1

    score_norm = min(5, round(score * 5 / 6))

    return {
        "adx": round(adx, 1),
        "atr_ratio": round(atr_ratio, 3),
        "rsi_range": round(rsi_range, 1),
        "score_norm": score_norm,
    }


def classify_regime(
    df_short: pd.DataFrame,
    df_long: pd.DataFrame,
    thresholds: dict | None = None,
) -> str:
    """
    Classify the current market regime.

    Returns TRENDING | TRANSITIONING | RANGING | HIGH_VOLATILITY | LOW_VOLATILITY
    Returns "UNKNOWN" when there is insufficient history or any signal is NaN.

    Score 3–5 → TRENDING. Score 2 → TRANSITIONING.
    Score 0–1 with high ATR ratio → HIGH_VOLATILITY.
    Score 0–1 with low ATR ratio  → LOW_VOLATILITY.
    Score 0–1 otherwise           → RANGING.
    """
    t = _resolve(thresholds)
    sigs = compute_signals(df_short, df_long, thresholds)

    if sigs is None:
        return "UNKNOWN"

    score_norm = sigs["score_norm"]

    if score_norm >= 3:
        return "TRENDING"
    if score_norm == 2:
        return "TRANSITIONING"

    # score_norm <= 1: split by volatility level
    atr_ratio = sigs["atr_ratio"]
    if atr_ratio >= t["HIGH_VOL_ATR"]:
        return "HIGH_VOLATILITY"
    if atr_ratio <= t["LOW_VOL_ATR"]:
        return "LOW_VOLATILITY"

    return "RANGING"


# ── Private signal calculators (identical math to shared_regime.py) ───────────


def _adx(df: pd.DataFrame, p: int = 14) -> float:
    h, l, c = df["high"], df["low"], df["close"].shift(1)
    pdm = h.diff().clip(lower=0)
    mdm = (-l.diff()).clip(lower=0)
    pdm = pdm.where(pdm > mdm, 0)
    mdm = mdm.where(mdm > pdm, 0)
    tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=p).mean()
    pdi = 100 * pdm.ewm(span=p).mean() / (atr + 1e-9)
    mdi = 100 * mdm.ewm(span=p).mean() / (atr + 1e-9)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi + 1e-9)
    return float(dx.ewm(span=p).mean().iloc[-1])


def _atr_ratio(df: pd.DataFrame, p: int = 14) -> float:
    h, l, c = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    atr = tr.rolling(p).mean()
    cur = float(atr.iloc[-1])
    avg = float(atr.rolling(20).mean().iloc[-1])
    return round(cur / avg, 3) if avg > 0 else 1.0


def _rsi_range(df: pd.DataFrame, p: int = 14) -> float:
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(p).mean()
    loss = (-delta.clip(upper=0)).rolling(p).mean()
    rsi = 100 - (100 / (1 + gain / (loss + 1e-9)))
    recent = rsi.tail(20)
    return float(recent.max() - recent.min())


def _resolve(cfg: dict | None) -> dict:
    defaults = {
        "ADX_TRENDING": _T.ADX_TRENDING,
        "ADX_RANGING": _T.ADX_RANGING,
        "ATR_EXPANDING": _T.ATR_EXPANDING,
        "ATR_COMPRESSING": _T.ATR_COMPRESSING,
        "RSI_TRENDING": _T.RSI_TRENDING,
        "RSI_RANGING": _T.RSI_RANGING,
        "HIGH_VOL_ATR": _T.HIGH_VOL_ATR,
        "LOW_VOL_ATR": _T.LOW_VOL_ATR,
        "MIN_ROWS_SHORT": _T.MIN_ROWS_SHORT,
        "MIN_ROWS_LONG": _T.MIN_ROWS_LONG,
    }
    if cfg:
        defaults.update(cfg)
    return defaults
