"""
shared_regime.py — Thin shim over trading/regime/classifier.py

Preserves the RegimeClassifier class interface used by all bots unchanged.
All signal math and classification logic now lives in trading/regime/.

Returns one of 5 labels: TRENDING | TRANSITIONING | RANGING | HIGH_VOLATILITY | LOW_VOLATILITY | UNKNOWN
Each bot owns its own REGIME_RISK_TABLE mapping these labels to (risk_multiplier, trade_allowed).
The shim returns risk_multiplier=1.0 and trade_allowed=True as defaults — bots override from their table.
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
        label = _classify_regime(df_h1, df_h4)

        if label == "UNKNOWN":
            log.warning(f"[{self.bot_name}] Insufficient data for regime classification "
                        f"— keeping cached state {self.current_regime}")
            return {
                "regime":          self.current_regime,
                "score":           self.regime_score,
                "trade_allowed":   True,
                "risk_multiplier": 1.0,
                "adx":             0.0,
                "atr_ratio":       0.0,
                "rsi_range":       0.0,
            }

        self.current_regime = label
        self.regime_score   = sigs["score_norm"]
        self.last_updated   = datetime.utcnow()
        self._save()

        log.info(f"[{self.bot_name}] Regime={label} score={sigs['score_norm']}/5 | "
                 f"ADX={sigs['adx']} ATR_ratio={sigs['atr_ratio']} RSI_range={sigs['rsi_range']}")

        return {
            "regime":          label,
            "score":           sigs["score_norm"],
            "trade_allowed":   True,
            "risk_multiplier": 1.0,
            "adx":             sigs["adx"],
            "atr_ratio":       sigs["atr_ratio"],
            "rsi_range":       sigs["rsi_range"],
        }

    def is_trade_allowed(self) -> tuple:
        """Quick gate check without re-running classification. Bots override via REGIME_RISK_TABLE."""
        return True, 1.0, f"{self.current_regime} (score={self.regime_score})"
