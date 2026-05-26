"""
Stage 1, Steps 1.4–1.5: Qualification and disqualification filters.

All thresholds come from config — never hardcoded here.

Steps covered:
  1.4  Monthly win rate windows + strike system
  1.5  Disqualification: trade concentration, weekly activity,
       drawdown, hold time, instrument concentration
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from datetime import datetime, timezone

from run_logger import StageLogger


# ---------------------------------------------------------------------------
# Monthly window builder
# ---------------------------------------------------------------------------

def build_monthly_windows(trades: list[dict], window_days: int = 30) -> list[dict]:
    """
    Segments trades into fixed non-overlapping windows of `window_days` days,
    anchored from the earliest trade timestamp.

    Returns a list of window dicts with keys:
      window_start, window_end, trade_count, win_count, loss_count,
      win_rate, total_pnl, peak_cum_pnl, trough_cum_pnl, active_weeks
    """
    if not trades:
        return []

    sorted_trades = sorted(trades, key=lambda t: t["close_ts"])
    epoch_ms = sorted_trades[0]["close_ts"]
    window_ms = window_days * 86_400 * 1_000

    windows: list[dict] = []
    window_start = epoch_ms

    while window_start <= sorted_trades[-1]["close_ts"]:
        window_end = window_start + window_ms
        bucket = [
            t for t in sorted_trades
            if window_start <= t["close_ts"] < window_end
        ]

        if bucket:
            wins = sum(1 for t in bucket if t["is_win"])
            losses = len(bucket) - wins
            total_pnl = sum(t["pnl"] for t in bucket)

            # peak / trough of cumulative PnL within this window
            cum = 0.0
            peak_cum = 0.0
            trough_cum = 0.0
            for t in bucket:
                cum += t["pnl"]
                if cum > peak_cum:
                    peak_cum = cum
                if cum < trough_cum:
                    trough_cum = cum

            # count distinct ISO weeks with at least 1 trade
            weeks = {
                datetime.fromtimestamp(t["close_ts"] / 1000, tz=timezone.utc).isocalendar()[:2]
                for t in bucket
            }

            windows.append({
                "window_start": window_start,
                "window_end": window_end,
                "trade_count": len(bucket),
                "win_count": wins,
                "loss_count": losses,
                "win_rate": wins / len(bucket) if bucket else 0.0,
                "total_pnl": round(total_pnl, 4),
                "peak_cum_pnl": round(peak_cum, 4),
                "trough_cum_pnl": round(trough_cum, 4),
                "active_weeks": len(weeks),
                "strike_level": 0,
            })

        window_start = window_end

    return windows


# ---------------------------------------------------------------------------
# Strike system (Step 1.4)
# ---------------------------------------------------------------------------

def apply_strike_system(windows: list[dict], config: dict) -> tuple[bool, list[dict]]:
    """
    Applies the strike system to monthly windows in chronological order.

    Returns (still_qualifies, windows_with_strike_levels_set).

    Strike levels: 0 = clean, 1 = yellow flag, 2 = disqualified.
    Reinstatement: 2 consecutive months back above threshold resets to 0.
    """
    min_wr = config["qualification"]["min_win_rate"]
    consec_disq = config["strike_system"]["disqualify_consecutive_months"]
    consec_reinstate = config["strike_system"]["reinstate_consecutive_months"]

    consecutive_below = 0
    consecutive_above = 0
    disqualified = False
    reinstated = False

    for w in windows:
        if w["win_rate"] >= min_wr:
            consecutive_below = 0
            consecutive_above += 1
            if disqualified and consecutive_above >= consec_reinstate:
                disqualified = False
                reinstated = True
            w["strike_level"] = 0
        else:
            consecutive_above = 0
            consecutive_below += 1
            if consecutive_below == 1:
                w["strike_level"] = 1  # yellow flag
            else:
                w["strike_level"] = 2  # disqualified territory
            if consecutive_below >= consec_disq:
                disqualified = True

    qualifies = not disqualified
    return qualifies, windows


# ---------------------------------------------------------------------------
# Disqualification filters (Step 1.5)
# ---------------------------------------------------------------------------

class DisqualificationFilter:
    """
    Applies all Step 1.5 disqualification rules to a set of matched trades.
    Each check returns (passes: bool, reason: str | None).
    """

    def __init__(self, config: dict):
        q = config["qualification"]
        self._max_single_pnl_share: float = q["max_single_trade_pnl_share"]
        self._min_weekly_active: int = q["min_active_weeks_per_month"]
        self._max_drawdown: float = q["max_drawdown"]
        self._max_hold_hours: float = q["max_avg_hold_hours"]
        self._min_instruments: int = q["min_instruments"]
        self._window_days: int = config["lookback"]["window_days"]

    def check_trade_concentration(
        self, trades: list[dict]
    ) -> tuple[bool, str | None]:
        """No single trade > max_single_trade_pnl_share of total absolute PnL."""
        total_abs_pnl = sum(abs(t["pnl"]) for t in trades)
        if total_abs_pnl == 0:
            return True, None
        worst = max(abs(t["pnl"]) for t in trades)
        share = worst / total_abs_pnl
        if share > self._max_single_pnl_share:
            return False, (
                f"Single trade PnL share {share:.1%} > "
                f"{self._max_single_pnl_share:.0%} limit"
            )
        return True, None

    def check_weekly_activity(
        self, trades: list[dict]
    ) -> tuple[bool, str | None]:
        """
        Each 30-day window must have trades across ≥ min_active_weeks_per_month distinct weeks.
        A wallet fails if *any* window has fewer active weeks.
        """
        windows = build_monthly_windows(trades, self._window_days)
        for w in windows:
            if w["active_weeks"] < self._min_weekly_active:
                return False, (
                    f"Window starting {w['window_start']} has only "
                    f"{w['active_weeks']} active weeks "
                    f"(need {self._min_weekly_active})"
                )
        return True, None

    def check_drawdown(
        self, trades: list[dict]
    ) -> tuple[bool, str | None]:
        """Peak drawdown across full period must not exceed max_drawdown."""
        sorted_trades = sorted(trades, key=lambda t: t["close_ts"])
        peak_cum = 0.0
        cum = 0.0
        max_dd = 0.0

        for t in sorted_trades:
            cum += t["pnl"]
            if cum > peak_cum:
                peak_cum = cum
            if peak_cum > 0:
                dd = (peak_cum - cum) / peak_cum
                if dd > max_dd:
                    max_dd = dd

        if max_dd > self._max_drawdown:
            return False, (
                f"Peak drawdown {max_dd:.1%} > {self._max_drawdown:.0%} limit"
            )
        return True, None

    def check_hold_time(
        self, trades: list[dict]
    ) -> tuple[bool, str | None]:
        """Average hold time must not exceed max_avg_hold_hours."""
        trades_with_hold = [
            t for t in trades
            if t.get("hold_time_seconds") is not None
        ]
        if not trades_with_hold:
            return True, None  # cannot determine — pass conservatively

        avg_seconds = sum(t["hold_time_seconds"] for t in trades_with_hold) / len(trades_with_hold)
        avg_hours = avg_seconds / 3600

        if avg_hours > self._max_hold_hours:
            return False, (
                f"Average hold time {avg_hours:.1f}h > {self._max_hold_hours}h limit"
            )
        return True, None

    def check_instrument_concentration(
        self, trades: list[dict]
    ) -> tuple[bool, str | None]:
        """PnL must not be concentrated in a single instrument."""
        if not trades:
            return True, None

        pnl_by_instrument: dict[str, float] = defaultdict(float)
        for t in trades:
            pnl_by_instrument[t["instrument"]] += t["pnl"]

        if len(pnl_by_instrument) < self._min_instruments:
            instruments = list(pnl_by_instrument.keys())
            return False, (
                f"Only {len(instruments)} instrument(s) traded "
                f"(need {self._min_instruments}+): {instruments}"
            )

        total_pos_pnl = sum(v for v in pnl_by_instrument.values() if v > 0)
        if total_pos_pnl == 0:
            return True, None

        top_instrument_pnl = max(pnl_by_instrument.values())
        concentration = top_instrument_pnl / total_pos_pnl if total_pos_pnl > 0 else 0.0

        # Disqualify if a single instrument contributes >80% of positive PnL
        if concentration > 0.80:
            top = max(pnl_by_instrument, key=pnl_by_instrument.get)
            return False, (
                f"Instrument PnL concentration: {top} = {concentration:.0%} of total profit"
            )
        return True, None

    def apply_all(
        self, trades: list[dict]
    ) -> tuple[bool, str | None]:
        """
        Runs all five checks. Returns (qualifies, first_failing_reason).
        Runs all checks so the log captures all issues but returns on first failure.
        """
        checks = [
            self.check_trade_concentration,
            self.check_weekly_activity,
            self.check_drawdown,
            self.check_hold_time,
            self.check_instrument_concentration,
        ]
        first_reason: str | None = None
        all_pass = True

        for check in checks:
            passes, reason = check(trades)
            if not passes:
                all_pass = False
                if first_reason is None:
                    first_reason = reason

        return all_pass, first_reason


# ---------------------------------------------------------------------------
# Combined qualification gate (Steps 1.4 + 1.5)
# ---------------------------------------------------------------------------

class QualificationGate:
    """
    Combines the monthly win rate check (1.4), strike system (1.4),
    and all disqualification filters (1.5) into one callable.
    """

    def __init__(self, config: dict, logger: StageLogger):
        self._config = config
        self._log = logger
        self._disq_filter = DisqualificationFilter(config)

    def evaluate(
        self, address: str, trades: list[dict], source: str = "hyperliquid"
    ) -> tuple[bool, list[dict], str | None]:
        """
        Returns (qualifies, monthly_windows, disqualification_reason_or_None).

        monthly_windows has strike_level set on each window.
        If disqualification_reason is None the wallet qualifies.
        """
        windows = build_monthly_windows(
            trades, self._config["lookback"]["window_days"]
        )

        # Require minimum trading span — wallet age alone is not enough
        if windows:
            span_ms = windows[-1]["window_end"] - windows[0]["window_start"]
            span_days = int(span_ms / (86_400 * 1_000))
            min_span = self._config["lookback"]["minimum_days"]
            if span_days < min_span:
                reason = f"Trading span {span_days} days < {min_span} day minimum"
                self._log.log_disqualified(address, reason)
                return False, windows, reason

        # Step 1.4: strike system
        qualifies_wr, windows = apply_strike_system(windows, self._config)
        if not qualifies_wr:
            yellow = sum(1 for w in windows if w["strike_level"] == 1)
            red = sum(1 for w in windows if w["strike_level"] == 2)
            reason = f"Strike system: {yellow} yellow, {red} red flags in {len(windows)} windows"
            self._log.log_disqualified(address, reason)
            return False, windows, reason

        # Log yellow flags even for passing wallets
        yellow_flags = sum(1 for w in windows if w["strike_level"] == 1)
        if yellow_flags:
            self._log.warning(f"{address[:10]}… — {yellow_flags} yellow flag(s) noted")

        # Step 1.5: disqualification filters
        passes_disq, disq_reason = self._disq_filter.apply_all(trades)
        if not passes_disq:
            self._log.log_disqualified(address, disq_reason)
            return False, windows, disq_reason

        return True, windows, None
