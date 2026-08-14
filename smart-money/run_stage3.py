"""
Stage 3 — Solana & Ethereum On-Chain Scanner
Independently rerunnable. Steps 3.1 through 3.7.

Prerequisites: set API keys as environment variables (see scanner/solana.py and scanner/ethereum.py).
Merges with Stage 1 results and produces a unified crypto candidate pool.

Usage:
  python run_stage3.py
  python run_stage3.py --dry-run    # Use existing DB data, skip API
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import database as db
from profiler.filters import QualificationGate
from profiler.hyperliquid_profiler import HyperliquidProfiler
from profiler.reporter import StageReporter, build_wallet_profile
from profiler.scorer import CompositeScorer
from run_logger import StageLogger
from scanner.ethereum import EthereumScanner
from scanner.solana import SolanaScanner

CONFIG_PATH = Path(__file__).parent / "config" / "config.json"


def run_stage3(config: dict, dry_run: bool = False) -> list[dict]:
    logger = StageLogger("3-solana-eth")
    run_id = db.start_run("stage3")
    logger.info("Stage 3 — Solana & Ethereum On-Chain starting")

    db.init_db()

    gate = QualificationGate(config, logger)
    scorer = CompositeScorer(config, logger)

    all_qualifying: list[dict] = []

    for source_name, scanner_cls in [("solana", SolanaScanner), ("ethereum", EthereumScanner)]:
        scanner = scanner_cls(config, logger)
        candidates = scanner.scan()
        logger.info(f"{source_name}: {len(candidates)} candidates from scanner")

        for wallet in candidates:
            address = wallet["address"]
            trades = wallet.get("trades", [])

            if not trades:
                reason = "No trades after parsing"
                db.log_disqualified(address, source_name, reason)
                continue

            wallet_id = db.upsert_wallet(
                address=address,
                source=source_name,
                trade_count=len(trades),
                account_age_days=wallet.get("account_age_days"),
                first_seen_ts=wallet.get("first_seen_ts"),
            )
            db.insert_trades(wallet_id, trades)

            qualifies, windows, disq_reason = gate.evaluate(address, trades, source=source_name)
            db.insert_monthly_windows(wallet_id, windows)

            if not qualifies:
                db.log_disqualified(address, source_name, disq_reason)
                continue

            score = scorer.compute(trades, windows)
            all_qualifying.append(
                {
                    "wallet": {**wallet, "id": wallet_id, "source": source_name},
                    "trades": trades,
                    "windows": windows,
                    "score": score,
                    "yellow_flags": sum(1 for w in windows if w["strike_level"] == 1),
                }
            )

    # Step 3.7: Merge with Stage 1 (Hyperliquid) and re-rank
    hl_wallets = db.get_ranked_wallets(source="hyperliquid")
    logger.info(
        f"Merging {len(all_qualifying)} new on-chain wallets with "
        f"{len(hl_wallets)} Hyperliquid wallets"
    )

    # Re-rank all crypto wallets together
    all_qualifying.sort(key=lambda e: e["score"]["composite_score"], reverse=True)
    for i, e in enumerate(all_qualifying, 1):
        e["score"]["rank"] = i
        wallet_id = e["wallet"]["id"]
        db.upsert_score(
            wallet_id,
            {
                "win_rate_consistency": e["score"]["win_rate_consistency"],
                "risk_adjusted_return": e["score"]["risk_adjusted_return"],
                "exit_efficiency": e["score"]["exit_efficiency"],
                "trade_frequency": e["score"]["trade_frequency"],
                "instrument_day_consistency": e["score"]["instrument_day_consistency"],
                "composite_score": e["score"]["composite_score"],
                "rank": e["score"]["rank"],
                "lookback_tier": e["score"]["lookback_tier"],
            },
        )

    # Build profiles for top N
    profiler = HyperliquidProfiler(config, logger)
    top_n = config["output"]["top_n_profiles"]
    profiles: list[dict] = []
    for entry in all_qualifying[:top_n]:
        balance_series = profiler.reconstruct_balance_series(entry["trades"])
        balance_stats = profiler.compute_balance_stats(balance_series)
        profile = build_wallet_profile(
            wallet=entry["wallet"],
            trades=entry["trades"],
            windows=entry["windows"],
            score=entry["score"],
            balance_stats=balance_stats,
            yellow_flags=entry.get("yellow_flags", 0),
        )
        profiles.append(profile)

    reporter = StageReporter(config, logger)
    run_counts = {"total_qualified": len(all_qualifying), "profiles_built": len(profiles)}
    reporter.export_json(profiles, stage="stage3")
    reporter.export_csv(profiles, stage="stage3")
    reporter.export_markdown_summary(profiles, stage="stage3", run_counts=run_counts)

    db.finish_run(
        run_id,
        counts={
            "total_qualified": len(all_qualifying),
            "total_scanned": len(all_qualifying),
        },
    )
    logger.print_summary()
    return profiles


def main():
    parser = argparse.ArgumentParser(description="Run Stage 3 — Solana & Ethereum")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(Path(__file__).parent / "config" / "config.json", encoding="utf-8") as f:
        config = json.load(f)

    run_stage3(config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
