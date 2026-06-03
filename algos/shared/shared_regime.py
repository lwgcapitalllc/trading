"""
shared_regime.py — Thin shim over trading/regime/classifier.py

Preserves the RegimeClassifier class interface used by all bots unchanged.
All signal math and classification logic now lives in trading/regime/.

Three signals scored every hour:
  ADX(14)    — trend strength (>25 trending, <20 ranging)
  ATR ratio  — current vs 20-period average (expansion vs compression)
  RSI range  — how wide RSI has swung over 20 bars (directional vs choppy)

Score 0–5:
  0–1 = RANGING     → Bot 1 pauses, Bot 2 trades full size
  2   = TRANSITIONING → both trade at reduced size
  3–5 = TRENDING    → Bot 1 trades full size, Bot 2 reduces
"""

import sys
import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

# Add repo root to sys.path so we can import from trading/regime/
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from regime import classify_regime as _classify_regime, compute_signals as _compute_signals

log = logging.getLogger("REGIME")


def _load_update_interval() -> int:
    cfg_file = Path(__file__).parent / "config.json"
    if cfg_file.exists():
        with open(cfg_file) as f:
            cfg = json.load(f)
        return cfg.get("regime", {}).get("update_interval_minutes", 60)
    return 60


_UPDATE_MINUTES = _load_update_interval()


class RegimeClassifier:
    def __init__(self, bot_name="BOT", update_minutes=None):
        self.bot_name       = bot_name
        self.update_minutes = update_minutes or _UPDATE_MINUTES
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
                "regime":  self.current_regime,
                "score":   self.regime_score,
                "updated": datetime.utcnow().isoformat(),
                "bot":     self.bot_name,
            }, f, indent=2)

    def needs_update(self) -> bool:
        if self.last_updated is None:
            return True
        elapsed = (datetime.utcnow() - self.last_updated).total_seconds() / 60
        return elapsed >= self.update_minutes

    def classify(self, df_h1: pd.DataFrame, df_h4: pd.DataFrame) -> dict:
        """Run all three signals and return classification dict."""
        sigs  = _compute_signals(df_h1, df_h4)
        label = _classify_regime(df_h1, df_h4, mode="coarse")

        if label == "UNKNOWN":
            log.warning(f"[{self.bot_name}] Insufficient data for regime classification "
                        f"— keeping cached state {self.current_regime}")
            allowed = self.current_regime != "RANGING"
            mult    = 1.0 if self.current_regime == "TRENDING" else (0.5 if self.current_regime == "TRANSITIONING" else 0.0)
            return {
                "regime":          self.current_regime,
                "score":           self.regime_score,
                "trade_allowed":   allowed,
                "risk_multiplier": mult,
                "adx":             0.0,
                "atr_ratio":       0.0,
                "rsi_range":       0.0,
            }

        allowed = label != "RANGING"
        mult    = 1.0 if label == "TRENDING" else (0.5 if label == "TRANSITIONING" else 0.0)

        self.current_regime = label
        self.regime_score   = sigs["score_norm"]
        self.last_updated   = datetime.utcnow()
        self._save()

        log.info(f"[{self.bot_name}] Regime={label} score={sigs['score_norm']}/5 | "
                 f"ADX={sigs['adx']} ATR_ratio={sigs['atr_ratio']} RSI_range={sigs['rsi_range']}")

        return {
            "regime":          label,
            "score":           sigs["score_norm"],
            "trade_allowed":   allowed,
            "risk_multiplier": mult,
            "adx":             sigs["adx"],
            "atr_ratio":       sigs["atr_ratio"],
            "rsi_range":       sigs["rsi_range"],
        }

    def is_trade_allowed(self) -> tuple:
        """Quick gate check without re-running classification."""
        if self.current_regime == "RANGING":
            return False, 0.0, f"RANGING (score={self.regime_score}) — entries blocked"
        elif self.current_regime == "TRANSITIONING":
            return True, 0.5, f"TRANSITIONING (score={self.regime_score}) — half size"
        return True, 1.0, f"TRENDING (score={self.regime_score}) — full size"
