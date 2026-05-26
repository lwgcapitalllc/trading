"""
Stage 2 — Validate & Calibrate (Manual Validation Helper)
Steps 2.1 through 2.3.

This script does NOT make API calls. It reads Stage 1 results from the database
and generates a validation report to be reviewed manually before proceeding.

Usage:
  python run_stage2.py               # validate Stage 1 results
  python run_stage2.py --address 0x  # deep-dive a specific wallet
  python run_stage2.py --check-pool  # check pool size and recommend threshold adjustments

Output:
  Console report + reports/stage2_validation_*.txt
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))

import database as db
from run_logger import StageLogger

CONFIG_PATH = Path(__file__).parent / "config" / "config.json"
REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def validate_pool_size(config: dict, logger: StageLogger):
    """Step 2.1: Check pool size and recommend calibration if needed."""
    ranked = db.get_ranked_wallets(source="hyperliquid")
    n = len(ranked)
    logger.info(f"\nPool size check: {n} qualified Hyperliquid wallets")

    thin = config["pool_calibration"]["thin_pool_threshold"]
    large = config["pool_calibration"]["large_pool_threshold"]

    if n == 0:
        logger.warning("Pool is EMPTY. Stage 1 may not have completed or no wallets qualified.")
    elif n < thin:
        fallback_wr = config["pool_calibration"]["thin_pool_fallback_win_rate"]
        logger.warning(
            f"Pool is THIN ({n} < {thin}). "
            f"Recommendation: rerun Stage 1 with --win-rate {fallback_wr}"
        )
    elif n > large:
        tighter_dd = config["pool_calibration"]["large_pool_tighter_drawdown"]
        logger.warning(
            f"Pool is LARGE ({n} > {large}). "
            f"Recommendation: tighten max_drawdown to {tighter_dd:.0%} in config.json and rerun."
        )
    else:
        logger.info(f"Pool size OK ({thin} ≤ {n} ≤ {large})")

    return ranked


def spot_check_wallet(wallet_id: int, address: str, logger: StageLogger):
    """Step 2.2: Manual verification report for one wallet."""
    trades = db.get_trades(wallet_id)
    windows = db.get_monthly_windows(wallet_id)

    if not trades:
        logger.warning(f"No trades found for wallet {address}")
        return

    wins = [t for t in trades if t["is_win"]]
    losses = [t for t in trades if not t["is_win"]]
    overall_wr = len(wins) / len(trades) if trades else 0

    logger.info(f"\n{'─'*60}")
    logger.info(f"SPOT CHECK: {address}")
    logger.info(f"{'─'*60}")
    logger.info(f"  Total trades:      {len(trades)}")
    logger.info(f"  Wins / Losses:     {len(wins)} / {len(losses)}")
    logger.info(f"  Overall win rate:  {overall_wr:.1%}")
    logger.info(f"  Total PnL:         {sum(t['pnl'] for t in trades):.2f}")
    logger.info(f"  Avg win:           {sum(t['pnl'] for t in wins)/len(wins):.2f}" if wins else "  Avg win:           N/A")
    logger.info(f"  Avg loss:          {sum(t['pnl'] for t in losses)/len(losses):.2f}" if losses else "  Avg loss:          N/A")

    logger.info(f"\n  Monthly Windows ({len(windows)} windows):")
    logger.info(f"  {'Month':<10} {'Trades':>8} {'Wins':>6} {'Win Rate':>10} {'PnL':>10} {'Strike':>8}")
    for w in windows:
        dt = datetime.fromtimestamp(w["window_start"] / 1000, tz=timezone.utc)
        strike_label = {0: "clean", 1: "yellow", 2: "RED"}.get(w["strike_level"], "?")
        logger.info(
            f"  {dt.strftime('%Y-%m'):<10} "
            f"{w['trade_count']:>8} "
            f"{w['win_count']:>6} "
            f"{w['win_rate']:>9.1%} "
            f"{w['total_pnl']:>10.2f} "
            f"{strike_label:>8}"
        )

    oldest_ts = min(t["close_ts"] for t in trades)
    newest_ts = max(t["close_ts"] for t in trades)
    oldest = datetime.fromtimestamp(oldest_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    newest = datetime.fromtimestamp(newest_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    logger.info(f"\n  Data range:  {oldest} → {newest}")
    logger.info(f"  Data gaps:   (check monthly windows for empty months)")


def check_score_calibration(ranked: list[dict], logger: StageLogger):
    """Step 2.3: Review if scoring weights are producing sensible rankings."""
    logger.info(f"\n{'─'*60}")
    logger.info("SCORE CALIBRATION CHECK")
    logger.info(f"{'─'*60}")
    logger.info(f"{'Rank':>5} {'Score':>7} {'WR Cons':>8} {'Risk Adj':>9} {'Exit Eff':>9} {'Freq':>6} {'Pattern':>8} Address")

    for w in ranked[:10]:
        logger.info(
            f"{w.get('rank', 'N/A'):>5} "
            f"{w['composite_score']:>7.1f} "
            f"{w.get('win_rate_consistency', 0):>8.1f} "
            f"{w.get('risk_adjusted_return', 0):>9.1f} "
            f"{w.get('exit_efficiency', 0):>9.1f} "
            f"{w.get('trade_frequency', 0):>6.1f} "
            f"{w.get('instrument_day_consistency', 0):>8.1f} "
            f"{w['address'][:16]}…"
        )

    if len(ranked) >= 2:
        top = ranked[0]["composite_score"]
        bottom = ranked[-1]["composite_score"]
        spread = top - bottom
        logger.info(f"\nScore spread: {spread:.1f} points (top={top:.1f}, bottom={bottom:.1f})")
        if spread < 10:
            logger.warning("Score spread is very tight — scoring weights may not be differentiating well")
        elif spread > 60:
            logger.warning("Score spread is very wide — check for outliers in the data")
        else:
            logger.info("Score spread looks healthy")


def run_stage2(config: dict, target_address: str = None, check_pool_only: bool = False):
    logger = StageLogger("2-validate")
    logger.info("Stage 2 — Validate & Calibrate")
    logger.info("(This is a read-only validation pass — no API calls made)")

    db.init_db()

    ranked = validate_pool_size(config, logger)

    if check_pool_only:
        logger.print_summary()
        return

    if not ranked:
        logger.warning("No ranked wallets to validate. Run Stage 1 first.")
        logger.print_summary()
        return

    if target_address:
        # Spot-check a specific wallet
        wallet_id = db.get_wallet_id(target_address, "hyperliquid")
        if not wallet_id:
            logger.error(f"Wallet not found in DB: {target_address}")
        else:
            spot_check_wallet(wallet_id, target_address, logger)
    else:
        # Default: spot-check top 5 (Step 2.2)
        logger.info(f"\nSpot checking top 5 wallets (Step 2.2)…")
        top5 = ranked[:5]
        for w in top5:
            spot_check_wallet(w["wallet_id"], w["address"], logger)

    # Step 2.3: Score calibration review
    check_score_calibration(ranked, logger)

    logger.info("\nManual validation checklist:")
    logger.info("  [ ] Win rates match expectations from spot checks")
    logger.info("  [ ] No obvious data gaps in monthly windows")
    logger.info("  [ ] Score rankings reflect genuine quality differences")
    logger.info("  [ ] No single wallet dominates via one instrument/trade")
    logger.info("  [ ] Proceed to Stage 3 once satisfied")

    logger.print_summary()


def main():
    parser = argparse.ArgumentParser(description="Stage 2 — Manual validation helper")
    parser.add_argument("--address", type=str, default=None,
                        help="Spot-check a specific wallet address")
    parser.add_argument("--check-pool", action="store_true",
                        help="Only check pool size and threshold recommendations")
    args = parser.parse_args()

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    run_stage2(config, target_address=args.address, check_pool_only=args.check_pool)


if __name__ == "__main__":
    main()
