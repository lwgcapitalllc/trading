"""
Stage 1, Steps 1.7–1.8: Wallet Intelligence Report builder and exporter.

For each qualifying wallet builds the full profile described in the spec,
then exports to JSON, CSV, and a human-readable Markdown summary.
"""

from __future__ import annotations

import csv
import json
import math
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from run_logger import StageLogger


# ---------------------------------------------------------------------------
# Profile builder (Step 1.7)
# ---------------------------------------------------------------------------

def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _win_rate_trend(windows: list[dict]) -> str:
    """
    Determines whether monthly win rate is improving, stable, or declining.
    Uses linear regression slope on the last 3+ windows.
    """
    active = [w for w in windows if w["trade_count"] > 0]
    if len(active) < 2:
        return "insufficient_data"

    rates = [w["win_rate"] for w in active]
    n = len(rates)
    x_mean = (n - 1) / 2
    y_mean = _avg(rates)
    numerator = sum((i - x_mean) * (r - y_mean) for i, r in enumerate(rates))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return "stable"

    slope = numerator / denominator

    if slope > 0.01:
        return "improving"
    if slope < -0.01:
        return "declining"
    return "stable"


def _preferred_instruments(trades: list[dict], top_n: int = 5) -> list[dict]:
    """Returns top instruments by trade frequency, with per-instrument win rate."""
    by_instrument: dict[str, list] = defaultdict(list)
    for t in trades:
        by_instrument[t["instrument"]].append(t)

    results = []
    for instrument, t_list in sorted(by_instrument.items(), key=lambda x: -len(x[1])):
        wins = sum(1 for t in t_list if t["is_win"])
        results.append({
            "instrument": instrument,
            "trade_count": len(t_list),
            "win_rate": round(wins / len(t_list), 4) if t_list else 0.0,
            "total_pnl": round(sum(t["pnl"] for t in t_list), 4),
        })

    return results[:top_n]


def _preferred_days(trades: list[dict]) -> list[dict]:
    """Returns weekdays ranked by frequency (0=Monday, 6=Sunday)."""
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_counter: Counter = Counter(
        datetime.fromtimestamp(t["close_ts"] / 1000, tz=timezone.utc).weekday()
        for t in trades
    )
    return [
        {"day": day_names[d], "trade_count": count}
        for d, count in sorted(day_counter.items(), key=lambda x: -x[1])
    ]


def _typical_entry_hour(trades: list[dict]) -> int | None:
    """UTC hour of day with the most opening activity."""
    hours = []
    for t in trades:
        if t.get("open_ts"):
            h = datetime.fromtimestamp(t["open_ts"] / 1000, tz=timezone.utc).hour
            hours.append(h)
    if not hours:
        return None
    return Counter(hours).most_common(1)[0][0]


def _month_over_month_balance(trades: list[dict], initial: float = 10_000.0) -> list[dict]:
    """
    Returns starting balance for each 30-day window using cumulative PnL reconstruction.
    """
    if not trades:
        return []

    sorted_trades = sorted(trades, key=lambda t: t["close_ts"])
    window_ms = 30 * 86_400 * 1_000
    epoch_ms = sorted_trades[0]["close_ts"]
    cum_pnl = 0.0
    progression = []
    window_start = epoch_ms

    while window_start <= sorted_trades[-1]["close_ts"]:
        window_end = window_start + window_ms
        bucket = [t for t in sorted_trades if window_start <= t["close_ts"] < window_end]
        window_pnl = sum(t["pnl"] for t in bucket)
        start_bal = initial + cum_pnl
        cum_pnl += window_pnl

        dt = datetime.fromtimestamp(window_start / 1000, tz=timezone.utc)
        progression.append({
            "month_label": dt.strftime("%Y-%m"),
            "starting_balance": round(start_bal, 2),
            "ending_balance": round(initial + cum_pnl, 2),
            "window_pnl": round(window_pnl, 4),
        })
        window_start = window_end

    return progression


def build_wallet_profile(
    wallet: dict,
    trades: list[dict],
    windows: list[dict],
    score: dict,
    balance_stats: dict,
    yellow_flags: int = 0,
) -> dict:
    """
    Assembles the full wallet intelligence report as specified in Step 1.7.
    """
    wins = [t for t in trades if t["is_win"]]
    losses = [t for t in trades if not t["is_win"]]

    avg_win = _avg([t["pnl"] for t in wins])
    avg_loss = _avg([t["pnl"] for t in losses])
    rr = abs(avg_win / avg_loss) if avg_loss != 0 else None

    overall_win_rate = len(wins) / len(trades) if trades else 0.0

    hold_times = [t["hold_time_seconds"] for t in trades if t.get("hold_time_seconds") is not None]
    avg_hold_hours = round(_avg(hold_times) / 3600, 2) if hold_times else None

    return {
        # Identifiers
        "address": wallet["address"],
        "source": wallet.get("source", "hyperliquid"),
        "rank": score.get("rank"),
        "composite_score": score.get("composite_score"),
        "lookback_tier": score.get("lookback_tier"),
        "lookback_span_days": score.get("lookback_span_days"),

        # Balance & Growth
        "balance_metrics": {
            **balance_stats,
            "month_over_month_progression": _month_over_month_balance(trades),
        },

        # Performance Metrics
        "performance_metrics": {
            "total_trades": len(trades),
            "overall_win_rate": round(overall_win_rate, 4),
            "win_rate_trend": _win_rate_trend(windows),
            "average_win_usd": round(avg_win, 4),
            "average_loss_usd": round(avg_loss, 4),
            "average_rr_ratio": round(rr, 4) if rr is not None else None,
            "average_hold_hours": avg_hold_hours,
            "peak_drawdown_pct": balance_stats.get("peak_drawdown_pct"),
        },

        # Sub-scores
        "score_breakdown": {
            "win_rate_consistency": score.get("win_rate_consistency"),
            "risk_adjusted_return": score.get("risk_adjusted_return"),
            "exit_efficiency": score.get("exit_efficiency"),
            "trade_frequency": score.get("trade_frequency"),
            "instrument_day_consistency": score.get("instrument_day_consistency"),
        },

        # Behavioral Patterns
        "behavioral_patterns": {
            "preferred_instruments": _preferred_instruments(trades),
            "preferred_days": _preferred_days(trades),
            "typical_entry_hour_utc": _typical_entry_hour(trades),
            "average_hold_hours": avg_hold_hours,
            "exit_efficiency_score": score.get("exit_efficiency"),
        },

        # Strike / Flag Status
        "flags": {
            "yellow_flags": yellow_flags,
            "window_count": len(windows),
            "windows_below_threshold": sum(1 for w in windows if w["win_rate"] < 0.80 and w["trade_count"] > 0),
        },

        # Raw monthly windows (for manual validation)
        "monthly_windows": [
            {
                "month": datetime.fromtimestamp(
                    w["window_start"] / 1000, tz=timezone.utc
                ).strftime("%Y-%m"),
                "trade_count": w["trade_count"],
                "win_rate": round(w["win_rate"], 4),
                "total_pnl": w["total_pnl"],
                "active_weeks": w["active_weeks"],
                "strike_level": w["strike_level"],
            }
            for w in windows if w["trade_count"] > 0
        ],
    }


# ---------------------------------------------------------------------------
# Exporters (Step 1.8)
# ---------------------------------------------------------------------------

class StageReporter:
    def __init__(self, config: dict, logger: StageLogger):
        self._cfg = config
        self._log = logger
        self._reports_dir = Path(__file__).parent.parent / config["output"]["reports_dir"]
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        self._top_n: int = config["output"]["top_n_profiles"]
        self._shortlist_n: int = config["output"]["top_n_shortlist"]

    def _timestamp_str(self) -> str:
        return datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    def export_json(self, profiles: list[dict], stage: str):
        ts = self._timestamp_str()
        path = self._reports_dir / f"{stage}_top{len(profiles)}_{ts}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profiles, f, indent=2, default=str)
        self._log.info(f"JSON report → {path}")
        return path

    def export_csv(self, profiles: list[dict], stage: str):
        if not profiles:
            return None
        ts = self._timestamp_str()
        path = self._reports_dir / f"{stage}_top{len(profiles)}_{ts}.csv"

        flat_rows = []
        for p in profiles:
            pm = p.get("performance_metrics", {})
            bm = p.get("balance_metrics", {})
            sb = p.get("score_breakdown", {})
            bp = p.get("behavioral_patterns", {})
            flags = p.get("flags", {})
            top_inst = bp.get("preferred_instruments", [{}])[0] if bp.get("preferred_instruments") else {}

            flat_rows.append({
                "rank": p.get("rank"),
                "address": p.get("address"),
                "source": p.get("source"),
                "composite_score": p.get("composite_score"),
                "lookback_tier": p.get("lookback_tier"),
                "lookback_span_days": p.get("lookback_span_days"),
                "starting_balance": bm.get("starting_balance"),
                "ending_balance": bm.get("ending_balance"),
                "net_growth_pct": bm.get("net_growth_pct"),
                "peak_balance": bm.get("peak_balance"),
                "lowest_balance": bm.get("lowest_balance"),
                "total_trades": pm.get("total_trades"),
                "overall_win_rate": pm.get("overall_win_rate"),
                "win_rate_trend": pm.get("win_rate_trend"),
                "avg_win_usd": pm.get("average_win_usd"),
                "avg_loss_usd": pm.get("average_loss_usd"),
                "avg_rr_ratio": pm.get("average_rr_ratio"),
                "avg_hold_hours": pm.get("average_hold_hours"),
                "peak_drawdown_pct": pm.get("peak_drawdown_pct"),
                "score_win_rate_consistency": sb.get("win_rate_consistency"),
                "score_risk_adjusted": sb.get("risk_adjusted_return"),
                "score_exit_efficiency": sb.get("exit_efficiency"),
                "score_trade_frequency": sb.get("trade_frequency"),
                "score_inst_day_consistency": sb.get("instrument_day_consistency"),
                "top_instrument": top_inst.get("instrument"),
                "top_instrument_win_rate": top_inst.get("win_rate"),
                "yellow_flags": flags.get("yellow_flags"),
                "windows_below_threshold": flags.get("windows_below_threshold"),
            })

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(flat_rows[0].keys()))
            writer.writeheader()
            writer.writerows(flat_rows)

        self._log.info(f"CSV report  → {path}")
        return path

    def export_markdown_summary(self, profiles: list[dict], stage: str,
                                run_counts: dict) -> Path:
        ts = self._timestamp_str()
        path = self._reports_dir / f"{stage}_summary_{ts}.md"
        shortlist = profiles[: self._shortlist_n]

        lines = [
            f"# Stage {stage} — Candidate Pool Report",
            f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "## Run Summary",
            f"| Metric | Count |",
            f"|--------|-------|",
        ]
        for k, v in run_counts.items():
            lines.append(f"| {k.replace('_', ' ').title()} | {v} |")

        lines += [
            "",
            f"## Top {self._top_n} Ranked Wallets",
            "",
            "| Rank | Address | Score | Tier | Win Rate | Net Growth | Peak DD |",
            "|------|---------|-------|------|----------|------------|---------|",
        ]
        for p in profiles:
            pm = p.get("performance_metrics", {})
            bm = p.get("balance_metrics", {})
            lines.append(
                f"| {p.get('rank')} "
                f"| `{p.get('address', '')[:12]}…` "
                f"| {p.get('composite_score'):.1f} "
                f"| {p.get('lookback_tier')} "
                f"| {pm.get('overall_win_rate', 0)*100:.1f}% "
                f"| {bm.get('net_growth_pct', 0):.1f}% "
                f"| {bm.get('peak_drawdown_pct', 0):.1f}% |"
            )

        lines += [
            "",
            f"## Top {self._shortlist_n} Shortlist",
            "",
        ]
        for p in shortlist:
            pm = p.get("performance_metrics", {})
            bm = p.get("balance_metrics", {})
            bp = p.get("behavioral_patterns", {})
            sb = p.get("score_breakdown", {})
            flags = p.get("flags", {})
            insts = [i["instrument"] for i in bp.get("preferred_instruments", [])[:3]]

            lines += [
                f"### #{p.get('rank')} — `{p.get('address', '')}`",
                f"- **Score:** {p.get('composite_score'):.1f} | **Tier:** {p.get('lookback_tier')} ({p.get('lookback_span_days')}d)",
                f"- **Win Rate:** {pm.get('overall_win_rate', 0)*100:.1f}% ({pm.get('win_rate_trend')}) | **Trades:** {pm.get('total_trades')}",
                f"- **Net Growth:** {bm.get('net_growth_pct', 0):.1f}% | **Peak DD:** {bm.get('peak_drawdown_pct', 0):.1f}%",
                f"- **Avg Win/Loss:** ${pm.get('average_win_usd', 0):.2f} / ${abs(pm.get('average_loss_usd', 0)):.2f} | **R/R:** {pm.get('average_rr_ratio') or 'N/A'}",
                f"- **Preferred Instruments:** {', '.join(insts) or 'N/A'} | **Avg Hold:** {pm.get('average_hold_hours')}h",
                f"- **Yellow Flags:** {flags.get('yellow_flags', 0)}",
                "",
            ]

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self._log.info(f"Markdown report → {path}")
        return path

    def export_watchlist(self, watchlist: list[dict], stage: str):
        ts = self._timestamp_str()
        path = self._reports_dir / f"{stage}_watchlist_{ts}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(watchlist, f, indent=2, default=str)
        self._log.info(f"Watchlist → {path} ({len(watchlist)} short-history wallets)")
        return path

    def export_disqualified_log(self, disqualified: list[dict], stage: str):
        ts = self._timestamp_str()
        path = self._reports_dir / f"{stage}_disqualified_{ts}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(disqualified, f, indent=2, default=str)
        self._log.info(f"Disqualified log → {path} ({len(disqualified)} entries)")
        return path
