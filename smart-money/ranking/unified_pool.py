"""
Stage 5, Steps 5.1–5.3: Unified candidate pool construction and final report.

Merges all sources (crypto wallets + forex accounts) from the database,
applies market transparency weighting, re-ranks the unified pool,
and generates the final structured report.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

import database as db
from run_logger import StageLogger

# ---------------------------------------------------------------------------
# Transparency weighting
# ---------------------------------------------------------------------------

CRYPTO_SOURCES = {"hyperliquid", "solana", "ethereum"}
FOREX_SOURCES = {"myfxbook", "fx_blue"}


def _apply_transparency_weight(score: float, source: str, config: dict) -> float:
    """
    Applies market transparency multiplier.
    Crypto is weighted 1.0 (blockchain forced transparency).
    Forex is weighted 0.85 (opt-in survivorship bias risk).
    Weights are configurable.
    """
    weights = config["forex"]
    if source in CRYPTO_SOURCES:
        return round(score * weights["crypto_transparency_weight"], 2)
    return round(score * weights["forex_transparency_weight"], 2)


# ---------------------------------------------------------------------------
# Unified pool builder
# ---------------------------------------------------------------------------


class UnifiedPool:
    def __init__(self, config: dict, logger: StageLogger):
        self._cfg = config
        self._log = logger
        self._reports_dir = Path(__file__).parent.parent / config["output"]["reports_dir"]
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    def _load_all_scored_wallets(self) -> list[dict]:
        """Loads all scored wallets from the database across all sources."""
        return db.get_ranked_wallets()

    def build(self) -> list[dict]:
        """
        Step 5.1: Merge all sources, apply transparency weights, re-rank.
        Returns ranked unified pool.
        """
        all_wallets = self._load_all_scored_wallets()
        self._log.info(f"Loaded {len(all_wallets)} scored wallets from all sources")

        if not all_wallets:
            self._log.warning("No scored wallets found in database. Run Stages 1–4 first.")
            return []

        # Apply transparency weighting
        for w in all_wallets:
            adjusted = _apply_transparency_weight(w["composite_score"], w["source"], self._cfg)
            w["adjusted_composite_score"] = adjusted

        # Re-rank by adjusted score
        all_wallets.sort(key=lambda w: w["adjusted_composite_score"], reverse=True)
        for i, w in enumerate(all_wallets, 1):
            w["unified_rank"] = i

        return all_wallets

    def _source_breakdown(self, pool: list[dict]) -> dict:
        breakdown: dict[str, int] = {}
        for w in pool:
            breakdown[w["source"]] = breakdown.get(w["source"], 0) + 1
        return breakdown

    def generate_final_report(self, pool: list[dict]) -> dict:
        """
        Step 5.2: Generates the structured final report dict.
        """
        if not pool:
            return {"error": "No qualifying candidates in unified pool"}

        top_n = self._cfg["output"]["top_n_profiles"]
        shortlist_n = self._cfg["output"]["top_n_shortlist"]
        top_20 = pool[:top_n]
        shortlist = pool[:shortlist_n]
        crypto_wallets = [w for w in pool if w["source"] in CRYPTO_SOURCES]
        forex_accounts = [w for w in pool if w["source"] in FOREX_SOURCES]

        report = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "summary": {
                "total_sources_scanned": len(set(w["source"] for w in pool)),
                "total_qualifying_candidates": len(pool),
                "breakdown_by_source": self._source_breakdown(pool),
            },
            "top_20_unified_rankings": [
                {
                    "unified_rank": w["unified_rank"],
                    "address": w["address"],
                    "source": w["source"],
                    "market": "crypto" if w["source"] in CRYPTO_SOURCES else "forex",
                    "composite_score": w["composite_score"],
                    "adjusted_composite_score": w["adjusted_composite_score"],
                    "lookback_tier": w["lookback_tier"],
                    "trade_count": w["trade_count"],
                    "account_age_days": w["account_age_days"],
                }
                for w in top_20
            ],
            "shortlist_top_5": [
                {
                    "unified_rank": w["unified_rank"],
                    "address": w["address"],
                    "source": w["source"],
                    "market": "crypto" if w["source"] in CRYPTO_SOURCES else "forex",
                    "composite_score": w["composite_score"],
                    "adjusted_composite_score": w["adjusted_composite_score"],
                    "lookback_tier": w["lookback_tier"],
                    "score_breakdown": {
                        "win_rate_consistency": w.get("win_rate_consistency"),
                        "risk_adjusted_return": w.get("risk_adjusted_return"),
                        "exit_efficiency": w.get("exit_efficiency"),
                        "trade_frequency": w.get("trade_frequency"),
                        "instrument_day_consistency": w.get("instrument_day_consistency"),
                    },
                }
                for w in shortlist
            ],
            "market_breakdown": {
                "top_10_crypto": [
                    {
                        "unified_rank": w["unified_rank"],
                        "address": w["address"],
                        "source": w["source"],
                        "adjusted_score": w["adjusted_composite_score"],
                    }
                    for w in crypto_wallets[:10]
                ],
                "top_10_forex": [
                    {
                        "unified_rank": w["unified_rank"],
                        "address": w["address"],
                        "source": w["source"],
                        "adjusted_score": w["adjusted_composite_score"],
                    }
                    for w in forex_accounts[:10]
                ],
                "top_5_overall": [
                    {
                        "unified_rank": w["unified_rank"],
                        "address": w["address"],
                        "market": "crypto" if w["source"] in CRYPTO_SOURCES else "forex",
                        "source": w["source"],
                        "adjusted_score": w["adjusted_composite_score"],
                    }
                    for w in shortlist
                ],
            },
        }
        return report

    def export_json(self, report: dict) -> Path:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = self._reports_dir / f"stage5_final_report_{ts}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        self._log.info(f"Final JSON report → {path}")
        return path

    def export_csv(self, pool: list[dict]) -> Path:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = self._reports_dir / f"stage5_unified_pool_{ts}.csv"
        if not pool:
            return path

        fieldnames = [
            "unified_rank",
            "address",
            "source",
            "market",
            "composite_score",
            "adjusted_composite_score",
            "lookback_tier",
            "trade_count",
            "account_age_days",
            "win_rate_consistency",
            "risk_adjusted_return",
            "exit_efficiency",
            "trade_frequency",
            "instrument_day_consistency",
        ]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for w in pool:
                writer.writerow(
                    {
                        **w,
                        "market": "crypto" if w["source"] in CRYPTO_SOURCES else "forex",
                    }
                )
        self._log.info(f"Unified pool CSV → {path}")
        return path

    def export_markdown(self, report: dict, pool: list[dict]) -> Path:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = self._reports_dir / f"stage5_summary_{ts}.md"
        summary = report.get("summary", {})
        shortlist = report.get("shortlist_top_5", [])
        market = report.get("market_breakdown", {})

        lines = [
            "# Smart Money Replication System — Final Candidate Pool Report",
            f"**Generated:** {report.get('generated_at', '')}",
            "",
            "## Summary",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Qualifying Candidates | {summary.get('total_qualifying_candidates', 0)} |",
            f"| Sources Active | {summary.get('total_sources_scanned', 0)} |",
        ]
        for src, count in summary.get("breakdown_by_source", {}).items():
            lines.append(f"| {src.title()} Candidates | {count} |")

        lines += [
            "",
            "## Top 20 Unified Rankings",
            "",
            "| Rank | Address | Market | Source | Adj. Score | Tier | Trades |",
            "|------|---------|--------|--------|------------|------|--------|",
        ]
        for w in report.get("top_20_unified_rankings", []):
            lines.append(
                f"| {w['unified_rank']} "
                f"| `{w['address'][:12]}…` "
                f"| {w['market']} "
                f"| {w['source']} "
                f"| {w['adjusted_composite_score']:.1f} "
                f"| {w['lookback_tier']} "
                f"| {w['trade_count']} |"
            )

        lines += [
            "",
            "## Final Shortlist — Top 5",
            "",
        ]
        for c in shortlist:
            sb = c.get("score_breakdown", {})
            lines += [
                f"### #{c['unified_rank']} — `{c['address']}`",
                f"- **Market:** {c['market']} | **Source:** {c['source']}",
                f"- **Adj. Score:** {c['adjusted_composite_score']:.1f} | **Tier:** {c['lookback_tier']}",
                f"- Win Rate Consistency: {sb.get('win_rate_consistency', 'N/A')} | "
                f"Risk-Adjusted Return: {sb.get('risk_adjusted_return', 'N/A')}",
                f"- Exit Efficiency: {sb.get('exit_efficiency', 'N/A')} | "
                f"Trade Frequency: {sb.get('trade_frequency', 'N/A')} | "
                f"Pattern Consistency: {sb.get('instrument_day_consistency', 'N/A')}",
                "",
            ]

        lines += [
            "## Market Breakdown",
            "",
            "### Top 10 Crypto Wallets",
            "| Rank | Address | Source | Adj. Score |",
            "|------|---------|--------|------------|",
        ]
        for w in market.get("top_10_crypto", []):
            lines.append(
                f"| {w['unified_rank']} | `{w['address'][:12]}…` "
                f"| {w['source']} | {w['adjusted_score']:.1f} |"
            )

        lines += [
            "",
            "### Top 10 Forex Accounts",
            "| Rank | Address | Source | Adj. Score |",
            "|------|---------|--------|------------|",
        ]
        for w in market.get("top_10_forex", []):
            lines.append(
                f"| {w['unified_rank']} | `{w['address'][:12]}…` "
                f"| {w['source']} | {w['adjusted_score']:.1f} |"
            )

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        self._log.info(f"Markdown summary → {path}")
        return path
