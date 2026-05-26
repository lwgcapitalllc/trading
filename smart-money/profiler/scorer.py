"""
Stage 1, Step 1.6: Composite scoring model.

Scoring factors and weights (from config):
  win_rate_consistency      25%  — how consistently ≥ threshold each window
  risk_adjusted_return      25%  — Sharpe-like: cumulative PnL / max drawdown
  exit_efficiency           20%  — fraction of gross potential captured as profit
  trade_frequency           15%  — trades per month vs target
  instrument_day_consistency 15% — entropy-based repeatable pattern score

All sub-scores are normalised to [0, 100] before weighting.
Elite lookback (365d) wallets receive a bonus multiplier defined in config.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timezone

from run_logger import StageLogger


# ---------------------------------------------------------------------------
# Sub-score functions
# ---------------------------------------------------------------------------

def _score_win_rate_consistency(windows: list[dict], min_wr: float) -> float:
    """
    How far above the threshold each window sits, averaged and scaled.
    A wallet where every window is well above threshold scores near 100.
    A wallet where windows hover at threshold scores near 50.
    """
    if not windows:
        return 0.0

    # We only score windows that have trades; empty windows are skipped
    active = [w for w in windows if w["trade_count"] > 0]
    if not active:
        return 0.0

    # margin above threshold per window, clamped to [-threshold, 1-threshold]
    margins = [(w["win_rate"] - min_wr) for w in active]
    max_possible_margin = 1.0 - min_wr  # e.g. 0.20 when threshold=0.80

    # Scale: margin of 0 → 50, margin of max → 100, negative margin → < 50
    scores = []
    for m in margins:
        normalised = (m / max_possible_margin) * 50 + 50  # [-50 → 0, 0 → 50, max → 100]
        scores.append(max(0.0, min(100.0, normalised)))

    return round(sum(scores) / len(scores), 2)


def _score_risk_adjusted_return(trades: list[dict]) -> float:
    """
    Modified Calmar-like ratio: total PnL / max drawdown (in absolute $ terms).
    Normalised against a reference ratio that scores 80.
    """
    if not trades:
        return 0.0

    sorted_trades = sorted(trades, key=lambda t: t["close_ts"])
    cum = 0.0
    peak = 0.0
    max_dd_abs = 0.0
    total_pnl = sum(t["pnl"] for t in trades)

    for t in sorted_trades:
        cum += t["pnl"]
        if cum > peak:
            peak = cum
        dd_abs = peak - cum
        if dd_abs > max_dd_abs:
            max_dd_abs = dd_abs

    if max_dd_abs == 0:
        # Never drew down — perfect score if profitable, 0 if not
        return 100.0 if total_pnl > 0 else 0.0

    calmar = total_pnl / max_dd_abs
    # Reference: calmar of 3.0 → score of 80; calmar of 5.0 → ~100
    # Score = min(100, calmar / 5.0 * 100)
    raw = (calmar / 5.0) * 100
    return round(max(0.0, min(100.0, raw)), 2)


def _score_exit_efficiency(trades: list[dict]) -> float:
    """
    Exit efficiency = total winning PnL / (total winning PnL + |total losing PnL|).
    Represents what fraction of gross P&L was captured as profit vs given back as losses.
    Range is naturally [0, 1]; scaled to [0, 100].
    A wallet with only wins scores 100; only losses scores 0.
    """
    if not trades:
        return 0.0

    gross_wins = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_losses = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    total_gross = gross_wins + gross_losses

    if total_gross == 0:
        return 50.0

    efficiency = gross_wins / total_gross
    return round(efficiency * 100, 2)


def _score_trade_frequency(
    trades: list[dict], target_per_month: int, lookback_days: int
) -> float:
    """
    Scores how close to the target monthly trade frequency the wallet is.
    Below target: linearly up to 50 at target. Above target (up to 2x): up to 100.
    Very low frequency (< 10% of target) scores near 0.
    """
    if not trades or lookback_days == 0:
        return 0.0

    months = lookback_days / 30.0
    actual_per_month = len(trades) / months

    ratio = actual_per_month / target_per_month
    if ratio <= 1.0:
        score = ratio * 100
    else:
        # cap at 100 for 2x target
        score = min(100.0, 100 + (ratio - 1.0) * 0)  # stays at 100 beyond target
        score = 100.0

    return round(max(0.0, min(100.0, score)), 2)


def _score_instrument_day_consistency(trades: list[dict]) -> float:
    """
    Measures repeatability using entropy over instrument frequencies and
    day-of-week frequencies. Lower entropy (more concentrated) → higher score.

    Score = 100 × (1 - normalised_entropy)
    where normalised_entropy = H / log2(N) for N categories.
    We average instrument and day-of-week scores equally.
    """
    if not trades:
        return 0.0

    def entropy_score(counter: Counter) -> float:
        total = sum(counter.values())
        if total == 0 or len(counter) <= 1:
            return 100.0  # single instrument/day = perfectly consistent
        probs = [v / total for v in counter.values()]
        H = -sum(p * math.log2(p) for p in probs if p > 0)
        H_max = math.log2(len(counter))
        normalised = H / H_max if H_max > 0 else 0.0
        return round((1 - normalised) * 100, 2)

    instrument_counter: Counter = Counter(t["instrument"] for t in trades)
    day_counter: Counter = Counter(
        datetime.fromtimestamp(t["close_ts"] / 1000, tz=timezone.utc).weekday()
        for t in trades
    )

    inst_score = entropy_score(instrument_counter)
    day_score = entropy_score(day_counter)

    return round((inst_score + day_score) / 2, 2)


# ---------------------------------------------------------------------------
# Composite scorer
# ---------------------------------------------------------------------------

class CompositeScorer:
    def __init__(self, config: dict, logger: StageLogger):
        self._cfg = config
        self._log = logger
        self._weights: dict[str, float] = config["scoring"]["weights"]
        self._min_wr: float = config["qualification"]["min_win_rate"]
        self._target_freq: int = config["scoring"]["target_trades_per_month"]
        self._elite_bonus: float = config["scoring"]["elite_lookback_bonus"]
        self._elite_days: int = config["lookback"]["elite_days"]
        self._preferred_days: int = config["lookback"]["preferred_days"]
        self._min_days: int = config["lookback"]["minimum_days"]

    def _lookback_tier(self, trades: list[dict]) -> tuple[str, int]:
        """Determine which tier this wallet falls into based on trade history span."""
        if not trades:
            return "minimum", self._min_days
        oldest = min(t["close_ts"] for t in trades)
        newest = max(t["close_ts"] for t in trades)
        span_days = int((newest - oldest) / (86_400 * 1_000))
        if span_days >= self._elite_days:
            return "elite", span_days
        if span_days >= self._preferred_days:
            return "preferred", span_days
        return "minimum", span_days

    def compute(
        self, trades: list[dict], windows: list[dict]
    ) -> dict:
        """
        Returns a dict with all sub-scores, the composite score, and the lookback tier.
        """
        tier, span_days = self._lookback_tier(trades)

        sub_scores = {
            "win_rate_consistency": _score_win_rate_consistency(windows, self._min_wr),
            "risk_adjusted_return": _score_risk_adjusted_return(trades),
            "exit_efficiency": _score_exit_efficiency(trades),
            "trade_frequency": _score_trade_frequency(trades, self._target_freq, span_days),
            "instrument_day_consistency": _score_instrument_day_consistency(trades),
        }

        composite = sum(
            sub_scores[factor] * weight
            for factor, weight in self._weights.items()
        )

        # Elite tier bonus (additive, capped at 100)
        if tier == "elite":
            composite *= (1 + self._elite_bonus)

        composite = round(min(100.0, composite), 2)

        return {
            **sub_scores,
            "composite_score": composite,
            "lookback_tier": tier,
            "lookback_span_days": span_days,
            "rank": None,  # set by caller after sorting all wallets
        }

    def rank_wallets(self, scored_wallets: list[dict]) -> list[dict]:
        """Assigns rank (1 = best) in-place after all wallets are scored."""
        sorted_wallets = sorted(
            scored_wallets, key=lambda w: w["composite_score"], reverse=True
        )
        for i, wallet in enumerate(sorted_wallets, start=1):
            wallet["rank"] = i
        return sorted_wallets
