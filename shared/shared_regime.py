"""
shared_regime.py — Regime Classifier
Used by both Bot 1 and Bot 2. Each bot has its own state file.

Three signals scored every hour:
  ADX(14)    — trend strength (>25 trending, <20 ranging)
  ATR ratio  — current vs 20-period average (expansion vs compression)
  RSI range  — how wide RSI has swung over 20 bars (directional vs choppy)

Score 0–5:
  0–1 = RANGING     → Bot 1 pauses, Bot 2 trades full size
  2   = TRANSITIONING → both trade at reduced size
  3–5 = TRENDING    → Bot 1 trades full size, Bot 2 reduces
"""

import pandas as pd
import numpy as np
import json, logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("REGIME")

# Load regime thresholds from config.json if available
def _load_regime_config():
    cfg_file = Path(__file__).parent / "config.json"
    defaults = {
        "update_interval_minutes": 60,
        "adx_trending_threshold":  25,
        "adx_ranging_threshold":   20,
        "atr_ratio_expanding":     1.2,
        "atr_ratio_compressing":   0.8,
        "rsi_range_trending":      35,
        "rsi_range_ranging":       20,
    }
    if cfg_file.exists():
        with open(cfg_file) as f:
            cfg = json.load(f)
        return cfg.get("regime", defaults)
    return defaults

_RCFG = _load_regime_config()


class RegimeClassifier:
    def __init__(self, bot_name="BOT", update_minutes=None):
        self.bot_name       = bot_name
        self.update_minutes = update_minutes or _RCFG["update_interval_minutes"]
        self.current_regime = "TRENDING"
        self.regime_score   = 3
        self.last_updated   = None
        self._file          = f"regime_state_{bot_name}.json"
        self._load()

    def _load(self):
        if Path(self._file).exists():
            with open(self._file) as f:
                s = json.load(f)
            self.current_regime = s.get("regime", "TRENDING")
            self.regime_score   = s.get("score", 3)
            log.info(f"[{self.bot_name}] Loaded regime: {self.current_regime} "
                     f"(score={self.regime_score})")

    def _save(self):
        with open(self._file, "w") as f:
            json.dump({
                "regime":    self.current_regime,
                "score":     self.regime_score,
                "updated":   datetime.utcnow().isoformat(),
                "bot":       self.bot_name,
            }, f, indent=2)

    def needs_update(self) -> bool:
        if self.last_updated is None: return True
        elapsed = (datetime.utcnow() - self.last_updated).total_seconds() / 60
        return elapsed >= self.update_minutes

    def classify(self, df_h1: pd.DataFrame, df_h4: pd.DataFrame) -> dict:
        """Run all three signals and return classification dict."""
        adx       = self._adx(df_h1)
        atr_ratio = self._atr_ratio(df_h4)
        rsi_range = self._rsi_range(df_h1)

        score = 0
        if adx >= _RCFG["adx_trending_threshold"]:      score += 2
        elif adx >= _RCFG["adx_ranging_threshold"]:     score += 1
        if atr_ratio >= _RCFG["atr_ratio_expanding"]:   score += 2
        elif atr_ratio >= _RCFG["atr_ratio_compressing"]: score += 1
        if rsi_range >= _RCFG["rsi_range_trending"]:    score += 2
        elif rsi_range >= _RCFG["rsi_range_ranging"]:   score += 1

        score_norm = min(5, round(score * 5 / 6))

        if score_norm >= 3:   regime, allowed, mult = "TRENDING",     True,  1.0
        elif score_norm == 2: regime, allowed, mult = "TRANSITIONING", True,  0.5
        else:                 regime, allowed, mult = "RANGING",       False, 0.0

        self.current_regime = regime
        self.regime_score   = score_norm
        self.last_updated   = datetime.utcnow()
        self._save()

        log.info(f"[{self.bot_name}] Regime={regime} score={score_norm}/5 | "
                 f"ADX={adx:.1f} ATR_ratio={atr_ratio:.2f} RSI_range={rsi_range:.1f}")

        return {
            "regime":         regime,
            "score":          score_norm,
            "trade_allowed":  allowed,
            "risk_multiplier": mult,
            "adx":            round(adx, 1),
            "atr_ratio":      atr_ratio,
            "rsi_range":      round(rsi_range, 1),
        }

    def is_trade_allowed(self) -> tuple:
        """Quick gate check without re-running classification."""
        if self.current_regime == "RANGING":
            return False, 0.0, f"RANGING (score={self.regime_score}) — entries blocked"
        elif self.current_regime == "TRANSITIONING":
            return True, 0.5, f"TRANSITIONING (score={self.regime_score}) — half size"
        return True, 1.0, f"TRENDING (score={self.regime_score}) — full size"

    # ── Signal calculators ────────────────────────────────────────────────────

    def _adx(self, df, p=14) -> float:
        h, l, c = df["high"], df["low"], df["close"].shift(1)
        pdm = h.diff().clip(lower=0)
        mdm = (-l.diff()).clip(lower=0)
        pdm = pdm.where(pdm > mdm, 0)
        mdm = mdm.where(mdm > pdm, 0)
        tr  = pd.concat([h-l, (h-c).abs(), (l-c).abs()], axis=1).max(axis=1)
        atr = tr.ewm(span=p).mean()
        pdi = 100 * pdm.ewm(span=p).mean() / (atr + 1e-9)
        mdi = 100 * mdm.ewm(span=p).mean() / (atr + 1e-9)
        dx  = 100 * (pdi - mdi).abs() / (pdi + mdi + 1e-9)
        return float(dx.ewm(span=p).mean().iloc[-1])

    def _atr_ratio(self, df, p=14) -> float:
        h, l, c = df["high"], df["low"], df["close"].shift(1)
        tr  = pd.concat([h-l, (h-c).abs(), (l-c).abs()], axis=1).max(axis=1)
        atr = tr.rolling(p).mean()
        cur = float(atr.iloc[-1])
        avg = float(atr.rolling(20).mean().iloc[-1])
        return round(cur / avg, 3) if avg > 0 else 1.0

    def _rsi_range(self, df, p=14) -> float:
        delta = df["close"].diff()
        gain  = delta.clip(lower=0).rolling(p).mean()
        loss  = (-delta.clip(upper=0)).rolling(p).mean()
        rsi   = 100 - (100 / (1 + gain / (loss + 1e-9)))
        recent = rsi.tail(20)
        return float(recent.max() - recent.min())
