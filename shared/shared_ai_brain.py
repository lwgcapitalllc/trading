"""
shared_ai_brain.py — AI Brain + Trade Logger
Used by both bots. Each bot has its own model file and trade history.

What this does:
  - Logs every trade with 13–15 market features at entry
  - After 30 closed trades, trains a Random Forest classifier
  - Walk-forward validates (TimeSeriesSplit) — no lookahead bias
  - Refuses to deploy if AUC ≤ 0.52 (no better than chance)
  - Each bot has its own model: bot1_model.pkl / bot2_model.pkl
  - Retrains automatically every 10 new closed trades

Install: pip install scikit-learn joblib
"""

import json, logging, numpy as np, pandas as pd
from datetime import datetime
from pathlib import Path

log = logging.getLogger("AI-BRAIN")

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import roc_auc_score
    import joblib
    ML_OK = True
except ImportError:
    ML_OK = False
    log.warning("scikit-learn not found. pip install scikit-learn joblib")

MIN_TRADES_TRAIN = 30
RETRAIN_EVERY    = 10

# ── Feature sets ──────────────────────────────────────────────────────────────
TREND_FEATURES = [
    "confluence_score",     # 0–8: how many signals aligned
    "atr_normalized",       # ATR as % of price
    "sweep_wick_size",      # Judas Swing wick size in points
    "session_london",       # 1 if London kill zone
    "session_ny",           # 1 if NY kill zone
    "h4_trend_aligned",     # 1 if H4 EMA200 aligns with trade
    "fvg_present",          # 1 if Fair Value Gap detected
    "day_of_week",          # 0=Mon … 4=Fri
    "hour_of_day",          # UTC hour at entry
    "spread_at_entry",      # broker spread in points
    "prev_trade_won",       # 1 if last closed trade won
    "rolling_wr_5",         # win rate last 5 trades
    "rolling_wr_10",        # win rate last 10 trades
    "price_vs_daily_range", # 0=at low, 1=at high of day
    "rr_ratio",             # actual R:R ratio of setup
]

REVERSION_FEATURES = [
    "confluence_score",
    "atr_normalized",
    "rsi_value",            # RSI at entry
    "stoch_rsi",            # Stochastic RSI
    "bb_pct_b",             # Bollinger Band %B (0=lower, 1=upper)
    "price_vs_vwap",        # deviation from VWAP in std units
    "spread_at_entry",
    "day_of_week",
    "hour_of_day",
    "prev_trade_won",
    "rolling_wr_5",
    "rolling_wr_10",
    "regime_score",         # 1=trending, 2=transitioning, 3=ranging
]


# ═════════════════════════════════════════════════════════════════════════════
# TRADE LOGGER
# ═════════════════════════════════════════════════════════════════════════════

class TradeLogger:
    """Persistent JSON store for every trade with features and outcomes."""

    def __init__(self, filepath="trades.json"):
        self.filepath = filepath
        self.trades   = self._load()

    def _load(self):
        if Path(self.filepath).exists():
            with open(self.filepath) as f:
                data = json.load(f)
            log.info(f"Loaded {len(data)} trades from {self.filepath}")
            return data
        return []

    def _save(self):
        with open(self.filepath, "w") as f:
            json.dump(self.trades, f, indent=2, default=str)

    def log_entry(self, ticket, features, direction, entry, sl, tp1, tp2):
        self.trades.append({
            "ticket":     ticket,
            "direction":  direction,
            "entry":      entry,
            "sl":         sl,
            "tp1":        tp1,
            "tp2":        tp2,
            "sl_dist":    abs(entry - sl),
            "features":   features,
            "opened_at":  datetime.utcnow().isoformat(),
            "closed_at":  None,
            "outcome":    None,
            "r_multiple": None,
            "close_price":None,
        })
        self._save()

    def log_close(self, ticket, close_price, pnl_usd=0):
        for t in self.trades:
            if t["ticket"] == ticket and t["outcome"] is None:
                t["closed_at"]   = datetime.utcnow().isoformat()
                t["close_price"] = close_price
                sl_d = t["sl_dist"]
                if sl_d > 0:
                    r = (close_price - t["entry"]) / sl_d
                    if t["direction"] == "bearish": r = -r
                    t["r_multiple"] = round(r, 3)
                else:
                    t["r_multiple"] = 0.0
                t["outcome"] = (
                    "win"       if t["r_multiple"] > 0.1
                    else "loss" if t["r_multiple"] < -0.5
                    else "breakeven"
                )
                self._save()
                log.info(f"Trade closed | ticket={ticket} | "
                         f"outcome={t['outcome']} | R={t['r_multiple']:.2f}")
                return
        log.warning(f"Could not find open trade for ticket {ticket}")

    def get_closed(self):
        return [t for t in self.trades if t["outcome"] is not None]

    def get_rolling_wr(self, n=10) -> float:
        closed = self.get_closed()
        if not closed: return 0.5
        recent = closed[-n:]
        return sum(1 for t in recent if t["outcome"] == "win") / len(recent)

    def get_last_outcome(self) -> float:
        closed = self.get_closed()
        return 1.0 if closed and closed[-1]["outcome"] == "win" else 0.0


# ═════════════════════════════════════════════════════════════════════════════
# FEATURE BUILDERS
# ═════════════════════════════════════════════════════════════════════════════

def build_features_trend(score, atr, price, sweep_wick, session,
                          h4_aligned, fvg_present, spread,
                          d_high, d_low, logger) -> dict:
    now   = datetime.utcnow()
    d_rng = d_high - d_low
    p_pct = (price - d_low) / d_rng if d_rng > 0 else 0.5
    return {
        "confluence_score":     score,
        "atr_normalized":       round((atr / price) * 100, 4),
        "sweep_wick_size":      round(sweep_wick, 2),
        "session_london":       1 if session == "london" else 0,
        "session_ny":           1 if session == "ny" else 0,
        "h4_trend_aligned":     1 if h4_aligned else 0,
        "fvg_present":          1 if fvg_present else 0,
        "day_of_week":          now.weekday(),
        "hour_of_day":          now.hour,
        "spread_at_entry":      round(spread, 2),
        "prev_trade_won":       logger.get_last_outcome(),
        "rolling_wr_5":         round(logger.get_rolling_wr(5), 3),
        "rolling_wr_10":        round(logger.get_rolling_wr(10), 3),
        "price_vs_daily_range": round(p_pct, 3),
        "rr_ratio":             3.0,
    }

def build_features_reversion(score, atr, price, rsi, stoch_rsi,
                               bb_mid, bb_upper, bb_lower,
                               vwap, spread, logger, regime) -> dict:
    now    = datetime.utcnow()
    bb_rng = bb_upper - bb_lower
    bb_pct = (price - bb_lower) / bb_rng if bb_rng > 0 else 0.5
    v_dev  = (price - vwap) / max(abs(price - bb_mid), 1.0) if vwap else 0.0
    reg_map = {"TRENDING": 1, "TRANSITIONING": 2, "RANGING": 3}
    return {
        "confluence_score": score,
        "atr_normalized":   round((atr / price) * 100, 4),
        "rsi_value":        round(rsi, 2),
        "stoch_rsi":        round(stoch_rsi, 3),
        "bb_pct_b":         round(bb_pct, 3),
        "price_vs_vwap":    round(v_dev, 3),
        "spread_at_entry":  round(spread, 2),
        "day_of_week":      now.weekday(),
        "hour_of_day":      now.hour,
        "prev_trade_won":   logger.get_last_outcome(),
        "rolling_wr_5":     round(logger.get_rolling_wr(5), 3),
        "rolling_wr_10":    round(logger.get_rolling_wr(10), 3),
        "regime_score":     reg_map.get(regime, 2),
    }


# ═════════════════════════════════════════════════════════════════════════════
# AI BRAIN
# ═════════════════════════════════════════════════════════════════════════════

class AIBrain:
    """
    Random Forest classifier that learns from closed trades.
    Predicts win probability for new setups.
    Retrains automatically every 10 closed trades.
    """

    def __init__(self, logger: TradeLogger, model_file="model.pkl",
                 scaler_file=None):
        self.logger      = logger
        self.model_file  = model_file
        self.scaler_file = scaler_file or model_file.replace(".pkl", "_scaler.pkl")
        self.model       = None
        self.scaler      = None
        self.is_trained  = False
        self.last_auc    = 0.0
        self.trades_since_retrain = 0
        self.feature_importance   = {}
        self._load_model()

    def _load_model(self):
        if not ML_OK: return
        if Path(self.model_file).exists() and Path(self.scaler_file).exists():
            try:
                self.model   = joblib.load(self.model_file)
                self.scaler  = joblib.load(self.scaler_file)
                self.is_trained = True
                log.info(f"Loaded model from {self.model_file}")
            except Exception as e:
                log.warning(f"Could not load model: {e}")

    def _detect_features(self, features: dict) -> list:
        """Auto-detect which feature set to use based on keys present."""
        return TREND_FEATURES if "sweep_wick_size" in features else REVERSION_FEATURES

    def train(self, force=False) -> bool:
        if not ML_OK: return False
        closed = self.logger.get_closed()
        if len(closed) < MIN_TRADES_TRAIN and not force:
            log.info(f"Need {MIN_TRADES_TRAIN} trades to train ({len(closed)} so far)")
            return False

        # Determine feature set from first trade
        sample_feats = next(
            (t["features"] for t in closed if t["features"]), {}
        )
        feature_names = self._detect_features(sample_feats)

        rows, labels = [], []
        for t in closed:
            if t["features"] and t["outcome"] in ("win", "loss"):
                rows.append([t["features"].get(k, 0) for k in feature_names])
                labels.append(1 if t["outcome"] == "win" else 0)

        if len(rows) < 20:
            log.warning(f"Only {len(rows)} valid labeled trades. Need 20+.")
            return False

        X, y = np.array(rows), np.array(labels)
        self.scaler  = StandardScaler()
        Xs = self.scaler.fit_transform(X)

        # Walk-forward cross-validation — no lookahead bias
        tscv = TimeSeriesSplit(n_splits=min(5, len(X) // 10))
        aucs = []
        for tr, te in tscv.split(Xs):
            if len(te) < 3: continue
            m = RandomForestClassifier(
                n_estimators=200, max_depth=6, min_samples_leaf=5,
                class_weight="balanced", random_state=42
            )
            m.fit(Xs[tr], y[tr])
            if len(set(y[te])) > 1:
                aucs.append(roc_auc_score(y[te], m.predict_proba(Xs[te])[:, 1]))

        mean_auc = np.mean(aucs) if aucs else 0.5
        if mean_auc < 0.52:
            log.warning(f"Walk-forward AUC={mean_auc:.3f} — not better than chance. "
                        f"Model not deployed. Keep collecting data.")
            return False

        # Train final model on all data
        self.model = RandomForestClassifier(
            n_estimators=300, max_depth=6, min_samples_leaf=5,
            class_weight="balanced", random_state=42
        )
        self.model.fit(Xs, y)
        self.is_trained = True
        self.last_auc   = mean_auc
        self.trades_since_retrain = 0

        self.feature_importance = dict(zip(
            feature_names,
            [round(v, 4) for v in self.model.feature_importances_]
        ))
        joblib.dump(self.model,  self.model_file)
        joblib.dump(self.scaler, self.scaler_file)

        log.info(f"Model trained | AUC={mean_auc:.3f} | {len(rows)} trades")
        top = sorted(self.feature_importance.items(), key=lambda x: -x[1])[:5]
        for f, v in top:
            log.info(f"  {f}: {v:.4f}")
        return True

    def predict_win_prob(self, features: dict) -> float:
        if not self.is_trained or not self.model: return 0.5
        feature_names = self._detect_features(features)
        try:
            X  = np.array([[features.get(k, 0) for k in feature_names]])
            Xs = self.scaler.transform(X)
            return round(float(self.model.predict_proba(Xs)[0][1]), 4)
        except Exception as e:
            log.warning(f"Prediction failed: {e}")
            return 0.5

    def should_take_trade(self, features: dict, threshold=0.55) -> tuple:
        """Returns (take_trade, win_probability, reason)."""
        prob = self.predict_win_prob(features)
        if not self.is_trained:
            return True, prob, "AI not yet trained — rules-based logic only"
        if prob >= threshold:
            return True, prob, f"AI approved {prob:.1%} ≥ {threshold:.1%}"
        return False, prob, f"AI blocked {prob:.1%} < {threshold:.1%}"

    def on_trade_closed(self, ticket, close_price, pnl=0):
        """Call from main bot whenever a trade closes."""
        self.logger.log_close(ticket, close_price, pnl)
        self.trades_since_retrain += 1
        closed = self.logger.get_closed()
        if (len(closed) >= MIN_TRADES_TRAIN and
                self.trades_since_retrain >= RETRAIN_EVERY):
            log.info(f"Retrain trigger: {self.trades_since_retrain} new trades since last train.")
            self.train()
