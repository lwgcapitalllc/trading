"""
shared_ai_brain.py — AI Brain + Trade Logger + Daily Performance Logger

Improvements over v1:
  - Training threshold lowered to 15 trades (was 30)
  - AUC gate raised to 0.55 (stricter — faster training needs stricter quality gate)
  - Daily performance logger — records drawdown, trade count, simultaneous positions
  - Drawdown awareness feature — AI learns which day patterns lead to losses
  - Re-entry tracking — logs whether a trade was a re-entry and its outcome
  - Retrains every 5 new closed trades (was 10)

Install: pip install scikit-learn joblib
"""

import json, logging, numpy as np
from datetime import datetime, date
from pathlib import Path

log = logging.getLogger("AI-BRAIN")

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import roc_auc_score
    import joblib
    ML_OK = True
except ImportError:
    ML_OK = False
    log.warning("scikit-learn not found. pip install scikit-learn joblib")

MIN_TRADES_TRAIN = 15   # lowered from 30
MIN_AUC_GATE     = 0.55 # raised from 0.52 — stricter since less data
RETRAIN_EVERY    = 5    # lowered from 10 — faster adaptation

# ── Feature sets ──────────────────────────────────────────────────────────────
TREND_FEATURES = [
    "confluence_score",
    "atr_normalized",
    "sweep_wick_size",
    "session_london",
    "session_ny",
    "h4_trend_aligned",
    "fvg_present",
    "day_of_week",
    "hour_of_day",
    "spread_at_entry",
    "prev_trade_won",
    "rolling_wr_5",
    "rolling_wr_10",
    "price_vs_daily_range",
    "rr_ratio",
    # New drawdown-aware features
    "daily_trades_so_far",      # how many trades already today
    "daily_pnl_pct",            # current day P&L % at time of entry
    "simultaneous_open",        # how many positions open at entry
    "is_reentry",               # 1 if this is a re-entry after BE stop
]

REVERSION_FEATURES = [
    "confluence_score",
    "atr_normalized",
    "rsi_value",
    "stoch_rsi",
    "bb_pct_b",
    "price_vs_vwap",
    "spread_at_entry",
    "day_of_week",
    "hour_of_day",
    "prev_trade_won",
    "rolling_wr_5",
    "rolling_wr_10",
    "regime_score",
    # New drawdown-aware features
    "daily_trades_so_far",
    "daily_pnl_pct",
    "simultaneous_open",
    "is_reentry",
]

SCALPER_FEATURES = [
    "ema_stack_strength",
    "pullback_depth_r",
    "momentum_body_r",
    "rsi_at_entry",
    "atr_normalized",
    "hour_of_day",
    "day_of_week",
    "prev_trade_won",
    "rolling_wr_5",
    "rolling_wr_10",
    "daily_pnl_pct",
    "spread_at_entry",
    "bias_direction",
    "daily_trades_so_far",
    "simultaneous_open",
    "is_reentry",
]


# =============================================================================
# DAILY PERFORMANCE LOGGER
# =============================================================================

class DailyLogger:
    """
    Records end-of-day performance metrics for AI training.
    The AI learns which day CONDITIONS produce drawdowns vs profits.
    """

    def __init__(self, filepath="daily_performance.json"):
        self.filepath = filepath
        self.records  = self._load()

    def _load(self):
        if Path(self.filepath).exists():
            with open(self.filepath) as f:
                return json.load(f)
        return []

    def _save(self):
        with open(self.filepath, "w") as f:
            json.dump(self.records, f, indent=2, default=str)

    def record_day(self, date_str: str, metrics: dict):
        """
        Call at end of each trading day with:
        metrics = {
            "total_trades": int,
            "wins": int,
            "losses": int,
            "breakevens": int,
            "max_simultaneous_open": int,
            "max_drawdown_pct": float,
            "final_pnl_pct": float,
            "regime": str,
            "day_of_week": int,
        }
        """
        record = {"date": date_str, **metrics}
        # Update existing record for today if already exists
        for i, r in enumerate(self.records):
            if r["date"] == date_str:
                self.records[i] = record
                self._save()
                log.info(f"Daily log updated | {date_str} | "
                         f"trades={metrics.get('total_trades')} | "
                         f"pnl={metrics.get('final_pnl_pct', 0):+.1f}% | "
                         f"max_dd={metrics.get('max_drawdown_pct', 0):.1f}% | "
                         f"max_open={metrics.get('max_simultaneous_open', 0)}")
                return
        self.records.append(record)
        self._save()
        log.info(f"Daily log saved | {date_str} | "
                 f"trades={metrics.get('total_trades')} | "
                 f"pnl={metrics.get('final_pnl_pct', 0):+.1f}%")

    def get_recent(self, n=30) -> list:
        return self.records[-n:]

    def get_avg_drawdown(self, n=10) -> float:
        recent = self.get_recent(n)
        if not recent: return 0.0
        return sum(r.get("max_drawdown_pct", 0) for r in recent) / len(recent)

    def get_bad_day_patterns(self) -> dict:
        """Return conditions that correlate with bad days."""
        if len(self.records) < 5:
            return {}
        bad  = [r for r in self.records if r.get("final_pnl_pct", 0) < -2]
        good = [r for r in self.records if r.get("final_pnl_pct", 0) > 1]
        if not bad or not good:
            return {}
        patterns = {
            "bad_days_avg_trades":      sum(r.get("total_trades", 0) for r in bad) / len(bad),
            "good_days_avg_trades":     sum(r.get("total_trades", 0) for r in good) / len(good),
            "bad_days_avg_max_open":    sum(r.get("max_simultaneous_open", 0) for r in bad) / len(bad),
            "good_days_avg_max_open":   sum(r.get("max_simultaneous_open", 0) for r in good) / len(good),
        }
        log.info(f"Bad day pattern: avg {patterns['bad_days_avg_trades']:.1f} trades, "
                 f"{patterns['bad_days_avg_max_open']:.1f} max open")
        log.info(f"Good day pattern: avg {patterns['good_days_avg_trades']:.1f} trades, "
                 f"{patterns['good_days_avg_max_open']:.1f} max open")
        return patterns


# =============================================================================
# TRADE LOGGER
# =============================================================================

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

    def log_entry(self, ticket, features, direction, entry, sl, tp1, tp2,
                  is_reentry=False):
        self.trades.append({
            "ticket":      ticket,
            "direction":   direction,
            "entry":       entry,
            "sl":          sl,
            "tp1":         tp1,
            "tp2":         tp2,
            "sl_dist":     abs(entry - sl),
            "features":    features,
            "opened_at":   datetime.utcnow().isoformat(),
            "closed_at":   None,
            "outcome":     None,
            "r_multiple":  None,
            "close_price": None,
            "is_reentry":  is_reentry,
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
                         f"outcome={t['outcome']} | R={t['r_multiple']:.2f}"
                         + (" [re-entry]" if t.get("is_reentry") else ""))
                return
        log.warning(f"Could not find open trade for ticket {ticket}")

    def get_closed(self):
        return [t for t in self.trades if t["outcome"] is not None]

    def get_reentry_stats(self) -> dict:
        """Compare win rate of re-entries vs original entries."""
        closed = self.get_closed()
        reentries = [t for t in closed if t.get("is_reentry")]
        originals = [t for t in closed if not t.get("is_reentry")]
        def wr(trades):
            if not trades: return 0.0
            return sum(1 for t in trades if t["outcome"] == "win") / len(trades)
        return {
            "reentry_wr":  round(wr(reentries), 3),
            "original_wr": round(wr(originals), 3),
            "reentry_count": len(reentries),
        }

    def get_rolling_wr(self, n=10) -> float:
        closed = self.get_closed()
        if not closed: return 0.5
        recent = closed[-n:]
        return sum(1 for t in recent if t["outcome"] == "win") / len(recent)

    def get_last_outcome(self) -> float:
        closed = self.get_closed()
        return 1.0 if closed and closed[-1]["outcome"] == "win" else 0.0

    def was_last_trade_breakeven(self) -> bool:
        """Used to detect re-entry opportunity."""
        closed = self.get_closed()
        return bool(closed and closed[-1]["outcome"] == "breakeven")


# =============================================================================
# FEATURE BUILDERS
# =============================================================================

def build_features_trend(score, atr, price, sweep_wick, session,
                          h4_aligned, fvg_present, spread,
                          d_high, d_low, logger,
                          daily_trades=0, daily_pnl_pct=0.0,
                          simultaneous_open=0, is_reentry=False) -> dict:
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
        "daily_trades_so_far":  daily_trades,
        "daily_pnl_pct":        round(daily_pnl_pct, 3),
        "simultaneous_open":    simultaneous_open,
        "is_reentry":           1 if is_reentry else 0,
    }


def build_features_reversion(score, atr, price, rsi, stoch_rsi,
                               bb_mid, bb_upper, bb_lower,
                               vwap, spread, logger, regime,
                               daily_trades=0, daily_pnl_pct=0.0,
                               simultaneous_open=0, is_reentry=False) -> dict:
    now       = datetime.utcnow()
    bb_range  = bb_upper - bb_lower
    bb_pct_b  = (price - bb_lower) / bb_range if bb_range > 0 else 0.5
    vwap_std  = (price - vwap) / (bb_range / 4) if bb_range > 0 else 0
    regime_map = {"RANGING": 3, "TRANSITIONING": 2, "TRENDING": 1}
    return {
        "confluence_score":  score,
        "atr_normalized":    round((atr / price) * 100, 4),
        "rsi_value":         round(rsi, 2),
        "stoch_rsi":         round(stoch_rsi, 3),
        "bb_pct_b":          round(bb_pct_b, 3),
        "price_vs_vwap":     round(vwap_std, 3),
        "spread_at_entry":   round(spread, 2),
        "day_of_week":       now.weekday(),
        "hour_of_day":       now.hour,
        "prev_trade_won":    logger.get_last_outcome(),
        "rolling_wr_5":      round(logger.get_rolling_wr(5), 3),
        "rolling_wr_10":     round(logger.get_rolling_wr(10), 3),
        "regime_score":      regime_map.get(regime, 2),
        "daily_trades_so_far": daily_trades,
        "daily_pnl_pct":     round(daily_pnl_pct, 3),
        "simultaneous_open": simultaneous_open,
        "is_reentry":        1 if is_reentry else 0,
    }


# =============================================================================
# AI BRAIN
# =============================================================================

class AIBrain:
    """
    Random Forest classifier that learns from closed trades.
    v2: Trains at 15 trades, retrains every 5, AUC gate 0.55.
    Includes drawdown awareness and re-entry tracking.
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
                self.model      = joblib.load(self.model_file)
                self.scaler     = joblib.load(self.scaler_file)
                self.is_trained = True
                log.info(f"AI model loaded | {self.model_file} | "
                         f"last AUC={self.last_auc:.3f}")
            except Exception as e:
                log.warning(f"Could not load model: {e}")

    def _detect_features(self, features: dict) -> list:
        if "sweep_wick_size" in features:   return TREND_FEATURES
        if "ema_stack_strength" in features: return SCALPER_FEATURES
        return REVERSION_FEATURES

    def train(self, force=False) -> bool:
        if not ML_OK: return False
        closed = self.logger.get_closed()
        n = len(closed)

        if n < MIN_TRADES_TRAIN and not force:
            remaining = MIN_TRADES_TRAIN - n
            log.info(f"AI: {n} closed trades. Need {remaining} more to train. "
                     f"Running rules-based logic.")
            return False

        sample_feats = next(
            (t["features"] for t in closed if t["features"]), {}
        )
        feature_names = self._detect_features(sample_feats)

        rows, labels = [], []
        for t in closed:
            if t["features"] and t["outcome"] in ("win", "loss"):
                rows.append([t["features"].get(k, 0) for k in feature_names])
                labels.append(1 if t["outcome"] == "win" else 0)

        if len(rows) < MIN_TRADES_TRAIN:
            log.warning(f"Only {len(rows)} win/loss trades (excluding breakevens). "
                        f"Need {MIN_TRADES_TRAIN}.")
            return False

        X, y = np.array(rows), np.array(labels)
        self.scaler = StandardScaler()
        Xs = self.scaler.fit_transform(X)

        # Walk-forward cross-validation
        n_splits = min(3, len(X) // 5)
        if n_splits < 2:
            log.warning("Not enough trades for walk-forward validation yet.")
            n_splits = 2

        tscv = TimeSeriesSplit(n_splits=n_splits)
        aucs = []
        for tr, te in tscv.split(Xs):
            if len(te) < 2: continue
            m = RandomForestClassifier(
                n_estimators=100, max_depth=4, min_samples_leaf=3,
                class_weight="balanced", random_state=42
            )
            m.fit(Xs[tr], y[tr])
            if len(set(y[te])) > 1:
                aucs.append(roc_auc_score(y[te], m.predict_proba(Xs[te])[:, 1]))

        mean_auc = np.mean(aucs) if aucs else 0.5
        if mean_auc < MIN_AUC_GATE:
            log.warning(f"AI: AUC={mean_auc:.3f} below gate {MIN_AUC_GATE}. "
                        f"Model not deployed. Need more quality data.")
            return False

        # Train final model
        self.model = RandomForestClassifier(
            n_estimators=200, max_depth=5, min_samples_leaf=3,
            class_weight="balanced", random_state=42
        )
        self.model.fit(Xs, y)
        self.is_trained  = True
        self.last_auc    = mean_auc
        self.trades_since_retrain = 0

        self.feature_importance = dict(zip(
            feature_names,
            [round(v, 4) for v in self.model.feature_importances_]
        ))
        joblib.dump(self.model,  self.model_file)
        joblib.dump(self.scaler, self.scaler_file)

        log.info(f"AI trained | AUC={mean_auc:.3f} | {len(rows)} trades | "
                 f"threshold={MIN_AUC_GATE}")
        top = sorted(self.feature_importance.items(), key=lambda x: -x[1])[:5]
        log.info("Top features: " + " | ".join(f"{f}={v:.3f}" for f, v in top))

        # Log re-entry stats
        stats = self.logger.get_reentry_stats()
        if stats["reentry_count"] > 0:
            log.info(f"Re-entry stats: {stats['reentry_count']} re-entries | "
                     f"WR={stats['reentry_wr']:.1%} vs original WR={stats['original_wr']:.1%}")
        return True

    def predict_win_prob(self, features: dict) -> float:
        if not self.is_trained or not self.model: return 0.5
        feature_names = self._detect_features(features)
        try:
            X  = np.array([[features.get(k, 0) for k in feature_names]])
            Xs = self.scaler.transform(X)
            return round(float(self.model.predict_proba(Xs)[0][1]), 4)
        except Exception as e:
            log.warning(f"AI prediction failed: {e}")
            return 0.5

    def should_take_trade(self, features: dict, threshold=0.55) -> tuple:
        """Returns (take_trade, win_probability, reason)."""
        prob = self.predict_win_prob(features)
        closed = self.logger.get_closed()
        n = len(closed)

        if not self.is_trained:
            remaining = max(0, MIN_TRADES_TRAIN - n)
            reason = (f"AI not yet trained ({n}/{MIN_TRADES_TRAIN} trades). "
                      f"Rules-based. {remaining} more needed.")
            return True, prob, reason

        if prob >= threshold:
            return True, prob, f"AI approved {prob:.1%} >= {threshold:.1%}"
        return False, prob, f"AI blocked {prob:.1%} < {threshold:.1%}"

    def on_trade_closed(self, ticket, close_price, pnl=0):
        """Call whenever a trade closes — logs outcome and triggers retrain."""
        self.logger.log_close(ticket, close_price, pnl)
        self.trades_since_retrain += 1
        closed = self.logger.get_closed()
        if (len(closed) >= MIN_TRADES_TRAIN and
                self.trades_since_retrain >= RETRAIN_EVERY):
            log.info(f"AI retrain: {self.trades_since_retrain} new trades since last train.")
            self.train()

    def status_report(self) -> str:
        closed = self.logger.get_closed()
        n = len(closed)
        if not self.is_trained:
            return (f"AI: Not trained | {n}/{MIN_TRADES_TRAIN} trades | "
                    f"{max(0, MIN_TRADES_TRAIN - n)} more needed")
        wr = self.logger.get_rolling_wr(10)
        return (f"AI: Trained | AUC={self.last_auc:.3f} | "
                f"WR(10)={wr:.1%} | {n} total trades")
